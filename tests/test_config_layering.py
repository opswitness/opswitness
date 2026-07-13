from quarterdeck.config import Settings, config_dir, resolve_api_key


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
    monkeypatch.setenv("QD_CONFIG_DIR", str(cfg))
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
    monkeypatch.setenv("QD_LOG_TAIL_BYTES", "2222")
    assert Settings().log_tail_bytes == 2222


def test_missing_yaml_files_fall_back_to_defaults(tmp_path, monkeypatch):
    _write_config_dir(tmp_path, monkeypatch)
    s = Settings()
    assert s.log_tail_bytes == 8192 and s.redact is True


def test_mail_settings_are_non_secret_config_and_strict(tmp_path, monkeypatch):
    import pytest

    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml=("mail:\n  enabled: true\n  gws_bin: /opt/tools/gws\n  max_messages: 7\n"),
    )
    settings = Settings()
    assert settings.mail.enabled is True
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
    monkeypatch.setenv("QD_CONFIG_DIR", str(tmp_path / "custom"))
    assert config_dir() == tmp_path / "custom"


def test_secret_in_config_is_rejected_even_if_secrets_would_override(tmp_path, monkeypatch):
    import pytest

    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml="paperclip:\n  api_key: leaked\n",
        secrets_yaml="paperclip:\n  api_key: safe-location\n",
    )
    with pytest.raises(ValueError, match="must move to secrets.yaml"):
        Settings()


def test_config_permissions_and_secrets_schema_are_enforced(tmp_path, monkeypatch):
    import pytest

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
