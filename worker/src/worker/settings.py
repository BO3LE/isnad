from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from adapters.factory import AdapterSettings


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
    mailtrap_api_token: str | None = None
    mail_from_email: str | None = None
    # "local" writes to STORAGE_ROOT (development); "supabase" uploads to the private bucket
    # STORAGE_BUCKET with the service key (production). A secret — never log it.
    storage_backend: Literal["local", "supabase"] = "local"
    storage_bucket: str = "artifacts"
    supabase_url: str = ""
    supabase_service_key: str | None = None
    # D-09: Google connections. Only read when FAKE_ADAPTERS=false and a node names an account.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    credentials_encryption_key: str | None = None


def adapter_settings(settings: WorkerSettings) -> AdapterSettings:
    """The one place worker settings become adapter settings."""
    return AdapterSettings(
        fake=settings.fake_adapters,
        storage_root=settings.storage_root,
        public_base_url=settings.public_files_url,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        openai_base_url=settings.openai_base_url,
        search_api_key=settings.search_api_key,
        cloudflare_account_id=settings.cloudflare_account_id,
        cloudflare_api_token=settings.cloudflare_api_token,
        mailtrap_api_token=settings.mailtrap_api_token,
        mail_from_email=settings.mail_from_email,
        storage_backend=settings.storage_backend,
        supabase_url=settings.supabase_url or None,
        supabase_service_key=settings.supabase_service_key,
        storage_bucket=settings.storage_bucket,
    )


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
