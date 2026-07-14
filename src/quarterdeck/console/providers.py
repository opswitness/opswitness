"""Verified local AI-provider authentication without handling user credentials."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from quarterdeck.config import Settings

ProviderName = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[list[str], float], CommandResult]


def _status_runner(argv: list[str], timeout: float) -> CommandResult:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return CommandResult(124)
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _login_runner(argv: list[str], timeout: float) -> CommandResult:
    try:
        result = subprocess.run(
            argv,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return CommandResult(124)
    return CommandResult(result.returncode)


def _usable_executable(*candidates: Path | str | None) -> Path | None:
    for raw in candidates:
        if raw is None:
            continue
        value = str(raw)
        discovered = shutil.which(value) if "/" not in value else value
        if not discovered:
            continue
        try:
            candidate = Path(discovered).expanduser().resolve(strict=True)
        except OSError:
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def provider_executable(settings: Settings, provider: ProviderName) -> Path | None:
    if provider == "openai":
        return _usable_executable(
            settings.console.codex_bin,
            shutil.which("codex"),
            "/Applications/Codex.app/Contents/Resources/codex",
        )
    return _usable_executable(settings.gate.claude_bin, shutil.which("claude"))


def _base_status(provider: ProviderName) -> dict[str, object]:
    return {
        "provider": provider,
        "label": "ChatGPT / OpenAI" if provider == "openai" else "Claude",
        "installed": False,
        "authenticated": False,
        "auth_mode": "none",
    }


def probe_provider(
    settings: Settings,
    provider: ProviderName,
    *,
    runner: Runner = _status_runner,
    executable: Path | None = None,
) -> dict[str, object]:
    """Return only fixed authentication facts; command output is never returned."""
    result = _base_status(provider)
    binary = executable or provider_executable(settings, provider)
    if binary is None:
        result.update(status="offline", detail="本机客户端未安装")
        return result
    result["installed"] = True
    if provider == "openai":
        checked = runner([str(binary), "login", "status"], 8.0)
        rendered = f"{checked.stdout}\n{checked.stderr}".casefold()
        authenticated = checked.returncode == 0
        if "chatgpt" in rendered:
            auth_mode = "chatgpt"
        elif "api key" in rendered or "api-key" in rendered:
            auth_mode = "api_key"
        else:
            auth_mode = "unknown" if authenticated else "none"
    else:
        checked = runner([str(binary), "auth", "status", "--json"], 8.0)
        authenticated = False
        auth_mode = "none"
        try:
            payload = json.loads(checked.stdout)
            if isinstance(payload, dict):
                authenticated = checked.returncode == 0 and payload.get("loggedIn") is True
                raw_method = str(payload.get("authMethod") or "").casefold()
                if authenticated:
                    auth_mode = "console" if raw_method in {"api_key", "console"} else "account"
        except json.JSONDecodeError:
            pass
    result.update(
        authenticated=authenticated,
        auth_mode=auth_mode,
        status="online" if authenticated else "setup",
        detail="账号已登录" if authenticated else "待登录",
    )
    return result


def login_command(settings: Settings, provider: ProviderName) -> list[str]:
    binary = provider_executable(settings, provider)
    if binary is None:
        raise ValueError("provider client is not installed")
    if provider == "openai":
        # Codex owns the browser OAuth flow; Quarterdeck never sees the credential.
        return [str(binary), "login"]
    # Commercial/product use follows Anthropic Console billing rather than consumer credentials.
    return [str(binary), "auth", "login", "--console"]


def login_provider(
    settings: Settings,
    provider: ProviderName,
    *,
    runner: Runner = _login_runner,
) -> bool:
    return runner(login_command(settings, provider), 420.0).returncode == 0
