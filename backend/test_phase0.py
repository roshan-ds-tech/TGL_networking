"""Phase 0 checks: subscriptions/invoices/payments, two-party meeting confirmation,
verified deal closure + evidence, admin referral review, audit log, security.

Run:  .venv/bin/python test_phase0.py

Uses a throwaway SQLite DB and upload dir (or TEST_DATABASE_URL for Postgres), like
test_p0.py. It also asserts that NO Growth Point behaviour exists.
"""
from __future__ import annotations

import asyncio
import io
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

TMP = tempfile.mkdtemp(prefix="tgl-phase0-")
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-definitely-long-enough-123456"
os.environ["DB_NULL_POOL"] = "true"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{TMP}/test.db".replace("\\", "/")
# A developer's local .env may switch Growth Points recording / preview on; the suites assume the shipped defaults unless they set these first.
os.environ.setdefault("GROWTH_POINTS_SHADOW_MODE", "false")
os.environ.setdefault("GROWTH_POINTS_MEMBER_PREVIEW", "false")
os.environ["UPLOAD_DIR"] = f"{TMP}/uploads"
os.environ["ADMIN_DIST_DIR"] = f"{TMP}/nonexistent"
os.environ["RESEND_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app import audit as audit_mod  # noqa: E402
from app import verification as ver  # noqa: E402
from app.config import settings as app_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin, AuditLog  # noqa: E402
from app.security import hash_password  # noqa: E402

# Admin routes that predate Phase 0 (registrations, finale, account deletion, business verification) are audited
# but have no reason field in their request; every Phase 0 admin action requires one.
LEGACY_ADMIN_ACTIONS = ("registration.", "business.", "finale.", "account.")
PASSWORD = "CorrectHorse123!"
ADMIN_EMAIL = "admin@tglseason.com"
PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
PNG2 = bytes.fromhex("89504e470d0a1a0a") + b"\x01" * 64
PDF = b"%PDF-1.4\n" + b"x" * 80
results: list[tuple[bool, str]] = []
app_settings.register_max_per_hour = 1000
_phone = itertools.count(1)


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), f"{name}{(' — ' + detail) if detail and not ok else ''}"))


def csrf(c: TestClient) -> str:
    return c.cookies.get("tgl_customer_csrf") or ""


def H(c: TestClient) -> dict:
    return {"X-CSRF-Token": csrf(c)}


def new_client() -> TestClient:
    return TestClient(app)


