"""Configuration with real layering: env (QD_*) > secrets.yaml > config.yaml > defaults.

Files live under the config dir (default ~/.config/quarterdeck, override QD_CONFIG_DIR):
- config.yaml  — non-secret settings (ledger_dir, paperclip.api_base, company_id, ...)
- secrets.yaml — secrets only (paperclip.api_key, telegram tokens), chmod 600, never in a repo

Legacy escape hatch: the Paperclip API key is also honored from the env var named by
`paperclip.api_key_env` (default PAPERCLIP_API_KEY) via resolve_api_key().
"""

import os
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


def config_dir() -> Path:
    return Path(
        os.environ.get("QD_CONFIG_DIR", str(Path.home() / ".config" / "quarterdeck"))
    ).expanduser()


class PaperclipConfig(BaseModel):
    api_base: str = "http://127.0.0.1:3100"
    api_key: str = ""  # set in secrets.yaml; resolve_api_key() adds the env fallback
    api_key_env: str = "PAPERCLIP_API_KEY"
    company_id: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QD_", env_nested_delimiter="__")

    paperclip: PaperclipConfig = PaperclipConfig()
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
        # Precedence: earlier wins. init > env > secrets.yaml > config.yaml > defaults.
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=config_dir() / "secrets.yaml"),
            YamlConfigSettingsSource(settings_cls, yaml_file=config_dir() / "config.yaml"),
            file_secret_settings,
        )


def resolve_api_key(settings: Settings) -> str:
    return settings.paperclip.api_key or os.environ.get(settings.paperclip.api_key_env, "")


def load_settings() -> Settings:
    return Settings()
