from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/gp"
    redis_url: str = "redis://localhost:6379/0"

    # HS256 secret for POST /auth/dev-login tokens only. Supabase-issued tokens are verified via
    # JWKS instead (see api/auth.py) — this never needs to match anything on Supabase's side.
    jwt_secret: str = "change-me-in-.env-at-least-32-characters-long"
    jwt_audience: str = "authenticated"
    jwt_expiry_minutes: int = 60 * 24 * 7
    enable_dev_login: bool = True

    # D-01: the isnad Supabase project. Only used to build the JWKS URL for verifying its tokens.
    supabase_url: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]
    storage_root: str = "/data/artifacts"
    public_files_url: str = "http://localhost:8000/files"

    @property
    def dev_login_allowed(self) -> bool:
        return self.enable_dev_login and self.environment != "production"


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()
