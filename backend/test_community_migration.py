"""Migration 0013 (Phase A community activity): it preserves everything that exists, adds only what it says, backfills history safely and can be undone.

Run:  .venv/bin/python test_community_migration.py          TEST_DATABASE_URL=postgresql+asyncpg://.../scratch .venv/bin/python test_community_migration.py
It needs an EMPTY scratch database (a SQLite temp file by default). It never touches the development database.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TMP = Path(tempfile.mkdtemp(prefix="tgl-mig13-"))
URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{TMP}/mig.db"
PG = URL.startswith("postgresql")
os.environ["DATABASE_URL"] = URL
os.environ.setdefault("ENVIRONMENT", "development")

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


def alembic(*args: str, destructive: bool = False) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": URL}
    if destructive:
        env["TGL_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
    code = "import sys; from app.migrate import _alembic, main; " + ("sys.exit(main())" if not args else f"_alembic{args!r}")
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)


async def q(sql: str, **p):
    eng = create_async_engine(URL, poolclass=NullPool)
    try:
        async with eng.begin() as c:
            res = await c.execute(text(sql), p)
            return res.all() if res.returns_rows else None
    finally:
        await eng.dispose()


def run(sql: str, **p):
    return asyncio.run(q(sql, **p))


def scalar(sql: str, **p):
    r = run(sql, **p)
    return r[0][0] if r else None


async def snapshot(skip: set[str], only_cols: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    eng = create_async_engine(URL, poolclass=NullPool)
    out: dict[str, list[str]] = {}
    try:
        async with eng.connect() as c:
            tables = await c.run_sync(lambda s: inspect(s).get_table_names())
            for t in sorted(set(tables) - skip):
                cols = (only_cols or {}).get(t) or [r["name"] for r in await c.run_sync(lambda s, t=t: inspect(s).get_columns(t))]
                rows = (await c.execute(text(f"SELECT {', '.join(cols)} FROM {t}"))).all()
                out[t] = sorted(hashlib.sha256(repr(r).encode()).hexdigest() for r in rows)
    finally:
        await eng.dispose()
    return out


def main() -> int:
    print(f"Database: {'PostgreSQL' if PG else 'SQLite'}")
    p = alembic("upgrade", "0012")
    assert p.returncode == 0, p.stderr[-800:]
    check("setup: a database at revision 0012 (the state before Phase A)", scalar("select version_num from alembic_version") == "0012")

    # --------------------------------------------------------------- seed what must be preserved
    ts = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    D = lambda d, h: datetime(2026, 3, d, h, 0, tzinfo=timezone.utc)  # noqa: E731
    for i in range(1, 5):
        run("insert into users (id, email, password_hash, is_active, failed_attempts, token_version, created_at, updated_at) values (:i, :e, 'x', :t, 0, 0, :ts, :ts)", i=f"u{i}", e=f"mig{i}@example.com", t=True, ts=ts)
    for i in (1, 2):
        run("insert into businesses (id, user_id, business_name, category, description, city, employee_band, business_age, business_stage, tgl_verified, verification_status, created_at, updated_at) "
            "values (:i, :u, 'Co', '01', 'd', 'Pune', '1-3', 'lt6', 'Early', :f, 'NOT_STARTED', :ts, :ts)", i=f"b{i}", u=f"u{i}", f=False, ts=ts)
    conns = [("c1", "u1", "u2", "PENDING", None), ("c2", "u1", "u3", "ACCEPTED", D(2, 10)), ("c3", "u2", "u3", "DECLINED", D(3, 10)),
             ("c4", "u3", "u4", "ACCEPTED", D(4, 10)), ("c5", "u4", "u3", "ACCEPTED", D(4, 11))]     # c4 + c5: a legacy mutual pair
    for cid, a, b, st, resp in conns:
        run("insert into connections (id, requester_user_id, target_user_id, status, responded_at, created_at) values (:i, :a, :b, :s, :r, :ts)", i=cid, a=a, b=b, s=st, r=resp, ts=ts)
    run("insert into business_needs (id, user_id, business_id, title, category, description, status, created_at, updated_at) values ('n1', 'u1', 'b1', 'Legacy short need', '01', 'old', 'OPEN', :ts, :ts)", ts=ts)
    run("insert into business_needs (id, user_id, business_id, title, category, description, status, created_at, updated_at) values ('n2', 'u1', 'b1', 'Legacy short need', '01', NULL, 'OPEN', :ts, :ts)", ts=ts)
    old_cols = {t: [r[1] if not PG else r[0] for r in (run(f"pragma table_info({t})") if not PG else run("select column_name from information_schema.columns where table_name = :t order by ordinal_position", t=t))] for t in ("connections", "business_needs")}
    ledger_before = scalar("select count(*) from growth_point_ledger")
    before = asyncio.run(snapshot({"alembic_version"}, old_cols))
    check("setup: pre-existing connections (pending, accepted, declined and a legacy mutual pair) and needs are in place", scalar("select count(*) from connections") == 5 and scalar("select count(*) from business_needs") == 2)

    # --------------------------------------------------------------- migrate with the real deploy step
    m = alembic()
    check("the deploy step (python -m app.migrate) succeeds and reaches 0013", m.returncode == 0 and scalar("select version_num from alembic_version") == "0013", m.stderr[-600:])
    after = asyncio.run(snapshot({"alembic_version", "community_events", "need_help_offers"}, old_cols))
    changed = [t for t in before if before[t] != after.get(t)]
    check("EVERY pre-existing row in every pre-existing table is unchanged, for every pre-existing column (users, connections, needs, subscriptions, invoices, payments, ledger, audit)", changed == [], str(changed))
    check("no Growth Points ledger row was created and no cutoff was recorded", scalar("select count(*) from growth_point_ledger") == ledger_before and scalar("select count(*) from growth_point_redemption_epoch") == 0)

    eng_tables = set(r[0] for r in run("select tablename from pg_tables where schemaname = 'public'" if PG else "select name from sqlite_master where type = 'table'"))
    check("the two new tables exist", {"community_events", "need_help_offers"} <= eng_tables)
    cols = lambda t: {r[0] for r in run("select column_name from information_schema.columns where table_name = :t" if PG else f"select name from pragma_table_info('{t}')", t=t)}  # noqa: E731
    check("business_needs gained the twelve lifecycle columns and connections gained pair_key (all nullable additions)", {"published_at", "resolved_at", "cancelled_at", "removed_at", "removed_by_admin_id", "removed_reason", "resolved_offer_id", "title_hash", "description_hash", "publish_month_key", "qualifies_for_future_reward", "quality_note"} <= cols("business_needs") and "pair_key" in cols("connections"))
    idx = lambda t: {r[0] for r in run("select indexname from pg_indexes where tablename = :t" if PG else f"select name from pragma_index_list('{t}')", t=t)}  # noqa: E731
    check("the live-pair and live-need unique indexes exist", "uq_connection_pair_live" in idx("connections") and "uq_need_live_title" in idx("business_needs"))
    check("existing needs: published_at filled from created_at, every other new column NULL (no rewrite of meaning)", scalar("select count(*) from business_needs where published_at is not null and title_hash is null and qualifies_for_future_reward is null and resolved_at is null") == 2)
    check("existing connections keep pair_key NULL (so a legacy mutual pair can never break the new index)", scalar("select count(*) from connections where pair_key is null") == 5)

    # --------------------------------------------------------------- backfilled history
    ev = run("select kind, reason_code, reconnection from community_events order by kind")
    kinds = [k for k, *_ in ev]
    check("history was seeded once from the existing connections: 5 REQUESTED, 2 ACCEPTED (the mutual pair counts once), 1 DECLINED, all marked BACKFILL, none a reconnection",
          kinds.count("REQUESTED") == 5 and kinds.count("ACCEPTED") == 2 and kinds.count("DECLINED") == 1 and all(r == "BACKFILL" for _, r, _ in ev) and not any(x for *_, x in ev))
    check("no event carries a note, name or e-mail", scalar("select count(*) from community_events where details like '%@%'") == 0)

    # --------------------------------------------------------------- constraints behave
    def refused(sql: str, **p) -> bool:
        try:
            run(sql, **p)
            return False
        except Exception:
            return True
    check("the history is append-only at the database (UPDATE and DELETE refused)", refused("update community_events set kind = 'X'") and refused("delete from community_events"))
    ins = "insert into connections (id, requester_user_id, target_user_id, status, created_at, pair_key) values (:i, :a, :b, 'PENDING', :ts, :k)"
    run(ins, i="n-ok", a="u1", b="u4", ts=ts, k="k" * 32)
    check("two live rows for one pair are refused by the database, while legacy NULL rows never interfere", refused(ins, i="n-dup", a="u4", b="u1", ts=ts, k="k" * 32))
    run("delete from connections where id = 'n-ok'")
    tn = "insert into business_needs (id, user_id, business_id, title, category, description, status, created_at, updated_at, title_hash) values (:i, 'u2', 'b2', 't', '01', 'd', :s, :ts, :ts, 'h')"
    run(tn, i="x1", s="OPEN", ts=ts)
    check("two identical live needs from one member are refused; a cancelled one is outside the index", refused(tn, i="x2", s="OPEN", ts=ts) and not refused(tn, i="x3", s="CANCELLED", ts=ts))
    run("delete from business_needs where id in ('x1', 'x3')")
    ok_offer = "insert into need_help_offers (id, need_id, helper_user_id, status, created_at, updated_at) values (:i, 'n1', :h, :s, :ts, :ts)"
    run(ok_offer, i="o1", h="u2", s="OFFERED", ts=ts)
    check("one offer per helper per need, and only the defined statuses are accepted", refused(ok_offer, i="o2", h="u2", s="OFFERED", ts=ts) and refused(ok_offer, i="o3", h="u3", s="MAYBE", ts=ts))
    run("delete from need_help_offers where id = 'o1'")
    if PG:
        no_rls = [t for t in ("community_events", "need_help_offers") if not scalar("select relrowsecurity from pg_class where oid = to_regclass(:t)", t=f"public.{t}")]
        check("row-level security is ON for both new tables (Supabase Data API closed)", no_rls == [], str(no_rls))

    # --------------------------------------------------------------- idempotent, and reversible without loss
    again = alembic()
    check("running the deploy step again changes nothing", again.returncode == 0 and scalar("select version_num from alembic_version") == "0013" and scalar("select count(*) from community_events") == len(ev))
    down = alembic("downgrade", "0012")
    check("with only backfilled history, downgrading to 0012 works and removes only what 0013 added", down.returncode == 0 and scalar("select version_num from alembic_version") == "0012" and "community_events" not in set(r[0] for r in run("select tablename from pg_tables where schemaname = 'public'" if PG else "select name from sqlite_master where type = 'table'")))
    back = asyncio.run(snapshot({"alembic_version"}, old_cols))
    check("after the downgrade every original row and column is byte-identical to the start", [t for t in before if before[t] != back.get(t)] == [])
    up = alembic()
    check("and upgrading again works", up.returncode == 0 and scalar("select version_num from alembic_version") == "0013")
    run("insert into community_events (id, created_at, domain, kind, reconnection) values ('real-1', :ts, 'NEED', 'PUBLISHED', :f)", ts=ts, f=False)
    refused_down = alembic("downgrade", "0012")
    check("once REAL activity is recorded the downgrade is REFUSED and nothing is lost", refused_down.returncode != 0 and "Refusing to downgrade 0013" in (refused_down.stderr + refused_down.stdout) and scalar("select count(*) from community_events where id = 'real-1'") == 1 and scalar("select version_num from alembic_version") == "0013")

    failed = [n for ok, n in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    import shutil
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