def member_client(email: str, name: str) -> TestClient:
    c = new_client()
    r = c.post("/api/v1/auth/register", json={"full_name": name, "phone": "9876543210", "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    r = c.post("/api/v1/auth/verify-email", data={"token": r.json()["dev_verification_token"]}, headers=H(c))
    assert r.status_code == 200, r.text
    assert c.put("/api/v1/profile/personal", json={"full_name": name, "phone": "9876543210", "city": "Bengaluru", "role": "Founder", "short_bio": "I build my business every day."}, headers=H(c)).status_code == 200
    assert c.put("/api/v1/business", json={"business_name": f"{name} Co", "category": "01", "description": "We make useful things for people.", "city": "Bengaluru", "employee_band": "1-3", "business_age": "lt6", "business_stage": "Early"}, headers=H(c)).status_code == 200
    return c


def register_season1(c: TestClient) -> None:
    r = c.post("/api/registrations", data={"name": "x", "business": "x", "email": "x@example.com", "phone": "9876543210", "category": "01", "employees": "1-3", "age": "lt6", "agree": "true", "mediaConsent": "true"}, files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 201, r.text


def me(c: TestClient) -> str:
    return c.get("/api/v1/auth/me").json()["id"]


def referral_payload(receiver_id: str, **over) -> dict:
    p = {
        "receiver_user_id": receiver_id, "prospect_name": "Priya Sharma", "prospect_phone": f"98765{next(_phone):05d}",
        "relationship": "BUSINESS_CONTACT", "opportunity_description": "Priya needs a responsive website with online booking before opening",
        "urgency": "HOT", "intro_method": "EMAIL", "contact_permission": "EXPECTING", "consent_confirmed": True, "value_range": "25K_1L",
    }
    p.update(over)
    return p


def db(fn):
    """Run an async DB helper from sync test code."""
    async def run():
        async with SessionLocal() as s:
            return await fn(s)
    return asyncio.run(run())


def scalar(sql: str, **params):
    return db(lambda s: s.scalar(text(sql), params))


def rows(sql: str, **params):
    async def f(s):
        return (await s.execute(text(sql), params)).all()
    return db(f)


async def seed() -> None:
    async with engine.begin() as c:
        if c.dialect.name == "postgresql":
            await c.exec_driver_sql("DROP SCHEMA public CASCADE")
            await c.exec_driver_sql("CREATE SCHEMA public")
        await c.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        s.add(Admin(email=ADMIN_EMAIL, password_hash=hash_password(PASSWORD)))
        await s.commit()
    await engine.dispose()


def main() -> int:
    asyncio.run(seed())
    with TestClient(app) as boot:  # runs the lifespan: triggers + default plans
        return body(boot)


def body(boot: TestClient) -> int:
    a, b, c3, outsider, sub2, admin = member_client("a@example.com", "Alpha Referrer"), member_client("b@example.com", "Beta Recipient"), member_client("c@example.com", "Gamma Third"), member_client("outsider@example.com", "Omega Outsider"), member_client("sub2@example.com", "Sigma Subscriber"), new_client()
    for m in (a, b, c3):
        register_season1(m)
    r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    acsrf = admin.cookies.get("tgl_csrf") or ""
    AH = {"X-CSRF-Token": acsrf}
    regs = admin.get("/api/admin/registrations", params={"page_size": 50}).json()["items"]
    for reg in regs:
        assert admin.patch(f"/api/admin/registrations/{reg['id']}/verify", json={"verified": True}, headers=AH).status_code == 200
    assert admin.post("/api/admin/events/season-1/complete", headers=AH).status_code == 200
    a_id, b_id, c_id, o_id, s2_id = me(a), me(b), me(c3), me(outsider), me(sub2)
    admin_id = scalar("select id from admins where email = :e", e=ADMIN_EMAIL)

    # =========================== SUBSCRIPTIONS ===========================
    check("pricing confirmation gate exists and is OFF", app_settings.subscription_pricing_confirmed is False)
    r = new_client().get("/api/v1/plans")
    check("plans require a session", r.status_code == 401, str(r.status_code))
    r = outsider.get("/api/v1/plans")
    plans = r.json() if r.status_code == 200 else []
    check("three plans are stored", [p["code"] for p in plans] == ["connect", "growth", "elite"], str(plans)[:200])
    check("plan prices are exact paise", [p["price_minor"] for p in plans] == [300000, 500000, 1000000], str(plans)[:200])
    check("each plan's term is explicit: Connect 3, Growth 6, Elite 12 months", [p["period_months"] for p in plans] == [3, 6, 12] and all(p["currency"] == "INR" for p in plans), str(plans)[:200])
    check("plans expose no internal ids or status", all(set(p) == {"code", "name", "price_minor", "currency", "period_months", "season_slug"} for p in plans))

    check("buying needs a session", new_client().post("/api/v1/subscriptions", json={"plan_code": "connect"}).status_code == 401)
    check("buying needs the CSRF header", outsider.post("/api/v1/subscriptions", json={"plan_code": "connect"}).status_code == 403)
    check("unknown plan is refused", outsider.post("/api/v1/subscriptions", json={"plan_code": "platinum"}, headers=H(outsider)).status_code == 404)
    check("malformed plan code is refused", outsider.post("/api/v1/subscriptions", json={"plan_code": "../x"}, headers=H(outsider)).status_code == 422)
    check("a member who already has access cannot buy", a.post("/api/v1/subscriptions", json={"plan_code": "connect"}, headers=H(a)).status_code == 409)

    r = outsider.post("/api/v1/subscriptions", json={"plan_code": "connect", "price_minor": 1, "amount_due_minor": 1, "discount_minor": 299999}, headers=H(outsider))
    sub = r.json() if r.status_code == 201 else {}
    check("subscription is created", r.status_code == 201, r.text[:200])
    check("the server sets the price, not the client", (sub.get("invoice") or {}).get("amount_due_minor") == 300000 and (sub.get("invoice") or {}).get("list_price_minor") == 300000, str(sub.get("invoice")))
    check("a forged discount is ignored (no discount is applied)", (sub.get("invoice") or {}).get("discount_minor") == 0 and (sub.get("invoice") or {}).get("amount_before_discount_minor") == 300000)
    check("new subscription is PENDING with an ISSUED invoice and PENDING payment", sub.get("status") == "PENDING" and sub["invoice"]["status"] == "ISSUED" and sub["payment"]["status"] == "PENDING", str(sub)[:300])
    check("invoice snapshots the plan", sub["invoice"]["plan_name"] == "Connect" and sub["invoice"]["period_months"] == 3 and sub["invoice"]["number"].startswith("INV-"))
    check("payment reference is generated", bool(sub["payment"]["reference"]) and sub["payment"]["has_proof"] is False)
    sub_id = sub["id"]
    check("a second live subscription is refused", outsider.post("/api/v1/subscriptions", json={"plan_code": "elite"}, headers=H(outsider)).status_code == 409)
    check("no access before payment is verified", outsider.get("/api/v1/networking/members").status_code == 403)
    check("current subscription is readable by its owner", (outsider.get("/api/v1/subscriptions/current").json() or {}).get("id") == sub_id)
    check("another member cannot read it", (a.get("/api/v1/subscriptions/current").json() or "none") in (None, "none") or (a.get("/api/v1/subscriptions/current").json() or {}).get("id") != sub_id)

    png = lambda: ("proof.png", io.BytesIO(PNG), "image/png")  # noqa: E731
    check("a spoofed payment proof is blocked", outsider.post(f"/api/v1/subscriptions/{sub_id}/payment-proof", files={"proof": ("x.png", io.BytesIO(b"<?php ?>"), "image/png")}, headers=H(outsider)).status_code == 415)
    check("another member cannot submit proof for it (IDOR)", a.post(f"/api/v1/subscriptions/{sub_id}/payment-proof", files={"proof": png()}, headers=H(a)).status_code == 404)
    check("another member cannot cancel it (IDOR)", a.post(f"/api/v1/subscriptions/{sub_id}/cancel", headers=H(a)).status_code == 404)
    check("proof upload needs CSRF", outsider.post(f"/api/v1/subscriptions/{sub_id}/payment-proof", files={"proof": png()}).status_code == 403)
    r = outsider.post(f"/api/v1/subscriptions/{sub_id}/payment-proof", files={"proof": png()}, headers=H(outsider))
    check("proof submission moves payment to SUBMITTED and invoice to PENDING", r.status_code == 200 and r.json()["payment"]["status"] == "SUBMITTED" and r.json()["invoice"]["status"] == "PENDING", r.text[:200])
    check("member response never exposes the stored proof name", "proof_filename" not in r.text and ".png" not in r.text)

    check("admin list rejects a customer session", outsider.get("/api/admin/subscriptions").status_code == 401)
    lst = admin.get("/api/admin/subscriptions", params={"payment_status": "SUBMITTED"}).json()
    check("admin sees the submitted payment", lst["total"] == 1 and lst["items"][0]["id"] == sub_id and lst["items"][0]["has_proof"], str(lst)[:300])
    check("admin list paginates and caps page size", admin.get("/api/admin/subscriptions", params={"page_size": 1000}).status_code == 422)
    check("admin can read the proof", admin.get(f"/api/admin/subscriptions/{sub_id}/proof").status_code == 200)
    check("a customer cannot read the proof", outsider.get(f"/api/admin/subscriptions/{sub_id}/proof").status_code == 401)
    check("verify needs CSRF", admin.post(f"/api/admin/subscriptions/{sub_id}/payment/verify").status_code == 403)
    check("a customer cannot verify a payment", outsider.post(f"/api/admin/subscriptions/{sub_id}/payment/verify", headers=H(outsider)).status_code == 401)
    r = admin.post(f"/api/admin/subscriptions/{sub_id}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
    v = r.json() if r.status_code == 200 else {}
    check("admin verification activates the subscription", r.status_code == 200 and v["status"] == "ACTIVE" and v["payment"]["status"] == "VERIFIED" and v["invoice"]["status"] == "PAID", r.text[:300])
    check("invoice records amount paid and paid_at", v["invoice"]["amount_paid_minor"] == 300000 and v["invoice"]["paid_at"])
    check("the period is exactly 3 calendar months", v["starts_at"] and v["expires_at"] and (int(v["expires_at"][5:7]) - int(v["starts_at"][5:7])) % 12 == 3)
    check("verifying twice is refused", admin.post(f"/api/admin/subscriptions/{sub_id}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH).status_code == 409)
    st = outsider.get("/api/v1/status").json()
    check("an active subscription grants networking access", st["networking_access"] is True and (st["membership"] or {}).get("pathway") == "SUBSCRIPTION" and st["membership"]["status"] == "ACTIVE", str(st.get("membership")))
    check("the subscriber can now read the directory", outsider.get("/api/v1/networking/members").status_code == 200)
    check("and appears in the directory for others", o_id in {m["user_id"] for m in a.get("/api/v1/networking/members").json()})

    # reject then resubmit
    r = sub2.post("/api/v1/subscriptions", json={"plan_code": "elite"}, headers=H(sub2))
    s2 = r.json()
    check("a ₹10,000 plan invoice is 1,000,000 paise", s2["invoice"]["amount_due_minor"] == 1000000)
    check("cannot verify before a proof is submitted", admin.post(f"/api/admin/subscriptions/{s2['id']}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH).status_code == 409)
    sub2.post(f"/api/v1/subscriptions/{s2['id']}/payment-proof", files={"proof": png()}, headers=H(sub2))
    check("rejecting needs a reason", admin.post(f"/api/admin/subscriptions/{s2['id']}/payment/reject", json={}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/subscriptions/{s2['id']}/payment/reject", json={"reason": "Amount does not match"}, headers=AH)
    check("rejection marks payment and invoice FAILED", r.status_code == 200 and r.json()["payment"]["status"] == "FAILED" and r.json()["invoice"]["status"] == "FAILED" and r.json()["status"] == "PENDING", r.text[:200])
    check("the rejection reason reaches the member", sub2.get("/api/v1/subscriptions/current").json()["payment"]["rejection_reason"] == "Amount does not match")
    check("still no access", sub2.get("/api/v1/networking/members").status_code == 403)
    r = sub2.post(f"/api/v1/subscriptions/{s2['id']}/payment-proof", files={"proof": ("again.pdf", io.BytesIO(PDF), "application/pdf")}, headers=H(sub2))
    check("the member can submit a new proof", r.status_code == 200 and r.json()["payment"]["status"] == "SUBMITTED")
    r = admin.post(f"/api/admin/subscriptions/{s2['id']}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
    check("then it verifies", r.status_code == 200 and r.json()["status"] == "ACTIVE")
    check("refund needs a reason", admin.post(f"/api/admin/subscriptions/{s2['id']}/refund", json={}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/subscriptions/{s2['id']}/refund", json={"reason": "Member requested a refund"}, headers=AH)
    check("refund marks everything REFUNDED and ends the subscription", r.status_code == 200 and r.json()["payment"]["status"] == "REFUNDED" and r.json()["invoice"]["status"] == "REFUNDED" and r.json()["status"] == "CANCELLED", r.text[:300])
    check("a refund ends access", sub2.get("/api/v1/networking/members").status_code == 403)
    check("a refunded subscription cannot be refunded again", admin.post(f"/api/admin/subscriptions/{s2['id']}/refund", json={"reason": "twice please"}, headers=AH).status_code == 409)
    r = sub2.post("/api/v1/subscriptions", json={"plan_code": "growth"}, headers=H(sub2))
    check("after a refund the member may buy again", r.status_code == 201)
    s3 = r.json()
    r = sub2.post(f"/api/v1/subscriptions/{s3['id']}/cancel", headers=H(sub2))
    check("the member can cancel an unpaid subscription", r.status_code == 200 and r.json()["status"] == "CANCELLED" and r.json()["invoice"]["status"] == "CANCELLED")
    check("a cancelled subscription cannot receive proof", sub2.post(f"/api/v1/subscriptions/{s3['id']}/payment-proof", files={"proof": png()}, headers=H(sub2)).status_code == 409)

    # database-level integrity
    def bad_insert(sql: str) -> bool:
        async def f(s):
            try:
                await s.execute(text(sql))
                await s.commit()
                return False
            except (IntegrityError, DBAPIError):
                await s.rollback()
                return True
        return db(f)

    inv = scalar("select id from invoices limit 1")
    check("DB: an invoice cannot carry a discount in Phase 0", bad_insert(f"update invoices set discount_minor = 100, amount_due_minor = amount_before_discount_minor - 100 where id = '{inv}'"))
    check("DB: amount due must equal price minus discount", bad_insert(f"update invoices set amount_due_minor = 1 where id = '{inv}'"))
    check("DB: a plan price must be positive", bad_insert("update plans set price_minor = 0 where code = 'connect'"))
    check("DB: a payment amount must be positive", bad_insert("update payments set amount_minor = 0"))
    check("DB: one live subscription per member", bad_insert(f"insert into subscriptions (id, user_id, plan_id, status, created_at, updated_at) select 'dup-live-sub', user_id, plan_id, 'PENDING', created_at, updated_at from subscriptions where user_id = '{o_id}' and status = 'ACTIVE'"))

    # =========================== MEETING CONFIRMATION ===========================
    def referral(giver: TestClient, receiver_id: str, **over) -> str:
        r = giver.post("/api/v1/referrals", json=referral_payload(receiver_id, **over), headers=H(giver))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def patch(c: TestClient, rid: str, st: str):
        return c.patch(f"/api/v1/referrals/{rid}", json={"status": st}, headers=H(c))

    def confirm(c: TestClient, rid: str, **kw):
        return c.post(f"/api/v1/referrals/{rid}/meeting/confirm", headers=H(c), **kw)

    r1 = referral(a, b_id)
    check("a meeting cannot be confirmed before acceptance", confirm(a, r1).status_code == 409)
    check("MEETING_DONE cannot be forced by a status update", patch(a, r1, "MEETING_DONE").status_code == 400 and patch(b, r1, "MEETING_DONE").status_code == 400)
    check("BUSINESS_CLOSED cannot be forced by a status update", patch(b, r1, "BUSINESS_CLOSED").status_code == 400)
    check("recipient accepts", patch(b, r1, "ACCEPTED").status_code == 200)
    check("an unauthenticated visitor cannot confirm", new_client().post(f"/api/v1/referrals/{r1}/meeting/confirm").status_code == 401)
    check("confirmation needs the CSRF header", a.post(f"/api/v1/referrals/{r1}/meeting/confirm").status_code == 403)
    check("a member outside the referral gets a 404", confirm(c3, r1).status_code == 404)
    check("an account without Networking access is refused", outsider is not None and confirm(sub2, r1).status_code == 403)
    check("an unknown referral id is a 404", confirm(a, "not-a-referral").status_code == 404)

    r = confirm(a, r1, json={"user_id": b_id, "role": "receiver"})  # forged identity in the body
    check("the first confirmation is accepted", r.status_code == 200 and r.json()["state"] == "WAITING_FOR_OTHER" and r.json()["you_confirmed"], r.text[:200])
    rows1 = rows("select user_id, role from referral_confirmations where referral_id = :r", r=r1)
    check("a forged user id in the body is ignored: only the caller is recorded", [(x[0], x[1]) for x in rows1] == [(a_id, "giver")], str(rows1))
    check("the referral does NOT advance on one confirmation", a.get(f"/api/v1/referrals/{r1}").json()["status"] == "ACCEPTED")
    check("the other member sees 'waiting for your confirmation'", b.get(f"/api/v1/referrals/{r1}").json()["meeting"]["state"] == "WAITING_FOR_YOU")
    check("the confirmer sees 'waiting for the other member'", a.get(f"/api/v1/referrals/{r1}").json()["meeting"]["state"] == "WAITING_FOR_OTHER")
    rep = confirm(a, r1)
    check("a repeat confirmation is idempotent: same answer, nothing added", rep.status_code == 200 and rep.json()["state"] == "WAITING_FOR_OTHER" and len(rows("select 1 from referral_confirmations where referral_id = :r", r=r1)) == 1
          and scalar("select count(*) from audit_log where action = 'referral.meeting_confirmed' and resource_id = :r", r=r1) == 1, rep.text[:200])
    check("a member cannot confirm on behalf of the other", len(rows("select 1 from referral_confirmations where referral_id = :r", r=r1)) == 1)
    r = b.post(f"/api/v1/referrals/{r1}/meeting/withdraw", headers=H(b))
    check("withdrawing a confirmation you never made is refused", r.status_code == 409)
    r = a.post(f"/api/v1/referrals/{r1}/meeting/withdraw", headers=H(a))
    check("a member can withdraw their own confirmation before the other confirms", r.status_code == 200 and r.json()["state"] == "WAITING_FOR_YOU")
    confirm(a, r1)
    r = confirm(b, r1)
    check("the second confirmation completes it", r.status_code == 200 and r.json()["state"] == "CONFIRMED_BY_BOTH", r.text[:200])
    rj = a.get(f"/api/v1/referrals/{r1}").json()
    check("the referral becomes MEETING_DONE with a timestamp", rj["status"] == "MEETING_DONE" and rj["meeting_done_at"] and rj["meeting"]["state"] == "CONFIRMED_BY_BOTH", str(rj)[:300])
    rows1 = rows("select role, confirmed_at from referral_confirmations where referral_id = :r order by role", r=r1)
    check("both confirmations are stored with actor and time", [x[0] for x in rows1] == ["giver", "receiver"] and all(x[1] for x in rows1))
    rep = confirm(a, r1)
    check("confirming again after both is idempotent too", rep.status_code == 200 and rep.json()["state"] == "CONFIRMED_BY_BOTH" and len(rows("select 1 from referral_confirmations where referral_id = :r", r=r1)) == 2
          and scalar("select count(*) from audit_log where action = 'referral.status_changed' and resource_id = :r and after_json like '%MEETING_DONE%'", r=r1) == 1)
    check("a completed confirmation cannot be withdrawn", a.post(f"/api/v1/referrals/{r1}/meeting/withdraw", headers=H(a)).status_code == 409)

    # race: both confirm at the same instant; and one member double-clicks
    r2 = referral(a, b_id)
    patch(b, r2, "ACCEPTED")
    clients = [new_client(), new_client()]
    for cl, src in zip(clients, (a, b)):
        cl.cookies.update(src.cookies)
    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(lambda cl: cl.post(f"/api/v1/referrals/{r2}/meeting/confirm", headers=H(cl)).status_code, clients))
    check("racing confirmations from both members both succeed", res == [200, 200], str(res))
    check("exactly two confirmation rows exist after the race", len(rows("select 1 from referral_confirmations where referral_id = :r", r=r2)) == 2)
    check("the referral advanced exactly once", scalar("select count(*) from audit_log where resource_id = :r and action = 'referral.status_changed' and after_json like '%MEETING_DONE%'", r=r2) == 1)
    r3 = referral(a, b_id)
    patch(b, r3, "ACCEPTED")
    dbl = [new_client(), new_client()]
    for cl in dbl:
        cl.cookies.update(a.cookies)
    with ThreadPoolExecutor(2) as ex:
        res = sorted(ex.map(lambda cl: cl.post(f"/api/v1/referrals/{r3}/meeting/confirm", headers=H(cl)).status_code, dbl))
    check("a double click confirms once", res == [200, 200] and len(rows("select 1 from referral_confirmations where referral_id = :r", r=r3)) == 1
          and scalar("select count(*) from audit_log where action = 'referral.meeting_confirmed' and resource_id = :r", r=r3) == 1, str(res))

    r = a.post(f"/api/v1/referrals/{r1}/meeting/dispute", json={"reason": "The meeting did not take place"}, headers=H(a))
    check("a member can dispute a confirmed meeting", r.status_code == 204)
    check("a dispute flags the referral for review", scalar("select flagged from business_referrals where id = :r", r=r1) in (1, True))
    check("an outsider cannot dispute", c3.post(f"/api/v1/referrals/{r1}/meeting/dispute", json={"reason": "I do not like it"}, headers=H(c3)).status_code == 404)

    # =========================== DEAL CLOSURE ===========================
    def report(c: TestClient, rid: str, value, **kw):
        return c.post(f"/api/v1/referrals/{rid}/closure", json={"actual_value": value, **kw}, headers=H(c))

    def confirm_deal(c: TestClient, rid: str, minor: int):
        return c.post(f"/api/v1/referrals/{rid}/closure/confirm", json={"expected_value_minor": minor}, headers=H(c))

    def ready_referral(**over) -> str:
        rid = referral(a, b_id, **over)
        patch(b, rid, "ACCEPTED")
        confirm(a, rid)
        confirm(b, rid)
        return rid

    # bands (pure function)
    check("value bands", [ver.value_band(x) for x in (1, 2_499_999, 2_500_000, 9_999_999, 10_000_000, 49_999_999, 50_000_000, 99_999_999, 100_000_000)]
          == ["UNDER_25K", "UNDER_25K", "25K_1L", "25K_1L", "1L_5L", "1L_5L", "5L_10L", "5L_10L", "10L_PLUS"])
    check("evidence is required from ₹1,00,000 and admin approval from ₹5,00,000", ver.evidence_required(10_000_000) and not ver.evidence_required(9_999_999) and ver.admin_approval_required(50_000_000) and not ver.admin_approval_required(49_999_999))

    r4 = ready_referral(value_range="1L_5L")  # the creation-time ESTIMATE
    check("only the recipient can report a closure", report(a, r4, 100.0).status_code == 403)
    check("an outsider gets a 404 on a closure", report(c3, r4, 100.0).status_code == 404)
    check("a closure needs the CSRF header", b.post(f"/api/v1/referrals/{r4}/closure", json={"actual_value": 10}).status_code == 403)
    check("an unauthenticated visitor cannot report", new_client().post(f"/api/v1/referrals/{r4}/closure", json={"actual_value": 10}).status_code == 401)
    for bad in (0, -5, 10 ** 12, "abc"):
        check(f"invalid amount {bad!r} is refused", report(b, r4, bad).status_code == 422)
    early = referral(a, b_id)
    patch(b, early, "ACCEPTED")
    check("a closure needs a meeting confirmed by both", report(b, early, 1000).status_code == 409)

    r = report(b, r4, 375000.00, note="Annual contract signed")
    cl = r.json() if r.status_code == 201 else {}
    check("the recipient reports the ACTUAL value", r.status_code == 201 and cl["actual_value_minor"] == 37_500_000 and cl["currency"] == "INR", r.text[:300])
    check("the band is derived from the actual value", cl["value_band"] == "1L_5L" and cl["evidence_required"] is True and cl["admin_approval_required"] is False)
    check("a fresh report is self-reported (level 0) and awaiting confirmation", cl["status"] == "AWAITING_CONFIRMATION" and cl["verification_level"] == 0)
    check("the creation-time estimate is kept separately", b.get(f"/api/v1/referrals/{r4}").json()["value_range"] == "1L_5L" and rows("select value_range from business_referrals where id = :r", r=r4)[0][0] == "1L_5L")
    check("the report does not move the referral yet", b.get(f"/api/v1/referrals/{r4}").json()["status"] == "MEETING_DONE")
    check("a duplicate report is refused", report(b, r4, 100.0).status_code == 409)
    r = b.patch(f"/api/v1/referrals/{r4}/closure", json={"actual_value": 480000}, headers=H(b))
    check("the reporter may correct it before confirmation", r.status_code == 200 and r.json()["actual_value_minor"] == 48_000_000 and r.json()["value_band"] == "1L_5L")
    check("the referrer cannot edit the value", a.patch(f"/api/v1/referrals/{r4}/closure", json={"actual_value": 1}, headers=H(a)).status_code == 403)
    check("the recipient cannot confirm their own report", b.post(f"/api/v1/referrals/{r4}/closure/confirm", json={"expected_value_minor": 48_000_000}, headers=H(b)).status_code == 403)
    check("an outsider cannot confirm", c3.post(f"/api/v1/referrals/{r4}/closure/confirm", json={"expected_value_minor": 48_000_000}, headers=H(c3)).status_code == 404)
    check("confirming a value the referrer did not see is refused", confirm_deal(a, r4, 37_500_000).status_code == 409)
    r = confirm_deal(a, r4, 48_000_000)
    check("the referrer confirms: both parties = level 2", r.status_code == 200 and r.json()["verification_level"] == 2 and r.json()["confirmed_by_referrer_at"] and r.json()["confirmed_by_receiver_at"], r.text[:300])
    check("evidence is now required", r.json()["status"] == "AWAITING_EVIDENCE")
    check("the referral becomes BUSINESS_CLOSED only now", a.get(f"/api/v1/referrals/{r4}").json()["status"] == "BUSINESS_CLOSED")
    check("confirming twice is refused (replay)", confirm_deal(a, r4, 48_000_000).status_code == 409)
    check("the value is locked after confirmation", b.patch(f"/api/v1/referrals/{r4}/closure", json={"actual_value": 1}, headers=H(b)).status_code == 409)
    check("revenue cannot be logged before verification", patch(b, r4, "REVENUE_GENERATED").status_code == 409)
    check("a referral with an open closure cannot be CLOSED or CANCELLED", patch(b, r4, "CLOSED").status_code in (400, 409) and patch(a, r4, "CANCELLED").status_code in (400, 409))

    # evidence
    ev = lambda c, rid, kind="INVOICE", f=None, **kw: c.post(f"/api/v1/referrals/{rid}/closure/evidence", data={"evidence_type": kind, **kw}, files={"file": f or ("invoice.png", io.BytesIO(PNG), "image/png")}, headers=H(c))  # noqa: E731
    check("an outsider cannot add evidence", ev(c3, r4).status_code == 404)
    check("evidence of an unknown type is refused", ev(b, r4, "SELFIE").status_code == 422)
    check("a spoofed evidence file is refused", ev(b, r4, f=("x.png", io.BytesIO(b"<script>alert(1)</script>"), "image/png")).status_code == 415)
    r = ev(b, r4, note="Invoice 118")
    cj = r.json() if r.status_code == 201 else {}
    check("evidence is stored and the closure goes under review", r.status_code == 201 and cj["status"] == "UNDER_REVIEW" and len(cj["evidence"]) == 1 and cj["evidence"][0]["status"] == "PENDING", r.text[:300])
    check("the member response exposes no storage name or url", "storage" not in r.text and "http" not in r.text and "sha256" not in r.text)
    eid = cj["evidence"][0]["id"]
    check("the file endpoint serves a party", b.get(f"/api/v1/referrals/{r4}/closure/evidence/{eid}/file").status_code == 200 and a.get(f"/api/v1/referrals/{r4}/closure/evidence/{eid}/file").status_code == 200)
    check("the file endpoint hides it from outsiders", c3.get(f"/api/v1/referrals/{r4}/closure/evidence/{eid}/file").status_code == 404)
    other_ref = ready_referral()
    check("evidence cannot be reached through a different referral (IDOR)", a.get(f"/api/v1/referrals/{other_ref}/closure/evidence/{eid}/file").status_code == 404)
    check("the file endpoint requires a session", new_client().get(f"/api/v1/referrals/{r4}/closure/evidence/{eid}/file").status_code == 401)
    h = b.get(f"/api/v1/referrals/{r4}/closure/evidence/{eid}/file").headers
    check("evidence is served without sniffing and uncached", h.get("x-content-type-options") == "nosniff" and "no-store" in h.get("cache-control", ""))
    check("a stored evidence file lives on the private store, not a public path", len(os.listdir(f"{TMP}/uploads")) >= 1 and all(not p.endswith(".html") for p in os.listdir(f"{TMP}/uploads")))

    # admin review
    check("a customer cannot use the admin referral API", b.get("/api/admin/referrals").status_code == 401 and b.get(f"/api/admin/referrals/{r4}").status_code == 401)
    check("admin actions need CSRF", admin.post(f"/api/admin/referrals/{r4}/closure/evidence/{eid}/verify", json={"reason": "Looks right"}).status_code == 403)
    check("verifying needs a reason", admin.post(f"/api/admin/referrals/{r4}/closure/evidence/{eid}/verify", json={}, headers=AH).status_code == 422)
    check("a customer cannot verify evidence", b.post(f"/api/admin/referrals/{r4}/closure/evidence/{eid}/verify", json={"reason": "Looks right"}, headers=H(b)).status_code == 401)
    det = admin.get(f"/api/admin/referrals/{r4}").json()
    check("admin detail shows referrer, recipient, closure, evidence and timeline", det["referrer"]["email"] == "a@example.com" and det["recipient"]["email"] == "b@example.com" and det["closure"]["actual_value_minor"] == 48_000_000 and len(det["closure"]["evidence"]) == 1 and len(det["meeting_confirmations"]) == 2 and len(det["timeline"]) >= 5, str(det)[:400])
    check("admin detail shows both the estimate and the actual value", det["estimated_value_range"] == "1L_5L" and det["closure"]["value_band_label"].startswith("₹1,00,000"))
    r = admin.post(f"/api/admin/referrals/{r4}/closure/evidence/{eid}/verify", json={"reason": "Invoice 118 matches the amount"}, headers=AH)
    d2 = r.json() if r.status_code == 200 else {}
    check("verified evidence under ₹5L completes verification at level 3", r.status_code == 200 and d2["closure"]["status"] == "VERIFIED" and d2["closure"]["verification_level"] == 3 and d2["closure"]["verified_by"] == ADMIN_EMAIL, r.text[:300])
    check("verifying the same evidence twice is refused", admin.post(f"/api/admin/referrals/{r4}/closure/evidence/{eid}/verify", json={"reason": "again"}, headers=AH).status_code == 409)
    check("evidence cannot be added after approval", ev(b, r4).status_code == 409)
    check("the value cannot change after verification", b.patch(f"/api/v1/referrals/{r4}/closure", json={"actual_value": 1}, headers=H(b)).status_code == 409)
    r = admin.post(f"/api/admin/referrals/{r4}/closure/verify", json={"reason": "Reviewed by finance"}, headers=AH)
    check("an admin can raise it to level 4", r.status_code == 200 and r.json()["closure"]["verification_level"] == 4)
    check("revenue can be logged once verified", patch(b, r4, "REVENUE_GENERATED").status_code == 200)

    # small deal: no evidence, verified by both parties
    r5 = ready_referral()
    report(b, r5, 40000)
    r = confirm_deal(a, r5, 4_000_000)
    check("a deal under ₹1,00,000 needs no evidence: verified at level 2", r.status_code == 200 and r.json()["status"] == "VERIFIED" and r.json()["verification_level"] == 2 and r.json()["evidence_required"] is False, r.text[:300])
    check("and moves the referral to BUSINESS_CLOSED", a.get(f"/api/v1/referrals/{r5}").json()["status"] == "BUSINESS_CLOSED")

    # a larger deal needs admin approval
    r6 = ready_referral()
    report(b, r6, 750000)
    r = confirm_deal(a, r6, 75_000_000)
    check("₹7,50,000 needs evidence and admin approval", r.json()["evidence_required"] and r.json()["admin_approval_required"] and r.json()["value_band"] == "5L_10L")
    e6 = ev(b, r6, "PAYMENT_PROOF", ("pay.pdf", io.BytesIO(PDF), "application/pdf")).json()["evidence"][0]["id"]
    admin.post(f"/api/admin/referrals/{r6}/closure/evidence/{e6}/verify", json={"reason": "Bank credit matches"}, headers=AH)
    d6 = admin.get(f"/api/admin/referrals/{r6}").json()
    check("verified evidence alone does NOT complete a ₹5L+ deal", d6["closure"]["status"] == "UNDER_REVIEW" and d6["closure"]["verification_level"] == 2, str(d6["closure"])[:200])
    r = admin.post(f"/api/admin/referrals/{r6}/closure/verify", json={"reason": "Approved"}, headers=AH)
    check("admin approval completes it at level 4", r.status_code == 200 and r.json()["closure"]["status"] == "VERIFIED" and r.json()["closure"]["verification_level"] == 4)

    # evidence rejection and re-upload; shared evidence flags
    r7 = ready_referral()
    report(b, r7, 200000)
    confirm_deal(a, r7, 20_000_000)
    e7 = ev(b, r7, f=("inv.png", io.BytesIO(PNG2), "image/png")).json()["evidence"][0]["id"]
    r = admin.post(f"/api/admin/referrals/{r7}/closure/evidence/{e7}/reject", json={"reason": "The document is unreadable"}, headers=AH)
    check("rejecting the only evidence returns the closure to 'awaiting evidence'", r.status_code == 200 and r.json()["closure"]["status"] == "AWAITING_EVIDENCE" and r.json()["closure"]["evidence"][0]["rejection_reason"] == "The document is unreadable", r.text[:300])
    check("the member sees the rejection reason", b.get(f"/api/v1/referrals/{r7}").json()["closure"]["evidence"][0]["rejection_reason"] == "The document is unreadable")
    r = ev(b, r7, f=("inv2.png", io.BytesIO(PNG), "image/png"))  # same bytes as r4's evidence
    check("a new document can be uploaded", r.status_code == 201 and r.json()["status"] == "UNDER_REVIEW")
    check("the same file used on another deal flags the referral", scalar("select flagged from business_referrals where id = :r", r=r7) in (1, True) and "same evidence" in (scalar("select flag_reason from business_referrals where id = :r", r=r7) or "").lower())
    d7 = admin.get(f"/api/admin/referrals/{r7}").json()
    check("admin sees how often a file was reused", any(x["reused_in_other_closures"] >= 1 for x in d7["closure"]["evidence"]))
    check("at most five evidence files per deal", all(ev(b, r7, f=("i.png", io.BytesIO(PNG2 + bytes([i])), "image/png")).status_code in (201, 409) for i in range(6)) and len(rows("select 1 from deal_evidence where closure_id = (select id from deal_closures where referral_id = :r and status not in ('REJECTED','CANCELLED','INVALIDATED'))", r=r7)) <= 6)

    # dispute, resolution, invalidation, re-report, cancel
    r = a.post(f"/api/v1/referrals/{r5}/closure/dispute", json={"reason": "The amount is wrong"}, headers=H(a))
    check("either member can dispute a closure", r.status_code == 200 and r.json()["status"] == "DISPUTED", r.text[:200])
    check("an outsider cannot dispute", c3.post(f"/api/v1/referrals/{r5}/closure/dispute", json={"reason": "I just dislike it"}, headers=H(c3)).status_code == 404)
    check("a disputed closure cannot be disputed again", a.post(f"/api/v1/referrals/{r5}/closure/dispute", json={"reason": "again please"}, headers=H(a)).status_code == 409)
    check("a dispute flags the referral", scalar("select flagged from business_referrals where id = :r", r=r5) in (1, True))
    check("resolving needs a reason and a valid outcome", admin.post(f"/api/admin/referrals/{r5}/closure/resolve-dispute", json={"outcome": "RESTORE"}, headers=AH).status_code == 422 and admin.post(f"/api/admin/referrals/{r5}/closure/resolve-dispute", json={"outcome": "MAYBE", "reason": "unclear"}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/referrals/{r5}/closure/resolve-dispute", json={"outcome": "RESTORE", "reason": "The amount was right"}, headers=AH)
    check("restoring returns the closure to its earlier state", r.status_code == 200 and r.json()["closure"]["status"] == "VERIFIED", r.text[:200])
    a.post(f"/api/v1/referrals/{r5}/closure/dispute", json={"reason": "Customer refunded the money"}, headers=H(a))
    r = admin.post(f"/api/admin/referrals/{r5}/closure/resolve-dispute", json={"outcome": "INVALIDATE", "reason": "Refunded by the customer"}, headers=AH)
    check("invalidating ends the closure and reverts the referral", r.status_code == 200 and r.json()["status"] == "MEETING_DONE" and r.json()["closure"] is None and r.json()["past_closures"][0]["status"] == "INVALIDATED", r.text[:300])
    r = report(b, r5, 41000)
    check("an invalidated deal can be reported again", r.status_code == 201 and r.json()["status"] == "AWAITING_CONFIRMATION")
    r = b.post(f"/api/v1/referrals/{r5}/closure/cancel", headers=H(b))
    check("the reporter can cancel an unconfirmed report", r.status_code == 200 and r.json()["status"] == "CANCELLED")
    check("and report again correctly", report(b, r5, 42000).status_code == 201)
    check("the referrer cannot cancel the recipient's report", a.post(f"/api/v1/referrals/{r5}/closure/cancel", headers=H(a)).status_code == 403)
    r = admin.post(f"/api/admin/referrals/{r5}/closure/reject", json={"reason": "Duplicate of an earlier invoice"}, headers=AH)
    check("admin can reject a closure", r.status_code == 200 and r.json()["closure"] is None and r.json()["past_closures"][0]["status"] == "REJECTED")
    check("a terminal closure cannot be moved again", admin.post(f"/api/admin/referrals/{r5}/closure/verify", json={"reason": "Trying anyway"}, headers=AH).status_code == 404)

    # direct invalidation of a verified deal (refund, fraud found later)
    r8 = ready_referral()
    report(b, r8, 30000)
    confirm_deal(a, r8, 3_000_000)
    check("invalidation needs a reason", admin.post(f"/api/admin/referrals/{r8}/closure/invalidate", json={}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/referrals/{r8}/closure/invalidate", json={"reason": "The customer cancelled and was refunded"}, headers=AH)
    check("an admin can invalidate a verified deal", r.status_code == 200 and r.json()["status"] == "MEETING_DONE" and r.json()["past_closures"][0]["status"] == "INVALIDATED" and r.json()["past_closures"][0]["invalidated_reason"], r.text[:300])
    check("revenue can no longer be logged on it", patch(b, r8, "REVENUE_GENERATED").status_code in (400, 409))

    # admin referral list: filters and pagination
    allr = admin.get("/api/admin/referrals", params={"page_size": 3}).json()
    check("the admin list is paginated", len(allr["items"]) == 3 and allr["pages"] == -(-allr["total"] // 3) and allr["total"] >= 8, str({k: allr[k] for k in ("total", "pages", "page_size")}))
    check("pages are distinct", {x["id"] for x in allr["items"]}.isdisjoint({x["id"] for x in admin.get("/api/admin/referrals", params={"page_size": 3, "page": 2}).json()["items"]}))
    check("the page size is capped", admin.get("/api/admin/referrals", params={"page_size": 101}).status_code == 422)
    f = lambda **p: admin.get("/api/admin/referrals", params=p).json()  # noqa: E731
    check("filter: status", {x["status"] for x in f(status="BUSINESS_CLOSED")["items"]} == {"BUSINESS_CLOSED"} and f(status="BUSINESS_CLOSED")["total"] >= 2)
    check("filter: closure status", all(x["closure_status"] == "VERIFIED" for x in f(closure_status="VERIFIED")["items"]) and f(closure_status="VERIFIED")["total"] >= 2)
    check("filter: no closure", all(x["closure_status"] is None for x in f(closure_status="NONE", page_size=100)["items"]))
    check("filter: verification level", all(x["closure_level"] == 4 for x in f(verification_level=4)["items"]) and f(verification_level=4)["total"] >= 2)
    check("filter: deal value band", {x["closure_band"] for x in f(deal_band="5L_10L")["items"]} == {"5L_10L"})
    check("filter: referrer", f(referrer="a@example.com", page_size=100)["total"] == f(page_size=100)["total"] and f(referrer="nobody@example.com")["total"] == 0)
    check("filter: recipient", f(recipient="Beta")["total"] >= 8 and f(recipient="Alpha")["total"] == 0)
    check("filter: flagged", f(flagged="true")["total"] >= 1 and all(x["flagged"] for x in f(flagged="true", page_size=100)["items"]))
    check("filter: date range", f(date_from="2000-01-01", date_to="2999-12-31")["total"] == f()["total"] and f(date_to="2000-01-01")["total"] == 0)
    check("the list shows actual value separately from the estimate", any(x["actual_value_minor"] and "estimated_value_range" in x for x in f(closure_status="VERIFIED")["items"]))
    check("the admin list carries no prospect contact data", "98765" not in json.dumps(f(page_size=100)))

    # flags, status correction, notes
    check("flagging needs a reason", admin.post(f"/api/admin/referrals/{r3}/flag", json={"flagged": True}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/referrals/{r3}/flag", json={"flagged": True, "reason": "Two accounts, same prospect"}, headers=AH)
    check("an admin can flag a referral", r.status_code == 200 and r.json()["flagged"] is True and r.json()["flag_reason"] == "Two accounts, same prospect")
    check("an admin can clear a flag", admin.post(f"/api/admin/referrals/{r3}/flag", json={"flagged": False, "reason": "Checked: fine"}, headers=AH).json()["flagged"] is False)
    check("a status correction needs a reason", admin.post(f"/api/admin/referrals/{r3}/status", json={"status": "CONTACTED"}, headers=AH).status_code == 422)
    check("an admin cannot set BUSINESS_CLOSED directly", admin.post(f"/api/admin/referrals/{r3}/status", json={"status": "BUSINESS_CLOSED", "reason": "Because I said so"}, headers=AH).status_code == 409)
    check("an unknown status is refused", admin.post(f"/api/admin/referrals/{r3}/status", json={"status": "FANTASTIC", "reason": "Nonsense status"}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/referrals/{r3}/status", json={"status": "CONTACTED", "reason": "Recipient called the prospect"}, headers=AH)
    check("an admin can correct a status", r.status_code == 200 and r.json()["status"] == "CONTACTED")
    check("a referral with a closed business cannot be status-corrected", admin.post(f"/api/admin/referrals/{r4}/status", json={"status": "ACCEPTED", "reason": "Trying to bypass"}, headers=AH).status_code == 409)
    # A referral advanced by the OLD one-member flow has no confirmations. It is never presented as verified,
    # cannot be used to report a deal, and can only be fixed by sending it back so BOTH members confirm.
    def force(sql: str, **params):
        async def f(s_):
            await s_.execute(text(sql), params)
            await s_.commit()
        db(f)

    legacy = referral(a, b_id)
    patch(b, legacy, "ACCEPTED")
    force("update business_referrals set status = 'BUSINESS_CLOSED', meeting_done_at = created_at, business_closed_at = created_at where id = :r", r=legacy)
    check("a legacy referral is not shown as a confirmed meeting", a.get(f"/api/v1/referrals/{legacy}").json()["meeting"]["state"] == "NOT_VERIFIED")
    det = admin.get(f"/api/admin/referrals/{legacy}").json()
    check("admin sees it as legacy and unverified", det["legacy_unverified"] is True and det["meeting_verified"] is False and det["meeting_confirmations"] == [])
    lst = admin.get("/api/admin/referrals", params={"legacy_unverified": "true"}).json()
    check("the admin list can filter to legacy referrals", legacy in [x["id"] for x in lst["items"]] and all(x["legacy_unverified"] for x in lst["items"]))
    check("a verified referral is not listed as legacy", r1 not in [x["id"] for x in lst["items"]])
    check("no closure can be reported on a legacy BUSINESS_CLOSED referral", report(b, legacy, 12345).status_code == 409)
    force("update business_referrals set status = 'MEETING_DONE', business_closed_at = null where id = :r", r=legacy)
    check("no closure can be reported on a legacy MEETING_DONE referral without both confirmations", report(b, legacy, 12345).status_code == 409)
    for target in ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED"):
        check(f"an admin cannot set {target}", admin.post(f"/api/admin/referrals/{legacy}/status", json={"status": target, "reason": "Trying to skip the workflow"}, headers=AH).status_code == 409)
    check("a correction needs a reason", admin.post(f"/api/admin/referrals/{legacy}/status", json={"status": "CONTACTED"}, headers=AH).status_code == 422)
    r = admin.post(f"/api/admin/referrals/{legacy}/status", json={"status": "CONTACTED", "reason": "Advanced by the old one-member flow; both members must confirm"}, headers=AH)
    check("a legacy referral can be sent back to CONTACTED", r.status_code == 200 and r.json()["status"] == "CONTACTED" and r.json()["meeting_done_at"] is None and r.json()["business_closed_at"] is None, r.text[:200])
    arow = rows("select metadata_json from audit_log where action = 'referral.status_corrected' and resource_id = :r order by created_at desc limit 1", r=legacy)[0][0]
    check("the audit entry marks it as a legacy correction", '"legacy_unverified": true' in arow.replace('":true', '": true'), arow[:200])
    check("it needs both members to confirm again", confirm(a, legacy).status_code == 200 and a.get(f"/api/v1/referrals/{legacy}").json()["status"] == "CONTACTED")
    check("and then the meeting is genuinely verified", confirm(b, legacy).status_code == 200 and a.get(f"/api/v1/referrals/{legacy}").json()["meeting"]["state"] == "CONFIRMED_BY_BOTH")
    check("only then can the recipient report the business", report(b, legacy, 12345).status_code == 201)
    # an error correction on a properly verified referral discards the confirmations (kept in the audit entry)
    fixed = ready_referral()
    admin.post(f"/api/admin/referrals/{fixed}/status", json={"status": "ACCEPTED", "reason": "Meeting was confirmed by mistake"}, headers=AH)
    check("moving a verified referral back discards its confirmations", scalar("select count(*) from referral_confirmations where referral_id = :r", r=fixed) == 0)
    check("what was discarded is preserved in the audit entry", "removed_meeting_confirmations" in rows("select metadata_json from audit_log where action = 'referral.status_corrected' and resource_id = :r", r=fixed)[0][0] and fixed in [x[0] for x in rows("select resource_id from audit_log where action = 'referral.status_corrected'")])
    check("the members can confirm the meeting again afterwards", confirm(a, fixed).status_code == 200 and confirm(b, fixed).status_code == 200)
    check("an admin can add a note", admin.post(f"/api/admin/referrals/{r3}/notes", json={"reason": "Spoke to both members; no action needed"}, headers=AH).status_code == 200)
    check("an unknown referral is a 404 for admins", admin.get("/api/admin/referrals/nope").status_code == 404)

    # =========================== AUDIT LOG ===========================
    actions = {x[0] for x in rows("select distinct action from audit_log")}
    wanted = {"subscription.created", "invoice.issued", "payment.proof_submitted", "payment.verified", "payment.rejected", "payment.refunded", "subscription.cancelled",
              "referral.created", "referral.status_changed", "referral.meeting_confirmed", "referral.meeting_withdrawn", "referral.meeting_disputed", "referral.flagged", "referral.unflagged",
              "referral.status_corrected", "admin.note", "closure.reported", "closure.value_changed", "closure.confirmed", "closure.disputed", "closure.cancelled", "closure.rejected",
              "closure.invalidated", "closure.verified", "closure.dispute_resolved", "evidence.uploaded", "evidence.verified", "evidence.rejected"}
    check("every sensitive action is recorded", wanted <= actions, str(sorted(wanted - actions)))
    crow = rows("select actor_type, actor_id, actor_role, after_json from audit_log where action = 'closure.reported' order by created_at limit 1")[0]
    check("the actor is recorded correctly", crow[0] == "USER" and crow[1] == b_id and crow[2] == "receiver", str(crow)[:200])
    erow = rows("select actor_type, actor_id, actor_role from audit_log where action = 'evidence.verified' limit 1")[0]
    check("an admin's actor id and role are recorded", erow[0] == "ADMIN" and erow[1] == admin_id and erow[2] == "admin", str(erow))
    check("before/after state is recorded", "37500000" in (rows("select before_json from audit_log where action = 'closure.value_changed' limit 1")[0][0] or "") and "48000000" in (rows("select after_json from audit_log where action = 'closure.value_changed' limit 1")[0][0] or ""))
    admin_rows = rows("select action, reason from audit_log where actor_type = 'ADMIN'")
    check("every admin action carries a reason", admin_rows and all((x[1] or "").strip() for x in admin_rows if not x[0].startswith(LEGACY_ADMIN_ACTIONS)), str([x for x in admin_rows if not (x[1] or '').strip()][:3]))
    check("every audit entry for a request carries its request id", scalar("select count(*) from audit_log where request_id is null and actor_type <> 'SYSTEM'") == 0)
    rid_resp = a.post("/api/v1/referrals", json=referral_payload(b_id), headers={**H(a), "X-Request-ID": "trace-12345"})
    check("the request id is echoed and recorded", rid_resp.status_code == 201 and rid_resp.headers.get("x-request-id") == "trace-12345" and scalar("select count(*) from audit_log where request_id = 'trace-12345'") >= 1)
    blob = " ".join(" ".join(str(c or "") for c in row) for row in rows("select before_json, after_json, reason, metadata_json from audit_log"))
    check("no secrets are recorded", not re.search(r"argon2|CorrectHorse|csrf|tgl_customer|password", blob, re.I), re.findall(r"argon2|CorrectHorse|csrf|password", blob, re.I)[:3].__repr__())
    check("no payment proof file names or prospect contact data in the audit log", not re.search(r"\.(png|pdf)|98765\d+", blob))
    cleaned = audit_mod._clean({"password": "x", "nested": {"api_key": "y", "ok": 1}, "csrf_token": "z", "note": "a" * 900})
    check("the sanitiser redacts credential-like keys and truncates long text", cleaned["password"] == "[redacted]" and cleaned["nested"]["api_key"] == "[redacted]" and cleaned["csrf_token"] == "[redacted]" and cleaned["nested"]["ok"] == 1 and len(cleaned["note"]) <= 500)
    check("DB: audit rows cannot be updated", bad_insert("update audit_log set action = 'tampered'"))
    check("DB: audit rows cannot be deleted", bad_insert("delete from audit_log"))

    async def orm_tamper(s):
        row = (await s.execute(text("select 1"))).first()
        obj = await s.get(AuditLog, scalar_id)
        obj.reason = "changed"
        try:
            await s.commit()
            return False
        except RuntimeError:
            await s.rollback()
            return True
        except Exception:
            await s.rollback()
            return True
    scalar_id = scalar("select id from audit_log limit 1")
    check("the ORM refuses to change an audit row", db(orm_tamper))

    # =========================== SECURITY ===========================
    check("cross-member leakage: an outsider's referral list is empty", c3.get("/api/v1/referrals").json() == [] and c3.get("/api/v1/referrals/summary").json()["total"] == 0)
    check("cross-member leakage: closures are not readable by outsiders", c3.get(f"/api/v1/referrals/{r4}/closure").status_code == 404)
    check("a party can read their closure", b.get(f"/api/v1/referrals/{r4}/closure").json()["actual_value_minor"] == 48_000_000)
    check("referral lists carry the meeting and closure state", all("meeting" in x and "closure" in x for x in b.get("/api/v1/referrals", params={"limit": 20}).json()))
    check("prospect phone numbers never appear in list responses", "98765" not in b.get("/api/v1/referrals", params={"limit": 20}).text)
    check("a PATCH cannot smuggle extra fields", b.patch(f"/api/v1/referrals/{r3}", json={"status": "CONTACTED", "meeting_done_at": "2020-01-01T00:00:00Z"}, headers=H(b)).status_code == 422)

    async def deactivate():
        async with SessionLocal() as s:
            await s.execute(text("update users set is_active = false where id = :i"), {"i": b_id})
            await s.commit()
    asyncio.run(deactivate())
    check("a suspended member cannot confirm a meeting", confirm(b, r3).status_code == 401)
    check("a suspended member cannot report a closure", report(b, r3, 100).status_code == 401)

    # =========================== PERFORMANCE (query budgets) ===========================
    # A regression to per-row lookups (N+1) fails here. Budgets are a little above today's counts.
    def queries(fn):
        n = [0]

        def _count(*_a, **_k):
            n[0] += 1
        event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            r = fn()
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _count)
        return r, n[0]

    measured: dict[str, int] = {}
    for label, cap, fn in [
        ("admin referral list (25 rows, filters)", 5, lambda: admin.get("/api/admin/referrals", params={"page_size": 25, "status": "MEETING_DONE", "flagged": "true"})),
        ("admin referral list (unfiltered page)", 5, lambda: admin.get("/api/admin/referrals", params={"page_size": 25})),
        ("admin referral detail", 14, lambda: admin.get(f"/api/admin/referrals/{r4}")),
        ("admin subscription list", 5, lambda: admin.get("/api/admin/subscriptions")),
        ("member referral list", 6, lambda: a.get("/api/v1/referrals", params={"limit": 20})),
        ("member referral detail", 8, lambda: a.get(f"/api/v1/referrals/{r4}")),
        ("current subscription", 6, lambda: outsider.get("/api/v1/subscriptions/current")),
    ]:
        resp, n = queries(fn)
        measured[label] = n
        check(f"perf budget: {label} uses <= {cap} queries", resp.status_code == 200 and n <= cap, f"{n} queries, HTTP {resp.status_code}")
    print("MEASURED QUERY COUNTS:", json.dumps(measured))

    # =========================== GROWTH POINTS: NONE ===========================
    tables = {x[0] for x in rows("select name from sqlite_master where type = 'table'")} if engine.dialect.name == "sqlite" else {x[0] for x in rows("select tablename from pg_tables where schemaname = 'public'")}
    check("no redemption, voucher, coupon, discount or reward table exists (Phase 1 adds the SHADOW growth_point_* tables only)",
          not [t for t in tables if not t.startswith("growth_point_") and re.search(r"growth|reward|point|redemption|ledger|voucher|coupon|discount", t)], str(sorted(tables)))
    check("no member has any Growth Points after all this activity", scalar("select coalesce(sum(growth_points), 0) from networking_profiles") == 0)
    inv_cols = {x[1] for x in rows("pragma table_info(invoices)")} if engine.dialect.name == "sqlite" else set()
    check("the only points columns on an invoice are the Phase 2 discount columns, and they are 0 on every invoice here (redemption is off)", {c for c in inv_cols if "point" in c} <= {"points_redeemed", "points_discount_minor"} and scalar("select count(*) from invoices where points_redeemed <> 0 or points_discount_minor <> 0") == 0)
    check("every invoice has a zero discount", scalar("select count(*) from invoices where discount_minor <> 0") == 0)
    check("no notification mentions Growth Points", scalar("select count(*) from notifications where lower(title || ' ' || body) like '%growth point%'") == 0)

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
