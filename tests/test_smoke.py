from typer.testing import CliRunner

from opswitness import __version__
from opswitness.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_settings_defaults() -> None:
    from opswitness.config import load_settings

    s = load_settings()
    assert s.paperclip.api_base.startswith("http://127.0.0.1")
    assert s.log_tail_bytes == 8192
