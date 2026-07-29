import importlib.util
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
STAGE_SCRIPT = ROOT / "desktop/scripts/stage_codex_only_paperclip.py"
MANIFEST_SCRIPT = ROOT / "desktop/scripts/make_resource_manifest.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_module = _load("stage_codex_only_paperclip", STAGE_SCRIPT)
manifest_module = _load("paperclip_resource_manifest", MANIFEST_SCRIPT)


def _vendor_lock(tmp_path: Path, *, version: str = "2026.707.0") -> Path:
    path = tmp_path / "vendor-lock.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": [
                    {
                        "id": "paperclip",
                        "version": version,
                        "entrypoints": ["paperclip/dist/index.js"],
                        "required_prefixes": ["paperclip/node_modules/"],
                        "staging_filter": {
                            "profile": "codex-only",
                            "applies_to_version": version,
                            "source_exclusions": [
                                path.as_posix()
                                for path in stage_module.SOURCE_SUBTREES
                            ],
                            "receipt": stage_module.RECEIPT_PATH.as_posix(),
                        },
                    }
                ],
            }
        )
    )
    return path


def _package(path: Path, name: str, version: str, license_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "license": license_name,
            },
            sort_keys=True,
        )
    )


def _upstream_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    paperclip = runtime / "paperclip"
    (paperclip / "dist").mkdir(parents=True)
    (paperclip / "dist/index.js").write_text("fixture-paperclip\n")

    acp = runtime / stage_module.SOURCE_SUBTREES[0]
    _package(
        acp / "package.json",
        "@agentclientprotocol/claude-agent-acp",
        "0.52.0",
        "Apache-2.0",
    )
    (acp / "dist").mkdir()
    (acp / "dist/index.js").write_text("fixture-acp\n")
    _package(
        acp / "node_modules/@anthropic-ai/claude-agent-sdk/package.json",
        "@anthropic-ai/claude-agent-sdk",
        "0.3.191",
        "SEE LICENSE IN README.md",
    )

    native = runtime / stage_module.SOURCE_SUBTREES[1]
    _package(
        native / "package.json",
        "@anthropic-ai/claude-agent-sdk-darwin-arm64",
        "0.3.191",
        "SEE LICENSE IN LICENSE.md",
    )
    (native / "LICENSE.md").write_text("fixture-license\n")
    (native / "claude").write_bytes(b"fixture-native-claude")
    (native / "claude").chmod(0o755)
    (native / "README.md").write_text("fixture\n")

    bin_directory = paperclip / "node_modules/.bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "claude-agent-acp").symlink_to(
        stage_module.COMPANION_LINK_TARGET
    )
    for adapter in ("adapter-claude-local", "adapter-acpx-local"):
        _package(
            paperclip / f"node_modules/@paperclipai/{adapter}/package.json",
            f"@paperclipai/{adapter}",
            "2026.707.0",
            "MIT",
        )
    return runtime


def _lock_fixture(monkeypatch, runtime: Path) -> None:
    entrypoint = runtime / stage_module.PAPERCLIP_ENTRYPOINT
    monkeypatch.setattr(
        stage_module,
        "PAPERCLIP_ENTRYPOINT_SHA256",
        stage_module.sha256_file(entrypoint),
    )
    trees = {
        relative: stage_module.tree_summary(runtime / relative)
        for relative in stage_module.SOURCE_SUBTREES
    }
    markers = {}
    for relative, relative_markers in stage_module.SOURCE_MARKERS.items():
        for marker in relative_markers:
            path = runtime / relative / marker
            markers[relative / marker] = (
                stage_module.sha256_file(path),
                path.stat().st_size,
            )
    monkeypatch.setattr(stage_module, "EXPECTED_SOURCE_TREES", trees)
    monkeypatch.setattr(stage_module, "EXPECTED_MARKERS", markers)


def _stage(tmp_path: Path, monkeypatch) -> tuple[Path, Path, dict]:
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    _lock_fixture(monkeypatch, runtime)
    payload = stage_module.stage(
        runtime,
        lock,
        runtime / stage_module.RECEIPT_PATH,
    )
    return runtime, lock, payload


def test_filter_removes_only_locked_payloads_and_companion_link(
    tmp_path, monkeypatch
):
    runtime, _, payload = _stage(tmp_path, monkeypatch)

    for relative in stage_module.SOURCE_SUBTREES:
        assert not (runtime / relative).exists()
    assert not (runtime / stage_module.COMPANION_LINK).exists()
    assert (
        runtime
        / "paperclip/node_modules/@paperclipai/adapter-claude-local/package.json"
    ).is_file()
    assert (
        runtime
        / "paperclip/node_modules/@paperclipai/adapter-acpx-local/package.json"
    ).is_file()
    assert payload["proprietary_path_scan"]["forbidden_matches"] == []
    assert payload["removed_companion_links"] == [
        {
            "path": stage_module.COMPANION_LINK.as_posix(),
            "target": stage_module.COMPANION_LINK_TARGET,
        }
    ]
    assert payload["locked_paperclip_entrypoint"]["sha256"] == (
        stage_module.PAPERCLIP_ENTRYPOINT_SHA256
    )


