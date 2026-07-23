"""Configuration with real layering and fail-closed legacy compatibility.

Files live under the selected config dir (new default ~/.config/opswitness):
- config.yaml  — non-secret settings (ledger_dir, paperclip.api_base, company_id, ...)
- secrets.yaml — secrets only (paperclip.api_key, telegram tokens), chmod 600, never in a repo

``OPSWITNESS_*`` is canonical. Every former ``QD_*`` variable remains an alias;
setting both names to different values is rejected. Existing Quarterdeck data is
used in place when it is the only installation found. The application never
silently merges two state trees.

Legacy escape hatch: the Paperclip API key is also honored from the env var named by
`paperclip.api_key_env` (default PAPERCLIP_API_KEY) via resolve_api_key().
"""

import os
import re
import stat
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from opswitness.fsutil import atomic_write


CANONICAL_ENV_PREFIX = "OPSWITNESS_"
LEGACY_ENV_PREFIX = "QD_"


def _expanded_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _validate_env_aliases() -> None:
    """Reject ambiguous canonical/legacy environment configuration."""
    for legacy_name, legacy_value in os.environ.items():
        if not legacy_name.startswith(LEGACY_ENV_PREFIX):
            continue
        canonical_name = f"{CANONICAL_ENV_PREFIX}{legacy_name[len(LEGACY_ENV_PREFIX):]}"
        canonical_value = os.environ.get(canonical_name)
        if canonical_value is not None and canonical_value != legacy_value:
            raise ValueError(
                f"conflicting environment variables: {canonical_name} and {legacy_name}"
            )


def _aliased_env_path(canonical_name: str, legacy_name: str) -> Path | None:
    canonical_value = os.environ.get(canonical_name)
    legacy_value = os.environ.get(legacy_name)
    if canonical_value is not None and legacy_value is not None:
        canonical_path = _expanded_path(canonical_value)
        legacy_path = _expanded_path(legacy_value)
        if canonical_path != legacy_path:
            raise ValueError(
                f"conflicting environment variables: {canonical_name} and {legacy_name}"
            )
        return canonical_path
    value = canonical_value if canonical_value is not None else legacy_value
    return _expanded_path(value) if value is not None else None


def _select_install_path(*, new: Path, legacy: Path, purpose: str) -> Path:
    """Reuse one existing tree and refuse an implicit merge."""
    new_exists = new.exists()
    legacy_exists = legacy.exists()
    if new_exists and legacy_exists and new != legacy:
        raise ValueError(
            f"both OpsWitness and Quarterdeck {purpose} directories exist; "
            "set an explicit OPSWITNESS_* path before starting"
        )
    if legacy_exists:
        return legacy
    return new


def config_dir() -> Path:
    _validate_env_aliases()
    explicit = _aliased_env_path("OPSWITNESS_CONFIG_DIR", "QD_CONFIG_DIR")
    if explicit is not None:
        return explicit
    return _select_install_path(
        new=Path.home() / ".config" / "opswitness",
        legacy=Path.home() / ".config" / "quarterdeck",
        purpose="configuration",
    )


def state_root() -> Path:
    explicit = _aliased_env_path("OPSWITNESS_STATE_DIR", "QD_STATE_DIR")
    if explicit is not None:
        return explicit
    return _select_install_path(
        new=Path.home() / ".local" / "state" / "opswitness",
        legacy=Path.home() / ".local" / "state" / "quarterdeck",
        purpose="state",
    )


def log_root() -> Path:
    return _select_install_path(
        new=Path.home() / "Library" / "Logs" / "OpsWitness",
        legacy=Path.home() / "Library" / "Logs" / "Quarterdeck",
        purpose="log",
    )


def cli_path() -> Path:
    canonical = Path.home() / ".local" / "bin" / "opswitness"
    legacy = Path.home() / ".local" / "bin" / "qd"
    if canonical.is_file():
        return canonical
    if legacy.is_file():
        return legacy
    return canonical


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
    qd_bin: Path = Field(default_factory=cli_path)
    paperclip_command: list[str] = []
    paperclip_home: Path = Path.home() / ".local" / "share" / "paperclip"
    log_dir: Path = Field(default_factory=log_root)


class BackupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: Path = Field(default_factory=lambda: state_root() / "backups")
    age_recipient: str = ""


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claude_bin: Path = Path.home() / ".local" / "bin" / "claude"
    state_dir: Path = Field(default_factory=lambda: state_root() / "gate")
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
    """Local console plus an explicit, fail-closed private HTTPS exposure mode."""

    model_config = ConfigDict(extra="forbid")
    exposure: Literal["loopback", "private"] = "loopback"
    private_transport: Literal["direct_tls", "trusted_loopback_proxy"] = "direct_tls"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    public_host: str = ""
    public_port: int | None = Field(default=None, ge=1, le=65535)
    tls_certfile: Path | None = None
    tls_keyfile: Path | None = None
    pairing_code_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    device_session_days: int = Field(default=90, ge=1, le=365)
    aionui_base: str = "http://127.0.0.1:63021"
    aionui_app: Path = Path("/Applications/AionUi.app")
    codex_bin: Path = Path("/Applications/Codex.app/Contents/Resources/codex")
    grok_bin: Path = Path.home() / ".local" / "bin" / "grok"
    state_dir: Path = Field(default_factory=lambda: state_root() / "console")
    planner_timeout_seconds: float = Field(default=180.0, ge=30.0, le=600.0)
    planner_assistant_id: str = "bare:2d23ff1c"
    runtime_assistants: dict[str, str] = Field(
        default_factory=lambda: {
            "claude_code": "bare:2d23ff1c",
            "codex_cli": "bare:8e1acf31",
            "aion_cli": "bare:632f31d2",
        }
    )

    @model_validator(mode="after")
    def validate_exposure(self) -> "ConsoleConfig":
        if self.exposure == "loopback":
            if self.host != "127.0.0.1":
                raise ValueError("console.host must be 127.0.0.1 in loopback mode")
            if self.public_host:
                raise ValueError("console.public_host is only valid in private mode")
            if self.public_port is not None:
                raise ValueError("console.public_port is only valid in private mode")
            if self.private_transport != "direct_tls":
                raise ValueError("console.private_transport is only valid in private mode")
            if self.tls_certfile is not None or self.tls_keyfile is not None:
                raise ValueError("console TLS files are only valid in private mode")
            return self

        try:
            bind_address = ip_address(self.host)
        except ValueError as exc:
            raise ValueError("console.host must be an IP address in private mode") from exc
        tailscale_v4 = ip_network("100.64.0.0/10")
        if not (
            bind_address.is_unspecified
            or bind_address.is_private
            or bind_address in tailscale_v4
        ):
            raise ValueError("console.host must be a private or wildcard IP address")
        if not self.public_host or any(
            character in self.public_host for character in "/:@?#[]"
        ):
            raise ValueError("console.public_host must be one DNS name or IPv4 address")
        if len(self.public_host) > 253 or self.public_host.startswith("."):
            raise ValueError("console.public_host is invalid")
        try:
            ip_address(self.public_host)
        except ValueError:
            labels = self.public_host.rstrip(".").split(".")
            if not labels or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels
            ):
                raise ValueError("console.public_host is invalid") from None
        if self.private_transport == "trusted_loopback_proxy":
            if self.host != "127.0.0.1":
                raise ValueError("trusted_loopback_proxy must bind console.host to 127.0.0.1")
            if self.tls_certfile is not None or self.tls_keyfile is not None:
                raise ValueError("trusted_loopback_proxy must not configure console TLS files")
        elif self.tls_certfile is None or self.tls_keyfile is None:
            raise ValueError("private direct_tls exposure requires tls_certfile and tls_keyfile")
        return self

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
    model_config = SettingsConfigDict(env_prefix="OPSWITNESS_", env_nested_delimiter="__", extra="forbid")

    paperclip: PaperclipConfig = Field(default_factory=PaperclipConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    gate: GateConfig = Field(default_factory=GateConfig)
    mail: MailConfig = Field(default_factory=MailConfig)
    console: ConsoleConfig = Field(default_factory=ConsoleConfig)
    database_url: str = ""  # secrets.yaml or OPSWITNESS_DATABASE_URL only
    ledger_dir: Path = Field(default_factory=lambda: state_root() / "ledger")
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
        _validate_env_aliases()
        validate_config_files(config_dir())
        legacy_env = EnvSettingsSource(
            settings_cls,
            env_prefix=LEGACY_ENV_PREFIX,
            env_nested_delimiter="__",
        )
        # Precedence: init > canonical env > legacy env > YAML > defaults.
        return (
            init_settings,
            env_settings,
            legacy_env,
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
