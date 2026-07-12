"""Configuration: env (QD_*) > yaml (~/.config/quarterdeck/config.yaml) > defaults.

Secrets (Paperclip API keys, Telegram bot token) live outside the repo in
~/.config/quarterdeck/secrets.yaml (chmod 600) or environment variables — never in config
files that could be committed.
"""

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path.home() / ".config" / "quarterdeck"


class PaperclipConfig(BaseModel):
    api_base: str = "http://127.0.0.1:3100"
    api_key_env: str = "PAPERCLIP_API_KEY"
    company_id: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QD_", env_nested_delimiter="__")

    paperclip: PaperclipConfig = PaperclipConfig()
    ledger_dir: Path = Path.home() / ".local" / "state" / "quarterdeck" / "ledger"
    log_tail_bytes: int = 8192
    capture_log_tail: bool = True
    redact: bool = True


def load_settings() -> Settings:
    return Settings()
