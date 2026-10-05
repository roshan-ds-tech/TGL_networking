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
    connect_args: dict = {
        # Supabase's pooler (Supavisor, transaction mode) cannot keep
        # server-side prepared statements between transactions; disabling the
        # statement caches makes the same URL work on the pooler, the session
        # pooler and a direct connection alike.
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
    _pool_args = {"pool_size": 5, "max_overflow": 5, "pool_recycle": 1800}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=_CONNECT_ARGS,
    **_pool_args,
)

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
    "registrations": {
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
        "full_name": None,
        "phone": None,
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
