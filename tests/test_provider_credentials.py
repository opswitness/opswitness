import json
import stat
from pathlib import Path

import pytest

from quarterdeck.config import Settings
from quarterdeck.console import provider_credentials
from quarterdeck.console.provider_credentials import (
    ProviderCredentialError,
    configure_anthropic_api_key,
    configure_provider_api_key,
    managed_anthropic_api_key_helper,
    managed_provider_api_key_helper,
    provider_api_key_available,
)


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def test_anthropic_key_is_validated_then_keychained_without_argv_or_disk_exposure(
    tmp_path,
    monkeypatch,
):
    claude_root = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_root))
    security = _executable(tmp_path / "security")
    monkeypatch.setattr(provider_credentials, "_SECURITY_BIN", security)
    settings = Settings(console={"state_dir": tmp_path / "console"})
    secret = "sk-ant-local-sentinel-value"
    validation_calls = []
    keychain_calls = []

    assert configure_anthropic_api_key(
        settings,
        secret,
        validator=lambda value, timeout: validation_calls.append((value, timeout)) or True,
        secret_runner=lambda argv, stdin, timeout: keychain_calls.append(
            (argv, stdin, timeout)
        )
        or 0,
    )

    assert validation_calls == [(secret, 12.0)]
    assert keychain_calls[0][1:] == (secret, 20.0)
    assert secret not in " ".join(keychain_calls[0][0])
    assert keychain_calls[0][0][-1] == "-w"

    helper = managed_anthropic_api_key_helper(settings)
    assert helper is not None
    assert stat.S_IMODE(helper.stat().st_mode) == 0o700
    rendered_helper = helper.read_text(encoding="utf-8")
    settings_payload = json.loads((claude_root / "settings.json").read_text())
    assert settings_payload["apiKeyHelper"] == str(helper)
    assert stat.S_IMODE((claude_root / "settings.json").stat().st_mode) == 0o600
    assert secret not in rendered_helper
    assert secret not in json.dumps(settings_payload)


def test_anthropic_key_rejects_invalid_key_before_any_local_write(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    security = _executable(tmp_path / "security")
    monkeypatch.setattr(provider_credentials, "_SECURITY_BIN", security)
    settings = Settings(console={"state_dir": tmp_path / "console"})
    calls = []

    assert not configure_anthropic_api_key(
        settings,
        "sk-ant-invalid",
        validator=lambda value, timeout: False,
        secret_runner=lambda argv, stdin, timeout: calls.append((argv, stdin)) or 0,
    )
    assert calls == []
    assert not settings.console.state_dir.exists()
    assert not (tmp_path / "claude").exists()


def test_anthropic_key_never_overwrites_an_unmanaged_claude_helper(tmp_path, monkeypatch):
    claude_root = tmp_path / "claude"
    claude_root.mkdir(mode=0o700)
    (claude_root / "settings.json").write_text(
        json.dumps({"apiKeyHelper": "/opt/company/key-helper"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_root))
    security = _executable(tmp_path / "security")
    monkeypatch.setattr(provider_credentials, "_SECURITY_BIN", security)
    settings = Settings(console={"state_dir": tmp_path / "console"})
    calls = []

    with pytest.raises(ProviderCredentialError, match="unmanaged"):
        configure_anthropic_api_key(
            settings,
            "sk-ant-valid-sentinel",
            validator=lambda value, timeout: True,
            secret_runner=lambda argv, stdin, timeout: calls.append((argv, stdin)) or 0,
        )
    assert calls == []
    assert json.loads((claude_root / "settings.json").read_text()) == {
        "apiKeyHelper": "/opt/company/key-helper"
    }


@pytest.mark.parametrize(
    ("provider", "service"),
    [
        ("deepseek", "com.quarterdeck.deepseek-api-key"),
        ("xai", "com.quarterdeck.xai-api-key"),
    ],
)
def test_provider_key_is_validated_and_keychained_without_aionui_or_disk_secret(
    tmp_path,
    monkeypatch,
    provider,
    service,
):
    security = _executable(tmp_path / "security")
    monkeypatch.setattr(provider_credentials, "_SECURITY_BIN", security)
    settings = Settings(console={"state_dir": tmp_path / "console"})
    secret = f"{provider}-local-sentinel-value"
    validation_calls = []
    keychain_calls = []

    assert configure_provider_api_key(
        settings,
        provider,
        secret,
        validator=lambda value, timeout: validation_calls.append((value, timeout)) or True,
        secret_runner=lambda argv, stdin, timeout: keychain_calls.append(
            (argv, stdin, timeout)
        )
        or 0,
    )

    assert validation_calls == [(secret, 12.0)]
    assert keychain_calls[0][1:] == (secret, 20.0)
    assert keychain_calls[0][0][-1] == "-w"
    assert service in keychain_calls[0][0]
    assert secret not in " ".join(keychain_calls[0][0])
    helper = managed_provider_api_key_helper(settings, provider)
    assert helper is not None
    assert stat.S_IMODE(helper.stat().st_mode) == 0o700
    assert secret not in helper.read_text(encoding="utf-8")
    assert "AionUi" not in helper.read_text(encoding="utf-8")

    status_calls = []
    assert provider_api_key_available(
        settings,
        provider,
        runner=lambda argv, timeout: status_calls.append((argv, timeout)) or 0,
    )
    assert status_calls == [
        (
            [
                str(security),
                "find-generic-password",
                "-a",
                "api-key",
                "-s",
                service,
            ],
            5.0,
        )
    ]
    assert "-w" not in status_calls[0][0]


@pytest.mark.parametrize("provider", ["deepseek", "xai"])
def test_provider_key_rejects_invalid_key_before_local_write(tmp_path, monkeypatch, provider):
    security = _executable(tmp_path / "security")
    monkeypatch.setattr(provider_credentials, "_SECURITY_BIN", security)
    settings = Settings(console={"state_dir": tmp_path / "console"})
    calls = []

    assert not configure_provider_api_key(
        settings,
        provider,
        "invalid-sentinel",
        validator=lambda value, timeout: False,
        secret_runner=lambda argv, stdin, timeout: calls.append((argv, stdin)) or 0,
    )
    assert calls == []
    assert not settings.console.state_dir.exists()


@pytest.mark.parametrize(
    ("validator", "url"),
    [
        (provider_credentials._validate_deepseek_api_key, "https://api.deepseek.com/models"),
        (provider_credentials._validate_xai_api_key, "https://api.x.ai/v1/models"),
    ],
)
def test_provider_validation_uses_only_fixed_models_endpoint(monkeypatch, validator, url):
    calls = []

    class Response:
        status_code = 200

    monkeypatch.setattr(
        provider_credentials.httpx,
        "get",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
    )
    secret = "provider-validation-sentinel"
    assert validator(secret, 7.0)
    assert calls == [
        (
            (url,),
            {
                "headers": {"Authorization": f"Bearer {secret}"},
                "follow_redirects": False,
                "timeout": 7.0,
            },
        )
    ]
