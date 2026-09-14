from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    wiki_root: Path | None = None
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    git_enabled: bool = False
    git_remote: str = "origin"
    git_branch: str = "main"
    log_level: str = "INFO"


settings = Settings()