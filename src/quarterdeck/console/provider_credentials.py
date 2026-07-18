"""Local provider credential bridges that never place raw keys in argv or evidence."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Callable, Literal

import httpx

from quarterdeck.config import Settings
from quarterdeck.fsutil import atomic_write


ANTHROPIC_KEYCHAIN_ACCOUNT = "api-key"
ANTHROPIC_KEYCHAIN_SERVICE = "com.quarterdeck.anthropic-api-key"
PROVIDER_KEYCHAIN_ACCOUNT = "api-key"
ApiProvider = Literal["deepseek", "xai"]
_PROVIDER_KEYCHAIN_SERVICES: dict[ApiProvider, str] = {
    "deepseek": "com.quarterdeck.deepseek-api-key",
    "xai": "com.quarterdeck.xai-api-key",
}
_SECURITY_BIN = Path("/usr/bin/security")
_MAX_CLAUDE_SETTINGS_BYTES = 1_048_576


class ProviderCredentialError(RuntimeError):
    """A credential could not be validated or installed without weakening its boundary."""


ApiKeyValidator = Callable[[str, float], bool]
SecretRunner = Callable[[list[str], str, float], int]
StatusRunner = Callable[[list[str], float], int]


def _validate_anthropic_api_key(api_key: str, timeout: float) -> bool:
    """Validate without a billable model call; no response content leaves this function."""
    try:
        response = httpx.get(
            "https://api.anthropic.com/v1/models",
            params={"limit": 1},
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            follow_redirects=False,
            timeout=timeout,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _validate_bearer_models_key(
    api_key: str,
    timeout: float,
    *,
    endpoint: str,
) -> bool:
    """Validate one provider key against a fixed, non-billable models endpoint."""
    try:
        response = httpx.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            follow_redirects=False,
            timeout=timeout,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _validate_deepseek_api_key(api_key: str, timeout: float) -> bool:
    return _validate_bearer_models_key(
        api_key,
        timeout,
        endpoint="https://api.deepseek.com/models",
    )


def _validate_xai_api_key(api_key: str, timeout: float) -> bool:
    return _validate_bearer_models_key(
        api_key,
        timeout,
        endpoint="https://api.x.ai/v1/models",
    )


_PROVIDER_VALIDATORS: dict[ApiProvider, ApiKeyValidator] = {
    "deepseek": _validate_deepseek_api_key,
    "xai": _validate_xai_api_key,
}


def _secret_runner(argv: list[str], secret: str, timeout: float) -> int:
    """Feed a secret only through stdin and suppress every child-process stream."""
    try:
        completed = subprocess.run(
            argv,
            input=f"{secret}\n",
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 124
    return completed.returncode


def _status_runner(argv: list[str], timeout: float) -> int:
    """Check Keychain metadata without reading or returning the stored password."""
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 124
    return completed.returncode


def anthropic_api_key_helper_path(settings: Settings) -> Path:
    return settings.console.state_dir.expanduser() / "provider-auth" / "anthropic-api-key-helper"


def provider_api_key_helper_path(settings: Settings, provider: ApiProvider) -> Path:
    return settings.console.state_dir.expanduser() / "provider-auth" / f"{provider}-api-key-helper"


def managed_provider_api_key_helper(settings: Settings, provider: ApiProvider) -> Path | None:
    """Return only a regular, executable helper installed under Quarterdeck state."""
    helper = provider_api_key_helper_path(settings, provider)
    try:
        if helper.is_symlink():
            return None
        metadata = helper.stat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or not os.access(helper, os.X_OK):
        return None
    return helper


def provider_api_key_available(
    settings: Settings,
    provider: ApiProvider,
    *,
    runner: StatusRunner = _status_runner,
) -> bool:
    """Prove that both the managed helper and its Keychain item still exist."""
    if managed_provider_api_key_helper(settings, provider) is None:
        return False
    if not _SECURITY_BIN.is_file() or not os.access(_SECURITY_BIN, os.X_OK):
        return False
    service = _PROVIDER_KEYCHAIN_SERVICES[provider]
    return (
        runner(
            [
                str(_SECURITY_BIN),
                "find-generic-password",
                "-a",
                PROVIDER_KEYCHAIN_ACCOUNT,
                "-s",
                service,
            ],
            5.0,
        )
        == 0
    )


def configure_provider_api_key(
    settings: Settings,
    provider: ApiProvider,
    api_key: str,
    *,
    validator: ApiKeyValidator | None = None,
    secret_runner: SecretRunner = _secret_runner,
) -> bool:
    """Validate and store a DeepSeek or xAI key without writing it to AionUi or disk."""
    api_key = api_key.strip()
    if not api_key or any(character.isspace() for character in api_key):
        return False
    selected_validator = validator or _PROVIDER_VALIDATORS[provider]
    if not selected_validator(api_key, 12.0):
        return False
    if not _SECURITY_BIN.is_file() or not os.access(_SECURITY_BIN, os.X_OK):
        raise ProviderCredentialError("macOS Keychain command is unavailable")

    helper = provider_api_key_helper_path(settings, provider)
    auth_root = helper.parent
    if auth_root.is_symlink():
        raise ProviderCredentialError("provider credential directory must not be a symlink")
    auth_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(auth_root, 0o700)
    if helper.is_symlink():
        raise ProviderCredentialError("provider API key helper must not be a symlink")

    service = _PROVIDER_KEYCHAIN_SERVICES[provider]
    keychain_argv = [
        str(_SECURITY_BIN),
        "add-generic-password",
        "-U",
        "-a",
        PROVIDER_KEYCHAIN_ACCOUNT,
        "-s",
        service,
        "-w",
    ]
    if secret_runner(keychain_argv, api_key, 20.0) != 0:
        return False

    helper_payload = (
        "#!/bin/sh\n"
        "set -eu\n"
        f'exec {_SECURITY_BIN} find-generic-password '
        f'-a {PROVIDER_KEYCHAIN_ACCOUNT} -s {service} -w\n'
    ).encode()
    atomic_write(helper, helper_payload, mode=0o700)
    return True


def claude_user_settings_path() -> Path:
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()
    return root / "settings.json"


def _read_claude_settings(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise ProviderCredentialError("Claude settings file must not be a symlink")
    if not path.exists():
        return {}
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_CLAUDE_SETTINGS_BYTES:
            raise ProviderCredentialError("Claude settings file is not a bounded regular file")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderCredentialError("Claude settings file is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderCredentialError("Claude settings file must contain one JSON object")
    return payload


def managed_anthropic_api_key_helper(settings: Settings) -> Path | None:
    """Return only a helper installed and still owned by this Quarterdeck state directory."""
    helper = anthropic_api_key_helper_path(settings)
    try:
        payload = _read_claude_settings(claude_user_settings_path())
        configured = payload.get("apiKeyHelper")
        if configured != str(helper) or helper.is_symlink():
            return None
        metadata = helper.stat()
    except (OSError, ProviderCredentialError):
        return None
    if not stat.S_ISREG(metadata.st_mode) or not os.access(helper, os.X_OK):
        return None
    return helper


def configure_anthropic_api_key(
    settings: Settings,
    api_key: str,
    *,
    validator: ApiKeyValidator = _validate_anthropic_api_key,
    secret_runner: SecretRunner = _secret_runner,
    claude_settings: Path | None = None,
) -> bool:
    """Validate, keychain-store, and expose an Anthropic key via Claude's apiKeyHelper."""
    api_key = api_key.strip()
    if not api_key or any(character.isspace() for character in api_key):
        return False
    if not validator(api_key, 12.0):
        return False
    if not _SECURITY_BIN.is_file() or not os.access(_SECURITY_BIN, os.X_OK):
        raise ProviderCredentialError("macOS Keychain command is unavailable")

    helper = anthropic_api_key_helper_path(settings)
    auth_root = helper.parent
    if auth_root.is_symlink():
        raise ProviderCredentialError("provider credential directory must not be a symlink")
    auth_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(auth_root, 0o700)
    if helper.is_symlink():
        raise ProviderCredentialError("Anthropic API key helper must not be a symlink")

    settings_path = (claude_settings or claude_user_settings_path()).expanduser()
    settings_root = settings_path.parent
    if settings_root.is_symlink():
        raise ProviderCredentialError("Claude configuration directory must not be a symlink")
    settings_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = _read_claude_settings(settings_path)
    existing_helper = payload.get("apiKeyHelper")
    if existing_helper not in {None, str(helper)}:
        raise ProviderCredentialError("an unmanaged Claude apiKeyHelper is already configured")

    keychain_argv = [
        str(_SECURITY_BIN),
        "add-generic-password",
        "-U",
        "-a",
        ANTHROPIC_KEYCHAIN_ACCOUNT,
        "-s",
        ANTHROPIC_KEYCHAIN_SERVICE,
        "-w",
    ]
    if secret_runner(keychain_argv, api_key, 20.0) != 0:
        return False

    helper_payload = (
        "#!/bin/sh\n"
        "set -eu\n"
        f'exec {_SECURITY_BIN} find-generic-password '
        f'-a {ANTHROPIC_KEYCHAIN_ACCOUNT} -s {ANTHROPIC_KEYCHAIN_SERVICE} -w\n'
    ).encode()
    atomic_write(helper, helper_payload, mode=0o700)
    payload["apiKeyHelper"] = str(helper)
    atomic_write(
        settings_path,
        (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode(),
        mode=0o600,
    )
    return True
