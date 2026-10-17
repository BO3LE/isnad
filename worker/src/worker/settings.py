from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from adapters.factory import AdapterSettings


class WorkerSettings(BaseSettings):
    # An empty variable (`LLM_MODEL=` in .env, `${X:-}` in compose) counts as unset, not as "".
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: str = "postgresql://postgres:postgres@localhost:5432/gp"
    redis_url: str = "redis://localhost:6379/0"
    fake_adapters: bool = True
    storage_root: str = "/data/artifacts"
    public_files_url: str = "http://localhost:8000/files"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    search_api_key: str | None = None  # a secret — never log it
    # The Researcher's search. Only read when FAKE_ADAPTERS=false: tavily (needs SEARCH_API_KEY) or
    # fake (made-up sources). Unset: tavily if SEARCH_API_KEY is set, else each Researcher step fails.
    search_provider: Literal["tavily", "fake"] | None = None
    # The LLM (Writer). Only read when FAKE_ADAPTERS=false. LLM_PROVIDER: local (LM Studio or Ollama,
    # the default), openai, openrouter, or fake. See adapters/llm/openai_compatible.py.
    llm_provider: Literal["local", "openai", "openrouter", "fake"] | None = None
    llm_base_url: str | None = None  # overrides the provider's default URL
    llm_local_base_url: str = "http://localhost:1234/v1"  # LM Studio; compose points it at the host
    llm_model: str | None = None
    llm_api_key: str | None = None  # a secret — never log it
    openrouter_api_key: str | None = None  # a secret — never log it
    llm_structured: Literal["json_schema", "json_object", "none"] = "json_schema"
    llm_timeout_s: float = 300.0
    llm_max_output_tokens: int = 4096
    llm_temperature: float | None = None
    llm_stream: bool = True
    # "local" writes to STORAGE_ROOT (development); "supabase" uploads to the private bucket
    # STORAGE_BUCKET with the service key (production). A secret — never log it.
    storage_backend: Literal["local", "supabase"] = "local"
    storage_bucket: str = "artifacts"
    supabase_url: str = ""
    supabase_service_key: str | None = None
    # Email, FAKE_ADAPTERS=false only: gmail (each Email step's Google account) or smtp (this server's
    # SMTP — Mailpit under docker compose, which catches every message at http://localhost:8025).
    email_transport: Literal["gmail", "smtp"] = "gmail"
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None  # a secret — never log it
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    email_from: str = "ISNAD <isnad@localhost>"
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
        search_api_key=settings.search_api_key,
        search_provider=settings.search_provider,
        llm_provider=settings.llm_provider,
        llm_base_url=settings.llm_base_url,
        llm_local_base_url=settings.llm_local_base_url,
        llm_model=settings.llm_model,
        llm_api_key=settings.llm_api_key,
        openrouter_api_key=settings.openrouter_api_key,
        llm_structured=settings.llm_structured,
        llm_timeout_s=settings.llm_timeout_s,
        llm_max_output_tokens=settings.llm_max_output_tokens,
        llm_temperature=settings.llm_temperature,
        llm_stream=settings.llm_stream,
        storage_backend=settings.storage_backend,
        supabase_url=settings.supabase_url or None,
        supabase_service_key=settings.supabase_service_key,
        storage_bucket=settings.storage_bucket,
        email_transport=settings.email_transport,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_username=settings.smtp_username,
        smtp_password=settings.smtp_password,
        smtp_starttls=settings.smtp_starttls,
        smtp_ssl=settings.smtp_ssl,
        email_from=settings.email_from,
    )


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