def test_filter_rejects_marker_drift_before_removing_anything(
    tmp_path, monkeypatch
):
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    _lock_fixture(monkeypatch, runtime)
    marker = runtime / stage_module.SOURCE_SUBTREES[1] / "claude"
    marker.write_bytes(marker.read_bytes() + b"-changed")

    with pytest.raises(SystemExit, match="payload tree changed"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )

    assert marker.exists()
    assert (runtime / stage_module.COMPANION_LINK).is_symlink()


def test_filter_rejects_symlinked_parent_and_changed_link_target(
    tmp_path, monkeypatch
):
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    _lock_fixture(monkeypatch, runtime)
    scope = runtime / "paperclip/node_modules/@agentclientprotocol"
    real_scope = scope.with_name("agentclientprotocol-real")
    scope.rename(real_scope)
    scope.symlink_to(real_scope.name, target_is_directory=True)

    with pytest.raises(SystemExit, match="parents must be real directories"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )

    scope.unlink()
    real_scope.rename(scope)
    link = runtime / stage_module.COMPANION_LINK
    link.unlink()
    link.symlink_to("../@paperclipai/adapter-acpx-local/dist/index.js")
    with pytest.raises(SystemExit, match="link target changed"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )


def test_filter_rejects_unreviewed_paperclip_version(tmp_path, monkeypatch):
    runtime = _upstream_runtime(tmp_path)
    _lock_fixture(monkeypatch, runtime)
    lock = _vendor_lock(tmp_path, version="2026.708.0")

    with pytest.raises(SystemExit, match="locked to version"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )


def test_filter_rejects_wrong_receipt_path_before_mutation(tmp_path, monkeypatch):
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    _lock_fixture(monkeypatch, runtime)

    with pytest.raises(SystemExit, match="vendor-locked path"):
        stage_module.stage(runtime, lock, runtime / "wrong-receipt.json")

    assert all((runtime / relative).is_dir() for relative in stage_module.SOURCE_SUBTREES)
    assert (runtime / stage_module.COMPANION_LINK).is_symlink()


def test_resource_manifest_binds_paperclip_receipt(tmp_path, monkeypatch):
    runtime, lock, receipt = _stage(tmp_path, monkeypatch)
    (runtime / "architecture-provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_architecture": "arm64",
                "entries": [],
            }
        )
    )
    monkeypatch.setattr(
        manifest_module,
        "PAPERCLIP_ENTRYPOINT_SHA256",
        manifest_module.sha256(runtime / "paperclip/dist/index.js"),
    )
    monkeypatch.setattr(
        manifest_module,
        "PAPERCLIP_STAGING_TREES",
        {
            entry["path"]: entry["original_tree"]
            for entry in receipt["source_exclusions"]
        },
    )
    monkeypatch.setattr(
        manifest_module,
        "PAPERCLIP_STAGING_MARKERS",
        {
            entry["path"]: entry["original_markers"]
            for entry in receipt["source_exclusions"]
        },
    )
    monkeypatch.setattr(manifest_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(manifest_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(MANIFEST_SCRIPT),
            "--runtime",
            str(runtime),
            "--vendor-lock",
            str(lock),
            "--mode",
            "adhoc",
        ],
    )

    manifest_module.main()

    manifest = json.loads((runtime / "resource-manifest.json").read_text())
    assert manifest["staging_filter"]["receipt"] == {
        "path": stage_module.RECEIPT_PATH.as_posix(),
        "sha256": manifest_module.sha256(runtime / stage_module.RECEIPT_PATH),
    }
    assert manifest["staging_filter"]["source_exclusions"] == [
        path.as_posix() for path in stage_module.SOURCE_SUBTREES
    ]
    paths = {entry["path"] for entry in manifest["files"]}
    assert stage_module.RECEIPT_PATH.as_posix() in paths
    assert not any("claude-agent-sdk" in path for path in paths)


