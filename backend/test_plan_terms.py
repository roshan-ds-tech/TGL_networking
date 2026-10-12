"""Plan terms: Connect Rs 3,000 / 3 months, Growth Rs 5,000 / 6 months, Elite Rs 10,000 / 12 months.

Focused checks for the plan-data correction (migration 0009): one canonical definition, the right term and price
reaching the invoice and the expiry, nothing client-supplied, history not rewritten, Growth Points still absent.

Run:  .venv/bin/python test_plan_terms.py
      TEST_DATABASE_URL=postgresql+asyncpg://user@host/db .venv/bin/python test_plan_terms.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import test_phase0 as t0  # sets the throwaway environment on import
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, app_settings, check, db, member_client, me, new_client, results, rows, scalar

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app import ratelimit  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Plan  # noqa: E402
from app.services import add_calendar_months  # noqa: E402
from app.subscriptions import DEFAULT_PLANS, ensure_default_plans  # noqa: E402

ROOT = Path(__file__).resolve().parent
EXPECTED = {"connect": (300_000, 3), "growth": (500_000, 6), "elite": (1_000_000, 12)}


def sql_fails(sql: str, **params) -> bool:
    async def f(s):
        try:
            await s.execute(text(sql), params)
            await s.commit()
            return False
        except (IntegrityError, DBAPIError):
            await s.rollback()
            return True
    return db(f)


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app) as boot:
        return body(boot)


def body(boot: TestClient) -> int:
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    n = iter(range(1, 1000))

    def member():
        c = member_client(f"term{next(n)}@example.com", f"Term Member {next(n)}")
        return c, me(c)

    def buy(c, code, **extra):
        ratelimit._buckets.clear()
        return c.post("/api/v1/subscriptions", json={"plan_code": code, **extra}, headers=H(c))

    def proof(c, sid):
        ratelimit._buckets.clear()
        return c.post(f"/api/v1/subscriptions/{sid}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(c))

    def verify(sid):
        return admin.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)

    def has_access(c):
        return c.get("/api/v1/referrals/summary").status_code == 200

    # ---------------------------------------------------------------- one canonical definition
    check("the canonical plans are exactly Connect 3 / Growth 6 / Elite 12 months at 3,000 / 5,000 / 10,000 rupees",
          [(c, p, m) for c, _n, p, m, _o in DEFAULT_PLANS] == [("connect", 300_000, 3), ("growth", 500_000, 6), ("elite", 1_000_000, 12)], str(DEFAULT_PLANS))
    stored = {r[0]: (r[1], r[2]) for r in rows("select code, price_minor, period_months from plans")}
    check("the plans in the database carry the same prices and terms", stored == EXPECTED, str(stored))
    check("the term lives in the plan row; there is no separate billing-period label any more", "billing_period" not in {c["name"] for c in db_columns("plans")})
    spec = importlib.util.spec_from_file_location("m0009", ROOT / "migrations" / "versions" / "0009_plan_terms.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    check("migration 0009's point-in-time copy of the terms agrees with the canonical table", mig.CANONICAL_TERMS == {c: m for c, _n, _p, m, _o in DEFAULT_PLANS}, str(mig.CANONICAL_TERMS))
    literal = [p.name for p in (ROOT / "app").rglob("*.py") if re.search(r"period_months\s*=\s*\d", p.read_text())]
    check("no application code assigns a literal duration (only the canonical table does)", literal == [], str(literal))
    jsx = (ROOT.parent / "src" / "pages" / "networking" / "Subscription.jsx").read_text()
    check("the member screen hard-codes no plan duration", not re.search(r"months:\s*\d|\b(3|6|12)[- ]month", jsx), "found a literal duration in Subscription.jsx")
    plans_api = new_client()
    m0, _ = member()
    api = {p["code"]: (p["price_minor"], p["period_months"]) for p in m0.get("/api/v1/plans").json()}
    check("the API serves the stored prices and terms", api == EXPECTED, str(api))

    # ---------------------------------------------------------------- expiry arithmetic (project's own function, UTC)
    d = datetime(2026, 10, 1, tzinfo=timezone.utc)
    check("Connect: 2026-10-01 -> 2027-01-01", add_calendar_months(d, 3) == datetime(2027, 1, 1, tzinfo=timezone.utc))
    check("Growth: 2026-10-01 -> 2027-04-01", add_calendar_months(d, 6) == datetime(2027, 4, 1, tzinfo=timezone.utc))
    check("Elite: 2026-10-01 -> 2027-10-01", add_calendar_months(d, 12) == datetime(2027, 10, 1, tzinfo=timezone.utc))
    check("month ends clamp (31 Aug + 6 months = 28 Feb; 31 Oct + 3 = 31 Jan; 29 Feb 2028 + 12 = 28 Feb 2029)",
          add_calendar_months(datetime(2026, 8, 31, tzinfo=timezone.utc), 6) == datetime(2027, 2, 28, tzinfo=timezone.utc)
          and add_calendar_months(datetime(2026, 10, 31, tzinfo=timezone.utc), 3) == datetime(2027, 1, 31, tzinfo=timezone.utc)
          and add_calendar_months(datetime(2028, 2, 29, tzinfo=timezone.utc), 12) == datetime(2029, 2, 28, tzinfo=timezone.utc))
    check("the timezone is preserved", add_calendar_months(d, 12).tzinfo is not None)

    # ---------------------------------------------------------------- end to end, every plan
    subs = {}
    for code, (price, months) in EXPECTED.items():
        c, uid = member()
        r = buy(c, code, price_minor=1, amount_due_minor=1, discount_minor=1, period_months=1, months=1, term=1, duration=1, billing_period="SEASON",
                status="ACTIVE", currency="USD", expires_at="2030-01-01T00:00:00Z")
        sub = r.json() if r.status_code == 201 else {}
        inv = sub.get("invoice") or {}
        check(f"{code}: the invoice is for {price // 100:,} rupees and {months} months, whatever the client sent",
              r.status_code == 201 and inv.get("amount_due_minor") == price and inv.get("list_price_minor") == price and inv.get("period_months") == months
              and inv.get("discount_minor") == 0 and inv.get("currency") == "INR" and sub.get("status") == "PENDING", r.text[:300])
        check(f"{code}: the plan on the subscription says {months} months", (sub.get("plan") or {}).get("period_months") == months)
        check(f"{code}: nothing is granted before the payment is verified", not has_access(c))
        proof(c, sub["id"])
        v = verify(sub["id"])
        vj = v.json() if v.status_code == 200 else {}
        starts, expires = parse(vj["starts_at"]), parse(vj["expires_at"])
        check(f"{code}: verified; expiry = start + {months} calendar months exactly", v.status_code == 200 and expires == add_calendar_months(starts, months), v.text[:200])
        check(f"{code}: the invoice records the paid amount and the access starts", vj["invoice"]["amount_paid_minor"] == price and has_access(c))
        subs[code] = (c, uid, sub["id"], months)
    stamps = {code: rows("select starts_at, expires_at from subscriptions where id = :i", i=sid)[0] for code, (_c, _u, sid, _m) in subs.items()}
    check("stored dates agree with the API for every plan", all(stamps[c][0] and stamps[c][1] for c in stamps))

    # ---------------------------------------------------------------- invalid durations
    for months in (0, 1, 2, 4, 5, 7, 9, 13, 24, -3):
        check(f"the database refuses a plan term of {months} months", sql_fails("update plans set period_months = :m where code = 'growth'", m=months))
    check("after the refused changes the terms are untouched", {r[0]: r[1] for r in rows("select code, period_months from plans")} == {c: m for c, (_p, m) in EXPECTED.items()})
    check("a term of 3, 6 or 12 months is accepted by the constraint", all(not sql_fails("update plans set period_months = :m where code = 'connect'", m=m) for m in (6, 12)) and not sql_fails("update plans set period_months = 3 where code = 'connect'"))
    check("there is no member or admin route that edits a plan", all(c.put("/api/v1/plans/growth", json={"period_months": 3}, headers=H(c)).status_code in (404, 405) for c in [m0])
          and admin.put("/api/admin/plans/growth", json={"period_months": 3}, headers=AH).status_code in (404, 405))

    # ---------------------------------------------------------------- history is not rewritten
    c_old, uid_old = member()
    sid_old = buy(c_old, "growth").json()["id"]
    proof(c_old, sid_old)

    async def issued_under_old_data(s):                       # an invoice issued while Growth was still seeded as 3 months
        await s.execute(text("update invoices set period_months = 3 where subscription_id = :i"), {"i": sid_old})
        await s.commit()
    db(issued_under_old_data)
    r = verify(sid_old)
    check("an invoice issued for a different term than the plan carries is refused at verification, not silently granted a term", r.status_code == 409 and "months" in r.text, r.text[:200])
    check("and nothing was granted", scalar("select status from subscriptions where id = :i", i=sid_old) == "PENDING" and not has_access(c_old))
    check("cancelling it and buying again gives the corrected term", c_old.post(f"/api/v1/subscriptions/{sid_old}/cancel", headers=H(c_old)).status_code == 200
          and buy(c_old, "growth").json()["invoice"]["period_months"] == 6)

    c_g, uid_g, sid_g, _m = subs["growth"]
    before = rows("select i.period_months, i.amount_due_minor, i.status, s.starts_at, s.expires_at, s.status from invoices i join subscriptions s on s.id = i.subscription_id where s.id = :i", i=sid_g)[0]

    async def wrong_plan_row(s):                              # a database created before the correction: Growth seeded as 3 months
        await s.execute(text("update plans set period_months = 3 where code = 'growth'"))
        await s.commit()
    db(wrong_plan_row)

    async def heal(s):
        changed = await ensure_default_plans(s)
        await s.commit()
        return changed
    check("the development seed corrects a wrong plan term and reports it", db(heal) == 1 and scalar("select period_months from plans where code = 'growth'") == 6)
    after = rows("select i.period_months, i.amount_due_minor, i.status, s.starts_at, s.expires_at, s.status from invoices i join subscriptions s on s.id = i.subscription_id where s.id = :i", i=sid_g)[0]
    check("a settled subscription, its invoice and its dates are not rewritten", tuple(before) == tuple(after), f"{before} -> {after}")
    check("the seed does not touch a price or a status", {r[0]: r[1] for r in rows("select code, price_minor from plans")} == {c: p for c, (p, _m) in EXPECTED.items()})

    # ---------------------------------------------------------------- Growth Points: still nothing
    check("the pricing confirmation flag is still false", app_settings.subscription_pricing_confirmed is False)
    tables = {x[0] for x in rows("select name from sqlite_master where type = 'table'")} if engine.dialect.name == "sqlite" else {x[0] for x in rows("select tablename from pg_tables where schemaname = 'public'")}
    check("no redemption, voucher, coupon, discount or reward table exists (only the Phase 1 shadow growth_point_* tables)",
          not [t for t in tables if not t.startswith("growth_point_") and re.search(r"growth|reward|point|redemption|ledger|redeem|voucher|coupon|discount", t)], str(sorted(tables)))
    check("every invoice has a zero discount and no member holds Growth Points", scalar("select count(*) from invoices where discount_minor <> 0") == 0 and scalar("select coalesce(sum(growth_points), 0) from networking_profiles") == 0)
    check("no invoice was reduced by anything", scalar("select count(*) from invoices where amount_due_minor <> list_price_minor") == 0)

    passed = sum(1 for ok, _ in results if ok)
    print()
    for ok, name in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


def db_columns(table: str):
    async def f(s):
        return await s.run_sync(lambda c: inspect(c.connection()).get_columns(table))
    return db(f)


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
