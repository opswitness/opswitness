#!/usr/bin/env python3
"""Replace AionCore's upstream Claude ACP payload with a fail-closed shim."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path


PROFILE = "codex-only"
COMPONENT = "aioncore"
AIONCORE_VERSION = "0.1.45"
SOURCE_SUBTREE = Path(
    "aioncore/managed-resources/acp/claude-agent-acp/0.58.1/darwin-arm64"
)
RECEIPT_PATH = Path("staging-exclusions.json")
UPSTREAM_MARKERS = (
    Path("manifest.json"),
    Path("node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js"),
    Path("node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude"),
)
MANAGED_RESOURCES = Path("aioncore/managed-resources")

SHIM_FILES: dict[Path, tuple[bytes, int]] = {
    Path("manifest.json"): (
        b'{\n  "entrypoint": "disabled-shim.js",\n  "path_entries": []\n}\n',
        0o644,
    ),
    Path("package.json"): (
        (
            b'{\n  "name": "opswitness-disabled-claude-agent-acp-shim",\n'
            b'  "private": true,\n  "version": "0.0.0"\n}\n'
        ),
        0o644,
    ),
    Path("package-lock.json"): (
        (
            b'{\n  "name": "opswitness-disabled-claude-agent-acp-shim",\n'
            b'  "version": "0.0.0",\n  "lockfileVersion": 3,\n'
            b'  "requires": true,\n  "packages": {\n    "": {\n'
            b'      "name": "opswitness-disabled-claude-agent-acp-shim",\n'
            b'      "version": "0.0.0"\n    }\n  }\n}\n'
        ),
        0o644,
    ),
    Path("disabled-shim.js"): (
        (
            b"#!/usr/bin/env node\n\n"
            b"process.stderr.write(\n"
            b'  "Claude Agent is disabled in this Codex-only OpsWitness build.\\n",\n'
            b");\n"
            b"process.exit(78);\n"
        ),
        0o644,
    ),
    Path(
        "node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude"
    ): (
        (
            b"#!/bin/sh\n\n"
            b'echo "Claude Agent is disabled in this Codex-only OpsWitness build." >&2\n'
            b"exit 78\n"
        ),
        0o755,
    ),
}
SHIM_NATIVE_PATH = (
    SOURCE_SUBTREE
    / "node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64/claude"
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_relative_path(value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{label} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SystemExit(f"{label} must be a normalized relative path")
    return path


def load_policy(vendor_lock: Path) -> dict[str, object]:
    try:
        payload = json.loads(vendor_lock.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("invalid vendor lock for Codex-only staging") from exc
    if (
        payload.get("schema_version") != 1
        or payload.get("target") != "aarch64-apple-darwin"
    ):
        raise SystemExit("unsupported vendor lock for Codex-only staging")
    matches = [
        component
        for component in payload.get("components", [])
        if isinstance(component, dict) and component.get("id") == COMPONENT
    ]
    if len(matches) != 1:
        raise SystemExit("vendor lock must contain exactly one AionCore component")
    policy = matches[0].get("staging_filter")
    if not isinstance(policy, dict):
        raise SystemExit("AionCore vendor lock is missing staging_filter")
    if policy.get("profile") != PROFILE:
        raise SystemExit("AionCore staging_filter must use the codex-only profile")
    if (
        matches[0].get("version") != AIONCORE_VERSION
        or policy.get("applies_to_version") != AIONCORE_VERSION
    ):
        raise SystemExit("AionCore staging_filter is not locked to version 0.1.45")
    exclusions = policy.get("source_exclusions")
    if exclusions != [SOURCE_SUBTREE.as_posix()]:
        raise SystemExit("AionCore staging_filter source_exclusions changed unexpectedly")
    shim_root = _validate_relative_path(
        policy.get("compatibility_shim_root"),
        label="AionCore compatibility_shim_root",
    )
    receipt = _validate_relative_path(
        policy.get("receipt"),
        label="AionCore staging_filter receipt",
    )
    if shim_root != SOURCE_SUBTREE or receipt != RECEIPT_PATH:
        raise SystemExit("AionCore staging_filter paths changed unexpectedly")
    return policy


def _safe_real_directory(root: Path, relative: Path, *, label: str) -> Path:
    root = root.resolve(strict=True)
    candidate = root
    for part in relative.parts:
        candidate /= part
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise SystemExit(f"{label} is missing: {relative.as_posix()}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise SystemExit(f"{label} and its parents must be real directories")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"{label} resolves outside the staged runtime") from exc
    return candidate


def tree_summary(root: Path) -> dict[str, object]:
    """Return a deterministic digest without following directory symlinks."""

    root = root.resolve(strict=True)
    records: list[bytes] = []
    file_count = 0
    symlink_count = 0
    total_bytes = 0
    candidates: list[Path] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        candidates.extend(directory_path / name for name in directory_names)
        candidates.extend(directory_path / name for name in file_names)
    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            target = os.readlink(path)
            records.append(f"L\\0{relative}\\0{mode:o}\\0{target}\\n".encode())
            symlink_count += 1
        elif stat.S_ISDIR(metadata.st_mode):
            records.append(f"D\\0{relative}\\0{mode:o}\\n".encode())
        elif stat.S_ISREG(metadata.st_mode):
            digest = sha256_file(path)
            records.append(
                f"F\\0{relative}\\0{mode:o}\\0{metadata.st_size}\\0{digest}\\n".encode()
            )
            file_count += 1
            total_bytes += metadata.st_size
        else:
            raise SystemExit(f"unsupported file type in staged runtime: {relative}")
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
    return {
        "sha256": digest.hexdigest(),
        "file_count": file_count,
        "symlink_count": symlink_count,
        "total_bytes": total_bytes,
    }


def _write_shim(root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for relative, (payload, mode) in SHIM_FILES.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        os.chmod(destination, mode)
        entries.append(
            {
                "path": (SOURCE_SUBTREE / relative).as_posix(),
                "sha256": sha256_bytes(payload),
                "size": len(payload),
                "executable": bool(mode & 0o111),
            }
        )
    return sorted(entries, key=lambda entry: str(entry["path"]))


def _audit_aioncore_manifest(runtime: Path) -> dict[str, object]:
    path = runtime / "aioncore/manifest.json"
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("AionCore top-level manifest is missing or invalid") from exc
    files = payload.get("files")
    if payload.get("version") != f"v{AIONCORE_VERSION}":
        raise SystemExit("AionCore manifest version changed; review the staging filter")
    if not isinstance(files, list) or "managed-resources/" not in files:
        raise SystemExit("AionCore manifest no longer declares managed-resources/")
    if any(
        isinstance(value, str) and "claude-agent-acp" in value
        for value in files
    ):
        raise SystemExit(
            "AionCore manifest now names Claude resources and requires an explicit rewrite"
        )
    return {
        "path": "aioncore/manifest.json",
        "sha256": sha256_file(path),
        "rewrite_required": False,
        "reason": (
            "The upstream manifest declares managed-resources/ as a directory and "
            "does not enumerate individual ACP payloads."
        ),
    }


def _forbidden_managed_resource_paths(runtime: Path) -> list[str]:
    root = runtime / MANAGED_RESOURCES
    forbidden: list[str] = []
    for path in root.rglob("*"):
        if not (path.is_file() or path.is_symlink()):
            continue
        relative = path.relative_to(runtime)
        parts = relative.parts
        if (
            "@anthropic-ai" in parts
            or "claude-agent-acp" in parts
            or path.name in {"anthropic-ai-sdk", "claude-agent-acp"}
        ) and relative != SHIM_NATIVE_PATH:
            if not relative.is_relative_to(SOURCE_SUBTREE):
                forbidden.append(relative.as_posix())
    return sorted(forbidden)


def stage(runtime: Path, vendor_lock: Path, receipt: Path) -> dict[str, object]:
    policy = load_policy(vendor_lock)
    runtime = _safe_real_directory(runtime.parent, Path(runtime.name), label="runtime")
    source = _safe_real_directory(
        runtime,
        SOURCE_SUBTREE,
        label="upstream Claude managed resource",
    )
    for marker in UPSTREAM_MARKERS:
        candidate = source / marker
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise SystemExit(
                f"upstream Claude managed resource marker is missing: {marker.as_posix()}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise SystemExit(
                f"upstream Claude managed resource marker is unsafe: {marker.as_posix()}"
            )

    original_markers = [
        {
            "path": (SOURCE_SUBTREE / marker).as_posix(),
            "sha256": sha256_file(source / marker),
            "size": (source / marker).stat().st_size,
        }
        for marker in UPSTREAM_MARKERS
    ]
    before = tree_summary(source)
    aioncore_manifest = _audit_aioncore_manifest(runtime)
    shutil.rmtree(source)
    source.mkdir(parents=True)
    generated = _write_shim(source)

    actual = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    expected = {path.as_posix() for path in SHIM_FILES}
    if actual != expected:
        raise SystemExit("generated Claude compatibility shim inventory is not exact")
    forbidden = _forbidden_managed_resource_paths(runtime)
    if forbidden:
        raise SystemExit(
            f"proprietary Anthropic managed-resource paths remain: {forbidden}"
        )
    after = tree_summary(runtime / MANAGED_RESOURCES)
    result = {
        "schema_version": 1,
        "profile": PROFILE,
        "component": COMPONENT,
        "reason": "upstream_anthropic_redistribution_not_approved",
        "source_exclusions": [
            {
                "path": SOURCE_SUBTREE.as_posix(),
                "original_tree": before,
                "original_markers": original_markers,
                "original_source_tree_removed": True,
            }
        ],
        "generated_compatibility_shim": {
            "root": SOURCE_SUBTREE.as_posix(),
            "purpose": (
                "Satisfy AionCore 0.1.45's fixed managed-resource validation while "
                "failing closed if the disabled Claude agent is invoked."
            ),
            "files": generated,
        },
        "aioncore_manifest_audit": aioncore_manifest,
        "proprietary_path_scan": {
            "forbidden_matches": [],
            "allowed_first_party_shim_path": SHIM_NATIVE_PATH.as_posix(),
            "allowed_first_party_shim_sha256": sha256_bytes(
                SHIM_FILES[
                    Path(
                        "node_modules/@anthropic-ai/"
                        "claude-agent-sdk-darwin-arm64/claude"
                    )
                ][0]
            ),
        },
        "managed_resources_after_filter_before_architecture_normalization": after,
        "policy": {
            "profile": policy["profile"],
            "applies_to_version": policy["applies_to_version"],
            "receipt": policy["receipt"],
        },
    }
    if receipt != runtime / RECEIPT_PATH:
        raise SystemExit("staging exclusion receipt must use its vendor-locked runtime path")
    temporary = receipt.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, receipt)
    os.chmod(receipt, 0o644)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--vendor-lock", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    stage(args.runtime, args.vendor_lock, args.receipt)


if __name__ == "__main__":
    main()
