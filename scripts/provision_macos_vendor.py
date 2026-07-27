#!/usr/bin/env python3
"""Provision the exact macOS runtime archives declared by the vendor lock.

The release runner is intentionally treated as empty.  Every third-party
runtime is downloaded from its immutable HTTPS URL, checked against the lock,
and safely extracted before its resolved path is exported to later build
steps.  The first-party PyInstaller backend is built from the checked-out
commit and is therefore not provisioned here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import shutil
import sys
import tarfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any


TARGET = "aarch64-apple-darwin"
FIRST_PARTY_ID = "opswitness-backend"
COMPONENT_OUTPUTS = {
    "node": ("OPSWITNESS_NODE_BIN", "executable"),
    "paperclip": ("OPSWITNESS_PAPERCLIP_DIR", "directory"),
    "aioncore": ("OPSWITNESS_AIONCORE_DIR", "directory"),
    "codex": ("OPSWITNESS_CODEX_BIN", "executable"),
}
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 8 * 1024 * 1024 * 1024
SHA256_LENGTH = 64

Fetcher = Callable[[str, Path], None]


class ProvisionError(ValueError):
    """The locked runtime cannot be provisioned without weakening a gate."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: object, *, label: str, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ProvisionError(f"{label} must be a non-empty relative path")
    if allow_dot and value == ".":
        return value
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ProvisionError(f"{label} is unsafe: {value!r}")
    return parsed.as_posix()


def _immutable_https_url(value: object, *, archive_type: str, component: str) -> str:
    if not isinstance(value, str):
        raise ProvisionError(f"{component}: source_url is required")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProvisionError(
            f"{component}: source_url must be an immutable HTTPS URL without credentials, "
            "query, or fragment"
        )
    filename = PurePosixPath(parsed.path).name
    if not filename or filename.casefold() in {"releases", "download", "dist"}:
        raise ProvisionError(f"{component}: source_url must identify one exact artifact")
    if archive_type == "tar.gz" and not (filename.endswith(".tar.gz") or filename.endswith(".tgz")):
        raise ProvisionError(f"{component}: tar.gz source_url has an unexpected filename")
    return value


def _component_provision(component: dict[str, Any]) -> dict[str, Any]:
    identifier = str(component.get("id") or "<unknown>")
    provision = component.get("provision")
    if not isinstance(provision, dict):
        raise ProvisionError(f"{identifier}: provision metadata is required")
    expected = {
        "archive_type",
        "root_path",
        "output_kind",
        "entrypoint",
        "required_paths",
    }
    if set(provision) != expected:
        raise ProvisionError(f"{identifier}: provision fields must be exactly {sorted(expected)}")
    archive_type = provision.get("archive_type")
    if archive_type not in {"tar.gz", "raw"}:
        raise ProvisionError(f"{identifier}: archive_type must be tar.gz or raw")
    root_path = _safe_relative(
        provision.get("root_path"),
        label=f"{identifier}.provision.root_path",
        allow_dot=True,
    )
    output_kind = provision.get("output_kind")
    expected_output = COMPONENT_OUTPUTS.get(identifier, (None, None))[1]
    if output_kind != expected_output:
        raise ProvisionError(
            f"{identifier}: output_kind must be {expected_output!r}, found {output_kind!r}"
        )
    entrypoint = _safe_relative(
        provision.get("entrypoint"),
        label=f"{identifier}.provision.entrypoint",
    )
    required_paths = provision.get("required_paths")
    if not isinstance(required_paths, list) or not required_paths:
        raise ProvisionError(f"{identifier}: provision.required_paths must not be empty")
    normalized_required = [
        _safe_relative(path, label=f"{identifier}.provision.required_paths")
        for path in required_paths
    ]
    if entrypoint not in normalized_required:
        raise ProvisionError(f"{identifier}: provision.required_paths must include the entrypoint")
    if archive_type == "raw" and root_path != ".":
        raise ProvisionError(f"{identifier}: raw artifacts require root_path='.'")
    return {
        "archive_type": archive_type,
        "root_path": root_path,
        "output_kind": output_kind,
        "entrypoint": entrypoint,
        "required_paths": normalized_required,
    }


