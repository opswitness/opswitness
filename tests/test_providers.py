import json
from pathlib import Path

import httpx
import pytest

from quarterdeck.config import Settings
from quarterdeck.console import providers
from quarterdeck.console.providers import (
    CommandResult,
    login_command,
    login_provider,
    probe_provider,
    start_local_provider,
)


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


@pytest.mark.parametrize(
    ("provider", "url", "payload", "expected"),
    [
        (
            "ollama",
            "http://127.0.0.1:11434/api/tags",
            {"models": [{"name": "qwen3:8b"}, {"name": "qwen3:8b"}]},
            ["qwen3:8b"],
        ),
        (
            "lmstudio",
            "http://127.0.0.1:1234/v1/models",
            {"data": [{"id": "local/qwen3-8b"}]},
            ["local/qwen3-8b"],
        ),
    ],
)
def test_local_provider_probe_uses_only_fixed_loopback_and_bounded_models(
    tmp_path,
    monkeypatch,
    provider,
    url,
    payload,
    expected,
):
    del tmp_path
    monkeypatch.setattr(providers, "_local_provider_installed", lambda *args: True)
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_provider(Settings(), provider, client=client)

    assert requested == [url]
    assert result["server_online"] is True
    assert result["authenticated"] is True
    assert result["auth_mode"] == "local"
    assert result["models"] == expected
    assert result["model_count"] == len(expected)


def test_local_provider_probe_does_not_claim_ready_without_a_model(monkeypatch):
    monkeypatch.setattr(providers, "_local_provider_installed", lambda *args: True)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []}))
    with httpx.Client(transport=transport) as client:
        result = probe_provider(Settings(), "ollama", client=client)

    assert result["server_online"] is True
    assert result["authenticated"] is False
    assert result["status"] == "attention"
    assert result["model_count"] == 0


def test_local_provider_start_uses_fixed_vendor_commands(tmp_path, monkeypatch):
    ollama_app = tmp_path / "Ollama.app"
    ollama_app.mkdir()
    monkeypatch.setitem(providers._LOCAL_PROVIDER_APPS, "ollama", ollama_app)
    lms = _executable(tmp_path / "lms")
    monkeypatch.setattr(
        providers,
        "provider_executable",
        lambda settings, selected: lms if selected == "lmstudio" else None,
    )
    calls = []

    def runner(argv, timeout):
        calls.append((argv, timeout))
        return CommandResult(0)

    def ready_after_start(selected):
        connected = any(
            (selected == "ollama" and call[0][0] == "/usr/bin/open")
            or (selected == "lmstudio" and call[0][0] == str(lms))
            for call in calls
        )
        return {"authenticated": connected}

    assert start_local_provider(
        Settings(),
        "ollama",
        runner=runner,
        probe=ready_after_start,
        sleeper=lambda _: None,
    )
    assert start_local_provider(
        Settings(),
        "lmstudio",
        runner=runner,
        probe=ready_after_start,
        sleeper=lambda _: None,
    )
    assert calls == [
        (["/usr/bin/open", "-gja", str(ollama_app.resolve())], 10.0),
        ([str(lms), "server", "start"], 45.0),
    ]


def test_openai_probe_distinguishes_chatgpt_login_without_returning_output(tmp_path):
    binary = _executable(tmp_path / "codex")
    calls = []

    def runner(argv, timeout):
        calls.append((argv, timeout))
        return CommandResult(0, "Logged in using ChatGPT", "private@example.com")

    result = probe_provider(
        Settings(console={"codex_bin": binary}),
        "openai",
        runner=runner,
        executable=binary,
    )
    assert result == {
        "provider": "openai",
        "label": "ChatGPT / OpenAI",
        "installed": True,
        "authenticated": True,
        "auth_mode": "chatgpt",
        "status": "online",
        "detail": "账号已登录",
    }
    assert calls == [([str(binary), "login", "status"], 8.0)]
    assert "private@example.com" not in json.dumps(result)


def test_claude_probe_requires_structured_logged_in_status(tmp_path):
    binary = _executable(tmp_path / "claude")

    def ready(argv, timeout):
        assert argv == [str(binary), "auth", "status", "--json"]
        assert timeout == 8.0
        return CommandResult(
            0,
            json.dumps(
                {"loggedIn": True, "authMethod": "api_key", "email": "private@example.com"}
            ),
        )

    result = probe_provider(
        Settings(gate={"claude_bin": binary}),
        "anthropic",
        runner=ready,
        executable=binary,
    )
    assert result["authenticated"] is True
    assert result["auth_mode"] == "console"
    assert "private@example.com" not in json.dumps(result)

    malformed = probe_provider(
        Settings(gate={"claude_bin": binary}),
        "anthropic",
        runner=lambda argv, timeout: CommandResult(0, "not-json"),
        executable=binary,
    )
    assert malformed["authenticated"] is False
    assert malformed["status"] == "setup"