def test_manifest_rejects_missing_receipt_and_any_forbidden_final_path(
    tmp_path, monkeypatch
):
    runtime, lock, receipt = _stage(tmp_path, monkeypatch)
    (runtime / stage_module.RECEIPT_PATH).unlink()
    files, discovered = manifest_module.resource_entries(runtime)
    with pytest.raises(SystemExit, match="missing Paperclip"):
        manifest_module._validate_paperclip_staging_filter(
            json.loads(lock.read_text())["components"][0],
            runtime,
            files,
            discovered,
        )

    (runtime / stage_module.RECEIPT_PATH).write_text(
        json.dumps(receipt, sort_keys=True)
    )
    forbidden = "paperclip/node_modules/@anthropic-ai/claude-agent-sdk/file.js"
    discovered.add(forbidden)
    files, _ = manifest_module.resource_entries(runtime)
    monkeypatch.setattr(
        manifest_module,
        "PAPERCLIP_ENTRYPOINT_SHA256",
        manifest_module.sha256(runtime / "paperclip/dist/index.js"),
    )
    monkeypatch.setattr(
        manifest_module,
        "PAPERCLIP_STAGING_TREES",
        {
            entry["path"]: entry["original_tree"]
            for entry in receipt["source_exclusions"]
        },
    )
    monkeypatch.setattr(
        manifest_module,
        "PAPERCLIP_STAGING_MARKERS",
        {
            entry["path"]: entry["original_markers"]
            for entry in receipt["source_exclusions"]
        },
    )
    with pytest.raises(SystemExit, match="payload remains"):
        manifest_module._validate_paperclip_staging_filter(
            json.loads(lock.read_text())["components"][0],
            runtime,
            files,
            discovered,
        )


def test_manifest_combines_aioncore_and_paperclip_receipts(monkeypatch):
    vendor = {
        "components": [
            {"id": "aioncore", "staging_filter": {}},
            {"id": "paperclip", "staging_filter": {}},
        ]
    }
    monkeypatch.setattr(
        manifest_module,
        "_validate_aioncore_staging_filter",
        lambda *args: {"receipt": {"path": "staging-exclusions.json"}},
    )
    monkeypatch.setattr(
        manifest_module,
        "_validate_paperclip_staging_filter",
        lambda *args: {"receipt": {"path": "paperclip-staging-exclusions.json"}},
    )

    result = manifest_module.validate_staging_filter(
        vendor, Path("/unused"), [], set()
    )

    assert result == {
        "profile": "codex-only",
        "components": {
            "aioncore": {"receipt": {"path": "staging-exclusions.json"}},
            "paperclip": {
                "receipt": {"path": "paperclip-staging-exclusions.json"}
            },
        },
        "upstream_proprietary_payloads_removed": True,
    }


def test_repository_lock_and_stage_order_are_fail_closed():
    lock = json.loads((ROOT / "desktop/vendor-lock.json").read_text())
    schema = json.loads((ROOT / "desktop/vendor-lock.schema.json").read_text())
    Draft202012Validator(schema).validate(lock)
    paperclip = next(
        component for component in lock["components"] if component["id"] == "paperclip"
    )
    assert paperclip["redistribution_review"] == "blocked"
    assert paperclip["staging_filter"] == {
        "profile": "codex-only",
        "applies_to_version": "2026.707.0",
        "source_exclusions": [
            path.as_posix() for path in stage_module.SOURCE_SUBTREES
        ],
        "receipt": stage_module.RECEIPT_PATH.as_posix(),
    }
    assert "Claude Agent SDK 0.3.191" in paperclip["notice"]
    assert manifest_module.PAPERCLIP_STAGING_EXCLUSIONS == [
        path.as_posix() for path in stage_module.SOURCE_SUBTREES
    ]
    assert (
        manifest_module.PAPERCLIP_ENTRYPOINT_SHA256
        == stage_module.PAPERCLIP_ENTRYPOINT_SHA256
    )
    assert manifest_module.PAPERCLIP_STAGING_TREES == {
        path.as_posix(): summary
        for path, summary in stage_module.EXPECTED_SOURCE_TREES.items()
    }
    assert manifest_module.PAPERCLIP_STAGING_MARKERS == {
        relative.as_posix(): [
            {
                "path": (relative / marker).as_posix(),
                "sha256": stage_module.EXPECTED_MARKERS[relative / marker][0],
                "size": stage_module.EXPECTED_MARKERS[relative / marker][1],
            }
            for marker in stage_module.SOURCE_MARKERS[relative]
        ]
        for relative in stage_module.SOURCE_SUBTREES
    }

    source = (ROOT / "desktop/scripts/stage_runtime.sh").read_text()
    assert source.index("stage_codex_only_aioncore.py") < source.index(
        "stage_codex_only_paperclip.py"
    )
    assert source.index("stage_codex_only_paperclip.py") < source.index(
        "normalize_macos_architecture.py"
    )
    supervisor = (ROOT / "desktop/src-tauri/src/supervisor.rs").read_text()
    assert '.env("HEARTBEAT_SCHEDULER_ENABLED", "false")' in supervisor
    assert '"adapterType": "process"' in supervisor
    assert "require_managed_paperclip_service_agent(&agent)?" in supervisor
