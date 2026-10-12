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


def parse_cutoff(raw: str):
    """The ONE reader of an eligibility cutoff. An ISO-8601 datetime with an explicit offset (or Z); anything else raises ValueError."""
    from datetime import datetime, timezone
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"not an ISO-8601 datetime ({text!r})") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{text!r} has no UTC offset: write it like 2027-01-01T00:00:00+05:30 (a date alone, or a time without an offset, is ambiguous)")
    return moment.astimezone(timezone.utc)


REQUIRED_APPROVALS = frozenset({"MANAGEMENT_MODEL", "ACCOUNTING_GST", "PRODUCTION_BACKUP", "ROLLBACK_TESTED", "MEMBER_TERMS", "MONITORING_OWNER"})


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
    # Members' profile photos: a second private bucket, served only through
    # the API (owner + members with Networking access).
    supabase_photos_bucket: str = "profile-photos"

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

    # FINANCIAL SAFETY GATE (Phase 0). Management must confirm in writing that the
    # Connect / Growth / Elite prices and terms (Rs 3,000 / 3 months, Rs 5,000 / 6 months,
    # Rs 10,000 / 12 months) are correct. No discount or redemption exists today.
    # Code must NEVER read this setting directly: the only sanctioned reader is
    # app/pricing_gate.py (`pricing_confirmed()` / `require_pricing_confirmed()`),
    # and test_phase0.py fails if any other module touches it. Any future feature
    # that lets points reduce an invoice MUST call require_pricing_confirmed().
    subscription_pricing_confirmed: bool = False

    # How a member pays a subscription invoice (bank/UPI details). Plain text shown
    # on the invoice. EMPTY until management supplies the official text: the UI then
    # says instructions are pending and shows no payment details at all.
    subscription_payment_instructions: str = Field(default="", max_length=1000)

    # GROWTH POINTS, PHASE 1 = SHADOW MODE ONLY (app/rewards/). Points are recorded in a shadow ledger and can be inspected,
    # simulated and analysed; they have NO monetary effect: no invoice, payment, subscription or price is read for writing,
    # and no redemption path exists. Only app/rewards/firewall.py reads these two flags.
    #   GROWTH_POINTS_SHADOW_MODE         true  -> reward events are recorded in the shadow ledger (default off: opt in per environment)
    #   GROWTH_POINTS_REDEMPTION_ENABLED  must stay false. The application REFUSES TO START with it true: redemption is not
    #                                     implemented and is a future, separately approved phase (specification gates G1-G5).
    #   GROWTH_POINTS_MEMBER_PREVIEW      true  -> members see a clearly labelled "shadow preview" of their points. Off by default:
    #                                     whether members see it at all is an open management decision.
    growth_points_shadow_mode: bool = False
    growth_points_redemption_enabled: bool = False
    growth_points_member_preview: bool = False

    # PROGRAMME_OWNER_EMAILS: comma-separated emails of the admin accounts that hold the highest-trust role (the programme owners).
    # Only they may approve a Growth Points pair-concentration exception and own the daily reconciliation. The project has no admin
    # roles table, so this is the role: EMPTY BY DEFAULT, which means nobody can approve an exception until it is set deliberately.
    programme_owner_emails: str = ""

    # GROWTH_POINTS_APPROVALS: comma-separated codes of EXTERNAL approvals that a human has recorded (MANAGEMENT_MODEL, ACCOUNTING_GST,
    # PRODUCTION_BACKUP, ROLLBACK_TESTED, MEMBER_TERMS, MONITORING_OWNER). Empty by default. The gates report treats a code as an attestation
    # by whoever set it, never as verified, and nothing is ever inferred as approved.
    growth_points_approvals: str = ""
    # Phase 3 rollout, same backend logic at every stage: "internal" (only the programme owners), "cohort" (owners + GROWTH_POINTS_ROLLOUT_EMAILS), "all".
    growth_points_rollout_stage: str = "internal"
    growth_points_rollout_emails: str = ""
    # THE ELIGIBILITY CUTOFF. Shadow-period points NEVER carry over (management decision, final): only points whose event_at is AT OR AFTER this
    # instant can ever be redeemed (boundary inclusive; compared in UTC). FORMAT: an ISO-8601 datetime WITH an explicit UTC offset or Z, e.g.
    # 2027-01-01T00:00:00+05:30. A bare date or a datetime without an offset is REFUSED at startup (its timezone would be a guess).
    # EMPTY = nothing is redeemable. It is only honoured when it equals the cutoff recorded, once and immutably, in the database
    # (growth_point_redemption_epoch, set by the programme owner after management approval); any mismatch, or a value that can not be read at
    # runtime, means NOTHING is redeemable. Never set it without an officially approved cutoff.
    growth_points_redeemable_from: str = ""
    # DEVELOPMENT / TEST ONLY: lets @demo.example.com demo members run a rolled-back redemption SIMULATION. Same format as above. Refused in production.
    growth_points_demo_cutoff: str = ""

    # Deal-verification thresholds, in whole rupees. AWAITING MANAGEMENT CONFIRMATION:
    # these defaults are engineering assumptions, not approved business rules.
    # deal_thresholds_confirmed records whether management has signed them off; it
    # changes nothing at runtime and is shown to admins so the status is never silent.
    deal_evidence_threshold_inr: int = Field(default=100_000, ge=1)      # evidence required from here
    deal_admin_approval_threshold_inr: int = Field(default=500_000, ge=1)  # an admin must also approve from here
    deal_quick_close_hours: int = Field(default=24, ge=0, le=24 * 30)    # flag closures reported sooner after acceptance
    deal_thresholds_confirmed: bool = False

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
    def _cutoffs_are_unambiguous(self) -> "Settings":
        for name in ("growth_points_redeemable_from", "growth_points_demo_cutoff"):
            raw = getattr(self, name)
            if raw.strip():
                try:
                    parse_cutoff(raw)
                except ValueError as exc:
                    raise ValueError(f"{name.upper()} is invalid: {exc}") from exc
        if self.growth_points_demo_cutoff.strip() and self.environment.strip().lower() == "production":
            raise ValueError("GROWTH_POINTS_DEMO_CUTOFF must be empty in production: the redemption simulation is for development and test only.")
        return self

    def growth_points_approval_codes(self) -> set[str]:
        return {e.strip().upper() for e in self.growth_points_approvals.split(",") if e.strip()}

    def programme_owners(self) -> set[str]:
        return {e.strip().lower() for e in self.programme_owner_emails.split(",") if e.strip()}

    @model_validator(mode="after")
    def _redemption_needs_every_approval(self) -> "Settings":
        """Real redemption can not even be switched on at boot unless every external approval is recorded (an attestation, not a verification;
        the runtime gates, including Gate A and the kill switch, are checked on every redemption as well)."""
        missing = sorted(REQUIRED_APPROVALS - self.growth_points_approval_codes())
        if self.growth_points_redemption_enabled and missing:
            raise ValueError(
                "GROWTH_POINTS_REDEMPTION_ENABLED=true is refused: these approvals are not recorded in GROWTH_POINTS_APPROVALS: " + ", ".join(missing) + "."
            )
        return self

    @model_validator(mode="after")
    def _validate_deal_thresholds(self) -> "Settings":
        if self.deal_admin_approval_threshold_inr < self.deal_evidence_threshold_inr:
            raise ValueError("DEAL_ADMIN_APPROVAL_THRESHOLD_INR must be at least DEAL_EVIDENCE_THRESHOLD_INR.")
        return self

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
