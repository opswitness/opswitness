#!/usr/bin/env python3
"""Create checksums and a fail-closed provenance manifest for release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path


BACKEND_PYTHON_VERSION = "3.12.13"
BACKEND_PYTHON_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    "20260510/cpython-3.12.13%2B20260510-aarch64-apple-darwin-install_only.tar.gz"
)
BACKEND_PYTHON_SHA256 = "5a30271f8d345a5b02b0c9e4e31e0f1e1455a8e4a04fba95cd9762472abc3b17"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def dirty_entries(root: Path) -> list[str]:
    output = git_output(root, "status", "--porcelain=v1", "--untracked-files=all")
    return [line for line in output.splitlines() if line]


def assert_clean_tree(root: Path) -> None:
    dirty = dirty_entries(root)
    if dirty:
        preview = ", ".join(dirty[:10])
        if len(dirty) > 10:
            preview += f", ... ({len(dirty)} entries)"
        raise ValueError(f"release build requires a clean Git tree: {preview}")
    result = subprocess.run(
        ["git", "diff", "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout or result.stderr).strip()
        raise ValueError(f"git diff --check failed: {detail}")


def release_identity(root: Path) -> tuple[str, str, str, str]:
    with (root / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    python_version = str(project["version"])
    if "a" not in python_version:
        raise ValueError(f"unsupported alpha Python version: {python_version}")
    base, alpha = python_version.rsplit("a", 1)
    if not alpha.isdigit():
        raise ValueError(f"unsupported alpha Python version: {python_version}")
    public_version = f"{base}-alpha.{alpha}"
    return str(project["name"]), python_version, public_version, f"v{public_version}"


def _created_at() -> str:
    epoch = os.getenv("SOURCE_DATE_EPOCH")
    if epoch is not None:
        moment = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    else:
        moment = datetime.now(timezone.utc)
    return moment.isoformat()


def _asset_files(dist: Path) -> list[Path]:
    excluded = {"SHA256SUMS", "build-manifest.json"}
    return sorted(
        [
            path
            for path in dist.iterdir()
            if path.is_file()
            and path.name not in excluded
            and (
                path.suffix in {".whl", ".dmg", ".sig"}
                or path.name.endswith(".tar.gz")
                or path.name.endswith(".spdx.json")
                or path.name
                in {
                    "THIRD_PARTY_NOTICES.txt",
                    "backend-build-provenance.json",
                    "macos-signing.json",
                    "updates-alpha-latest.json",
                    "vendor-lock.json",
                }
            )
        ],
        key=lambda path: path.name,
    )


def artifact_kind(path: Path) -> str:
    name = path.name
    if path.suffix == ".whl":
        return "wheel"
    if name.endswith("-macos-arm64.dmg"):
        return "macos_dmg"
    if name.endswith("-macos-arm64-updater.tar.gz"):
        return "macos_updater"
    if name.endswith("-macos-arm64-updater.tar.gz.sig"):
        return "updater_signature"
    if name.endswith(".tar.gz"):
        return "sdist"
    if name.endswith(".spdx.json"):
        return "sbom"
    if name == "THIRD_PARTY_NOTICES.txt":
        return "third_party_notices"
    if name == "backend-build-provenance.json":
        return "backend_build_provenance"
    if name == "macos-signing.json":
        return "macos_signing_metadata"
    if name == "updates-alpha-latest.json":
        return "updater_feed"
    if name == "vendor-lock.json":
        return "vendor_lock"
    return "release_asset"


def _read_json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def assert_vendor_lock(
    path: Path,
    *,
    require_complete: bool,
    allow_first_party_unresolved: bool = False,
    root: Path | None = None,
) -> dict[str, object]:
    payload = _read_json_object(path, label="vendor lock")
    if payload.get("schema_version") != 1:
        raise ValueError("vendor lock must use schema_version 1")
    if "components" in payload and payload.get("target") != "aarch64-apple-darwin":
        raise ValueError("desktop vendor lock target must be aarch64-apple-darwin")
    runtimes = payload.get("components", payload.get("runtimes"))
    if not isinstance(runtimes, list) or not runtimes:
        raise ValueError("vendor lock must contain at least one runtime")
    for runtime in runtimes:
        if not isinstance(runtime, dict):
            raise ValueError("vendor lock runtime entries must be objects")
        name = runtime.get("id", runtime.get("name", "<unknown>"))
        first_party = (
            name == "opswitness-backend"
            and runtime.get("source_url") == "https://github.com/opswitness/opswitness"
        )
        digest_key = "upstream_sha256" if "components" in payload else "sha256"
        required = {"version", "source_url", "license", digest_key}
        missing = sorted(key for key in required if not runtime.get(key))
        if first_party and digest_key in missing:
            missing.remove(digest_key)
        if "components" not in payload and not runtime.get("architecture"):
            missing.append("architecture")
        if require_complete and "components" in payload:
            if runtime.get("redistribution_review") != "approved" and not first_party:
                missing.append("redistribution_review=approved")
            provision = runtime.get("provision")
            if first_party:
                if not allow_first_party_unresolved:
                    if not re.fullmatch(
                        r"[0-9a-f]{40}", str(runtime.get("build_source_commit", ""))
                    ):
                        missing.append("build_source_commit")
                    if not re.fullmatch(
                        r"[0-9a-f]{64}",
                        str(runtime.get("build_artifact_sha256", "")),
                    ):
                        missing.append("build_artifact_sha256")
                if "provision" not in runtime or provision is not None:
                    missing.append("provision=null")
                python_bundle = runtime.get("python_bundle")
                if not isinstance(python_bundle, dict):
                    missing.append("python_bundle")
                else:
                    if python_bundle.get("runtime_version") != BACKEND_PYTHON_VERSION:
                        missing.append(f"python_bundle.runtime_version={BACKEND_PYTHON_VERSION}")
                    python_required = {
                        "runtime_version",
                        "runtime_source_url",
                        "runtime_sha256",
                        "runtime_license",
                        "runtime_notice",
                        "dependency_lock_path",
                        "dependency_lock_sha256",
                        "dependency_license_review_path",
                        "dependency_license_review_sha256",
                    }
                    python_missing = sorted(
                        key for key in python_required if not python_bundle.get(key)
                    )
                    if python_bundle.get("runtime_redistribution_review") != "approved":
                        python_missing.append("runtime_redistribution_review=approved")
                    if python_bundle.get("dependency_license_review") != "approved":
                        python_missing.append("dependency_license_review=approved")
                    missing.extend(f"python_bundle.{key}" for key in python_missing)
                    runtime_digest = python_bundle.get("runtime_sha256")
                    if runtime_digest and not re.fullmatch(r"[0-9a-f]{64}", str(runtime_digest)):
                        raise ValueError(
                            "vendor lock entry opswitness-backend has invalid python runtime sha256"
                        )
                    if runtime_digest and runtime_digest != BACKEND_PYTHON_SHA256:
                        raise ValueError(
                            "backend Python runtime sha256 does not match the reviewed "
                            "CPython 3.12.13 arm64 archive"
                        )
                    runtime_url = python_bundle.get("runtime_source_url")
                    if runtime_url and runtime_url != BACKEND_PYTHON_URL:
                        raise ValueError(
                            "backend Python runtime source must be the exact immutable "
                            "CPython 3.12.13 macOS arm64 archive"
                        )
                    lock_digest = python_bundle.get("dependency_lock_sha256")
                    if lock_digest and not re.fullmatch(r"[0-9a-f]{64}", str(lock_digest)):
                        raise ValueError(
                            "vendor lock entry opswitness-backend has invalid "
                            "Python dependency lock sha256"
                        )
                    lock_path = python_bundle.get("dependency_lock_path")
                    if root is not None and isinstance(lock_path, str) and lock_digest:
                        dependency_lock = (root / lock_path).resolve()
                        try:
                            dependency_lock.relative_to(root.resolve())
                        except ValueError as exc:
                            raise ValueError(
                                "Python dependency lock escapes the release root"
                            ) from exc
                        if not dependency_lock.is_file():
                            missing.append("python_bundle.dependency_lock_path")
                        elif sha256(dependency_lock) != lock_digest:
                            raise ValueError(
                                "Python dependency lock digest does not match vendor lock"
                            )
                    review_digest = python_bundle.get("dependency_license_review_sha256")
                    if review_digest and not re.fullmatch(r"[0-9a-f]{64}", str(review_digest)):
                        raise ValueError(
                            "vendor lock entry opswitness-backend has invalid "
                            "Python dependency review sha256"
                        )
                    review_path = python_bundle.get("dependency_license_review_path")
                    if root is not None and isinstance(review_path, str) and review_digest:
                        dependency_review = (root / review_path).resolve()
                        try:
                            dependency_review.relative_to(root.resolve())
                        except ValueError as exc:
                            raise ValueError(
                                "Python dependency review escapes the release root"
                            ) from exc
                        if not dependency_review.is_file():
                            missing.append("python_bundle.dependency_license_review_path")
                        elif sha256(dependency_review) != review_digest:
                            raise ValueError(
                                "Python dependency review digest does not match vendor lock"
                            )
                        else:
                            review_payload = _read_json_object(
                                dependency_review,
                                label="Python dependency license review",
                            )
                            if review_payload.get("review_status") != "approved":
                                missing.append("python_bundle.dependency_license_review=approved")
                            if review_payload.get("lock_sha256") != lock_digest:
                                raise ValueError(
                                    "Python dependency review is not bound to the "
                                    "locked dependency graph"
                                )
            elif not isinstance(provision, dict):
                missing.append("provision")
        if missing and require_complete:
            raise ValueError(f"vendor lock entry {name} is incomplete: " + ", ".join(missing))
        digest = runtime.get(digest_key)
        if digest and not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise ValueError(f"vendor lock entry {name} has invalid sha256")
    return payload


def assert_macos_metadata(
    path: Path,
    *,
    require_release_ready: bool,
) -> dict[str, object]:
    payload = _read_json_object(path, label="macOS signing metadata")
    required_values = {
        "architecture": "arm64",
        "minimum_macos": "14.0",
        "bundle_id": "com.opswitness.app",
    }
    for key, expected in required_values.items():
        if payload.get(key) != expected:
            raise ValueError(f"macOS signing metadata requires {key}={expected}")
    signing = payload.get("signing")
    notarization = payload.get("notarization")
    if not isinstance(signing, dict) or not isinstance(notarization, dict):
        raise ValueError("macOS signing metadata requires signing and notarization objects")
    if signing.get("hardened_runtime") is not True:
        raise ValueError("macOS signing metadata must confirm hardened runtime")
    if signing.get("nested_code_verified") is not True:
        raise ValueError("macOS signing metadata must confirm nested code verification")
    if signing.get("app_sandbox") is not False:
        raise ValueError("macOS signing metadata must explicitly record app_sandbox=false")
    if require_release_ready:
        if signing.get("mode") != "developer-id":
            raise ValueError("public release requires Developer ID signing")
        for key in ("identity", "cdhash"):
            if not signing.get(key):
                raise ValueError(f"public release signing metadata requires {key}")
        if notarization.get("status") != "Accepted":
            raise ValueError("public release requires accepted notarization")
        if notarization.get("stapled") is not True:
            raise ValueError("public release requires a stapled notarization ticket")
        if notarization.get("gatekeeper_assessment") != "accepted":
            raise ValueError("public release requires an accepted Gatekeeper assessment")
    return payload


def assert_backend_provenance(
    path: Path,
    *,
    distribution: str,
    version: str,
    vendor_payload: dict[str, object],
    wheel_sha256: str,
) -> dict[str, object]:
    payload = _read_json_object(path, label="backend build provenance")
    if payload.get("schema") != 1 or payload.get("build_mode") != "release":
        raise ValueError("backend build provenance must describe a release build")
    python = payload.get("python")
    wheel = payload.get("wheel")
    requirements = payload.get("requirements")
    license_review = payload.get("license_review")
    source_isolation = payload.get("source_isolation")
    if not all(
        isinstance(item, dict)
        for item in (
            python,
            wheel,
            requirements,
            license_review,
            source_isolation,
        )
    ):
        raise ValueError("backend build provenance is structurally incomplete")
    assert isinstance(python, dict)
    assert isinstance(wheel, dict)
    assert isinstance(requirements, dict)
    assert isinstance(license_review, dict)
    assert isinstance(source_isolation, dict)
    if python != {
        "implementation": "CPython",
        "version": BACKEND_PYTHON_VERSION,
        "architecture": "arm64",
    }:
        raise ValueError(
            f"backend build provenance requires CPython {BACKEND_PYTHON_VERSION} arm64"
        )
    if (
        str(wheel.get("distribution", "")).casefold() != distribution.casefold()
        or wheel.get("version") != version
        or wheel.get("sha256") != wheel_sha256
    ):
        raise ValueError("backend build provenance does not match the release wheel")
    if (
        requirements.get("hashes_required") is not True
        or not isinstance(requirements.get("package_count"), int)
        or int(requirements["package_count"]) < 1
    ):
        raise ValueError("backend build provenance lacks a frozen dependency graph")
    if (
        license_review.get("status") != "approved"
        or license_review.get("release_gate_enforced") is not True
    ):
        raise ValueError("backend build provenance lacks approved dependency licenses")
    if source_isolation != {
        "release_wheel_only": True,
        "repository_source_on_import_path": False,
    }:
        raise ValueError("backend build provenance does not prove wheel-only isolation")

    components = vendor_payload.get("components")
    if not isinstance(components, list):
        raise ValueError("vendor lock lacks backend Python evidence")
    backend = next(
        (
            component
            for component in components
            if isinstance(component, dict) and component.get("id") == "opswitness-backend"
        ),
        None,
    )
    if not isinstance(backend, dict) or not isinstance(backend.get("python_bundle"), dict):
        raise ValueError("vendor lock lacks backend Python evidence")
    python_bundle = backend["python_bundle"]
    assert isinstance(python_bundle, dict)
    if requirements.get("sha256") != python_bundle.get(
        "dependency_lock_sha256"
    ) or license_review.get("sha256") != python_bundle.get("dependency_license_review_sha256"):
        raise ValueError("backend build provenance does not match the vendor lock")
    return payload


def assert_spdx_sbom(path: Path, *, distribution: str, version: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"SPDX SBOM is unreadable: {path.name}") from exc
    if not isinstance(payload, dict) or payload.get("spdxVersion") != "SPDX-2.3":
        raise ValueError(f"SPDX SBOM has an unsupported or missing version: {path.name}")
    packages = payload.get("packages")
    if not isinstance(packages, list) or not any(
        isinstance(package, dict)
        and str(package.get("name") or "").casefold() == distribution.casefold()
        and str(package.get("versionInfo") or "") == version
        for package in packages
    ):
        raise ValueError(
            f"SPDX SBOM does not identify the {distribution} {version} distribution: {path.name}"
        )


def write_manifest(
    *,
    root: Path,
    dist: Path,
    tag: str,
    require_sbom: bool = False,
    require_macos: bool = False,
    require_release_ready: bool = False,
    vendor_lock: Path | None = None,
    macos_metadata: Path | None = None,
    candidate_run_id: str | None = None,
    candidate_run_attempt: str | None = None,
) -> dict[str, object]:
    assert_clean_tree(root)
    distribution, python_version, public_version, expected_tag = release_identity(root)
    if tag != expected_tag:
        raise ValueError(f"release tag mismatch: expected {expected_tag}, found {tag}")
    candidate_values = (candidate_run_id, candidate_run_attempt)
    if any(value is not None for value in candidate_values):
        if not all(
            isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value)
            for value in candidate_values
        ):
            raise ValueError("candidate workflow run id and attempt must both be positive integers")

    files = _asset_files(dist)
    if not files:
        raise ValueError(f"no release assets under {dist}")
    if not any(path.suffix == ".whl" for path in files):
        raise ValueError("release assets do not contain a wheel")
    if not any(path.name.endswith(".tar.gz") for path in files):
        raise ValueError("release assets do not contain an sdist")
    sboms = [path for path in files if path.name.endswith(".spdx.json")]
    if require_sbom:
        if not sboms:
            raise ValueError("release assets do not contain an SPDX SBOM")
        python_sboms = [path for path in sboms if path.name.startswith("python-")]
        candidates = python_sboms or sboms
        for sbom in sboms:
            payload = _read_json_object(sbom, label="SPDX SBOM")
            if payload.get("spdxVersion") != "SPDX-2.3":
                raise ValueError(f"SPDX SBOM has an unsupported or missing version: {sbom.name}")
        for sbom in candidates:
            assert_spdx_sbom(
                sbom,
                distribution=distribution,
                version=python_version,
            )
    macos = [path for path in files if artifact_kind(path) == "macos_dmg"]
    updaters = [path for path in files if artifact_kind(path) == "macos_updater"]
    updater_signatures = [path for path in files if artifact_kind(path) == "updater_signature"]
    notices = [path for path in files if artifact_kind(path) == "third_party_notices"]
    backend_provenance = [
        path for path in files if artifact_kind(path) == "backend_build_provenance"
    ]
    update_feeds = [path for path in files if artifact_kind(path) == "updater_feed"]
    if require_macos:
        expected_dmg = f"OpsWitness-{public_version}-macos-arm64.dmg"
        expected_updater = f"OpsWitness-{public_version}-macos-arm64-updater.tar.gz"
        if [path.name for path in macos] != [expected_dmg]:
            raise ValueError(f"release assets must contain exactly {expected_dmg}")
        if [path.name for path in updaters] != [expected_updater]:
            raise ValueError(f"release assets must contain exactly {expected_updater}")
        if [path.name for path in updater_signatures] != [f"{expected_updater}.sig"]:
            raise ValueError(f"release assets must contain exactly {expected_updater}.sig")
        if [path.name for path in update_feeds] != ["updates-alpha-latest.json"]:
            raise ValueError("release assets must contain exactly updates-alpha-latest.json")
        if len(notices) != 1:
            raise ValueError("release assets must contain THIRD_PARTY_NOTICES.txt")
        if len(backend_provenance) != 1:
            raise ValueError("macOS release assets must contain backend-build-provenance.json")
        if not any(path.name == "python-sbom.spdx.json" for path in sboms):
            raise ValueError("macOS release assets must contain python-sbom.spdx.json")
        if not any(path.name == "app-sbom.spdx.json" for path in sboms):
            raise ValueError("macOS release assets must contain app-sbom.spdx.json")
        if vendor_lock is None or macos_metadata is None:
            raise ValueError("macOS release requires vendor lock and signing metadata")

    vendor_payload: dict[str, object] | None = None
    if vendor_lock is not None:
        vendor_payload = assert_vendor_lock(
            vendor_lock,
            require_complete=require_release_ready,
            root=root,
        )
    vendor_components: list[object] = []
    if vendor_payload is not None:
        raw_vendor_components = vendor_payload.get(
            "components",
            vendor_payload.get("runtimes", []),
        )
        if isinstance(raw_vendor_components, list):
            vendor_components = raw_vendor_components
    macos_payload: dict[str, object] | None = None
    if macos_metadata is not None:
        macos_payload = assert_macos_metadata(
            macos_metadata,
            require_release_ready=require_release_ready,
        )
    if require_macos and vendor_payload is not None:
        wheels = [path for path in files if artifact_kind(path) == "wheel"]
        if len(wheels) != 1:
            raise ValueError("macOS release assets must contain exactly one wheel")
        assert_backend_provenance(
            backend_provenance[0],
            distribution=distribution,
            version=python_version,
            vendor_payload=vendor_payload,
            wheel_sha256=sha256(wheels[0]),
        )

    records = [
        {
            "name": path.name,
            "kind": artifact_kind(path),
            "sha256": sha256(path),
            "size": path.stat().st_size,
        }
        for path in files
    ]
    (dist / "SHA256SUMS").write_text(
        "".join(f"{record['sha256']}  {record['name']}\n" for record in records),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 3,
        "product": "OpsWitness",
        "distribution": distribution,
        "python_version": python_version,
        "public_version": public_version,
        "tag": tag,
        "git_commit": git_output(root, "rev-parse", "HEAD"),
        "clean_tree": True,
        "builder_python": sys.version.split()[0],
        "created_at": _created_at(),
        "artifacts": records,
        "platforms": {
            "macos": macos_payload
            or {
                "architecture": "arm64",
                "minimum_macos": "14.0",
                "bundle_id": "com.opswitness.app",
                "status": "not_built",
            }
        },
        "vendor_runtime_lock": (
            {
                "schema_version": vendor_payload.get("schema_version"),
                "sha256": sha256(vendor_lock),
                "runtime_count": len(vendor_components),
                "components": [
                    {
                        key: component.get(key)
                        for key in (
                            "id",
                            "name",
                            "version",
                            "source_url",
                            "upstream_sha256",
                            "sha256",
                            "license",
                            "redistribution_review",
                            "python_bundle",
                        )
                        if key in component
                    }
                    for component in vendor_components
                    if isinstance(component, dict)
                ],
            }
            if vendor_payload is not None and vendor_lock is not None
            else None
        ),
        "candidate": (
            {
                "workflow_run_id": int(candidate_run_id),
                "workflow_run_attempt": int(candidate_run_attempt),
            }
            if candidate_run_id is not None and candidate_run_attempt is not None
            else None
        ),
        "release_ready": require_release_ready,
    }
    (dist / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", nargs="?", type=Path, default=Path("dist"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", default=os.getenv("RELEASE_TAG"))
    parser.add_argument("--require-sbom", action="store_true")
    parser.add_argument("--require-macos", action="store_true")
    parser.add_argument("--require-release-ready", action="store_true")
    parser.add_argument("--vendor-lock", type=Path)
    parser.add_argument("--macos-metadata", type=Path)
    parser.add_argument("--candidate-run-id")
    parser.add_argument("--candidate-run-attempt")
    args = parser.parse_args()
    root = args.root.resolve()
    _, _, _, expected_tag = release_identity(root)
    tag = args.tag or expected_tag
    try:
        write_manifest(
            root=root,
            dist=args.dist.resolve(),
            tag=tag,
            require_sbom=args.require_sbom,
            require_macos=args.require_macos,
            require_release_ready=args.require_release_ready,
            vendor_lock=args.vendor_lock.resolve() if args.vendor_lock else None,
            macos_metadata=(args.macos_metadata.resolve() if args.macos_metadata else None),
            candidate_run_id=args.candidate_run_id,
            candidate_run_attempt=args.candidate_run_attempt,
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"release manifest failed: {exc}", file=sys.stderr)
        return 1
    print(f"release manifest written for {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
