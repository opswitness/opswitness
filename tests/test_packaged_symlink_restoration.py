import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "desktop"
    / "scripts"
    / "restore_packaged_symlinks.py"
)
SPEC = importlib.util.spec_from_file_location("restore_packaged_symlinks", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
restorer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = restorer
SPEC.loader.exec_module(restorer)


def _manifest(runtime: Path, entries: list[dict]) -> Path:
    path = runtime / "resource-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "target": "aarch64-apple-darwin",
                "distribution_mode": "adhoc",
                "integrity_phase": "staged",
                "files": entries,
            }
        )
    )
    return path


def test_restore_replaces_only_an_identical_flattened_symlink(tmp_path):
    runtime = tmp_path / "runtime"
    target = runtime / "package" / "bin" / "tool.js"
    target.parent.mkdir(parents=True)
    target.write_text("tool\n")
    flattened = runtime / "package" / "node_modules" / ".bin" / "tool"
    flattened.parent.mkdir(parents=True)
    flattened.write_text("tool\n")
    manifest = _manifest(
        runtime,
        [
            {
                "path": "package/node_modules/.bin/tool",
                "kind": "symlink",
                "target": "../../bin/tool.js",
            }
        ],
    )

    assert restorer.restore(runtime, manifest) == 1

    assert flattened.is_symlink()
    assert flattened.readlink() == Path("../../bin/tool.js")
    assert flattened.read_text() == "tool\n"


def test_restore_is_idempotent_for_an_existing_matching_symlink(tmp_path):
    runtime = tmp_path / "runtime"
    target = runtime / "package" / "tool.js"
    target.parent.mkdir(parents=True)
    target.write_text("tool\n")
    link = runtime / "package" / "tool"
    link.symlink_to("tool.js")
    manifest = _manifest(
        runtime,
        [{"path": "package/tool", "kind": "symlink", "target": "tool.js"}],
    )

    assert restorer.restore(runtime, manifest) == 0
    assert link.is_symlink()


def test_restore_rejects_changed_flattened_content_before_any_replacement(tmp_path):
    runtime = tmp_path / "runtime"
    first_target = runtime / "first" / "target"
    first_target.parent.mkdir(parents=True)
    first_target.write_text("same\n")
    first_flattened = runtime / "first" / "link"
    first_flattened.write_text("same\n")
    second_target = runtime / "second" / "target"
    second_target.parent.mkdir(parents=True)
    second_target.write_text("expected\n")
    second_flattened = runtime / "second" / "link"
    second_flattened.write_text("changed\n")
    manifest = _manifest(
        runtime,
        [
            {"path": "first/link", "kind": "symlink", "target": "target"},
            {"path": "second/link", "kind": "symlink", "target": "target"},
        ],
    )

    with pytest.raises(ValueError, match="differs from its target"):
        restorer.restore(runtime, manifest)

    assert first_flattened.is_file()
    assert not first_flattened.is_symlink()
    assert second_flattened.is_file()


def test_restore_rejects_escaping_or_non_staged_manifest(tmp_path):
    runtime = tmp_path / "runtime"
    flattened = runtime / "package" / "link"
    flattened.parent.mkdir(parents=True)
    flattened.write_text("data\n")
    manifest = _manifest(
        runtime,
        [{"path": "package/link", "kind": "symlink", "target": "../../outside"}],
    )

    with pytest.raises(ValueError, match="escapes"):
        restorer.restore(runtime, manifest)

    payload = json.loads(manifest.read_text())
    payload["integrity_phase"] = "post-sign"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="requires a staged"):
        restorer.restore(runtime, manifest)
