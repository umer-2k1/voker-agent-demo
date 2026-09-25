from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Runtime configuration loaded from the repository-root .env file."""

    app_name: str = "Voker Voice API"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://voker:voker_dev@localhost:5432/voker_voice"
    api_prefix: str = "/api"
    ingest_max_body_bytes: int = 2_000_000
    ingest_max_events: int = 500
    semantic_evaluator_provider: Literal["openrouter", "deepseek"] = "openrouter"
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-flash"
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    session_secret: str | None = None
    credential_encryption_key: str | None = None
    recording_retention_days: int = 30
    # Keep the dashboard host aligned with the local API host.  `localhost`
    # and `127.0.0.1` are distinct browser sites, so mixing them prevents the
    # browser from sending the signed session cookie to `/auth/me`.
    dashboard_url: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
