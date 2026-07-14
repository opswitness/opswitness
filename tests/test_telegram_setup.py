import stat

import pytest
import yaml
from typer.testing import CliRunner

from quarterdeck.cli import app
from quarterdeck.config import clear_telegram_credentials, save_telegram_credentials


def test_save_telegram_credentials_merges_atomically_with_private_modes(tmp_path):
    root = tmp_path / "config"
    root.mkdir(mode=0o700)
    secrets = root / "secrets.yaml"
    secrets.write_text("paperclip:\n  api_key: fixture-key\n")
    secrets.chmod(0o600)

    result = save_telegram_credentials("1:fixture", "12345", root=root)
    loaded = yaml.safe_load(result.read_text())

    assert loaded == {
        "paperclip": {"api_key": "fixture-key"},
        "telegram": {"bot_token": "1:fixture", "chat_id": "12345"},
    }
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(result.stat().st_mode) == 0o600
    assert not list(root.glob("*.qd-tmp"))


def test_save_telegram_credentials_refuses_overwrite_without_replace(tmp_path):
    root = tmp_path / "config"
    save_telegram_credentials("1:first", "12345", root=root)

    with pytest.raises(ValueError, match="already exist"):
        save_telegram_credentials("2:second", "67890", root=root)

    save_telegram_credentials("2:second", "67890", root=root, replace=True)
    loaded = yaml.safe_load((root / "secrets.yaml").read_text())
    assert loaded["telegram"] == {"bot_token": "2:second", "chat_id": "67890"}


def test_clear_telegram_credentials_preserves_other_secrets(tmp_path):
    root = tmp_path / "config"
    root.mkdir(mode=0o700)
    secrets = root / "secrets.yaml"
    secrets.write_text("paperclip:\n  api_key: fixture-key\n")
    secrets.chmod(0o600)
    save_telegram_credentials("1:fixture", "12345", root=root)

    assert clear_telegram_credentials(root=root) is True
    assert yaml.safe_load(secrets.read_text()) == {
        "paperclip": {"api_key": "fixture-key"}
    }
    assert stat.S_IMODE(secrets.stat().st_mode) == 0o600
    assert clear_telegram_credentials(root=root) is False


def test_save_telegram_credentials_rejects_symlinks_and_invalid_values(tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="must not be a symlink"):
        save_telegram_credentials("1:fixture", "12345", root=linked_root)

    root = tmp_path / "config"
    root.mkdir(mode=0o700)
    real_secret = tmp_path / "real-secret"
    real_secret.write_text("{}\n")
    real_secret.chmod(0o600)
    (root / "secrets.yaml").symlink_to(real_secret)
    with pytest.raises(ValueError, match="must not be a symlink"):
        save_telegram_credentials("1:fixture", "12345", root=root)

    with pytest.raises(ValueError, match="token has an invalid format"):
        save_telegram_credentials("not-a-token", "12345", root=tmp_path / "a")
    with pytest.raises(ValueError, match="chat ID has an invalid format"):
        save_telegram_credentials("1:fixture", "not a chat", root=tmp_path / "b")


def test_telegram_configure_hides_values_and_does_not_use_argv(tmp_path, monkeypatch):
    root = tmp_path / "config"
    monkeypatch.setenv("QD_CONFIG_DIR", str(root))

    result = CliRunner().invoke(
        app,
        ["telegram", "configure"],
        input="1:local-fixture\n12345\n",
    )

    assert result.exit_code == 0
    assert "1:local-fixture" not in result.output
    assert "12345" not in result.output
    assert (root / "secrets.yaml").exists()


def test_telegram_test_reports_send_result(tmp_path, monkeypatch):
    root = tmp_path / "config"
    monkeypatch.setenv("QD_CONFIG_DIR", str(root))
    save_telegram_credentials("1:fixture", "12345", root=root)
    calls = []

    monkeypatch.setattr(
        "quarterdeck.notify.telegram.send_telegram",
        lambda text, settings: calls.append((text, settings.telegram.chat_id)) or True,
    )
    sent = CliRunner().invoke(app, ["telegram", "test"])
    assert sent.exit_code == 0
    assert calls == [("Quarterdeck Telegram delivery test", "12345")]

    monkeypatch.setattr("quarterdeck.notify.telegram.send_telegram", lambda *args: False)
    failed = CliRunner().invoke(app, ["telegram", "test"])
    assert failed.exit_code == 1
    assert "failed" in failed.output
