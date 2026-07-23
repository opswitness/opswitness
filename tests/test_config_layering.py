import stat

import pytest

from opswitness.config import (
    MAIL_ACTIVATION_FILE,
    Settings,
    cli_path,
    config_dir,
    resolve_api_key,
    state_root,
    save_mail_activation,
)


def _write_config_dir(tmp_path, monkeypatch, config_yaml: str = "", secrets_yaml: str = ""):
    cfg = tmp_path / "qdconf"
    cfg.mkdir(parents=True)
    cfg.chmod(0o700)
    if config_yaml:
        (cfg / "config.yaml").write_text(config_yaml)
    if secrets_yaml:
        secrets = cfg / "secrets.yaml"
        secrets.write_text(secrets_yaml)
        secrets.chmod(0o600)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(cfg))
    return cfg


def test_config_yaml_is_loaded(tmp_path, monkeypatch):
    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml="log_tail_bytes: 1111\npaperclip:\n  company_id: from-config\n",
    )
    s = Settings()
    assert s.log_tail_bytes == 1111
    assert s.paperclip.company_id == "from-config"


def test_secrets_yaml_is_loaded(tmp_path, monkeypatch):
    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml="paperclip:\n  api_base: http://127.0.0.1:3100\n",
        secrets_yaml="paperclip:\n  api_key: from-secrets\n",
    )
    assert Settings().paperclip.api_key == "from-secrets"


def test_env_beats_yaml(tmp_path, monkeypatch):
    _write_config_dir(tmp_path, monkeypatch, config_yaml="log_tail_bytes: 1111\n")
    monkeypatch.setenv("OPSWITNESS_LOG_TAIL_BYTES", "2222")
    assert Settings().log_tail_bytes == 2222


def test_legacy_env_alias_is_supported_and_canonical_conflicts_fail_closed(
    tmp_path, monkeypatch
):
    _write_config_dir(tmp_path, monkeypatch)
    monkeypatch.setenv("QD_LOG_TAIL_BYTES", "2222")
    assert Settings().log_tail_bytes == 2222

    monkeypatch.setenv("OPSWITNESS_LOG_TAIL_BYTES", "2222")
    assert Settings().log_tail_bytes == 2222

    monkeypatch.setenv("OPSWITNESS_LOG_TAIL_BYTES", "3333")
    with pytest.raises(ValueError, match="conflicting environment variables"):
        Settings()


def test_missing_yaml_files_fall_back_to_defaults(tmp_path, monkeypatch):
    _write_config_dir(tmp_path, monkeypatch)
    s = Settings()
    assert s.log_tail_bytes == 8192 and s.redact is True


def test_mail_settings_are_non_secret_config_and_strict(tmp_path, monkeypatch):
    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml=(
            "mail:\n"
            "  enabled: true\n"
            "  model_metadata_consent: true\n"
            "  gws_bin: /opt/tools/gws\n"
            "  max_messages: 7\n"
        ),
    )
    settings = Settings()
    assert settings.mail.enabled is True
    assert settings.mail.model_metadata_consent is True
    assert str(settings.mail.gws_bin) == "/opt/tools/gws"
    assert settings.mail.max_messages == 7

    _write_config_dir(
        tmp_path / "bad",
        monkeypatch,
        config_yaml="mail:\n  runtime_query: from:anyone\n",
    )
    with pytest.raises(ValueError, match="runtime_query"):
        Settings()


def test_resolve_api_key_prefers_secrets_then_env(tmp_path, monkeypatch):
    _write_config_dir(tmp_path, monkeypatch, secrets_yaml="paperclip:\n  api_key: sec-key\n")
    monkeypatch.setenv("PAPERCLIP_API_KEY", "env-key")
    assert resolve_api_key(Settings()) == "sec-key"

    _write_config_dir(tmp_path / "b", monkeypatch)  # no secrets file
    assert resolve_api_key(Settings()) == "env-key"

    monkeypatch.delenv("PAPERCLIP_API_KEY")
    assert resolve_api_key(Settings()) == ""


def test_config_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "custom"))
    assert config_dir() == tmp_path / "custom"


