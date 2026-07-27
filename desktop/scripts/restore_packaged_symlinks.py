#!/usr/bin/env python3
"""Restore safe runtime symlinks that the Tauri resource copier dereferences."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Replacement:
    path: Path
    relative_path: str
    target: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lexical_destination(relative_link: Path, target: Path) -> Path:
    if target.is_absolute():
        raise ValueError("target must be relative")
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
    if not parts:
        raise ValueError("target is empty")
    return Path(*parts)


def safe_relative(value: str) -> Path:
    path = Path(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"unsafe runtime resource path: {value!r}")
    return path


def plan(runtime: Path, manifest: dict) -> list[Replacement]:
    runtime = runtime.resolve(strict=True)
    if (
        manifest.get("schema_version") != 2
        or manifest.get("integrity_phase") != "staged"
        or not isinstance(manifest.get("files"), list)
    ):
        raise ValueError("packaged symlink restoration requires a staged resource manifest")

    replacements: list[Replacement] = []
    seen: set[Path] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or entry.get("kind") != "symlink":
            continue
        relative_text = entry.get("path")
        target_text = entry.get("target")
        if not isinstance(relative_text, str) or not isinstance(target_text, str):
            raise ValueError("invalid symlink entry in staged resource manifest")
        relative = safe_relative(relative_text)
        if relative in seen:
            raise ValueError(f"duplicate staged symlink entry: {relative_text}")
        seen.add(relative)
        destination = lexical_destination(relative, Path(target_text))
        link_path = runtime / relative
        destination_path = runtime / destination

        link_metadata = link_path.lstat()
        if link_path.is_symlink():
            if os.readlink(link_path) != target_text:
                raise ValueError(f"packaged symlink target mismatch: {relative_text}")
            continue
        if not stat.S_ISREG(link_metadata.st_mode):
            raise ValueError(
                f"packaged symlink was not flattened to a regular file: {relative_text}"
            )

        resolved_destination = destination_path.resolve(strict=True)
        try:
            resolved_destination.relative_to(runtime)
        except ValueError as exc:
            raise ValueError(
                f"packaged symlink target escapes the runtime payload: {relative_text}"
            ) from exc
        if not resolved_destination.is_file():
            raise ValueError(
                f"packaged symlink target is not a regular file: {relative_text}"
            )
        if (
            link_metadata.st_size != resolved_destination.stat().st_size
            or sha256(link_path) != sha256(resolved_destination)
        ):
            raise ValueError(
                f"flattened packaged symlink differs from its target: {relative_text}"
            )
        replacements.append(
            Replacement(
                path=link_path,
                relative_path=relative_text,
                target=target_text,
            )
        )
    return replacements


def restore(runtime: Path, manifest_path: Path) -> int:
    runtime = runtime.resolve(strict=True)
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read staged resource manifest") from exc
    replacements = plan(runtime, manifest)

    # The complete plan is validated before any path changes. Each replacement
    # is then a same-directory atomic swap from a verified flattened copy to the
    # original relative symlink.
    for replacement in replacements:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{replacement.path.name}.symlink-",
            dir=replacement.path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        temporary.unlink()
        try:
            os.symlink(replacement.target, temporary)
            os.replace(temporary, replacement.path)
        finally:
            temporary.unlink(missing_ok=True)
    return len(replacements)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        restored = restore(args.runtime, args.manifest)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"packaged runtime symlink restoration failed: {exc}") from exc
    print(f"Restored {restored} verified packaged runtime symlinks")


if __name__ == "__main__":
    main()
