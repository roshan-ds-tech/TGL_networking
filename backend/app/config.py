"""Application settings.

Every secret comes from the environment. The app refuses to boot in production
with an unsafe or missing SECRET_KEY rather than silently using a default.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
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

    # Origin(s) of the public marketing site, for CORS on the register and
    # availability endpoints. Accepts a comma-separated list so the deployed site
    # and a local dev server can both be allowed, e.g.
    #   PUBLIC_ORIGIN="https://tglwebsite.vercel.app,http://localhost:5173"
    # Always an explicit allowlist — "*" is deliberately not supported.
    public_origin: str = "http://localhost:5173"

    # Built admin SPA; served same-origin by this app so cookies stay SameSite=Strict.
    admin_dist_dir: str = "./static/admin"

    session_hours: int = 12
    max_upload_bytes: int = 2 * 1024 * 1024  # 2 MB — caps worst-case disk use on free-tier hosting

    # Season capacity. Drives the public "x of 40 slots filled" counters and the
    # admin dashboard's early-bird thresholds.
    slots_per_category: int = 40

    # Registrations are refused from this instant onward. The offset is explicit
    # (IST, where the event is held) so it means the same moment no matter what
    # timezone the server runs in — a bare "2026-11-20T23:59:59" would close at
    # a different real-world time on a UTC host than on an IST one.
    registration_closes_at: datetime = datetime(
        2026, 11, 20, 23, 59, 59, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )

    # Brute-force controls
    login_max_attempts: int = 5
    login_window_seconds: int = 900  # 15 min
    register_max_per_hour: int = 10

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def registration_open(self) -> bool:
        """False once the deadline has passed. Pydantic parses an env override
        without an offset as naive, so treat that as IST rather than guessing."""
        closes = self.registration_closes_at
        if closes.tzinfo is None:
            closes = closes.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
        return datetime.now(timezone.utc) < closes

    @property
    def public_origins(self) -> list[str]:
        """`public_origin` split into the list CORSMiddleware expects."""
        origins = [o.strip().rstrip("/") for o in self.public_origin.split(",")]
        return [o for o in origins if o and o != "*"]

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
