"""Configuration with real layering: env (QD_*) > secrets.yaml > config.yaml > defaults.

Files live under the config dir (default ~/.config/quarterdeck, override QD_CONFIG_DIR):
- config.yaml  — non-secret settings (ledger_dir, paperclip.api_base, company_id, ...)
- secrets.yaml — secrets only (paperclip.api_key, telegram tokens), chmod 600, never in a repo

Legacy escape hatch: the Paperclip API key is also honored from the env var named by
`paperclip.api_key_env` (default PAPERCLIP_API_KEY) via resolve_api_key().
"""

import os
import re
import stat
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from quarterdeck.fsutil import atomic_write


def config_dir() -> Path:
    return Path(
        os.environ.get("QD_CONFIG_DIR", str(Path.home() / ".config" / "quarterdeck"))
    ).expanduser()


MAIL_ACTIVATION_FILE = "mail-activation.yaml"


class PaperclipConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_base: str = "http://127.0.0.1:3100"
    api_key: str = ""  # set in secrets.yaml; resolve_api_key() adds the env fallback
    api_key_env: str = "PAPERCLIP_API_KEY"
    company_id: str | None = None


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot_token: str = ""  # secrets.yaml only
    chat_id: str = ""


class ServicesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    qd_bin: Path = Path.home() / ".local" / "bin" / "qd"
    paperclip_command: list[str] = []
    paperclip_home: Path = Path.home() / ".local" / "share" / "paperclip"
    log_dir: Path = Path.home() / "Library" / "Logs" / "Quarterdeck"


class BackupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: Path = Path.home() / ".local" / "state" / "quarterdeck" / "backups"
    age_recipient: str = ""


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claude_bin: Path = Path.home() / ".local" / "bin" / "claude"
    state_dir: Path = Path.home() / ".local" / "state" / "quarterdeck" / "gate"
    approval_ttl_seconds: int = Field(default=3600, ge=30, le=604800)
    poll_seconds: float = Field(default=2.0, ge=0.1, le=60)


class MailConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    model_metadata_consent: bool = False
    gws_bin: Path = Path.home() / ".local" / "bin" / "gws"
    required_version: str = "0.22.5"
    query: str = Field(
        default="in:inbox is:unread newer_than:14d -in:spam -in:trash",
        min_length=1,
        max_length=512,
    )
    max_messages: int = Field(default=20, ge=1, le=100)
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    oauth_timeout_seconds: float = Field(default=300.0, ge=60.0, le=900.0)


class ConsoleConfig(BaseModel):
    """Loopback-only total console and local AionUi adapter settings."""

    model_config = ConfigDict(extra="forbid")
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    aionui_base: str = "http://127.0.0.1:63021"
    state_dir: Path = Path.home() / ".local" / "state" / "quarterdeck" / "console"
    planner_timeout_seconds: float = Field(default=180.0, ge=30.0, le=600.0)
    planner_assistant_id: str = "bare:2d23ff1c"
    runtime_assistants: dict[str, str] = Field(
        default_factory=lambda: {
            "claude_code": "bare:2d23ff1c",
            "codex_cli": "bare:8e1acf31",
            "aion_cli": "bare:632f31d2",
        }
    )

    @field_validator("host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("console.host must be 127.0.0.1")
        return value

    @field_validator("aionui_base")
    @classmethod
    def local_aionui_only(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("console.aionui_base must be an unauthenticated loopback HTTP URL")
        return value.rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QD_", env_nested_delimiter="__", extra="forbid")

    paperclip: PaperclipConfig = PaperclipConfig()
    telegram: TelegramConfig = TelegramConfig()
    services: ServicesConfig = ServicesConfig()
    backup: BackupConfig = BackupConfig()
    gate: GateConfig = GateConfig()
    mail: MailConfig = MailConfig()
    console: ConsoleConfig = ConsoleConfig()
    database_url: str = ""  # secrets.yaml or QD_DATABASE_URL only
    ledger_dir: Path = Path.home() / ".local" / "state" / "quarterdeck" / "ledger"
    log_tail_bytes: int = 8192
    capture_log_tail: bool = True
    redact: bool = True

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        validate_config_files(config_dir())
        # Precedence: earlier wins. init > env > secrets.yaml > config.yaml > defaults.
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=config_dir() / MAIL_ACTIVATION_FILE,
            ),
            YamlConfigSettingsSource(settings_cls, yaml_file=config_dir() / "secrets.yaml"),
            YamlConfigSettingsSource(settings_cls, yaml_file=config_dir() / "config.yaml"),
            file_secret_settings,
        )


