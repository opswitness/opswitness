#!/usr/bin/env python3
"""Remove Paperclip's bundled Claude Agent runtime from Codex-only staging."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path


PROFILE = "codex-only"
COMPONENT = "paperclip"
PAPERCLIP_VERSION = "2026.707.0"
PAPERCLIP_ENTRYPOINT = Path("paperclip/dist/index.js")
PAPERCLIP_ENTRYPOINT_SHA256 = (
    "070df2f71906daac276da1c90404fd11463c4992f78f5d43fee69d6036d61252"
)
SOURCE_SUBTREES = (
    Path("paperclip/node_modules/@agentclientprotocol/claude-agent-acp"),
    Path("paperclip/node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64"),
)
COMPANION_LINK = Path("paperclip/node_modules/.bin/claude-agent-acp")
COMPANION_LINK_TARGET = "../@agentclientprotocol/claude-agent-acp/dist/index.js"
RECEIPT_PATH = Path("paperclip-staging-exclusions.json")
SOURCE_MARKERS: dict[Path, tuple[Path, ...]] = {
    SOURCE_SUBTREES[0]: (
        Path("package.json"),
        Path("dist/index.js"),
        Path("node_modules/@anthropic-ai/claude-agent-sdk/package.json"),
    ),
    SOURCE_SUBTREES[1]: (
        Path("package.json"),
        Path("LICENSE.md"),
        Path("claude"),
    ),
}
EXPECTED_SOURCE_TREES: dict[Path, dict[str, object]] = {
    SOURCE_SUBTREES[0]: {
        "sha256": "804a73195127da096a64a3a607890e92d3180d7e79f92c8b8438cc2786909c44",
        "file_count": 757,
        "symlink_count": 0,
        "total_bytes": 8_526_606,
    },
    SOURCE_SUBTREES[1]: {
        "sha256": "65910ea7797a768278c01ded9c16369ba0f7f06050cf96bfa0d3f09d2a018b88",
        "file_count": 4,
        "symlink_count": 0,
        "total_bytes": 219_856_632,
    },
}
EXPECTED_MARKERS: dict[Path, tuple[str, int]] = {
    SOURCE_SUBTREES[0] / "package.json": (
        "f3f714ec0caf56a571662fdc0d9b653c98be34ad4ea0ab09f0f67c22bd421d6c",
        2_194,
    ),
    SOURCE_SUBTREES[0] / "dist/index.js": (
        "5d946f0d74a75ce418796b5c232a844b96a6c6c902c45dfc73027634d48ee273",
        2_972,
    ),
    SOURCE_SUBTREES[0]
    / "node_modules/@anthropic-ai/claude-agent-sdk/package.json": (
        "1c5d0b2ca32a2fe1349543120d21fe64eb82e340305381be37dfc88d5964bb62",
        2_380,
    ),
    SOURCE_SUBTREES[1] / "package.json": (
        "f9e2f053b8ed6e31d7cfe3076fc7add848d0a6bb0e24bb3ace0935a0143a87de",
        274,
    ),
    SOURCE_SUBTREES[1] / "LICENSE.md": (
        "8ce94b9478bb9868f9641f818e06cd722fbe55d4c22e2d2ed11971b20146173a",
        147,
    ),
    SOURCE_SUBTREES[1] / "claude": (
        "252307a7413de6e151ef91168903a4f5bf1159296b0e71d1cb7ae2e74ff18e9a",
        219_856_048,
    ),
}
EXPECTED_PACKAGES: dict[Path, tuple[str, str, str]] = {
    SOURCE_SUBTREES[0] / "package.json": (
        "@agentclientprotocol/claude-agent-acp",
        "0.52.0",
        "Apache-2.0",
    ),
    SOURCE_SUBTREES[0]
    / "node_modules/@anthropic-ai/claude-agent-sdk/package.json": (
        "@anthropic-ai/claude-agent-sdk",
        "0.3.191",
        "SEE LICENSE IN README.md",
    ),
    SOURCE_SUBTREES[1] / "package.json": (
        "@anthropic-ai/claude-agent-sdk-darwin-arm64",
        "0.3.191",
        "SEE LICENSE IN LICENSE.md",
    ),
}


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
    """Return a deterministic tree digest without following directory symlinks."""

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
            records.append(
                f"L\\0{relative}\\0{mode:o}\\0{os.readlink(path)}\\n".encode()
            )
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
        raise SystemExit("vendor lock must contain exactly one Paperclip component")
    policy = matches[0].get("staging_filter")
    if not isinstance(policy, dict):
        raise SystemExit("Paperclip vendor lock is missing staging_filter")
    if policy.get("profile") != PROFILE:
        raise SystemExit("Paperclip staging_filter must use the codex-only profile")
    if (
        matches[0].get("version") != PAPERCLIP_VERSION
        or policy.get("applies_to_version") != PAPERCLIP_VERSION
    ):
        raise SystemExit(
            "Paperclip staging_filter is not locked to version 2026.707.0"
        )
    exclusions = policy.get("source_exclusions")
    if exclusions != [path.as_posix() for path in SOURCE_SUBTREES]:
        raise SystemExit(
            "Paperclip staging_filter source_exclusions changed unexpectedly"
        )
    receipt = _validate_relative_path(
        policy.get("receipt"),
        label="Paperclip staging_filter receipt",
    )
    if receipt != RECEIPT_PATH:
        raise SystemExit("Paperclip staging_filter receipt changed unexpectedly")
    if policy.get("compatibility_shim_root") is not None:
        raise SystemExit("Paperclip staging_filter must not generate a compatibility shim")
    return policy


def _validate_companion_link(runtime: Path) -> str:
    link = runtime / COMPANION_LINK
    try:
        metadata = link.lstat()
    except OSError as exc:
        raise SystemExit("Paperclip Claude ACP companion link is missing") from exc
    if not stat.S_ISLNK(metadata.st_mode):
        raise SystemExit("Paperclip Claude ACP companion link must be a symlink")
    target = os.readlink(link)
    if target != COMPANION_LINK_TARGET:
        raise SystemExit("Paperclip Claude ACP companion link target changed")
    try:
        resolved = link.resolve(strict=True)
        resolved.relative_to(runtime.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise SystemExit("Paperclip Claude ACP companion link is unsafe") from exc
    return target


def _forbidden_paths(runtime: Path) -> list[str]:
    root = runtime / "paperclip/node_modules"
    forbidden: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(runtime).as_posix()
        if (
            "claude-agent-sdk" in relative
            or "@agentclientprotocol/claude-agent-acp" in relative
            or relative == COMPANION_LINK.as_posix()
        ):
            forbidden.append(relative)
    return sorted(forbidden)


def _validate_locked_package(path: Path, expected: tuple[str, str, str]) -> None:
    try:
        package = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid locked package metadata: {path}") from exc
    observed = (
        package.get("name"),
        package.get("version"),
        package.get("license"),
    )
    if observed != expected:
        raise SystemExit(f"locked Paperclip Claude package metadata changed: {path}")


def stage(runtime: Path, vendor_lock: Path, receipt: Path) -> dict[str, object]:
    policy = load_policy(vendor_lock)
    runtime = _safe_real_directory(runtime.parent, Path(runtime.name), label="runtime")
    if receipt.absolute() != (runtime / RECEIPT_PATH).absolute():
        raise SystemExit("Paperclip exclusion receipt must use its vendor-locked path")
    entrypoint = runtime / PAPERCLIP_ENTRYPOINT
    if (
        not entrypoint.is_file()
        or entrypoint.is_symlink()
        or sha256_file(entrypoint) != PAPERCLIP_ENTRYPOINT_SHA256
    ):
        raise SystemExit("Paperclip entrypoint digest changed from the locked source")
    sources = [
        _safe_real_directory(runtime, relative, label="Paperclip Claude Agent payload")
        for relative in SOURCE_SUBTREES
    ]
    companion_target = _validate_companion_link(runtime)

    source_exclusions: list[dict[str, object]] = []
    for relative, source in zip(SOURCE_SUBTREES, sources, strict=True):
        observed_tree = tree_summary(source)
        if observed_tree != EXPECTED_SOURCE_TREES[relative]:
            raise SystemExit(
                f"Paperclip Claude payload tree changed: {relative.as_posix()}"
            )
        markers: list[dict[str, object]] = []
        for marker in SOURCE_MARKERS[relative]:
            candidate = source / marker
            try:
                metadata = candidate.lstat()
            except OSError as exc:
                raise SystemExit(
                    f"Paperclip Claude payload marker is missing: {marker.as_posix()}"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise SystemExit(
                    f"Paperclip Claude payload marker is unsafe: {marker.as_posix()}"
                )
            expected_sha256, expected_size = EXPECTED_MARKERS[relative / marker]
            observed_sha256 = sha256_file(candidate)
            if (
                observed_sha256 != expected_sha256
                or metadata.st_size != expected_size
            ):
                raise SystemExit(
                    f"Paperclip Claude payload marker changed: {marker.as_posix()}"
                )
            package_expectation = EXPECTED_PACKAGES.get(relative / marker)
            if package_expectation is not None:
                _validate_locked_package(candidate, package_expectation)
            markers.append(
                {
                    "path": (relative / marker).as_posix(),
                    "sha256": observed_sha256,
                    "size": metadata.st_size,
                }
            )
        source_exclusions.append(
            {
                "path": relative.as_posix(),
                "original_tree": observed_tree,
                "original_markers": markers,
                "original_source_tree_removed": True,
            }
        )

    (runtime / COMPANION_LINK).unlink()
    for source in sources:
        shutil.rmtree(source)

    forbidden = _forbidden_paths(runtime)
    if forbidden:
        raise SystemExit(
            f"proprietary Anthropic Paperclip payload paths remain: {forbidden}"
        )
    after = tree_summary(runtime / "paperclip")
    result = {
        "schema_version": 1,
        "profile": PROFILE,
        "component": COMPONENT,
        "reason": "upstream_anthropic_redistribution_not_approved",
        "locked_paperclip_entrypoint": {
            "path": PAPERCLIP_ENTRYPOINT.as_posix(),
            "sha256": PAPERCLIP_ENTRYPOINT_SHA256,
        },
        "source_exclusions": source_exclusions,
        "removed_companion_links": [
            {
                "path": COMPANION_LINK.as_posix(),
                "target": companion_target,
            }
        ],
        "proprietary_path_scan": {
            "forbidden_matches": [],
        },
        "paperclip_after_filter_before_architecture_normalization": after,
        "policy": {
            "profile": policy["profile"],
            "applies_to_version": policy["applies_to_version"],
            "source_exclusions": policy["source_exclusions"],
            "receipt": policy["receipt"],
        },
    }
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
