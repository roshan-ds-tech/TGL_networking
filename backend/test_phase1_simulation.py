"""Deterministic 10,000-operation simulation of the SHADOW economy (awards, voids, reversals, expiry, renewal records), then reconciliation.

Synthetic data for a test only: it is never counted as real observation. Seeded, so a failure reproduces.
Run:  .venv/bin/python test_phase1_simulation.py        (or TEST_DATABASE_URL=postgresql+asyncpg://... for PostgreSQL)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import random
import shutil
import sys
import time
from datetime import timedelta

os.environ["GROWTH_POINTS_SHADOW_MODE"] = "true"
import test_phase0 as t0  # noqa: E402
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, check, member_client, me, new_client, results, rows, scalar  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.main import app  # noqa: E402
from app.models import utcnow  # noqa: E402
from app.rewards import engine as reng, firewall, jobs, ledger, reconcile, rules  # noqa: E402
from app.rewards.engine import AwardRequest  # noqa: E402

N_OPS, SEED = 10_000, 20261009


def run(fn):
    async def go():
        from app.database import SessionLocal
        async with SessionLocal() as s:
            with firewall.guard():
                r = await fn(s)
            await s.commit()
            return r
    return asyncio.run(go())


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app) as boot:
        return body()


def body() -> int:
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    members = []
    for i, code in enumerate(["connect", "growth", "elite"] * 5):
        ratelimit._buckets.clear()
        c = member_client(f"sim{i}@example.com", f"Sim {i}")
        sid = c.post("/api/v1/subscriptions", json={"plan_code": code}, headers=H(c)).json()["id"]
        ratelimit._buckets.clear()
        c.post(f"/api/v1/subscriptions/{sid}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(c))
        admin.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
        c.get("/api/v1/status")
        members.append((me(c), code))
    rng = random.Random(SEED)
    now = utcnow()
    ev = [("REFERRAL_ACCEPTED", 45, 1), ("PROSPECT_CONTACTED", 15, 1), ("MEETING_COMPLETED", 60, 2), ("BUSINESS_CLOSED", 1890, 4), ("BUSINESS_CLOSED", 525, 2), ("PROFILE_COMPLETED", 75, 3)]
    counts = {"award": 0, "void": 0, "reversal": 0, "expiry_sweeps": 0}
    started = time.time()
    for op in range(N_OPS):
        r = rng.random()
        if r < 0.90:
            (a, _), (b, _) = rng.sample(members, 2)
            name, pts, lvl = rng.choice(ev)
            at = now + timedelta(days=rng.randint(0, 80), hours=rng.randint(0, 23))
            req = AwardRequest(member_id=a, counterparty_id=None if name == "PROFILE_COMPLETED" else b, role="referrer", event_type=name, reference_type="deal_closure" if name == "BUSINESS_CLOSED" else "referral",
                               reference_id=f"sim-{op}", requested=pts, level=lvl, event_at=at)
            run(lambda s: reng.award(s, req))
            counts["award"] += 1
        elif r < 0.99:
            kind = "VOID" if rng.random() < 0.5 else "REVERSAL"
            async def adj(s):
                lots = await ledger.lots(s, now=now + timedelta(days=(0 if kind == "VOID" else 95)))      # reversals need lots that are already usable
                lots = [l for l in lots if l.remaining > 0 and (l.state == "PENDING") == (kind == "VOID")]
                return await reng.adjust(s, rng.choice(lots), kind, "simulation") if lots else None
            if run(adj):
                counts["void" if kind == "VOID" else "reversal"] += 1
        else:
            run(lambda s: jobs.expire_due(s, now=now + timedelta(days=rng.randint(100, 400))))
            counts["expiry_sweeps"] += 1
        if op % 2500 == 2499:
            rec = run(lambda s: reconcile.reconcile(s))
            check(f"after {op + 1} operations: no drift and no ceiling violation", rec["ok"], str(rec)[:300])
    run(lambda s: jobs.expire_due(s, now=now + timedelta(days=500)))
    rec = run(lambda s: reconcile.reconcile(s))
    check(f"{N_OPS} operations ({counts}) in {time.time() - started:.0f}s: reconciliation clean (ledger sum = cached balance, no ceiling or pair-budget violation)", rec["ok"], str(rec)[:400])
    check("no negative balance, no impossible lot", scalar("select count(*) from growth_point_balances where total_points < 0") == 0 and not [d for d in rec["drift"] if "negative" in str(d)])
    check("no duplicate reward (idempotency keys are unique)", scalar("select count(*) from (select idempotency_key from growth_point_ledger group by idempotency_key having count(*) > 1) x") == 0)
    check("no orphan child entry: every void, reversal and expiry has a parent of the same member", scalar("select count(*) from growth_point_ledger c left join growth_point_ledger p on p.id = c.parent_id where c.parent_id is not null and (p.id is null or p.member_id <> c.member_id)") == 0)
    check("no cycle ever above its ceiling", scalar("select count(*) from (select c.id from growth_point_cycles c join growth_point_ledger l on l.cycle_id = c.id where l.entry_type in ('EARN','VOID','REVERSAL') group by c.id, c.ceiling_points having sum(l.points_delta) > c.ceiling_points) x") == 0)
    check("every ledger row is shadow and no financial row was touched", scalar("select count(*) from growth_point_ledger where not shadow") == 0 and scalar("select count(*) from invoices where discount_minor <> 0") == 0)
    digest = hashlib.sha256(repr(rows("select member_id, sum(points_delta) from growth_point_ledger group by member_id order by member_id")).encode()).hexdigest()[:16]
    print(f"SIMULATION DIGEST (seed {SEED}): {digest}  ops={counts}")
    passed = sum(1 for ok, _ in results if ok)
    print()
    for ok, name in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
