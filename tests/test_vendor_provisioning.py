import importlib.util
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest


_SPEC = importlib.util.spec_from_file_location(
    "opswitness_provision_macos_vendor",
    Path(__file__).parents[1] / "scripts" / "provision_macos_vendor.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_PROVISION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PROVISION)


def _tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        root = tarfile.TarInfo(".")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o755 if name.endswith(("/aioncore", "/node")) else 0o644
            archive.addfile(info, io.BytesIO(body))


def _component(
    identifier: str,
    source: Path,
    *,
    archive_type: str,
    root_path: str,
    output_kind: str,
    entrypoint: str,
    required_paths: list[str],
) -> dict[str, object]:
    suffix = ".tar.gz" if archive_type == "tar.gz" else ""
    return {
        "id": identifier,
        "version": "1",
        "source_url": f"https://downloads.example.test/{identifier}{suffix}",
        "upstream_sha256": _PROVISION.sha256(source),
        "license": "MIT",
        "notice": "fixture",
        "redistribution_review": "approved",
        "entrypoints": [entrypoint],
        "provision": {
            "archive_type": archive_type,
            "root_path": root_path,
            "output_kind": output_kind,
            "entrypoint": entrypoint,
            "required_paths": required_paths,
        },
    }


def _complete_lock(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    sources = {
        "node": tmp_path / "node",
        "codex": tmp_path / "codex",
        "paperclip": tmp_path / "paperclip.tar.gz",
        "aioncore": tmp_path / "aioncore.tar.gz",
    }
    sources["node"].write_bytes(b"node")
    sources["codex"].write_bytes(b"codex")
    _tar(
        sources["paperclip"],
        {
            "package/dist/index.js": b"console.log('paperclip')",
            "package/node_modules/dependency/index.js": b"module.exports = true",
        },
    )
    _tar(
        sources["aioncore"],
        {
            "payload/aioncore/aioncore": b"aion",
            "payload/aioncore/managed-resources/resource.txt": b"resource",
        },
    )
    components = [
        {
            "id": "opswitness-backend",
            "version": "0.1.0-alpha.1",
            "source_url": "https://github.com/opswitness/opswitness",
            "upstream_sha256": None,
            "license": "Apache-2.0",
            "notice": "first party",
            "redistribution_review": "blocked",
            "entrypoints": ["backend/opswitness-backend"],
            "provision": None,
        },
        _component(
            "node",
            sources["node"],
            archive_type="raw",
            root_path=".",
            output_kind="executable",
            entrypoint="node",
            required_paths=["node"],
        ),
        _component(
            "paperclip",
            sources["paperclip"],
            archive_type="tar.gz",
            root_path="package",
            output_kind="directory",
            entrypoint="dist/index.js",
            required_paths=["dist/index.js", "node_modules/dependency/index.js"],
        ),
        _component(
            "aioncore",
            sources["aioncore"],
            archive_type="tar.gz",
            root_path="payload/aioncore",
            output_kind="directory",
            entrypoint="aioncore",
            required_paths=["aioncore", "managed-resources/resource.txt"],
        ),
        _component(
            "codex",
            sources["codex"],
            archive_type="raw",
            root_path=".",
            output_kind="executable",
            entrypoint="codex",
            required_paths=["codex"],
        ),
    ]
    lock = tmp_path / "vendor-lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": components,
            }
        ),
        encoding="utf-8",
    )
    return lock, sources


def test_repository_vendor_lock_intentionally_blocks_public_provisioning():
    lock = Path(__file__).parents[1] / "desktop" / "vendor-lock.json"

    with pytest.raises(_PROVISION.ProvisionError, match="redistribution review"):
        _PROVISION.validate_lock(lock)


def test_provision_downloads_checks_and_exports_exact_runtime_paths(tmp_path):
    lock, sources = _complete_lock(tmp_path)
    by_url = {
        component["source_url"]: sources[component["id"]]
        for component in json.loads(lock.read_text())["components"]
        if component["id"] != "opswitness-backend"
    }

    def fetch(url: str, destination: Path) -> None:
        shutil.copyfile(by_url[url], destination)

    resolved = _PROVISION.provision(lock, tmp_path / "provisioned", fetcher=fetch)
    environment = tmp_path / "github-env"
    _PROVISION._write_github_env(environment, resolved)

    assert Path(resolved["node"]["path"]).read_bytes() == b"node"
    assert Path(resolved["codex"]["path"]).read_bytes() == b"codex"
    assert Path(resolved["paperclip"]["path"], "dist", "index.js").is_file()
    assert Path(resolved["aioncore"]["path"], "managed-resources", "resource.txt").is_file()
    exported = environment.read_text(encoding="utf-8")
    assert "OPSWITNESS_NODE_BIN=" in exported
    assert "OPSWITNESS_PAPERCLIP_DIR=" in exported
    assert "OPSWITNESS_AIONCORE_DIR=" in exported
    assert "OPSWITNESS_CODEX_BIN=" in exported


def test_provision_rejects_download_with_wrong_digest(tmp_path):
    lock, sources = _complete_lock(tmp_path)
    payload = json.loads(lock.read_text())
    node = next(item for item in payload["components"] if item["id"] == "node")
    node["upstream_sha256"] = "0" * 64
    lock.write_text(json.dumps(payload))

    def fetch(url: str, destination: Path) -> None:
        identifier = Path(url).name.removesuffix(".tar.gz")
        shutil.copyfile(sources[identifier], destination)

    with pytest.raises(_PROVISION.ProvisionError, match="SHA-256 mismatch"):
        _PROVISION.provision(lock, tmp_path / "provisioned", fetcher=fetch)


def test_provision_rejects_archive_link_that_escapes_root(tmp_path):
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        link = tarfile.TarInfo("payload/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        bundle.addfile(link)

    with pytest.raises(_PROVISION.ProvisionError, match="escapes extraction root"):
        _PROVISION._extract_tar(archive, tmp_path / "extract")


def test_provision_rejects_mutable_or_parameterized_source_url(tmp_path):
    lock, _ = _complete_lock(tmp_path)
    payload = json.loads(lock.read_text())
    node = next(item for item in payload["components"] if item["id"] == "node")
    node["source_url"] = "https://downloads.example.test/latest?asset=node"
    lock.write_text(json.dumps(payload))

    with pytest.raises(_PROVISION.ProvisionError, match="without credentials"):
        _PROVISION.validate_lock(lock)
