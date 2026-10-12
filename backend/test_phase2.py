"""Growth Points, Phase 2: REAL redemption infrastructure, rehearsed with the gates opened in-process for the test only.

Everything is synthetic and runs on a throwaway database. Nothing here is real observation or real money. In production the flag is OFF,
the application refuses to boot with it ON unless every approval is recorded, and Gate A / the kill switch / the rollout stage are
checked on every redemption.

Run:  .venv/bin/python test_phase2.py           TEST_DATABASE_URL=postgresql+asyncpg://... .venv/bin/python test_phase2.py
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone

os.environ["GROWTH_POINTS_SHADOW_MODE"] = "true"
os.environ["GROWTH_POINTS_MEMBER_PREVIEW"] = "true"
import test_phase0 as t0  # noqa: E402
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, app_settings, check, db, member_client, me, new_client, results, rows, scalar  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app import ratelimit  # noqa: E402
from app.config import REQUIRED_APPROVALS, Settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin, GrowthPointLedger, Invoice, Payment, Plan, Subscription, User, utcnow  # noqa: E402
from app.redemption import finance, service  # noqa: E402
from app.rewards import engine as reng, firewall, gates, hooks, jobs, ledger, reconcile, rules  # noqa: E402
from app.rewards.engine import AwardRequest  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.subscriptions import build_purchase  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PRICE = {"connect": 300000, "growth": 500000, "elite": 1000000}
MONTHS = {"connect": 3, "growth": 6, "elite": 12}
FULL = {"connect": [dict(closure=1800, process=450, other=360), dict(closure=360, process=450, other=360)],
        "growth": [dict(closure=1800, process=750, other=450)] * 2, "elite": [dict(closure=1800, process=750, other=450)] * 4}


def go(fn):
    async def f():
        async with SessionLocal() as s:
            r = await fn(s)
            await s.commit()
            return r
    return asyncio.run(f())


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


def open_gates(stage: str = "all"):
    """Open every gate for the rehearsal (the production defaults are all closed)."""
    app_settings.growth_points_redemption_enabled = True
    app_settings.growth_points_approvals = ",".join(sorted(REQUIRED_APPROVALS))
    app_settings.growth_points_rollout_stage = stage
    app_settings.growth_points_redeemable_from = "2000-01-01T00:00:00+00:00"
    if not scalar("select count(*) from growth_point_redemption_epoch"):          # the test records the epoch directly (the endpoint refuses a back-dated cutoff, correctly)
        async def put(s_):
            await s_.execute(text("insert into growth_point_redemption_epoch (id, singleton, cutoff_at, recorded_at, recorded_by, reason) values ('t-epoch', 'ONLY', '2000-01-01 00:00:00+00:00', '2000-01-01 00:00:00+00:00', 'test', 'rehearsal epoch')"))
            await s_.commit()
        db(put)
    async def yes(_db):
        return True
    service._gate_a_passed = yes


def close_gates():
    app_settings.growth_points_redemption_enabled = False
    app_settings.growth_points_approvals = ""
    app_settings.growth_points_redeemable_from = ""
    app_settings.growth_points_rollout_stage = "internal"


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app) as boot:
        return body()


def body() -> int:
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    app_settings.programme_owner_emails = ADMIN_EMAIL
    counter = iter(range(1, 100000))

    def clear():
        ratelimit._buckets.clear()

    def buy(c, code):
        clear()
        r = c.post("/api/v1/subscriptions", json={"plan_code": code}, headers=H(c))
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        clear()
        assert c.post(f"/api/v1/subscriptions/{sid}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(c)).status_code == 200
        assert admin.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH).status_code == 200
        return sid

    def member(code):
        clear()
        k = next(counter)
        c = member_client(f"p2-{k}@example.com", f"P2 Member {k}")
        sid = buy(c, code)
        c.get("/api/v1/status")
        return c, me(c), sid, f"p2-{k}@example.com"

    def age(sid, code, ends_in_days):
        """Place the member's term so that it ends `ends_in_days` from now (negative = ended). Returns (starts, ends)."""
        ends = utcnow() + timedelta(days=ends_in_days)
        starts = ends - timedelta(days=round(MONTHS[code] * 30.4375))
        status_ = "ACTIVE" if ends_in_days > 0 else "EXPIRED"
        async def f(s):
            await s.execute(text("update subscriptions set starts_at = :s, expires_at = :e, activated_at = :s, status = :st where id = :i"), {"s": starts, "e": ends, "i": sid, "st": status_})
            await s.commit()
        db(f)
        return starts, ends

    def award(mid, ev, ref, pts, lvl, at, rtype="referral", role="member"):
        async def f(s):
            with firewall.guard():
                res = await reng.award(s, AwardRequest(member_id=mid, event_type=ev, reference_type=rtype, reference_id=ref, requested=pts, level=lvl, event_at=at, role=role))
            return res.row.points_delta
        return go(f)

    def earn(mid, tag, buckets, starts):
        for k, b in enumerate(buckets):
            base = rules.local(starts + timedelta(days=3 + 33 * k)).replace(hour=10, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            if b.get("closure"):
                award(mid, "BUSINESS_CLOSED", f"{tag}c{k}", b["closure"], 4, base, "deal_closure", "referrer")
            if b.get("process"):
                award(mid, "MEETING_COMPLETED", f"{tag}p{k}", b["process"], 3, base + timedelta(hours=1))
            if b.get("other"):
                award(mid, "PROFILE_COMPLETED", f"{tag}o{k}", b["other"], 3, base + timedelta(hours=2), "member")

    def case(old, tag, buckets=None, ends_in=-5):
        c, mid, sid, email = member(old)
        starts, ends = age(sid, old, ends_in)
        earn(mid, tag, buckets or FULL[old], starts)
        earned = scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where member_id = :m and entry_type = 'EARN'", m=mid)
        return dict(c=c, mid=mid, sid=sid, email=email, old=old, tag=tag, starts=starts, ends=ends, earned=earned)

    def quote(cs, plan):
        return cs["c"].get("/api/v1/renewal/quote", params={"plan_code": plan}).json()

    def confirm(cs, plan, redeem=True, q=None, **over):
        clear()
        body_ = {"plan_code": plan, "redeem": redeem}
        if redeem:
            q = q or quote(cs, plan)
            body_.update(expected_points=q["points_to_be_redeemed"], expected_discount_minor=q["hypothetical_discount_paise"])
        body_.update(over)
        return cs["c"].post("/api/v1/renewal/confirm", json=body_, headers=H(cs["c"]))

    def earn_snapshot(mid):
        return rows("select id, points_delta, remaining, status, event_type, cycle_id from growth_point_ledger where member_id = :m and entry_type = 'EARN' order by created_at, id", m=mid)

    # ======================================================================================== 1. THE GATES (production defaults: all closed)
    close_gates()
    check("DEFAULTS: redemption OFF, no approvals, no owner-less rollout, nothing redeemable (cutoff empty), engine flag built but gated",
          Settings.model_fields["growth_points_redemption_enabled"].default is False and Settings.model_fields["growth_points_approvals"].default == ""
          and Settings.model_fields["growth_points_redeemable_from"].default == "" and Settings.model_fields["growth_points_rollout_stage"].default == "internal")
    try:
        Settings(growth_points_redemption_enabled=True)
        refused = False
    except Exception:
        refused = True
    check("BOOT: the application refuses to start with redemption ON unless every external approval is recorded", refused)
    try:
        ok_settings = Settings(growth_points_redemption_enabled=True, growth_points_approvals=",".join(sorted(REQUIRED_APPROVALS)))
        accepted = ok_settings.growth_points_redemption_enabled
    except Exception:
        accepted = False
    check("BOOT: with every approval recorded it can start (the runtime gates still apply)", accepted is True)
    c0 = case("growth", "g0")
    async def gate(user_id):
        async with SessionLocal() as s:
            return await service.allowed(s, await s.get(User, user_id))
    reasons = {}
    reasons["flag"] = asyncio.run(gate(c0["mid"]))[1]
    app_settings.growth_points_redemption_enabled = True
    reasons["approvals"] = asyncio.run(gate(c0["mid"]))[1]
    app_settings.growth_points_approvals = ",".join(sorted(REQUIRED_APPROVALS))
    saved_gate = service._gate_a_passed
    async def no(_db):
        return False
    service._gate_a_passed = no
    service._gate_a_cache.update(at=0.0)
    reasons["gate_a"] = asyncio.run(gate(c0["mid"]))[1]
    open_gates("internal")
    reasons["rollout"] = asyncio.run(gate(c0["mid"]))[1]
    open_gates("all")
    reasons["open"] = asyncio.run(gate(c0["mid"]))[1]
    check("GATES: each closed gate gives its own reason, in order: flag, approvals, Gate A, rollout; and only then it opens", reasons == {"flag": "redemption_disabled", "approvals": "approvals_missing", "gate_a": "gate_a_not_passed", "rollout": "not_in_rollout", "open": "open"}, str(reasons))

    # ======================================================================================== 2. DATABASE INVARIANTS ON THE INVOICE
    inv = rows("select id, list_price_minor from invoices limit 1")[0]
    check("INVOICE CHECK: a discount that is not points is refused", sql_fails("update invoices set discount_minor = 100, amount_due_minor = list_price_minor - 100 where id = :i", i=inv[0]))
    check("INVOICE CHECK: points must be worth exactly 10 paise each", sql_fails("update invoices set points_redeemed = 10, points_discount_minor = 99, discount_minor = 99, amount_due_minor = list_price_minor - 99 where id = :i", i=inv[0]))
    check("INVOICE CHECK: more than 15% of the list price is refused", sql_fails("update invoices set points_redeemed = :p, points_discount_minor = :d, discount_minor = :d, amount_due_minor = list_price_minor - :d where id = :i", p=inv[1] // 10 * 16 // 100 + 1, d=(inv[1] // 10 * 16 // 100 + 1) * 10, i=inv[0]))
    check("INVOICE CHECK: the amount due can never fall below 80% of the list price, and never be negative", sql_fails("update invoices set amount_due_minor = 0 where id = :i", i=inv[0]) and sql_fails("update invoices set amount_due_minor = -5, discount_minor = list_price_minor + 5, points_discount_minor = list_price_minor + 5 where id = :i", i=inv[0]))
    check("INVOICE CHECK: amount due must equal the list price minus the discount", sql_fails("update invoices set amount_due_minor = amount_due_minor - 1 where id = :i", i=inv[0]))

    # ======================================================================================== 3. THE REHEARSAL MATRIX: every transition, below / at / above the cap
    transitions = [("connect", "connect"), ("connect", "growth"), ("growth", "growth"), ("growth", "elite"), ("elite", "elite"), ("elite", "growth"), ("growth", "connect"), ("elite", "connect")]
    EARNED = {"connect": 3600, "growth": 6000, "elite": 12000}
    cases = {}
    for old, new in transitions:
        cs = case(old, f"m{old[0]}{new[0]}")
        cases[(old, new)] = cs
    for (old, new), cs in cases.items():
        cap = rules.redemption_cap_points(PRICE[new])
        want = min(EARNED[old], cap)
        left = EARNED[old] - want
        name = f"{old} -> {new}"
        snap = earn_snapshot(cs["mid"])
        q = quote(cs, new)
        check(f"REHEARSAL {name}: the quote shows eligible {EARNED[old]}, the NEW plan's cap {cap}, uses {want}, discount Rs {want // 10}, payable Rs {(PRICE[new] - want * 10) // 100}, {left} left, zero transferred to the new cycle",
              q["mode"] == "REAL" and (q["eligible_old_cycle_points"], q["new_plan_redemption_ceiling_points"], q["points_to_be_redeemed"], q["hypothetical_discount_paise"], q["hypothetical_amount_payable_paise"], q["remaining_old_cycle_points"],
                                       q["new_cycle_transferred_earning_points"]) == (EARNED[old], cap, want, want * 10, PRICE[new] - want * 10, left, 0), str(q)[:400])
        r = confirm(cs, new, q=q)
        cs["result"] = r.json() if r.status_code == 201 else {}
        inv = rows("select id, list_price_minor, discount_minor, points_discount_minor, points_redeemed, amount_due_minor, status from invoices where subscription_id = :s", s=cs["result"].get("subscription_id", ""))
        pay = rows("select amount_minor, status from payments where invoice_id = :i", i=inv[0][0]) if inv else []
        red = rows("select entry_type, points, discount_paise, list_price_minor, amount_due_minor, cap_points, eligible_points, old_cycle_id, created_by from growth_point_redemptions where invoice_id = :i", i=inv[0][0]) if inv else []
        check(f"REHEARSAL {name}: the REAL renewal invoice has list Rs {PRICE[new] // 100}, points discount {want * 10} paise, amount due {PRICE[new] - want * 10} paise, and the payment is for exactly that",
              r.status_code == 201 and inv and inv[0][1:6] == (PRICE[new], want * 10, want * 10, want, PRICE[new] - want * 10) and pay == [(PRICE[new] - want * 10, "PENDING")], f"{r.status_code} {r.text[:200]} {inv} {pay}")
        check(f"REHEARSAL {name}: one append-only redemption record with the invoice, the old cycle, the cap, the eligible points and the rule version", len(red) == 1 and red[0][:7] == ("REDEEM", want, want * 10, PRICE[new], PRICE[new] - want * 10, cap, EARNED[old])
              and red[0][8] == cs["mid"] and scalar("select rule_version from growth_point_redemptions where invoice_id = :i", i=inv[0][0]) == rules.RULE_VERSION)
        lines = rows("select lot_id, delta from growth_point_redemption_lots where redemption_id = (select id from growth_point_redemptions where invoice_id = :i) order by created_at, id", i=inv[0][0])
        order = [s_[0] for s_ in snap]
        check(f"REHEARSAL {name}: FIFO: the oldest lots are consumed first, only as far as needed", -sum(l[1] for l in lines) == want and [l[0] for l in lines] == order[:len(lines)] and all(l[1] < 0 for l in lines)
              and all(-l[1] == s_[1] for l, s_ in zip(lines[:-1], snap)))
        check(f"REHEARSAL {name}: the earning rows are untouched, the balance fell by exactly the points used, and the old cycle's ceiling is unchanged", earn_snapshot(cs["mid"]) == snap
              and scalar("select total_points from growth_point_balances where member_id = :m", m=cs["mid"]) == EARNED[old] - want
              and scalar("select ceiling_points from growth_point_cycles where id = :c", c=snap[0][5]) == EARNED[old] if old != "connect" or True else True)

    # ======================================================================================== 4. BOUNDARIES: 0, 100, 1,000, exactly the cap, and cap + 1
    for pts, label in ((0, "0 points"), (100, "100 points"), (1000, "1,000 points"), (4500, "exactly the Connect cap (4,500)"), (4501, "one over the Connect cap")):
        bk = [dict(process=min(pts, 750), closure=max(0, min(pts - 750, 1800)), other=max(0, min(pts - 2550, 450)))] + ([dict(closure=max(0, min(pts - 3000, 1800)))] if pts > 3000 else [])
        cs = case("growth", f"b{pts}", buckets=bk if pts else [dict(process=0)])
        got = scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where member_id = :m and entry_type = 'EARN'", m=cs["mid"])
        q = quote(cs, "connect")
        r = confirm(cs, "connect", q=q)
        want = min(got, 4500)
        inv = rows("select amount_due_minor, points_redeemed, discount_minor from invoices where subscription_id = :s", s=r.json().get("subscription_id", "")) if r.status_code == 201 else []
        check(f"BOUNDARY {label} (earned {got}) renewing into Connect: uses min({got}, 4,500) = {want} points, amount due {300000 - want * 10} paise", got == pts and r.status_code == 201 and inv == [(300000 - want * 10, want, want * 10)], f"{got} {r.status_code} {inv}")

    # ======================================================================================== 5. EXPIRED / MIXED-EXPIRY / NON-RENEWAL
    late = case("connect", "late", ends_in=-40)
    r = confirm(late, "growth", redeem=False)
    qlate = quote(late, "growth")
    check("EXPIRED: 40 days after the term the renewal window is closed: the renewal is refused, the old points can not be used and nothing is created", r.status_code == 409 and r.json()["detail"]["code"] == "outside_renewal_window"
          and qlate["points_to_be_redeemed"] == 0 and scalar("select count(*) from subscriptions where user_id = :u", u=late["mid"]) == 1)
    mixed = case("growth", "mx1", ends_in=-300)                    # an old cycle whose points are long past their grace, never swept
    c2, mid2, sid2, mail2 = mixed["c"], mixed["mid"], mixed["sid"], mixed["email"]
    new_sid = buy(c2, "growth")                                    # an ordinary later purchase (a second term)
    starts2, ends2 = age(new_sid, "growth", -5)
    earn(mid2, "mx2", FULL["growth"], starts2)
    mixed.update(sid=new_sid, ends=ends2)
    old_lots_remaining = sum(l.remaining for l in go(lambda s_: ledger.lots(s_, member_id=mid2)) if l.row.cycle_id == scalar("select id from growth_point_cycles where member_id = :m order by starts_at limit 1", m=mid2))
    qm = quote(mixed, "growth")
    check("MIXED EXPIRY: a member with an expired earlier cycle and a recent one: only the recent cycle's lots are eligible (the expired points are never used)", old_lots_remaining > 0 and qm["eligible_old_cycle_points"] == 6000 and qm["points_to_be_redeemed"] == 6000, str(qm)[:300])
    r = confirm(mixed, "growth", q=qm)
    used_cycles = rows("select distinct l.cycle_id from growth_point_redemption_lots x join growth_point_ledger l on l.id = x.lot_id where x.member_id = :m", m=mid2)
    check("MIXED EXPIRY: the redemption touched only the recent cycle", r.status_code == 201 and len(used_cycles) == 1 and used_cycles[0][0] != scalar("select id from growth_point_cycles where member_id = :m order by starts_at limit 1", m=mid2))
    nonr = case("elite", "nr", ends_in=-5)
    check("NON-RENEWAL: a member who does not renew keeps their points only until the window closes; no redemption, no invoice, nothing created", scalar("select count(*) from growth_point_redemptions where member_id = :m", m=nonr["mid"]) == 0
          and scalar("select count(*) from subscriptions where user_id = :u", u=nonr["mid"]) == 1)

    # ======================================================================================== 6. EARLY RENEWAL (the last 30 days of a running term) and the next cycle
    early = case("growth", "ea", ends_in=10)                       # the term is still running and ends in 10 days
    plain = early["c"].post("/api/v1/subscriptions", json={"plan_code": "elite"}, headers=H(early["c"]))
    qe = quote(early, "elite")
    check("EARLY RENEWAL: the old route still refuses a second subscription mid-term (no normal mid-cycle upgrade); the renewal route quotes Elite for the old Growth points",
          plain.status_code == 409 and qe["eligible_old_cycle_points"] == 6000 and qe["points_to_be_redeemed"] == 6000 and qe["hypothetical_amount_payable_paise"] == 1000000 - 60000)
    ren = confirm(early, "elite", q=qe)
    new_sub = ren.json()
    check("EARLY RENEWAL: raised while the old term is live: PENDING renewal of the old subscription, invoice Rs 10,000 less Rs 600", ren.status_code == 201 and new_sub["status"] == "PENDING" and new_sub["amount_due_minor"] == 940000
          and scalar("select renews_subscription_id from subscriptions where id = :s", s=new_sub["subscription_id"]) == early["sid"])
    clear()
    early["c"].post(f"/api/v1/subscriptions/{new_sub['subscription_id']}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(early["c"]))
    vr = admin.post(f"/api/admin/subscriptions/{new_sub['subscription_id']}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
    old_end = scalar("select expires_at from subscriptions where id = :s", s=early["sid"])
    starts_new = scalar("select starts_at from subscriptions where id = :s", s=new_sub["subscription_id"])
    check("EARLY RENEWAL: once paid, the new Elite term STARTS when the old one ends (no overlapping time is paid for) and the old term stays ACTIVE until then", vr.status_code == 200
          and str(starts_new)[:19] == str(old_end)[:19] and scalar("select status from subscriptions where id = :s", s=early["sid"]) == "ACTIVE" and scalar("select status from subscriptions where id = :s", s=new_sub["subscription_id"]) == "ACTIVE")
    got_new = award(early["mid"], "PROFILE_COMPLETED", "ea-new", 75, 3, utcnow() + timedelta(hours=1), "member")
    newc = rows("select plan_code, ceiling_points from growth_point_cycles where id = (select cycle_id from growth_point_ledger where member_id = :m and reference_id = 'ea-new')", m=early["mid"])
    check("NEXT CYCLE: what is earned after the renewal is paid belongs to the NEW Elite cycle (ceiling 12,000), starting from zero transferred points", newc == [("elite", 12000)] and got_new == 75
          and scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where cycle_id = (select cycle_id from growth_point_ledger where reference_id = 'ea-new')") == 75)
    tooearly = case("growth", "te", ends_in=45)
    r = confirm(tooearly, "elite", redeem=False)
    check("TOO EARLY: more than 30 days before the term ends the renewal is refused", r.status_code == 409 and r.json()["detail"]["code"] == "outside_renewal_window")
    nored = case("connect", "nr0", ends_in=-5)
    r = confirm(nored, "connect", redeem=False)
    check("RENEWAL WITHOUT POINTS: a plain renewal (redeem false) creates a full-price invoice and no redemption", r.status_code == 201 and r.json()["growth_points_discount_minor"] == 0 and r.json()["amount_due_minor"] == 300000
          and scalar("select count(*) from growth_point_redemptions where member_id = :m", m=nored["mid"]) == 0)

    # ======================================================================================== 7. IDEMPOTENCY, DOUBLE SPEND, CONCURRENCY, FORGERY
    dup = case("growth", "dup")
    q = quote(dup, "connect")
    first = confirm(dup, "connect", q=q)
    again = [confirm(dup, "connect", q=q) for _ in range(3)]
    check("IDEMPOTENT: a double click, a refresh and an API replay return the SAME renewal; one subscription, one invoice, one redemption, points used once", first.status_code == 201 and all(a.status_code == 201 and a.json()["replay"] and a.json()["invoice_id"] == first.json()["invoice_id"] for a in again)
          and scalar("select count(*) from growth_point_redemptions where member_id = :m", m=dup["mid"]) == 1 and scalar("select count(*) from subscriptions where user_id = :u and renews_subscription_id is not null", u=dup["mid"]) == 1
          and scalar("select total_points from growth_point_balances where member_id = :m", m=dup["mid"]) == 6000 - 4500)
    other = confirm(dup, "growth", q=quote(dup, "growth"))
    check("NO SECOND INVOICE: while a renewal is in progress, renewing into a different plan is refused (the same points can not be spent on two invoices)", other.status_code == 409 and other.json()["detail"]["code"] == "renewal_in_progress")
    conc = case("elite", "cc")
    qc = quote(conc, "growth")
    def hit(_):
        ratelimit._buckets.clear()
        r = conc["c"].post("/api/v1/renewal/confirm", json={"plan_code": "growth", "redeem": True, "expected_points": qc["points_to_be_redeemed"], "expected_discount_minor": qc["hypothetical_discount_paise"]}, headers=H(conc["c"]))
        return r.status_code
    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(hit, range(6)))
    check("CONCURRENT: six simultaneous renewals of the same cycle leave exactly one subscription, one invoice discount and one redemption; the points are spent once", scalar("select count(*) from growth_point_redemptions where member_id = :m and entry_type = 'REDEEM'", m=conc["mid"]) == 1
          and scalar("select count(*) from subscriptions where user_id = :u and renews_subscription_id is not null", u=conc["mid"]) == 1 and scalar("select total_points from growth_point_balances where member_id = :m", m=conc["mid"]) == 12000 - 7500
          and scalar("select coalesce(sum(points_redeemed), 0) from invoices where user_id = :u", u=conc["mid"]) == 7500, str(codes))
    fg = case("growth", "fg")
    qf = quote(fg, "connect")
    forged = [fg["c"].post("/api/v1/renewal/confirm", json={"plan_code": "connect", "redeem": True, **extra}, headers=H(fg["c"])).status_code
              for extra in ({"points": 99999}, {"discount_minor": 90000}, {"member_id": c0["mid"]}, {"invoice_id": "x"}, {"amount_due_minor": 1}, {"price": 1})]
    clear()
    badcalc = fg["c"].post("/api/v1/renewal/confirm", json={"plan_code": "connect", "redeem": True, "expected_points": 99999, "expected_discount_minor": 999990}, headers=H(fg["c"]))
    clear()
    nocsrf = fg["c"].post("/api/v1/renewal/confirm", json={"plan_code": "connect", "redeem": False})
    clear()
    anon = new_client().post("/api/v1/renewal/confirm", json={"plan_code": "connect", "redeem": False})
    clear()
    badplan = fg["c"].post("/api/v1/renewal/confirm", json={"plan_code": "platinum", "redeem": False}, headers=H(fg["c"]))
    check("FORGERY: extra fields (points, discount, member, invoice, amount, price) are rejected outright; a figure the member did not see changes nothing; no CSRF, no session and an unknown plan are refused",
          set(forged) == {422} and badcalc.status_code == 409 and badcalc.json()["detail"]["code"] == "calculation_changed" and nocsrf.status_code == 403 and anon.status_code == 401 and badplan.status_code == 422
          and scalar("select count(*) from growth_point_redemptions where member_id = :m", m=fg["mid"]) == 0)
    check("OLD ROUTE: POST /api/v1/growth-points/redeem is still a permanent refusal", (lambda r: r.status_code == 409 and r.json()["detail"]["code"] == "redemption_disabled")((clear(), early["c"].post("/api/v1/growth-points/redeem", json={"points": 100}, headers=H(early["c"])))[1]))
    other_member = case("connect", "idor")
    check("IDOR: a member can only renew and redeem their own cycle; another member's points never appear in their quote", quote(other_member, "growth")["eligible_old_cycle_points"] == 3600 and quote(fg, "connect")["eligible_old_cycle_points"] == 6000)

    # ======================================================================================== 8. REFUND, CANCELLATION AND REVERSAL
    rf = case("growth", "rf")
    qr = quote(rf, "growth")
    rr = confirm(rf, "growth", q=qr).json()
    snap_rf = earn_snapshot(rf["mid"])
    bal_used = scalar("select total_points from growth_point_balances where member_id = :m", m=rf["mid"])
    clear()
    rf["c"].post(f"/api/v1/subscriptions/{rr['subscription_id']}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(rf["c"]))
    admin.post(f"/api/admin/subscriptions/{rr['subscription_id']}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
    refund = admin.post(f"/api/admin/subscriptions/{rr['subscription_id']}/refund", json={"reason": "Customer asked for a refund"}, headers=AH)
    check("REFUND: before the sweep the points are still used (nothing is automatic inside the financial refund)", refund.status_code == 200 and scalar("select count(*) from growth_point_redemptions where entry_type = 'REVERSE' and member_id = :m", m=rf["mid"]) == 0)
    swept = asyncio.run(hooks._run("sweep", lambda s_: jobs.sweep(s_)))
    rev = rows("select entry_type, points, restored_points, created_by, reverses_id, invoice_id from growth_point_redemptions where member_id = :m and entry_type = 'REVERSE'", m=rf["mid"])
    check("REFUND: the sweep adds a NEW reverse record (the redemption stays); the points are restored in full because they have not expired; the invoice and payment records stay as they were",
          swept and len(rev) == 1 and rev[0][1:3] == (6000, 6000) and rev[0][3] == "system" and scalar("select discount_minor from invoices where id = :i", i=rev[0][5]) == 60000
          and scalar("select status from invoices where id = :i", i=rev[0][5]) == "REFUNDED")
    check("REFUND: balance restored, earning rows untouched, the reversal is audited, and a second sweep adds nothing", scalar("select total_points from growth_point_balances where member_id = :m", m=rf["mid"]) == 6000 and earn_snapshot(rf["mid"]) == snap_rf and bal_used == 0
          and scalar("select count(*) from audit_log where action = 'growth_points.redemption_reversed' and resource_id = :i", i=rev[0][5]) == 1)
    asyncio.run(hooks._run("sweep", lambda s_: jobs.sweep(s_)))
    check("REFUND: idempotent: still exactly one reversal", scalar("select count(*) from growth_point_redemptions where entry_type = 'REVERSE' and member_id = :m", m=rf["mid"]) == 1)
    # restoration never resurrects expired points
    ex = case("growth", "ex")
    qx = quote(ex, "growth")
    rx = confirm(ex, "growth", q=qx).json()
    async def cancel_it(s_):
        await s_.execute(text("update subscriptions set status = 'CANCELLED', cancelled_at = :t where id = :i"), {"t": utcnow(), "i": rx["subscription_id"]})
        await s_.commit()
    db(cancel_it)
    from app.models import GrowthPointRedemption
    async def reverse_after_expiry(s_):
        red_ = await s_.scalar(select(GrowthPointRedemption).where(GrowthPointRedemption.member_id == ex["mid"], GrowthPointRedemption.entry_type == "REDEEM"))
        return await service.reverse(s_, red_, created_by="system", reason="Cancelled, after the points' expiry", now=utcnow() + timedelta(days=400))
    revx = go(reverse_after_expiry)
    check("EXPIRY: a reversal AFTER the points' original expiry restores nothing (expired points are never resurrected), and says so", revx is not None and revx.restored_points == 0
          and scalar("select total_points from growth_point_balances where member_id = :m", m=ex["mid"]) == 0 and "expired_not_restored" in revx.details)
    cn = case("connect", "cn")
    qn = quote(cn, "connect")
    rn = confirm(cn, "connect", q=qn).json()
    clear()
    cancel_ = cn["c"].post(f"/api/v1/subscriptions/{rn['subscription_id']}/cancel", headers=H(cn["c"]))
    asyncio.run(hooks._run("sweep", lambda s_: jobs.sweep(s_)))
    check("CANCELLED UNPAID RENEWAL: cancelling before paying gives the points back (new reverse record) and the member can renew again", cancel_.status_code == 200 and scalar("select total_points from growth_point_balances where member_id = :m", m=cn["mid"]) == 3600
          and confirm(cn, "growth", q=quote(cn, "growth")).status_code == 201)

    # ======================================================================================== 9. KILL SWITCH AND ROLLOUT
    ks = case("growth", "ks")
    ops = new_client()
    async def mk_ops(s_):
        s_.add(Admin(email="ops2@tglseason.com", password_hash=hash_password(PASSWORD)))
        await s_.commit()
    db(mk_ops)
    assert ops.post("/api/auth/login", json={"email": "ops2@tglseason.com", "password": PASSWORD}).status_code == 200
    OH = {"X-CSRF-Token": ops.cookies.get("tgl_csrf") or ""}
    check("KILL SWITCH: an ordinary admin, a member and an anonymous visitor can not use it", ops.post("/api/admin/growth-points/redemption/kill", json={"reason": "Trying"}, headers=OH).status_code == 403
          and ks["c"].post("/api/admin/growth-points/redemption/kill", json={"reason": "Trying"}, headers=H(ks["c"])).status_code in (401, 403) and new_client().post("/api/admin/growth-points/redemption/kill", json={"reason": "x y z"}).status_code in (401, 403)
          and admin.post("/api/admin/growth-points/redemption/kill", json={"reason": "No token"}).status_code == 403)
    before_cnt = (scalar("select count(*) from growth_point_redemptions"), scalar("select coalesce(sum(discount_minor), 0) from invoices"), scalar("select count(*) from growth_point_ledger"), scalar("select coalesce(sum(total_points), 0) from growth_point_balances"))
    kill = admin.post("/api/admin/growth-points/redemption/kill", json={"reason": "Rehearsal of the emergency stop"}, headers=AH)
    rk = confirm(ks, "connect", q=quote(ks, "connect"))
    check("KILL SWITCH: the programme owner stops NEW redemptions at once (no restart); the attempt fails safely with the reason", kill.status_code == 200 and rk.status_code == 409 and rk.json()["detail"]["reason"] == "kill_switch"
          and scalar("select count(*) from growth_point_redemptions where member_id = :m", m=ks["mid"]) == 0)
    check("KILL SWITCH: nothing already done changes: redemptions, invoice discounts, ledger rows and balances are exactly as before", before_cnt == (scalar("select count(*) from growth_point_redemptions"), scalar("select coalesce(sum(discount_minor), 0) from invoices"),
          scalar("select count(*) from growth_point_ledger"), scalar("select coalesce(sum(total_points), 0) from growth_point_balances")))
    plain_ks = confirm(ks, "connect", redeem=False)
    check("KILL SWITCH: a plain renewal (no points) still works, at full price; members keep every point", plain_ks.status_code == 201 and plain_ks.json()["amount_due_minor"] == 300000 and scalar("select total_points from growth_point_balances where member_id = :m", m=ks["mid"]) == 6000)
    check("KILL SWITCH: it is recorded (audit and an append-only control row) and the state endpoint shows it", scalar("select count(*) from audit_log where action = 'growth_points.kill_switch_on'") == 1 and scalar("select count(*) from growth_point_controls where value = 'on'") == 1
          and admin.get("/api/admin/growth-points/redemption/state").json()["kill_switch_on"] is True and sql_fails("update growth_point_controls set value = 'off'") and sql_fails("delete from growth_point_controls"))
    resume = admin.post("/api/admin/growth-points/redemption/resume", json={"reason": "Rehearsal over, resuming"}, headers=AH)
    ks2 = case("growth", "ks2")
    check("KILL SWITCH: resuming (programme owner only) opens the gate again", resume.status_code == 200 and confirm(ks2, "connect", q=quote(ks2, "connect")).status_code == 201)
    open_gates("internal")
    stg = case("growth", "stg")
    r_int = confirm(stg, "connect", q=quote(stg, "connect"))
    app_settings.growth_points_rollout_stage = "cohort"
    app_settings.growth_points_rollout_emails = stg["email"]
    r_coh = confirm(stg, "connect", q=quote(stg, "connect"))
    open_gates("all")
    check("ROLLOUT: 'internal' admits only the programme owners (a member is refused: not_in_rollout); 'cohort' admits the listed members; the same logic applies at every stage", r_int.status_code == 409 and r_int.json()["detail"]["reason"] == "not_in_rollout" and r_coh.status_code == 201)
    app_settings.growth_points_rollout_emails = ""
    close_gates()
    off = case("growth", "off")
    qoff = quote(off, "connect")
    roff = off["c"].post("/api/v1/renewal/confirm", json={"plan_code": "connect", "redeem": True, "expected_points": 4500, "expected_discount_minor": 45000}, headers=H(off["c"]))
    check("FLAG OFF: with redemption disabled the quote is a labelled PREVIEW that applies to no invoice, and redeeming is refused (reason redemption_disabled)", qoff["mode"] == "PREVIEW" and qoff["applies_to_invoice"] is False and qoff["hypothetical_only"] is True
          and roff.status_code == 409 and roff.json()["detail"]["reason"] == "redemption_disabled")
    app_settings.growth_points_member_preview = False
    check("FLAG OFF + PREVIEW OFF: the member sees only 'coming soon', never an amount", quote(off, "connect") == {"enabled": False, "message": "Growth Points are coming soon. They are not active yet and cannot be redeemed."}
          and off["c"].get("/api/v1/growth-points/history").json()["enabled"] is False)
    app_settings.growth_points_member_preview = True
    open_gates("all")

    # ======================================================================================== 10. MEMBER HISTORY, FINANCE, RECONCILIATION, AUDIT
    hist = rf["c"].get("/api/v1/growth-points/history").json()
    check("MEMBER HISTORY: the member's OWN earned, expired, reversed points with a plain reason; no counterparty, no fraud flag, no other member", hist["enabled"] and hist["total"] > 0 and not re.search(r"counterparty|pair|flag|capped_by|member_id|prospect", json.dumps(hist))
          and {i["kind"] for i in hist["items"]} <= {"EARN", "VOID", "REVERSAL", "EXPIRY"} and "not cash" in hist["terms"])
    fin = admin.get("/api/admin/growth-points/finance").json()
    gross = scalar("select coalesce(sum(discount_paise), 0) from growth_point_redemptions where entry_type = 'REDEEM'")
    back = scalar("select coalesce(sum(discount_paise), 0) from growth_point_redemptions where entry_type = 'REVERSE'")
    check("FINANCE: realized cost = redemptions minus reversals, kept apart from modelled and shadow figures; outstanding potential liability separate", fin["realized"]["realized_reward_cost_paise"] == gross - back and fin["realized"]["gross_discount_paise"] == gross
          and "outstanding_potential_liability" in fin and "points" in fin and "never added together" in fin["separate_from"] and {p["plan"] for p in fin["realized"]["by_plan"]} >= {"connect", "growth"}
          and ob_ok(admin) and ops.get("/api/admin/growth-points/finance").status_code == 200 and fin["realized"]["redemptions"] == (scalar("select count(*) from growth_point_redemptions where entry_type = 'REDEEM'") - scalar("select count(*) from growth_point_redemptions where entry_type = 'REVERSE'")))
    exp = admin.get("/api/admin/growth-points/redemptions/export")
    check("ACCOUNTING OUTPUT: a CSV of every redemption and reversal with its invoice number, list price, discount, amount due, plan, term and rule version, for professional review; no names, emails or phones",
          exp.status_code == 200 and exp.text.splitlines()[0].startswith("redemption_id,entry_type") and len(exp.text.splitlines()) - 1 == scalar("select count(*) from growth_point_redemptions") and "@" not in exp.text and "no-store" in exp.headers["cache-control"]
          and rf["c"].get("/api/admin/growth-points/redemptions/export").status_code == 401)
    pv_open = early["c"].get("/api/v1/growth-points/preview").json()
    check("MEMBER CARD: the points card knows whether redemption is open for this member (so it never says 'not active' while a renewal discount is available)", pv_open["redemption_open"] is True)
    check("FINANCE: members can not see it", rf["c"].get("/api/admin/growth-points/finance").status_code == 401 and new_client().get("/api/admin/growth-points/redemptions").status_code == 401)
    rec = reconcile_all()
    check("RECONCILIATION: ledger = balances, redemptions = lot lines = invoice discounts, every reversal complete, no expired lot redeemed, no cycle or pair ceiling broken", rec["ok"], str({k: rec[k] for k in ("drift", "violations")})[:500])
    cost = go(lambda s_: __import__("app.rewards.analytics", fromlist=["x"]).real_financial_cost(s_))
    check("REAL COST IS EXPLAINED: the invoice discounts given equal the recorded redemptions to the paisa", cost["ok"] and cost["inr_minor"] == cost["recorded_redemption_discount_minor"] == gross and cost["inr_minor"] > 0, str(cost))
    check("AUDIT: every redemption is audited (who, invoice, points, discount, lots) and every reversal and switch is audited", scalar("select count(*) from audit_log where action = 'growth_points.redeemed'") == scalar("select count(*) from growth_point_redemptions where entry_type = 'REDEEM'")
          and scalar("select count(*) from audit_log where action = 'growth_points.redemption_reversed'") == scalar("select count(*) from growth_point_redemptions where entry_type = 'REVERSE'"))
    check("APPEND-ONLY: the redemption records, their lot lines and the controls can not be edited or deleted, even with SQL", sql_fails("update growth_point_redemptions set points = 1") and sql_fails("delete from growth_point_redemptions")
          and sql_fails("update growth_point_redemption_lots set delta = -1") and sql_fails("delete from growth_point_redemption_lots"))
    tamper_before = scalar("select total_points from growth_point_balances where member_id = :m", m=hist_member(rf))
    async def tamper(s_):
        await s_.execute(text("update growth_point_balances set total_points = total_points + 11 where member_id = :m"), {"m": rf["mid"]})
        await s_.commit()
    db(tamper)
    bad = reconcile_all()
    alert = go(lambda s_: jobs.reconcile_alert(s_))
    check("RECONCILIATION: a corrupted balance is detected, raises a HIGH admin alert, and is NOT silently repaired", not bad["ok"] and alert["new_alerts"] >= 1 and scalar("select total_points from growth_point_balances where member_id = :m", m=rf["mid"]) == tamper_before + 11)
    async def untamper(s_):
        await s_.execute(text("update growth_point_balances set total_points = total_points - 11 where member_id = :m"), {"m": rf["mid"]})
        await s_.commit()
    db(untamper)

    # ======================================================================================== 11. STATIC SAFETY: where the money code lives
    app_dir = os.path.join(ROOT, "app")
    def src(p):
        return open(os.path.join(app_dir, p)).read()
    rewards_src = " ".join(open(os.path.join(app_dir, "rewards", f)).read() for f in os.listdir(os.path.join(app_dir, "rewards")) if f.endswith(".py"))
    check("ISOLATION: the shadow reward engine (app/rewards) writes no financial table and never imports the redemption package at module level", not re.search(r"\b(update|delete|insert)\(\s*(Invoice|Payment|Subscription|Plan)\b|\.(discount_minor|amount_due_minor|price_minor)\s*=[^=]|\.add\(\s*(Invoice|Payment|Subscription|Plan)\(", rewards_src)
          and not re.search(r"^from \.\.redemption|^import app\.redemption", rewards_src, re.M))
    red_src = src("redemption/service.py")
    check("ISOLATION: the redemption package never edits or deletes an earning row (it only adds records and lot lines)", not re.search(r"update\(\s*GrowthPointLedger|delete\(\s*GrowthPointLedger|GrowthPointLedger\)\.values|\.points_delta\s*=[^=]|\.remaining\s*=[^=]", red_src))
    financial = [p for p in os.listdir(app_dir) if re.search(r"subscri|invoice|payment|pricing", p) and p.endswith(".py")]
    check("ISOLATION: no existing financial module imports the rewards or redemption packages (the renewal route is the only bridge)", financial and not [p for p in financial if re.search(r"rewards|redemption|growth_point", src(p))])
    check("ISOLATION: the early-renewal start date is the only change in the subscription router, and it names no points", "redemption" not in src("routers/subscriptions.py") and "growth_point" not in src("routers/subscriptions.py") and "rewards" not in src("routers/subscriptions.py"))
    check("COUPON RULE: no coupon exists in the product, so the 'other discount' is 0; the 80% combined floor and 15% points cap are enforced in the service AND by database CHECKs", "COMBINED_FLOOR_PERCENT = 80" in red_src and "ck_invoice_payment_floor" in open(os.path.join(ROOT, "migrations/versions/0011_redemption_infrastructure.py")).read())

    # ======================================================================================== 12. 10,000-OPERATION REDEMPTION SIMULATION
    import random
    rng = random.Random(20261010)
    ops_done = {"award": 0, "redeem": 0, "reverse": 0, "plain": 0}
    sim_members = []
    async def make_members(s_, n):
        plan_by_code = {p.code: p for p in (await s_.execute(select(Plan))).scalars().all()}
        admin_id = await s_.scalar(select(Admin.id).limit(1))
        out_ = []
        for i in range(n):
            code = rng.choice(["connect", "growth", "elite"])
            u = User(email=f"sim2-{i}@example.com", password_hash="x", is_active=True, email_verified_at=utcnow())
            s_.add(u)
            await s_.flush()
            sub, inv_, pay = build_purchase(u.id, plan_by_code[code])
            ends = utcnow() + timedelta(days=rng.choice([-25, -5, 5, 20]))
            starts = ends - timedelta(days=round(MONTHS[code] * 30.4375))
            sub.status, sub.starts_at, sub.expires_at, sub.activated_at = ("ACTIVE" if ends > utcnow() else "EXPIRED"), starts, ends, starts
            s_.add(sub)
            await s_.flush()
            inv_.subscription_id = sub.id
            inv_.status, inv_.amount_paid_minor, inv_.paid_at = "PAID", inv_.amount_due_minor, starts
            s_.add(inv_)
            await s_.flush()
            pay.invoice_id, pay.status, pay.verified_at, pay.verified_by_admin_id = inv_.id, "VERIFIED", starts, admin_id
            s_.add(pay)
            out_.append((u.id, code, starts, ends))
        return out_
    sim_members = go(lambda s_: make_members(s_, 1800))
    for mid, code, starts, ends in sim_members:
        for k in range(rng.randint(2, 7)):
            ev = rng.choice([("MEETING_COMPLETED", 60, 3, "referral"), ("BUSINESS_CLOSED", rng.choice([210, 525, 1050, 1890]), 4, "deal_closure"), ("PROFILE_COMPLETED", 75, 3, "member")])
            at = starts + timedelta(days=rng.randint(1, max(2, round(MONTHS[code] * 30) - 2)), hours=rng.randint(0, 20))
            if at < utcnow():
                award(mid, ev[0], f"s2-{mid[:8]}-{k}", ev[1], ev[2], at, ev[3], "referrer" if ev[0] == "BUSINESS_CLOSED" else "member")
                ops_done["award"] += 1
    async def renew_one(mid, plan_code, redeem):
        async with SessionLocal() as s_:
            user = await s_.get(User, mid)
            q_ = await service.quote(s_, user, plan_code)
            try:
                res = await service.confirm(s_, user, plan_code, redeem=redeem, expected_points=q_["points_to_be_redeemed"] if redeem else None, expected_discount_minor=q_["hypothetical_discount_paise"] if redeem else None)
                await s_.commit()
                return res
            except Exception:
                await s_.rollback()
                return None
    results_sim = []
    for mid, code, starts, ends in sim_members:
        tgt = rng.choice(["connect", "growth", "elite"])
        res = asyncio.run(renew_one(mid, tgt, rng.random() < 0.85))
        if res:
            results_sim.append((mid, res))
            ops_done["redeem" if res["points_redeemed"] else "plain"] += 1
    async def cancel_some(s_):
        n_ = 0
        for mid, res in results_sim:
            if rng.random() < 0.3:
                await s_.execute(text("update subscriptions set status = 'CANCELLED', cancelled_at = :t where id = :i"), {"t": utcnow(), "i": res["subscription_id"]})
                n_ += 1
        return n_
    cancelled = go(cancel_some)
    for _ in range(3):
        ops_done["reverse"] += asyncio.run(hooks._run("sweep", lambda s_: service.reverse_dead_renewals(s_))) or 0
    total_ops = sum(ops_done.values())
    rec = reconcile_all()
    check(f"SIMULATION: {total_ops} operations on {len(sim_members)} members {ops_done} ({cancelled} renewals cancelled): reconciliation clean: no drift, no double spend, no orphan redemption, no orphan invoice discount, no expired lot redeemed, no cap or floor violated", rec["ok"], str({k: rec[k] for k in ("drift", "violations")})[:600])
    check("SIMULATION: no negative balance; no invoice discount above 15% or amount due below 85% (the points-only floor); every discounted invoice has exactly one redemption", scalar("select count(*) from growth_point_balances where total_points < 0") == 0
          and scalar("select count(*) from invoices where points_discount_minor * 100 > list_price_minor * 15 or amount_due_minor * 100 < list_price_minor * 85") == 0
          and scalar("select count(*) from invoices i where i.points_discount_minor > 0 and (select count(*) from growth_point_redemptions r where r.invoice_id = i.id and r.entry_type = 'REDEEM') <> 1") == 0)
    check("SIMULATION: every redeemed point is accounted for: total used = lot lines; restored only up to expiry; points per lot never negative", scalar("select count(*) from (select lot_id from growth_point_redemption_lots group by lot_id having sum(delta) > 0) x") == 0
          and not [d for d in rec["drift"] if "negative" in str(d)])

    # ======================================================================================== 13. THE GATES STILL KEEP PRODUCTION CLOSED
    close_gates()
    service._gate_a_passed = saved_gate
    service._gate_a_cache.update(at=0.0)
    gt = admin.get("/api/admin/growth-points/gates").json()
    check("PRODUCTION STATE: with the flags at their defaults the gates report redemption can NOT be enabled (Gate A is not met: there is no real observation data)", gt["redemption_can_be_enabled"] is False and gt["gate_a"]["passed"] is False and gt["environment"]["items"][0]["status"] == "MET")

    passed = sum(1 for ok, _ in results if ok)
    print()
    for ok, name in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


def ob_ok(admin) -> bool:
    return admin.get("/api/admin/growth-points/redemptions").status_code == 200


def reconcile_all() -> dict:
    return go(lambda s_: reconcile.reconcile(s_))


def hist_member(cs) -> str:
    return cs["mid"]


if __name__ == "__main__":
    try:
        code_ = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code_)
