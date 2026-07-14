import json
from pathlib import Path

from quarterdeck.config import Settings
from quarterdeck.console.providers import (
    CommandResult,
    login_command,
    login_provider,
    probe_provider,
)


def _executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return path


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


def test_provider_login_uses_only_fixed_vendor_owned_flows(tmp_path):
    codex = _executable(tmp_path / "codex")
    claude = _executable(tmp_path / "claude")
    settings = Settings(console={"codex_bin": codex}, gate={"claude_bin": claude})
    assert login_command(settings, "openai") == [str(codex), "login"]
    assert login_command(settings, "anthropic") == [
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
    assert calls == [([str(claude), "auth", "login", "--console"], 420.0)]