def test_config_dir_reuses_one_legacy_install_and_refuses_two_trees(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPSWITNESS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("QD_CONFIG_DIR", raising=False)
    legacy = tmp_path / ".config" / "quarterdeck"
    canonical = tmp_path / ".config" / "opswitness"
    legacy.mkdir(parents=True)
    assert config_dir() == legacy

    canonical.mkdir()
    with pytest.raises(ValueError, match="both OpsWitness and Quarterdeck configuration"):
        config_dir()


def test_legacy_config_dir_env_alias_and_conflict(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy-config"
    monkeypatch.setenv("QD_CONFIG_DIR", str(legacy))
    assert config_dir() == legacy

    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(legacy))
    assert config_dir() == legacy

    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(tmp_path / "canonical-config"))
    with pytest.raises(ValueError, match="conflicting environment variables"):
        config_dir()


def test_state_and_cli_defaults_reuse_legacy_install_without_copying(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy_state = tmp_path / ".local" / "state" / "quarterdeck"
    legacy_state.mkdir(parents=True)
    legacy_cli = tmp_path / ".local" / "bin" / "qd"
    legacy_cli.parent.mkdir(parents=True)
    legacy_cli.write_text("#!/bin/sh\n")

    assert state_root() == legacy_state
    assert cli_path() == legacy_cli
    settings = Settings()
    assert settings.ledger_dir == legacy_state / "ledger"
    assert settings.console.state_dir == legacy_state / "console"


def test_state_root_refuses_implicit_new_and_legacy_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".local" / "state" / "quarterdeck").mkdir(parents=True)
    (tmp_path / ".local" / "state" / "opswitness").mkdir()
    with pytest.raises(ValueError, match="both OpsWitness and Quarterdeck state"):
        state_root()


def test_secret_in_config_is_rejected_even_if_secrets_would_override(tmp_path, monkeypatch):
    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml="paperclip:\n  api_key: leaked\n",
        secrets_yaml="paperclip:\n  api_key: safe-location\n",
    )
    with pytest.raises(ValueError, match="must move to secrets.yaml"):
        Settings()


def test_config_permissions_and_secrets_schema_are_enforced(tmp_path, monkeypatch):
    cfg = _write_config_dir(tmp_path, monkeypatch, secrets_yaml="paperclip:\n  api_key: key\n")
    cfg.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        Settings()
    cfg.chmod(0o700)
    (cfg / "secrets.yaml").chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        Settings()
    (cfg / "secrets.yaml").chmod(0o600)
    (cfg / "secrets.yaml").write_text("ledger_dir: /tmp/not-a-secret\n")
    with pytest.raises(ValueError, match="non-secret fields"):
        Settings()


def test_managed_mail_activation_is_atomic_scoped_and_does_not_rewrite_config(
    tmp_path, monkeypatch
):
    cfg = _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml=(
            "# user-owned comment\n"
            "mail:\n"
            "  enabled: false\n"
            "  model_metadata_consent: false\n"
            "  max_messages: 7\n"
        ),
    )
    original = (cfg / "config.yaml").read_bytes()

    path = save_mail_activation(enabled=True, model_metadata_consent=True)

    assert path == cfg / MAIL_ACTIVATION_FILE
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert (cfg / "config.yaml").read_bytes() == original
    settings = Settings()
    assert settings.mail.enabled is True
    assert settings.mail.model_metadata_consent is True
    assert settings.mail.max_messages == 7

    save_mail_activation(enabled=False, model_metadata_consent=False)
    revoked = Settings()
    assert revoked.mail.enabled is False
    assert revoked.mail.model_metadata_consent is False


def test_managed_mail_activation_rejects_bad_state_and_env_still_wins(
    tmp_path, monkeypatch
):
    cfg = _write_config_dir(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="requires the mail adapter"):
        save_mail_activation(enabled=False, model_metadata_consent=True)

    activation = cfg / MAIL_ACTIVATION_FILE
    activation.write_text("mail:\n  enabled: true\n  query: from:anyone\n")
    activation.chmod(0o600)
    with pytest.raises(ValueError, match="unsupported managed mail fields"):
        Settings()

    activation.write_text(
        "mail:\n  enabled: true\n  model_metadata_consent: true\n"
    )
    activation.chmod(0o600)
    monkeypatch.setenv("OPSWITNESS_MAIL__ENABLED", "false")
    assert Settings().mail.enabled is False

    activation.chmod(0o644)
    with pytest.raises(ValueError, match="managed mail state mode must be 0600"):
        Settings()
