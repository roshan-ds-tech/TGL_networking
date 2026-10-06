"""Deploy-time database migration: `python -m app.migrate`, run before uvicorn.

    migrate database  ->  start application  ->  serve traffic

The app itself no longer touches the schema in production (see main.py), so a
cold start is no longer dozens of schema round trips before the first request.

Fast path: if the database is already at HEAD — every normal restart and every
Render Free wake-up — this does ONE query and exits without importing Alembic.

Safety:
  * Never drops or rewrites data. Alembic upgrades only move forward.
  * A database created before migrations existed (tables present, no
    alembic_version) is STAMPED at the baseline after checking every baseline
    table is really there; anything unexpected aborts the deploy instead of
    guessing.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from .config import settings
from .database import _CONNECT_ARGS, DATABASE_URL

# Latest revision in migrations/versions. test_production.py asserts this
# matches Alembic's head, so it can't silently drift.
HEAD = "0003"
BASELINE = "0001"
BASELINE_TABLES = {
    "admins", "events", "users", "business_referrals", "businesses", "connections", "notifications",
    "personal_profiles", "referral_requests", "user_verification_tokens", "business_needs",
    "event_registrations", "networking_profiles", "registrations", "tgl_memberships",
}
ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(levelname)s migrate %(message)s")
log = logging.getLogger("tgl.migrate")


async def _state() -> tuple[str | None, set[str]]:
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=_CONNECT_ARGS)
    try:
        async with engine.connect() as conn:
            try:
                version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                return version, set()
            except Exception:
                await conn.rollback()
            tables = set(
                await conn.run_sync(lambda c: __import__("sqlalchemy").inspect(c).get_table_names())
            )
            return None, tables
    finally:
        await engine.dispose()


def _alembic(*args: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    getattr(command, args[0])(cfg, *args[1:])


async def _lock_version_table() -> None:
    """alembic_version is a table in `public` too: keep it out of Supabase's
    Data API like every other table."""
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=_CONNECT_ARGS)
    try:
        async with engine.begin() as conn:
            from .database import lock_down_postgres  # noqa: F401  (same rule)

            if conn.dialect.name == "postgresql":
                roles = [r for (r,) in await conn.execute(text(
                    "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"))]
                await conn.execute(text('ALTER TABLE public."alembic_version" ENABLE ROW LEVEL SECURITY'))
                for role in roles:
                    await conn.execute(text(f'REVOKE ALL ON TABLE public."alembic_version" FROM {role}'))
    finally:
        await engine.dispose()


def main() -> int:
    start = time.perf_counter()
    version, tables = asyncio.run(_state())
    if version == HEAD:
        log.info("schema at %s — nothing to do (%.0f ms)", HEAD, (time.perf_counter() - start) * 1000)
        return 0

    if version is None and tables:
        missing = BASELINE_TABLES - tables
        if missing:
            log.error("database has tables but no migration history, and baseline tables %s are "
                      "missing — refusing to guess. Inspect it before deploying.", sorted(missing))
            return 1
        log.info("existing pre-migration database: stamping baseline %s", BASELINE)
        _alembic("stamp", BASELINE)

    log.info("upgrading schema %s -> %s", version or ("baseline" if tables else "empty"), HEAD)
    _alembic("upgrade", "head")
    asyncio.run(_lock_version_table())

    # Deploy-time (not request-time) check that the private proof bucket exists.
    from .storage import init_storage

    asyncio.run(init_storage())
    log.info("done in %.1f s", time.perf_counter() - start)
    return 0


if __name__ == "__main__":
    if settings.database_url.startswith("sqlite"):
        Path(settings.database_url.split("///", 1)[-1]).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    sys.exit(main())
