"""Application settings.

Every secret comes from the environment. The app refuses to boot in production
with an unsafe or missing SECRET_KEY rather than silently using a default.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
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

    # Optional CA bundle for verifying the Postgres server certificate
    # (Supabase: Project Settings -> Database -> SSL -> download certificate).
    # Unset, Supabase connections are encrypted but not CA-verified.
    database_ssl_root_cert: str = ""

    # Create/patch tables at app startup. Development and tests only; when
    # unset it is on outside production. Production migrates at deploy time
    # instead (python -m app.migrate) so startup does no schema work.
    auto_create_schema: bool | None = None

    # Cache prepared statements per connection (one round trip per query
    # instead of two). Forced off for Supabase's transaction pooler (6543).
    db_statement_cache: bool = True
    # Ping each pooled connection before use (+1 round trip per request).
    db_pool_pre_ping: bool = False

    # Open a fresh DB connection per checkout instead of pooling. For test
    # harnesses that run the app across several event loops; production keeps
    # the pool.
    db_null_pool: bool = False

    # Screenshots live here, deliberately OUTSIDE any statically served directory.
    upload_dir: str = "./var/uploads"

    # Origin(s) of the public marketing site, for CORS on the register and
    # availability endpoints. Accepts a comma-separated list so the deployed site
    # and a local dev server can both be allowed, e.g.
    #   PUBLIC_ORIGIN="https://tglwebsite.vercel.app,http://localhost:5173"
    # Always an explicit allowlist — "*" is deliberately not supported.
    public_origin: str = "http://localhost:5173"
    # Set automatically by Render on every web service (its onrender.com URL).
    # Used as the public origin when PUBLIC_ORIGIN is left empty, so a first
    # deploy works before a custom domain exists — no placeholder needed.
    render_external_url: str = ""

    # Built admin SPA; served same-origin by this app so cookies stay SameSite=Strict.
    admin_dist_dir: str = "./static/admin"

    # Built public site + member app (the repo-root `npm run build` output).
    # When the directory exists this app serves it too, so the whole product
    # is one origin: session cookies stay SameSite=Strict and no CORS is
    # involved. Absent in local dev, where Vite serves the site instead.
    site_dist_dir: str = "./static/site"

    # Payment-proof storage: "local" (upload_dir on disk) or "supabase" (a
    # private Supabase Storage bucket — production on Render, which has no
    # persistent disk by default).
    storage_backend: str = "local"
    supabase_url: str = ""
    # Server-side only. Never exposed to the browser or committed.
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "payment-proofs"

    # Must be >= the 24h email-verification token lifetime (see services.py /
    # customer.py register()) — otherwise a user's session can expire before
    # their still-valid verification token, leaving them stuck.
    session_hours: int = 24
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

    # How many reverse proxies sit in front of the app and append to
    # X-Forwarded-For (Render: 1). 0 ignores the header — the right setting
    # when nothing trusted is in front, since the header is client-supplied.
    trusted_proxy_hops: int = 0

    # Brute-force controls
    login_max_attempts: int = 5
    login_window_seconds: int = 900  # 15 min
    register_max_per_hour: int = 10

    # Resend (https://resend.com) — free-tier transactional email for signup
    # verification codes. Empty means "don't send" (dev falls back to
    # returning the code in the API response; production just has no way to
    # verify).
    resend_api_key: str = ""
    email_from: str = "TGL <tgl@skykeen.in>"
    resend_api_url: str = "https://api.resend.com/emails"

    # Read-only copy of event registrations from the legacy system (the
    # PythonAnywhere backend that tgl.skykeen.in posts to). Unset = disabled.
    # Use a dedicated admin account there; it is only used to read the list.
    legacy_registrations_url: str = ""
    legacy_admin_email: str = ""
    legacy_admin_password: str = ""
    legacy_sync_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def expose_dev_codes(self) -> bool:
        """Return signup/login codes in the API response (and so let the SPA
        pre-fill them) only when they cannot be emailed: local dev without a
        RESEND_API_KEY. Once email is configured the code must come from the
        inbox, even in development — otherwise verification proves nothing."""
        return not self.is_production and not self.resend_api_key

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

    @model_validator(mode="after")
    def _validate_storage(self) -> "Settings":
        if self.auto_create_schema is None:
            self.auto_create_schema = not self.is_production
        if not self.public_origin.strip() or "public_origin" not in self.model_fields_set:
            if self.render_external_url.strip():
                self.public_origin = self.render_external_url.strip()
        self.storage_backend = self.storage_backend.lower().strip()
        if self.storage_backend not in {"local", "supabase"}:
            raise ValueError('STORAGE_BACKEND must be "local" or "supabase".')
        if self.storage_backend == "supabase" and not (self.supabase_url and self.supabase_service_role_key):
            raise ValueError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        if self.is_production and self.storage_backend == "supabase" and self.database_url.startswith("sqlite"):
            # The Render deployment (no persistent disk): a missing DATABASE_URL
            # would otherwise fall back to SQLite inside the container and every
            # record would silently vanish on the next deploy or restart.
            raise ValueError(
                "DATABASE_URL must point at Supabase Postgres in production — refusing to "
                "store records in a local SQLite file on an ephemeral filesystem."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
