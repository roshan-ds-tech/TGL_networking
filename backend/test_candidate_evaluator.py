"""The HYPOTHETICAL Community rewards evaluator (scripts/community_candidate_evaluation.py): read-only, genuine-only, aggregate-only.

Targeted. Run:  .venv/bin/python test_candidate_evaluator.py      (SQLite, or TEST_DATABASE_URL=postgresql+asyncpg://... for PostgreSQL)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import test_phase0 as t0
from test_phase0 import TMP, check, member_client, me, results, rows

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.models import CommunityEvent

HERE = Path(__file__).parent


def snapshot() -> dict:
    """A hash of every row of every table: the evaluator must leave all of it byte-for-byte unchanged."""
    tables = [r[0] for r in rows("select name from sqlite_master where type = 'table' order by name")] if "sqlite" in os.environ["DATABASE_URL"] \
        else [r[0] for r in rows("select tablename from pg_tables where schemaname = 'public' order by tablename")]
    out = {}
    for tname in tables:
        data = rows(f'select * from "{tname}"')
        out[tname] = (len(data), hashlib.sha256(repr(sorted(map(repr, data))).encode()).hexdigest())
    return out


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ}
    env.pop("TEST_DATABASE_URL", None)
    return subprocess.run([sys.executable, "scripts/community_candidate_evaluation.py", *args], capture_output=True, text=True, env=env, cwd=str(HERE))


def at(d: int, h: int = 9) -> datetime:
    return datetime(2027, 1, d, h, 0, tzinfo=timezone.utc)


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app):
        a_c, b_c, s_c = member_client("a-eval@example.com", "Asha Rao"), member_client("b-eval@example.com", "Bala Iyer"), member_client("s-eval@example.com", "Synthetic Sam")
        A, B, S = me(a_c), me(b_c), me(s_c)
    asyncio.run(_make_synthetic(S))

    # ---- nothing genuine yet: it says so and stops
    before = snapshot()
    empty = run_cli("--json")
    j = json.loads(empty.stdout) if empty.returncode == 0 else {}
    check("EMPTY: with no community history it reports 'no genuine community activity', claims no observation, and exits 0", empty.returncode == 0 and j.get("genuine_events") == 0 and "Observation has not started" in j.get("result", ""), empty.stderr[-300:])

    async def seed_events():
        async with SessionLocal() as s:
            def e(i, d, k, when, actor=None, subject=None, reason=None):
                s.add(CommunityEvent(id=f"ev-{i:03d}", created_at=when, domain=d, kind=k, actor_user_id=actor, subject_user_id=subject, reason_code=reason))
            e(1, "CONNECTION", "ACCEPTED", at(3), A, B)
            for i, day in enumerate((4, 9, 16)):
                e(2 + i, "NEED", "PUBLISHED", at(day), A)                            # three needs in one month: the proposed limit rewards two
            e(5, "HELP", "CONFIRMED_HELPFUL", at(20), A, B)                         # poster A confirms helper B
            e(6, "NEED", "RESOLVED", at(22), A, B)                                  # A resolves with B credited
            e(7, "CONNECTION", "REQUESTED", at(2), A, B)                            # a request earns nothing
            e(8, "HELP", "OFFERED", at(19), B, A)                                   # an offer earns nothing
            e(9, "CONNECTION", "ACCEPTED", at(5), A, S)                              # synthetic counterparty: excluded
            e(10, "NEED", "PUBLISHED", at(6), S)                                     # synthetic actor: excluded
            e(11, "CONNECTION", "ACCEPTED", at(7), B, A, reason="BACKFILL")         # backfilled history: excluded
            await s.commit()
    asyncio.run(seed_events())
    before = snapshot()
    out = run_cli("--json")
    j = json.loads(out.stdout) if out.returncode == 0 else {}
    bk = j.get("by_kind", {})
    check("REPLAY: genuine history only. Connection x2, need published x3 (limit 2), confirmed help, resolved + closed = requested 160, HYPOTHETICAL award 140 (Rs14.00)",
          j.get("requested_points") == 160 and j.get("hypothetical_awarded_points") == 140 and j.get("hypothetical_rupee_value") == 14.0, out.stderr[-300:] + out.stdout[-300:])
    check("PER KIND: NEED_PUBLISHED 3 events -> 60 requested, 40 awarded (FREQUENCY_LIMIT); CONNECTION_ACCEPTED 2 events -> 20; HELP 25; RESOLVED 45; CLOSED 10",
          bk.get("NEED_PUBLISHED") == {"events": 3, "requested": 60, "awarded": 40} and bk.get("CONNECTION_ACCEPTED", {}).get("awarded") == 20 and bk.get("NEED_HELP_CONFIRMED", {}).get("awarded") == 25
          and bk.get("NEED_RESOLVED", {}).get("awarded") == 45 and bk.get("NEED_CLOSED", {}).get("awarded") == 10 and j.get("events_reduced_by_rule") == {"FREQUENCY_LIMIT": 1}, str(bk))
    check("EXCLUDED: the synthetic member's two events and the backfilled event are counted as excluded (3) and never replayed",
          j.get("synthetic_or_backfilled_events_excluded") == 3 and j.get("events_replayed") == 8)
    check("LABELLED: the output states it is hypothetical, not approved, not awarded and not a balance; and it lists what Phase A cannot see",
          "HYPOTHETICAL" in j.get("label", "") and "NOT approved" in j.get("label", "") and len(j.get("not_visible", [])) == 2)
    blob = out.stdout
    check("ANONYMOUS: the output contains no member id, name, e-mail or event id", not any(x in blob for x in (A, B, S, "Asha", "Bala", "example.com", "ev-0")))
    after = snapshot()
    check("READ-ONLY: every table, with every row, is byte-for-byte identical after the run (no ledger row, no new table, no points)", before == after)
    since = run_cli("--json", "--since", "2027-01-10")
    js = json.loads(since.stdout)
    check("--since: only events on or after the date are replayed (the need at day 16, the confirmed help, the resolution and its close = 4 events, 100 points requested)", js.get("events_replayed") == 4 and js.get("requested_points") == 100, str(js))
    text_out = run_cli()
    check("the plain-text form prints the same label first", text_out.returncode == 0 and text_out.stdout.splitlines()[0].startswith("HYPOTHETICAL"))
    check("no Growth Point exists anywhere because of the evaluator", (rows("select count(*) from growth_point_ledger") or [(0,)])[0][0] == 0 if _has_table("growth_point_ledger") else True)

    w = j.get("observation_window", {})
    check("OBSERVATION WINDOW: the first and last genuine event are reported (backfilled and synthetic ones never set them) and a short history is not called a full quarter",
          w.get("first_genuine_event", "").startswith("2027-01-") and w.get("full_quarter_observed") is False and j.get("members_priced_by_assumed_plan", -1) >= 0, str(w))
    empty_db = Path(TMP) / "no_schema.db"
    bare = subprocess.run([sys.executable, "scripts/community_candidate_evaluation.py"], capture_output=True, text=True, cwd=str(HERE),
                          env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{empty_db}", "ENVIRONMENT": "development"})
    check("FAILS SAFE: on a database without the Phase A tables it exits 2 and explains, instead of a traceback or a false 'zero activity'",
          bare.returncode == 2 and "0013" in bare.stderr and "Traceback" not in bare.stderr, bare.stderr[-300:])

    failed = [n for ok, n in results if not ok]
    for ok, n in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


async def _make_synthetic(user_id: str) -> None:
    async with SessionLocal() as s:
        await s.execute(text("update users set email = 'demo-eval@demo.example.com' where id = :i"), {"i": user_id})
        await s.commit()


def _has_table(name: str) -> bool:
    return bool(rows("select name from sqlite_master where type='table' and name = :n", n=name)) if "sqlite" in os.environ["DATABASE_URL"] \
        else bool(rows("select tablename from pg_tables where schemaname='public' and tablename = :n", n=name))


if __name__ == "__main__":
    sys.exit(main())
