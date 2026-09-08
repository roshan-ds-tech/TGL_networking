"""Async SQLAlchemy engine/session wiring.

SQLite is put into WAL mode (settings.sqlite_wal) so reads never block the
writer — that keeps the dashboard responsive while registrations are coming
in. WAL is skipped when settings.sqlite_wal is false, for hosts whose disk
doesn't support the shared-memory locking WAL depends on (see config.py).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from pathlib import Path

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

is_sqlite = settings.database_url.startswith("sqlite")

if is_sqlite:
    # SQLite will not create missing parent directories for the database file,
    # so ensure they exist before the first connection is attempted.
    _db_path = settings.database_url.split("///", 1)[-1]
    if _db_path and _db_path != ":memory:":
        Path(_db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # SQLite's async driver ignores pool sizing; Postgres benefits from it.
    **({} if is_sqlite else {"pool_size": 10, "max_overflow": 20}),
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
# Every entry must be nullable: rows written before the column existed cannot
# have a value for it. Requiring the field for *new* submissions is the API
# schema's job, not the database's.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "registrations": {
        # UPI reference for the payment, captured alongside the screenshot.
        "utr": "VARCHAR(32)",
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
    for table, columns in _ADDED_COLUMNS.items():
        if not inspector.has_table(table):
            continue  # create_all() just made it, already with every column
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name not in existing:
                sync_conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


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
    from .storage import upload_root

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(sync_schema)
        await engine.dispose()

    upload_root()
    asyncio.run(_create())
