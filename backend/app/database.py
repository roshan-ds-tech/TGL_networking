"""Async SQLAlchemy engine/session wiring.

SQLite is put into WAL mode (settings.sqlite_wal) so reads never block the
writer — that keeps the dashboard responsive while registrations are coming
in. WAL is skipped when settings.sqlite_wal is false, for hosts whose disk
doesn't support the shared-memory locking WAL depends on (see config.py).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from pathlib import Path

import ssl
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from .config import settings


def _normalise_url(raw: str) -> tuple[str, dict]:
    """Accept a Postgres URL exactly as Supabase/Render hand it out.

    * postgres:// and postgresql:// become postgresql+asyncpg:// (the async
      driver this app uses).
    * libpq-only query params (sslmode, ...) are not understood by asyncpg;
      sslmode is translated into an SSL context instead and the rest dropped.
    """
    if raw.startswith("sqlite"):
        return raw, {}
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            raw = "postgresql+asyncpg://" + raw[len(prefix):]
    # Passwords pasted straight from a dashboard often contain '@', ':' or
    # '!' unencoded. The host starts after the LAST '@', so percent-encode
    # the credentials before parsing rather than mis-splitting them.
    scheme, sep, rest = raw.partition("://")
    authority, slash, tail = rest.partition("/")
    if authority.count("@") > 1 or ("@" in authority and any(c in authority.rpartition("@")[0] for c in "!#?[]")):
        creds, _, hostport = authority.rpartition("@")
        user, colon, password = creds.partition(":")
        creds = quote(unquote(user), safe="") + (colon + quote(unquote(password), safe="") if colon else "")
        raw = f"{scheme}{sep}{creds}@{hostport}{slash}{tail}"
    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query))
    sslmode = query.pop("sslmode", None)
    for libpq_only in ("channel_binding", "gssencmode", "target_session_attrs"):
        query.pop(libpq_only, None)
    # Prepared-statement caching. Without it asyncpg prepares every query
    # afresh — an extra network round trip per query (measured: a single
    # SELECT cost 2 round trips, ~183 ms Render->Supabase). The session pooler
    # (port 5432) and direct connections keep one server connection per
    # client connection, so cached statements are safe there. Supabase's
    # TRANSACTION pooler (port 6543) hands each transaction a different server
    # connection, so caching must stay off for it.
    transaction_pooler = parts.port == 6543
    use_cache = settings.db_statement_cache and not transaction_pooler
    connect_args: dict = {} if use_cache else {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
    host = parts.hostname or ""
    root_cert = query.pop("sslrootcert", None) or settings.database_ssl_root_cert
    if host.endswith((".supabase.co", ".supabase.com")) and sslmode is None:
        # Supabase's documented default. Its certificates chain to Supabase's
        # own root CA, which is not in public trust stores — so full
        # verification needs that CA file (DATABASE_SSL_ROOT_CERT).
        sslmode = "verify-full" if root_cert else "require"
    if sslmode in {"require", "verify-ca", "verify-full"}:
        ctx = ssl.create_default_context(cafile=root_cert) if root_cert else ssl.create_default_context()
        if sslmode == "require":
            # libpq "require": always encrypted, certificate not verified.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif sslmode == "verify-ca":
            ctx.check_hostname = False
        connect_args["ssl"] = ctx
    return urlunsplit(parts._replace(query=urlencode(query))), connect_args


DATABASE_URL, _CONNECT_ARGS = _normalise_url(settings.database_url)
is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # SQLite will not create missing parent directories for the database file,
    # so ensure they exist before the first connection is attempted.
    _db_path = settings.database_url.split("///", 1)[-1]
    if _db_path and _db_path != ":memory:":
        Path(_db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

if settings.db_null_pool:
    _pool_args: dict = {"poolclass": NullPool}
elif is_sqlite:
    _pool_args = {}  # SQLite's async driver ignores pool sizing
else:
    # Kept small on purpose: a hosted Postgres (Supabase) caps connections
    # per project, and one web instance doesn't need more than this.
    _pool_args = {"pool_size": 5, "max_overflow": 5, "pool_recycle": 240, "pool_timeout": 10}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    # Pre-ping costs a full network round trip on every request. Off by
    # default: stale connections are retired by pool_recycle instead, and
    # Render restarts the process (fresh pool) whenever the service wakes.
    pool_pre_ping=settings.db_pool_pre_ping,
    connect_args=_CONNECT_ARGS,
    **_pool_args,
)

if not is_sqlite:
    import time as _time

    from sqlalchemy.exc import DisconnectionError

    _IDLE_PING_SECONDS = 30

    @event.listens_for(engine.sync_engine, "checkin")
    def _mark_idle(dbapi_conn, record):  # pragma: no cover - pool hook
        record.info["tgl_idle_since"] = _time.monotonic()

    @event.listens_for(engine.sync_engine, "checkout")
    def _ping_if_idle(dbapi_conn, record, proxy):  # pragma: no cover - pool hook
        """Ping only connections that sat idle for a while — the ones a pooler
        may have dropped. Busy connections skip the extra round trip."""
        if settings.db_pool_pre_ping:
            return  # the always-ping mode already covers it
        idle_since = record.info.get("tgl_idle_since")
        if idle_since is not None and _time.monotonic() - idle_since > _IDLE_PING_SECONDS:
            try:
                dbapi_conn.ping()
            except Exception as exc:
                raise DisconnectionError() from exc  # pool replaces it and retries


if is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        if settings.sqlite_wal:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
        else:
            # Default rollback journal: slower under concurrent access, but
            # doesn't depend on the mmap/shared-memory locking that hangs on
            # network filesystems. synchronous=FULL is the safe pairing for it.
            cur.execute("PRAGMA journal_mode=DELETE")
            cur.execute("PRAGMA synchronous=FULL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Per-request DB time and query count (observability.py).
from .observability import install_db_timing  # noqa: E402

install_db_timing(engine)


class Base(DeclarativeBase):
    pass


# Columns added to a table after its first release.
#
# There is no migration tool here, and create_all() only creates missing
# *tables* — it will never alter one that already exists. Deploying a new model
# column against a database that already holds rows would therefore leave every
# query failing with "no such column". sync_schema() closes that gap.
#
# Each value is the SQL literal existing rows should get. None means the column
# is nullable and pre-existing rows can simply hold NULL; anything else is a
# NOT NULL column, and the literal both backfills the old rows and satisfies
# the constraint while ALTER TABLE runs. Requiring the field for *new*
# submissions is the API schema's job, not the database's.
#
# Types are not listed: they are read off the model at run time, so a column
# can never be added here with a type that drifts from the one create_all()
# would have produced — and so the DDL is correct on both SQLite and Postgres.
_ADDED_COLUMNS: dict[str, dict[str, str | None]] = {
    # Phase 2 (migration 0011): a development database created before it gets the columns here, so the admin Subscriptions view and the
    # renewal flow work without running Alembic. Existing invoices have no points discount.
    "subscriptions": {"renews_subscription_id": None},
    # Phase A (migration 0013): the need lifecycle. All nullable: a need that predates it stays valid and is simply an OPEN, legacy need.
    "business_needs": {"published_at": None, "resolved_at": None, "cancelled_at": None, "removed_at": None, "removed_by_admin_id": None, "removed_reason": None,
                       "resolved_offer_id": None, "title_hash": None, "description_hash": None, "publish_month_key": None, "qualifies_for_future_reward": None, "quality_note": None},
    "invoices": {"points_redeemed": "0", "points_discount_minor": "0"},
    "registrations": {
        "source": "'local'",
        # Nullable bridge fields for authenticated P0 registrations. Legacy
        # public registrations stay valid; new product registrations point to
        # the customer/user-owned event-registration domain.
        "user_id": None,
        "business_id": None,
        "event_registration_id": None,
    },
    "user_verification_tokens": {
        # Added when passwordless login and password reset joined signup on
        # this table. Every token that predates the split was a signup code.
        "purpose": "'EMAIL_VERIFY'",
    },
    "notifications": {
        "actor_user_id": None,
    },
    "users": {
        "photo_key": None,
        "full_name": None,
        "phone": None,
    },
    "connections": {
        # Request lifecycle (PENDING / ACCEPTED / DECLINED). Every request made
        # before it existed was, by definition, still pending.
        "status": "'PENDING'",
        "responded_at": None,
        "pair_key": None,                      # Phase A (migration 0013); rows that predate it keep NULL
    },
    "business_referrals": {
        # Prospect snapshot, opportunity context and lifecycle stamps (migration
        # 0006). All nullable: referrals made before it simply have none.
        "contacted_at": None,
        "closed_at": None,
        "prospect_name": None,
        "prospect_phone": None,
        "prospect_email": None,
        "prospect_company": None,
        "prospect_role": None,
        "prospect_location": None,
        "preferred_contact_method": None,
        "relationship": None,
        "relationship_other": None,
        "opportunity_description": None,
        "category": None,
        "urgency": None,
        "value_range": None,
        "intro_method": None,
        "intro_call_preference": None,
        "contact_permission": None,
        "consent_confirmed_at": None,
        "quality": None,
        "last_action_at": None,
        # Admin review marker (Phase 0). Existing referrals start unflagged.
        "flagged": "false",
        "flag_reason": None,
        "flagged_at": None,
        "flagged_by": None,
    },
    "businesses": {
        # KYB submission workflow, added after the tgl_verified badge it sets.
        # Businesses that predate it have, correctly, not started it.
        "verification_status": "'NOT_STARTED'",
        "verification_submitted_at": None,
    },
}


def sync_schema(sync_conn) -> None:
    """Add model columns the live database is missing. Safe to run every boot.

    Idempotent by construction — it inspects what is actually there first, so
    reloading the app repeatedly is a no-op once the column exists. Table and
    column names come from the constant above (our own source), never from
    request data, so interpolating them into the DDL is safe.
    """
    inspector = inspect(sync_conn)
    for table, backfills in _ADDED_COLUMNS.items():
        if not inspector.has_table(table):
            continue  # create_all() just made it, already with every column
        model_table = Base.metadata.tables[table]
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, backfill in backfills.items():
            if name in existing:
                continue
            column = model_table.columns[name]
            ddl = f"ALTER TABLE {table} ADD COLUMN {name} {column.type.compile(sync_conn.dialect)}"
            if backfill is not None:
                ddl += f" NOT NULL DEFAULT {backfill}"
            sync_conn.exec_driver_sql(ddl)
    _sync_referral_indexes(sync_conn, inspector)
    _sync_connections(sync_conn, inspector)
    _sync_subscription_indexes(sync_conn, inspector)
    _sync_need_indexes(sync_conn, inspector)


def _sync_subscription_indexes(sync_conn, inspector) -> None:
    """Development databases: make the live-subscription indexes the Phase 2 shape (an early renewal may coexist with the running term)."""
    fresh = inspect(sync_conn)                           # the inspector above predates the ALTER TABLE that added the column
    if not fresh.has_table("subscriptions") or "renews_subscription_id" not in {c["name"] for c in fresh.get_columns("subscriptions")}:
        return
    dialect = sync_conn.dialect.name
    if dialect == "sqlite":
        row = sync_conn.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'uq_subscription_live_user'").first()
    elif dialect == "postgresql":
        row = sync_conn.exec_driver_sql("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_subscription_live_user'").first()
    else:
        return
    if row is not None and "renews_subscription_id" not in (row[0] or ""):
        sync_conn.exec_driver_sql("DROP INDEX uq_subscription_live_user")
        row = None
    if row is None:
        sync_conn.exec_driver_sql("CREATE UNIQUE INDEX uq_subscription_live_user ON subscriptions (user_id) WHERE status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NULL")
    sync_conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_live_renewal ON subscriptions (renews_subscription_id) WHERE status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NOT NULL")


def install_audit_triggers(sync_conn) -> None:
    """Make audit_log append-only at the database level (idempotent, safe every boot).

    The application never updates or deletes audit rows, and an ORM guard refuses to;
    these triggers close the remaining gap: raw SQL, a bug, or a mistaken script.
    They apply to SQLite and Postgres, the two engines this project runs on."""
    dialect = sync_conn.dialect.name
    if dialect == "sqlite":
        for name, op in (("audit_log_no_update", "UPDATE"), ("audit_log_no_delete", "DELETE")):
            sync_conn.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op} ON audit_log "
                "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
            )
    elif dialect == "postgresql":
        sync_conn.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION tgl_audit_log_immutable() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql"
        )
        sync_conn.exec_driver_sql("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log")
        sync_conn.exec_driver_sql(
            "CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION tgl_audit_log_immutable()"
        )
        sync_conn.exec_driver_sql("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
        sync_conn.exec_driver_sql(
            "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION tgl_audit_log_immutable()"
        )


def install_ledger_triggers(sync_conn) -> None:
    """Make the shadow ledger and the shadow renewal records append-only at the database level (idempotent, safe every boot), exactly as
    audit_log is. They are the record every later number is explained from: never edited, only added to."""
    dialect = sync_conn.dialect.name
    tables = ("growth_point_ledger", "growth_point_renewals", "growth_point_redemptions", "growth_point_redemption_lots", "growth_point_controls", "growth_point_redemption_epoch")
    from sqlalchemy import inspect as _inspect
    existing = set(_inspect(sync_conn).get_table_names())
    tables = tuple(t for t in tables if t in existing)
    if dialect == "sqlite":
        for t in tables:
            for name, op in ((f"{t}_no_update", "UPDATE"), (f"{t}_no_delete", "DELETE")):
                sync_conn.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op} ON {t} BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END"
                )
    elif dialect == "postgresql" and tables:
        sync_conn.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION tgl_gp_ledger_immutable() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'growth point history is append-only'; END; $$ LANGUAGE plpgsql"
        )
        for t in tables:
            sync_conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {t}_no_change ON {t}")
            sync_conn.exec_driver_sql(f"CREATE TRIGGER {t}_no_change BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION tgl_gp_ledger_immutable()")
            sync_conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
            sync_conn.exec_driver_sql(f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} FOR EACH STATEMENT EXECUTE FUNCTION tgl_gp_ledger_immutable()")


def _sync_need_indexes(sync_conn, inspector) -> None:
    """Phase A: the live-need unique index on a pre-0013 development table (create_all builds indexes only with a new table)."""
    fresh = inspect(sync_conn)
    if not fresh.has_table("business_needs") or "title_hash" not in {c["name"] for c in fresh.get_columns("business_needs")}:
        return
    have = {i["name"] for i in fresh.get_indexes("business_needs")}
    for index in Base.metadata.tables["business_needs"].indexes:
        if index.name not in have and index.name.startswith("uq_need_"):
            index.create(sync_conn)


def install_community_triggers(sync_conn) -> None:
    """Make the Phase A community history append-only at the database level (idempotent, safe every boot), exactly as the ledger and the audit log are."""
    from sqlalchemy import inspect as _inspect
    if "community_events" not in set(_inspect(sync_conn).get_table_names()):
        return
    dialect = sync_conn.dialect.name
    if dialect == "sqlite":
        for name, op in (("community_events_no_update", "UPDATE"), ("community_events_no_delete", "DELETE")):
            sync_conn.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op} ON community_events BEGIN SELECT RAISE(ABORT, 'community_events is append-only'); END")
    elif dialect == "postgresql":
        sync_conn.exec_driver_sql("CREATE OR REPLACE FUNCTION tgl_community_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'community activity history is append-only'; END; $$ LANGUAGE plpgsql")
        sync_conn.exec_driver_sql("DROP TRIGGER IF EXISTS community_events_no_change ON community_events")
        sync_conn.exec_driver_sql("CREATE TRIGGER community_events_no_change BEFORE UPDATE OR DELETE ON community_events FOR EACH ROW EXECUTE FUNCTION tgl_community_immutable()")
        sync_conn.exec_driver_sql("DROP TRIGGER IF EXISTS community_events_no_truncate ON community_events")
        sync_conn.exec_driver_sql("CREATE TRIGGER community_events_no_truncate BEFORE TRUNCATE ON community_events FOR EACH STATEMENT EXECUTE FUNCTION tgl_community_immutable()")


def _sync_connections(sync_conn, inspector) -> None:
    """Two members who each asked the other are connected: accept both rows.
    Needed once for requests made before accepting existed (migration 0007 does
    the same in production), and harmless afterwards - the API never leaves a
    mutual pair pending."""
    if not inspector.has_table("connections"):
        return
    sync_conn.exec_driver_sql(
        "UPDATE connections SET status = 'ACCEPTED', responded_at = CURRENT_TIMESTAMP "
        "WHERE status = 'PENDING' AND EXISTS ("
        "SELECT 1 FROM connections r WHERE r.requester_user_id = connections.target_user_id "
        "AND r.target_user_id = connections.requester_user_id)"
    )
    # Phase A: the live-pair unique index on a pre-0013 development table (create_all builds indexes only with a new table). It covers only rows that
    # carry a pair_key, so existing rows, including any legacy mutual pair, can never make it fail.
    fresh = inspect(sync_conn)
    if "pair_key" in {c["name"] for c in fresh.get_columns("connections")}:
        have = {i["name"] for i in fresh.get_indexes("connections")}
        for index in Base.metadata.tables["connections"].indexes:
            if index.name not in have:
                index.create(sync_conn)


def _sync_referral_indexes(sync_conn, inspector) -> None:
    """Bring a pre-0006 local business_referrals table up to the model, the way
    migration 0006 does in production: the composite/partial indexes (including
    the unique one that stops a double-click creating two live referrals) and the
    last_action_at backfill. create_all() builds these only with a new table."""
    table_name = "business_referrals"
    if not inspector.has_table(table_name):
        return
    have = {i["name"] for i in inspector.get_indexes(table_name)}
    for index in Base.metadata.tables[table_name].indexes:
        if index.name not in have:
            index.create(sync_conn)
    sync_conn.exec_driver_sql(
        f"UPDATE {table_name} SET last_action_at = updated_at WHERE last_action_at IS NULL"
    )


def lock_down_postgres(sync_conn) -> None:
    """Close Supabase's auto-generated Data API over every app table.

    Supabase exposes tables in `public` through PostgREST/GraphQL to anyone
    holding the project's *public* anon key. This app never uses that API: the
    backend connects as the table owner, which bypasses RLS. So every table
    gets RLS enabled with NO policies (deny-all for anon/authenticated), and
    those roles lose their table grants as a second layer. Idempotent; runs
    every boot so tables added later are covered too. A no-op on SQLite and on
    a plain Postgres without Supabase's roles.
    """
    if sync_conn.dialect.name != "postgresql":
        return
    api_roles = [
        r for (r,) in sync_conn.exec_driver_sql(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
        )
    ]
    for table in Base.metadata.tables:
        # Names come from our own model metadata, never from request data.
        sync_conn.exec_driver_sql(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        for role in api_roles:
            sync_conn.exec_driver_sql(f'REVOKE ALL ON TABLE public."{table}" FROM {role}')


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def init_db_sync() -> None:
    """Create tables and the upload directory from a synchronous context.

    ASGI servers get this via the app's lifespan handler. WSGI-only hosts
    (PythonAnywhere's free tier, via a2wsgi) never run lifespan at all, so
    without this the first request fails with "no such table: admins".

    The engine is disposed afterwards on purpose: this runs in a throwaway
    event loop, and pooled connections bound to it must not leak into the
    long-lived loop that actually serves requests.
    """
    import asyncio

    # Importing models is what registers them on Base.metadata. Without this,
    # create_all() silently creates nothing when init_db_sync() is called
    # before the rest of the app has been imported (as the WSGI entrypoint
    # does), and every request then fails with "no such table".
    from . import models  # noqa: F401
    from .storage import init_storage

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(sync_schema)
            await conn.run_sync(lock_down_postgres)
        await engine.dispose()

    async def _boot() -> None:
        await init_storage()
        await _create()

    asyncio.run(_boot())
