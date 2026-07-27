#!/usr/bin/env python3
"""Create and verify the complete desktop runtime file inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock(path: Path, *, release: bool) -> dict:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise SystemExit("unsupported vendor-lock schema")
    if payload.get("target") != "aarch64-apple-darwin":
        raise SystemExit("vendor-lock target must be aarch64-apple-darwin")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise SystemExit("vendor-lock must contain components")
    identifiers: set[str] = set()
    for component in components:
        identifier = component.get("id")
        if not isinstance(identifier, str) or identifier in identifiers:
            raise SystemExit(f"invalid or duplicate vendor component: {identifier!r}")
        identifiers.add(identifier)
        entrypoints = component.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            raise SystemExit(f"{identifier}: entrypoints are required")
        if release:
            approved = component.get("redistribution_review") == "approved"
            if identifier == "opswitness-backend":
                complete = (
                    isinstance(component.get("build_source_commit"), str)
                    and isinstance(component.get("build_artifact_sha256"), str)
                )
            else:
                complete = isinstance(component.get("upstream_sha256"), str)
            if not approved or not complete:
                raise SystemExit(f"{identifier}: redistribution lock is incomplete")
    return payload


def _lexical_symlink_destination(relative_link: Path, target: Path) -> Path:
    """Resolve ``target`` lexically without allowing it to leave the payload."""

    parts: list[str] = []
    for part in (*relative_link.parent.parts, *target.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("target escapes the runtime payload")
            parts.pop()
            continue
        parts.append(part)
    return Path(*parts)


def validate_symlink(runtime: Path, link: Path, target_text: str) -> None:
    """Require a relative, contained, and currently resolvable symlink target."""

    if not target_text:
        raise ValueError("target is empty")
    target = Path(target_text)
    if target.is_absolute():
        raise ValueError("target must be relative")
    relative_link = link.relative_to(runtime)
    _lexical_symlink_destination(relative_link, target)
    try:
        resolved = (link.parent / target).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"target is broken: {exc}") from exc
    try:
        resolved.relative_to(runtime)
    except ValueError as exc:
        raise ValueError("target resolves outside the runtime payload") from exc


def resource_entries(runtime: Path) -> tuple[list[dict[str, object]], set[str]]:
    """Inventory regular files and safe symlinks without following link directories."""

    runtime = runtime.resolve(strict=True)
    files: list[dict[str, object]] = []
    discovered: set[str] = set()
    candidates: list[Path] = []
    for directory, directory_names, file_names in os.walk(runtime, followlinks=False):
        directory_path = Path(directory)
        candidates.extend(directory_path / name for name in directory_names)
        candidates.extend(directory_path / name for name in file_names)

    for path in sorted(candidates, key=lambda candidate: candidate.relative_to(runtime).as_posix()):
        if path.name in {".gitkeep", "resource-manifest.json"}:
            if path.is_symlink():
                raise SystemExit(f"reserved runtime resource must not be a symlink: {path}")
            continue
        relative = path.relative_to(runtime).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            try:
                validate_symlink(runtime, path, target)
            except ValueError as exc:
                raise SystemExit(f"unsafe runtime resource symlink {path}: {exc}") from exc
            discovered.add(relative)
            files.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "target": target,
                }
            )
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"unsupported runtime resource type: {path}")
        discovered.add(relative)
        mode = stat.S_IMODE(path.stat().st_mode)
        files.append(
            {
                "path": relative,
                "kind": "file",
                "sha256": sha256(path),
                "size": path.stat().st_size,
                "executable": bool(mode & 0o111),
            }
        )
    return files, discovered


def validate_architecture_provenance(
    provenance: dict, discovered: set[str]
) -> None:
    """Require a complete, auditable architecture-normalization record."""

    if (
        provenance.get("schema_version") != 1
        or provenance.get("target_architecture") != "arm64"
        or not isinstance(provenance.get("entries"), list)
    ):
        raise SystemExit("invalid macOS architecture normalization provenance")
    for entry in provenance["entries"]:
        if not isinstance(entry, dict):
            raise SystemExit("invalid macOS architecture normalization provenance")
        path = entry.get("path")
        before_archs = entry.get("before_archs")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(before_archs, list)
            or not before_archs
            or not isinstance(entry.get("before_sha256"), str)
        ):
            raise SystemExit("invalid macOS architecture normalization provenance")
        action = entry.get("action")
        if action == "excluded_non_arm_vendor_prebuild":
            if (
                entry.get("after_archs") != []
                or entry.get("after_sha256") is not None
                or path in discovered
            ):
                raise SystemExit("invalid macOS architecture normalization exclusion")
            continue
        if action not in {"preserved", "thinned_to_arm64"}:
            raise SystemExit("invalid macOS architecture normalization provenance")
        if (
            entry.get("after_archs") != ["arm64"]
            or not isinstance(entry.get("after_sha256"), str)
            or path not in discovered
        ):
            raise SystemExit("invalid macOS architecture normalization provenance")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--vendor-lock", required=True, type=Path)
    parser.add_argument("--mode", choices=("adhoc", "release"), default="adhoc")
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument(
        "--verify-existing",
        action="store_true",
        help="verify the staged manifest before any nested code signature changes",
    )
    phase.add_argument(
        "--post-sign",
        action="store_true",
        help="refresh hashes after nested signing and before the outer app is signed",
    )
    parser.add_argument(
        "--pre-sign-manifest-sha256",
        help="required staged-manifest digest that binds a post-sign refresh",
    )
    args = parser.parse_args()

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("runtime staging requires native macOS arm64")
    pre_sign_manifest_sha256 = args.pre_sign_manifest_sha256
    if args.post_sign:
        if (
            not isinstance(pre_sign_manifest_sha256, str)
            or len(pre_sign_manifest_sha256) != 64
            or any(character not in "0123456789abcdef" for character in pre_sign_manifest_sha256)
        ):
            raise SystemExit(
                "post-sign manifest refresh requires a lowercase staged-manifest SHA-256"
            )
    elif pre_sign_manifest_sha256 is not None:
        raise SystemExit("--pre-sign-manifest-sha256 requires --post-sign")

    vendor = load_lock(args.vendor_lock, release=args.mode == "release")
    expected_entrypoints = {
        entrypoint
        for component in vendor["components"]
        for entrypoint in component["entrypoints"]
    }
    files, discovered = resource_entries(args.runtime)

    provenance_path = "architecture-provenance.json"
    provenance_entry = next(
        (entry for entry in files if entry["path"] == provenance_path), None
    )
    if provenance_entry is None or provenance_entry.get("kind") != "file":
        raise SystemExit("missing macOS architecture normalization provenance")
    try:
        provenance = json.loads((args.runtime / provenance_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("invalid macOS architecture normalization provenance") from exc
    validate_architecture_provenance(provenance, discovered)

    missing = expected_entrypoints - discovered
    if missing:
        raise SystemExit(f"missing vendor entrypoints: {sorted(missing)}")
    for component in vendor["components"]:
        for prefix in component.get("required_prefixes", []):
            if not any(path.startswith(prefix) for path in discovered):
                raise SystemExit(
                    f"{component['id']}: required resource prefix is empty: {prefix}"
                )
    if args.mode == "release" and not args.post_sign:
        backend = next(
            component
            for component in vendor["components"]
            if component["id"] == "opswitness-backend"
        )
        backend_path = args.runtime / backend["entrypoints"][0]
        if sha256(backend_path) != backend["build_artifact_sha256"]:
            raise SystemExit("opswitness-backend build artifact digest does not match resolved lock")
    manifest = {
        "schema_version": 2,
        "target": "aarch64-apple-darwin",
        "distribution_mode": args.mode,
        "integrity_phase": "post-sign" if args.post_sign else "staged",
        "architecture_normalization": {
            "path": provenance_path,
            "sha256": provenance_entry["sha256"],
        },
        "files": files,
    }
    if args.post_sign:
        manifest["pre_sign_manifest_sha256"] = pre_sign_manifest_sha256
    destination = args.runtime / "resource-manifest.json"
    if args.verify_existing:
        try:
            existing = json.loads(destination.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("missing or invalid staged runtime resource manifest") from exc
        if existing != manifest:
            raise SystemExit("staged runtime resource manifest does not match current payload")
        return
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, destination)
    os.chmod(destination, 0o644)


if __name__ == "__main__":
    main()
