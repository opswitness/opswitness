from quarterdeck.config import Settings, config_dir, resolve_api_key


def _write_config_dir(tmp_path, monkeypatch, config_yaml: str = "", secrets_yaml: str = ""):
    cfg = tmp_path / "qdconf"
    cfg.mkdir(parents=True)
    if config_yaml:
        (cfg / "config.yaml").write_text(config_yaml)
    if secrets_yaml:
        (cfg / "secrets.yaml").write_text(secrets_yaml)
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


def test_secrets_yaml_beats_config_yaml(tmp_path, monkeypatch):
    _write_config_dir(
        tmp_path,
        monkeypatch,
        config_yaml="paperclip:\n  api_key: from-config\n",
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
