"""Alembic environment: async engine built exactly like the app's (same URL
normalisation, SSL and pooler handling — see app/database.py)."""
from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.database import _CONNECT_ARGS, DATABASE_URL, Base

target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite needs batch ALTERs
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=_CONNECT_ARGS)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
        await conn.commit()
    await engine.dispose()


asyncio.run(_main())
