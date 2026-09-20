from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from the repository-root .env file."""

    app_name: str = "Voker Voice API"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://voker:voker_dev@localhost:5432/voker_voice"
    api_prefix: str = "/api"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
