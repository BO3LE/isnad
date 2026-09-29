from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/gp"
    redis_url: str = "redis://localhost:6379/0"
    fake_adapters: bool = True
    storage_root: str = "/data/artifacts"
    public_files_url: str = "http://localhost:8000/files"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None
    search_api_key: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    mailtrap_api_token: str | None = None
    mail_from_email: str | None = None
    jwt_secret: str = "change-me-in-production"


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
