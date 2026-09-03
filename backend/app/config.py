"""Application settings.

Every secret comes from the environment. The app refuses to boot in production
with an unsafe or missing SECRET_KEY rather than silently using a default.
"""
from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_SENTINEL = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Signing key for session JWTs. MUST be set in production.
    secret_key: str = DEV_SECRET_SENTINEL

    # sqlite+aiosqlite:///./tgl.db  |  postgresql+asyncpg://user:pass@host/db
    database_url: str = "sqlite+aiosqlite:///./var/tgl.db"

    # WAL mode needs proper shared-memory file locking, which network
    # filesystems (notably PythonAnywhere's free-tier home directory, which is
    # NFS-backed) do not support reliably — it silently hangs rather than
    # erroring. Set SQLITE_WAL=false on hosts where the database lives on such
    # storage; safe to leave on (the default) anywhere with a normal local disk.
    sqlite_wal: bool = True

    # Screenshots live here, deliberately OUTSIDE any statically served directory.
    upload_dir: str = "./var/uploads"

    # Origin of the public marketing site (needed for CORS on the register endpoint).
    public_origin: str = "http://localhost:5173"

    # Built admin SPA; served same-origin by this app so cookies stay SameSite=Strict.
    admin_dist_dir: str = "./static/admin"

    session_hours: int = 12
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 MB

    # Brute-force controls
    login_max_attempts: int = 5
    login_window_seconds: int = 900  # 15 min
    register_max_per_hour: int = 10

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cookie_secure(self) -> bool:
        # Secure cookies require HTTPS; disabling in dev keeps localhost usable.
        return self.is_production

    @field_validator("secret_key")
    @classmethod
    def _validate_secret(cls, v: str, info) -> str:
        env = (info.data.get("environment") or "development").lower()
        if env in {"production", "prod"}:
            if not v or v == DEV_SECRET_SENTINEL or len(v) < 32:
                raise ValueError(
                    "SECRET_KEY must be set to a random value of at least 32 chars "
                    "in production. Generate one with: python -c \"import secrets;"
                    "print(secrets.token_urlsafe(48))\""
                )
        return v or secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
