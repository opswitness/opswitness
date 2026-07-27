"""Verified local AI-provider authentication with narrowly scoped credential handoff."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, cast

import httpx

from opswitness.config import Settings
from opswitness.console.provider_credentials import (
    ApiProvider,
    configure_anthropic_api_key,
    configure_provider_api_key,
    managed_anthropic_api_key_helper,
    provider_api_key_available,
)

LocalProviderName = Literal["ollama", "lmstudio"]
ProviderName = Literal["openai", "anthropic", "deepseek", "xai", "ollama", "lmstudio"]
ConnectionMethod = Literal["account", "api", "api_key", "local"]

_LOCAL_PROVIDER_ENDPOINTS: dict[LocalProviderName, str] = {
    "ollama": "http://127.0.0.1:11434/api/tags",
    "lmstudio": "http://127.0.0.1:1234/v1/models",
}
_LOCAL_PROVIDER_APPS: dict[LocalProviderName, Path] = {
    "ollama": Path("/Applications/Ollama.app"),
    "lmstudio": Path("/Applications/LM Studio.app"),
}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[list[str], float], CommandResult]
ApiKeyRunner = Callable[[list[str], str, float], CommandResult]


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


def _api_key_login_runner(argv: list[str], api_key: str, timeout: float) -> CommandResult:
    """Pass a one-time key through stdin without exposing it in argv or command output."""
    try:
        result = subprocess.run(
            argv,
            check=False,
            input=f"{api_key}\n",
            text=True,
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
    if provider == "anthropic":
        return _usable_executable(settings.gate.claude_bin, shutil.which("claude"))
    if provider == "xai":
        return _usable_executable(settings.console.grok_bin, shutil.which("grok"))
    if provider == "ollama":
        return _usable_executable(
            shutil.which("ollama"),
            "/opt/homebrew/bin/ollama",
            "/usr/local/bin/ollama",
        )
    if provider == "lmstudio":
        return _usable_executable(
            shutil.which("lms"),
            Path.home() / ".lmstudio" / "bin" / "lms",
        )
    return None


def _base_status(provider: ProviderName) -> dict[str, object]:
    labels = {
        "openai": "ChatGPT / OpenAI",
        "anthropic": "Claude",
        "deepseek": "DeepSeek",
        "xai": "Grok / xAI",
        "ollama": "Ollama",
        "lmstudio": "LM Studio",
    }
    return {
        "provider": provider,
        "label": labels[provider],
        "installed": False,
        "authenticated": False,
        "auth_mode": "none",
    }


def _local_provider_installed(settings: Settings, provider: LocalProviderName) -> bool:
    app = _LOCAL_PROVIDER_APPS[provider]
    try:
        app_ready = app.resolve(strict=True).is_dir()
    except OSError:
        app_ready = False
    return app_ready or provider_executable(settings, provider) is not None


def _bounded_model_names(provider: LocalProviderName, payload: Any) -> list[str]:
    rows: Any
    key = "name" if provider == "ollama" else "id"
    if provider == "ollama" and isinstance(payload, dict):
        rows = payload.get("models")
    elif provider == "lmstudio" and isinstance(payload, dict):
        rows = payload.get("data")
    else:
        rows = None
    if not isinstance(rows, list):
        return []
    models: list[str] = []
    for row in rows[:100]:
        value = row.get(key) if isinstance(row, dict) else None
        if (
            isinstance(value, str)
            and 0 < len(value) <= 200
            and value.strip() == value
            and not any(ord(character) < 32 for character in value)
            and value not in models
        ):
            models.append(value)
    return models


def _probe_local_provider(
    settings: Settings,
    provider: LocalProviderName,
    *,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    result = _base_status(provider)
    result["installed"] = _local_provider_installed(settings, provider)
    owned_client = client is None
    local_client = client or httpx.Client(follow_redirects=False, trust_env=False)
    try:
        response = local_client.get(_LOCAL_PROVIDER_ENDPOINTS[provider], timeout=0.75)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        result.update(
            server_online=False,
            model_count=0,
            models=[],
            status="setup" if result["installed"] else "offline",
            detail=(
                "已安装；本地模型服务未启动"
                if result["installed"]
                else "本机未安装"
            ),
        )
        return result
    finally:
        if owned_client:
            local_client.close()

    models = _bounded_model_names(provider, payload)
    ready = bool(models)
    result.update(
        server_online=True,
        model_count=len(models),
        models=models,
        authenticated=ready,
        auth_mode="local",
        status="online" if ready else "attention",
        detail=(
            f"本地服务已启动，发现 {len(models)} 个模型"
            if ready
            else "本地服务已启动，但没有已加载模型"
        ),
    )
    return result


def start_local_provider(
    settings: Settings,
    provider: LocalProviderName,
    *,
    runner: Runner = _login_runner,
    probe: Callable[[LocalProviderName], dict[str, object]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """Start only the two fixed loopback model servers after explicit user confirmation."""
    check = probe or (lambda selected: probe_provider(settings, selected))
    if check(provider).get("authenticated") is True:
        return True

    if provider == "ollama":
        app = _LOCAL_PROVIDER_APPS[provider]
        try:
            resolved = app.resolve(strict=True)
        except OSError:
            return False
        if not resolved.is_dir():
            return False
        started = runner(["/usr/bin/open", "-gja", str(resolved)], 10.0)
    else:
        binary = provider_executable(settings, provider)
        if binary is None:
            return False
        started = runner([str(binary), "server", "start"], 45.0)
    if started.returncode != 0:
        return False
    for _ in range(50):
        sleeper(0.5)
        if check(provider).get("authenticated") is True:
            return True
    return False


def probe_provider(
    settings: Settings,
    provider: ProviderName,
    *,
    runner: Runner = _status_runner,
    executable: Path | None = None,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    """Return only fixed authentication facts; command output is never returned."""
    if provider in {"ollama", "lmstudio"}:
        return _probe_local_provider(
            settings,
            cast(LocalProviderName, provider),
            client=client,
        )
    result = _base_status(provider)
    if provider == "deepseek":
        authenticated = provider_api_key_available(settings, "deepseek")
        result.update(
            installed=True,
            authenticated=authenticated,
            auth_mode="api_key" if authenticated else "none",
            status="online" if authenticated else "setup",
            detail="API Key 已连接" if authenticated else "待连接 API Key",
        )
        return result

    binary = executable or provider_executable(settings, provider)
    if provider == "xai" and provider_api_key_available(settings, "xai"):
        result.update(
            installed=binary is not None,
            authenticated=True,
            auth_mode="api_key",
            status="online",
            detail="API Key 已连接",
        )
        return result
    if binary is None:
        detail = "官方 Grok Build 未安装；API Key 仍可连接" if provider == "xai" else "本机客户端未安装"
        result.update(status="offline", detail=detail)
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
    elif provider == "anthropic":
        checked = runner([str(binary), "auth", "status", "--json"], 8.0)
        authenticated = False
        auth_mode = "none"
        try:
            payload = json.loads(checked.stdout)
            if isinstance(payload, dict):
                authenticated = checked.returncode == 0 and payload.get("loggedIn") is True
                raw_method = str(payload.get("authMethod") or "").casefold()
                if authenticated:
                    if raw_method == "api_key" and managed_anthropic_api_key_helper(settings):
                        auth_mode = "api_key"
                    elif raw_method in {"api_key", "console"}:
                        auth_mode = "console"
                    else:
                        auth_mode = "account"
        except json.JSONDecodeError:
            pass
    else:
        checked = runner([str(binary), "models"], 8.0)
        authenticated = checked.returncode == 0
        auth_mode = "account" if authenticated else "none"
    result.update(
        authenticated=authenticated,
        auth_mode=auth_mode,
        status="online" if authenticated else "setup",
        detail="账号已登录" if authenticated else "待登录",
    )
    return result


def login_command(
    settings: Settings,
    provider: ProviderName,
    *,
    method: ConnectionMethod = "account",
) -> list[str]:
    if provider in {"ollama", "lmstudio"}:
        raise ValueError("local model servers use the explicit local connection flow")
    binary = provider_executable(settings, provider)
    if binary is None:
        raise ValueError("provider client is not installed")
    if provider == "openai":
        if method == "api":
            return [str(binary), "login", "--with-api-key"]
        # Codex owns the browser OAuth flow; OpsWitness never sees the credential.
        return [str(binary), "login"]
    if provider == "xai":
        if method != "account":
            raise ValueError("xAI API keys use the managed Keychain path")
        return [str(binary), "login"]
    if provider == "deepseek":
        raise ValueError("DeepSeek supports API key connection only")
    if method == "api_key":
        raise ValueError("Anthropic API keys use the managed apiKeyHelper path")
    raise ValueError(
        "OpsWitness supports Anthropic API keys only; Claude subscription login is not routed"
    )


def login_provider(
    settings: Settings,
    provider: ProviderName,
    *,
    method: ConnectionMethod = "account",
    api_key: str | None = None,
    runner: Runner = _login_runner,
    api_key_runner: ApiKeyRunner = _api_key_login_runner,
    anthropic_api_key_installer: Callable[[Settings, str], bool] = configure_anthropic_api_key,
    provider_api_key_installer: Callable[[Settings, ApiProvider, str], bool] = (
        configure_provider_api_key
    ),
) -> bool:
    if api_key is not None and not (
        (provider == "openai" and method == "api")
        or (provider in {"anthropic", "deepseek", "xai"} and method == "api_key")
    ):
        return False
    if provider == "openai" and method == "api":
        if not api_key or not api_key.strip():
            return False
        return (
            api_key_runner(login_command(settings, provider, method=method), api_key.strip(), 420.0)
            .returncode
            == 0
        )
    if provider == "anthropic" and method == "api_key":
        if not api_key or not api_key.strip():
            return False
        return anthropic_api_key_installer(settings, api_key.strip())
    if provider in {"deepseek", "xai"} and method == "api_key":
        if not api_key or not api_key.strip():
            return False
        return provider_api_key_installer(settings, provider, api_key.strip())
    return runner(login_command(settings, provider, method=method), 420.0).returncode == 0
