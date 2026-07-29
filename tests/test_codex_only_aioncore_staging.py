import importlib.util
import json
import stat
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
STAGE_SCRIPT = ROOT / "desktop" / "scripts" / "stage_codex_only_aioncore.py"
MANIFEST_SCRIPT = ROOT / "desktop" / "scripts" / "make_resource_manifest.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_module = _load("stage_codex_only_aioncore", STAGE_SCRIPT)
manifest_module = _load("codex_only_resource_manifest", MANIFEST_SCRIPT)


def _vendor_lock(tmp_path: Path) -> Path:
    path = tmp_path / "vendor-lock.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": [
                    {
                        "id": "aioncore",
                        "version": "0.1.45",
                        "entrypoints": ["aioncore/aioncore"],
                        "required_prefixes": ["aioncore/managed-resources/"],
                        "staging_filter": {
                            "profile": "codex-only",
                            "applies_to_version": "0.1.45",
                            "source_exclusions": [
                                stage_module.SOURCE_SUBTREE.as_posix()
                            ],
                            "compatibility_shim_root": (
                                stage_module.SOURCE_SUBTREE.as_posix()
                            ),
                            "receipt": stage_module.RECEIPT_PATH.as_posix(),
                        },
                    }
                ],
            }
        )
    )
    return path


def _upstream_runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    (runtime / "aioncore").mkdir(parents=True)
    executable = runtime / "aioncore" / "aioncore"
    executable.write_bytes(b"fixture-aioncore")
    executable.chmod(0o755)
    (runtime / "aioncore" / "manifest.json").write_text(
        json.dumps(
            {
                "platform": "darwin",
                "arch": "arm64",
                "version": "v0.1.45",
                "files": ["aioncore", "managed-resources/"],
            }
        )
    )
    source = runtime / stage_module.SOURCE_SUBTREE
    for marker in stage_module.UPSTREAM_MARKERS:
        path = source / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"upstream-proprietary::{marker.as_posix()}".encode())
        if marker.name == "claude":
            path.chmod(0o755)
    shared = runtime / "aioncore/managed-resources/acp/codex-acp/1.1.2/darwin-arm64"
    shared.mkdir(parents=True)
    (shared / "manifest.json").write_text('{"entrypoint":"codex.js"}\n')
    (shared / "codex.js").write_text("process.exit(0);\n")
    return runtime


def _stage(tmp_path: Path) -> tuple[Path, Path, dict]:
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    receipt = runtime / stage_module.RECEIPT_PATH
    payload = stage_module.stage(runtime, lock, receipt)
    return runtime, lock, payload