def validate_lock(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProvisionError(f"vendor lock is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ProvisionError("vendor lock must use schema_version 1")
    if payload.get("target") != TARGET:
        raise ProvisionError(f"vendor lock target must be {TARGET}")
    components = payload.get("components")
    if not isinstance(components, list):
        raise ProvisionError("vendor lock components must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for raw_component in components:
        if not isinstance(raw_component, dict):
            raise ProvisionError("vendor lock components must be objects")
        identifier = raw_component.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in by_id:
            raise ProvisionError(f"invalid or duplicate vendor component: {identifier!r}")
        by_id[identifier] = raw_component

    expected = {FIRST_PARTY_ID, *COMPONENT_OUTPUTS}
    if set(by_id) != expected:
        raise ProvisionError(
            "vendor lock component set does not match the desktop runtime; "
            f"missing={sorted(expected - set(by_id))} "
            f"unexpected={sorted(set(by_id) - expected)}"
        )

    backend = by_id[FIRST_PARTY_ID]
    if backend.get("provision") is not None:
        raise ProvisionError("opswitness-backend must be built from source, not downloaded")

    for identifier in COMPONENT_OUTPUTS:
        component = by_id[identifier]
        if component.get("redistribution_review") != "approved":
            raise ProvisionError(f"{identifier}: redistribution review is not approved")
        digest = component.get("upstream_sha256")
        if not isinstance(digest, str) or len(digest) != SHA256_LENGTH:
            raise ProvisionError(f"{identifier}: upstream_sha256 is required")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ProvisionError(f"{identifier}: upstream_sha256 is invalid") from exc
        if digest != digest.lower():
            raise ProvisionError(f"{identifier}: upstream_sha256 must be lowercase")
        provision = _component_provision(component)
        _immutable_https_url(
            component.get("source_url"),
            archive_type=str(provision["archive_type"]),
            component=identifier,
        )
    return payload


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OpsWitness-release-provisioner/1"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    written = 0
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("xb") as output,
        ):
            final_url = urllib.parse.urlsplit(response.geturl())
            if final_url.scheme != "https":
                raise ProvisionError("vendor download redirected away from HTTPS")
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_ARCHIVE_BYTES:
                    raise ProvisionError("vendor archive exceeds the 4 GiB safety limit")
                output.write(chunk)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _safe_link_target(member: tarfile.TarInfo) -> None:
    link = PurePosixPath(member.linkname)
    if link.is_absolute():
        raise ProvisionError(f"archive link is absolute: {member.name!r}")
    base = PurePosixPath(member.name).parent if member.issym() else PurePosixPath()
    normalized = posixpath.normpath((base / link).as_posix())
    if normalized == ".." or normalized.startswith("../"):
        raise ProvisionError(f"archive link escapes extraction root: {member.name!r}")


def _extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as bundle:
        total = 0
        members = bundle.getmembers()
        for member in members:
            if member.name in {".", "./"} and member.isdir():
                continue
            _safe_relative(member.name, label="archive member")
            if member.isreg():
                total += member.size
                if total > MAX_EXTRACTED_BYTES:
                    raise ProvisionError("vendor archive exceeds the 8 GiB extraction limit")
            elif member.isdir():
                pass
            elif member.issym() or member.islnk():
                _safe_link_target(member)
            else:
                raise ProvisionError(
                    f"vendor archive contains a forbidden entry type: {member.name!r}"
                )
        bundle.extractall(destination, members=members, filter="data")


def _contained(path: Path, root: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ProvisionError(f"{label} is unavailable: {path}") from exc
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ProvisionError(f"{label} escapes the provisioned component: {path}") from exc
    return resolved


def provision(
    lock_path: Path,
    destination: Path,
    *,
    fetcher: Fetcher = _download,
) -> dict[str, dict[str, str]]:
    payload = validate_lock(lock_path)
    if destination.exists() and any(destination.iterdir()):
        raise ProvisionError(f"provision destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, dict[str, str]] = {}
    components = {str(component["id"]): component for component in payload["components"]}
    for identifier, (environment_name, expected_kind) in COMPONENT_OUTPUTS.items():
        component = components[identifier]
        provision_data = _component_provision(component)
        component_root = destination / identifier
        component_root.mkdir()
        archive_type = str(provision_data["archive_type"])
        source_url = _immutable_https_url(
            component["source_url"],
            archive_type=archive_type,
            component=identifier,
        )
        filename = PurePosixPath(urllib.parse.urlsplit(source_url).path).name
        archive = component_root / filename
        fetcher(source_url, archive)
        actual_digest = sha256(archive)
        if actual_digest != component["upstream_sha256"]:
            raise ProvisionError(
                f"{identifier}: downloaded SHA-256 mismatch; "
                f"expected={component['upstream_sha256']} actual={actual_digest}"
            )

        extracted = component_root / "extracted"
        extracted.mkdir()
        if archive_type == "tar.gz":
            _extract_tar(archive, extracted)
        else:
            raw_name = str(provision_data["entrypoint"])
            raw_path = extracted.joinpath(*PurePosixPath(raw_name).parts)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, raw_path)
            raw_path.chmod(0o755)

        root_path = str(provision_data["root_path"])
        root = (
            extracted if root_path == "." else extracted.joinpath(*PurePosixPath(root_path).parts)
        )
        root = _contained(root, extracted, label=f"{identifier} root")
        if not root.is_dir():
            raise ProvisionError(f"{identifier}: provisioned root is not a directory")
        entrypoint = _contained(
            root.joinpath(*PurePosixPath(str(provision_data["entrypoint"])).parts),
            root,
            label=f"{identifier} entrypoint",
        )
        for required in provision_data["required_paths"]:
            _contained(
                root.joinpath(*PurePosixPath(str(required)).parts),
                root,
                label=f"{identifier} required path",
            )
        if expected_kind == "executable":
            if not entrypoint.is_file():
                raise ProvisionError(f"{identifier}: entrypoint is not a file")
            entrypoint.chmod(entrypoint.stat().st_mode | 0o111)
            output = entrypoint
        else:
            output = root
        resolved[identifier] = {
            "environment": environment_name,
            "path": str(output),
            "source_url": source_url,
            "upstream_sha256": actual_digest,
        }
    return resolved


def _write_github_env(path: Path, resolved: dict[str, dict[str, str]]) -> None:
    lines = []
    for identifier in COMPONENT_OUTPUTS:
        record = resolved[identifier]
        value = record["path"]
        if "\n" in value or "\r" in value:
            raise ProvisionError("provisioned path contains a newline")
        lines.append(f"{record['environment']}={value}\n")
    with path.open("a", encoding="utf-8") as output:
        output.writelines(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        validate_lock(args.lock)
        if args.validate_only:
            print("vendor provisioning lock is complete")
            return 0
        if args.destination is None:
            raise ProvisionError("--destination is required unless --validate-only is used")
        resolved = provision(args.lock, args.destination)
        if args.github_env is not None:
            _write_github_env(args.github_env, resolved)
        encoded = json.dumps(resolved, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
    except (OSError, ProvisionError, tarfile.TarError) as exc:
        print(f"vendor provisioning failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
