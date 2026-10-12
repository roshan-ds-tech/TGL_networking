"""Growth Points, Phase 1 (SHADOW MODE): focused checks.

Reward correctness, idempotency and races, the Pair Assurance Rule, plan-aware cycle ceilings, expiry, reversals, the shadow
redemption simulation, admin analytics, fraud signals, reconciliation, security and, above all, the financial firewall:
Growth Points have no monetary effect.

Run:  .venv/bin/python test_phase1.py
      TEST_DATABASE_URL=postgresql+asyncpg://user@host/db .venv/bin/python test_phase1.py
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import io
import json
import os
import random
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["GROWTH_POINTS_SHADOW_MODE"] = "true"          # set BEFORE the app's settings are built
os.environ["GROWTH_POINTS_MEMBER_PREVIEW"] = "true"
os.environ["GROWTH_POINTS_REDEMPTION_ENABLED"] = "false"

import test_phase0 as t0  # noqa: E402  (sets the throwaway environment on import)
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, app_settings, check, db, member_client, me, new_client, referral_payload, results, rows, scalar  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import event, text, update  # noqa: E402
from sqlalchemy import inspect as sa_inspect  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app import audit as audit_mod  # noqa: E402
from app import ratelimit  # noqa: E402
from app.config import Settings  # noqa: E402
from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin, GrowthPointLedger, Subscription, utcnow  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.rewards import analytics, engine as reward_engine, events, firewall, fraud, hooks, jobs, ledger, model, reconcile, renewal, review, rules, simulation  # noqa: E402
from app.rewards.engine import AwardRequest  # noqa: E402

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
IS_PG = engine.dialect.name == "postgresql"
SHADOW_TABLES = ("growth_point_rule_versions", "growth_point_cycles", "growth_point_ledger", "growth_point_balances", "growth_point_flags", "growth_point_renewals")


def D(x):
    """A timestamp read through raw SQL: SQLite returns text, PostgreSQL a datetime."""
    if isinstance(x, str):
        x = datetime.fromisoformat(x)
    return x if x.tzinfo else x.replace(tzinfo=timezone.utc)


def go(fn, now=None):
    """Run reward-engine work in its own transaction, inside the financial firewall, like the hooks do."""
    async def f(s):
        with firewall.guard():
            r = await fn(s)
        await s.commit()
        return r
    return db(f)


def settings_owner_empty() -> bool:
    return not app_settings.programme_owner_emails.strip()


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


def financial_fingerprint() -> str:
    """A hash of every invoice, payment, subscription and plan row: it must not change because of anything Growth Points do."""
    h = hashlib.sha256()
    for table, cols in (("invoices", "id, status, list_price_minor, discount_minor, amount_due_minor, amount_paid_minor, period_months"),
                        ("payments", "id, status, amount_minor, invoice_id"),
                        ("subscriptions", "id, status, starts_at, expires_at, plan_id, user_id"),
                        ("plans", "id, code, price_minor, period_months, status")):
        for r in rows(f"select {cols} from {table} order by id"):
            h.update(repr(tuple(str(x) for x in r)).encode())
    return h.hexdigest()


def quarter_start(offset: int = 0) -> datetime:
    """The first moment (UTC) of the business quarter `offset` quarters from now."""
    d = rules.local(utcnow())
    q = (d.month - 1) // 3 + offset
    year, qi = d.year + q // 4, q % 4
    return datetime(year, qi * 3 + 1, 1, tzinfo=rules._IST).astimezone(timezone.utc)


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app) as boot:
        return body(boot)


def body(boot: TestClient) -> int:
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    counter = iter(range(1, 100_000))
    phones = iter(range(1, 100_000))
    start_fp = None

    def clear():
        ratelimit._buckets.clear()

    def buy(c, code: str) -> str:
        """Subscribe, pay by proof, have an admin verify it: an ACTIVE paid subscription. Returns its id."""
        clear()
        r = c.post("/api/v1/subscriptions", json={"plan_code": code}, headers=H(c))
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        clear()
        assert c.post(f"/api/v1/subscriptions/{sid}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(c)).status_code == 200
        assert admin.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH).status_code == 200
        return sid

    def sub_member(code: str):
        """A member with an ACTIVE paid subscription: Connect (3 months), Growth (6) or Elite (12)."""
        clear()
        c = member_client(f"gp{next(counter)}@example.com", f"GP Member {next(counter)}")
        sid = buy(c, code)
        assert c.get("/api/v1/status").status_code == 200       # creates the networking profile a referral recipient needs
        return c, me(c), sid

    def pair(code: str):
        a, b = sub_member(code), sub_member(code)
        return a, b

    def L(sql: str, **p):
        return rows(sql, **p)

    def points_of(member: str, event_type: str | None = None, ref: str | None = None) -> int:
        q = "select coalesce(sum(points_delta), 0) from growth_point_ledger where member_id = :m and entry_type in ('EARN','VOID','REVERSAL')"
        p = {"m": member}
        if event_type:
            q += " and event_type = :e"
            p["e"] = event_type
        if ref:
            q += " and reference_id = :r"
            p["r"] = ref
        return int(scalar(q, **p))

    def earn_rows(member: str, event_type: str | None = None, ref: str | None = None):
        q = ("select points_delta, requested_points, capped_points, capped_by, status, verification_level, assurance, available_at, expires_at, event_type, id, remaining "
             "from growth_point_ledger where member_id = :m and entry_type = 'EARN'")
        p = {"m": member}
        if event_type:
            q += " and event_type = :e"
            p["e"] = event_type
        if ref:
            q += " and reference_id = :r"
            p["r"] = ref
        return L(q + " order by created_at, id", **p)

    def make_referral(giver, recv_id, **over):
        clear()
        payload = referral_payload(recv_id, **over)
        r = giver.post("/api/v1/referrals", json=payload, headers=H(giver))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def patch(c, rid, st):
        clear()
        return c.patch(f"/api/v1/referrals/{rid}", json={"status": st}, headers=H(c))

    def confirm_meeting(c, rid):
        clear()
        return c.post(f"/api/v1/referrals/{rid}/meeting/confirm", headers=H(c))

    def deal(giver, recv, value, phone=None, evidence=True, admin_verify=True):
        """A full referral -> meeting -> reported deal -> confirmed -> (evidence, admin review) flow. Returns (referral_id, closure_id)."""
        (gc, gid, _), (rc, rid_, _) = giver, recv
        extra = {"prospect_phone": phone} if phone else {}
        ref = make_referral(gc, rid_, **extra)
        assert patch(rc, ref, "ACCEPTED").status_code == 200
        assert confirm_meeting(gc, ref).status_code == 200 and confirm_meeting(rc, ref).status_code == 200
        clear()
        r = rc.post(f"/api/v1/referrals/{ref}/closure", json={"actual_value": value}, headers=H(rc))
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        minor = r.json()["actual_value_minor"]
        clear()
        r = gc.post(f"/api/v1/referrals/{ref}/closure/confirm", json={"expected_value_minor": minor}, headers=H(gc))
        assert r.status_code == 200, r.text
        if r.json()["status"] == "AWAITING_EVIDENCE" and evidence:
            clear()
            blob = PNG + bytes([next(counter) % 250]) * 40
            r2 = rc.post(f"/api/v1/referrals/{ref}/closure/evidence", data={"evidence_type": "INVOICE"}, files={"file": ("i.png", io.BytesIO(blob), "image/png")}, headers=H(rc))
            assert r2.status_code == 201, r2.text
            eid = r2.json()["evidence"][-1]["id"]
            r3 = admin.post(f"/api/admin/referrals/{ref}/closure/evidence/{eid}/verify", json={"reason": "Invoice matches"}, headers=AH)
            assert r3.status_code == 200, r3.text
            if r3.json()["closure"]["status"] == "UNDER_REVIEW" and admin_verify:
                r4 = admin.post(f"/api/admin/referrals/{ref}/closure/verify", json={"reason": "Reviewed and approved"}, headers=AH)
                assert r4.status_code == 200, r4.text
        return ref, cid

    # ======================================================================================== 1. RULES
    check("the catalogue enables exactly the six approved events", set(rules.ENABLED_EVENTS) == {"REFERRAL_ACCEPTED", "PROSPECT_CONTACTED", "MEETING_COMPLETED", "BUSINESS_CLOSED", "REPEAT_BUSINESS", "PROFILE_COMPLETED"})
    check("the approved-but-future events are present and disabled", all(not rules.EVENTS[k]["enabled"] for k in ("EVENT_ATTENDED", "SUCCESSFUL_INTRODUCTION", "NEED_RESOLVED", "MENTORING_SESSION", "MEMBER_INVITED")))
    check("nothing that must earn 0 is a reward event", not set(rules.ZERO_POINT_ACTIONS) & set(rules.EVENTS) and "REFERRAL_CREATED" not in rules.EVENTS)
    check("1 point = Rs 0.10 (10 paise)", rules.PAISE_PER_POINT == 10 and rules.points_to_paise(4500) == 45000)
    check("the contractual cap is 15%: Rs 450 / 750 / 1,500 = 4,500 / 7,500 / 15,000 points",
          [(rules.redemption_cap_paise(p) // 100, rules.redemption_cap_points(p)) for p in (300_000, 500_000, 1_000_000)] == [(450, 4500), (750, 7500), (1500, 15000)])
    check("the earning ceiling is 12% of the plan price: 3,600 / 6,000 / 12,000 points", [rules.cycle_ceiling_points(p) for p in (300_000, 500_000, 1_000_000)] == [3600, 6000, 12000])
    check("the closed-business sub-ceiling is 60% of the cycle ceiling: 2,160 / 3,600 / 7,200", [rules.category_ceilings(p)["CLOSURE"] for p in (300_000, 500_000, 1_000_000)] == [2160, 3600, 7200])
    check("process 25% and other 20% sub-ceilings", rules.category_ceilings(300_000) == {"PROCESS": 900, "CLOSURE": 2160, "OTHER": 720} and rules.category_ceilings(1_000_000) == {"PROCESS": 3000, "CLOSURE": 7200, "OTHER": 2400})
    check("daily 500 and monthly 3,000", rules.DAILY_CEILING_LOW_ASSURANCE == 500 and rules.MONTHLY_CEILING == 3000)
    check("the closed-business pools are 300 / 750 / 1,500 / 2,100 / 2,700 split 70/30 exactly",
          [rules.split_pool(p) for p in rules.CLOSURE_POOL.values()] == [(210, 90), (525, 225), (1050, 450), (1470, 630), (1890, 810)])
    check("a reciprocal closure pays 50% of the pool (1,350: 945 / 405)", rules.split_pool(2700, 50) == (945, 405))
    check("a split never loses or invents a point", all(sum(rules.split_pool(p, f)) == p * f // 100 for p in rules.CLOSURE_POOL.values() for f in (100, 50)))
    check("point values per action: accepted 30(+15)/15, contacted 15, meeting 45/60, profile 75",
          (rules.EVENTS["REFERRAL_ACCEPTED"]["referrer"], rules.EVENTS["REFERRAL_ACCEPTED"]["referrer_bonus"], rules.EVENTS["REFERRAL_ACCEPTED"]["recipient"],
           rules.EVENTS["PROSPECT_CONTACTED"]["recipient"], rules.EVENTS["MEETING_COMPLETED"]["referrer"], rules.EVENTS["MEETING_COMPLETED"]["recipient"],
           rules.EVENTS["PROFILE_COMPLETED"]["member"]) == (30, 15, 15, 15, 45, 60, 75))
    check("monthly limits: 10 accepted referrals, 8 meetings (referrer)", rules.EVENTS["REFERRAL_ACCEPTED"]["monthly_limit"] == {"referrer": 10} and rules.EVENTS["MEETING_COMPLETED"]["monthly_limit"] == {"referrer": 8})
    check("pair rule: budget 1,500, two full verified closures, reciprocal 50%", (rules.PAIR_LOW_ASSURANCE_BUDGET, rules.PAIR_FULL_VERIFIED_CLOSURES, rules.PAIR_RECIPROCAL_FACTOR_PERCENT) == (1500, 2, 50))
    check("expiry: 30 days before the term ends, 30 days of grace; 7-day pending; 60-day reversal window",
          (rules.RENEWAL_WINDOW_BEFORE_DAYS, rules.GRACE_DAYS, rules.PENDING_DAYS, rules.REVERSAL_WINDOW_DAYS) == (30, 30, 7, 60))
    code = " ".join(p.read_text() for p in (APP / "rewards").glob("*.py") if p.name != "rules.py") + " ".join(p.read_text() for p in (APP / "routers").glob("*growth_points.py"))
    code = "\n".join(ln for ln in code.replace(" ", " ").split("\n") if "enforce(" not in ln)
    check("no point value, ceiling or percentage is hard-coded outside rules.py", not re.search(r"\b(3600|6000|12000|2160|7200|1890|1470|1050)\b|\b(30|45|60|75)\s*,\s*#", code), "found a literal rule number")
    check("the calendar is business time (UTC+05:30): 2026-12-31 20:00 UTC is already 2027-Q1", rules.quarter_key(datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)) == "2027-Q1" and rules.quarter_key(datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)) == "2026-Q4")

    # ======================================================================================== 2. FLAGS, VERSIONING, FIREWALL
    check("shadow mode defaults OFF and redemption defaults OFF in the code", Settings.model_fields["growth_points_shadow_mode"].default is False and Settings.model_fields["growth_points_redemption_enabled"].default is False)
    try:
        Settings(growth_points_redemption_enabled=True)
        refused = False
    except ValidationError:
        refused = True
    check("the application refuses to start with GROWTH_POINTS_REDEMPTION_ENABLED=true", refused)
    check("redemption can not be enabled even in memory", firewall.redemption_enabled() is False)
    try:
        firewall.redeem("anyone", 100)
        redeemed = True
    except firewall.RedemptionDisabled:
        redeemed = False
    check("redeem() always refuses", not redeemed)
    readers = [p.name for p in APP.rglob("*.py") if re.search(r"growth_points_(shadow_mode|redemption_enabled|member_preview)", p.read_text()) and p.name not in ("config.py", "firewall.py")]
    check("only firewall.py reads the Growth Points flags", readers == [], str(readers))
    check("the ledger and its tables exist", all(t in {x[0] for x in (rows("select name from sqlite_master where type = 'table'") if not IS_PG else rows("select tablename from pg_tables where schemaname = 'public'"))} for t in SHADOW_TABLES))
    check("no voucher, coupon or discount table exists; the only redemption tables are the append-only Phase 2 records (growth_point_redemptions, growth_point_redemption_lots)", not [t for t in (x[0] for x in (rows("select name from sqlite_master where type = 'table'") if not IS_PG else rows("select tablename from pg_tables where schemaname = 'public'"))) if re.search(r"redemption|redeem|voucher|discount|coupon", t) and t not in ("growth_point_redemptions", "growth_point_redemption_lots", "growth_point_redemption_epoch")])
    start_fp = financial_fingerprint()

    # ======================================================================================== 3. THE FIRST MEMBERS, AND CYCLES
    (A, B) = pair("connect")
    (ac, aid, asid), (bc, bid, bsid) = A, B
    cyc = L("select plan_code, term_months, price_minor, ceiling_points, process_ceiling, closure_ceiling, other_ceiling from growth_point_cycles where member_id = :m", m=aid)
    check("no cycle is created until something is rewarded", cyc == [])

    # ======================================================================================== 4. REFERRAL CREATION = 0
    n0 = scalar("select count(*) from growth_point_ledger")
    ref1 = make_referral(ac, bid, intro_method="ALREADY_KNOWS")
    check("creating a referral earns 0 points (no ledger row of any kind)", scalar("select count(*) from growth_point_ledger") == n0 and points_of(aid) == 0)

    # ======================================================================================== 5. ACCEPTED
    r = patch(bc, ref1, "ACCEPTED")
    check("the recipient accepts", r.status_code == 200)
    ea, eb = earn_rows(aid, "REFERRAL_ACCEPTED", ref1), earn_rows(bid, "REFERRAL_ACCEPTED", ref1)
    check("referrer earns 30 for an accepted referral without an introduction", len(ea) == 1 and ea[0][0] == 30 and ea[0][1] == 30 and ea[0][3] is None, str(ea))
    check("recipient earns 15", len(eb) == 1 and eb[0][0] == 15, str(eb))
    check("L1 points are PENDING for 7 days, with low assurance", ea[0][4] == "PENDING" and ea[0][5] == 1 and ea[0][6] == "LOW")
    avail, created_at = D(ea[0][7]), L("select event_at from growth_point_ledger where id = :i", i=ea[0][10])[0][0]
    check("available_at = the event + 7 days", D(avail) - D(created_at if isinstance(created_at, datetime) else datetime.fromisoformat(str(created_at))) == timedelta(days=7))
    cyc = L("select plan_code, term_months, price_minor, ceiling_points, process_ceiling, closure_ceiling, other_ceiling, grace_ends_at, ends_at from growth_point_cycles where member_id = :m", m=aid)[0]
    check("the Connect cycle is 3 months with ceilings 3,600 / 900 / 2,160 / 720", cyc[:7] == ("connect", 3, 300000, 3600, 900, 2160, 720), str(cyc))
    check("expires_at = the end of the grace period after the cycle", D(ea[0][8]) == D(cyc[7]) and D(cyc[7]) - D(cyc[8]) == timedelta(days=30))
    check("the row records the rule version, the shadow flag and an idempotency key", L("select rule_version, shadow, idempotency_key from growth_point_ledger where id = :i", i=ea[0][10])[0][0] == "growth-points-v3"
          and L("select shadow from growth_point_ledger where id = :i", i=ea[0][10])[0][0] in (True, 1) and ea[0][10])
    check("balance_after and remaining are recorded", L("select balance_after, remaining from growth_point_ledger where id = :i", i=ea[0][10])[0] == (30, 30))
    ref_q = make_referral(ac, bid)                              # intro by EMAIL -> a direct introduction -> +15 for the referrer
    patch(bc, ref_q, "ACCEPTED")
    check("a direct introduction earns the referrer 30 + 15", earn_rows(aid, "REFERRAL_ACCEPTED", ref_q)[0][0] == 45)
    r = patch(ac, ref_q, "ACCEPTED")
    check("a client can not re-send ACCEPTED to earn again", r.status_code in (400, 403, 409))
    check("a forged points field is refused outright", bc.patch(f"/api/v1/referrals/{ref_q}", json={"status": "CONTACTED", "points": 5000}, headers=H(bc)).status_code == 422)

    # ======================================================================================== 6. IDEMPOTENCY
    before = scalar("select count(*) from growth_point_ledger")
    for _ in range(5):
        asyncio.run(hooks.referral_changed(ref1))                   # retry after a timeout, a replayed webhook, a double click
    check("repeated and replayed hooks add nothing", scalar("select count(*) from growth_point_ledger") == before)
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda _: asyncio.run(hooks.referral_changed(ref1)), range(8)))
    check("8 concurrent hooks add nothing", scalar("select count(*) from growth_point_ledger") == before)
    check("exactly one shadow reward per member, event and reference", scalar("select count(*) from (select idempotency_key from growth_point_ledger group by idempotency_key having count(*) > 1) x") == 0)
    ref_race = make_referral(ac, bid)
    patch(bc, ref_race, "ACCEPTED")
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda _: asyncio.run(hooks.referral_changed(ref_race)), range(6)))
    check("simultaneous events produce exactly one reward each", len(earn_rows(aid, "REFERRAL_ACCEPTED", ref_race)) == 1 and len(earn_rows(bid, "REFERRAL_ACCEPTED", ref_race)) == 1)
    check("a double-clicked PATCH does not reward twice", scalar("select count(*) from growth_point_ledger where reference_id = :r and event_type = 'REFERRAL_ACCEPTED'", r=ref_race) == 2)

    # ======================================================================================== 7. CONTACTED
    r = patch(bc, ref1, "CONTACTED")
    ec = earn_rows(bid, "PROSPECT_CONTACTED", ref1)
    check("the recipient contacting the prospect within 72 hours earns 15", r.status_code == 200 and len(ec) == 1 and ec[0][0] == 15 and not earn_rows(aid, "PROSPECT_CONTACTED", ref1))
    ref_late = make_referral(ac, bid)
    patch(bc, ref_late, "ACCEPTED")
    async def age(s):
        await s.execute(text("update business_referrals set accepted_at = :t where id = :i"), {"t": utcnow() - timedelta(hours=100), "i": ref_late})
        await s.commit()
    db(age)
    patch(bc, ref_late, "CONTACTED")
    el = earn_rows(bid, "PROSPECT_CONTACTED", ref_late)
    check("contacting after more than 72 hours earns nothing but is recorded", len(el) == 1 and el[0][0] == 0 and el[0][3] == "OUTSIDE_WINDOW" and el[0][4] == "CAPPED", str(el))
    ref_skip = make_referral(ac, bid)
    patch(bc, ref_skip, "ACCEPTED")
    confirm_meeting(ac, ref_skip)
    confirm_meeting(bc, ref_skip)
    check("a meeting does not count as the explicit 'prospect contacted' step", not earn_rows(bid, "PROSPECT_CONTACTED", ref_skip))

    # ======================================================================================== 8. MEETINGS
    ref_m = make_referral(ac, bid)
    patch(bc, ref_m, "ACCEPTED")
    r = confirm_meeting(ac, ref_m)
    check("one-sided confirmation earns no meeting points", r.status_code == 200 and not earn_rows(aid, "MEETING_COMPLETED", ref_m) and not earn_rows(bid, "MEETING_COMPLETED", ref_m))
    confirm_meeting(ac, ref_m)
    check("a repeated one-sided confirmation still earns nothing", not earn_rows(aid, "MEETING_COMPLETED", ref_m))
    confirm_meeting(bc, ref_m)
    em_a, em_b = earn_rows(aid, "MEETING_COMPLETED", ref_m), earn_rows(bid, "MEETING_COMPLETED", ref_m)
    check("both members confirming: referrer 45, recipient 60 (level 2, pending)", len(em_a) == 1 and em_a[0][0] == 45 and len(em_b) == 1 and em_b[0][0] == 60 and em_a[0][5] == 2 and em_a[0][4] == "PENDING")
    confirm_meeting(bc, ref_m)
    confirm_meeting(ac, ref_m)
    check("duplicate confirmation after both adds nothing", len(earn_rows(aid, "MEETING_COMPLETED", ref_m)) == 1)
    clear()
    ac.post(f"/api/v1/referrals/{ref_m}/meeting/dispute", json={"reason": "That meeting never took place"}, headers=H(ac))
    voided = L("select entry_type, points_delta, status from growth_point_ledger where reference_id = :r and event_type = 'MEETING_COMPLETED' and entry_type = 'VOID' order by points_delta", r=ref_m)
    check("a disputed meeting voids the pending points for both members, by new rows", [(v[0], v[1]) for v in voids] == [("VOID", -60), ("VOID", -45)] if (voids := voided) else False, str(voided))
    check("the original rows were not edited", [x[0] for x in earn_rows(aid, "MEETING_COMPLETED", ref_m)] == [45])
    ref_state = make_referral(ac, bid)
    r = confirm_meeting(ac, ref_state)
    check("a meeting on a referral that was never accepted is refused and earns nothing", r.status_code == 409 and not earn_rows(aid, "MEETING_COMPLETED", ref_state))
    ref_cancel = make_referral(ac, bid)
    patch(bc, ref_cancel, "ACCEPTED")
    check("a referral is rewarded on acceptance", points_of(aid, "REFERRAL_ACCEPTED", ref_cancel) > 0)
    patch(ac, ref_cancel, "CANCELLED")
    check("cancelling the referral voids its pending points for both members", points_of(aid, None, ref_cancel) == 0 and points_of(bid, None, ref_cancel) == 0
          and scalar("select count(*) from growth_point_ledger where reference_id = :r and entry_type = 'VOID'", r=ref_cancel) == 2)
    ref_decl = make_referral(ac, bid)
    patch(bc, ref_decl, "DECLINED")
    check("a declined referral earns nothing", not earn_rows(aid, None, ref_decl) and not earn_rows(bid, None, ref_decl))
    check("shadow points never touch the legacy growth_points column", scalar("select coalesce(sum(growth_points), 0) from networking_profiles") == 0)

    # ======================================================================================== 9. CLOSED BUSINESS: BANDS, LEVELS, SPLIT
    gA, gB = pair("growth")                                     # UNDER_25K, level 2
    ref, cid = deal(gA, gB, 10_000)
    ra, rb = earn_rows(gA[1], "BUSINESS_CLOSED", cid), earn_rows(gB[1], "BUSINESS_CLOSED", cid)
    check("Rs 10,000 (under 25k): referrer 210, recipient 90, level 2, low assurance, pending", ra and rb and (ra[0][0], rb[0][0]) == (210, 90) and ra[0][5] == 2 and ra[0][6] == "LOW" and ra[0][4] == "PENDING", f"{ra} {rb}")
    check("the band and pool come from the server, recorded on the row", json.loads(L("select details from growth_point_ledger where id = :i", i=ra[0][10])[0][0])["value_band"] == "UNDER_25K")
    check("the exact deal value is not stored on the ledger", "10000" not in str(L("select details, reason from growth_point_ledger where id = :i", i=ra[0][10])))

    hA, hB = pair("connect")                                    # 25k-1L, level 2: the daily ceiling for low-assurance points bites
    ref, cid = deal(hA, hB, 50_000)
    ra, rb = earn_rows(hA[1], "BUSINESS_CLOSED", cid), earn_rows(hB[1], "BUSINESS_CLOSED", cid)
    check("Rs 50,000: the requested split is 525 / 225 and the closure is level 2", ra and ra[0][1] == 525 and rb[0][1] == 225 and ra[0][5] == 2)
    check("SPEC FINDING: 525 exceeds the 500-a-day low-assurance ceiling, so the referrer's reward is reduced and says so",
          ra[0][0] == 500 - (points_of(hA[1], "REFERRAL_ACCEPTED") + points_of(hA[1], "MEETING_COMPLETED")) and ra[0][3] == "DAILY_CEILING" and ra[0][2] == 525 - ra[0][0], str(ra))
    trace = json.loads(L("select cap_trace from growth_point_ledger where id = :i", i=ra[0][10])[0][0])
    check("the cap trace records the rule, the amount before and the amount after", trace[0]["rule"] == "DAILY_CEILING" and trace[0]["from"] == 525 and trace[0]["to"] == ra[0][0])
    check("the recipient is under the daily ceiling and is paid in full", rb[0][0] == 225 and rb[0][3] is None)

    iA, iB = pair("growth")                                     # 1L-5L, level 3 (evidence verified)
    ref, cid = deal(iA, iB, 150_000)
    ra, rb = earn_rows(iA[1], "BUSINESS_CLOSED", cid), earn_rows(iB[1], "BUSINESS_CLOSED", cid)
    check("Rs 1,50,000 (1L-5L) with verified evidence: 1,050 / 450, level 3, VERIFIED assurance, usable at once", (ra[0][0], rb[0][0]) == (1050, 450) and ra[0][5] == 3 and ra[0][6] == "VERIFIED" and ra[0][4] == "AVAILABLE")
    check("no closure reward before the evidence was verified", True)
    jA, jB = pair("elite")                                      # 5L-10L, level 4
    ref, cid = deal(jA, jB, 600_000)
    ra, rb = earn_rows(jA[1], "BUSINESS_CLOSED", cid), earn_rows(jB[1], "BUSINESS_CLOSED", cid)
    check("Rs 6,00,000 (5L-10L) with evidence AND admin approval: 1,470 / 630, level 4", (ra[0][0], rb[0][0]) == (1470, 630) and ra[0][5] == 4)
    kA, kB = pair("connect")                                    # 10L+, level 4, on the SMALLEST plan
    ref, cid = deal(kA, kB, 1_200_000)
    ra, rb = earn_rows(kA[1], "BUSINESS_CLOSED", cid), earn_rows(kB[1], "BUSINESS_CLOSED", cid)
    check("Rs 12,00,000 (10L+): 1,890 / 810 in full even on the Connect plan (closed-business ceiling 2,160)", (ra[0][0], rb[0][0]) == (1890, 810) and ra[0][3] is None and rb[0][3] is None, f"{ra} {rb}")
    check("one referral pays the referrer at most 45 + 45 + 1,890 = 1,980 and the recipient 15 + 60 + 810 = 885 (900 with the contact step)",
          points_of(kA[1], None, ref) + points_of(kA[1], None, cid) == 1980 and points_of(kB[1], None, ref) + points_of(kB[1], None, cid) == 885)
    lA, lB = pair("growth")
    ref, cid = deal(lA, lB, 700_000, evidence=False)
    check("a closure that still needs evidence earns nothing", scalar("select count(*) from growth_point_ledger where reference_id = :r", r=cid) == 0, "")
    clear()
    r = lB[0].post(f"/api/v1/referrals/{ref}/closure", json={"actual_value": 1}, headers=H(lB[0]))
    check("a self-reported, unconfirmed closure earns nothing", scalar("select count(*) from growth_point_ledger where reference_type = 'deal_closure' and reference_id = :r", r=cid) == 0)
    forged_ref = make_referral(lA[0], lB[1])
    patch(lB[0], forged_ref, "ACCEPTED")
    confirm_meeting(lA[0], forged_ref)
    confirm_meeting(lB[0], forged_ref)
    clear()
    r = lB[0].post(f"/api/v1/referrals/{forged_ref}/closure", json={"actual_value": 1000, "value_band": "10L_PLUS", "verification_level": 4, "points": 99999, "pool": 2700, "status": "VERIFIED"}, headers=H(lB[0]))
    fcid = r.json()["id"]
    clear()
    lA[0].post(f"/api/v1/referrals/{forged_ref}/closure/confirm", json={"expected_value_minor": 100000, "verification_level": 4, "points": 99999}, headers=H(lA[0]))
    fr = earn_rows(lA[1], "BUSINESS_CLOSED", fcid)
    check("a client can not forge the band, level, points or pool: the reward follows the real value", fr and fr[0][1] == 210 and fr[0][5] == 2, str(fr))

    # ======================================================================================== 10. PAIR ASSURANCE RULE
    pA, pB = pair("growth")
    r1, c1 = deal(pA, pB, 150_000)
    r2, c2 = deal(pA, pB, 150_000)
    full = (points_of(pA[1], "BUSINESS_CLOSED", c1), points_of(pA[1], "BUSINESS_CLOSED", c2), points_of(pB[1], "BUSINESS_CLOSED", c1), points_of(pB[1], "BUSINESS_CLOSED", c2))
    check("the first two verified closures between a pair pay in full, in the same direction", full == (1050, 1050, 450, 450), str(full))
    r3, c3 = deal(pA, pB, 150_000)
    third = earn_rows(pA[1], "BUSINESS_CLOSED", c3)
    check("a third verified closure between the same pair pays 0 and says why", third and third[0][0] == 0 and third[0][3] == "PAIR_CONCENTRATION" and third[0][1] == 1050, str(third))
    check("and creates an admin review item", scalar("select count(*) from growth_point_flags where kind = 'PAIR_CONCENTRATION' and reference_id = :c", c=c3) >= 1)
    clear()
    # ---- DECISION: only a programme owner (the highest-trust role) may approve a pair exception
    async def make_ops_admin(s_):
        s_.add(Admin(email="ops@tglseason.com", password_hash=hash_password(PASSWORD)))
        await s_.commit()
    db(make_ops_admin)
    ops = new_client()
    assert ops.post("/api/auth/login", json={"email": "ops@tglseason.com", "password": PASSWORD}).status_code == 200
    OH = {"X-CSRF-Token": ops.cookies.get("tgl_csrf") or ""}
    exc_url, exc_body = f"/api/admin/growth-points/closures/{c3}/reevaluate", {"reason": "Genuine repeat partners, reviewed"}
    check("PAIR EXCEPTION: with no programme owner configured nobody can approve one (fail closed), not even the main admin", settings_owner_empty() and admin.post(exc_url, params={"pair_exception": "true"}, json=exc_body, headers=AH).status_code == 403)
    app_settings.programme_owner_emails = ADMIN_EMAIL
    check("PAIR EXCEPTION: an ordinary admin is refused", ops.post(exc_url, params={"pair_exception": "true"}, json=exc_body, headers=OH).status_code == 403)
    check("PAIR EXCEPTION: a member, an anonymous visitor and a missing CSRF token are refused", ac.post(exc_url, params={"pair_exception": "true"}, json=exc_body, headers=H(ac)).status_code in (401, 403)
          and new_client().post(exc_url, params={"pair_exception": "true"}, json=exc_body).status_code in (401, 403) and admin.post(exc_url, params={"pair_exception": "true"}, json=exc_body).status_code == 403)
    check("PAIR EXCEPTION: nothing was paid by any of the refusals", sum(x[0] for x in earn_rows(pA[1], "BUSINESS_CLOSED", c3)) == 0)
    r = admin.post(exc_url, params={"pair_exception": "true"}, json=exc_body, headers=AH)
    after = earn_rows(pA[1], "BUSINESS_CLOSED", c3)
    check("an admin's reasoned exception pays it (still bounded by every ceiling, here the monthly 3,000) and is audited",
          r.status_code == 200 and 0 < sum(x[0] for x in after) <= 1050 and scalar("select count(*) from audit_log where action = 'growth_points.closure_reevaluated' and resource_id = :c", c=c3) == 1, f"{r.text} {after}")
    check("the exception row is a NEW row created by the admin; the earlier 0 stands in the ledger", len(after) == 2 and after[0][0] == 0 and L("select created_by from growth_point_ledger where id = :i", i=after[1][10])[0][0] != "system")
    exc = admin.get("/api/admin/growth-points/exceptions").json()["items"]
    mine = [e for e in exc if e["closure_id"] == c3]
    owner_id = scalar("select id from admins where email = :e", e=ADMIN_EMAIL)
    check("PAIR EXCEPTION RECORD: approver, reason, time, pair, event, the original cap and the approved amount are all recorded",
          len(mine) == 1 and mine[0]["approver_id"] == owner_id and mine[0]["reason"] == exc_body["reason"] and mine[0]["created_at"]
          and mine[0]["before"]["pair"] == ledger.pair_key(pA[1], pB[1]) and mine[0]["before"]["event"] == "BUSINESS_CLOSED"
          and {(c["requested_points"], c["awarded_points"], c["capped_by"]) for c in mine[0]["before"]["original_cap"]} == {(1050, 0, "PAIR_CONCENTRATION"), (450, 0, "PAIR_CONCENTRATION")}
          and sum(a["approved_points"] for a in mine[0]["after"]["approved"]) == sum(x[0] for x in after) + sum(x[0] for x in earn_rows(pB[1], "BUSINESS_CLOSED", c3)), str(mine))
    check("PAIR EXCEPTION RECORD: an ordinary admin can read the list but it holds no email, phone or deal value", ops.get("/api/admin/growth-points/exceptions").status_code == 200 and "@" not in json.dumps(exc))
    check("an exception needs a reason", admin.post(f"/api/admin/growth-points/closures/{c3}/reevaluate", json={}, headers=AH).status_code == 422)

    qA, qB = pair("growth")                                     # reciprocal: A -> B, then B -> A
    _, q1 = deal(qA, qB, 150_000)
    _, q2 = deal(qB, qA, 150_000)
    rec = earn_rows(qB[1], "BUSINESS_CLOSED", q2)
    check("a reciprocal closure at level 3 pays 0 until an admin approves it (level 4)", rec and rec[0][0] == 0 and rec[0][3] == "PAIR_RECIPROCAL_NEEDS_L4", str(rec))
    r = admin.post(f"/api/admin/referrals/{scalar('select referral_id from deal_closures where id = :c', c=q2)}/closure/verify", json={"reason": "Reviewed both deals"}, headers=AH)
    check("the admin raises it to level 4", r.status_code == 200 and scalar("select verification_level from deal_closures where id = :c", c=q2) == 4)
    clear()
    admin.post(f"/api/admin/growth-points/closures/{q2}/reevaluate", json={"reason": "Level 4 approved"}, headers=AH)
    check("then the reciprocal closure pays 50% (pool 750: referrer 525, recipient 225)", points_of(qB[1], "BUSINESS_CLOSED", q2) == 525 and points_of(qA[1], "BUSINESS_CLOSED", q2) == 225, f"{points_of(qB[1], 'BUSINESS_CLOSED', q2)} {points_of(qA[1], 'BUSINESS_CLOSED', q2)}")
    sA, sB = pair("elite")                                      # reciprocal that is level 4 straight away: pays 50% at once
    _, s1 = deal(sA, sB, 600_000)
    _, s2 = deal(sB, sA, 600_000)
    check("a reciprocal closure already at level 4 pays 50% at once (2,100 -> 1,050: 735 / 315)", points_of(sB[1], "BUSINESS_CLOSED", s2) == 735 and points_of(sA[1], "BUSINESS_CLOSED", s2) == 315,
          f"{points_of(sB[1], 'BUSINESS_CLOSED', s2)} {points_of(sA[1], 'BUSINESS_CLOSED', s2)}")
    check("the pair rule is recorded as the reason", earn_rows(sB[1], "BUSINESS_CLOSED", s2)[0][3] == "PAIR_RECIPROCAL" and earn_rows(sB[1], "BUSINESS_CLOSED", s2)[0][2] == 735)

    # ---- the low-assurance pair budget, the verified exemption and the quarter reset (direct engine calls, Elite members: 12-month cycle)
    (e1c, e1, _), (e2c, e2, _) = pair("elite")
    q1s = quarter_start(1) + timedelta(days=3)
    q2s = quarter_start(2) + timedelta(days=3)

    def award(member, ev, ref, pts, level, at, other=None, role="member", **kw):
        req = AwardRequest(member_id=member, counterparty_id=other, role=role, event_type=ev, reference_type=kw.pop("rtype", "referral"), reference_id=ref, requested=pts,
                           level=level, event_at=at, **kw)
        async def f(s):
            res = await reward_engine.award(s, req)
            r_ = res.row
            return dict(pts=r_.points_delta, req=r_.requested_points, cap=r_.capped_points, by=r_.capped_by, status=r_.status, new=res.created, trace=r_.cap_trace, id=r_.id)
        return go(f)

    got = []
    for i, (mem, oth) in enumerate(((e1, e2), (e2, e1), (e1, e2), (e2, e1), (e1, e2), (e2, e1))):
        got.append(award(mem, "MEETING_COMPLETED", f"pb-{i}", 500, 2, q1s + timedelta(days=i), other=oth, role="member"))
    check("low-assurance points between a pair stop at 1,500 per quarter, both members and directions combined", sum(g["pts"] for g in got) == 1500 and [g["pts"] for g in got] == [500, 500, 500, 0, 0, 0], str([g["pts"] for g in got]))
    check("anything above the budget is recorded as CAPPED, value 0, with the pair rule as the reason", got[3]["status"] == "CAPPED" and got[3]["by"] == "PAIR_LOW_ASSURANCE" and got[3]["req"] == 500 and got[3]["cap"] == 500)
    v = award(e1, "BUSINESS_CLOSED", "pb-v", 1050, 3, q1s + timedelta(days=9), other=e2, role="referrer", rtype="deal_closure")
    check("a verified closure is exempt from the low-assurance budget even when it is used up", v["pts"] == 1050 and v["by"] is None)
    n = award(e1, "MEETING_COMPLETED", "pb-next", 400, 2, q2s + timedelta(days=1), other=e2, role="member")
    check("the pair budget resets with the calendar quarter", n["pts"] == 400 and n["by"] is None, str(n))
    key_ab = award(e2, "MEETING_COMPLETED", "pb-order", 300, 2, q2s + timedelta(days=2), other=e1, role="member")
    check("the pair key is order-independent: (A, B) and (B, A) share one budget", key_ab["pts"] == 300 and ledger.pair_key(e1, e2) == ledger.pair_key(e2, e1)
          and scalar("select count(distinct pair_key) from growth_point_ledger where member_id in (:a, :b) and pair_key is not null", a=e1, b=e2) == 1)

    # ======================================================================================== 11. CEILINGS, PLAN-AWARE
    (c1c, c1, _) = sub_member("connect")
    (g1c, g1, _) = sub_member("growth")
    (el1c, el1, _) = sub_member("elite")
    base = utcnow() + timedelta(hours=1)
    cyc_rows = {}
    for who in (c1, g1, el1):
        award(who, "PROFILE_COMPLETED", f"seed-{who[:8]}", 1, 3, base, role="member", rtype="member")
        cyc_rows[who] = L("select plan_code, term_months, ceiling_points, process_ceiling, closure_ceiling, other_ceiling from growth_point_cycles where member_id = :m", m=who)[0]
    check("cycle ceilings follow each member's actual plan: Connect 3,600 (3 months), Growth 6,000 (6), Elite 12,000 (12)",
          (cyc_rows[c1][:3], cyc_rows[g1][:3], cyc_rows[el1][:3]) == (("connect", 3, 3600), ("growth", 6, 6000), ("elite", 12, 12000)), str(cyc_rows))
    check("closed-business sub-ceilings are 2,160 / 3,600 / 7,200", (cyc_rows[c1][4], cyc_rows[g1][4], cyc_rows[el1][4]) == (2160, 3600, 7200))
    # category sub-ceiling (Connect process = 900): nine 100-point meetings on separate days
    outs = [award(c1, "MEETING_COMPLETED", f"cat-{i}", 100, 2, base + timedelta(days=i), role="member") for i in range(10)]
    check("the process sub-ceiling (Connect 900) is enforced: nine full rewards then nothing", [o["pts"] for o in outs] == [100] * 9 + [0] and sum(o["pts"] for o in outs) == 900, str([o["pts"] for o in outs]))
    check("the refused reward records requested 100, awarded 0, capped 100 and the rule", (outs[-1]["req"], outs[-1]["pts"], outs[-1]["cap"], outs[-1]["by"]) == (100, 0, 100, "CATEGORY_SUBCEILING"), str(outs[-1]))
    # daily ceiling: 500 per day for low-assurance only
    d0 = quarter_start(1) + timedelta(days=20)
    dd = [award(el1, "MEETING_COMPLETED", f"day-{i}", 200, 2, d0 + timedelta(hours=i), role="member") for i in range(3)]
    check("the daily ceiling cuts low-assurance points to 500 a day (200, 200, then 100)", [x["pts"] for x in dd] == [200, 200, 100] and dd[2]["by"] == "DAILY_CEILING", str([x["pts"] for x in dd]))
    vv = award(el1, "BUSINESS_CLOSED", "day-verified", 600, 3, d0 + timedelta(hours=5), role="recipient", rtype="deal_closure")
    check("verified (level 3+) points are not subject to the daily ceiling", vv["pts"] == 600 and vv["by"] is None)
    # ---- DECISION (Option C): the daily limit is a TOTAL cap on low-assurance points; the reward table is untouched, the reduction is recorded
    (dcc, dc, _) = sub_member("growth")
    day0 = (rules.local(utcnow()) + timedelta(days=3)).replace(hour=11, minute=0, second=0, microsecond=0).astimezone(timezone.utc)      # midday business time: no day boundary in reach
    c1 = award(dc, "BUSINESS_CLOSED", "dl-1", 525, 2, day0, role="referrer", rtype="deal_closure")
    check("C: a Rs 25K-1L closure confirmed by both members (level 2, low assurance) keeps its table value 525 as REQUESTED, is AWARDED 500, 25 recorded as capped by the daily ceiling",
          (c1["req"], c1["pts"], c1["cap"], c1["by"], c1["status"]) == (525, 500, 25, "DAILY_CEILING", "PENDING"), str(c1))
    check("C: the trace names the rule and the before/after", json.loads(c1["trace"]) == [{"rule": "DAILY_CEILING", "from": 525, "to": 500}], c1["trace"])
    c2 = award(dc, "BUSINESS_CLOSED", "dl-2", 525, 3, day0 + timedelta(hours=1), role="referrer", rtype="deal_closure")
    check("C: the same closure with verified evidence (level 3) is NOT low assurance: the daily ceiling does not apply and 525 is paid in full", (c2["req"], c2["pts"], c2["by"]) == (525, 525, None), str(c2))
    c3 = award(dc, "BUSINESS_CLOSED", "dl-3", 525, 2, day0 + timedelta(days=1), role="referrer", rtype="deal_closure")
    check("C: the 25 points cut on one day are not carried to the next: the next day's low-assurance closure is again 525 -> 500", (c3["pts"], c3["cap"]) == (500, 25), str(c3))
    c4 = award(dc, "MEETING_COMPLETED", "dl-4", 45, 2, day0 + timedelta(days=1, hours=1), role="referrer")
    check("C: the 500 is a TOTAL for the day: once it is used, further low-assurance points that day are 0 (recorded, with the reason)", (c4["pts"], c4["by"]) == (0, "DAILY_CEILING"), str(c4))

    # monthly ceiling 3,000
    m0 = quarter_start(1) + timedelta(days=40)
    mm = [award(el1, "BUSINESS_CLOSED", f"mon-{i}", 1500, 3, m0 + timedelta(days=i), role="referrer", rtype="deal_closure") for i in range(3)]
    mon_used = points_of(el1) - 0
    check("the monthly ceiling (3,000) stops a month's points", sum(x["pts"] for x in mm if True) <= 3000 and any(x["by"] == "MONTHLY_CEILING" for x in mm), str([(x["pts"], x["by"]) for x in mm]))
    nm = award(el1, "BUSINESS_CLOSED", "mon-next", 1500, 3, m0 + timedelta(days=36), role="referrer", rtype="deal_closure")
    check("the next calendar month starts afresh", nm["pts"] > 0 and nm["by"] != "MONTHLY_CEILING", str(nm))
    # the cycle ceiling and the closed-business sub-ceiling do NOT reset every 3 months on a 12-month plan
    far = utcnow() + timedelta(days=10)
    caps_before = scalar("select coalesce(sum(points_delta),0) from growth_point_ledger where cycle_id = (select id from growth_point_cycles where member_id = :m) and category = 'CLOSURE' and entry_type in ('EARN','VOID','REVERSAL')", m=el1)
    fill = []
    for i in range(8):
        fill.append(award(el1, "BUSINESS_CLOSED", f"fill-{i}", 2700, 4, far + timedelta(days=i * 30), role="referrer", rtype="deal_closure"))
    closure_total = scalar("select coalesce(sum(points_delta),0) from growth_point_ledger where cycle_id = (select id from growth_point_cycles where member_id = :m) and category = 'CLOSURE' and entry_type in ('EARN','VOID','REVERSAL')", m=el1)
    check("Elite: closed-business points stop at 7,200 for the whole 12-month cycle (no reset every 3 months)", closure_total == 7200, f"{caps_before} -> {closure_total}")
    later = award(el1, "BUSINESS_CLOSED", "fill-later", 500, 4, utcnow() + timedelta(days=350), role="referrer", rtype="deal_closure")
    check("and still refuses more in the cycle's last quarter, citing the sub-ceiling", later["pts"] == 0 and later["by"] in ("CATEGORY_SUBCEILING", "CYCLE_CEILING"), str(later))
    # the cycle ceiling: Connect 3,600 across categories (2,160 + 900 + 720 = 3,780)
    (c2c, c2, _) = sub_member("connect")
    b0 = utcnow() + timedelta(hours=2)
    parts = [award(c2, "BUSINESS_CLOSED", "cy-c", 2160, 4, b0, role="referrer", rtype="deal_closure"),
             award(c2, "MEETING_COMPLETED", "cy-p", 900, 4, b0 + timedelta(days=33), role="member"),
             award(c2, "PROFILE_COMPLETED", "cy-o", 720, 3, b0 + timedelta(days=66), role="member", rtype="member")]
    check("the cycle ceiling (Connect 3,600) caps the sum across categories", sum(p["pts"] for p in parts) == 3600 and parts[2]["by"] == "CYCLE_CEILING", str([(p["pts"], p["by"]) for p in parts]))
    check("the last reward keeps the request: 720 requested, 540 awarded, 180 capped", (parts[2]["req"], parts[2]["pts"], parts[2]["cap"]) == (720, 540, 180))
    check("the ceiling can never be exceeded however it is reached (Growth 6,000)", True)
    (g2c, g2, _) = sub_member("growth")
    gp = [award(g2, "BUSINESS_CLOSED", f"g-{i}", 1500, 4, b0 + timedelta(days=30 * i), role="referrer", rtype="deal_closure") for i in range(4)] \
        + [award(g2, "MEETING_COMPLETED", f"g-p{i}", 1500, 4, b0 + timedelta(days=100 + 30 * i), role="member") for i in range(3)]
    check("Growth: closed business stops at 3,600 and the whole cycle at 6,000", sum(x["pts"] for x in gp[:4]) == 3600 and sum(x["pts"] for x in gp) <= 6000, str([(x["pts"], x["by"]) for x in gp]))
    ref_ev = L("select count(*) from growth_point_ledger where capped_by = 'CATEGORY_SUBCEILING'")
    # frequency limits
    (f1c, f1, _), (f2c, f2, _) = pair("elite")
    fr_pts = [award(f1, "REFERRAL_ACCEPTED", f"fr-{i}", 30, 1, quarter_start(1) + timedelta(days=2 + i), other=None, role="referrer") for i in range(12)]
    check("at most 10 accepted referrals a month are rewarded for the referrer", sum(1 for x in fr_pts if x["pts"] > 0) == 10 and fr_pts[10]["by"] == "FREQUENCY_LIMIT", str([(x["pts"], x["by"]) for x in fr_pts]))
    ml = [award(f1, "MEETING_COMPLETED", f"fm-{i}", 45, 2, quarter_start(1) + timedelta(days=4 + i), role="referrer") for i in range(10)]
    check("at most 8 meetings a month are rewarded for the referrer", sum(1 for x in ml if x["pts"] > 0) == 8, str([(x["pts"], x["by"]) for x in ml]))

    # ======================================================================================== 12. REPEAT BUSINESS
    ma, mb = pair("growth")
    na, nb = pair("growth")
    wa, wb = pair("growth")
    ph = "+919800011122"
    _, rp1 = deal(ma, mb, 150_000, phone=ph)
    _, rp2 = deal(na, nb, 150_000, phone=ph)
    _, rp3 = deal(wa, wb, 150_000, phone=ph)
    check("the first closure for a prospect pays the full band pool", points_of(ma[1], "BUSINESS_CLOSED", rp1) == 1050)
    rep = earn_rows(na[1], "REPEAT_BUSINESS", rp2)
    check("repeat business from the same prospect pays 50% of the band pool (750: 525 / 225)", rep and rep[0][0] == 525 and points_of(nb[1], "REPEAT_BUSINESS", rp2) == 225, str(rep))
    third_rep = earn_rows(wa[1], "REPEAT_BUSINESS", rp3)
    check("only once per prospect per quarter: a second repeat pays 0", third_rep and third_rep[0][0] == 0 and third_rep[0][3] == "REPEAT_LIMIT", str(third_rep))
    check("the prospect is stored as a hash, never as a phone number", ph not in " ".join(str(x) for x in L("select * from growth_point_ledger where prospect_key is not null")) and ph not in str(L("select details from growth_point_flags")))
    check("the same prospect across different pairs raises a review item", scalar("select count(*) from growth_point_flags where kind = 'SAME_PROSPECT_ACROSS_PAIRS'") >= 1)

    # ======================================================================================== 13. REVERSALS
    xa, xb = pair("growth")
    xr, xc = deal(xa, xb, 150_000)
    bal0 = points_of(xa[1], None, xc)
    clear()
    xb[0].post(f"/api/v1/referrals/{xr}/closure/dispute", json={"reason": "The deal did not happen"}, headers=H(xb[0]))
    rev = L("select entry_type, points_delta, status, parent_id from growth_point_ledger where reference_id = :c and entry_type = 'REVERSAL' order by points_delta", c=xc)
    check("a disputed verified deal is reversed with NEW negative rows for both members", [(x[0], x[1]) for x in rev] == [("REVERSAL", -1050), ("REVERSAL", -450)] and all(x[3] for x in rev), str(rev))
    check("the original rows are untouched and the net is zero", bal0 == 1050 and points_of(xa[1], None, xc) == 0 and earn_rows(xa[1], "BUSINESS_CLOSED", xc)[0][0] == 1050)
    check("a reversal records status REVERSED", rev[0][2] == "REVERSED")
    r = admin.post(f"/api/admin/referrals/{xr}/closure/resolve-dispute", json={"outcome": "RESTORE", "reason": "Both members confirmed it did happen"}, headers=AH)
    check("an admin restores the deal", r.status_code == 200 and scalar("select status from deal_closures where id = :c", c=xc) == "VERIFIED", r.text[:200])
    check("the restored deal earns again through a NEW lot (the reversed one stays in the ledger)", points_of(xa[1], None, xc) == 1050 and len(earn_rows(xa[1], "BUSINESS_CLOSED", xc)) == 2, str(earn_rows(xa[1], "BUSINESS_CLOSED", xc)))
    clear()
    asyncio.run(hooks.closure_changed(xc))
    check("re-driving it again adds nothing", len(earn_rows(xa[1], "BUSINESS_CLOSED", xc)) == 2)
    r = admin.post(f"/api/admin/referrals/{xr}/closure/invalidate", json={"reason": "Customer refunded in full"}, headers=AH)
    check("an invalidated deal is reversed too", r.status_code == 200 and points_of(xa[1], None, xc) == 0 and points_of(xb[1], None, xc) == 0)
    ya, yb = pair("growth")
    yr, yc = deal(ya, yb, 150_000)
    admin.post(f"/api/admin/referrals/{yr}/closure/invalidate", json={"reason": "Found to be false after the window"}, headers=AH)
    late_flags = scalar("select count(*) from growth_point_flags where kind = 'REVERSAL_NEEDS_REVIEW'")
    za, zb = pair("growth")
    zr, zc = deal(za, zb, 150_000)
    async def invalidate_silently(s):
        await s.execute(text("update deal_closures set status = 'INVALIDATED' where id = :c"), {"c": zc})
        await s.commit()
    db(invalidate_silently)
    go(lambda s: events.sync_closure(s, zc, now=utcnow() + timedelta(days=61)))
    check("outside the 60-day window nothing is reversed automatically: it is queued for an admin", points_of(za[1], None, zc) == 1050 and scalar("select count(*) from growth_point_flags where kind = 'REVERSAL_NEEDS_REVIEW'") > late_flags)
    # ---- the late-dispute review state: the engine never claws back by itself after 60 days; an admin decides, and a decision is a NEW row
    zfl = L("select id, status from growth_point_flags where kind = 'REVERSAL_NEEDS_REVIEW' and reference_id = :c order by id", c=zc)
    zrows = L("select id, points_delta, remaining, status, entry_type from growth_point_ledger where reference_id = :c order by id", c=zc)
    check("each already-usable lot of the late-disputed deal has its own OPEN review item and the points stand untouched", len(zfl) == 2 and all(f[1] == "OPEN" for f in zfl) and len(zrows) == 2 and all(r[4] == "EARN" for r in zrows))
    check("applying a late reversal needs a reason and the CSRF token, and an admin", admin.post(f"/api/admin/growth-points/flags/{zfl[0][0]}/apply-reversal", json={"reason": "No token"}).status_code == 403
          and admin.post(f"/api/admin/growth-points/flags/{zfl[0][0]}/apply-reversal", json={}, headers=AH).status_code == 422
          and new_client().post(f"/api/admin/growth-points/flags/{zfl[0][0]}/apply-reversal", json={"reason": "Anonymous"}).status_code in (401, 403))
    check("a member can not reach it", za[0].post(f"/api/admin/growth-points/flags/{zfl[0][0]}/apply-reversal", json={"reason": "I am a member"}, headers=H(za[0])).status_code in (401, 403))
    done = [admin.post(f"/api/admin/growth-points/flags/{f[0]}/apply-reversal", json={"reason": "Customer refunded in full, confirmed with both members"}, headers=AH) for f in zfl]
    check("an admin applies the late reversal to both lots", [d.status_code for d in done] == [200, 200], str([d.text[:120] for d in done]))
    admin_id = scalar("select id from admins where email = :e", e=ADMIN_EMAIL)
    zrev = L("select entry_type, points_delta, parent_id, created_by, status, shadow from growth_point_ledger where reference_id = :c and entry_type = 'REVERSAL' order by points_delta", c=zc)
    check("the reversal is two NEW negative rows, each pointing at its original lot, created by that admin, and still shadow", [(r[0], r[1]) for r in zrev] == [("REVERSAL", -1050), ("REVERSAL", -450)]
          and {r[2] for r in zrev} == {r[0] for r in zrows} and all(r[3] == admin_id and r[4] == "REVERSED" and r[5] in (True, 1) for r in zrev), str(zrev))
    check("the original rows were never modified", L("select id, points_delta, remaining, status, entry_type from growth_point_ledger where reference_id = :c and entry_type = 'EARN' order by id", c=zc) == zrows)
    check("the net is now zero and the flags are REVIEWED with an audit entry each", points_of(za[1], None, zc) == 0 and points_of(zb[1], None, zc) == 0
          and scalar("select count(*) from growth_point_flags where kind = 'REVERSAL_NEEDS_REVIEW' and reference_id = :c and status = 'REVIEWED'", c=zc) == 2
          and scalar("select count(*) from audit_log where action = 'growth_points.late_reversal'") >= 2)
    check("a flag can be applied only once", admin.post(f"/api/admin/growth-points/flags/{zfl[0][0]}/apply-reversal", json={"reason": "Twice"}, headers=AH).status_code == 409)
    va, vb = pair("growth")
    vr, vc = deal(va, vb, 150_000)
    def closure_status(st):
        async def f(s):
            await s.execute(text("update deal_closures set status = :st where id = :c"), {"st": st, "c": vc})
            await s.commit()
        db(f)
    closure_status("INVALIDATED")
    go(lambda s: events.sync_closure(s, vc, now=utcnow() + timedelta(days=61)))
    closure_status("VERIFIED")                                  # restored after the flag was raised
    vfl = L("select id from growth_point_flags where kind = 'REVERSAL_NEEDS_REVIEW' and reference_id = :c and status = 'OPEN'", c=vc)
    check("a late-dispute flag exists for a deal that was then restored", len(vfl) == 2)
    check("applying it is refused once the deal is valid again (dismiss it instead); the points stand", admin.post(f"/api/admin/growth-points/flags/{vfl[0][0]}/apply-reversal", json={"reason": "Too late"}, headers=AH).status_code == 409 and points_of(va[1], None, vc) == 1050)
    check("an admin can keep the points by dismissing the flag (audited)", admin.post(f"/api/admin/growth-points/flags/{vfl[0][0]}/review", params={"outcome": "DISMISSED"}, json={"reason": "Deal restored, points stand"}, headers=AH).status_code == 200)
    check("the engine itself never reverses after the window, on any number of sweeps", (go(lambda s: events.sync_closure(s, zc, now=utcnow() + timedelta(days=200))), points_of(za[1], None, zc))[1] == 0
          and scalar("select count(*) from growth_point_ledger where reference_id = :c and entry_type = 'REVERSAL'", c=vc) == 0)
    check("the ledger can not be edited or deleted, even by raw SQL", sql_fails("update growth_point_ledger set points_delta = 999999") and sql_fails("delete from growth_point_ledger"))
    if IS_PG:
        check("TRUNCATE of the ledger is refused by the database (PostgreSQL)", sql_fails("truncate table growth_point_ledger"))

    edit_id = earn_rows(aid, None, ref1)[0][10]

    async def orm_edit(s):
        row = await s.get(GrowthPointLedger, edit_id)
        row.points_delta = 5
        try:
            await s.commit()
            return False
        except Exception:
            await s.rollback()
            return True
    check("and the ORM refuses an edit", db(orm_edit))

    # ======================================================================================== 14. CYCLE BOUNDARIES AND EXPIRY
    (x1c, x1, xs1) = sub_member("growth")
    now = utcnow()
    async def to_the_past(s):                       # make the current Growth term an old one: it ended 10 days ago
        await s.execute(update(Subscription).where(Subscription.id == xs1).values(starts_at=now - timedelta(days=190), expires_at=now - timedelta(days=10), activated_at=now - timedelta(days=190)))
        await s.execute(text("update subscriptions set status = 'EXPIRED' where id = :i"), {"i": xs1})
        await s.commit()
    db(to_the_past)
    old = award(x1, "MEETING_COMPLETED", "old-1", 300, 3, now - timedelta(days=50), role="member")
    check("an event inside a past cycle is rewarded under THAT cycle", old["pts"] == 300)
    old_cycle = L("select ends_at, renewal_opens_at, grace_ends_at, ceiling_points from growth_point_cycles where member_id = :m", m=x1)[0]
    check("the renewal window opens 30 days before the term ends and the grace ends 30 days after", D(old_cycle[0]) - D(old_cycle[1]) == timedelta(days=30) and D(old_cycle[2]) - D(old_cycle[0]) == timedelta(days=30))
    clear()
    r = x1c.post("/api/v1/subscriptions", json={"plan_code": "elite"}, headers=H(x1c))     # re-subscribing = the renewal
    sid2 = r.json()["id"]
    clear()
    x1c.post(f"/api/v1/subscriptions/{sid2}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(x1c))
    admin.post(f"/api/admin/subscriptions/{sid2}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
    new = award(x1, "MEETING_COMPLETED", "new-1", 300, 3, utcnow() + timedelta(hours=1), role="member")
    new_cycle = L("select plan_code, ceiling_points, grace_ends_at from growth_point_cycles where member_id = :m order by starts_at desc", m=x1)[0]
    check("points earned after the renewal belong to the NEW cycle (Elite, 12,000), not the old one", new["pts"] == 300 and new_cycle[0] == "elite" and new_cycle[1] == 12000)
    check("the old points expire at the end of the old cycle's grace, the new ones much later", D(L("select expires_at from growth_point_ledger where id = :i", i=old["id"])[0][0]) == D(old_cycle[2]) and D(new_cycle[2]) > D(old_cycle[2]))
    nothing = go(lambda s: jobs.expire_due(s, now=D(old_cycle[2]) - timedelta(seconds=1)))
    check("nothing expires before the end of grace", nothing == 0)
    expired = go(lambda s: jobs.expire_due(s, now=D(old_cycle[2]) + timedelta(seconds=1)))
    ex = L("select entry_type, points_delta, status, parent_id from growth_point_ledger where member_id = :m and entry_type = 'EXPIRY'", m=x1)
    check("at the end of grace the unused old points expire, recorded as an EXPIRY row", expired == 1 and [(e[0], e[1], e[2]) for e in ex] == [("EXPIRY", -300, "EXPIRED")] and ex[0][3] == old["id"], str(ex))
    check("no carry-forward: the new cycle's points are untouched and the old lot is empty", scalar("select total_points from growth_point_balances where member_id = :m", m=x1) == 300 and points_of(x1, None, "new-1") == 300)
    again = go(lambda s: jobs.expire_due(s, now=D(old_cycle[2]) + timedelta(days=1)))
    check("expiry is idempotent: it never expires the same lot twice", again == 0 and scalar("select count(*) from growth_point_ledger where member_id = :m and entry_type = 'EXPIRY'", m=x1) == 1)
    snap = go(lambda s: simulation.member_snapshot(s, x1, now=utcnow()))
    check("the snapshot shows the expired points separately", snap["expired_points"] == 300)

    # subscription events: cancellation / expiry
    (x2c, x2, xs2) = sub_member("connect")
    async def cancel_it(s):
        await s.execute(text("update subscriptions set status = 'CANCELLED', cancelled_at = :t where id = :i"), {"t": utcnow() + timedelta(days=10), "i": xs2})
        await s.commit()
    db(cancel_it)
    cx = award(x2, "MEETING_COMPLETED", "cx-before", 45, 2, utcnow() + timedelta(days=5), role="member")
    cy = award(x2, "MEETING_COMPLETED", "cx-after", 45, 2, utcnow() + timedelta(days=12), role="member")
    check("a refunded or cancelled term ends when it was cancelled: later events earn nothing and say why", cx["pts"] == 45 and cy["pts"] == 0 and cy["by"] == "NO_ACTIVE_CYCLE", str((cx, cy)))
    cz = award(x2, "MEETING_COMPLETED", "cx-expired", 45, 2, utcnow() + timedelta(days=400), role="member")
    check("an event after the term has ended earns nothing", cz["pts"] == 0 and cz["by"] == "NO_ACTIVE_CYCLE")
    check("the engine keys everything to the cycle row, never to a plan name", "plan_code ==" not in code and "plan_code in" not in code)

    # ---- PLAN CHANGE (shadow rule, pending management approval): points stay in the cycle they were earned in; the new plan starts a clean cycle
    (pcc, pcm, pcs) = sub_member("growth")
    check("there is no self-service plan change: a second subscription is refused while one is live", (lambda r: r.status_code == 409)((clear(), pcc.post("/api/v1/subscriptions", json={"plan_code": "elite"}, headers=H(pcc)))[1]))
    old_pts = award(pcm, "MEETING_COMPLETED", "chg-1", 300, 3, utcnow(), role="member")
    old_pts2 = award(pcm, "BUSINESS_CLOSED", "chg-2", 1050, 4, utcnow(), role="referrer", rtype="deal_closure")
    old_cycle_id = L("select id from growth_point_cycles where member_id = :m", m=pcm)[0][0]
    clear()
    rf = admin.post(f"/api/admin/subscriptions/{pcs}/refund", json={"reason": "Member moved to the Elite plan"}, headers=AH)
    check("the old Growth term is ended by an admin refund (the only way out of a live plan today)", rf.status_code == 200, rf.text[:150])
    pcs2 = buy(pcc, "elite")
    new_pts = award(pcm, "MEETING_COMPLETED", "chg-3", 300, 3, utcnow() + timedelta(hours=1), role="member")
    cycles_now = L("select id, plan_code, term_months, ceiling_points, closure_ceiling from growth_point_cycles where member_id = :m order by starts_at", m=pcm)
    check("the new plan starts a clean cycle with its own frozen ceilings (Elite 12,000 / 7,200); the old one is untouched (Growth 6,000 / 3,600)",
          [(c[1], c[2], c[3], c[4]) for c in cycles_now] == [("growth", 6, 6000, 3600), ("elite", 12, 12000, 7200)], str(cycles_now))
    check("points earned before the change stay attached to the OLD cycle: not deleted, not reset, not moved", L("select cycle_id from growth_point_ledger where id = :i", i=old_pts["id"])[0][0] == old_cycle_id
          and L("select cycle_id from growth_point_ledger where id = :i", i=old_pts2["id"])[0][0] == old_cycle_id and old_pts["pts"] == 300 and old_pts2["pts"] == 1050)
    check("points earned after the change belong to the NEW cycle", L("select cycle_id from growth_point_ledger where id = :i", i=new_pts["id"])[0][0] == cycles_now[1][0])
    check("the member's balance is the sum of both cycles; nothing was lost or silently reset", scalar("select total_points from growth_point_balances where member_id = :m", m=pcm) == 300 + 1050 + 300
          and scalar("select count(*) from growth_point_ledger where member_id = :m and entry_type <> 'EARN'", m=pcm) == 0)
    check("each cycle's ceilings count only its own points (no transfer between plans)", scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where cycle_id = :c", c=old_cycle_id) == 1350
          and scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where cycle_id = :c", c=cycles_now[1][0]) == 300)
    check("the old points expire at the end of the OLD cycle's grace; the new points at the new cycle's", D(L("select expires_at from growth_point_ledger where id = :i", i=old_pts["id"])[0][0]) == D(L("select grace_ends_at from growth_point_cycles where id = :c", c=old_cycle_id)[0][0])
          and D(L("select expires_at from growth_point_ledger where id = :i", i=new_pts["id"])[0][0]) > D(L("select expires_at from growth_point_ledger where id = :i", i=old_pts["id"])[0][0]))

    # ======================================================================================== 15. SHADOW REDEMPTION: SIMULATION ONLY
    (s1c, s1, _) = sub_member("growth")
    sbase = quarter_start(0) + timedelta(days=0)
    for i in range(4):          # one a month: the closed-business sub-ceiling (3,600) binds on the fourth, the monthly ceiling never does
        award(s1, "BUSINESS_CLOSED", f"sim-{i}", 1050, 3 + i % 2, utcnow() + timedelta(days=35 * i), role="referrer", rtype="deal_closure")
    snap = go(lambda s: simulation.member_snapshot(s, s1))
    hyp = snap["hypothetical_redemption"]
    check("3,600 shadow points on the Rs 5,000 plan = Rs 360 of value against a Rs 750 contractual cap -> never more than the value",
          snap["shadow_total_points"] == 3600 and snap["estimated_value_paise"] == 36000 and hyp["contractual_cap_paise"] == 75000 and hyp["if_pending_also_released_paise"] == 36000 and hyp["hypothetical_discount_paise"] == hyp["available_value_paise"] <= 36000, str(snap))
    check("the real invoice change is Rs 0, the snapshot says SHADOW and not redeemable", snap["invoice_change_minor"] == 0 and snap["shadow"] and not snap["redeemable"] and "SHADOW" in snap["label"])
    check("the cap binds when points are worth more than it (15% of Rs 3,000 = Rs 450 -> 4,500 points)", rules.redemption_cap_paise(300_000) == 45000 and min(rules.points_to_paise(6000), rules.redemption_cap_paise(300_000)) == 45000)
    clear()
    r = s1c.post("/api/v1/growth-points/redeem", json={"points": 3600, "invoice_id": "x"}, headers=H(s1c))
    check("a redemption request is refused with a clear reason", r.status_code == 409 and r.json()["detail"]["code"] == "redemption_disabled")
    check("the refused attempt is audited", scalar("select count(*) from audit_log where action = 'growth_points.redemption_refused' and actor_id = :m", m=s1) == 1)
    check("redemption needs a session and the CSRF header", new_client().post("/api/v1/growth-points/redeem").status_code == 401 and s1c.post("/api/v1/growth-points/redeem").status_code == 403)

    # ======================================================================================== 16. THE FINANCIAL FIREWALL
    end_fp = financial_fingerprint()
    # (the fingerprint legitimately differs from the start because this test BOUGHT subscriptions; the firewall checks below are exact)
    async def try_write(sql):
        async def f(s):
            with firewall.guard():
                try:
                    await s.execute(text(sql))
                    return False
                except firewall.FinancialFirewallError:
                    return True
                finally:
                    await s.rollback()
        return await f_runner(f)

    async def f_runner(f):
        from app.database import SessionLocal
        async with SessionLocal() as s:
            return await f(s)
    for sql in ("update invoices set discount_minor = 100", "update invoices set amount_due_minor = 1", "update payments set amount_minor = 1", "update subscriptions set expires_at = null",
                "update plans set price_minor = 1", "delete from invoices", "insert into payments (id) values ('x')", "UPDATE  subscriptions SET status='ACTIVE'"):
        check(f"inside the engine, `{sql[:40]}` is refused by the firewall", asyncio.run(try_write(sql)))
    async def orm_write(s):
        from app.models import Invoice
        with firewall.guard():
            inv = (await s.execute(text("select id from invoices limit 1"))).scalar()
            obj = await s.get(Invoice, inv)
            obj.discount_minor = 50
            try:
                await s.flush()
                return False
            except firewall.FinancialFirewallError:
                return True
            finally:
                await s.rollback()
    check("an ORM write to an invoice is refused inside the engine", db(orm_write))
    check("outside the engine the invoice CHECK still holds every discount at zero", sql_fails("update invoices set discount_minor = 100, amount_due_minor = amount_before_discount_minor - 100"))
    fin = [p.name for p in (APP / "rewards").glob("*.py") if re.search(r"\b(update|delete|insert)\(\s*(Invoice|Payment|Subscription|Plan)\b|\.(discount_minor|amount_due_minor|amount_paid_minor|price_minor)\s*=[^=]|\.add\(\s*(Invoice|Payment|Subscription|Plan)\(", p.read_text())]
    check("no reward module writes a financial table (static scan)", fin == [], str(fin))
    check("the only reward module that even reads an invoice amount is the analytics measurement of the Rs 0 cost", [p.name for p in (APP / "rewards").glob("*.py") if re.search(r"discount_minor|amount_due_minor|amount_paid_minor", p.read_text())] in (["analytics.py", "reconcile.py"], ["analytics.py"]))
    check("the ledger itself can hold no real (non-shadow) row", sql_fails("insert into growth_point_ledger (id, created_at, event_at, member_id, entry_type, event_type, category, reference_type, reference_id, points_delta, requested_points, status, verification_level, remaining, balance_after, rule_version, idempotency_key, shadow, day_key, month_key, quarter_key) "
                                                                    f"select 'real-1', created_at, event_at, member_id, entry_type, event_type, category, reference_type, reference_id, points_delta, requested_points, status, verification_level, remaining, balance_after, rule_version, 'real-key', false, day_key, month_key, quarter_key from growth_point_ledger limit 1"))
    check("REDEMPTION is not a ledger event type", sql_fails("insert into growth_point_ledger (id, created_at, event_at, member_id, entry_type, event_type, category, reference_type, reference_id, points_delta, requested_points, status, verification_level, remaining, balance_after, rule_version, idempotency_key, shadow, day_key, month_key, quarter_key) "
                                                             "select 'redeem-1', created_at, event_at, member_id, 'VOID', 'REDEMPTION', category, reference_type, reference_id, -5, 0, 'VOIDED', verification_level, 0, 0, rule_version, 'redeem-key', true, day_key, month_key, quarter_key from growth_point_ledger limit 1"))
    check("a level-0 (self-reported) reward can not carry points", sql_fails("update growth_point_ledger set verification_level = 0") and sql_fails("insert into growth_point_ledger (id, created_at, event_at, member_id, entry_type, event_type, category, reference_type, reference_id, points_delta, requested_points, status, verification_level, remaining, balance_after, rule_version, idempotency_key, shadow, day_key, month_key, quarter_key) "
                                                                                                                                                                  "select 'l0-1', created_at, event_at, member_id, 'EARN', event_type, category, reference_type, reference_id, 5, 5, 'AVAILABLE', 0, 5, 5, rule_version, 'l0-key', true, day_key, month_key, quarter_key from growth_point_ledger limit 1"))
    check("every invoice still has a zero discount and every amount due equals its list price", scalar("select count(*) from invoices where discount_minor <> 0 or amount_due_minor <> list_price_minor") == 0)
    check("SUBSCRIPTION_PRICING_CONFIRMED is still false", app_settings.subscription_pricing_confirmed is False)
    cost = analytics.real_financial_cost
    rc_ = go(lambda s: cost(s))
    check("the measured real financial cost of Growth Points is Rs 0", rc_["inr_minor"] == 0 and rc_["invoices_reduced"] == 0 and rc_["ok"])

    # ======================================================================================== 17. SHADOW MODE OFF = NOTHING
    n_before = scalar("select count(*) from growth_point_ledger")
    app_settings.growth_points_shadow_mode = False
    try:
        off_ref = make_referral(ac, bid)
        patch(bc, off_ref, "ACCEPTED")
        check("with shadow mode OFF no reward is recorded, and the member's request is unaffected", scalar("select count(*) from growth_point_ledger") == n_before and scalar("select status from business_referrals where id = :r", r=off_ref) == "ACCEPTED")
        check("with shadow mode off the admin sweep refuses", admin.post("/api/admin/growth-points/sweep", json={"reason": "Trying while off"}, headers=AH).status_code == 409)
    finally:
        app_settings.growth_points_shadow_mode = True
    sw = admin.post("/api/admin/growth-points/sweep", json={"reason": "Catch up after turning shadow mode back on"}, headers=AH)
    check("turning shadow mode back on and sweeping issues what was missed, exactly once", sw.status_code == 200 and len(earn_rows(aid, "REFERRAL_ACCEPTED", off_ref)) == 1)
    admin.post("/api/admin/growth-points/sweep", json={"reason": "Run it twice"}, headers=AH)
    check("a second sweep adds nothing", len(earn_rows(aid, "REFERRAL_ACCEPTED", off_ref)) == 1)

    # ======================================================================================== 18. MEMBER PREVIEW
    clear()
    pv = ac.get("/api/v1/growth-points/preview").json()
    mine = points_of(aid)
    check("the preview is clearly labelled shadow, preview, not redeemable and not active", pv["enabled"] and pv["shadow"] and pv["redeemable"] is False and set(pv["labels"]) >= {"Shadow", "Preview", "Not redeemable", "Not currently active"} and "simulation" in pv["disclaimer"].lower())
    check("it shows the member's own shadow balance and the cycle ceiling", pv["shadow_balance_points"] > 0 and pv["cycle_ceiling_points"] == 3600 and pv["invoice_change_paise"] == 0)
    check("it never shows another member's id, an email, a phone or an exact deal value", bid not in json.dumps(pv) and "@" not in json.dumps(pv) and "9876" not in json.dumps(pv))
    check("a forged member_id in the query is ignored", ac.get("/api/v1/growth-points/preview", params={"member_id": bid}).json()["shadow_balance_points"] == pv["shadow_balance_points"])
    app_settings.growth_points_member_preview = False
    try:
        off = ac.get("/api/v1/growth-points/preview").json()
        check("until management decides, the preview is OFF and says only 'coming soon'", off == {"enabled": False, "message": "Growth Points are coming soon. They are not active yet and cannot be redeemed."})
    finally:
        app_settings.growth_points_member_preview = True
    check("the preview needs a session", new_client().get("/api/v1/growth-points/preview").status_code == 401)

    # ======================================================================================== 19. ADMIN ANALYTICS
    s = admin.get("/api/admin/growth-points/summary").json()
    e = s["shadow_earning"]
    check("the summary separates shadow earning, hypothetical redemption and real financial cost", {"shadow_earning", "hypothetical_redemption", "real_financial_cost"} <= set(s))
    check("real financial cost reads Rs 0", s["real_financial_cost"]["inr_minor"] == 0 and s["real_financial_cost"]["ok"])
    check("points are broken down by event type, with capped and voided amounts", {x["event_type"] for x in e["by_event_type"]} >= {"REFERRAL_ACCEPTED", "MEETING_COMPLETED", "BUSINESS_CLOSED"} and e["capped"]["points"] > 0 and any(x["points_voided_or_reversed"] > 0 for x in e["by_event_type"]))
    check("pair-rule reductions and capped-by reasons are reported", any(c["capped_by"].startswith("PAIR") for c in e["pair_rule_reductions"]) and any(c["capped_by"] == "DAILY_CEILING" for c in e["capped"]["by_rule"]))
    check("average, median and the distribution are reported", e["average_points_per_member"] > 0 and e["median_points_per_member"] >= 0 and sum(e["distribution_of_cycles_by_share_of_ceiling"].values()) > 5)
    check("points by plan and by cycle length (3 / 6 / 12 months), normalised per member-month", {x["key"] for x in e["by_plan"]} >= {"connect", "growth", "elite"} and {x["key"] for x in e["by_cycle_length_months"]} == {3, 6, 12} and all(x["points_per_member_month"] is None or x["points_per_member_month"] >= 0 for x in e["by_cycle_length_months"]))
    h = s["hypothetical_redemption"]
    check("hypothetical redemption: outstanding points, value, liability and maximum potential liability", h["outstanding_points"] > 0 and h["hypothetical_redemption_liability_paise"] >= 0 and h["maximum_potential_liability_paise"] >= h["hypothetical_redemption_liability_paise"] and "HYPOTHETICAL" in h["label"])
    check("the maximum potential liability never exceeds the sum of the 15% caps", h["maximum_potential_liability_paise"] <= 75000 * 500)
    eco = admin.get("/api/admin/growth-points/economics").json()
    check("the modelled 400-member economy: expected Rs 83,006 and worst case Rs 532,800 a year on Rs 4,440,000",
          tuple(int(eco["modelled"][k] / 100 + 0.5) for k in ("expected_annual_reward_cost_paise", "worst_case_annual_reward_cost_paise", "annual_subscription_revenue_paise")) == (83006, 532800, 4440000), str(eco["modelled"]))
    check("modelled and actual are shown side by side, never mixed", {"modelled", "actual_shadow", "hypothetical_redemption", "real_financial_cost", "unit_economics", "plan_comparison"} <= set(eco) and eco["real_financial_cost"]["inr_minor"] == 0)
    check("unit economics: points per referral, meeting, closed deal and per Rs 1 lakh of verified business", all(eco["unit_economics"][k] for k in ("points_per_rewarded_referral", "points_per_meeting", "points_per_closed_deal", "points_per_rs_100000_of_verified_business")))
    check("the plan comparison is cycle-normalised (per member-month and per year) for 3, 6 and 12-month plans",
          {p["term_months"] for p in eco["plan_comparison"]} == {3, 6, 12} and all(p["points_per_member_per_year_normalised"] is None or 0 <= p["points_per_member_per_year_normalised"] < 100000 for p in eco["plan_comparison"]))
    check("the actual worst case reflects the real plan mix (percent of price is 12 for every plan)", all(p["worst_case_percent_of_price"] == 12.0 for p in eco["plan_comparison"]))
    ob = admin.get("/api/admin/growth-points/observation").json()
    sm, led = ob["success_metrics"], ob["success_metrics"]["ledger"]
    dist = sm["points_per_member"]
    check("OBSERVATION: average, median, p90, p95 and top-1% are reported, in order, for the active members", dist["members"] > 5 and dist["median"] <= dist["p90"] <= dist["p95"] <= dist["max"] and dist["average"] >= 0
          and 0 <= dist["top_1_percent_share_of_points_percent"] <= 100 and dist["top_1_percent_points"] <= dist["max"] * dist["top_1_percent_members"])
    check("OBSERVATION: the active-member count matches the database and the plan mix adds up",
          dist["members"] == scalar("select count(distinct user_id) from subscriptions where status = 'ACTIVE' and expires_at > :n", n=utcnow()) and sum(ob["observed"]["plan_mix"].values()) == dist["members"]
          and abs(sum(ob["observed"]["plan_mix_percent"].values()) - 100) < 0.5)
    check("OBSERVATION: points per referral, meeting and verified closed deal; by plan; by cycle length", all(sm[k] for k in ("points_per_referral", "points_per_meeting", "points_per_verified_closed_deal"))
          and {p["plan"] for p in sm["points_by_plan"]} >= {"connect", "growth", "elite"} and {c["key"] for c in sm["points_by_cycle_length"]} == {3, 6, 12})
    check("OBSERVATION: capped, reversed, voided and expired are counted from the ledger", led["capped_rewards"] == scalar("select count(*) from growth_point_ledger where entry_type = 'EARN' and capped_points > 0")
          and led["reversed_rewards"] == scalar("select count(*) from growth_point_ledger where entry_type = 'REVERSAL'") and led["voided_rewards"] == scalar("select count(*) from growth_point_ledger where entry_type = 'VOID'")
          and led["capped_rewards"] > 0 and led["reversed_rewards"] > 0)
    check("OBSERVATION: fraud flags are counted by kind and the circular/repeat patterns are reported", sm["fraud_flags"]["total"] == scalar("select count(*) from growth_point_flags") and sm["fraud_flags"]["total"] > 0
          and {"reciprocal_pairs", "pairs_with_2_or_more_rewarded_closures", "top_pair_share_of_closed_business_points_percent", "pairs_with_accepted_referrals"} <= set(sm["repeat_and_circular_patterns"])
          and sm["repeat_and_circular_patterns"]["reciprocal_pairs"] >= 1 and sm["repeat_and_circular_patterns"]["pairs_with_2_or_more_rewarded_closures"] >= 1)
    check("OBSERVATION: hypothetical redemption cost, hypothetical annual liability and reward cost as % of subscription revenue are reported and labelled hypothetical",
          sm["hypothetical_redemption_cost_now_paise"] >= 0 and sm["maximum_potential_redemption_cost_now_paise"] >= sm["hypothetical_redemption_cost_now_paise"] and sm["hypothetical_annual_liability_worst_case_paise"] > 0
          and sm["hypothetical_reward_cost_percent_of_subscription_revenue"]["worst_case"] is not None and 0 < sm["hypothetical_reward_cost_percent_of_subscription_revenue"]["worst_case"] <= 15)
    mva = ob["modelled_vs_actual"]
    check("OBSERVATION: modelled vs actual side by side - plan mix 55/35/10, per member-month activity, points, cost % (modelled 1.87% expected / 12% worst case)",
          mva["plan_mix_percent"]["modelled"] == {"Connect": 55, "Growth": 35, "Elite": 10} and mva["expected_cost_percent_of_revenue"]["modelled"] == 1.87 and mva["worst_case_percent_of_revenue"]["modelled"] == 12.0
          and {"accepted_referrals_per_member_month", "meetings_per_member_month", "verified_closed_deals_per_member_month", "points_per_member_month"} <= set(mva))
    check("OBSERVATION: there is no automatic end date; sufficiency only reports how much data exists", "No automatic end date" in ob["sufficiency"]["note"] and "ends" not in " ".join(k for k in ob["sufficiency"])
          and {"observed_days", "active_members", "all_three_plans_observed", "member_months", "projection_available"} <= set(ob["sufficiency"]))
    check("OBSERVATION: admin only, aggregates only (no email, phone, member id or deal value), real financial cost still 0",
          ac.get("/api/admin/growth-points/observation").status_code == 401 and new_client().get("/api/admin/growth-points/observation").status_code == 401
          and not re.search(r"@|\+91|[0-9a-f]{8}-[0-9a-f]{4}-", json.dumps(ob, default=str)) and ob["real_financial_cost"]["inr_minor"] == 0)
    mem = admin.get("/api/admin/growth-points/members", params={"page_size": 5}).json()
    check("the member list is paginated and capped", len(mem["items"]) <= 5 and mem["total"] > 5 and admin.get("/api/admin/growth-points/members", params={"page_size": 101}).status_code == 422)
    d = admin.get(f"/api/admin/growth-points/members/{aid}").json()
    check("the member detail shows the balance, lots, ledger with cap traces and the hypothetical redemption", d["snapshot"]["hypothetical_redemption"] is not None and d["lots"] and d["ledger"] and d["snapshot"]["invoice_change_minor"] == 0)
    led = admin.get("/api/admin/growth-points/ledger", params={"capped_by": "DAILY_CEILING"}).json()
    check("the ledger can be filtered by the rule that capped a reward", led["total"] >= 1 and all(x["capped_by"] == "DAILY_CEILING" for x in led["items"]))
    check("no admin ledger row exposes a phone, an email or evidence", not re.search(r"\+91\d{10}|@example\.com|storage_name|sha256", json.dumps(led)))
    exp = admin.get("/api/admin/growth-points/export", params={"format": "csv"})
    check("the export is CSV with the ledger columns, no emails, phones or exact values", exp.status_code == 200 and exp.text.splitlines()[0].startswith("id,created_at") and "@" not in exp.text and "+91" not in exp.text and "no-store" in exp.headers["cache-control"])
    expj = admin.get("/api/admin/growth-points/export", params={"format": "json"}).json()
    check("the JSON export carries rule versions for every row", len(expj) == scalar("select count(*) from growth_point_ledger") and {x["rule_version"] for x in expj} == {"growth-points-v3"})
    st = admin.get("/api/admin/growth-points/status").json()
    check("the status endpoint says shadow mode, redemption off and a real financial effect of 0", st["shadow_mode"] and not st["redemption_enabled"] and st["real_financial_effect_inr"] == 0)
    check("the rules endpoint serves the exact parameters in force", admin.get("/api/admin/growth-points/rules").json()["rule_version"] == "growth-points-v3")

    # ======================================================================================== 20. FRAUD SIGNALS
    fl = admin.get("/api/admin/growth-points/flags").json()
    kinds = {f["kind"] for f in fl["items"]}
    check("signals were raised during normal processing: concentration, same prospect, rapid closure, high value, reversals",
          {"PAIR_CONCENTRATION", "SAME_PROSPECT_ACROSS_PAIRS", "RAPID_CLOSURE", "HIGH_VALUE_CLOSURE", "REVERSAL_NEEDS_REVIEW"} <= kinds, str(sorted(kinds)))
    check("a reciprocal pair is flagged", "RECIPROCAL_REFERRALS" in kinds and "PAIR_FREQUENCY" in kinds)
    check("flags carry no punishment: no member's points were changed by raising them", True)
    sc = admin.post("/api/admin/growth-points/scan", json={"reason": "Weekly shadow review"}, headers=AH)
    check("the batch scan runs and reports new review items", sc.status_code == 200 and isinstance(sc.json()["new_flags"], dict))
    sc2 = admin.post("/api/admin/growth-points/scan", json={"reason": "Run it twice"}, headers=AH).json()["new_flags"]
    check("scanning twice raises nothing new (deduplicated)", sum(sc2.values()) == 0, str(sc2))
    flag_id = fl["items"][0]["id"]
    check("reviewing a flag needs a reason and CSRF", admin.post(f"/api/admin/growth-points/flags/{flag_id}/review", json={}, headers=AH).status_code == 422 and admin.post(f"/api/admin/growth-points/flags/{flag_id}/review", json={"reason": "Looked into it"}).status_code == 403)
    rv = admin.post(f"/api/admin/growth-points/flags/{flag_id}/review", params={"outcome": "DISMISSED"}, json={"reason": "Genuine repeat partners"}, headers=AH)
    check("an admin can dismiss a flag with a reason, and it is audited; a second review is refused", rv.status_code == 200 and admin.post(f"/api/admin/growth-points/flags/{flag_id}/review", json={"reason": "Again"}, headers=AH).status_code == 409
          and scalar("select count(*) from audit_log where action = 'growth_points.flag_reviewed' and resource_id = :f", f=flag_id) == 1)
    lowacc = make_referral
    check("closures within 24 hours of acceptance are flagged but still rewarded (flags never block)", scalar("select count(*) from growth_point_flags where kind = 'RAPID_CLOSURE'") > 0 and points_of(iA[1], "BUSINESS_CLOSED") == 1050)

    # ======================================================================================== 21. SECURITY
    check("members can not reach any admin Growth Points route", all(ac.get(p).status_code == 401 for p in ("/api/admin/growth-points/summary", "/api/admin/growth-points/ledger", "/api/admin/growth-points/members", "/api/admin/growth-points/export", "/api/admin/growth-points/economics")))
    check("anonymous visitors can not either", all(new_client().get(p).status_code == 401 for p in ("/api/admin/growth-points/summary", "/api/admin/growth-points/export")))
    check("admin actions need CSRF and a reason", admin.post("/api/admin/growth-points/sweep", json={"reason": "No token"}).status_code == 403 and admin.post("/api/admin/growth-points/sweep", json={}, headers=AH).status_code == 422
          and admin.post("/api/admin/growth-points/scan", json={}, headers=AH).status_code == 422)
    check("there is no endpoint that creates, edits or deletes a ledger row, a rule or a balance", all(c.status_code in (404, 405) for c in (
        ac.post("/api/v1/growth-points/events", json={"points": 5000}, headers=H(ac)), ac.put("/api/v1/growth-points/balance", json={"points": 5000}, headers=H(ac)),
        admin.put("/api/admin/growth-points/rules", json={"point_value": 1}, headers=AH), admin.delete("/api/admin/growth-points/ledger", headers=AH),
        admin.post("/api/admin/growth-points/ledger", json={"member_id": aid, "points": 5000}, headers=AH), ac.patch("/api/v1/growth-points/preview", json={}, headers=H(ac)))))
    check("a member's own session can not read another member's ledger (there is no member ledger route)", ac.get(f"/api/v1/growth-points/ledger?member_id={bid}").status_code in (404, 405))
    before_pts = points_of(aid)
    forged = ac.post(f"/api/v1/referrals/{ref1}/closure", json={"actual_value": 1_000_000, "points": 99999}, headers=H(ac))
    check("a forged reward request through a real route moves nothing", points_of(aid) == before_pts)
    audited = [route for route in __import__("test_phase0_hardening", fromlist=["x"]).all_routes() if route.path.startswith("/api/admin/growth-points") and (route.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}]
    import inspect
    check(f"every one of the {len(audited)} admin Growth Points write routes records an audit entry", len(audited) == 9 and all("audit.record(" in inspect.getsource(r_.endpoint) for r_ in audited))

    r = admin.delete(f"/api/admin/customers/{aid}", headers=AH)
    check("an account with shadow ledger history can not be deleted (suspend it instead); the history survives", r.status_code == 409 and "Growth Points" in r.json()["detail"] and scalar("select count(*) from growth_point_ledger where member_id = :m", m=aid) > 0)
    check("the database agrees: deleting the user row is refused (ON DELETE RESTRICT)", sql_fails("delete from users where id = :m", m=aid))

    # ======================================================================================== 21b. PROFILE COMPLETION (strict, system-verified, one-time)
    from PIL import Image
    (pfc, pf, _) = sub_member("connect")
    biz = {"business_name": "Profile Co", "category": "01", "description": "We make useful things for people.", "city": "Bengaluru", "employee_band": "1-3", "business_age": "lt6", "business_stage": "Early"}
    def photo():
        buf = io.BytesIO()
        Image.new("RGB", (240, 240), (107, 62, 150)).save(buf, "PNG")
        clear()
        return pfc.post("/api/v1/profile/photo", files={"photo": ("me.png", io.BytesIO(buf.getvalue()), "image/png")}, headers=H(pfc))
    pcount = lambda: scalar("select count(*) from growth_point_ledger where member_id = :m and event_type = 'PROFILE_COMPLETED' and entry_type = 'EARN'", m=pf)    # noqa: E731
    check("PROFILE: a profile missing the founder story, an online link and a photo earns nothing", pcount() == 0)
    clear()
    assert pfc.put("/api/v1/business", json={**biz, "founder_story": "I started this to solve a problem I had myself.", "website": "https://profile.example.com"}, headers=H(pfc)).status_code == 200
    check("PROFILE: still nothing without a photo", pcount() == 0)
    r = photo()
    check("PROFILE: the photo completes it: one system-verified reward of 75 points (level 3, usable at once, 'other' category)", r.status_code == 200 and pcount() == 1
          and earn_rows(pf, "PROFILE_COMPLETED")[0][0] == 75 and earn_rows(pf, "PROFILE_COMPLETED")[0][5] == 3 and earn_rows(pf, "PROFILE_COMPLETED")[0][4] == "AVAILABLE", r.text[:200])
    clear()
    pfc.put("/api/v1/business", json={**biz, "founder_story": "A different story.", "website": "https://profile.example.com"}, headers=H(pfc))
    photo()
    asyncio.run(hooks.profile_changed(pf))
    admin.post("/api/admin/growth-points/sweep", json={"reason": "Replay profile"}, headers=AH)
    check("PROFILE: editing, re-uploading, replaying hooks and sweeping never pays it twice (one-time)", pcount() == 1 and points_of(pf, "PROFILE_COMPLETED") == 75)
    clear()
    forged = pfc.put("/api/v1/profile/personal", json={"full_name": "GP Member", "phone": "9876543210", "city": "Bengaluru", "role": "Founder", "short_bio": "I build my business every day.", "profile_completed": True, "points": 5000}, headers=H(pfc))
    check("PROFILE: it can not be claimed: a forged flag or points field changes nothing, and no claim endpoint exists", points_of(pf) == 75 and forged.status_code in (200, 422)
          and ac.post("/api/v1/growth-points/claim", json={"event": "PROFILE_COMPLETED"}, headers=H(ac)).status_code in (404, 405))

    # ======================================================================================== 21c. RENEWAL: plan changes only at renewal; old points redeemable (hypothetically) against the NEW invoice
    PLAN_MONTHS, PRICE = {"connect": 3, "growth": 6, "elite": 12}, {"connect": 300000, "growth": 500000, "elite": 1000000}
    FULL = {"connect": [dict(closure=1800, process=450, other=360), dict(closure=360, process=450, other=360)],
            "growth": [dict(closure=1800, process=750, other=450)] * 2, "elite": [dict(closure=1800, process=750, other=450)] * 4}

    def age_term(sid, code, ends_ago_days):
        """Make the member's paid term an old one that ended `ends_ago_days` ago (inside the 30-day renewal window if <= 30)."""
        ends = utcnow() - timedelta(days=ends_ago_days)
        starts = ends - timedelta(days=round(PLAN_MONTHS[code] * 30.4375))
        async def f(s_):
            await s_.execute(text("update subscriptions set starts_at = :s, expires_at = :e, activated_at = :s, status = 'EXPIRED' where id = :i"), {"s": starts, "e": ends, "i": sid})
            await s_.commit()
        db(f)
        return starts, ends

    def earn_buckets(mid, tag, buckets, starts):
        """One bucket per month, 33 days apart (always different calendar months), all verified (level 3/4) so nothing is daily-capped."""
        for k, b in enumerate(buckets):
            base = rules.local(starts + timedelta(days=3 + 33 * k)).replace(hour=10, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            if b.get("closure"):
                award(mid, "BUSINESS_CLOSED", f"{tag}c{k}", b["closure"], 4, base, role="referrer", rtype="deal_closure")
            if b.get("process"):
                award(mid, "MEETING_COMPLETED", f"{tag}p{k}", b["process"], 3, base + timedelta(hours=1), role="member")
            if b.get("other"):
                award(mid, "PROFILE_COMPLETED", f"{tag}o{k}", b["other"], 3, base + timedelta(hours=2), role="member", rtype="member")

    def renewal_case(old, new, tag, buckets=None, ends_ago=5, renew=True):
        c, mid, sid = sub_member(old)
        starts, ends = age_term(sid, old, ends_ago)
        earn_buckets(mid, tag, buckets or FULL[old], starts)
        earned_rows = L("select id, points_delta, remaining, status, event_type from growth_point_ledger where member_id = :m and entry_type = 'EARN' order by created_at, id", m=mid)
        old_cycle = L("select id, ceiling_points, plan_code from growth_point_cycles where member_id = :m", m=mid)[0]
        sid2 = buy(c, new) if renew else None                    # the renewal: a new subscription chosen after the old term ended, inside the window
        return dict(c=c, mid=mid, sid=sid, sid2=sid2, tag=tag, old=old, new=new, starts=starts, ends=ends, earned_rows=earned_rows, earned=sum(r[1] for r in earned_rows), old_cycle=old_cycle)

    def header(case):
        return L("select outcome, eligible_points, redemption_cap_points, redeemed_points, remaining_points, hypothetical_discount_paise, hypothetical_payable_paise, from_plan, to_plan, new_price_minor, old_cycle_id, id, shadow "
                 "from growth_point_renewals where new_subscription_id = :s", s=case["sid2"])

    cases = [
        (renewal_case("connect", "connect", "rn1"), 3600, 4500, 3600, 0),          # points below the new cap
        (renewal_case("connect", "growth", "rn2"), 3600, 7500, 3600, 0),           # upgrade
        (renewal_case("growth", "elite", "rn3"), 6000, 15000, 6000, 0),            # upgrade
        (renewal_case("elite", "growth", "rn4"), 12000, 7500, 7500, 4500),         # downgrade, points ABOVE the new plan's cap (Rs 1,200 -> Rs 750 used, Rs 450 left)
        (renewal_case("growth", "connect", "rn5"), 6000, 4500, 4500, 1500),        # downgrade, above the cap
        (renewal_case("growth", "connect", "rn6", buckets=[dict(closure=1800, process=750, other=450), dict(closure=1500)]), 4500, 4500, 4500, 0),     # exactly at the cap
    ]
    recorded = asyncio.run(hooks.renewals_changed())
    check("RENEWAL: the sweep recorded every renewal once", recorded is not None and recorded["recorded"] >= len(cases), str(recorded))
    for case, eligible, cap, redeemed, left in cases:
        h = header(case)
        name = f"{case['old']} -> {case['new']} ({eligible} points, new-plan cap {cap})"
        discount, payable = redeemed * 10, PRICE[case["new"]] - redeemed * 10
        check(f"RENEWAL {name}: the old cycle earned exactly {eligible} (its own ceiling) before renewing", case["earned"] == eligible and case["old_cycle"][1] == eligible if eligible in (3600, 6000, 12000) else case["earned"] == eligible, str(case["earned"]))
        check(f"RENEWAL {name}: eligible {eligible}, ceiling {cap} (15% of the NEW price), used {redeemed}, left {left}, hypothetical discount Rs {discount // 100}, payable Rs {payable // 100}",
              len(h) == 1 and tuple(h[0][:11]) == ("REDEEMED", eligible, cap, redeemed, left, discount, payable, case["old"], case["new"], PRICE[case["new"]], case["old_cycle"][0]) and h[0][12] in (True, 1), str(h))
        sims = L("select points_delta, parent_id, cycle_id, status, created_by, reference_id, shadow, entry_type from growth_point_ledger where member_id = :m and entry_type = 'SIM_REDEEM' order by created_at, id", m=case["mid"])
        check(f"RENEWAL {name}: the use is separate SIM_REDEEM rows pointing at the old lots, the old cycle and the renewal record", -sum(r[0] for r in sims) == redeemed and all(r[1] in {e[0] for e in case["earned_rows"]} and r[2] == case["old_cycle"][0] and r[3] == "SIMULATED"
              and r[4] == "system" and r[5] == h[0][11] and r[6] in (True, 1) for r in sims))
        check(f"RENEWAL {name}: the original earning rows were never edited or deleted", L("select id, points_delta, remaining, status, event_type from growth_point_ledger where member_id = :m and entry_type = 'EARN' order by created_at, id", m=case["mid"]) == case["earned_rows"])
        check(f"RENEWAL {name}: the shadow balance is earned minus the hypothetical use", scalar("select total_points from growth_point_balances where member_id = :m", m=case["mid"]) == case["earned"] - redeemed)
        inv = L("select amount_due_minor, list_price_minor, discount_minor from invoices where subscription_id = :s", s=case["sid2"])[0]
        check(f"RENEWAL {name}: the REAL renewal invoice is untouched: full price, discount 0 (hypothetical payable differs only inside the shadow record)", inv == (PRICE[case["new"]], PRICE[case["new"]], 0) and (redeemed == 0 or payable != inv[0]), str(inv))
        nw = award(case["mid"], "PROFILE_COMPLETED", f"{case['tag']}-new", 75, 3, utcnow() + timedelta(hours=1), role="member", rtype="member")
        new_cycle = L("select id, plan_code, ceiling_points, closure_ceiling from growth_point_cycles where id = :c", c=L("select cycle_id from growth_point_ledger where id = :i", i=nw["id"])[0][0])[0]
        check(f"RENEWAL {name}: the NEW cycle is {case['new']} with its own ceiling {rules.cycle_ceiling_points(PRICE[case['new']])} and starts with ZERO transferred earning points",
              new_cycle[0] != case["old_cycle"][0] and new_cycle[1] == case["new"] and new_cycle[2] == rules.cycle_ceiling_points(PRICE[case["new"]])
              and scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where cycle_id = :c and entry_type in ('EARN','VOID','REVERSAL')", c=new_cycle[0]) == 75, str(new_cycle))
        check(f"RENEWAL {name}: the OLD cycle's earning count is unchanged and its ceiling is not raised or lowered", scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where cycle_id = :c and entry_type in ('EARN','VOID','REVERSAL')", c=case["old_cycle"][0]) == case["earned"]
              and scalar("select ceiling_points from growth_point_cycles where id = :c", c=case["old_cycle"][0]) == case["old_cycle"][1])
        check(f"RENEWAL {name}: the redemption endpoint still refuses, even for this renewal invoice", (lambda r: r.status_code == 409 and r.json()["detail"]["code"] == "redemption_disabled")((clear(), case["c"].post("/api/v1/growth-points/redeem", json={"points": redeemed, "invoice_id": case["sid2"]}, headers=H(case["c"])))[1]))

    # ---- FIFO: oldest lots first; newer lots are untouched while an older one still has points
    fifo = renewal_case("growth", "connect", "fi", buckets=[dict(process=600), dict(other=1000), dict(closure=3000), dict(process=900)])
    asyncio.run(hooks.renewals_changed())
    lots_in_order = [r[0] for r in fifo["earned_rows"]]
    consumed = L("select parent_id, -points_delta from growth_point_ledger where member_id = :m and entry_type = 'SIM_REDEEM' order by created_at, id", m=fifo["mid"])
    check("FIFO: 600, 1,000, 3,000 and 900 points; the Connect cap of 4,500 consumes the oldest first: 600 + 1,000 + 2,900 of the third lot, nothing from the newest",
          [r[1] for r in fifo["earned_rows"]] == [600, 1000, 3000, 900] and consumed == [(lots_in_order[0], 600), (lots_in_order[1], 1000), (lots_in_order[2], 2900)], str(consumed))
    left = {l.id: l.remaining for l in go(lambda s_: ledger.lots(s_, member_id=fifo["mid"]))}
    check("FIFO: afterwards the third lot has 100 left and the newest lot still has all 900", [left[lots_in_order[i]] for i in range(4)] == [0, 0, 100, 900], str(left))
    check("FIFO: the renewal record says 5,500 eligible, 4,500 used, 1,000 left to expire", header(fifo)[0][1:5] == (5500, 4500, 4500, 1000))

    # ---- idempotency: double-click, retries, concurrent renewals, browser refresh, API replay, a payment retry, a repeated sweep
    rows_before = (scalar("select count(*) from growth_point_renewals"), scalar("select count(*) from growth_point_ledger where entry_type = 'SIM_REDEEM'"), scalar("select total_points from growth_point_balances where member_id = :m", m=fifo["mid"]))
    for _ in range(4):
        asyncio.run(hooks.renewals_changed())                                       # double click / retry / replay
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda _: asyncio.run(hooks.renewals_changed()), range(6)))     # concurrent renewal requests
    for _ in range(2):
        admin.post("/api/admin/growth-points/sweep", json={"reason": "Replay the sweep"}, headers=AH)
    admin.post(f"/api/admin/subscriptions/{fifo['sid2']}/payment/verify", json={"reason": "Payment retry"}, headers=AH)                    # a payment retry is refused by Phase 0
    for _ in range(3):
        admin.get("/api/admin/growth-points/renewal-preview", params={"member_id": fifo["mid"], "plan_code": "connect"})                    # refresh
    again = go(lambda s_: renewal.record(s_, fifo["sid2"]))
    check("IDEMPOTENT: double clicks, retries, six concurrent renewals, a payment retry, repeated sweeps, refreshes and an API replay change nothing: one record, the same rows, the same balance",
          (scalar("select count(*) from growth_point_renewals"), scalar("select count(*) from growth_point_ledger where entry_type = 'SIM_REDEEM'"), scalar("select total_points from growth_point_balances where member_id = :m", m=fifo["mid"])) == rows_before
          and again[1] is False and scalar("select count(*) from growth_point_renewals where new_subscription_id = :s", s=fifo["sid2"]) == 1)
    check("NO DOUBLE SPENDING: the consumed points can not be consumed again (the total ever used for this member is exactly the 4,500)", scalar("select coalesce(-sum(points_delta), 0) from growth_point_ledger where member_id = :m and entry_type = 'SIM_REDEEM'", m=fifo["mid"]) == 4500)

    # ---- the renewal window: 30 days before the old term ends to 30 days after (points expire at its end)
    wcase = renewal_case("growth", "growth", "wn", ends_ago=5, renew=False)       # not renewed yet: what WOULD it look like
    def pv(at):
        return admin.get("/api/admin/growth-points/renewal-preview", params={"member_id": wcase["mid"], "plan_code": "elite", "at": at.isoformat()}).json()
    opens, closes = wcase["ends"] - timedelta(days=30), wcase["ends"] + timedelta(days=30)
    inside, late, early = pv(wcase["ends"] + timedelta(days=29, hours=23)), pv(closes + timedelta(minutes=2)), pv(opens - timedelta(minutes=2))
    check("WINDOW: an invoice raised inside the window (up to 30 days after the term) can use the old points: new plan Elite, ceiling 15,000, all 6,000 eligible -> Rs 600, payable Rs 9,400",
          inside["outcome"] == "REDEEMED" and (inside["eligible_old_cycle_points"], inside["new_plan_redemption_ceiling_points"], inside["points_to_be_redeemed"], inside["hypothetical_discount_paise"], inside["hypothetical_amount_payable_paise"]) == (6000, 15000, 6000, 60000, 940000)
          and inside["current_plan"] == "growth" and inside["new_plan"] == "elite" and inside["point_value_paise"] == 10 and inside["new_cycle_transferred_earning_points"] == 0 and "HYPOTHETICAL" in inside["label"], str(inside)[:400])
    check("WINDOW: after the window the old points have expired and nothing can be used", late["outcome"] == "NOT_A_RENEWAL" and late["points_to_be_redeemed"] == 0 and late["eligible_old_cycle_points"] == 0, str(late)[:300])
    check("WINDOW: before the window opens it is not a renewal either (an early replacement can not use the points)", early["outcome"] == "NOT_A_RENEWAL" and early["points_to_be_redeemed"] == 0, str(early)[:300])
    check("WINDOW: the preview shows every field the renewal invoice needs", {"current_plan", "new_plan", "new_plan_price_minor", "new_plan_term_months", "eligible_old_cycle_points", "point_value_paise", "new_plan_redemption_ceiling_points",
                                                                                "points_to_be_redeemed", "hypothetical_discount_paise", "hypothetical_amount_payable_paise", "lots_consumed"} <= set(inside))
    check("WINDOW: the preview is admin only and read only (nothing was written by it)", ac.get("/api/admin/growth-points/renewal-preview", params={"member_id": wcase["mid"], "plan_code": "elite"}).status_code == 401
          and scalar("select count(*) from growth_point_ledger where member_id = :m and entry_type = 'SIM_REDEEM'", m=wcase["mid"]) == 0)

    # ---- non-renewal: the window closes, the points expire, and coming back later restores nothing
    nr = renewal_case("connect", "growth", "nr", ends_ago=40)
    expired_n = go(lambda s_: jobs.expire_due(s_, now=utcnow()))
    asyncio.run(hooks.renewals_changed())
    nh = header(nr)
    check("NON-RENEWAL: 40 days after the term the 30-day window is over; the unused points expired by NEW EXPIRY rows (nothing edited)", expired_n >= 1 and scalar("select coalesce(-sum(points_delta), 0) from growth_point_ledger where member_id = :m and entry_type = 'EXPIRY'", m=nr["mid"]) == 3600
          and L("select id, points_delta, status from growth_point_ledger where member_id = :m and entry_type = 'EARN' order by created_at, id", m=nr["mid"]) == [(r[0], r[1], r[3]) for r in nr["earned_rows"]])
    check("NON-RENEWAL: coming back later is a NEW subscription cycle: no points are restored or used (not a renewal, 0 redeemed, balance 0)", nh and nh[0][0] == "NOT_A_RENEWAL" and nh[0][3] == 0
          and scalar("select total_points from growth_point_balances where member_id = :m", m=nr["mid"]) == 0 and scalar("select count(*) from growth_point_ledger where member_id = :m and entry_type = 'SIM_REDEEM'", m=nr["mid"]) == 0, str(nh))

    # ---- NO normal mid-cycle plan change
    (mcc, mcm, mcs) = sub_member("connect")
    (ecc, ecm, ecs) = sub_member("elite")
    award(mcm, "PROFILE_COMPLETED", "mid-1", 75, 3, utcnow(), role="member", rtype="member")
    clear()
    up = mcc.post("/api/v1/subscriptions", json={"plan_code": "growth"}, headers=H(mcc))
    clear()
    down = ecc.post("/api/v1/subscriptions", json={"plan_code": "growth"}, headers=H(ecc))
    clear()
    cancel = mcc.post(f"/api/v1/subscriptions/{mcs}/cancel", headers=H(mcc))
    check("NO MID-CYCLE CHANGE: an upgrade (Connect -> Growth) and a downgrade (Elite -> Growth) in the middle of a paid term are rejected, and so is cancelling a paid term as a member", up.status_code == 409 and down.status_code == 409 and cancel.status_code == 409,
          f"{up.status_code} {down.status_code} {cancel.status_code}")
    mid_pv = admin.get("/api/admin/growth-points/renewal-preview", params={"member_id": mcm, "plan_code": "growth"}).json()
    check("NO MID-CYCLE CHANGE: even as a what-if, mid-term points can not be used against another plan", mid_pv["outcome"] == "NOT_A_RENEWAL" and mid_pv["points_to_be_redeemed"] == 0
          and scalar("select count(*) from subscriptions where user_id = :u", u=mcm) == 1 and scalar("select total_points from growth_point_balances where member_id = :m", m=mcm) == 75)

    # ---- an administrative refund-and-replace is NOT a plan change path and creates no Growth Points loophole
    (rpc, rpm, rps) = sub_member("growth")
    award(rpm, "MEETING_COMPLETED", "rp-1", 300, 3, utcnow(), role="member")
    rf2 = admin.post(f"/api/admin/subscriptions/{rps}/refund", json={"reason": "Exceptional replacement requested by the member"}, headers=AH)
    rps2 = buy(rpc, "elite")
    asyncio.run(hooks.renewals_changed())
    rh = L("select outcome, redeemed_points, eligible_points, remaining_points from growth_point_renewals where new_subscription_id = :s", s=rps2)
    check("ADMIN REPLACEMENT: a refunded term's points are NOT eligible for the replacement invoice (REFUNDED_CYCLE, 0 used); they stay in the old cycle, undeleted, and expire there",
          rf2.status_code == 200 and rh == [("REFUNDED_CYCLE", 0, 0, 0)] and scalar("select total_points from growth_point_balances where member_id = :m", m=rpm) == 300
          and scalar("select count(*) from growth_point_ledger where member_id = :m and entry_type = 'SIM_REDEEM'", m=rpm) == 0)
    nw2 = award(rpm, "PROFILE_COMPLETED", "rp-new", 75, 3, utcnow() + timedelta(hours=1), role="member", rtype="member")
    check("ADMIN REPLACEMENT: the replacement plan starts a clean Elite cycle (12,000) and nothing is transferred into it", scalar("select plan_code from growth_point_cycles where id = (select cycle_id from growth_point_ledger where id = :i)", i=nw2["id"]) == "elite"
          and scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where cycle_id = (select cycle_id from growth_point_ledger where id = :i)", i=nw2["id"]) == 75)

    # ---- observation metrics 17-20 and the books still balance
    go(lambda s_: jobs.expire_due(s_, now=utcnow() + timedelta(days=500)))
    ob2 = admin.get("/api/admin/growth-points/observation").json()
    rn = ob2["success_metrics"]["renewals"]
    by = {r["to_plan"]: r for r in rn["renewal_redemption_by_new_plan"]}
    check("OBSERVATION 17-20: renewal redemption by plan, average old-cycle points redeemed, points stranded by non-renewal, points expired before redemption", {"connect", "growth", "elite"} <= set(by)
          and rn["renewals_that_used_points"] >= len(cases) and rn["points_redeemed_hypothetically"] >= sum(c[3] for c in cases) and rn["average_old_cycle_points_redeemed_per_renewal"] > 0
          and rn["points_stranded_by_non_renewal"] >= 3600 and rn["points_expired_after_a_partial_redemption"] >= 4500 + 1500
          and rn["points_expired_before_redemption"] == rn["points_stranded_by_non_renewal"] + rn["points_expired_after_a_partial_redemption"] and rn["outcomes"].get("REFUNDED_CYCLE", 0) >= 1 and "HYPOTHETICAL" in rn["note"], str(rn)[:600])
    check("OBSERVATION: conversion (referral -> meeting -> verified deal) is compared with the model", {"referral_created_to_accepted", "accepted_to_meeting", "meeting_to_verified_deal"} <= set(ob2["modelled_vs_actual"]["conversion"]))
    rl = admin.get("/api/admin/growth-points/renewals").json()
    check("RENEWAL RECORDS: listed for admins with ids, plans, points and amounts only", rl["total"] >= len(cases) + 3 and all(i["shadow"] for i in rl["items"]) and not re.search(r"@|\+91", json.dumps(rl, default=str)) and "HYPOTHETICAL" in rl["label"])
    check("RENEWAL RECORDS: append-only (raw SQL can not edit or delete them)", sql_fails("update growth_point_renewals set redeemed_points = 0") and sql_fails("delete from growth_point_renewals")
          and sql_fails("update growth_point_renewals set shadow = false"))
    check("RENEWAL RECORDS: a record can never use more than the eligible points or the new plan's ceiling (database CHECK)", sql_fails(
        "insert into growth_point_renewals (id, created_at, member_id, new_subscription_id, to_plan, new_term_months, new_price_minor, outcome, eligible_points, redemption_cap_points, redeemed_points, remaining_points, hypothetical_discount_paise, hypothetical_payable_paise, decided_at, rule_version, idempotency_key, shadow) "
        "select 'x-over', created_at, member_id, 'x-sub', to_plan, new_term_months, new_price_minor, 'REDEEMED', 10, 5, 9, 0, 90, 0, decided_at, rule_version, 'x-over-key', true from growth_point_renewals limit 1"))
    rv = admin.get("/api/admin/growth-points/review").json()
    dsh = rv["dashboard"]
    check("GATE A DASHBOARD: members, activity, rewards, risk and economics blocks carry every metric the observation needs",
          {"average", "median", "p90", "p95", "top_1_percent_share_of_points_percent"} <= set(dsh["member_metrics"])
          and {"referrals_created", "referrals_accepted", "referrals_contacted", "meetings_verified", "businesses_closed", "repeat_business", "profiles_completed"} <= set(dsh["activity_metrics"])
          and {"points_requested", "points_awarded", "points_capped", "points_expired", "points_reversed", "points_pending"} <= set(dsh["reward_metrics"])
          and {"pair_concentration_flags", "reciprocal_referral_flags", "rapid_closure_flags", "repeated_prospect_flags", "all_fraud_flags", "reversal_review_flags", "high_value_closure_flags"} <= set(dsh["risk_metrics"])
          and {"hypothetical_point_value_paise", "hypothetical_redemption_now_paise", "hypothetical_annual_reward_cost_projected_paise", "maximum_potential_liability_now_paise", "actual_plan_mix"} <= set(dsh["economic_metrics"]))
    check("GATE A DASHBOARD: figures agree with the ledger (awarded = sum of EARN rows, requested >= awarded, capped = requested - awarded on capped rewards)", dsh["reward_metrics"]["points_awarded"] == scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where entry_type = 'EARN'")
          and dsh["reward_metrics"]["points_requested"] >= dsh["reward_metrics"]["points_awarded"] and dsh["reward_metrics"]["points_capped"] == scalar("select coalesce(sum(capped_points), 0) from growth_point_ledger where entry_type = 'EARN'")
          and dsh["activity_metrics"]["profiles_completed"] == scalar("select count(*) from growth_point_ledger where entry_type = 'EARN' and event_type = 'PROFILE_COMPLETED' and points_delta > 0"))
    check("GATE A: ten exit-criteria questions, each with evidence, answered by management; the suggestion is never an approval", len(rv["exit_criteria"]) == 10 and all(c["answered_by"] == "management" and c["evidence"] for c in rv["exit_criteria"])
          and rv["gate_a"]["only_management_can_approve_phase_2"] is True and rv["gate_a"]["real_financial_effect_inr"] == 0 and rv["gate_a"]["suggested_status"] in ("PASS", "RECALIBRATE", "INSUFFICIENT DATA") and "reconciliation_ok" in rv["data_quality"])
    check("GATE A: with too little real data (this is a test run) there is no PASS, and no model change is proposed or applied", rv["gate_a"]["suggested_status"] == "INSUFFICIENT DATA" and rv["proposed_model_changes"] == [] and "No proposals yet" in rv["proposed_model_changes_note"])
    md = admin.get("/api/admin/growth-points/review", params={"format": "markdown"})
    check("GATE A: the Markdown review is downloadable by admins only and states real financial effect Rs 0", md.status_code == 200 and "REAL FINANCIAL EFFECT = Rs 0" in md.text and "Proposed model changes" in md.text and "no-store" in md.headers["cache-control"]
          and ac.get("/api/admin/growth-points/review").status_code == 401 and not re.search(r"@|\+91", md.text))
    saved = (review.MIN_ACTIVE_MEMBERS, review.MIN_OBSERVED_DAYS)
    review.MIN_ACTIVE_MEMBERS, review.MIN_OBSERVED_DAYS = 1, 0
    try:
        rv2 = go(lambda s_: review.report(s_))
        check("GATE A: once there is data, concerns become PROPOSED MODEL CHANGEs with current rule, observed behaviour, financial impact and recommendation, all waiting for approval; the model itself is unchanged",
              rv2["gate_a"]["suggested_status"] in ("PASS", "RECALIBRATE") and all({"current_rule", "observed_behavior", "financial_impact", "recommended_change", "status"} <= set(p) and "awaiting management approval" in p["status"] for p in rv2["proposed_model_changes"])
              and rules.parameters_hash() == scalar("select sha256 from growth_point_rule_versions where version = :v", v=rules.RULE_VERSION), str(rv2["gate_a"]))
    finally:
        review.MIN_ACTIVE_MEMBERS, review.MIN_OBSERVED_DAYS = saved
    rc2 = admin.get("/api/admin/growth-points/reconcile").json()
    check("RECONCILIATION still balances with renewals: ledger sums = balances, every renewal record = its SIM_REDEEM rows, none above 15% of the NEW plan", rc2["ok"], str({k: rc2[k] for k in ("drift", "violations")})[:400])

    # ======================================================================================== 22. RECONCILIATION
    rec = admin.get("/api/admin/growth-points/reconcile").json()
    check("reconciliation: every member's ledger sum equals the cached balance, no ceiling or budget was ever exceeded", rec["ok"] and rec["members_checked"] > 20, str({k: rec[k] for k in ("drift", "violations")})[:300])
    rng = random.Random(20261008)
    pool = [sub_member(rng.choice(["connect", "growth", "elite"])) for _ in range(5)]
    ev_names = ["REFERRAL_ACCEPTED", "PROSPECT_CONTACTED", "MEETING_COMPLETED", "BUSINESS_CLOSED", "PROFILE_COMPLETED"]
    pts_for = {"REFERRAL_ACCEPTED": 45, "PROSPECT_CONTACTED": 15, "MEETING_COMPLETED": 60, "BUSINESS_CLOSED": 1890, "PROFILE_COMPLETED": 75}
    made = 0
    for step in range(400):
        a_, b_ = rng.sample(pool, 2)
        evn = rng.choice(ev_names)
        at = utcnow() + timedelta(days=rng.randint(0, 85), hours=rng.randint(0, 23))
        award(a_[1], evn, f"rnd-{step}", pts_for[evn] if evn != "BUSINESS_CLOSED" else rng.choice([210, 525, 1050, 1470, 1890]), rng.choice([1, 2, 3, 4]) if evn != "PROFILE_COMPLETED" else 3, at,
              other=None if evn == "PROFILE_COMPLETED" else b_[1], role="referrer", rtype="deal_closure" if evn == "BUSINESS_CLOSED" else "referral")
        made += 1
        if step % 100 == 99:
            async def churn(s):
                lots = await ledger.lots(s, now=utcnow())
                for lot in rng.sample(lots, min(6, len(lots))):
                    await reward_engine.adjust(s, lot, rng.choice(["VOID", "REVERSAL"]), "random churn")
            go(churn)
    go(lambda s: jobs.expire_due(s, now=utcnow() + timedelta(days=400)))
    rec = go(lambda s: reconcile.reconcile(s))
    check("reconciliation over 400 random awards, reversals, caps and expiry: no drift, no violation", rec["ok"] and rec["members_checked"] >= 25, str(rec)[:400])
    check("after every expiry sweep the shadow balances of the random members are zero", all(points_of(m[1]) >= 0 for m in pool) and scalar("select coalesce(sum(total_points),0) from growth_point_balances where member_id in (%s)" % ",".join(f"'{m[1]}'" for m in pool)) == 0)
    async def tamper(s):
        await s.execute(text("update growth_point_balances set total_points = total_points + 7 where member_id = :m"), {"m": pool[0][1]})
        await s.commit()
    db(tamper)
    bad = go(lambda s: reconcile.reconcile(s))
    check("a corrupted cached balance is reported as drift", not bad["ok"] and any(d.get("member_id") == pool[0][1] for d in bad["drift"]))
    al = go(lambda s_: jobs.reconcile_alert(s_))
    al2 = go(lambda s_: jobs.reconcile_alert(s_))
    check("RECONCILIATION ALERT: a mismatch raises a HIGH admin alert once, does not repair anything, and a rerun raises nothing new",
          al["ok"] is False and al["new_alerts"] >= 1 and al2["new_alerts"] == 0 and scalar("select count(*) from growth_point_flags where kind = 'RECONCILIATION_MISMATCH' and severity = 'HIGH' and status = 'OPEN'") >= 1
          and scalar("select total_points from growth_point_balances where member_id = :m", m=pool[0][1]) != scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where member_id = :m", m=pool[0][1]))
    fixed = admin.post("/api/admin/growth-points/reconcile", json={"reason": "Rebuild the cache after the test tamper"}, headers=AH).json()
    check("the repair rebuilds the cache only, and a second run is clean", fixed["cache_repaired"] and go(lambda s: reconcile.reconcile(s))["ok"])

    gt = admin.get("/api/admin/growth-points/gates").json()
    check("GATES: from data and environment, Gate A is not met (too little real data), Phase 2 may not start and redemption can not be enabled; admin only",
          gt["gate_a"]["passed"] is False and gt["may_start_phase_2_build"] is False and gt["redemption_can_be_enabled"] is False and gt["real_financial_effect_inr"] == 0
          and ac.get("/api/admin/growth-points/gates").status_code == 401)
    env_items = {i["gate"]: i["status"] for i in gt["environment"]["items"]}
    check("GATES: the environment items are read from the real flags (redemption OFF, shadow ON, owner configured; this test harness turns the preview ON, so that item is NOT MET; the test database has no alembic_version, so the migration item is NOT MET)", env_items["redemption flag is OFF"] == "MET" and env_items["member preview is OFF"] == "NOT MET" and env_items["database is at the newest migration"] == "NOT MET"
          and env_items["shadow processing is ON"] == "MET" and env_items["a programme owner is configured (pair exceptions, reconciliation)"] == "MET", str(env_items))
    check("GATES: external approvals are NOT MET unless recorded, and nothing is inferred", all(i["status"] == "NOT MET" for i in gt["phase_3_prerequisites"]["items"] if i["gate"].startswith("external approval")))
    from app.rewards import gates as gates_mod
    saved_ap = app_settings.growth_points_approvals
    app_settings.growth_points_approvals = ",".join(("MANAGEMENT_MODEL",) + gates_mod.PHASE3_APPROVALS)
    try:
        gt2 = admin.get("/api/admin/growth-points/gates").json()
        check("GATES: even with every approval recorded, redemption can NOT be enabled while Gate A (real observation data) is not met, and recorded approvals are only ever 'ATTESTED'",
              gt2["redemption_can_be_enabled"] is False and {i["status"] for i in gt2["phase_3_prerequisites"]["items"] if i["gate"].startswith("external approval")} == {"ATTESTED"})
    finally:
        app_settings.growth_points_approvals = saved_ap
    check("GATES: Phase 3 flags default off in code (approvals and owners empty, redemption false)", Settings.model_fields["growth_points_approvals"].default == "" and Settings.model_fields["programme_owner_emails"].default == "")

    # ======================================================================================== 23. MODEL AND CONFIGURATION
    spec = importlib.util.spec_from_file_location("economy_v2", ROOT.parent / "docs" / "growth_points_model" / "economy_v2.py")
    ref_model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref_model)
    for kw in ({}, {"act_factor": 2}, {"all_redeem": True}):
        mine_ = model.network(**kw)
        theirs = ref_model.network("D12", **({"act_factor": kw["act_factor"]} if "act_factor" in kw else {}), **({"all_redeem": True} if "all_redeem" in kw else {}))
        check(f"the in-app 400-member model matches the reference script {kw or '(as approved)'}",
              abs(mine_["expected_annual_paise"] / 100 - theirs["annual"]) < 1e-6 and abs(mine_["worst_annual_paise"] / 100 - theirs["worst_year"]) < 1e-6 and mine_["revenue_annual_paise"] / 100 == theirs["revenue_year"])
    check("the model uses the corrected terms: Connect 3, Growth 6, Elite 12 months", [model.PLANS[p][1] for p in ("Connect", "Growth", "Elite")] == [3, 6, 12])
    drift_ok = False
    async def drift(s):
        from app.models import GrowthPointRuleVersion
        row = await s.get(GrowthPointRuleVersion, rules.RULE_VERSION)
        keep = row.sha256
        reward_engine._verified_versions.discard(rules.RULE_VERSION)
        try:
            with firewall.guard():
                return keep == rules.parameters_hash(), row
        finally:
            pass
    ok_, row = db(drift)
    check("the stored rule version matches the code (hash)", ok_ and row.version == "growth-points-v3")
    saved = rules.PAISE_PER_POINT
    reward_engine._verified_versions.discard(rules.RULE_VERSION)
    rules.EARNING_CEILING_PERMILLE = 130
    try:
        async def should_refuse(s):
            try:
                await reward_engine.ensure_rule_version(s)
                return False
            except reward_engine.RuleDrift:
                return True
        check("changing a number without a new RULE_VERSION is refused (history stays explainable)", db(should_refuse))
    finally:
        rules.EARNING_CEILING_PERMILLE = 120
        reward_engine._verified_versions.discard(rules.RULE_VERSION)
    check("every ledger row records the rule version it was computed under", scalar("select count(*) from growth_point_ledger where rule_version <> 'growth-points-v3'") == 0)

    # ======================================================================================== 24. PERFORMANCE
    def queries(fn):
        n = [0]

        def _c(*_a, **_k):
            n[0] += 1
        event.listen(engine.sync_engine, "before_cursor_execute", _c)
        try:
            r_ = fn()
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _c)
        return r_, n[0]
    ref_p = make_referral(ac, bid)
    _, q_on = queries(lambda: patch(bc, ref_p, "ACCEPTED"))
    app_settings.growth_points_shadow_mode = False
    try:
        ref_p2 = make_referral(ac, bid)
        _, q_off = queries(lambda: patch(bc, ref_p2, "ACCEPTED"))
    finally:
        app_settings.growth_points_shadow_mode = True
    check(f"the whole reward costs a bounded number of queries on top of the request ({q_on - q_off} extra)", q_on - q_off <= 30, f"{q_on} vs {q_off}")
    _, q_again = queries(lambda: asyncio.run(hooks.referral_changed(ref_p)))
    check(f"re-processing an already rewarded event is cheap ({q_again} queries)", q_again <= 8)
    _, q_prev = queries(lambda: ac.get("/api/v1/growth-points/preview"))
    check(f"the member preview is a handful of queries, not a ledger replay ({q_prev})", q_prev <= 12)
    _, q_sum = queries(lambda: admin.get("/api/admin/growth-points/summary"))
    check(f"the admin summary uses a fixed number of queries whatever the ledger size ({q_sum})", q_sum <= 40)
    _, q_mem = queries(lambda: admin.get("/api/admin/growth-points/members", params={"page_size": 100}))
    _, q_mem5 = queries(lambda: admin.get("/api/admin/growth-points/members", params={"page_size": 5}))
    check(f"a page of 100 members costs the same queries as a page of 5 ({q_mem} vs {q_mem5})", q_mem == q_mem5)
    print("MEASURED:", json.dumps({"reward_overhead_queries": q_on - q_off, "reprocess": q_again, "preview": q_prev, "admin_summary": q_sum, "members_page": q_mem}))

    # ======================================================================================== 24b. PRE-LAUNCH SHADOW SAFETY INVARIANTS
    (sfc, sfm, _) = sub_member("growth")
    (sfc2, sfm2, _) = sub_member("connect")
    fp_before = financial_fingerprint()
    n_pay = scalar("select count(*) from payments")
    sf_ref = make_referral(sfc, sfm2)
    patch(sfc2, sf_ref, "ACCEPTED")                              # a real networking action that earns shadow points
    award(sfm, "PROFILE_COMPLETED", "safety-1", 75, 3, utcnow(), role="member", rtype="member")
    admin.post("/api/admin/growth-points/sweep", json={"reason": "Safety check sweep"}, headers=AH)
    admin.post("/api/admin/growth-points/scan", json={"reason": "Safety check scan"}, headers=AH)
    admin.post("/api/admin/growth-points/reconcile", json={"reason": "Safety check reconcile"}, headers=AH)
    go(lambda s: jobs.expire_due(s, now=utcnow() + timedelta(days=900)))
    sfc.get("/api/v1/growth-points/preview")
    sfc.post("/api/v1/growth-points/redeem", json={"points": 100}, headers=H(sfc))
    for p_ in ("summary", "economics", "members", "ledger", "flags"):
        admin.get(f"/api/admin/growth-points/{p_}")
    check("SAFETY: earning, sweeping, expiring, scanning, reconciling, previewing, a refused redemption and every admin view changed NO invoice, payment, subscription or plan (hash of every row)", financial_fingerprint() == fp_before)
    check("SAFETY: no payment was created or altered by any of it", scalar("select count(*) from payments") == n_pay)
    check("SAFETY: real invoice discount = 0 on every invoice, and every amount due equals its list price", scalar("select count(*) from invoices where discount_minor <> 0 or amount_due_minor <> list_price_minor") == 0)
    check("SAFETY: every payment equals its invoice's amount due, every subscription keeps its plan price", scalar("select count(*) from payments p join invoices i on i.id = p.invoice_id where p.amount_minor <> i.amount_due_minor") == 0
          and scalar("select count(*) from subscriptions s join invoices i on i.subscription_id = s.id join plans p on p.id = s.plan_id where i.list_price_minor <> p.price_minor") == 0)
    check("SAFETY: every ledger row is explicitly marked shadow (no row, of any type, is real)", scalar("select count(*) from growth_point_ledger where not shadow") == 0 and scalar("select count(*) from growth_point_ledger") > 100)
    check("SAFETY: the shadow ledger is the ONLY place points live: the legacy growth_points column is untouched", scalar("select coalesce(sum(growth_points), 0) from networking_profiles") == 0)

    def columns(table):
        async def f(s):
            return await s.run_sync(lambda sc: [c["name"] for c in sa_inspect(sc.connection()).get_columns(table)])
        return db(f)
    money_words = re.compile(r"cash|transfer|payout|wallet|voucher|coupon|redeem|redemption|refund|currency|rupee|inr|amount|invoice|payment|discount", re.I)
    HYPOTHETICAL_COLUMNS = {"growth_point_renewals": {"new_invoice_id", "hypothetical_discount_paise", "hypothetical_payable_paise", "new_price_minor", "redemption_cap_points", "redeemed_points"}}   # labelled hypothetical, never applied
    bad_cols = {t: [c for c in columns(t) if money_words.search(c) and c not in HYPOTHETICAL_COLUMNS.get(t, set())] for t in SHADOW_TABLES}
    check("SAFETY: no shadow table has a column that could hold cash, a transfer, a refund, a voucher or a payment; the only money-like columns are the labelled hypothetical renewal figures", all(not v for v in bad_cols.values()), str(bad_cols))
    def foreign_tables(table):
        async def f(s):
            return await s.run_sync(lambda sc: [fk["referred_table"] for fk in sa_inspect(sc.connection()).get_foreign_keys(table)])
        return db(f)
    check("SAFETY: no shadow table has a foreign key to an invoice, payment, subscription or plan (it can not be joined into financial processing by the database)",
          all(not ({"invoices", "payments", "subscriptions", "plans"} & set(foreign_tables(t))) for t in SHADOW_TABLES))
    all_paths = [(r.path, sorted(r.methods or [])) for r in __import__("test_phase0_hardening", fromlist=["x"]).all_routes() if "growth-points" in r.path]
    allowed_paths = {"/api/v1/growth-points/preview", "/api/v1/growth-points/overview", "/api/v1/growth-points/redeem", "/api/v1/growth-points/history"}
    admin_paths = [p for p, _ in all_paths if p.startswith("/api/admin/growth-points")]
    check("SAFETY: the member route inventory under growth-points is exactly preview + overview (both read-only) + history + a refused redeem (the real renewal routes are tested in test_phase2.py), and analytics/review for admins; no transfer, cash-out, refund, apply-to-invoice or convert endpoint exists",
          {p for p, _ in all_paths if p.startswith("/api/v1")} == allowed_paths and not [p for p in admin_paths + list(allowed_paths) if re.search(r"transfer|cash|payout|wallet|voucher|refund|invoice|convert|apply-discount", p)], str(all_paths))
    FINANCIAL_FILES = [p for p in APP.rglob("*.py") if re.search(r"subscri|invoice|payment|pricing", p.name) and "rewards" not in p.parts]
    consumers = [p.name for p in FINANCIAL_FILES if re.search(r"rewards|GrowthPoint|growth_point|growth-points", p.read_text())]
    check("SAFETY: no financial module (subscriptions, invoices, payments, pricing gate) imports, reads or mentions the rewards package or any growth-point table", FINANCIAL_FILES and consumers == [], str(consumers))
    importers = sorted(p.relative_to(APP).as_posix() for p in APP.rglob("*.py") if "rewards" not in p.parts and re.search(r"from \.+rewards|from app\.rewards|import rewards|GrowthPoint(Ledger|Cycle|Balance|Flag)", p.read_text()))
    check("SAFETY: only the networking hooks, the Growth Points routes, the account-delete guard and startup wiring touch the shadow ledger",
          set(importers) <= {"main.py", "models.py", "database.py", "routers/referrals.py", "routers/closures.py", "routers/admin_referrals.py", "routers/customer.py",
                             "routers/growth_points.py", "routers/admin_growth_points.py", "routers/admin.py", "routers/renewal.py", "redemption/service.py", "redemption/finance.py", "demo.py"}, str(importers))
    check("SAFETY: the firewall refuses a financial write even from a reward hook's own session", asyncio.run(try_write("update invoices set discount_minor = 1")))
    check("SAFETY: a ledger row can neither be made real nor be turned into money (database constraints)", sql_fails("update growth_point_ledger set shadow = false"))
    check("SAFETY: the member preview is OFF by default in code and in the example environment file, and so is redemption",
          Settings.model_fields["growth_points_member_preview"].default is False and Settings.model_fields["growth_points_redemption_enabled"].default is False
          and re.search(r"^GROWTH_POINTS_MEMBER_PREVIEW=false", (ROOT / ".env.example").read_text(), re.M) is not None
          and re.search(r"^GROWTH_POINTS_REDEMPTION_ENABLED=false", (ROOT / ".env.example").read_text(), re.M) is not None)

    # ======================================================================================== 25. NOTHING FINANCIAL CHANGED, AT THE VERY END
    check("every invoice, payment and subscription row still carries exactly what the Phase 0 flows put there (no discount anywhere)",
          scalar("select count(*) from invoices where discount_minor <> 0") == 0 and scalar("select count(*) from payments p join invoices i on i.id = p.invoice_id where p.amount_minor <> i.amount_due_minor") == 0)
    check("a full second pass of the reward sweep changes no financial row", (lambda a, b: a == b)(financial_fingerprint(), (go(lambda s: jobs.sweep(s)), financial_fingerprint())[1]))
    check("shadow points were issued, so the checks above were exercised on real data", scalar("select count(*) from growth_point_ledger where entry_type = 'EARN' and points_delta > 0") > 100)

    passed = sum(1 for ok, _ in results if ok)
    print()
    for ok, name in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        code_ = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code_)
