"""Copy TGL from one Supabase project to another (e.g. Mumbai -> Singapore).

Credentials come from the environment only — never pass them as arguments:

    OLD_DATABASE_URL, OLD_SUPABASE_URL, OLD_SUPABASE_SERVICE_ROLE_KEY
    NEW_DATABASE_URL, NEW_SUPABASE_URL, NEW_SUPABASE_SERVICE_ROLE_KEY

    python scripts/move_supabase.py            # dry run: counts only, writes nothing
    python scripts/move_supabase.py --apply    # copy

What it does (with --apply):
  1. builds the schema on the NEW database with the app's migrations
     (python -m app.migrate: tables, RLS lockdown, private proof bucket);
  2. copies every table's rows in dependency order — INSERT ... ON CONFLICT DO
     NOTHING, so it never overwrites or deletes anything and is safe to re-run
     (run it again right after switching Render over to catch late writes);
  3. copies every payment-proof file bucket -> bucket (skips files already there);
  4. verifies row counts and file counts match, and exits non-zero if not.

The OLD project is only ever read.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402
import httpx  # noqa: E402

# Parent tables before children. registrations <-> event_registrations
# reference each other; registrations.event_registration_id is filled in a
# second pass once both tables are populated.
TABLES = [
    "admins", "events", "users", "personal_profiles", "businesses", "user_verification_tokens",
    "registrations", "event_registrations", "tgl_memberships", "networking_profiles",
    "connections", "referral_requests", "business_referrals", "business_needs", "notifications",
    "email_outbox",
]
CYCLE = ("registrations", "event_registration_id")
BUCKET = "payment-proofs"


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"missing environment variable {name}")
    return value


async def connect(url: str) -> asyncpg.Connection:
    # Same URL handling as the app (pasted Supabase URLs, SSL, poolers).
    os.environ.setdefault("SECRET_KEY", "x" * 48)
    from app.database import _normalise_url

    norm, args = _normalise_url(url)
    dsn = norm.replace("postgresql+asyncpg://", "postgresql://", 1)
    return await asyncpg.connect(dsn, ssl=args.get("ssl"), statement_cache_size=0)


async def primary_key(conn: asyncpg.Connection, table: str) -> list[str]:
    rows = await conn.fetch(
        """SELECT a.attname FROM pg_index i JOIN pg_attribute a
           ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
           WHERE i.indrelid = $1::regclass AND i.indisprimary""",
        f'public."{table}"',
    )
    return [r["attname"] for r in rows]


async def copy_rows(old, new, apply: bool) -> dict[str, tuple[int, int]]:
    counts = {}
    existing_old = {r["tablename"] for r in await old.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    for table in TABLES:
        if table not in existing_old:
            counts[table] = (0, await new.fetchval(f'SELECT count(*) FROM "{table}"') if apply else 0)
            continue
        rows = await old.fetch(f'SELECT * FROM "{table}"')
        if apply and rows:
            cols = list(rows[0].keys())
            pk = await primary_key(new, table)
            values = [list(r.values()) for r in rows]
            if table == CYCLE[0]:
                idx = cols.index(CYCLE[1])
                values = [v[:idx] + [None] + v[idx + 1:] for v in values]  # filled in below
            placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
            col_sql = ", ".join(f'"{c}"' for c in cols)
            await new.executemany(
                f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders}) '
                f'ON CONFLICT ({", ".join(chr(34) + c + chr(34) for c in pk)}) DO NOTHING',
                values,
            )
        counts[table] = (len(rows), await new.fetchval(f'SELECT count(*) FROM "{table}"') if apply else 0)
    if apply:
        links = await old.fetch(f'SELECT id, "{CYCLE[1]}" FROM "{CYCLE[0]}" WHERE "{CYCLE[1]}" IS NOT NULL')
        await new.executemany(
            f'UPDATE "{CYCLE[0]}" SET "{CYCLE[1]}" = $2 WHERE id = $1 AND "{CYCLE[1]}" IS NULL',
            [(r["id"], r[CYCLE[1]]) for r in links],
        )
    return counts


def sb_headers(key: str) -> dict:
    h = {"apikey": key}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    return h


async def list_objects(client: httpx.AsyncClient, base: str, key: str) -> list[str]:
    names, offset = [], 0
    while True:
        r = await client.post(f"{base}/storage/v1/object/list/{BUCKET}",
                              json={"prefix": "", "limit": 1000, "offset": offset}, headers=sb_headers(key))
        r.raise_for_status()
        batch = [o["name"] for o in r.json() if o.get("id")]  # skip folder placeholders
        names += batch
        if len(batch) < 1000:
            return names
        offset += 1000


async def copy_files(apply: bool) -> tuple[int, int]:
    old_base, old_key = env("OLD_SUPABASE_URL").rstrip("/"), env("OLD_SUPABASE_SERVICE_ROLE_KEY")
    new_base, new_key = env("NEW_SUPABASE_URL").rstrip("/"), env("NEW_SUPABASE_SERVICE_ROLE_KEY")
    async with httpx.AsyncClient(timeout=60) as client:
        old_names = await list_objects(client, old_base, old_key)
        if not apply:
            return len(old_names), 0
        have = set(await list_objects(client, new_base, new_key))
        for name in old_names:
            if name in have:
                continue
            got = await client.get(f"{old_base}/storage/v1/object/{BUCKET}/{name}", headers=sb_headers(old_key))
            got.raise_for_status()
            put = await client.post(
                f"{new_base}/storage/v1/object/{BUCKET}/{name}", content=got.content,
                headers={**sb_headers(new_key), "Content-Type": got.headers.get("content-type", "application/octet-stream"), "x-upsert": "false"},
            )
            if put.status_code >= 300 and put.status_code != 409:
                sys.exit(f"upload of {name} failed: HTTP {put.status_code}")
        return len(old_names), len(await list_objects(client, new_base, new_key))


async def main() -> int:
    apply = "--apply" in sys.argv
    print("mode:", "APPLY (writes to the NEW project)" if apply else "DRY RUN (nothing is written)")
    if apply:
        print("1/4 schema on the new database (python -m app.migrate)")
        child_env = {
            **os.environ,
            "ENVIRONMENT": "production",
            "SECRET_KEY": os.environ.get("SECRET_KEY") or "migration-only-" + "x" * 40,
            "DATABASE_URL": env("NEW_DATABASE_URL"),
            "STORAGE_BACKEND": "supabase",
            "SUPABASE_URL": env("NEW_SUPABASE_URL"),
            "SUPABASE_SERVICE_ROLE_KEY": env("NEW_SUPABASE_SERVICE_ROLE_KEY"),
        }
        subprocess.run([sys.executable, "-m", "app.migrate"], cwd=ROOT, env=child_env, check=True)
    old = await connect(env("OLD_DATABASE_URL"))
    new = await connect(env("NEW_DATABASE_URL"))
    try:
        print("2/4 rows")
        counts = await copy_rows(old, new, apply)
    finally:
        await old.close()
        await new.close()
    print("3/4 payment-proof files")
    files_old, files_new = await copy_files(apply)

    print("4/4 verification")
    ok = True
    for table, (n_old, n_new) in counts.items():
        flag = "" if not apply else ("ok" if n_new >= n_old else "MISSING ROWS")
        ok &= (not apply) or n_new >= n_old
        print(f"  {table:26} old={n_old:<6} new={n_new if apply else '-':<6} {flag}")
    fflag = "" if not apply else ("ok" if files_new >= files_old else "MISSING FILES")
    ok &= (not apply) or files_new >= files_old
    print(f"  {'payment-proof files':26} old={files_old:<6} new={files_new if apply else '-':<6} {fflag}")
    print("RESULT:", "OK" if ok else "INCOMPLETE — do not switch over")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
