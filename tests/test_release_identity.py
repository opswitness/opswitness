import importlib.util
from pathlib import Path

from typer.testing import CliRunner

from opswitness.cli import app

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "opswitness_release_identity",
    ROOT / "scripts" / "check_release_identity.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_IDENTITY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_IDENTITY)
RELEASE_TAG = _IDENTITY.RELEASE_TAG
_editable_lock_package = _IDENTITY._editable_lock_package
identity_errors = _IDENTITY.identity_errors


def test_release_identity_is_consistent():
    assert identity_errors(ROOT, tag=RELEASE_TAG) == []


def test_release_identity_rejects_wrong_tag():
    errors = identity_errors(ROOT, tag="v0.1.0")
    assert any(error.startswith("tag:") for error in errors)


def test_release_identity_reads_exactly_one_editable_lock_package(tmp_path):
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\nrequires-python = "==3.12.*"\n\n'
        '[[package]]\nname = "opswitness"\nversion = "0.1.0a1"\n'
        'source = { editable = "." }\n'
    )

    assert _editable_lock_package(lock) == {
        "name": "opswitness",
        "version": "0.1.0a1",
        "source": {"editable": "."},
    }


def test_primary_cli_help_uses_opswitness_examples():
    result = CliRunner().invoke(app, ["wrap", "--help"])

    assert result.exit_code == 0
    assert "opswitness wrap --job NAME" in result.output
    assert "qd wrap --job NAME" not in result.output
