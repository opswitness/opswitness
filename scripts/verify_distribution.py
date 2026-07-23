#!/usr/bin/env python3
"""Fail closed when release archives contain private or untracked workspace files."""

from __future__ import annotations

import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath

from packaging.specifiers import InvalidSpecifier, SpecifierSet


class DistributionError(ValueError):
    pass


SDIST_ROOTS = {
    ".gitignore",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "PKG-INFO",
    "README.md",
    "SECURITY.md",
    "console-ui",
    "docs",
    "examples",
    "pyproject.toml",
    "scripts",
    "src",
    "tests",
}
SDIST_REQUIRED = {
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
    "docs/KNOWN-LIMITATIONS.md",
    "docs/QUICKSTART.md",
    "docs/SUPPORT-MATRIX.md",
    "pyproject.toml",
    "examples/showcase/run.py",
    "src/opswitness/__init__.py",
    "src/opswitness/console/static/index.html",
    "src/opswitness/templates/quant-fleet/launchd/com.opswitness.console.plist",
}
FORBIDDEN_PARTS = {
    ".claude",
    ".codex",
    ".env",
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "secrets.yaml",
    "settings.local.json",
}


def _safe_parts(name: str) -> tuple[str, ...]:
    if "\\" in name:
        raise DistributionError(f"archive path uses a backslash: {name}")
    path = PurePosixPath(name.rstrip("/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DistributionError(f"unsafe archive path: {name}")
    return path.parts


def _reject_private(parts: tuple[str, ...], name: str) -> None:
    lowered = {part.casefold() for part in parts}
    if lowered & FORBIDDEN_PARTS or any(part.startswith(".") for part in parts):
        raise DistributionError(f"private or hidden path in distribution: {name}")


def tracked_files() -> set[str]:
    try:
        output = subprocess.check_output(["git", "ls-files", "-z"])
    except (OSError, subprocess.CalledProcessError) as exc:
        raise DistributionError("git-tracked file inventory is unavailable") from exc
    return {item.decode() for item in output.split(b"\0") if item}


def verify_sdist(path: Path, *, tracked: set[str] | None = None) -> None:
    tracked = tracked if tracked is not None else tracked_files()
    files: set[str] = set()
    archive_root: str | None = None
    try:
        archive = tarfile.open(path, "r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise DistributionError(f"cannot read sdist {path}") from exc
    with archive:
        for member in archive.getmembers():
            parts = _safe_parts(member.name)
            root = parts[0]
            _reject_private((root,), member.name)
            if archive_root is None:
                archive_root = root
            elif root != archive_root:
                raise DistributionError("sdist contains more than one archive root")
            if not (member.isfile() or member.isdir()):
                raise DistributionError(f"sdist contains a non-file entry: {member.name}")
            relative = parts[1:]
            if not relative:
                continue
            if relative != (".gitignore",):
                _reject_private(relative, member.name)
            if relative[0] not in SDIST_ROOTS:
                raise DistributionError(f"unexpected sdist root: {relative[0]}")
            if member.isfile():
                files.add("/".join(relative))

    missing = sorted(SDIST_REQUIRED - files)
    if missing:
        raise DistributionError("sdist is missing required files: " + ", ".join(missing))
    untracked = sorted(files - tracked - {"PKG-INFO"})
    if untracked:
        raise DistributionError("sdist contains untracked files: " + ", ".join(untracked))


def _project_identity(pyproject: Path = Path("pyproject.toml")) -> tuple[str, str]:
    with pyproject.open("rb") as source:
        project = tomllib.load(source)["project"]
    normalized = re.sub(r"[-_.]+", "_", str(project["name"]))
    return normalized, str(project["version"])


def verify_wheel(path: Path, *, pyproject: Path = Path("pyproject.toml")) -> None:
    package, version = _project_identity(pyproject)
    dist_info = f"{package}-{version}.dist-info"
    required = {
        f"{package}/__init__.py",
        f"{package}/console/static/index.html",
        f"{package}/templates/quant-fleet/launchd/com.opswitness.console.plist",
        f"{dist_info}/METADATA",
        f"{dist_info}/entry_points.txt",
        f"{dist_info}/licenses/LICENSE",
        f"{dist_info}/licenses/NOTICE",
    }
    files: set[str] = set()
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DistributionError(f"cannot read wheel {path}") from exc
    metadata_text = ""
    entry_points_text = ""
    with archive:
        for info in archive.infolist():
            parts = _safe_parts(info.filename)
            _reject_private(parts, info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise DistributionError(f"wheel contains a symlink: {info.filename}")
            if parts[0] not in {package, dist_info}:
                raise DistributionError(f"unexpected wheel root: {parts[0]}")
            if not info.is_dir():
                files.add("/".join(parts))
        metadata_name = f"{dist_info}/METADATA"
        entry_points_name = f"{dist_info}/entry_points.txt"
        if metadata_name in files:
            metadata_text = archive.read(metadata_name).decode("utf-8")
        if entry_points_name in files:
            entry_points_text = archive.read(entry_points_name).decode("utf-8")
    missing = sorted(required - files)
    if missing:
        raise DistributionError("wheel is missing required files: " + ", ".join(missing))
    metadata = Parser().parsestr(metadata_text)
    if metadata.get("Name") != "opswitness":
        raise DistributionError(f"wheel metadata has unexpected Name: {metadata.get('Name')}")
    if metadata.get("Version") != version:
        raise DistributionError(f"wheel metadata has unexpected Version: {metadata.get('Version')}")
    requires_python = metadata.get("Requires-Python")
    try:
        parsed_requires_python = SpecifierSet(requires_python or "")
    except InvalidSpecifier as exc:
        raise DistributionError(
            f"wheel metadata has invalid Requires-Python: {requires_python}"
        ) from exc
    if parsed_requires_python != SpecifierSet(">=3.12,<3.13"):
        raise DistributionError(
            f"wheel metadata has unexpected Requires-Python: {requires_python}"
        )
    expected_entries = {
        "opswitness = opswitness.cli:app",
        "qd = opswitness.cli:app",
    }
    entry_lines = {line.strip() for line in entry_points_text.splitlines() if " = " in line}
    if entry_lines != expected_entries:
        raise DistributionError(
            "wheel console scripts do not match the primary and compatibility CLIs"
        )


def verify_directory(dist: Path) -> tuple[Path, Path]:
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise DistributionError(
            f"expected exactly one wheel and one sdist under {dist}; "
            f"found wheels={len(wheels)} sdists={len(sdists)}"
        )
    verify_wheel(wheels[0])
    verify_sdist(sdists[0])
    return wheels[0], sdists[0]


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    try:
        wheel, sdist = verify_directory(dist)
    except DistributionError as exc:
        print(f"distribution verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"distribution verified: {wheel.name}, {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
