#!/usr/bin/env python3
"""Create checksums and a fail-closed provenance manifest for release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path


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
    return sorted(
        [
            *dist.glob("*.whl"),
            *dist.glob("*.tar.gz"),
            *dist.glob("*.spdx.json"),
        ],
        key=lambda path: path.name,
    )


def assert_spdx_sbom(path: Path, *, distribution: str) -> None:
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
        for package in packages
    ):
        raise ValueError(
            f"SPDX SBOM does not identify the {distribution} distribution: {path.name}"
        )


def write_manifest(
    *,
    root: Path,
    dist: Path,
    tag: str,
    require_sbom: bool = False,
) -> dict[str, object]:
    assert_clean_tree(root)
    distribution, python_version, public_version, expected_tag = release_identity(root)
    if tag != expected_tag:
        raise ValueError(f"release tag mismatch: expected {expected_tag}, found {tag}")

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
        for sbom in sboms:
            assert_spdx_sbom(sbom, distribution=distribution)

    records = [
        {"name": path.name, "sha256": sha256(path), "size": path.stat().st_size}
        for path in files
    ]
    (dist / "SHA256SUMS").write_text(
        "".join(f"{record['sha256']}  {record['name']}\n" for record in records),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 2,
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
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"release manifest failed: {exc}", file=sys.stderr)
        return 1
    print(f"release manifest written for {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