def resolve_api_key(settings: Settings) -> str:
    return settings.paperclip.api_key or os.environ.get(settings.paperclip.api_key_env, "")


def load_settings() -> Settings:
    return Settings()


_CONFIG_SECRET_PATHS = {
    ("database_url",),
    ("paperclip", "api_key"),
    ("telegram", "bot_token"),
    ("telegram", "chat_id"),
}
_SECRETS_ALLOWED_PATHS = _CONFIG_SECRET_PATHS
_MAIL_ACTIVATION_ALLOWED_PATHS = {
    ("mail", "enabled"),
    ("mail", "model_metadata_consent"),
}


def _yaml_mapping(path: Path) -> dict:
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: cannot read valid YAML — {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    return raw


def _leaf_paths(value: object, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if not isinstance(value, dict):
        return {prefix}
    found: set[tuple[str, ...]] = set()
    for key, child in value.items():
        found.update(_leaf_paths(child, (*prefix, str(key))))
    return found


def validate_config_files(root: Path | None = None) -> None:
    """Enforce the secret boundary before any Settings source is read."""
    root = root or config_dir()
    config_path = root / "config.yaml"
    secrets_path = root / "secrets.yaml"
    mail_activation_path = root / MAIL_ACTIVATION_FILE
    if not root.exists():
        return
    try:
        root_mode = stat.S_IMODE(root.stat().st_mode)
    except OSError as exc:
        raise ValueError(f"{root}: cannot stat config directory — {exc}") from exc
    if root_mode != 0o700:
        raise ValueError(f"{root}: config directory mode must be 0700, found {root_mode:04o}")
    if not config_path.exists() and not secrets_path.exists() and not mail_activation_path.exists():
        return
    if secrets_path.exists():
        mode = stat.S_IMODE(secrets_path.stat().st_mode)
        if mode != 0o600:
            raise ValueError(f"{secrets_path}: secrets mode must be 0600, found {mode:04o}")
        secret_paths = _leaf_paths(_yaml_mapping(secrets_path))
        forbidden = sorted(secret_paths - _SECRETS_ALLOWED_PATHS)
        if forbidden:
            rendered = ", ".join(".".join(path) for path in forbidden)
            raise ValueError(f"{secrets_path}: non-secret fields are forbidden here: {rendered}")
    if config_path.exists():
        config_paths = _leaf_paths(_yaml_mapping(config_path))
        leaked = sorted(config_paths & _CONFIG_SECRET_PATHS)
        if leaked:
            rendered = ", ".join(".".join(path) for path in leaked)
            raise ValueError(f"{config_path}: secret fields must move to secrets.yaml: {rendered}")
    if mail_activation_path.exists():
        if mail_activation_path.is_symlink():
            raise ValueError(f"{mail_activation_path}: managed mail state must not be a symlink")
        mode = stat.S_IMODE(mail_activation_path.stat().st_mode)
        if mode != 0o600:
            raise ValueError(
                f"{mail_activation_path}: managed mail state mode must be 0600, "
                f"found {mode:04o}"
            )
        activation_paths = _leaf_paths(_yaml_mapping(mail_activation_path))
        forbidden = sorted(activation_paths - _MAIL_ACTIVATION_ALLOWED_PATHS)
        if forbidden:
            rendered = ", ".join(".".join(path) for path in forbidden)
            raise ValueError(
                f"{mail_activation_path}: unsupported managed mail fields: {rendered}"
            )


_TELEGRAM_BOT_TOKEN = re.compile(r"^[0-9]+:[A-Za-z0-9_-]+$")
_TELEGRAM_CHAT_ID = re.compile(r"^(?:-?[0-9]+|@[A-Za-z][A-Za-z0-9_]{4,31})$")


def save_telegram_credentials(
    bot_token: str,
    chat_id: str,
    *,
    replace: bool = False,
    root: Path | None = None,
) -> Path:
    """Atomically merge Telegram credentials into the permission-checked secret file."""
    bot_token = bot_token.strip()
    chat_id = chat_id.strip()
    if not _TELEGRAM_BOT_TOKEN.fullmatch(bot_token):
        raise ValueError("Telegram bot token has an invalid format")
    if not _TELEGRAM_CHAT_ID.fullmatch(chat_id):
        raise ValueError("Telegram chat ID has an invalid format")

    root = (root or config_dir()).expanduser()
    if root.is_symlink():
        raise ValueError(f"{root}: config directory must not be a symlink")
    secrets_path = root / "secrets.yaml"
    if root.exists():
        if secrets_path.is_symlink():
            raise ValueError(f"{secrets_path}: secrets file must not be a symlink")
        validate_config_files(root)
    else:
        root.mkdir(parents=True, mode=0o700)
        root.chmod(0o700)

    raw = _yaml_mapping(secrets_path) if secrets_path.exists() else {}
    telegram = raw.get("telegram", {})
    if not isinstance(telegram, dict):
        raise ValueError(f"{secrets_path}: telegram must be a mapping")
    if not replace and (telegram.get("bot_token") or telegram.get("chat_id")):
        raise ValueError("Telegram credentials already exist; pass --replace to overwrite them")

    raw["telegram"] = {"bot_token": bot_token, "chat_id": chat_id}
    payload = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode()
    atomic_write(secrets_path, payload, mode=0o600)
    validate_config_files(root)
    return secrets_path


def clear_telegram_credentials(*, root: Path | None = None) -> bool:
    """Remove only Telegram values while preserving every other secret."""
    root = (root or config_dir()).expanduser()
    if root.is_symlink():
        raise ValueError(f"{root}: config directory must not be a symlink")
    secrets_path = root / "secrets.yaml"
    if not root.exists() or not secrets_path.exists():
        return False
    if secrets_path.is_symlink():
        raise ValueError(f"{secrets_path}: secrets file must not be a symlink")
    validate_config_files(root)
    raw = _yaml_mapping(secrets_path)
    if "telegram" not in raw:
        return False
    del raw["telegram"]
    payload = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode()
    atomic_write(secrets_path, payload, mode=0o600)
    validate_config_files(root)
    return True


def save_mail_activation(
    *,
    enabled: bool,
    model_metadata_consent: bool,
    root: Path | None = None,
) -> Path:
    """Persist the console-owned mail enable/consent decision without rewriting config.yaml."""
    if model_metadata_consent and not enabled:
        raise ValueError("model metadata consent requires the mail adapter to be enabled")

    root = (root or config_dir()).expanduser()
    if root.is_symlink():
        raise ValueError(f"{root}: config directory must not be a symlink")
    activation_path = root / MAIL_ACTIVATION_FILE
    if root.exists():
        if activation_path.is_symlink():
            raise ValueError(f"{activation_path}: managed mail state must not be a symlink")
        validate_config_files(root)
    else:
        root.mkdir(parents=True, mode=0o700)
        root.chmod(0o700)

    payload = yaml.safe_dump(
        {
            "mail": {
                "enabled": enabled,
                "model_metadata_consent": model_metadata_consent,
            }
        },
        sort_keys=False,
        allow_unicode=True,
    ).encode()
    atomic_write(activation_path, payload, mode=0o600)
    validate_config_files(root)
    return activation_path
