"""Shared migration helpers."""
from __future__ import annotations

from alembic import op


def lock_down(tables: list[str]) -> None:
    """Supabase Data API lockdown for new tables: RLS on with no policies, and
    the anon/authenticated roles lose their grants. The app connects as the
    table owner, so it is unaffected. No-op on SQLite / non-Supabase Postgres
    (roles absent). Same rule as app.database.lock_down_postgres."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    roles = [r for (r,) in bind.exec_driver_sql(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
    )]
    for table in tables:
        bind.exec_driver_sql(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        for role in roles:
            bind.exec_driver_sql(f'REVOKE ALL ON TABLE public."{table}" FROM {role}')
