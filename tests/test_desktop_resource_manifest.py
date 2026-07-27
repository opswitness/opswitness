import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "desktop"
    / "scripts"
    / "make_resource_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("make_resource_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
manifest_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_module)


def _runtime_tree(tmp_path: Path) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    entrypoint = runtime / "paperclip" / "dist" / "index.js"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("export {};\n")
    target = runtime / "paperclip" / "node_modules" / "tool" / "bin" / "tool.js"
    target.parent.mkdir(parents=True)
    target.write_text("#!/usr/bin/env node\n")
    link = runtime / "paperclip" / "node_modules" / ".bin" / "tool"
    link.parent.mkdir(parents=True)
    link.symlink_to("../tool/bin/tool.js")
    (runtime / "architecture-provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_architecture": "arm64",
                "entries": [],
            }
        )
    )
    return runtime, link


def _vendor_lock(tmp_path: Path) -> Path:
    lock = tmp_path / "vendor-lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "aarch64-apple-darwin",
                "components": [
                    {
                        "id": "paperclip",
                        "entrypoints": ["paperclip/dist/index.js"],
                        "required_prefixes": ["paperclip/node_modules/"],
                    }
                ],
            }
        )
    )
    return lock


def test_manifest_records_safe_relative_symlink_target(tmp_path, monkeypatch):
    runtime, link = _runtime_tree(tmp_path)
    lock = _vendor_lock(tmp_path)
    monkeypatch.setattr(manifest_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(manifest_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
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
    assert payload["schema_version"] == 2
    assert payload["integrity_phase"] == "staged"
    assert payload["architecture_normalization"] == {
        "path": "architecture-provenance.json",
        "sha256": manifest_module.sha256(runtime / "architecture-provenance.json"),
    }
    by_path = {entry["path"]: entry for entry in payload["files"]}
    relative = link.relative_to(runtime).as_posix()
    assert by_path[relative] == {
        "path": relative,
        "kind": "symlink",
        "target": "../tool/bin/tool.js",
    }


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/tmp/opswitness-manifest-outside", "must be relative"),
        ("../../opswitness-manifest-outside", "escapes the runtime payload"),
        ("../missing/tool.js", "broken"),
    ],
)
def test_manifest_rejects_unsafe_symlink_target(tmp_path, target, expected):
    runtime = tmp_path / "runtime"
    link = runtime / "bin" / "tool"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)

    with pytest.raises(SystemExit, match=expected):
        manifest_module.resource_entries(runtime)


def test_manifest_rejects_an_architecture_provenance_exclusion_that_remains(tmp_path):
    runtime, _ = _runtime_tree(tmp_path)
    excluded = runtime / "paperclip" / "node_modules" / "tool" / "prebuilds" / "darwin-x64" / "tool.node"
    excluded.parent.mkdir(parents=True)
    excluded.write_text("not actually excluded")
    provenance = {
        "schema_version": 1,
        "target_architecture": "arm64",
        "entries": [
            {
                "path": excluded.relative_to(runtime).as_posix(),
                "before_archs": ["x86_64"],
                "after_archs": [],
                "before_sha256": "a" * 64,
                "after_sha256": None,
                "action": "excluded_non_arm_vendor_prebuild",
            }
        ],
    }
    files, discovered = manifest_module.resource_entries(runtime)

    with pytest.raises(SystemExit, match="normalization exclusion"):
        manifest_module.validate_architecture_provenance(provenance, discovered)


def test_manifest_verifies_the_staged_inventory_before_signing(
    tmp_path, monkeypatch
):
    runtime, _ = _runtime_tree(tmp_path)
    lock = _vendor_lock(tmp_path)
    monkeypatch.setattr(manifest_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(manifest_module.platform, "machine", lambda: "arm64")
    base_argv = [
        str(SCRIPT),
        "--runtime",
        str(runtime),
        "--vendor-lock",
        str(lock),
        "--mode",
        "adhoc",
    ]
    monkeypatch.setattr(sys, "argv", base_argv)
    manifest_module.main()

    monkeypatch.setattr(sys, "argv", [*base_argv, "--verify-existing"])
    manifest_module.main()

    (runtime / "paperclip" / "dist" / "index.js").write_text("tampered\n")
    with pytest.raises(SystemExit, match="does not match current payload"):
        manifest_module.main()


def test_post_sign_manifest_binds_staged_manifest_and_refreshes_hashes(
    tmp_path, monkeypatch
):
    runtime, _ = _runtime_tree(tmp_path)
    lock = _vendor_lock(tmp_path)
    monkeypatch.setattr(manifest_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(manifest_module.platform, "machine", lambda: "arm64")
    base_argv = [
        str(SCRIPT),
        "--runtime",
        str(runtime),
        "--vendor-lock",
        str(lock),
        "--mode",
        "adhoc",
    ]
    monkeypatch.setattr(sys, "argv", base_argv)
    manifest_module.main()
    manifest_path = runtime / "resource-manifest.json"
    staged_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    entrypoint = runtime / "paperclip" / "dist" / "index.js"
    entrypoint.write_text("signed bytes\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            *base_argv,
            "--post-sign",
            "--pre-sign-manifest-sha256",
            staged_sha256,
        ],
    )
    manifest_module.main()

    payload = json.loads(manifest_path.read_text())
    by_path = {entry["path"]: entry for entry in payload["files"]}
    assert payload["integrity_phase"] == "post-sign"
    assert payload["pre_sign_manifest_sha256"] == staged_sha256
    assert by_path["paperclip/dist/index.js"]["sha256"] == manifest_module.sha256(
        entrypoint
    )


def test_post_sign_manifest_requires_a_valid_staged_digest(tmp_path, monkeypatch):
    runtime, _ = _runtime_tree(tmp_path)
    lock = _vendor_lock(tmp_path)
    monkeypatch.setattr(manifest_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(manifest_module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--runtime",
            str(runtime),
            "--vendor-lock",
            str(lock),
            "--post-sign",
            "--pre-sign-manifest-sha256",
            "not-a-digest",
        ],
    )

    with pytest.raises(SystemExit, match="requires a lowercase staged-manifest"):
        manifest_module.main()