def test_claude_probe_identifies_quarterdeck_managed_api_key_helper(tmp_path, monkeypatch):
    binary = _executable(tmp_path / "claude")
    state = tmp_path / "state"
    helper = state / "provider-auth" / "anthropic-api-key-helper"
    helper.parent.mkdir(parents=True)
    _executable(helper)
    claude_root = tmp_path / "claude-config"
    claude_root.mkdir()
    (claude_root / "settings.json").write_text(
        json.dumps({"apiKeyHelper": str(helper)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_root))
    result = probe_provider(
        Settings(gate={"claude_bin": binary}, console={"state_dir": state}),
        "anthropic",
        runner=lambda argv, timeout: CommandResult(
            0,
            json.dumps({"loggedIn": True, "authMethod": "api_key"}),
        ),
        executable=binary,
    )
    assert result["authenticated"] is True
    assert result["auth_mode"] == "api_key"


def test_provider_login_uses_only_fixed_vendor_owned_flows(tmp_path):
    codex = _executable(tmp_path / "codex")
    claude = _executable(tmp_path / "claude")
    settings = Settings(console={"codex_bin": codex}, gate={"claude_bin": claude})
    assert login_command(settings, "openai") == [str(codex), "login"]
    assert login_command(settings, "openai", method="api") == [
        str(codex),
        "login",
        "--with-api-key",
    ]
    assert login_command(settings, "anthropic") == [
        str(claude),
        "auth",
        "login",
        "--claudeai",
    ]
    assert login_command(settings, "anthropic", method="api") == [
        str(claude),
        "auth",
        "login",
        "--console",
    ]
    calls = []
    assert login_provider(
        settings,
        "anthropic",
        runner=lambda argv, timeout: calls.append((argv, timeout)) or CommandResult(0),
    )
    assert calls == [([str(claude), "auth", "login", "--claudeai"], 420.0)]
    assert login_provider(
        settings,
        "anthropic",
        method="api",
        runner=lambda argv, timeout: calls.append((argv, timeout)) or CommandResult(0),
    )
    assert calls[-1] == ([str(claude), "auth", "login", "--console"], 420.0)


def test_openai_api_key_login_only_passes_key_to_stdin_runner(tmp_path):
    codex = _executable(tmp_path / "codex")
    settings = Settings(console={"codex_bin": codex})
    secret = "sk-local-sentinel-value"
    calls = []

    assert login_provider(
        settings,
        "openai",
        method="api",
        api_key=secret,
        api_key_runner=lambda argv, api_key, timeout: calls.append((argv, api_key, timeout))
        or CommandResult(0),
    )
    assert calls == [([str(codex), "login", "--with-api-key"], secret, 420.0)]
    assert secret not in " ".join(calls[0][0])
    assert not login_provider(settings, "openai", method="api")
    assert not login_provider(
        settings,
        "anthropic",
        method="api",
        api_key=secret,
    )


def test_anthropic_api_key_uses_managed_installer_not_vendor_login_runner(tmp_path):
    claude = _executable(tmp_path / "claude")
    settings = Settings(gate={"claude_bin": claude})
    secret = "sk-ant-local-sentinel-value"
    installs = []
    vendor_calls = []

    assert login_provider(
        settings,
        "anthropic",
        method="api_key",
        api_key=secret,
        runner=lambda argv, timeout: vendor_calls.append((argv, timeout)) or CommandResult(1),
        anthropic_api_key_installer=lambda configured, value: installs.append(
            (configured, value)
        )
        or True,
    )
    assert installs == [(settings, secret)]
    assert vendor_calls == []
    assert not login_provider(settings, "anthropic", method="api_key")


def test_deepseek_probe_reports_managed_key_without_claiming_a_client(tmp_path, monkeypatch):
    settings = Settings(console={"state_dir": tmp_path / "state"})
    monkeypatch.setattr(providers, "provider_api_key_available", lambda configured, name: True)

    result = probe_provider(settings, "deepseek")

    assert result == {
        "provider": "deepseek",
        "label": "DeepSeek",
        "installed": True,
        "authenticated": True,
        "auth_mode": "api_key",
        "status": "online",
        "detail": "API Key 已连接",
    }


def test_grok_probe_supports_account_and_managed_api_key(tmp_path, monkeypatch):
    grok = _executable(tmp_path / "grok")
    settings = Settings(console={"grok_bin": grok, "state_dir": tmp_path / "state"})
    monkeypatch.setattr(providers, "provider_api_key_available", lambda configured, name: False)
    calls = []
    account = probe_provider(
        settings,
        "xai",
        executable=grok,
        runner=lambda argv, timeout: calls.append((argv, timeout)) or CommandResult(0, "private"),
    )
    assert calls == [([str(grok), "models"], 8.0)]
    assert account["authenticated"] is True
    assert account["auth_mode"] == "account"
    assert "private" not in json.dumps(account)

    monkeypatch.setattr(providers, "provider_api_key_available", lambda configured, name: True)
    keyed = probe_provider(settings, "xai", executable=grok)
    assert keyed["authenticated"] is True
    assert keyed["auth_mode"] == "api_key"


def test_grok_account_login_uses_only_official_cli_flow(tmp_path):
    grok = _executable(tmp_path / "grok")
    settings = Settings(console={"grok_bin": grok})
    assert login_command(settings, "xai") == [str(grok), "login"]
    calls = []
    assert login_provider(
        settings,
        "xai",
        runner=lambda argv, timeout: calls.append((argv, timeout)) or CommandResult(0),
    )
    assert calls == [([str(grok), "login"], 420.0)]


@pytest.mark.parametrize("provider", ["deepseek", "xai"])
def test_provider_api_key_uses_managed_installer_without_vendor_process(tmp_path, provider):
    settings = Settings(console={"state_dir": tmp_path / "state"})
    secret = f"{provider}-local-sentinel-value"
    installs = []
    vendor_calls = []

    assert login_provider(
        settings,
        provider,
        method="api_key",
        api_key=secret,
        runner=lambda argv, timeout: vendor_calls.append((argv, timeout)) or CommandResult(1),
        provider_api_key_installer=lambda configured, selected, value: installs.append(
            (configured, selected, value)
        )
        or True,
    )
    assert installs == [(settings, provider, secret)]
    assert vendor_calls == []
    assert not login_provider(settings, provider, method="api_key")
