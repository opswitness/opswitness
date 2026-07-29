#!/usr/bin/env python3
"""Verify that every public release surface describes the same OpsWitness build."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


PRODUCT_NAME = "OpsWitness"
DISTRIBUTION_NAME = "opswitness"
PYTHON_VERSION = "0.1.0a2"
PUBLIC_VERSION = "0.1.0-alpha.2"
RELEASE_TAG = f"v{PUBLIC_VERSION}"
REPOSITORY_URL = "https://github.com/opswitness/opswitness"


def _pep440_public(version: str) -> str | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)a(\d+)", version)
    if match is None:
        return None
    major, minor, patch, alpha = match.groups()
    return f"{major}.{minor}.{patch}-alpha.{alpha}"


def _module_version(path: Path) -> str | None:
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$',
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _frontend_constant(path: Path) -> str | None:
    match = re.search(
        r"^export const APP_VERSION = ['\"]([^'\"]+)['\"];\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _editable_lock_package(path: Path) -> dict[str, object] | None:
    with path.open("rb") as source:
        packages = tomllib.load(source).get("package", [])
    editable = [
        package
        for package in packages
        if package.get("source") == {"editable": "."}
    ]
    return editable[0] if len(editable) == 1 else None


def identity_errors(root: Path, *, tag: str) -> list[str]:
    errors: list[str] = []
    with (root / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    frontend = json.loads((root / "console-ui" / "package.json").read_text())
    lock = json.loads((root / "console-ui" / "package-lock.json").read_text())
    manifest = json.loads(
        (root / "console-ui" / "public" / "manifest.webmanifest").read_text()
    )
    editable_lock = _editable_lock_package(root / "uv.lock")
    with (root / "desktop" / "src-tauri" / "Cargo.toml").open("rb") as source:
        desktop_package = tomllib.load(source)["package"]
    with (root / "desktop" / "src-tauri" / "Cargo.lock").open("rb") as source:
        desktop_lock_packages = tomllib.load(source).get("package", [])
    desktop_lock_package = [
        package
        for package in desktop_lock_packages
        if package.get("name") == "opswitness-desktop"
    ]
    tauri = json.loads(
        (root / "desktop" / "src-tauri" / "tauri.conf.json").read_text()
    )
    vendor_lock = json.loads((root / "desktop" / "vendor-lock.json").read_text())
    first_party_components = [
        component
        for component in vendor_lock.get("components", [])
        if component.get("id") == "opswitness-backend"
    ]

    def expect(label: str, actual: object, expected: object) -> None:
        if actual != expected:
            errors.append(f"{label}: expected {expected!r}, found {actual!r}")

    expect("distribution", project.get("name"), DISTRIBUTION_NAME)
    expect("python version", project.get("version"), PYTHON_VERSION)
    expect("PEP 440 mapping", _pep440_public(str(project.get("version"))), PUBLIC_VERSION)
    expect("tag", tag, RELEASE_TAG)
    expect("requires-python", project.get("requires-python"), ">=3.12,<3.13")
    lock_metadata = tomllib.loads((root / "uv.lock").read_text())
    expect(
        "uv lock requires-python",
        lock_metadata.get("requires-python"),
        "==3.12.*",
    )
    expect(
        "uv lock editable package",
        editable_lock and editable_lock.get("name"),
        DISTRIBUTION_NAME,
    )
    expect(
        "uv lock editable version",
        editable_lock and editable_lock.get("version"),
        PYTHON_VERSION,
    )
    scripts = project.get("scripts", {})
    expect("primary CLI", scripts.get("opswitness"), "opswitness.cli:app")
    expect("compatibility CLI", scripts.get("qd"), "opswitness.cli:app")
    urls = project.get("urls", {})
    expect("homepage", urls.get("Homepage"), REPOSITORY_URL)
    expect("repository", urls.get("Repository"), REPOSITORY_URL)
    expect("issues", urls.get("Issues"), f"{REPOSITORY_URL}/issues")
    expect(
        "module version",
        _module_version(root / "src" / "opswitness" / "__init__.py"),
        PYTHON_VERSION,
    )
    expect("frontend name", frontend.get("name"), "opswitness-console-ui")
    expect("frontend version", frontend.get("version"), PUBLIC_VERSION)
    expect("lockfile version", lock.get("version"), PUBLIC_VERSION)
    expect("lockfile root version", lock.get("packages", {}).get("", {}).get("version"), PUBLIC_VERSION)
    expect(
        "frontend display version",
        _frontend_constant(root / "console-ui" / "src" / "version.ts"),
        PUBLIC_VERSION,
    )
    expect("desktop package version", desktop_package.get("version"), PUBLIC_VERSION)
    expect(
        "desktop lock package count",
        len(desktop_lock_package),
        1,
    )
    expect(
        "desktop lock package version",
        desktop_lock_package[0].get("version") if len(desktop_lock_package) == 1 else None,
        PUBLIC_VERSION,
    )
    expect("Tauri version", tauri.get("version"), PUBLIC_VERSION)
    expect(
        "first-party vendor component count",
        len(first_party_components),
        1,
    )
    expect(
        "first-party vendor version",
        first_party_components[0].get("version")
        if len(first_party_components) == 1
        else None,
        PUBLIC_VERSION,
    )
    expect("PWA name", manifest.get("name"), PRODUCT_NAME)
    expect("PWA short name", manifest.get("short_name"), PRODUCT_NAME)

    readme = (root / "README.md").read_text(encoding="utf-8")
    if not readme.startswith(f"# {PRODUCT_NAME}\n"):
        errors.append("README: first heading must be '# OpsWitness'")
    if (root / "src" / "quarterdeck").exists():
        errors.append("legacy Python package directory still exists: src/quarterdeck")
    public_metadata = json.dumps(
        {
            "project": project,
            "frontend": frontend,
            "manifest": manifest,
        },
        sort_keys=True,
    ).casefold()
    if "quarterdeck" in public_metadata:
        errors.append("legacy brand remains in public package metadata")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", default=RELEASE_TAG)
    args = parser.parse_args()
    errors = identity_errors(args.root.resolve(), tag=args.tag)
    if errors:
        for error in errors:
            print(f"release identity error: {error}", file=sys.stderr)
        return 1
    print(f"release identity verified: {PRODUCT_NAME} {RELEASE_TAG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
