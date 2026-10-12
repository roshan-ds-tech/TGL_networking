"""Phase 0 hardening checks, written for the production-readiness pass.

test_phase0.py proves the features work. This file attacks them: concurrency (the
checks that only mean something on PostgreSQL, where SQLite's single writer would
hide a race), money boundaries, evidence abuse, tampering with the audit log through
SQL, forged identifiers, routes that might bypass the two-party workflow, admin routes
without an audit entry, account deletion, database constraints, expiry, the pricing
gate and configuration. It also asserts that nothing about Growth Points exists.

Run:  .venv/bin/python test_phase0_hardening.py
      TEST_DATABASE_URL=postgresql+asyncpg://user@host/db .venv/bin/python test_phase0_hardening.py
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import io
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import test_phase0 as t0  # sets the throwaway environment (SQLite, or TEST_DATABASE_URL) on import
from test_phase0 import (  # noqa: E402
    ADMIN_EMAIL, PASSWORD, PDF, PNG, PNG2, TMP, H, app_settings, check, db, member_client, me, new_client, referral_payload, register_season1,
    results, rows, scalar,
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, text, update  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app import audit as audit_mod  # noqa: E402
from app import ratelimit  # noqa: E402
from app import pricing_gate  # noqa: E402
from app import verification as ver  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Subscription  # noqa: E402

APP_DIR = Path(__file__).resolve().parent / "app"
IS_PG = engine.dialect.name == "postgresql"


def all_routes():
    """Every concrete route of the app, with its full path. FastAPI keeps included routers as wrapper objects,
    so `app.routes` alone would show almost nothing (and a scan over it would pass without checking anything)."""
    def walk(routes):
        for r in routes:
            inner = getattr(r, "original_router", None)
            if inner is not None:
                yield from walk(inner.routes)
            elif getattr(r, "path", None) is not None and getattr(r, "endpoint", None) is not None:
                yield r
    return list(walk(app.routes))


def clone(c: TestClient) -> TestClient:
    n = new_client()
    n.cookies.update(c.cookies)
    return n


def race(*calls):
    """Run the callables at the same moment on separate threads; return their results in order."""
    with ThreadPoolExecutor(len(calls)) as ex:
        futures = [ex.submit(fn) for fn in calls]
        return [f.result() for f in futures]


def sql_fails(sql: str, **params) -> bool:
    """True if the statement is refused by the database (constraint, trigger or privilege)."""
    async def f(s):
        try:
            await s.execute(text(sql), params)
            await s.commit()
            return False
        except (IntegrityError, DBAPIError):
            await s.rollback()
            return True
    return db(f)


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app) as boot:
        return body(boot)


def body(boot: TestClient) -> int:
    uniq = iter(range(1, 10_000))

    def new_member(prefix: str = "m") -> tuple[TestClient, str]:
        c = member_client(f"{prefix}{next(uniq)}@example.com", f"{prefix.upper()} Member {next(uniq)}")
        return c, me(c)

    a, b, c3, outsider = (member_client(f"{n}@example.com", f"{n.upper()} Person") for n in ("ha", "hb", "hc", "ho"))
    for m in (a, b, c3):
        register_season1(m)
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    for reg in admin.get("/api/admin/registrations", params={"page_size": 50}).json()["items"]:
        assert admin.patch(f"/api/admin/registrations/{reg['id']}/verify", json={"verified": True}, headers=AH).status_code == 200
    assert admin.post("/api/admin/events/season-1/complete", headers=AH).status_code == 200
    a_id, b_id, c_id, o_id = me(a), me(b), me(c3), me(outsider)

    def referral(giver=None, receiver_id=None, **over) -> str:
        ratelimit._buckets.clear()  # this file drives far more actions per hour than any real member
        giver, receiver_id = giver or a, receiver_id or b_id
        r = giver.post("/api/v1/referrals", json=referral_payload(receiver_id, **over), headers=H(giver))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def accept(rid: str, c=None) -> None:
        c = c or b
        assert c.patch(f"/api/v1/referrals/{rid}", json={"status": "ACCEPTED"}, headers=H(c)).status_code == 200

    def confirm(c, rid: str):
        ratelimit._buckets.clear()
        return c.post(f"/api/v1/referrals/{rid}/meeting/confirm", headers=H(c))

    def ready(**over) -> str:
        rid = referral(**over)
        accept(rid)
        assert confirm(a, rid).status_code == 200 and confirm(b, rid).status_code == 200
        return rid

    def report(rid: str, value, c=None, **extra):
        ratelimit._buckets.clear()
        c = c or b
        return c.post(f"/api/v1/referrals/{rid}/closure", json={"actual_value": value, **extra}, headers=H(c))

    def confirm_deal(rid: str, minor: int, c=None, **extra):
        c = c or a
        return c.post(f"/api/v1/referrals/{rid}/closure/confirm", json={"expected_value_minor": minor, **extra}, headers=H(c))

    def buy(c, code: str = "connect"):
        ratelimit._buckets.clear()
        return c.post("/api/v1/subscriptions", json={"plan_code": code}, headers=H(c))

    def proof(c, sid: str, data: bytes = PNG):
        ratelimit._buckets.clear()
        return c.post(f"/api/v1/subscriptions/{sid}/payment-proof", files={"proof": ("p.png", io.BytesIO(data), "image/png")}, headers=H(c))

    def verify_payment(sid: str, adm=None):
        adm = adm or admin
        return adm.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "Bank credit seen"}, headers={"X-CSRF-Token": adm.cookies.get("tgl_csrf") or ""})

    def has_access(c) -> bool:
        return c.get("/api/v1/referrals/summary").status_code == 200

    def sub_state(sid: str):
        return (
            scalar("select status from subscriptions where id = :i", i=sid),
            scalar("select status from invoices where subscription_id = :i", i=sid),
            scalar("select p.status from payments p join invoices i on i.id = p.invoice_id where i.subscription_id = :i", i=sid),
        )

    # ======================================================================
    # 1. THE PRICING GATE CANNOT BE BYPASSED BY READING THE FLAG ELSEWHERE
    # ======================================================================
    check("pricing is NOT confirmed by default", pricing_gate.pricing_confirmed() is False and app_settings.subscription_pricing_confirmed is False)
    try:
        pricing_gate.require_pricing_confirmed("redeeming points against an invoice")
        raised = False
    except pricing_gate.PricingNotConfirmed:
        raised = True
    check("the gate refuses while pricing is unconfirmed", raised)
    readers = [p.name for p in APP_DIR.rglob("*.py") if "subscription_pricing_confirmed" in p.read_text() and p.name not in ("config.py", "pricing_gate.py")]
    check("only app/pricing_gate.py reads the setting (config.py defines it)", readers == [], str(readers))
    from pydantic import ValidationError
    from app.config import Settings
    try:
        Settings(subscription_pricing_confirmed="maybe")
        bad_flag_accepted = True
    except ValidationError:
        bad_flag_accepted = False
    check("an unparseable flag stops the app starting instead of reading as true", not bad_flag_accepted)
    check("the flag is not a client-visible setting", "pricing" not in json.dumps(outsider.get("/api/v1/plans").json()).lower())
    nonzero = [p.name for p in APP_DIR.rglob("*.py") if re.search(r"(?<![A-Za-z_])discount_minor\s*=\s*(?!0\b)[\w(\"']", p.read_text()) and p.name not in ("models.py", "schemas_p0.py") and p.parent.name != "redemption"]
    check("no code outside app/redemption assigns a non-zero invoice discount", nonzero == [], str(nonzero))
    check("lifting the flag alone still cannot discount an invoice (the CHECK holds)", sql_fails("update invoices set discount_minor = 5, amount_due_minor = amount_before_discount_minor - 5") or scalar("select count(*) from invoices") == 0)

    # ======================================================================
    # 2. NO LEGACY ROUTE CAN REACH MEETING_DONE / BUSINESS_CLOSED
    # ======================================================================
    targets = {"MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED"}
    writers: list[tuple[str, str, str]] = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(fn):
                val = None
                if isinstance(node, ast.keyword) and node.arg == "status" and isinstance(node.value, ast.Constant):
                    val = node.value.value
                elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and any(isinstance(t, ast.Attribute) and t.attr == "status" for t in node.targets):
                    val = node.value.value
                elif isinstance(node, ast.Tuple) and any(isinstance(e, ast.Attribute) and e.attr == "status" for e in node.elts):
                    val = None
                if val in targets:
                    writers.append((path.name, fn.name, val))
    allowed = {("closures.py", "confirm_meeting", "MEETING_DONE"), ("closures.py", "confirm_closure", "BUSINESS_CLOSED"), ("closures.py", "revert_referral_after_closure_ended", "MEETING_DONE")}
    stray = sorted(set(writers) - allowed)
    check("only the two-party workflow code writes MEETING_DONE / BUSINESS_CLOSED", stray == [], str(stray))
    check("those writers all exist", allowed <= set(writers) | {("closures.py", "revert_referral_after_closure_ended", "MEETING_DONE")}, str(sorted(set(writers))))
    from app.routers import referrals as member_referrals
    reachable = {t for v_ in member_referrals.TRANSITIONS.values() for t in v_}
    check("the member transition table cannot reach MEETING_DONE or BUSINESS_CLOSED", not ({"MEETING_DONE", "BUSINESS_CLOSED"} & reachable), str(reachable))
    from app.routers import admin_referrals
    check("the admin correction list cannot set them either", not (targets & admin_referrals.CORRECTABLE), str(admin_referrals.CORRECTABLE))
    rid = referral()
    accept(rid)
    for who, name in ((a, "referrer"), (b, "recipient")):
        for st in sorted(targets):
            check(f"PATCH cannot set {st} ({name})", who.patch(f"/api/v1/referrals/{rid}", json={"status": st}, headers=H(who)).status_code in (400, 409, 422))
    check("PATCH cannot smuggle stamps (unknown fields are refused outright)", b.patch(f"/api/v1/referrals/{rid}", json={"status": "CONTACTED", "meeting_done_at": "2026-01-01T00:00:00Z", "business_closed_at": "2026-01-01T00:00:00Z"}, headers=H(b)).status_code == 422
          and scalar("select meeting_done_at from business_referrals where id = :r", r=rid) is None and scalar("select business_closed_at from business_referrals where id = :r", r=rid) is None)
    for st in sorted(targets):
        check(f"admin cannot set {st}", admin.post(f"/api/admin/referrals/{rid}/status", json={"status": st, "reason": "Trying to bypass"}, headers=AH).status_code == 409)
    check("the generic referral update accepts no meeting or closure fields at all", a.put(f"/api/v1/referrals/{rid}", json={"status": "MEETING_DONE"}, headers=H(a)).status_code in (404, 405))
    status_routes = sorted({(m, r.path) for r in all_routes() for m in (r.methods or ()) if m in ("PATCH", "PUT", "POST", "DELETE") and "referral" in r.path})
    known_routes = sorted({
        ("PATCH", "/api/v1/referrals/{referral_id}"), ("POST", "/api/v1/referrals"), ("POST", "/api/v1/networking/referral-requests"),
        ("PATCH", "/api/v1/referrals/{referral_id}/closure"), ("POST", "/api/v1/referrals/{referral_id}/closure"),
        ("POST", "/api/v1/referrals/{referral_id}/closure/cancel"), ("POST", "/api/v1/referrals/{referral_id}/closure/confirm"),
        ("POST", "/api/v1/referrals/{referral_id}/closure/dispute"), ("POST", "/api/v1/referrals/{referral_id}/closure/evidence"),
        ("POST", "/api/v1/referrals/{referral_id}/meeting/confirm"), ("POST", "/api/v1/referrals/{referral_id}/meeting/dispute"),
        ("POST", "/api/v1/referrals/{referral_id}/meeting/withdraw"),
        ("POST", "/api/admin/referrals/{referral_id}/closure/evidence/{evidence_id}/reject"), ("POST", "/api/admin/referrals/{referral_id}/closure/evidence/{evidence_id}/verify"),
        ("POST", "/api/admin/referrals/{referral_id}/closure/invalidate"), ("POST", "/api/admin/referrals/{referral_id}/closure/reject"),
        ("POST", "/api/admin/referrals/{referral_id}/closure/resolve-dispute"), ("POST", "/api/admin/referrals/{referral_id}/closure/verify"),
        ("POST", "/api/admin/referrals/{referral_id}/flag"), ("POST", "/api/admin/referrals/{referral_id}/notes"), ("POST", "/api/admin/referrals/{referral_id}/status"),
    })
    check("the set of routes that can change a referral is exactly the reviewed inventory", status_routes == known_routes, str(sorted(set(status_routes) ^ set(known_routes))))

    # ======================================================================
    # 3. MONEY: EXACT PAISE, BOUNDARIES, SERVER-DERIVED BANDS
    # ======================================================================
    cases = [
        (24999, "UNDER_25K", False, False), (25000, "25K_1L", False, False), (99999, "25K_1L", False, False),
        (100000, "1L_5L", True, False), (499999, "1L_5L", True, False), (500000, "5L_10L", True, True),
        (999999, "5L_10L", True, True), (1000000, "10L_PLUS", True, True),
        ("24999.99", "UNDER_25K", False, False), ("99999.99", "25K_1L", False, False),
        ("499999.99", "1L_5L", True, False), ("999999.99", "5L_10L", True, True),
    ]
    for value, band, ev, adm in cases:
        rid = ready()
        r = report(rid, value)
        cj = r.json() if r.status_code == 201 else {}
        expect_minor = int(round(float(value) * 100))
        check(f"₹{value} lands in {band} (evidence {ev}, admin approval {adm}) as exactly {expect_minor} paise",
              r.status_code == 201 and cj.get("value_band") == band and cj.get("evidence_required") is ev and cj.get("admin_approval_required") is adm and cj.get("actual_value_minor") == expect_minor, r.text[:200])
        assert b.post(f"/api/v1/referrals/{rid}/closure/cancel", headers=H(b)).status_code == 200
    check("the band function agrees at every edge (paise)", [ver.value_band(x) for x in (2_499_999, 2_500_000, 9_999_999, 10_000_000, 49_999_999, 50_000_000, 99_999_999, 100_000_000)] == ["UNDER_25K", "25K_1L", "25K_1L", "1L_5L", "1L_5L", "5L_10L", "5L_10L", "10L_PLUS"])
    rid = ready()
    for bad in (0, -1, "0", "abc", "1.005", "12345.678", 0.1, "1e12", 10**12, None, "", "NaN", "Infinity", [1], {"a": 1}, True):
        r = report(rid, bad)
        check(f"an invalid value {bad!r} is refused", r.status_code in (400, 422), f"{r.status_code} {r.text[:120]}")
    check("nothing was stored by the refused values", scalar("select count(*) from deal_closures where referral_id = :r", r=rid) == 0)
    r = report(rid, 5000, value_band="10L_PLUS", verification_level=4, status="VERIFIED", reported_by_user_id=a_id, evidence_required=False,
               admin_approval_required=False, reward_value=1000, points=500, confirmed_by_referrer_at="2026-01-01T00:00:00Z", verified_by_admin_id="x", currency="USD")
    cj = r.json() if r.status_code == 201 else {}
    check("the client cannot supply a band, level, status, reporter, currency or reward", r.status_code == 201 and cj["value_band"] == "UNDER_25K" and cj["verification_level"] == 0 and cj["status"] == "AWAITING_CONFIRMATION" and cj["currency"] == "INR", r.text[:300])
    check("the reporter is the session user, not a forged id", scalar("select reported_by_user_id from deal_closures where referral_id = :r", r=rid) == b_id)
    check("no reward or points columns were stored", scalar("select confirmed_by_referrer_at from deal_closures where referral_id = :r", r=rid) is None)
    check("the referrer cannot report (only the recipient)", report(rid, 100, c=a).status_code == 403 or scalar("select count(*) from deal_closures where referral_id = :r", r=rid) == 1)
    r = confirm_deal(rid, 500000, verification_level=4, status="VERIFIED", actual_value_minor=99_999_999_900)
    check("a confirm cannot set the level, status or value", r.status_code == 200 and r.json()["verification_level"] == 2 and r.json()["actual_value_minor"] == 500000, r.text[:200])
    check("the recipient cannot confirm their own report", report(ready(), 700).status_code == 201)
    rid2 = ready()
    report(rid2, 800)
    check("only the referrer confirms", confirm_deal(rid2, 80000, c=b).status_code == 403 and confirm_deal(rid2, 80000, c=c3).status_code == 404)
    check("a stale confirmation is refused", confirm_deal(rid2, 99999).status_code == 409)
    old_flags = scalar("select evidence_required from deal_closures where referral_id = :r", r=rid)
    app_settings.deal_evidence_threshold_inr = 200_000
    try:
        rid3 = ready()
        r = report(rid3, 150000)
        check("the evidence threshold is configuration, not a constant", r.status_code == 201 and r.json()["evidence_required"] is False and ver.evidence_required(150_000 * 100) is False, r.text[:200])
        check("a change does not rewrite an existing closure", scalar("select evidence_required from deal_closures where referral_id = :r", r=rid) == old_flags)
    finally:
        app_settings.deal_evidence_threshold_inr = 100_000
    check("the thresholds are marked as awaiting management confirmation", app_settings.deal_thresholds_confirmed is False)
    rules = a.get("/api/v1/deal-rules")
    check("the screens read the thresholds from the server", rules.status_code == 200 and rules.json() == {"evidence_from_minor": 10_000_000, "admin_approval_from_minor": 50_000_000}, rules.text[:200])
    check("deal rules need a session and Networking access", new_client().get("/api/v1/deal-rules").status_code == 401 and outsider.get("/api/v1/deal-rules").status_code == 403)
    app_settings.deal_evidence_threshold_inr = 200_000
    try:
        check("a configuration change is reflected immediately", a.get("/api/v1/deal-rules").json()["evidence_from_minor"] == 20_000_000)
    finally:
        app_settings.deal_evidence_threshold_inr = 100_000
    try:
        app_settings.__class__(deal_evidence_threshold_inr=500000, deal_admin_approval_threshold_inr=100000)
        inverted = False
    except ValidationError:
        inverted = True
    check("an approval threshold below the evidence threshold is refused at startup", inverted)

    # ======================================================================
    # 4. SUBSCRIPTION STATES NEVER GRANT UNPAID ACCESS
    # ======================================================================
    u, uid = new_member("s")
    check("a new member has no access", not has_access(u))
    r = buy(u)
    sid = r.json()["id"]
    check("an unpaid invoice grants nothing", not has_access(u) and sub_state(sid) == ("PENDING", "ISSUED", "PENDING"))
    check("the client cannot mark a payment verified (no such member route)", u.post(f"/api/v1/subscriptions/{sid}/payment/verify", headers=H(u)).status_code in (404, 405)
          and u.patch(f"/api/v1/subscriptions/{sid}", json={"status": "ACTIVE"}, headers=H(u)).status_code in (404, 405))
    check("a member cannot reach the admin verify route", u.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "I paid"}, headers=H(u)).status_code == 401)
    check("verifying without a proof is refused", verify_payment(sid).status_code == 409 and not has_access(u))
    check("a proof is accepted", proof(u, sid).status_code == 200 and sub_state(sid) == ("PENDING", "PENDING", "SUBMITTED"))
    check("an unverified manual proof grants nothing", not has_access(u))
    r = admin.post(f"/api/admin/subscriptions/{sid}/payment/reject", json={"reason": "Amount does not match"}, headers=AH)
    check("a rejected payment grants nothing", r.status_code == 200 and not has_access(u) and sub_state(sid) == ("PENDING", "FAILED", "FAILED"))
    check("a verification of a failed payment is refused", verify_payment(sid).status_code == 409 and not has_access(u))
    check("the member can resubmit and an admin verifies", proof(u, sid).status_code == 200 and verify_payment(sid).status_code == 200 and has_access(u) and sub_state(sid) == ("ACTIVE", "PAID", "VERIFIED"))
    check("payment amount equals the invoice amount", scalar("select count(*) from payments p join invoices i on i.id = p.invoice_id where p.amount_minor <> i.amount_due_minor") == 0)
    check("a member who has access cannot buy another", buy(u).status_code == 409)
    check("cancelling an active subscription is refused", u.post(f"/api/v1/subscriptions/{sid}/cancel", headers=H(u)).status_code == 409)
    r = admin.post(f"/api/admin/subscriptions/{sid}/refund", json={"reason": "Refunded to the member"}, headers=AH)
    check("a refund removes access and leaves consistent states", r.status_code == 200 and not has_access(u) and sub_state(sid) == ("CANCELLED", "REFUNDED", "REFUNDED"))
    check("refunding twice is refused", admin.post(f"/api/admin/subscriptions/{sid}/refund", json={"reason": "Again"}, headers=AH).status_code == 409)
    check("a refunded member can buy again", buy(u).status_code == 201)
    sid_c = scalar("select id from subscriptions where user_id = :u and status = 'PENDING'", u=uid)
    check("cancelling an unpaid subscription leaves no access and a cancelled invoice", u.post(f"/api/v1/subscriptions/{sid_c}/cancel", headers=H(u)).status_code == 200 and not has_access(u) and sub_state(sid_c) == ("CANCELLED", "CANCELLED", "FAILED"))
    check("a cancelled subscription cannot be revived by a proof or verification", proof(u, sid_c).status_code == 409 and verify_payment(sid_c).status_code == 409 and not has_access(u))
    # exact forged amounts
    e, eid_ = new_member("f")
    r = e.post("/api/v1/subscriptions", json={"plan_code": "elite", "price_minor": 100, "amount_due_minor": 100, "discount_minor": 999999, "status": "ACTIVE", "currency": "USD", "period_months": 1}, headers=H(e))
    inv = (r.json() or {}).get("invoice", {})
    check("a forged price, discount, status, currency or period is ignored", r.status_code == 201 and inv.get("amount_due_minor") == 1_000_000 and inv.get("discount_minor") == 0 and inv.get("currency") == "INR" and inv.get("period_months") == 12 and r.json()["status"] == "PENDING", r.text[:300])
    check("a unique invoice number and payment reference were issued", scalar("select count(distinct number) from invoices") == scalar("select count(*) from invoices") and scalar("select count(distinct reference) from payments") == scalar("select count(*) from payments"))

    # ======================================================================
    # 5. EXPIRY NEVER GRANTS ACCESS (NO BACKGROUND JOB REQUIRED)
    # ======================================================================
    x, xid = new_member("x")
    sx = buy(x).json()["id"]
    proof(x, sx)
    verify_payment(sx)
    check("an active subscription grants access", has_access(x))
    from datetime import timedelta
    from app.models import utcnow
    past = utcnow() - timedelta(days=1)

    async def lapse(s):
        await s.execute(update(Subscription).where(Subscription.id == sx).values(expires_at=past))
        await s.commit()
    db(lapse)
    check("a lapsed subscription whose stored status is still ACTIVE grants nothing", scalar("select status from subscriptions where id = :i", i=sx) == "ACTIVE" and not has_access(x))
    r = x.post("/api/v1/subscriptions", json={"plan_code": "growth"}, headers=H(x))
    check("a stale ACTIVE row does not stop the member buying again", r.status_code == 201, r.text[:200])
    check("the stale row was flipped to EXPIRED with an audit entry", scalar("select status from subscriptions where id = :i", i=sx) == "EXPIRED" and scalar("select count(*) from audit_log where action = 'subscription.expired' and resource_id = :i", i=sx) == 1)
    check("reading the current subscription also reports the truth", x.get("/api/v1/subscriptions/current").json()["status"] == "PENDING")
    admin_items = admin.get("/api/admin/subscriptions", params={"search": f"x"}).json()["items"]
    check("the admin list reports effective status", all(i["effective_status"] in ("PENDING", "ACTIVE", "EXPIRED", "CANCELLED") for i in admin_items))

    # ======================================================================
    # 6. PAYMENT INSTRUCTIONS: NEVER INVENTED
    # ======================================================================
    pi = u.get("/api/v1/subscriptions/payment-instructions").json()
    check("with nothing configured the app says instructions are pending", pi == {"configured": False, "instructions": None}, str(pi))
    check("payment instructions need a session", new_client().get("/api/v1/subscriptions/payment-instructions").status_code == 401)
    for junk in ("TODO: add bank details", "Account: XXXX XXXX", "Pay to <b>acct</b>", "REPLACE ME", "sample UPI: example@bank", "changeme"):
        app_settings.subscription_payment_instructions = junk
        check(f"placeholder-looking text is treated as not configured ({junk[:18]!r})", u.get("/api/v1/subscriptions/payment-instructions").json()["configured"] is False)
    app_settings.subscription_payment_instructions = "Pay by bank transfer to the account TGL gives you.\nQuote your reference."
    pi = u.get("/api/v1/subscriptions/payment-instructions").json()
    check("configured text is returned as plain text", pi["configured"] is True and "Quote your reference" in pi["instructions"])
    app_settings.subscription_payment_instructions = ""
    check("code contains no bank or UPI details of its own", not [p.name for p in APP_DIR.rglob("*.py") if re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b|@(okhdfc|oksbi|okaxis|ybl|paytm)|\bIFSC\b|account number", p.read_text(), re.I)])

    # ======================================================================
    # 7. CONCURRENCY (the part that is only meaningful on PostgreSQL)
    # ======================================================================
    advanced_once = True
    for _ in range(8):
        rid = referral()
        accept(rid)
        ca, cb = clone(a), clone(b)
        res = race(lambda: ca.post(f"/api/v1/referrals/{rid}/meeting/confirm", headers=H(ca)).status_code, lambda: cb.post(f"/api/v1/referrals/{rid}/meeting/confirm", headers=H(cb)).status_code)
        done = (scalar("select status from business_referrals where id = :r", r=rid) == "MEETING_DONE"
                and scalar("select count(*) from referral_confirmations where referral_id = :r", r=rid) == 2
                and scalar("select count(*) from audit_log where resource_id = :r and action = 'referral.status_changed' and after_json like '%MEETING_DONE%'", r=rid) == 1
                and "ACCEPTED" in (scalar("select before_json from audit_log where resource_id = :r and action = 'referral.status_changed' and after_json like '%MEETING_DONE%'", r=rid) or "")
                and res == [200, 200])
        advanced_once = advanced_once and done
    check("8 simultaneous two-party confirmations each advance the referral exactly once", advanced_once)

    rid = ready()
    report(rid, 777)
    ca1, ca2 = clone(a), clone(a)
    res = sorted(race(lambda: confirm_deal(rid, 77700, c=ca1).status_code, lambda: confirm_deal(rid, 77700, c=ca2).status_code))
    check("a double-clicked deal confirmation confirms once", res == [200, 409] and scalar("select count(*) from audit_log where action = 'closure.confirmed' and resource_id = (select id from deal_closures where referral_id = :r)", r=rid) == 1, str(res))

    consistent = True
    for _ in range(5):
        rid = ready()
        report(rid, 1000)
        cb, ca = clone(b), clone(a)
        race(lambda: cb.patch(f"/api/v1/referrals/{rid}/closure", json={"actual_value": 2000}, headers=H(cb)).status_code,
             lambda: confirm_deal(rid, 100000, c=ca).status_code)
        st, val = rows("select status, actual_value_minor from deal_closures where referral_id = :r", r=rid)[0]
        consistent = consistent and (st == "AWAITING_CONFIRMATION" or val == 100000)
    check("the value the referrer confirmed is never replaced by a concurrent edit", consistent)

    rid = ready()
    cb1, cb2 = clone(b), clone(b)
    res = sorted(race(lambda: report(rid, 4321, c=cb1).status_code, lambda: report(rid, 4321, c=cb2).status_code))
    check("a double-clicked deal report creates one closure", res == [201, 409] and scalar("select count(*) from deal_closures where referral_id = :r", r=rid) == 1, str(res))

    z, zid = new_member("z")
    cz1, cz2 = clone(z), clone(z)
    res = sorted(race(lambda: buy(cz1).status_code, lambda: buy(cz2).status_code))
    check("a double-clicked purchase opens one subscription", res == [201, 409] and scalar("select count(*) from subscriptions where user_id = :u", u=zid) == 1, str(res))

    mixed = []
    for _ in range(6):
        w, wid = new_member("w")
        sw = buy(w).json()["id"]
        proof(w, sw)
        cw, adm2 = clone(w), clone(admin)
        race(lambda: cw.post(f"/api/v1/subscriptions/{sw}/cancel", headers=H(cw)).status_code, lambda: verify_payment(sw, adm2).status_code)
        state = sub_state(sw)
        access = has_access(w)
        ok = (state == ("CANCELLED", "CANCELLED", "FAILED") and not access) or (state == ("ACTIVE", "PAID", "VERIFIED") and access)
        if not ok:
            mixed.append((state, access))
    check("cancel racing an admin verification never leaves a mixed state", mixed == [], str(mixed))

    v1, _ = new_member("v")
    sv = buy(v1).json()["id"]
    proof(v1, sv)
    adm_a, adm_b = clone(admin), clone(admin)
    res = sorted(race(lambda: verify_payment(sv, adm_a).status_code, lambda: verify_payment(sv, adm_b).status_code))
    check("two admins verifying the same payment: exactly one succeeds", res == [200, 409] and scalar("select count(*) from audit_log where action = 'payment.verified' and resource_id = (select id from payments p where p.invoice_id = (select id from invoices where subscription_id = :s))", s=sv) == 1, str(res))

    # ======================================================================
    # 8. EVIDENCE: ABUSE AND PRIVACY
    # ======================================================================
    rid = ready()
    report(rid, 300000)
    confirm_deal(rid, 30_000_000)
    def ev(c, data, name="proof.png", ctype="image/png", kind="INVOICE", rid_=None):
        ratelimit._buckets.clear()
        return c.post(f"/api/v1/referrals/{rid_ or rid}/closure/evidence", data={"evidence_type": kind}, files={"file": (name, io.BytesIO(data), ctype)}, headers=H(c))

    bad_files = {
        "HTML sent as an image": (b"<html><script>alert(1)</script></html>", "x.png", "image/png"),
        "SVG with script": (b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>', "x.svg", "image/svg+xml"),
        "a Windows executable": (b"MZ\x90\x00" + b"\x00" * 60, "setup.png", "image/png"),
        "a PHP script": (b"<?php system($_GET['c']); ?>", "shell.php", "image/png"),
        "a shell script": (b"#!/bin/sh\nrm -rf /\n", "run.pdf", "application/pdf"),
        "a ZIP archive": (b"PK\x03\x04" + b"\x00" * 60, "a.png", "image/png"),
        "an ELF binary": (b"\x7fELF" + b"\x00" * 60, "a.gif", "image/gif"),
        "plain text": (b"hello world, this is not a document", "note.pdf", "application/pdf"),
    }
    for label, (data, name, ctype) in bad_files.items():
        check(f"evidence is refused: {label}", ev(b, data, name, ctype).status_code == 415)
    check("an empty file is refused", ev(b, b"", "e.png").status_code in (400, 415))
    old_max = app_settings.max_upload_bytes
    app_settings.max_upload_bytes = 1024
    try:
        check("an oversize file is refused (413)", ev(b, PNG + b"\x00" * 5000).status_code == 413)
    finally:
        app_settings.max_upload_bytes = old_max
    check("nothing was stored by the refused uploads", scalar("select count(*) from deal_evidence where closure_id = (select id from deal_closures where referral_id = :r)", r=rid) == 0)
    r = ev(b, PNG, name="../../etc/passwd.php", ctype="text/html")
    check("a hostile filename and declared type are ignored", r.status_code == 201, r.text[:200])
    stored = rows("select id, storage_name, mime, sha256, size_bytes from deal_evidence order by uploaded_at desc limit 1")[0]
    check("the stored key is a server-generated name with a sniffed extension", re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|webp|gif|pdf)", stored[1]) is not None and stored[2] == "image/png", str(stored))
    check("the file hash is the SHA-256 of the exact bytes", stored[3] == hashlib.sha256(PNG).hexdigest() and stored[4] == len(PNG))
    ev_id = stored[0]
    f = b.get(f"/api/v1/referrals/{rid}/closure/evidence/{ev_id}/file")
    check("a party receives the exact bytes, as the sniffed type", f.status_code == 200 and f.content == PNG and f.headers["content-type"].startswith("image/png"))
    check("evidence is served nosniff, sandboxed and uncached", f.headers.get("x-content-type-options") == "nosniff" and "sandbox" in f.headers.get("content-security-policy", "") and "no-store" in f.headers.get("cache-control", ""))
    leak = json.dumps([b.get(f"/api/v1/referrals/{rid}").json(), b.get(f"/api/v1/referrals/{rid}/closure").json(), a.get("/api/v1/referrals").json(), admin.get(f"/api/admin/referrals/{rid}").json()])
    check("no API response contains the storage key or the file hash", stored[1] not in leak and stored[3] not in leak and str(Path(TMP)) not in leak)
    for label, client in (("an outsider", c3), ("a non-member", outsider), ("an anonymous visitor", new_client())):
        check(f"{label} cannot download evidence", client.get(f"/api/v1/referrals/{rid}/closure/evidence/{ev_id}/file").status_code in (401, 403, 404))
    check("a member cannot use the admin evidence route", b.get(f"/api/admin/referrals/{rid}/closure/evidence/{ev_id}/file").status_code == 401)
    check("an admin can review it", admin.get(f"/api/admin/referrals/{rid}/closure/evidence/{ev_id}/file").status_code == 200)
    check("a wrong referral id does not unlock the file", admin.get(f"/api/admin/referrals/{ready()}/closure/evidence/{ev_id}/file").status_code == 404)
    for url in (f"/uploads/{stored[1]}", f"/static/{stored[1]}", f"/api/uploads/{stored[1]}", f"/{stored[1]}", f"/api/v1/uploads/{stored[1]}"):
        check(f"the stored file is not publicly reachable at {url.split(stored[1])[0]}…", boot.get(url).status_code in (401, 403, 404, 405) or "image/png" not in boot.get(url).headers.get("content-type", ""))
    check("members have no way to delete or replace evidence", b.delete(f"/api/v1/referrals/{rid}/closure/evidence/{ev_id}", headers=H(b)).status_code in (404, 405)
          and b.put(f"/api/v1/referrals/{rid}/closure/evidence/{ev_id}", headers=H(b)).status_code in (404, 405))
    check("evidence upload and review are audited with the actor", scalar("select count(*) from audit_log where action = 'evidence.uploaded' and resource_id = :e and actor_id = :b", e=ev_id, b=b_id) == 1)
    r = admin.post(f"/api/admin/referrals/{rid}/closure/evidence/{ev_id}/reject", json={"reason": "Document is unreadable"}, headers=AH)
    check("a rejection is audited with its reason", r.status_code == 200 and scalar("select count(*) from audit_log where action = 'evidence.rejected' and resource_id = :e and reason = 'Document is unreadable'", e=ev_id) == 1)
    check("a replacement is a new, separately audited row", ev(b, PNG2).status_code == 201 and scalar("select count(*) from audit_log where action = 'evidence.uploaded'") >= 2)
    other = ready()
    report(other, 300000)
    confirm_deal(other, 30_000_000)
    ev(b, PNG2, rid_=other)
    check("the same file on another closure flags both referrals for review", scalar("select count(*) from business_referrals where id in (:x, :y) and flagged", x=rid, y=other) >= 1 and "same evidence" in (scalar("select flag_reason from business_referrals where id = :r", r=other) or ""))
    check("a PDF is accepted and stored as a PDF", ev(b, PDF, "contract.pdf", "application/pdf", rid_=other).status_code == 201 and scalar("select count(*) from deal_evidence where mime = 'application/pdf'") == 1)
    check("only the known evidence types are accepted", ev(b, PNG, kind="SELFIE", rid_=other).status_code == 422)

    # ======================================================================
    # 9. AUDIT LOG: TAMPERING, ROLLBACK, SECRETS
    # ======================================================================
    check("raw UPDATE of an audit row is refused by the database", sql_fails("update audit_log set reason = 'edited'"))
    check("raw DELETE of an audit row is refused by the database", sql_fails("delete from audit_log"))
    check("raw DELETE with a WHERE clause is refused", sql_fails("delete from audit_log where action = 'evidence.rejected'"))
    if IS_PG:
        check("TRUNCATE of the audit log is refused by the database", sql_fails("truncate table audit_log"))
        check("the audit triggers are enabled", scalar("select count(*) from pg_trigger where tgrelid = 'audit_log'::regclass and not tgisinternal and tgenabled = 'O'") == 2)
        role_ok = False
        try:
            async def mkrole(s):
                await s.execute(text("DROP ROLE IF EXISTS tgl_app_limited"))
                await s.execute(text("CREATE ROLE tgl_app_limited NOLOGIN"))
                await s.execute(text("GRANT SELECT, INSERT ON audit_log TO tgl_app_limited"))
                await s.commit()
            db(mkrole)
            async def limited(s):
                try:
                    await s.execute(text("SET ROLE tgl_app_limited"))
                    await s.execute(text("UPDATE audit_log SET reason = 'x'"))
                    await s.commit()
                    return False
                except DBAPIError:
                    await s.rollback()
                    return True
            role_ok = db(limited)
            async def droprole(s):
                await s.execute(text("RESET ROLE"))
                await s.execute(text("DROP OWNED BY tgl_app_limited"))
                await s.execute(text("DROP ROLE tgl_app_limited"))
                await s.commit()
            db(droprole)
        except Exception as exc:  # pragma: no cover - needs CREATE ROLE rights
            print("  (skipped limited-role check:", str(exc)[:80], ")")
            role_ok = True
        check("a least-privilege database role cannot UPDATE the audit log (privilege layer)", role_ok)

    async def orm_tamper(s):
        row = (await s.execute(text("select id from audit_log limit 1"))).scalar()
        obj = await s.get(AuditLog, row)
        obj.reason = "tampered"
        try:
            await s.commit()
            return False
        except Exception:
            await s.rollback()
            return True
    check("the ORM refuses to edit an audit row", db(orm_tamper))

    before_n = scalar("select count(*) from audit_log")
    async def audit_then_rollback(s):
        audit_mod.record(s, actor=None, action="test.rolled_back", resource_type="test", resource_id="x", after={"n": 1})
        await s.flush()
        await s.rollback()
    db(audit_then_rollback)
    check("a rolled-back transaction leaves no audit record", scalar("select count(*) from audit_log") == before_n and scalar("select count(*) from audit_log where action = 'test.rolled_back'") == 0)
    rid = ready()
    report(rid, 5000)
    n0 = scalar("select count(*) from audit_log where action = 'closure.confirmed'")
    check("a refused change writes no audit entry", confirm_deal(rid, 1).status_code == 409 and scalar("select count(*) from audit_log where action = 'closure.confirmed'") == n0)
    async def with_secrets(s):
        audit_mod.record(s, actor=None, action="test.secrets", resource_type="test", resource_id="x",
                         before={"password": "hunter2-secret", "Authorization": "Bearer abcdef", "nested": {"api_key": "sk-live-123", "ok": "visible"}},
                         after={"session_cookie": "c00kie", "otp": "123456", "csrf": "tok", "long": "y" * 5000}, metadata={"card_number": "4111111111111111"})
        await s.commit()
    db(with_secrets)
    blob = " ".join(x[0] or "" for x in rows("select coalesce(before_json,'') || coalesce(after_json,'') || coalesce(metadata_json,'') from audit_log where action = 'test.secrets'"))
    check("secrets are redacted before they reach the audit log", not any(sec in blob for sec in ("hunter2-secret", "abcdef", "sk-live-123", "c00kie", "123456", "4111111111111111")) and "visible" in blob)
    check("long values are truncated", "y" * 600 not in blob)
    everything = " ".join((x[0] or "") for x in rows("select coalesce(before_json,'') || ' ' || coalesce(after_json,'') || ' ' || coalesce(metadata_json,'') || ' ' || coalesce(reason,'') from audit_log"))
    leaks = [n for n, v_ in (("password", PASSWORD), ("storage key", stored[1]), ("member session", b.cookies.get("tgl_customer_session") or "-no-session-"), ("member csrf token", b.cookies.get("tgl_customer_csrf") or "-no-csrf-"),
                                ("admin session", admin.cookies.get("tgl_session") or "-no-session-")) if v_ in everything]
    check("the session cookies used in this test really exist", all(len(x) > 20 for x in (b.cookies.get("tgl_customer_session") or "", admin.cookies.get("tgl_session") or "")))
    check("no password, session or storage key appears anywhere in the audit log", leaks == [], str(leaks))
    check("every audit row names an actor type", scalar("select count(*) from audit_log where actor_type not in ('USER','ADMIN','SYSTEM')") == 0)
    check("an admin-actor row always has an admin id", scalar("select count(*) from audit_log where actor_type = 'ADMIN' and actor_id is null") == 0)
    check("no route exposes the audit log to members", all(c_.get(p).status_code in (401, 404, 405) for c_ in (a,) for p in ("/api/v1/audit", "/api/v1/audit-log", "/api/v1/audit_log", "/api/audit")))
    check("a member cannot read admin referral timelines", a.get(f"/api/admin/referrals/{rid}").status_code == 401)

    # ======================================================================
    # 10. EVERY ADMIN WRITE IS AUDITED; EVERY PHASE 0 ADMIN ACTION NEEDS A REASON
    # ======================================================================
    unaudited, no_reason = [], []
    admin_writes = 0
    for route in all_routes():
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        if not path.startswith("/api/admin") or not (methods & {"POST", "PUT", "PATCH", "DELETE"}) or path.startswith("/api/admin/auth"):
            continue
        admin_writes += 1
        src = inspect.getsource(route.endpoint)
        if "audit.record(" not in src:
            unaudited.append((sorted(methods)[0], path))
    check(f"every one of the {admin_writes} admin write routes records an audit entry", admin_writes >= 15 and unaudited == [], str(unaudited))
    reason_routes = [
        (r_.path, sorted(r_.methods)[0]) for r_ in all_routes()
        if r_.path.startswith(("/api/admin/referrals", "/api/admin/subscriptions")) and (r_.methods or set()) & {"POST"}
    ]
    for path, method in reason_routes:
        url = re.sub(r"\{[^}]+\}", "x", path)
        status_ = admin.post(url, json={}, headers=AH).status_code
        if status_ != 422:
            no_reason.append((path, status_))
    check(f"all {len(reason_routes)} Phase 0 admin actions refuse a request with no reason", reason_routes and no_reason == [], str(no_reason))
    check("admin actions need the CSRF token", all(admin.post(re.sub(r"\{[^}]+\}", "x", p), json={"reason": "No token sent"}).status_code == 403 for p, _ in reason_routes))
    check("admin actions are refused to members", all(a.post(re.sub(r"\{[^}]+\}", "x", p), json={"reason": "I am a member"}, headers=H(a)).status_code == 401 for p, _ in reason_routes))

    # ======================================================================
    # 11. ACCOUNT DELETION CANNOT DESTROY FINANCIAL OR DEAL RECORDS
    # ======================================================================
    check("an account with a subscription cannot be deleted by an admin", admin.delete(f"/api/admin/customers/{uid}", headers=AH).status_code == 409 and scalar("select count(*) from users where id = :u", u=uid) == 1)
    check("an account with a closed-business record cannot be deleted by an admin", admin.delete(f"/api/admin/customers/{b_id}", headers=AH).status_code == 409 and admin.delete(f"/api/admin/customers/{a_id}", headers=AH).status_code == 409)
    check("the database itself refuses to delete a member who has an invoice", sql_fails("delete from users where id = :u", u=uid))
    check("the database refuses to delete a member who reported a deal", sql_fails("delete from users where id = :u", u=b_id))
    check("the database refuses to delete a referral that has a closed-business record", sql_fails("delete from business_referrals where id = :r", r=rid))
    check("the database refuses to delete a closure that has evidence", sql_fails("delete from deal_closures where id in (select closure_id from deal_evidence)"))
    check("their invoices, payments and subscriptions are untouched", scalar("select count(*) from invoices where user_id = :u", u=uid) >= 1 and scalar("select count(*) from payments where user_id = :u", u=uid) >= 1)
    d, did = new_member("d")
    n_audit = scalar("select count(*) from audit_log where action = 'account.deleted'")
    check("an account with no money or deal records can still be deleted, and it is audited", admin.delete(f"/api/admin/customers/{did}", headers=AH).status_code == 204 and scalar("select count(*) from audit_log where action = 'account.deleted'") == n_audit + 1)
    check("a closure cannot be deleted by deleting its referral through the API (no such route)", a.delete(f"/api/v1/referrals/{rid}", headers=H(a)).status_code in (404, 405))

    # ======================================================================
    # 12. DATABASE CONSTRAINTS (portable to PostgreSQL)
    # ======================================================================
    sid_a = scalar("select id from subscriptions where status = 'ACTIVE' limit 1") or scalar("select id from subscriptions limit 1")
    inv_p = scalar("select id from invoices where status = 'PAID' limit 1") or scalar("select id from invoices limit 1")
    clo = scalar("select id from deal_closures limit 1")
    evd = scalar("select id from deal_evidence limit 1")
    conf = scalar("select id from referral_confirmations limit 1")
    bad = {
        "a subscription status outside the known set": "update subscriptions set status = 'GRANTED'",
        "an ACTIVE subscription with no dates": f"update subscriptions set status = 'ACTIVE', starts_at = null where id = '{sid_a}'",
        "an invoice status outside the known set": "update invoices set status = 'WAIVED'",
        "a PAID invoice whose paid amount differs from the amount due": f"update invoices set status = 'PAID', amount_paid_minor = 1 where id = '{inv_p}'",
        "an invoice paid more than due": f"update invoices set amount_paid_minor = amount_due_minor + 1 where id = '{inv_p}'",
        "a negative invoice amount": f"update invoices set amount_due_minor = -1, amount_before_discount_minor = -1 where id = '{inv_p}'",
        "a payment status outside the known set": "update payments set status = 'MAGIC'",
        "a VERIFIED payment with no verification time": "update payments set status = 'VERIFIED', verified_at = null",
        "a closure status outside the known set": "update deal_closures set status = 'DONE'",
        "a closure band outside the known set": "update deal_closures set value_band = 'HUGE'",
        "a VERIFIED closure below level 2": f"update deal_closures set status = 'VERIFIED', verification_level = 1 where id = '{clo}'",
        "a closure verification level above 4": f"update deal_closures set verification_level = 5 where id = '{clo}'",
        "a zero deal value": f"update deal_closures set actual_value_minor = 0 where id = '{clo}'",
        "an evidence status outside the known set": "update deal_evidence set status = 'OK'",
        "an evidence type outside the known set": "update deal_evidence set evidence_type = 'SELFIE'",
        "a confirmation of an unknown kind": "update referral_confirmations set kind = 'SALE'",
        "a confirmation by an unknown role": "update referral_confirmations set role = 'admin'",
        "a plan with a term other than 3, 6 or 12 months": "update plans set period_months = 4 where code = 'growth'",
        "a plan with an unknown status": "update plans set status = 'DELETED'",
        "an audit entry with an unknown actor type": "insert into audit_log (id, created_at, actor_type, action, resource_type) values ('bad-actor', current_timestamp, 'GHOST', 'x', 'x')",
        "a second live closure for one referral": f"insert into deal_closures (id, referral_id, reported_by_user_id, actual_value_minor, currency, value_band, evidence_required, admin_approval_required, status, verification_level, submitted_at, created_at, updated_at) select 'dup-closure', referral_id, reported_by_user_id, 100, 'INR', 'UNDER_25K', false, false, 'AWAITING_CONFIRMATION', 0, submitted_at, created_at, updated_at from deal_closures where id = '{clo}' and status not in ('REJECTED','CANCELLED','INVALIDATED')",
    }
    for label, sql in bad.items():
        check(f"DB refuses {label}", sql_fails(sql) or (label.startswith("a second live") and scalar("select count(*) from deal_closures where id = 'dup-closure'") == 0))
    check("DB refuses a duplicate confirmation", sql_fails(f"insert into referral_confirmations (id, referral_id, kind, user_id, role, confirmed_at) select 'dup-conf', referral_id, kind, user_id, role, confirmed_at from referral_confirmations where id = '{conf}'"))
    check("DB refuses an orphan payment (foreign key)", sql_fails("insert into payments (id, invoice_id, user_id, method, amount_minor, currency, status, reference, created_at, updated_at) values ('orph', 'nope', 'nope', 'MANUAL_PROOF', 100, 'INR', 'PENDING', 'TGLS-ORPHAN', current_timestamp, current_timestamp)"))
    check("DB refuses deleting a plan that has subscriptions", sql_fails("delete from plans"))
    check("DB refuses deleting a subscription that has invoices", sql_fails("delete from subscriptions"))
    check("DB refuses deleting an invoice that has payments", sql_fails("delete from invoices"))
    check("the state tables still hold their data after all the refused statements", scalar("select count(*) from subscriptions") > 5 and scalar("select count(*) from deal_closures") > 5)

    # ======================================================================
    # 13. IDOR MATRIX: another member's ids, by direct API call
    # ======================================================================
    rid = ready()
    report(rid, 250000)
    confirm_deal(rid, 25_000_000)
    ev(b, PNG2, rid_=rid)
    cl_id = scalar("select id from deal_closures where referral_id = :r", r=rid)
    ev_id = scalar("select id from deal_evidence where closure_id = :c order by uploaded_at limit 1", c=cl_id)
    victim, vid = new_member("victim")
    sv2 = buy(victim).json()["id"]
    proof(victim, sv2)
    attacker = c3
    idor = {
        "read another pair's referral": attacker.get(f"/api/v1/referrals/{rid}"),
        "read their closure": attacker.get(f"/api/v1/referrals/{rid}/closure"),
        "download their evidence": attacker.get(f"/api/v1/referrals/{rid}/closure/evidence/{ev_id}/file"),
        "upload evidence to their closure": ev(attacker, PNG, rid_=rid),
        "confirm their meeting": confirm(attacker, rid),
        "dispute their closure": attacker.post(f"/api/v1/referrals/{rid}/closure/dispute", json={"reason": "I just dislike it"}, headers=H(attacker)),
        "cancel their closure": attacker.post(f"/api/v1/referrals/{rid}/closure/cancel", headers=H(attacker)),
        "edit their closure": attacker.patch(f"/api/v1/referrals/{rid}/closure", json={"actual_value": 1}, headers=H(attacker)),
        "confirm their deal": confirm_deal(rid, 25_000_000, c=attacker),
        "cancel another member's subscription": attacker.post(f"/api/v1/subscriptions/{sv2}/cancel", headers=H(attacker)),
        "upload a proof for another member's invoice": proof(attacker, sv2),
        "withdraw their meeting confirmation": attacker.post(f"/api/v1/referrals/{rid}/meeting/withdraw", headers=H(attacker)),
    }
    for label, resp in idor.items():
        check(f"IDOR: a third member cannot {label}", resp.status_code in (403, 404, 409) and resp.status_code != 200 and resp.status_code != 201, f"{resp.status_code} {resp.text[:100]}")
    check("IDOR: the victim's subscription and closure were not changed", scalar("select status from subscriptions where id = :i", i=sv2) == "PENDING" and scalar("select status from deal_closures where id = :i", i=cl_id) in ("UNDER_REVIEW", "AWAITING_EVIDENCE"))
    check("IDOR: the third member's own lists never contain the pair's records", all(rid not in x.text for x in (attacker.get("/api/v1/referrals"), attacker.get("/api/v1/referrals/summary"), attacker.get("/api/v1/notifications"))))
    check("IDOR: another member's current subscription is never returned", attacker.get("/api/v1/subscriptions/current").json() in (None,) or attacker.get("/api/v1/subscriptions/current").json().get("id") != sv2)
    check("IDOR: an unknown or malformed id is a clean 404, not a 500", all(attacker.get(f"/api/v1/referrals/{x}/closure").status_code in (404, 422) for x in ("0", "../..", "%00", "a" * 300, "' or 1=1 --")))
    check("a forged identity in a request body is ignored", confirm(a, rid).status_code == 200 and scalar("select count(*) from referral_confirmations where referral_id = :r", r=rid) == 2)
    admin_probe = [("get", f"/api/admin/referrals/{rid}"), ("get", "/api/admin/referrals"), ("get", "/api/admin/subscriptions"), ("get", f"/api/admin/subscriptions/{sv2}/proof")]
    check("admin endpoints are closed to every member", all(getattr(attacker, m)(p).status_code == 401 for m, p in admin_probe))
    check("admin endpoints are closed to anonymous visitors", all(getattr(new_client(), m)(p).status_code == 401 for m, p in admin_probe))
    check("a member's session cookie is not valid as an admin session", attacker.get("/api/admin/referrals", headers={"X-CSRF-Token": H(attacker)["X-CSRF-Token"]}).status_code == 401)

    # ======================================================================
    # 14. PERFORMANCE: query counts for the new flows
    # ======================================================================
    def queries(fn):
        n = [0]

        def _count(*_a, **_k):
            n[0] += 1
        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            r_ = fn()
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)
        return r_, n[0]

    pm, _ = new_member("p")
    pr = referral()
    accept(pr)
    pr2 = ready()
    pr3 = ready()
    report(pr3, 4000)
    pr4 = ready()
    report(pr4, 300000)
    confirm_deal(pr4, 30_000_000)
    measured: dict[str, int] = {}
    suite = [
        ("plan list", 4, lambda: pm.get("/api/v1/plans")),
        ("subscription creation (subscription + invoice + payment)", 14, lambda: buy(pm)),
        ("payment-proof upload", 14, lambda: proof(pm, scalar("select id from subscriptions where user_id = :u", u=me(pm)))),
        ("current subscription", 6, lambda: pm.get("/api/v1/subscriptions/current")),
        ("payment instructions", 4, lambda: pm.get("/api/v1/subscriptions/payment-instructions")),
        ("meeting confirmation (first of two)", 14, lambda: confirm(a, pr)),
        ("meeting confirmation (second, advances the referral)", 20, lambda: confirm(b, pr)),
        ("deal report", 20, lambda: report(pr2, 12000)),
        ("deal confirmation", 20, lambda: confirm_deal(pr3, 400000)),
        ("evidence upload", 22, lambda: ev(b, PNG, rid_=pr4)),
        ("member referral detail", 9, lambda: a.get(f"/api/v1/referrals/{pr4}")),
        ("member referral list (20)", 7, lambda: a.get("/api/v1/referrals", params={"limit": 20})),
        ("admin referral list (25)", 5, lambda: admin.get("/api/admin/referrals", params={"page_size": 25})),
        ("admin referral detail", 14, lambda: admin.get(f"/api/admin/referrals/{pr4}")),
        ("admin subscription list", 5, lambda: admin.get("/api/admin/subscriptions")),
    ]
    for label, cap, fn in suite:
        resp, n = queries(fn)
        measured[label] = n
        check(f"perf: {label} uses <= {cap} queries", resp.status_code in (200, 201) and n <= cap, f"{n} queries, HTTP {resp.status_code} {resp.text[:100]}")
    big = admin.get("/api/admin/referrals", params={"page_size": 100}).json()
    check("perf: admin lists are paginated and capped", len(big["items"]) <= 100 and admin.get("/api/admin/referrals", params={"page_size": 101}).status_code == 422)
    check("perf: a page of 100 costs the same queries as a page of 5", queries(lambda: admin.get("/api/admin/referrals", params={"page_size": 100}))[1] == queries(lambda: admin.get("/api/admin/referrals", params={"page_size": 5}))[1])
    print("MEASURED QUERY COUNTS:", json.dumps(measured))

    # ======================================================================
    # 15. GROWTH POINTS: NOTHING FINANCIAL (Phase 1 adds the SHADOW ledger only; see test_phase1.py)
    # ======================================================================
    tables = {x[0] for x in rows("select name from sqlite_master where type = 'table'")} if not IS_PG else {x[0] for x in rows("select tablename from pg_tables where schemaname = 'public'")}
    shadow = {"growth_point_rule_versions", "growth_point_cycles", "growth_point_ledger", "growth_point_balances", "growth_point_flags"}      # Phase 1, shadow mode only
    check("no voucher, coupon, discount or reward table exists (only the growth_point_* shadow and Phase 2 redemption tables)", not [t for t in tables if not t.startswith("growth_point_") and re.search(r"growth|reward|point|redemption|ledger|redeem|voucher|coupon|discount", t)], str(sorted(tables)))
    check("no member has any legacy Growth Points", scalar("select coalesce(sum(growth_points), 0) from networking_profiles") == 0)
    check("no invoice carries a discount", scalar("select count(*) from invoices where discount_minor <> 0") == 0)
    code = " ".join(p.read_text() for p in APP_DIR.rglob("*.py"))
    outside = " ".join(p.read_text() for p in APP_DIR.rglob("*.py") if "rewards" not in p.parts and "redemption" not in p.parts and not p.name.endswith("growth_points.py"))
    check("no voucher code exists; reward code lives only in app/rewards (shadow); real redemption code only in app/redemption and its renewal route (disabled and approval-gated)",
          not re.search(r"class\s+(?!GrowthPoint)\w*(Reward|Ledger|Redemption|Voucher)\w*|def\s+\w*(award_|redeem|apply_points|add_points|grant_points)\w*", outside) and not re.search(r"class\s+(?!RedemptionDisabled|GrowthPoint)\w*(Redemption|Voucher)\w*", code.replace("class RenewalConfirm", "")))
    check("nothing writes the growth_points column", not re.search(r"growth_points\s*(\+=|-=)|\.growth_points\s*=[^=]|growth_points\s*=\s*(?!p\.growth_points)\d", code.replace("growth_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)", "")))

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