def test_codex_only_filter_replaces_every_upstream_file_with_exact_first_party_shim(
    tmp_path,
):
    runtime, _, payload = _stage(tmp_path)
    shim = runtime / stage_module.SOURCE_SUBTREE
    observed = {
        path.relative_to(shim).as_posix()
        for path in shim.rglob("*")
        if path.is_file() or path.is_symlink()
    }

    assert observed == {path.as_posix() for path in stage_module.SHIM_FILES}
    assert payload["source_exclusions"][0]["original_source_tree_removed"] is True
    assert payload["source_exclusions"][0]["original_tree"]["file_count"] >= 3
    assert len(payload["source_exclusions"][0]["original_markers"]) == 3
    assert payload["proprietary_path_scan"]["forbidden_matches"] == []
    assert payload["aioncore_manifest_audit"]["rewrite_required"] is False
    assert payload["generated_compatibility_shim"]["files"]

    native = runtime / stage_module.SHIM_NATIVE_PATH
    assert native.read_bytes() == stage_module.SHIM_FILES[
        stage_module.SHIM_NATIVE_PATH.relative_to(stage_module.SOURCE_SUBTREE)
    ][0]
    assert stat.S_IMODE(native.stat().st_mode) == 0o755
    assert b"upstream-proprietary" not in b"".join(
        path.read_bytes()
        for path in shim.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    assert str(tmp_path) not in json.dumps(payload)


def test_codex_only_filter_fails_closed_if_aioncore_manifest_names_claude(tmp_path):
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    manifest = runtime / "aioncore/manifest.json"
    payload = json.loads(manifest.read_text())
    payload["files"].append("managed-resources/acp/claude-agent-acp/")
    manifest.write_text(json.dumps(payload))

    with pytest.raises(SystemExit, match="requires an explicit rewrite"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )

    assert (runtime / stage_module.SOURCE_SUBTREE / stage_module.UPSTREAM_MARKERS[-1]).exists()


def test_codex_only_filter_rejects_a_symlinked_source_parent(tmp_path):
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    acp = runtime / "aioncore/managed-resources/acp"
    actual_acp = acp.with_name("acp-real")
    acp.rename(actual_acp)
    acp.symlink_to(actual_acp.name, target_is_directory=True)

    with pytest.raises(SystemExit, match="parents must be real directories"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )

    assert (
        actual_acp
        / stage_module.SOURCE_SUBTREE.relative_to(
            "aioncore/managed-resources/acp"
        )
        / stage_module.UPSTREAM_MARKERS[-1]
    ).exists()


def test_codex_only_filter_rejects_an_unreviewed_aioncore_version(tmp_path):
    runtime = _upstream_runtime(tmp_path)
    lock = _vendor_lock(tmp_path)
    manifest = runtime / "aioncore/manifest.json"
    payload = json.loads(manifest.read_text())
    payload["version"] = "v0.1.46"
    manifest.write_text(json.dumps(payload))

    with pytest.raises(SystemExit, match="manifest version changed"):
        stage_module.stage(
            runtime,
            lock,
            runtime / stage_module.RECEIPT_PATH,
        )

    assert (runtime / stage_module.SOURCE_SUBTREE / stage_module.UPSTREAM_MARKERS[-1]).exists()


def test_resource_manifest_explicitly_binds_codex_only_removal_receipt(
    tmp_path, monkeypatch
):
    runtime, lock, receipt = _stage(tmp_path)
    (runtime / "architecture-provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_architecture": "arm64",
                "entries": [],
            }
        )
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

    payload = json.loads((runtime / "resource-manifest.json").read_text())
    assert payload["staging_filter"] == {
        "profile": "codex-only",
        "receipt": {
            "path": "staging-exclusions.json",
            "sha256": manifest_module.sha256(runtime / "staging-exclusions.json"),
        },
        "source_exclusions": [stage_module.SOURCE_SUBTREE.as_posix()],
        "compatibility_shim_root": stage_module.SOURCE_SUBTREE.as_posix(),
        "upstream_source_tree_removed": True,
    }
    paths = {entry["path"] for entry in payload["files"]}
    assert "staging-exclusions.json" in paths
    assert stage_module.SHIM_NATIVE_PATH.as_posix() in paths
    assert (
        stage_module.SOURCE_SUBTREE
        / "node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js"
    ).as_posix() not in paths
    assert receipt["proprietary_path_scan"]["forbidden_matches"] == []


def test_resource_manifest_rejects_an_unrecorded_file_in_the_shim(
    tmp_path, monkeypatch
):
    runtime, lock, _ = _stage(tmp_path)
    (runtime / stage_module.SOURCE_SUBTREE / "unrecorded.js").write_text("bad\n")
    (runtime / "architecture-provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_architecture": "arm64",
                "entries": [],
            }
        )
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

    with pytest.raises(SystemExit, match="unrecorded files"):
        manifest_module.main()


def test_runtime_stage_orders_codex_only_filter_before_architecture_inventory():
    source = (ROOT / "desktop/scripts/stage_runtime.sh").read_text()

    assert "stage_codex_only_aioncore.py" in source
    assert source.index("stage_codex_only_aioncore.py") < source.index(
        "normalize_macos_architecture.py"
    )


def test_repository_vendor_lock_declares_filtered_upstream_and_validates():
    lock = json.loads((ROOT / "desktop/vendor-lock.json").read_text())
    schema = json.loads((ROOT / "desktop/vendor-lock.schema.json").read_text())
    Draft202012Validator(schema).validate(lock)
    aioncore = next(
        component for component in lock["components"] if component["id"] == "aioncore"
    )

    assert aioncore["redistribution_review"] == "blocked"
    assert aioncore["staging_filter"] == {
        "profile": "codex-only",
        "applies_to_version": "0.1.45",
        "source_exclusions": [stage_module.SOURCE_SUBTREE.as_posix()],
        "compatibility_shim_root": stage_module.SOURCE_SUBTREE.as_posix(),
        "receipt": stage_module.RECEIPT_PATH.as_posix(),
    }
    assert "upstream archive subtree excluded" in aioncore["license"]
    assert "No upstream Anthropic package or native binary may remain" in aioncore[
        "notice"
    ]


def test_desktop_supervisor_has_no_claude_executable_or_credential_injection():
    source = (ROOT / "desktop/src-tauri/src/supervisor.rs").read_text()

    assert "OPSWITNESS_GATE__CLAUDE_BIN" not in source
    assert "CLAUDE_CONFIG_DIR" not in source
    assert "resolve_bundled_claude_executable" not in source
    assert "reqwest::Method::PATCH" in source
    assert 'const CLAUDE_AGENT_ID: &str = "2d23ff1c";' in source
