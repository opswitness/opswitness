#!/usr/bin/env python3
"""Normalize staged macOS Mach-O resources to the supported arm64 slice.

This is intentionally a *slice* operation, not a dependency-pruning step. It
replaces a universal Mach-O only with its existing arm64 slice. The sole
exception is a Mach-O in an explicit vendor x64 prebuild directory: it is an
unusable alternative platform payload and is excluded file-by-file while its
package directories and all arm64 resources remain intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from re import fullmatch


LIPO = "/usr/bin/lipo"
TARGET_ARCHITECTURE = "arm64"
PROVENANCE_SCHEMA_VERSION = 1
MACHO_MAGICS = frozenset(
    {
        b"\xce\xfa\xed\xfe",  # MH_MAGIC
        b"\xfe\xed\xfa\xce",  # MH_CIGAM
        b"\xcf\xfa\xed\xfe",  # MH_MAGIC_64
        b"\xfe\xed\xfa\xcf",  # MH_CIGAM_64
        b"\xca\xfe\xba\xbe",  # FAT_MAGIC
        b"\xbe\xba\xfe\xca",  # FAT_CIGAM
        b"\xca\xfe\xba\xbf",  # FAT_MAGIC_64
        b"\xbf\xba\xfe\xca",  # FAT_CIGAM_64
    }
)
NON_ARM_PREBUILD_TARGET = r"(?:x64|x86_64|amd64|ia32|i386)"
APPLE_PREBUILD_TARGET = r"(?:darwin|macos|osx|ios)"
VENDOR_NON_ARM_PREBUILD_DIRECTORY = (
    rf"{APPLE_PREBUILD_TARGET}-{NON_ARM_PREBUILD_TARGET}(?:-simulator)?"
)
NON_ARM_MACHO_ARCHITECTURES = frozenset({"x86_64", "i386"})


@dataclass(frozen=True)
class MachO:
    path: Path
    relative_path: str
    before_archs: tuple[str, ...]
    before_sha256: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{argv[0]} failed for {argv[-1]}: {detail}")
    return completed.stdout.strip()


def is_macho(path: Path) -> bool:
    # Reading the fixed file magic avoids launching `/usr/bin/file` once for
    # every JavaScript or metadata file in the complete vendor dependency tree.
    with path.open("rb") as handle:
        return handle.read(4) in MACHO_MAGICS


def lipo_archs(path: Path) -> tuple[str, ...]:
    raw = _run([LIPO, "-archs", str(path)])
    archs = tuple(raw.split())
    if not archs:
        raise RuntimeError(f"lipo reported no architectures for {path}")
    return archs


def regular_files(runtime: Path) -> list[Path]:
    """Return regular files in lexical order without following symlinks."""

    files: list[Path] = []
    for directory, directory_names, file_names in os.walk(runtime, followlinks=False):
        directory_names[:] = sorted(
            name for name in directory_names if not (Path(directory) / name).is_symlink()
        )
        directory_path = Path(directory)
        for name in sorted(file_names):
            path = directory_path / name
            if not path.is_symlink() and path.is_file():
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(runtime).as_posix())


def inspect(runtime: Path) -> list[MachO]:
    records: list[MachO] = []
    for path in regular_files(runtime):
        if not is_macho(path):
            continue
        records.append(
            MachO(
                path=path,
                relative_path=path.relative_to(runtime).as_posix(),
                before_archs=lipo_archs(path),
                before_sha256=sha256(path),
            )
        )
    return records


def is_excludable_non_arm_vendor_prebuild(record: MachO) -> bool:
    """Allow only explicit Apple x64 vendor prebuild leaf directories.

    The target directory must be the immediate child of a literal ``prebuilds``
    directory, such as ``prebuilds/darwin-x64`` or
    ``prebuilds/ios-x64-simulator``. The Mach-O itself must be Intel-only. A
    similarly named arbitrary directory, an ARM object, or an unknown CPU
    architecture never qualifies.
    """

    parts = Path(record.relative_path).parts
    for index, part in enumerate(parts[:-2]):
        if part != "prebuilds":
            continue
        target = parts[index + 1]
        if fullmatch(VENDOR_NON_ARM_PREBUILD_DIRECTORY, target) is None:
            continue
        return set(record.before_archs).issubset(NON_ARM_MACHO_ARCHITECTURES)
    return False


def validate(records: list[MachO]) -> list[MachO]:
    exclusions = [
        record
        for record in records
        if TARGET_ARCHITECTURE not in record.before_archs
        and is_excludable_non_arm_vendor_prebuild(record)
    ]
    invalid = [
        record
        for record in records
        if TARGET_ARCHITECTURE not in record.before_archs and record not in exclusions
    ]
    if invalid:
        rendered = ", ".join(
            f"{record.relative_path} ({' '.join(record.before_archs)})" for record in invalid
        )
        raise RuntimeError(
            "staged Mach-O resources without an arm64 slice are forbidden: " + rendered
        )
    return exclusions


def _thin(record: MachO) -> tuple[Path, int]:
    """Create and verify a sibling arm64 slice without mutating the source."""

    mode = stat.S_IMODE(record.path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{record.path.name}.arm64-", dir=record.path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _run([LIPO, str(record.path), "-thin", TARGET_ARCHITECTURE, "-output", str(temporary)])
        os.chmod(temporary, mode)
        after_archs = lipo_archs(temporary)
        if after_archs != (TARGET_ARCHITECTURE,):
            raise RuntimeError(
                f"thin output for {record.relative_path} is not arm64-only: {' '.join(after_archs)}"
            )
        return temporary, mode
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def normalize(runtime: Path, provenance: Path) -> dict[str, object]:
    runtime = runtime.resolve(strict=True)
    try:
        provenance.relative_to(runtime)
    except ValueError as exc:
        raise ValueError("provenance path must be inside the runtime payload") from exc
    if provenance.is_symlink():
        raise ValueError("provenance path must not be a symlink")

    records = inspect(runtime)
    # Validate and prepare the complete tree before changing any Mach-O path.
    exclusions = validate(records)
    exclusion_paths = {record.path for record in exclusions}
    temporary_slices: list[tuple[MachO, Path, int]] = []
    try:
        for record in records:
            if record.path in exclusion_paths:
                continue
            if record.before_archs == (TARGET_ARCHITECTURE,):
                continue
            temporary, mode = _thin(record)
            temporary_slices.append((record, temporary, mode))

        thin_by_path = {record.path: temporary for record, temporary, _ in temporary_slices}
        entries: list[dict[str, object]] = []
        for record in records:
            if record.path in exclusion_paths:
                entries.append(
                    {
                        "path": record.relative_path,
                        "before_archs": list(record.before_archs),
                        "after_archs": [],
                        "before_sha256": record.before_sha256,
                        "after_sha256": None,
                        "action": "excluded_non_arm_vendor_prebuild",
                    }
                )
                continue
            temporary = thin_by_path.get(record.path)
            after_path = temporary or record.path
            after_archs = lipo_archs(after_path)
            if after_archs != (TARGET_ARCHITECTURE,):
                raise RuntimeError(
                    f"normalized Mach-O is not arm64-only: {record.relative_path} "
                    f"({' '.join(after_archs)})"
                )
            entries.append(
                {
                    "path": record.relative_path,
                    "before_archs": list(record.before_archs),
                    "after_archs": list(after_archs),
                    "before_sha256": record.before_sha256,
                    "after_sha256": sha256(after_path),
                    "action": "preserved" if temporary is None else "thinned_to_arm64",
                }
            )

        # All temporary slices were verified first, so this is an all-or-nothing
        # plan up to the final same-directory atomic replacements.
        for record, temporary, mode in temporary_slices:
            os.replace(temporary, record.path)
            os.chmod(record.path, mode)
        # Exclusions are planned and validated before any replacement. Remove
        # only the Mach-O leaf file; keep every package and dependency directory.
        for record in exclusions:
            record.path.unlink()

        payload: dict[str, object] = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "target_architecture": TARGET_ARCHITECTURE,
            "entries": entries,
        }
        provenance.parent.mkdir(parents=True, exist_ok=True)
        temporary_provenance = provenance.with_suffix(provenance.suffix + ".tmp")
        temporary_provenance.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary_provenance, provenance)
        os.chmod(provenance, 0o644)
        return payload
    finally:
        for _, temporary, _ in temporary_slices:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument(
        "--provenance",
        type=Path,
        help="path inside runtime for deterministic architecture provenance",
    )
    args = parser.parse_args()
    runtime = args.runtime.resolve(strict=True)
    provenance = args.provenance or runtime / "architecture-provenance.json"
    if not provenance.is_absolute():
        provenance = runtime / provenance
    try:
        normalize(runtime, provenance)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"macOS runtime architecture normalization failed: {exc}") from exc


if __name__ == "__main__":
    main()
