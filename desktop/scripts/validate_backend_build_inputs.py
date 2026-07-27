#!/usr/bin/env python3
"""Validate the immutable inputs used to freeze the desktop Python backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import stat
import sys
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


EXPECTED_DISTRIBUTION = "opswitness"
EXPECTED_PYTHON = (3, 12, 13)
EXPECTED_MACHINE = "arm64"
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})\Z")
PIN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.+!_-]*)\Z")
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class ValidationError(ValueError):
    """Raised when a build input is not immutable or does not match policy."""


@dataclass(frozen=True)
class LockedPackage:
    name: str
    version: str
    hashes: tuple[str, ...]


@dataclass(frozen=True)
class WheelIdentity:
    distribution: str
    version: str
    filename: str
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def assert_build_interpreter() -> None:
    actual_version = sys.version_info[:3]
    actual_machine = platform.machine()
    if platform.python_implementation() != "CPython":
        raise ValidationError("backend build requires CPython")
    if actual_version != EXPECTED_PYTHON:
        rendered = ".".join(str(part) for part in actual_version)
        raise ValidationError(
            f"backend build requires CPython 3.12.13 exactly; selected interpreter is {rendered}"
        )
    if actual_machine != EXPECTED_MACHINE:
        raise ValidationError(
            f"backend build requires native arm64 Python; selected interpreter is {actual_machine}"
        )


def _logical_requirement_records(contents: str) -> list[str]:
    records: list[str] = []
    current: list[str] = []
    for line_number, raw_line in enumerate(contents.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line[:1].isspace():
            if not current:
                raise ValidationError(
                    f"requirements lock has an orphan continuation at line {line_number}"
                )
        elif current:
            records.append(" ".join(current))
            current = []
        if stripped.endswith("\\"):
            stripped = stripped[:-1].rstrip()
        current.append(stripped)
    if current:
        records.append(" ".join(current))
    return records


def parse_requirements_lock(path: Path) -> dict[str, LockedPackage]:
    if not path.is_file() or path.is_symlink():
        raise ValidationError("requirements lock must be a regular non-symlink file")
    packages: dict[str, LockedPackage] = {}
    for record in _logical_requirement_records(path.read_text(encoding="utf-8")):
        try:
            tokens = shlex.split(record)
        except ValueError as exc:
            raise ValidationError(f"invalid requirements lock record: {record}") from exc
        if len(tokens) < 2:
            raise ValidationError(f"requirement has no SHA-256 hash: {record}")
        pin_match = PIN_RE.fullmatch(tokens[0])
        if pin_match is None:
            raise ValidationError(f"requirement is not an exact name==version pin: {tokens[0]}")
        name = canonical_name(pin_match.group(1))
        version = pin_match.group(2)
        hashes: list[str] = []
        for token in tokens[1:]:
            hash_match = HASH_RE.fullmatch(token)
            if hash_match is None:
                raise ValidationError(f"unsupported requirements lock token: {token}")
            hashes.append(hash_match.group(1))
        if len(set(hashes)) != len(hashes):
            raise ValidationError(f"duplicate SHA-256 hash for locked package {name}")
        if name in packages:
            raise ValidationError(f"duplicate locked package: {name}")
        packages[name] = LockedPackage(name=name, version=version, hashes=tuple(hashes))

    if not packages:
        raise ValidationError("requirements lock is empty")
    if "opswitness" in packages:
        raise ValidationError("OpsWitness must come only from OPSWITNESS_RELEASE_WHEEL")
    pyinstaller = packages.get("pyinstaller")
    if pyinstaller is None or pyinstaller.version != "6.16.0":
        raise ValidationError("requirements lock must pin pyinstaller==6.16.0")
    if "mcp" not in packages:
        raise ValidationError("requirements lock must include the MCP runtime dependency graph")
    return packages


def _expected_wheel_version(tauri_config: Path) -> str:
    try:
        payload = json.loads(tauri_config.read_text(encoding="utf-8"))
        app_version = payload["version"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValidationError("unable to read the Tauri application version") from exc
    if not isinstance(app_version, str):
        raise ValidationError("Tauri application version must be a string")
    match = re.fullmatch(
        r"(?P<base>[0-9]+\.[0-9]+\.[0-9]+)"
        r"(?:-(?P<kind>alpha|beta|rc)\.(?P<number>[0-9]+))?",
        app_version,
    )
    if match is None:
        raise ValidationError(f"unsupported Tauri application version: {app_version}")
    if match.group("kind") is None:
        return match.group("base")
    kind = {"alpha": "a", "beta": "b", "rc": "rc"}[match.group("kind")]
    return f"{match.group('base')}{kind}{match.group('number')}"


def validate_wheel(
    path: Path,
    *,
    expected_version: str,
    expected_sha256: str | None,
) -> WheelIdentity:
    if not path.is_absolute():
        raise ValidationError("OPSWITNESS_RELEASE_WHEEL must be an absolute path")
    if path.is_symlink() or not path.is_file():
        raise ValidationError("OPSWITNESS_RELEASE_WHEEL must be a regular non-symlink file")
    if path.suffix != ".whl":
        raise ValidationError("OPSWITNESS_RELEASE_WHEEL must name a .whl artifact")
    expected_filename = f"{EXPECTED_DISTRIBUTION}-{expected_version}-py3-none-any.whl"
    if path.name != expected_filename:
        raise ValidationError(
            f"release wheel filename must be {expected_filename}, got {path.name}"
        )
    actual_sha256 = sha256_file(path)
    if expected_sha256:
        if SHA256_RE.fullmatch(expected_sha256) is None:
            raise ValidationError("OPSWITNESS_RELEASE_WHEEL_SHA256 must be exactly 64 hex digits")
        if actual_sha256 != expected_sha256.lower():
            raise ValidationError(
                "release wheel SHA-256 mismatch: "
                f"expected {expected_sha256.lower()}, got {actual_sha256}"
            )

    try:
        with zipfile.ZipFile(path) as archive:
            broken_member = archive.testzip()
            if broken_member is not None:
                raise ValidationError(f"release wheel CRC failed for {broken_member}")
            members = archive.namelist()
            for member_info in archive.infolist():
                member = member_info.filename
                candidate = Path(member)
                if candidate.is_absolute() or ".." in candidate.parts:
                    raise ValidationError(f"release wheel contains an unsafe path: {member}")
                if stat.S_ISLNK(member_info.external_attr >> 16):
                    raise ValidationError(f"release wheel contains a symlink: {member}")
                lowered = candidate.name.lower()
                customize_hook = any(
                    part == base or part.startswith(f"{base}.")
                    for part in (item.lower() for item in candidate.parts)
                    for base in ("sitecustomize", "usercustomize")
                )
                if lowered.endswith(".pth") or customize_hook:
                    raise ValidationError(
                        f"release wheel contains an import-path startup hook: {member}"
                    )
            metadata_members = [
                member for member in members if member.endswith(".dist-info/METADATA")
            ]
            if len(metadata_members) != 1:
                raise ValidationError("release wheel must contain exactly one METADATA file")
            metadata = BytesParser().parsebytes(archive.read(metadata_members[0]))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError("release wheel is not a valid wheel archive") from exc

    distribution = canonical_name(metadata.get("Name", ""))
    version = metadata.get("Version", "")
    if distribution != EXPECTED_DISTRIBUTION:
        raise ValidationError(
            f"release wheel distribution must be {EXPECTED_DISTRIBUTION}, got {distribution or '-'}"
        )
    if version != expected_version:
        raise ValidationError(
            f"release wheel version must match the app ({expected_version}), got {version or '-'}"
        )
    return WheelIdentity(
        distribution=distribution,
        version=version,
        filename=path.name,
        sha256=actual_sha256,
    )


def _reviewed_packages(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw_packages = payload.get("packages")
    if not isinstance(raw_packages, list):
        raise ValidationError("license review packages must be a list")
    reviewed: dict[str, dict[str, str]] = {}
    required_fields = {
        "name",
        "version",
        "license_expression",
        "source_url",
        "redistribution_review",
        "notice",
    }
    for raw_package in raw_packages:
        if not isinstance(raw_package, dict) or set(raw_package) != required_fields:
            raise ValidationError(
                "each license review package must contain only the required evidence fields"
            )
        if not all(isinstance(raw_package[field], str) for field in required_fields):
            raise ValidationError("license review evidence fields must be strings")
        name = canonical_name(raw_package["name"])
        if not name or name in reviewed:
            raise ValidationError(f"invalid or duplicate license review package: {name or '-'}")
        if raw_package["redistribution_review"] != "approved":
            raise ValidationError(f"license review is not approved for {name}")
        license_expression = raw_package["license_expression"].strip()
        if (
            not license_expression
            or license_expression.upper() in {"NOASSERTION", "NONE"}
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+(): -]*", license_expression) is None
        ):
            raise ValidationError(f"license expression is incomplete for {name}")
        source = urlsplit(raw_package["source_url"])
        if (
            source.scheme != "https"
            or not source.hostname
            or source.username is not None
            or source.password is not None
        ):
            raise ValidationError(f"license evidence source must use HTTPS for {name}")
        if not raw_package["notice"].strip():
            raise ValidationError(f"license notice evidence is empty for {name}")
        reviewed[name] = raw_package
    return reviewed


def validate_license_review(
    path: Path,
    *,
    requirements_path: Path,
    packages: dict[str, LockedPackage],
    mode: str,
) -> tuple[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ValidationError("license review must be a regular non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("license review is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValidationError("license review schema must be 1")
    expected_lock_sha256 = sha256_file(requirements_path)
    if payload.get("lock_sha256") != expected_lock_sha256:
        raise ValidationError("license review does not describe the current requirements lock")
    status = payload.get("review_status")
    if status not in {"incomplete", "approved"}:
        raise ValidationError("license review status must be incomplete or approved")
    if not isinstance(payload.get("notice"), str) or not payload["notice"].strip():
        raise ValidationError("license review notice must be non-empty")
    reviewed = _reviewed_packages(payload)
    for name, evidence in reviewed.items():
        locked = packages.get(name)
        if locked is None:
            raise ValidationError(f"license review contains package absent from lock: {name}")
        if evidence["version"] != locked.version:
            raise ValidationError(f"license review version does not match lock for {name}")

    if status == "approved":
        missing = sorted(set(packages) - set(reviewed))
        if missing:
            raise ValidationError(
                "approved license review is missing locked packages: " + ", ".join(missing)
            )
    if mode == "release" and status != "approved":
        raise ValidationError(
            "public release blocked: Python dependency license review is incomplete"
        )
    return status, sha256_file(path)


def write_provenance(
    path: Path,
    *,
    wheel: WheelIdentity,
    requirements_path: Path,
    packages: dict[str, LockedPackage],
    license_path: Path,
    license_status: str,
    license_sha256: str,
    mode: str,
) -> None:
    payload = {
        "schema": 1,
        "build_mode": mode,
        "python": {
            "implementation": "CPython",
            "version": ".".join(str(part) for part in EXPECTED_PYTHON),
            "architecture": EXPECTED_MACHINE,
        },
        "wheel": {
            "distribution": wheel.distribution,
            "version": wheel.version,
            "filename": wheel.filename,
            "sha256": wheel.sha256,
        },
        "requirements": {
            "filename": requirements_path.name,
            "sha256": sha256_file(requirements_path),
            "package_count": len(packages),
            "hashes_required": True,
        },
        "license_review": {
            "filename": license_path.name,
            "sha256": license_sha256,
            "status": license_status,
            "release_gate_enforced": mode == "release",
        },
        "source_isolation": {
            "release_wheel_only": True,
            "repository_source_on_import_path": False,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def finalize_provenance(
    *,
    input_path: Path,
    backend: Path,
    output: Path,
) -> None:
    if input_path.is_symlink() or not input_path.is_file():
        raise ValidationError("validated backend input provenance is missing")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("validated backend input provenance is invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != 1
        or payload.get("source_isolation")
        != {
            "release_wheel_only": True,
            "repository_source_on_import_path": False,
        }
    ):
        raise ValidationError("validated backend input provenance is incomplete")
    if backend.is_symlink() or not backend.is_file() or not os.access(backend, os.X_OK):
        raise ValidationError("frozen backend executable is missing or unsafe")
    payload["frozen_backend"] = {
        "build_completed": True,
        "filename": backend.name,
        "format": "pyinstaller-onedir",
        "sha256": sha256_file(backend),
        "size": backend.stat().st_size,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def validate_installed_package_set(
    installed_packages: dict[str, str],
    locked_packages: dict[str, LockedPackage],
) -> None:
    expected_packages = {name: package.version for name, package in locked_packages.items()}
    if installed_packages == expected_packages:
        return
    missing = sorted(set(expected_packages) - set(installed_packages))
    unexpected = sorted(set(installed_packages) - set(expected_packages))
    changed = sorted(
        name
        for name in set(expected_packages) & set(installed_packages)
        if expected_packages[name] != installed_packages[name]
    )
    details = []
    if missing:
        details.append("missing=" + ",".join(missing))
    if unexpected:
        details.append("unexpected=" + ",".join(unexpected))
    if changed:
        details.append("version_mismatch=" + ",".join(changed))
    raise ValidationError(
        "isolated environment does not exactly match requirements lock: " + "; ".join(details)
    )


def verify_installed_distribution(
    *,
    expected_version: str,
    repository: Path,
    locked_packages: dict[str, LockedPackage],
) -> None:
    from importlib import import_module
    from importlib.metadata import distribution, distributions

    repository = repository.resolve(strict=True)
    prefix = Path(sys.prefix).resolve(strict=True)
    for raw_entry in sys.path:
        if not raw_entry:
            raise ValidationError("unsafe current-directory entry found on Python import path")
        entry = Path(raw_entry)
        if entry.exists() and entry.resolve().is_relative_to(repository):
            raise ValidationError("repository path leaked into the backend build import path")

    installed = distribution(EXPECTED_DISTRIBUTION)
    installed_version = installed.version
    distribution_root = Path(str(installed.locate_file(""))).resolve(strict=True)
    console_entries = [
        entry
        for entry in installed.entry_points
        if entry.group == "console_scripts" and entry.name == "opswitness"
    ]

    if installed_version != expected_version:
        raise ValidationError(
            f"installed OpsWitness version must be {expected_version}, got {installed_version}"
        )
    if len(console_entries) != 1 or console_entries[0].value != "opswitness.cli:app":
        raise ValidationError("release wheel must expose opswitness = opswitness.cli:app")
    if not distribution_root.is_relative_to(prefix):
        raise ValidationError("installed OpsWitness did not load from the isolated environment")
    if distribution_root.is_relative_to(repository):
        raise ValidationError("repository source was imported into the backend build")

    installed_packages: dict[str, str] = {}
    for candidate in distributions():
        name = canonical_name(candidate.metadata.get("Name", ""))
        if not name or name in {"opswitness", "pip"}:
            continue
        if name in installed_packages:
            raise ValidationError(f"duplicate distribution in isolated environment: {name}")
        installed_packages[name] = candidate.version
    validate_installed_package_set(installed_packages, locked_packages)

    console_script = prefix / "bin" / "opswitness"
    if (
        console_script.is_symlink()
        or not console_script.is_file()
        or not os.access(console_script, os.X_OK)
    ):
        raise ValidationError("release wheel did not install a regular executable entrypoint")

    package = import_module("opswitness")
    module_path = Path(package.__file__ or "").resolve(strict=True)
    if not module_path.is_relative_to(prefix) or module_path.is_relative_to(repository):
        raise ValidationError("repository source was imported into the backend build")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inputs = subparsers.add_parser("inputs")
    inputs.add_argument("--wheel", required=True, type=Path)
    inputs.add_argument("--wheel-sha256")
    inputs.add_argument("--requirements", required=True, type=Path)
    inputs.add_argument("--license-review", required=True, type=Path)
    inputs.add_argument("--tauri-config", required=True, type=Path)
    inputs.add_argument("--mode", choices=("adhoc", "release"), required=True)
    inputs.add_argument("--provenance", required=True, type=Path)

    installed = subparsers.add_parser("installed")
    installed.add_argument("--repository", required=True, type=Path)
    installed.add_argument("--requirements", required=True, type=Path)
    installed.add_argument("--tauri-config", required=True, type=Path)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--input-provenance", required=True, type=Path)
    finalize.add_argument("--backend", required=True, type=Path)
    finalize.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        assert_build_interpreter()
        if args.command == "finalize":
            finalize_provenance(
                input_path=args.input_provenance,
                backend=args.backend,
                output=args.output,
            )
            return
        expected_version = _expected_wheel_version(args.tauri_config)
        if args.command == "installed":
            locked_packages = parse_requirements_lock(args.requirements)
            verify_installed_distribution(
                expected_version=expected_version,
                repository=args.repository,
                locked_packages=locked_packages,
            )
            return

        packages = parse_requirements_lock(args.requirements)
        wheel = validate_wheel(
            args.wheel,
            expected_version=expected_version,
            expected_sha256=args.wheel_sha256,
        )
        license_status, license_sha256 = validate_license_review(
            args.license_review,
            requirements_path=args.requirements,
            packages=packages,
            mode=args.mode,
        )
        write_provenance(
            args.provenance,
            wheel=wheel,
            requirements_path=args.requirements,
            packages=packages,
            license_path=args.license_review,
            license_status=license_status,
            license_sha256=license_sha256,
            mode=args.mode,
        )
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
