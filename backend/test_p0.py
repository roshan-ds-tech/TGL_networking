"""P0 business-rule checks: customer auth, Season 1, membership, Networking.

Run:  .venv/Scripts/python.exe test_p0.py

Uses a throwaway SQLite DB and upload dir so it never touches real data.
Companion to test_security.py, which covers the legacy public/admin surface.
"""
from __future__ import annotations

import asyncio
import io
import itertools
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import httpx

TMP = tempfile.mkdtemp(prefix="tgl-p0-")
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-definitely-long-enough-123456"
# TEST_DATABASE_URL runs the suite against Postgres (the engine production
# uses); the tables are dropped and recreated, so never point it at real data.
os.environ["DB_NULL_POOL"] = "true"  # tests drive the app from more than one event loop
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{TMP}/test.db".replace("\\", "/")
os.environ["UPLOAD_DIR"] = f"{TMP}/uploads"
os.environ["ADMIN_DIST_DIR"] = f"{TMP}/nonexistent"
# Never let a real key in a developer's backend/.env cause this run to hit
# the live Resend API — env vars set here win over .env either way.
os.environ["RESEND_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings as app_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin, NetworkingProfile, TGLMembership, utcnow  # noqa: E402
from app.ratelimit import reset  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import add_calendar_months  # noqa: E402

PASSWORD = "CorrectHorse123!"
ADMIN_EMAIL = "admin@tglseason.com"

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64


def _real_png() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (300, 200), (20, 90, 160)).save(out, format="PNG")
    return out.getvalue()


PNG_REAL = _real_png()
results: list[tuple[bool, str]] = []

# Several users are signed up below; the default ceiling of 10/hour per IP is
# close enough to matter once helpers re-run, so widen it for the test run.
app_settings.register_max_per_hour = 1000
app_settings.login_max_attempts = 5




_phone_seq = itertools.count(1)


def rp(receiver_id: str, need: str = "Priya needs a responsive website with online booking before opening", **over) -> dict:
    """A valid referral payload; each call gets a fresh prospect phone number."""
    payload = {
        "receiver_user_id": receiver_id,
        "prospect_name": "Priya Sharma",
        "prospect_phone": f"98765{next(_phone_seq):05d}",
        "relationship": "BUSINESS_CONTACT",
        "opportunity_description": need,
        "urgency": "HOT",
        "intro_method": "EMAIL",
        "contact_permission": "EXPECTING",
        "consent_confirmed": True,
    }
    payload.update(over)
    return payload


def confirm_meeting_both(first: TestClient, second: TestClient, ref_id: str) -> None:
    """Both members confirm the meeting (a referral reaches MEETING_DONE only this way)."""
    for c in (first, second):
        r = c.post(f"/api/v1/referrals/{ref_id}/meeting/confirm", headers={"X-CSRF-Token": customer_csrf(c)})
        assert r.status_code == 200, r.text


def close_deal(giver: TestClient, receiver: TestClient, ref_id: str, value: float = 50_000) -> None:
    """The recipient reports the actual value and the referrer confirms it (under Rs 1L: no evidence needed)."""
    r = receiver.post(f"/api/v1/referrals/{ref_id}/closure", json={"actual_value": value}, headers={"X-CSRF-Token": customer_csrf(receiver)})
    assert r.status_code == 201, r.text
    r = giver.post(f"/api/v1/referrals/{ref_id}/closure/confirm", json={"expected_value_minor": round(value * 100)}, headers={"X-CSRF-Token": customer_csrf(giver)})
    assert r.status_code == 200, r.text


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((condition, f"{name}{(' — ' + detail) if detail and not condition else ''}"))


def customer_csrf(c: TestClient) -> str:
    return c.cookies.get("tgl_customer_csrf") or ""


def new_client() -> TestClient:
    # No context manager: the first `with TestClient(app)` below already ran
    # the lifespan (tables created); further clients just make requests.
    return TestClient(app)


def signup(c: TestClient, email: str) -> str:
    """Create an account on client `c`. Returns the dev verification token."""
    r = c.post("/api/v1/auth/register", json={"full_name": "Test User", "phone": "9876543210", "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["dev_verification_token"]


def verify_email(c: TestClient, token: str) -> None:
    r = c.post(
        "/api/v1/auth/verify-email",
        data={"token": token},
        headers={"X-CSRF-Token": customer_csrf(c)},
    )
    assert r.status_code == 200, r.text


def save_personal(c: TestClient, **over) -> httpx.Response:
    payload = {
        "full_name": "Test Founder",
        "phone": "9876543210",
        "city": "Bengaluru",
        "role": "Founder",
        "short_bio": "I run a small business and I am building it every day.",
    }
    payload.update(over)
    return c.put(
        "/api/v1/profile/personal",
        json=payload,
        headers={"X-CSRF-Token": customer_csrf(c)},
    )


def save_business(c: TestClient, **over) -> httpx.Response:
    payload = {
        "business_name": "Test Biz",
        "category": "01",
        "description": "We make handcrafted products for everyday use.",
        "city": "Bengaluru",
        "employee_band": "1-3",
        "business_age": "lt6",
        "business_stage": "Early",
    }
    payload.update(over)
    return c.put(
        "/api/v1/business",
        json=payload,
        headers={"X-CSRF-Token": customer_csrf(c)},
    )


def register_season1(c: TestClient, **over) -> httpx.Response:
    """Register client `c` for Season 1 via the public form.

    That endpoint (see public.py's create_registration) now does double duty:
    for a logged-in submitter it ignores these identity/business fields
    (derived server-side from the account's saved profile instead) and links
    the registration to the account. The placeholder values below only need
    to satisfy the multipart schema. No CSRF header: the public endpoint is
    also used anonymously, so it isn't gated on the customer CSRF cookie.
    """
    files = over.pop("files", {"paymentProof": ("proof.png", io.BytesIO(PNG), "image/png")})
    data = {
        "name": "ignored",
        "business": "ignored",
        "email": "ignored@example.com",
        "phone": "9876543210",
        "category": "01",
        "employees": "1-3",
        "age": "lt6",
        "agree": "true",
        "mediaConsent": "true",
    }
    data.update(over)
    return c.post(
        "/api/registrations",
        data=data,
        files=files,
    )


def full_member(email: str, name: str = "Test Founder", business: str = "Test Biz", category: str = "01", city: str = "Bengaluru") -> TestClient:
    """A signed-up, verified, onboarded user with their own client."""
    c = new_client()
    token = signup(c, email)
    verify_email(c, token)
    assert save_personal(c, full_name=name, city=city).status_code == 200
    assert save_business(c, business_name=business, category=category, city=city).status_code == 200
    return c


async def seed() -> None:
    async with engine.begin() as c:
        if c.dialect.name == "postgresql":  # clean slate on a reused Postgres DB
            await c.exec_driver_sql("DROP SCHEMA public CASCADE")
            await c.exec_driver_sql("CREATE SCHEMA public")
        await c.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        db.add(Admin(email=ADMIN_EMAIL, password_hash=hash_password(PASSWORD)))
        await db.commit()
    await engine.dispose()


def main() -> int:
    asyncio.run(seed())

    with TestClient(app) as anon:
        # ---------- anonymous access ----------
        r = anon.get("/api/v1/networking/members")
        check("member directory requires authentication", r.status_code == 401, str(r.status_code))

        r = anon.get("/api/v1/auth/me")
        check("session query requires authentication", r.status_code == 401, str(r.status_code))

        r = anon.get("/api/v1/status")
        check("status requires authentication", r.status_code == 401, str(r.status_code))
        # Season 1 registration is now the public form (see below) — it works
        # anonymously by design, so there is no "requires authentication"
        # check for it here anymore.

    u1 = new_client()
    u2 = new_client()
    admin = new_client()

    # ---------- signup ----------
    r = u1.post("/api/v1/auth/register", json={"full_name": "Test User", "phone": "9876543210", "email": "founder1@example.com", "password": PASSWORD})
    check("customer signup succeeds", r.status_code == 201, r.text[:200])
    u1_token = r.json().get("dev_verification_token")
    check("dev verification token issued outside production", bool(u1_token))
    check(
        "customer session cookie is HttpOnly + SameSite=Strict",
        "httponly" in r.headers.get("set-cookie", "").lower()
        and "samesite=strict" in r.headers.get("set-cookie", "").lower(),
        r.headers.get("set-cookie", "")[:120],
    )
    check("signup response omits password hash", "$argon2" not in r.text)

    r = u1.post("/api/v1/auth/register", json={"full_name": "Test User", "phone": "9876543210", "email": "founder1@example.com", "password": PASSWORD})
    check("duplicate signup is rejected", r.status_code == 409, str(r.status_code))

    r = u1.post("/api/v1/auth/register", json={"email": "shortpw@example.com", "password": "short"})
    check("weak password is rejected server-side", r.status_code == 422, str(r.status_code))

    # ---------- login ----------
    r = u1.post("/api/v1/auth/login", json={"email": "founder1@example.com", "password": "wrong-password"})
    check("customer wrong password is rejected", r.status_code == 401, str(r.status_code))
    check("bad login message is generic", "Invalid email or password." in r.text, r.text[:120])

    r = u1.post("/api/v1/auth/login", json={"email": "who-knows@example.com", "password": PASSWORD})
    check("unknown customer email gives the same 401", r.status_code == 401, str(r.status_code))
    check("no account enumeration on customer login", "Invalid email or password." in r.text, r.text[:120])

    r = u1.post("/api/v1/auth/login", json={"email": "founder1@example.com", "password": PASSWORD})
    check("customer login succeeds", r.status_code == 200, r.text[:200])
    check("customer login response omits password hash", "password_hash" not in r.text and "$argon2" not in r.text)

    # account lockout on repeated failures (throwaway account)
    u4 = new_client()
    signup(u4, "lockout@example.com")
    r = u4.get("/api/v1/status")
    check("signup stores name and phone on the account", r.json()["user"].get("full_name") == "Test User" and r.json()["user"].get("phone") == "9876543210", r.text[:200])
    check("no registration for this email: networking_access is false", r.json().get("networking_access") is False, r.text[:200])
    r = u4.get("/api/v1/networking/members")
    check("account without a registration cannot read the directory", r.status_code == 403, str(r.status_code))
    codes = []
    for i in range(5):
        reset("customer-login:testclient")
        codes.append(
            u4.post("/api/v1/auth/login", json={"email": "lockout@example.com", "password": f"bad{i}"}).status_code
        )
    check("five bad logins all rejected 401", codes == [401] * 5, str(codes))
    reset("customer-login:testclient")
    r = u4.post("/api/v1/auth/login", json={"email": "lockout@example.com", "password": PASSWORD})
    check("correct password still refused while locked", r.status_code == 401, str(r.status_code))
    reset("customer-login:testclient")

    # ---------- email verification gate ----------
    r = save_personal(u1)
    check("unverified user cannot write personal profile", r.status_code == 403, str(r.status_code))

    r = u1.post("/api/v1/auth/verify-email", data={"token": "not-the-token"})
    check("verify-email requires CSRF like other mutations", r.status_code == 403, str(r.status_code))

    r = u1.post(
        "/api/v1/auth/verify-email",
        data={"token": "not-the-token"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("bogus verification token is rejected", r.status_code == 400, str(r.status_code))

    verify_email(u1, u1_token)
    r = u1.get("/api/v1/auth/me")
    check("verification marks the account verified", r.json().get("email_verified_at") is not None, r.text[:160])

    # ---------- CSRF on mutations ----------
    r = u1.put("/api/v1/profile/personal", json={"full_name": "X"})
    check("profile write without CSRF header is blocked", r.status_code == 403, str(r.status_code))

    # ---------- onboarding ----------
    r = save_personal(u1, phone="123")
    check("personal profile validates phone server-side", r.status_code == 422, str(r.status_code))

    r = save_personal(u1)
    check("personal profile saves", r.status_code == 200, r.text[:200])

    r = save_business(u1, category="99")
    check("business profile validates category server-side", r.status_code == 422, str(r.status_code))

    r = save_business(u1)
    check("business profile saves", r.status_code == 200, r.text[:200])
    check("TGL Verified defaults to false (separate status)", r.json().get("tgl_verified") is False, r.text[:200])

    # ---------- Season 1 registration ----------
    r = register_season1(u1, files={"paymentProof": ("x.png", io.BytesIO(b"<?php?>"), "image/png")})
    check("spoofed payment proof is blocked", r.status_code == 415, str(r.status_code))

    r = register_season1(u1)
    check("authenticated Season 1 registration succeeds", r.status_code == 201, r.text[:300])
    # The response itself is the minimal public-form shape ({"status",
    # "name"}, deliberately no internal IDs) — the "pre-activation state"
    # section below confirms PAYMENT_REVIEW/PENDING via /api/v1/status.

    r = register_season1(u1)
    check("duplicate Season 1 registration is rejected", r.status_code == 409, str(r.status_code))

    # registration data must come from the profile, not the client
    r = u1.get("/api/v1/status")
    reg_email = (r.json().get("user") or {}).get("email")
    check("status reports the authenticated identity", reg_email == "founder1@example.com", str(reg_email))

    # a verified but non-onboarded user cannot register yet
    u5 = new_client()
    u5_token = signup(u5, "not-onboarded@example.com")
    verify_email(u5, u5_token)
    r = register_season1(u5)
    check("registration blocked until personal profile exists", r.status_code == 409, str(r.status_code))
    check("blocked registration explains the missing step", "personal profile" in r.text.lower(), r.text[:160])

    # u2: full member, registers too. u3: registers but admin will NOT verify.
    full_member("founder2@example.com", name="Second Founder", business="Biz Two", category="02", city="Mumbai")
    r = u2.post("/api/v1/auth/login", json={"email": "founder2@example.com", "password": PASSWORD})
    check("second customer logs in", r.status_code == 200, r.text[:200])
    r = register_season1(u2)
    check("second customer registers for Season 1", r.status_code == 201, r.text[:300])

    u3 = full_member("founder3@example.com", name="Third Founder", business="Biz Three", category="03", city="Chennai")
    r = register_season1(u3)
    check("third customer registers for Season 1", r.status_code == 201, r.text[:300])

    # ---------- pre-activation state ----------
    r = u1.get("/api/v1/status")
    st = r.json()
    check("status shows registration under review", st.get("event_registration", {}).get("status") == "PAYMENT_REVIEW", r.text[:200])
    check("status shows membership PENDING before verification", st.get("membership", {}).get("status") == "PENDING", r.text[:200])
    check("status reports unread notifications", st.get("unread_notifications", 0) >= 1, str(st.get("unread_notifications")))
    check("status never exposes payment proof internals", "proof_filename" not in r.text and "proof_bytes" not in r.text)

    r = u1.get("/api/v1/networking/members")
    check("registered email stays locked before the Grand Finale", r.status_code == 403, str(r.status_code))
    check("status flags has_registration but no networking_access", st.get("has_registration") is True and st.get("networking_access") is False, r.text[:200])

    # ---------- admin verification (payment confirm ≠ membership activation) ----------
    r = u1.get("/api/admin/registrations")
    check("customer session cannot read admin API", r.status_code == 401, str(r.status_code))

    r = admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    check("admin login succeeds", r.status_code == 200, r.text[:200])
    admin_csrf = admin.cookies.get("tgl_csrf") or ""

    rows = admin.get("/api/admin/registrations", params={"search": "founder1@example.com"}).json()
    check("admin sees the authenticated registration", rows.get("total") == 1, str(rows.get("total")))
    reg1_id = rows["items"][0]["id"] if rows.get("items") else ""

    rows2 = admin.get("/api/admin/registrations", params={"search": "founder2@example.com"}).json()
    reg2_id = rows2["items"][0]["id"] if rows2.get("items") else ""
    rows3 = admin.get("/api/admin/registrations", params={"search": "founder3@example.com"}).json()
    reg3_id = rows3["items"][0]["id"] if rows3.get("items") else ""
    check("admin finds all three authenticated registrations", all([reg1_id, reg2_id, reg3_id]))

    r = admin.patch(f"/api/admin/registrations/{reg1_id}/verify", json={"verified": True})
    check("mutation without CSRF is blocked on admin too", r.status_code == 403, str(r.status_code))
    r = admin.patch(
        f"/api/admin/registrations/{reg1_id}/verify",
        json={"verified": True},
        headers={"X-CSRF-Token": admin_csrf},
    )
    check("admin payment verification succeeds", r.status_code == 200, r.text[:200])

    r = u1.get("/api/v1/status")
    st = r.json()
    check("registration becomes CONFIRMED after verification", st.get("event_registration", {}).get("status") == "CONFIRMED", r.text[:300])
    check("membership stays PENDING after payment confirmation", st.get("membership", {}).get("status") == "PENDING", r.text[:300])

    r = u1.get("/api/v1/networking/members")
    check("confirmed payment alone still cannot read member data", r.status_code == 403, str(r.status_code))

    r = u1.get("/api/v1/notifications")
    types = [n["type"] for n in r.json()]
    check("registration-confirmed notification was created", "registration_confirmed" in types, str(types))

    admin.patch(f"/api/admin/registrations/{reg2_id}/verify", json={"verified": True}, headers={"X-CSRF-Token": admin_csrf})

    # ---------- Grand Finale completion ----------
    r = admin.post("/api/admin/events/season-1/complete", headers={"X-CSRF-Token": admin_csrf})
    check("admin records Grand Finale completion", r.status_code == 200, r.text[:300])
    res = r.json() if r.status_code == 200 else {}
    check("bulk activation activates exactly the confirmed registrations", res.get("activated") == 2, str(res))
    check("bulk activation reports no double-activation", res.get("already_active") == 0, str(res))

    r = u1.get("/api/v1/status")
    st = r.json()
    m = st.get("membership") or {}
    check("membership is ACTIVE after Grand Finale completion", m.get("status") == "ACTIVE", r.text[:300])
    start, expires = m.get("starts_at"), m.get("expires_at")
    check("membership start timestamp is the recorded completion time", bool(start), str(m))
    if start and expires:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        check(
            "expiry is exactly 3 calendar months after start",
            (e.year - s.year) * 12 + e.month - s.month == 3
            and e.day == s.day
            and e.hour == s.hour,
            f"{start} -> {expires}",
        )

    r = u3.get("/api/v1/status")
    check("finale opens Networking for a registered email even before payment confirmation", (r.json().get("membership") or {}).get("status") == "ACTIVE" and r.json().get("networking_access") is True, r.text[:300])
    r = u3.get("/api/v1/networking/members")
    check("registered (unconfirmed) email can read member data", r.status_code == 200, str(r.status_code))

    # idempotency: running completion again must not double-activate
    r = admin.post("/api/admin/events/season-1/complete", headers={"X-CSRF-Token": admin_csrf})
    res = r.json() if r.status_code == 200 else {}
    check("completion is idempotent (no new activations)", res.get("activated") == 0 and res.get("already_active") == 2, str(res))

    # late confirmation: verify u3 after the finale, then re-run the bulk activation
    admin.patch(f"/api/admin/registrations/{reg3_id}/verify", json={"verified": True}, headers={"X-CSRF-Token": admin_csrf})
    r = u3.get("/api/v1/status")
    check("late payment confirmation keeps the membership ACTIVE", (r.json().get("membership") or {}).get("status") == "ACTIVE", r.text[:300])
    r = admin.post("/api/admin/events/season-1/complete", headers={"X-CSRF-Token": admin_csrf})
    res = r.json() if r.status_code == 200 else {}
    check("re-running bulk activation activates the late confirmation", res.get("activated") == 1 and res.get("already_active") == 2, str(res))

    r = u1.get("/api/v1/notifications")
    types = [n["type"] for n in r.json()]
    check("membership-activated notification was created", "membership_activated" in types, str(types))

    # ---------- member directory + profiles ----------
    u1_id = u1.get("/api/v1/auth/me").json()["id"]
    u2_me = u2.get("/api/v1/auth/me").json()
    u3_id = u3.get("/api/v1/auth/me").json()["id"]

    r = u1.get("/api/v1/networking/members")
    check("active member can read the directory", r.status_code == 200, r.text[:200])
    directory = r.json() if r.status_code == 200 else []
    check(
        "directory lists exactly the active members",
        {m.get("user_id") for m in directory} == {u1_id, u2_me["id"], u3_id},
        str([m.get("user_id") for m in directory]),
    )
    check("directory shows businesses, not contact data", "founder2@example.com" not in r.text and "phone" not in r.text)
    check("directory entries carry TGL Verified separately", all("tgl_verified" in m for m in directory))

    r = u1.get("/api/v1/networking/members", params={"q": "Second Founder"})
    hits = r.json() if r.status_code == 200 else []
    check("directory search by name works", len(hits) == 1, str(len(hits)))
    member2_id = hits[0]["member_id"] if hits else ""

    r = u1.get("/api/v1/networking/members", params={"category": "02"})
    hits = r.json() if r.status_code == 200 else []
    check("directory filters by category", len(hits) == 1 and hits[0]["business_name"] == "Biz Two", str(hits)[:200])

    r = u1.get("/api/v1/networking/members", params={"city": "Mumbai"})
    hits = r.json() if r.status_code == 200 else []
    check("directory filters by city", len(hits) == 1 and hits[0]["city"] == "Mumbai", str(hits)[:200])

    # mentoring filter: flag u2's networking profile directly (no P0 edit endpoint)
    async def flag_u2_mentoring() -> None:
        from sqlalchemy import update

        async with SessionLocal() as db:
            await db.execute(
                update(NetworkingProfile).where(NetworkingProfile.user_id == u2_me["id"]).values(open_to_mentoring=True)
            )
            await db.commit()

    asyncio.run(flag_u2_mentoring())
    r = u1.get("/api/v1/networking/members", params={"open_to_mentoring": "true"})
    hits = r.json() if r.status_code == 200 else []
    check("directory filters by open-to-mentoring", len(hits) == 1 and hits[0]["user_id"] == u2_me["id"], str(hits)[:200])

    r = u1.get(f"/api/v1/networking/members/{member2_id}")
    check("active member can view a member profile", r.status_code == 200, r.text[:200])
    detail = r.json() if r.status_code == 200 else {}
    check("member profile shows zero Trust Score (no invented metrics)", detail.get("trust_score") == 0, str(detail.get("trust_score")))
    check("member profile shows zero Growth Points", detail.get("growth_points") == 0, str(detail.get("growth_points")))
    check("member profile hides private contact data", "email" not in r.text and "phone" not in r.text)

    r = u1.get("/api/v1/networking/members/not-a-real-id")
    check("unknown member id 404s", r.status_code == 404, str(r.status_code))

    # ---------- referrals ----------
    r = u1.post(
        "/api/v1/referrals",
        json=rp("no-such-user", "Introduce a packaging supplier for our eco range"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("referral to unknown receiver is refused", r.status_code == 404, str(r.status_code))

    # u4 exists (account only, no membership)
    r = u4.get("/api/v1/auth/me")
    u4_id = r.json().get("id") if r.status_code == 200 else ""
    r = u1.post(
        "/api/v1/referrals",
        json=rp(u4_id, "Introduce a packaging supplier for our eco range"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("referral to a non-active member is refused", r.status_code == 404, str(r.status_code))

    r = u1.post(
        "/api/v1/referrals",
        json=rp(u1_id, "Introduce myself to myself, which is not allowed"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("self-referral is refused", r.status_code == 400, str(r.status_code))

    r = u1.post(
        "/api/v1/referrals",
        json=rp("founder2@example.com", "Introduce a packaging supplier for our eco range"),
    )
    check("referral mutation without CSRF is blocked", r.status_code == 403, str(r.status_code))

    r = u1.post(
        "/api/v1/referrals",
        json=rp(u2_me["id"], "Introduce a packaging supplier for our eco range"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("active member can create a referral", r.status_code == 201, r.text[:300])
    ref_id = r.json().get("id") if r.status_code == 201 else ""

    r = u1.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "REVENUE_GENERATED"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("invalid referral transition is refused", r.status_code == 400, str(r.status_code))

    # a non-participant cannot even see/touch the referral
    r = u3.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "ACCEPTED"},
        headers={"X-CSRF-Token": customer_csrf(u3)},
    )
    check("non-participant cannot transition a referral", r.status_code == 404, str(r.status_code))

    r = u2.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "ACCEPTED"},
        headers={"X-CSRF-Token": customer_csrf(u2)},
    )
    check("receiver can accept the referral", r.status_code == 200, r.text[:200])
    check("acceptance is stamped", (r.json() or {}).get("accepted_at") is not None, r.text[:200])

    r = u1.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "MEETING_DONE"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("one member can no longer set MEETING_DONE by themselves", r.status_code == 400, str(r.status_code))
    confirm_meeting_both(u1, u2, ref_id)
    check("referral reaches MEETING_DONE once both members confirm", u1.get(f"/api/v1/referrals/{ref_id}").json()["status"] == "MEETING_DONE")
    r = u2.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "BUSINESS_CLOSED"},
        headers={"X-CSRF-Token": customer_csrf(u2)},
    )
    check("BUSINESS_CLOSED can no longer be set by a status update", r.status_code == 400, str(r.status_code))
    close_deal(u1, u2, ref_id)
    check("referral reaches BUSINESS_CLOSED through a confirmed closure", u1.get(f"/api/v1/referrals/{ref_id}").json()["status"] == "BUSINESS_CLOSED")
    r = u1.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "REVENUE_GENERATED"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("referral can progress to REVENUE_GENERATED", r.status_code == 200, str(r.status_code))
    r = u1.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "ACCEPTED"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("terminal referral state cannot transition further", r.status_code == 400, str(r.status_code))

    # decline + cancel paths
    r = u1.post(
        "/api/v1/referrals",
        json=rp(u2_me["id"], "Second opinion on pricing for the new wholesale range"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    ref2_id = r.json()["id"]
    r = u2.patch(
        f"/api/v1/referrals/{ref2_id}",
        json={"status": "DECLINED"},
        headers={"X-CSRF-Token": customer_csrf(u2)},
    )
    check("receiver can decline a referral", r.status_code == 200 and r.json()["status"] == "DECLINED", r.text[:200])
    r = u1.patch(
        f"/api/v1/referrals/{ref2_id}",
        json={"status": "ACCEPTED"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("declined referral is terminal", r.status_code == 400, str(r.status_code))

    r = u1.get("/api/v1/referrals")
    check("referral list returns sent and received", r.status_code == 200 and len(r.json()) >= 2, str(len(r.json() or [])))

    # ---------- referral workflow v2: member search ----------
    import time as _time

    H1 = {"X-CSRF-Token": customer_csrf(u1)}
    H2 = {"X-CSRF-Token": customer_csrf(u2)}
    H3 = {"X-CSRF-Token": customer_csrf(u3)}

    def search(c, **params):
        return c.get("/api/v1/networking/members/search", params=params)

    r = new_client().get("/api/v1/networking/members/search")
    check("search requires authentication", r.status_code == 401, str(r.status_code))
    r = search(u4)
    check("search refuses a non-member account", r.status_code == 403, str(r.status_code))
    r = search(u1)
    items = r.json()["items"] if r.status_code == 200 else []
    check("empty search lists suggested members", r.status_code == 200 and len(items) >= 2, r.text[:200])
    check("search never lists the caller", u1_id not in {m["user_id"] for m in items})
    check("search results carry no contact data", not any(k in r.text for k in ("email", "phone", "@example.com")), r.text[:200])
    check("search items expose only recognition fields", set(items[0]) == {"member_id", "user_id", "name", "business_name", "profession", "category", "category_name", "city", "photo_url"}, str(set(items[0])))
    check("search honours the limit and reports more", search(u1, limit=1).json() == {**search(u1, limit=1).json(), "has_more": True} and len(search(u1, limit=1).json()["items"]) == 1)
    r = search(u1, q="second")
    check("search by partial member name", [m["user_id"] for m in r.json()["items"]] == [u2_me["id"]], r.text[:200])
    r = search(u1, q="biz tw")
    check("search by partial business name", [m["business_name"] for m in r.json()["items"]] == ["Biz Two"], r.text[:200])
    r = search(u1, q="food")
    check("search by category name", [m["category"] for m in r.json()["items"]] == ["02"], r.text[:200])
    r = search(u1, q="mumbai")
    check("search by city", [m["business_name"] for m in r.json()["items"]] == ["Biz Two"], r.text[:200])
    r = search(u1, q="FOUNDER")
    check("search by profession is case-insensitive", len(r.json()["items"]) == 2, r.text[:200])
    r = search(u1, q="zzzz-nobody")
    check("search with no match returns an empty list", r.status_code == 200 and r.json() == {"items": [], "has_more": False}, r.text[:200])
    r = search(u1, q="%")
    check("LIKE wildcards in the query are literal", r.json()["items"] == [], r.text[:200])
    r = search(u1, q="x" * 200)
    check("over-long search query is rejected", r.status_code == 422, str(r.status_code))
    r = search(u1, limit=500)
    check("search limit is capped", r.status_code == 422, str(r.status_code))

    async def set_active(uid: str, value: bool) -> None:
        from sqlalchemy import update
        from app.models import User

        async with SessionLocal() as db:
            await db.execute(update(User).where(User.id == uid).values(is_active=value))
            await db.commit()

    asyncio.run(set_active(u3_id, False))
    r = search(u1, q="third")
    check("deactivated members are not searchable", r.json()["items"] == [], r.text[:200])
    r = u1.post("/api/v1/referrals", json=rp(u3_id), headers=H1)
    check("referral to a deactivated member is refused", r.status_code == 404, str(r.status_code))
    asyncio.run(set_active(u3_id, True))

    # ---------- referral workflow v2: creation ----------
    def create(client=u1, headers=None, **kw):
        return client.post("/api/v1/referrals", json=rp(**kw), headers=headers or {"X-CSRF-Token": customer_csrf(client)})

    t0 = _time.perf_counter()
    r = create(receiver_id=u2_me["id"], prospect_name="  Priya   Sharma ", prospect_phone="+91 98765-43210",
               prospect_email="Priya@XYZ-Restaurant.IN", prospect_company="XYZ Restaurant", category="02",
               note="Owner is the decision maker.", prospect_role="Owner", prospect_location="Indiranagar",
               preferred_contact_method="WHATSAPP")
    create_ms = (_time.perf_counter() - t0) * 1000
    v2 = r.json() if r.status_code == 201 else {}
    check("full referral is created", r.status_code == 201, r.text[:400])
    check("referrer is taken from the session", v2.get("giver_user_id") == u1_id and v2.get("my_role") == "giver", str(v2)[:200])
    check("recipient is the chosen member's id", v2.get("receiver_user_id") == u2_me["id"] and v2.get("receiver_business") == "Biz Two", str(v2)[:200])
    check("prospect is stored separately, normalised", (v2.get("prospect_name"), v2.get("prospect_phone"), v2.get("prospect_email")) == ("Priya Sharma", "+919876543210", "priya@xyz-restaurant.in"), str(v2)[:300])
    check("new referral starts as GIVEN with derived quality", v2.get("status") == "GIVEN" and v2.get("quality") == "DIRECT_INTRO", str(v2)[:200])
    check("giver sees no actions except withdrawing", v2.get("allowed_actions") == ["CANCELLED"], str(v2.get("allowed_actions")))
    v2_id = v2.get("id", "")

    r = u2.get(f"/api/v1/referrals/{v2_id}")
    d = r.json() if r.status_code == 200 else {}
    check("recipient can open the referral with prospect details", r.status_code == 200 and d.get("prospect_phone") == "+919876543210" and d.get("my_role") == "receiver", r.text[:200])
    check("recipient may accept or decline", sorted(d.get("allowed_actions", [])) == ["ACCEPTED", "DECLINED"], str(d.get("allowed_actions")))
    r = u3.get(f"/api/v1/referrals/{v2_id}")
    check("IDOR: a third member cannot read the referral", r.status_code == 404, str(r.status_code))
    r = u3.patch(f"/api/v1/referrals/{v2_id}", json={"status": "ACCEPTED"}, headers=H3)
    check("IDOR: a third member cannot update the referral", r.status_code == 404, str(r.status_code))
    r = u3.get("/api/v1/referrals")
    check("a third member's list excludes it", all(x["id"] != v2_id for x in r.json()), r.text[:100])
    r = u2.get("/api/v1/referrals", params={"view": "received"})
    check("list items omit prospect phone and email", r.status_code == 200 and "+919876543210" not in r.text and "priya@xyz" not in r.text)
    r = u1.get(f"/api/v1/referrals/00000000-0000-0000-0000-000000000000")
    check("unknown referral id is a 404", r.status_code == 404, str(r.status_code))

    r = create(receiver_id=u2_me["id"], prospect_phone="98765 43210", prospect_email=None, headers=H1)
    check("duplicate: same prospect to same member is blocked", r.status_code == 409 and r.json()["detail"]["code"] == "duplicate_referral" and r.json()["detail"]["existing_referral_id"] == v2_id, r.text[:300])
    r = create(receiver_id=u2_me["id"], prospect_phone="9123456780", prospect_email="priya@xyz-restaurant.in")
    check("duplicate: same email to same member is blocked", r.status_code == 409, r.text[:200])
    r = create(receiver_id=u3_id, prospect_phone="9876543210")
    check("similar: same prospect to another member asks for review", r.status_code == 409 and r.json()["detail"]["code"] == "possible_duplicate" and r.json()["detail"]["matches"][0]["id"] == v2_id, r.text[:300])
    check("similar-referral warning shows only the caller's own data", "9876543210" not in r.text and u2_me["id"] not in r.text, r.text[:300])
    r = create(receiver_id=u3_id, prospect_phone="9876543210", confirm_duplicate=True)
    check("similar: referrer may continue after reviewing", r.status_code == 201, r.text[:200])
    r = u3.get("/api/v1/referrals", params={"view": "received"})
    check("recipient of a confirmed duplicate is notified normally", r.status_code == 200 and len(r.json()) == 1, r.text[:200])

    async def raw_dup():
        from app.models import BusinessReferral
        from sqlalchemy.exc import IntegrityError

        async with SessionLocal() as db:
            db.add(BusinessReferral(giver_user_id=u1_id, receiver_user_id=u2_me["id"], business_need="x", status="GIVEN", prospect_phone="+919876543210"))
            try:
                await db.commit()
            except IntegrityError:
                return True
        return False

    check("database itself rejects a live duplicate (partial unique index)", asyncio.run(raw_dup()))

    async def concurrent_creates():
        import httpx as _httpx

        # Two identical submissions racing: exactly one may win.
        async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url="http://testserver", cookies=u1.cookies) as ac:
            payload = rp(u3_id, prospect_phone="9000011122", confirm_duplicate=True)
            return await asyncio.gather(*[ac.post("/api/v1/referrals", json=payload, headers=H1) for _ in range(2)])

    codes = sorted(x.status_code for x in asyncio.run(concurrent_creates()))
    check("concurrent identical submissions create exactly one referral", codes == [201, 409], str(codes))

    bad = {
        "missing prospect name": dict(prospect_name=""),
        "one-letter prospect name": dict(prospect_name="P"),
        "numeric-only name": dict(prospect_name="12345"),
        "missing phone": dict(prospect_phone=""),
        "short phone": dict(prospect_phone="12345"),
        "letters in phone": dict(prospect_phone="98765abcde"),
        "repeated-digit phone": dict(prospect_phone="9999999999"),
        "Indian number starting with 1": dict(prospect_phone="1234567890"),
        "invalid email": dict(prospect_email="not-an-email"),
        "description too short": dict(need="Needs website."),
        "description too long": dict(need="x" * 1001),
        "unknown urgency": dict(urgency="URGENT!!"),
        "unknown intro method": dict(intro_method="TELEPATHY"),
        "unknown relationship": dict(relationship="ENEMY"),
        "unknown category": dict(category="99"),
        "consent not given": dict(consent_confirmed=False),
        "forged referrer id": dict(giver_user_id=u2_me["id"]),
        "forged status": dict(status="CONVERTED"),
        "forged referrer name": dict(referrer_name="Someone Else"),
    }
    for label, over in bad.items():
        r = create(receiver_id=u2_me["id"], **over)
        check(f"rejected: {label}", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    r = u1.post("/api/v1/referrals", content=b"{not json", headers={**H1, "Content-Type": "application/json"})
    check("rejected: malformed JSON", r.status_code == 422, str(r.status_code))
    r = u1.post("/api/v1/referrals", json=["a", "list"], headers=H1)
    check("rejected: wrong payload shape", r.status_code == 422, str(r.status_code))
    r = create(receiver_id=u1_id)
    check("rejected: self-referral", r.status_code == 400, str(r.status_code))
    r = create(receiver_id="not-a-real-id")
    check("rejected: invalid recipient id", r.status_code == 404, str(r.status_code))
    r = create(receiver_id=u4_id)
    check("rejected: recipient without Networking access (same answer as unknown id)", r.status_code == 404 and r.json() == create(receiver_id="not-a-real-id").json(), r.text[:200])
    r = create(client=u4, receiver_id=u2_me["id"])
    check("rejected: caller without Networking access", r.status_code == 403, str(r.status_code))
    r = create(client=new_client(), receiver_id=u2_me["id"], headers={})
    check("rejected: unauthenticated caller", r.status_code == 401, str(r.status_code))
    r = u1.post("/api/v1/referrals", json=rp(u2_me["id"]))
    check("rejected: missing CSRF token", r.status_code == 403, str(r.status_code))

    weird = "Café ‘Spice’ <script>alert(1)</script> & “Sons”, \x00\x07 ₹50,000\r\n\r\n\r\n\r\nline two"
    r = create(receiver_id=u2_me["id"], need="Needs help with: " + weird, prospect_name="Zoë O'Brien-Núñez", prospect_company="  Spice & <b>Sons</b>  ", note="  \t spaced \t out  ")
    w = r.json() if r.status_code == 201 else {}
    check("special characters and unicode are accepted", r.status_code == 201, r.text[:200])
    d = u1.get(f"/api/v1/referrals/{w.get('id')}").json() if w else {}
    check("control characters are stripped, excess blank lines collapsed",
          "\x00" not in d.get("opportunity_description", "") and "\x07" not in d.get("opportunity_description", "") and "\n\n\n" not in d.get("opportunity_description", ""), repr(d.get("opportunity_description")))
    check("markup is kept as inert text (escaped on output, not stripped)", "<script>" in d.get("opportunity_description", "") and d.get("note") == "spaced out", repr(d.get("note")))
    r = create(receiver_id=u2_me["id"], need="y" * 1000, prospect_phone="+44 20 7946 0958", prospect_name="Oliver Smith")
    check("1000-character description and international number are accepted", r.status_code == 201 and r.json()["prospect_phone"] == "+442079460958", r.text[:200])
    r = create(receiver_id=u2_me["id"], intro_method="CALL", intro_call_preference="Tuesday after 4pm", prospect_phone="9811122233")
    check("a scheduled call is recorded as a meeting arranged", r.status_code == 201 and r.json()["quality"] == "MEETING_ARRANGED", r.text[:200])
    r = create(receiver_id=u2_me["id"], intro_method="SHARE_DETAILS", need="Short but long enough to pass validation.", prospect_phone="9811122244")
    check("details-only referral is contact-only quality", r.status_code == 201 and r.json()["quality"] == "CONTACT_ONLY", r.text[:200])
    r = create(receiver_id=u2_me["id"], intro_method="ALREADY_KNOWS", prospect_company="Acme", prospect_phone="9811122255", need="Acme needs a full rebrand with new packaging and a refreshed website before their summer launch in June.")
    check("context-rich referral is a warm referral", r.status_code == 201 and r.json()["quality"] == "WARM_REFERRAL", r.text[:200])

    # ---------- notifications + outbox ----------
    async def outbox_rows():
        from sqlalchemy import select
        from app.models import EmailOutbox

        async with SessionLocal() as db:
            return (await db.execute(select(EmailOutbox).where(EmailOutbox.kind == "referral_received"))).scalars().all()

    rows_ob = asyncio.run(outbox_rows())
    check("an email is queued per referral, in the outbox", len(rows_ob) >= 5 and all(x.to_email in ("founder2@example.com", "founder3@example.com") for x in rows_ob), str(len(rows_ob)))
    pending = [x for x in rows_ob if x.html]
    check("queued email carries no prospect phone or email", all("98765" not in (x.html + x.text) and "priya@xyz" not in (x.html + x.text).lower() for x in pending))
    check("queued email escapes user text", all("<script>" not in x.html for x in pending))

    import app.email_service as _es

    async def _boom(*a, **k):
        raise RuntimeError("email provider is down")

    _orig = _es.deliver
    _es.deliver = _boom
    try:
        r = create(receiver_id=u2_me["id"], prospect_phone="9811122266")
    finally:
        _es.deliver = _orig
    check("referral creation does not depend on the email provider", r.status_code == 201, r.text[:200])

    r = u2.get("/api/v1/notifications")
    n = next((x for x in r.json() if x["related_entity_id"] == v2_id), None)
    check("recipient gets an in-app notification naming referrer and prospect", bool(n) and "Test Founder" in n["title"] and "XYZ Restaurant" in n["body"] and n["detail"]["urgency"] == "HOT", str(n)[:300])
    check("notification text omits prospect phone/email", n is not None and "98765" not in (n["body"] + n["title"]) and "@" not in n["body"])

    # ---------- status lifecycle ----------
    def move(client, ref_id, to):
        return client.patch(f"/api/v1/referrals/{ref_id}", json={"status": to}, headers={"X-CSRF-Token": customer_csrf(client)})

    r = move(u1, v2_id, "ACCEPTED")
    check("giver cannot accept their own referral", r.status_code == 403, str(r.status_code))
    r = move(u2, v2_id, "CANCELLED")
    check("recipient cannot withdraw the giver's referral", r.status_code == 403, str(r.status_code))
    r = move(u2, v2_id, "CONTACTED")
    check("invalid jump GIVEN -> CONTACTED is refused", r.status_code == 400, str(r.status_code))
    r = move(u2, v2_id, "CONVERTED")
    check("unknown status is refused", r.status_code == 400, str(r.status_code))
    r = u2.patch(f"/api/v1/referrals/{v2_id}", json={"status": "ACCEPTED", "prospect_phone": "+910000000000"}, headers=H2)
    check("a status update cannot smuggle other fields", r.status_code == 422, str(r.status_code))
    r = move(u2, v2_id, "ACCEPTED")
    check("recipient accepts", r.status_code == 200 and r.json()["status"] == "ACCEPTED", r.text[:200])
    r = move(u2, v2_id, "ACCEPTED")
    check("accepting twice is refused", r.status_code == 400, str(r.status_code))
    r = move(u2, v2_id, "CONTACTED")
    cj = r.json() if r.status_code == 200 else {}
    check("recipient records first contact", r.status_code == 200 and cj.get("contacted_at") and cj.get("last_action_at"), r.text[:200])
    r = move(u1, v2_id, "CLOSED")
    check("giver cannot close on the recipient's behalf", r.status_code == 403, str(r.status_code))
    r = move(u1, v2_id, "MEETING_DONE")
    check("a meeting cannot be recorded by one member alone", r.status_code == 400, r.text[:200])
    confirm_meeting_both(u1, u2, v2_id)
    close_deal(u1, u2, v2_id)
    r = u2.get(f"/api/v1/referrals/{v2_id}")
    check("business won through both members' confirmation", r.status_code == 200 and r.json()["status"] == "BUSINESS_CLOSED", r.text[:200])
    r = move(u2, v2_id, "CLOSED")
    check("converted referral cannot be closed as lost", r.status_code == 400, str(r.status_code))
    r = move(u2, v2_id, "REVENUE_GENERATED")
    check("revenue can be logged", r.status_code == 200 and r.json()["allowed_actions"] == [], r.text[:200])
    r = u1.get("/api/v1/notifications")
    check("giver is notified of progress", sum(1 for x in r.json() if x["related_entity_id"] == v2_id) >= 4, str(len(r.json())))

    lost = create(receiver_id=u2_me["id"], prospect_phone="9811122277").json()["id"]
    move(u2, lost, "ACCEPTED")
    r = move(u2, lost, "CLOSED")
    check("recipient can close a referral that went nowhere", r.status_code == 200 and r.json()["closed_at"], r.text[:200])
    r = move(u2, lost, "MEETING_DONE")
    check("closed referral is terminal", r.status_code == 400, str(r.status_code))
    r = create(receiver_id=u2_me["id"], prospect_phone="9811122277")
    check("a closed referral no longer blocks re-referring the prospect", r.status_code == 201, r.text[:200])
    wd = r.json()["id"]
    r = move(u1, wd, "CANCELLED")
    check("giver can withdraw before acceptance", r.status_code == 200 and r.json()["status"] == "CANCELLED", r.text[:200])

    async def race():
        import httpx as _httpx

        fresh = create(receiver_id=u2_me["id"], prospect_phone="9811122288").json()["id"]
        async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=app), base_url="http://testserver", cookies=u2.cookies) as ac:
            rs = await asyncio.gather(
                ac.patch(f"/api/v1/referrals/{fresh}", json={"status": "ACCEPTED"}, headers=H2),
                ac.patch(f"/api/v1/referrals/{fresh}", json={"status": "DECLINED"}, headers=H2),
            )
        return sorted(x.status_code for x in rs)

    rc = asyncio.run(race())
    check("racing status changes: exactly one wins", rc[0] == 200 and rc[1] in (400, 409), str(rc))

    # ---------- listing, filters, pagination, summary ----------
    r = u2.get("/api/v1/referrals/summary")
    sm = r.json() if r.status_code == 200 else {}
    check("summary counts add up", sm.get("total") == sm.get("sent", 0) + sm.get("received", 0) and sm.get("received", 0) >= 8 and sm.get("sent") == 0, str(sm))
    check("summary groups statuses", sm.get("converted") == 2 and sm.get("by_status", {}).get("REVENUE_GENERATED") == 2, str(sm))
    page1 = u2.get("/api/v1/referrals", params={"view": "received", "limit": 3}).json()
    page2 = u2.get("/api/v1/referrals", params={"view": "received", "limit": 3, "offset": 3}).json()
    check("pagination returns distinct pages", len(page1) == 3 and len(page2) == 3 and not {x["id"] for x in page1} & {x["id"] for x in page2}, f"{len(page1)} {len(page2)}")
    check("sent view excludes received", u2.get("/api/v1/referrals", params={"view": "sent"}).json() == [])
    conv = u2.get("/api/v1/referrals", params={"view": "converted"}).json()
    check("converted view holds only won business", len(conv) == 2 and v2_id in {x["id"] for x in conv} and all(x["status"] in ("BUSINESS_CLOSED", "REVENUE_GENERATED") for x in conv), str(conv)[:200])
    cl = u2.get("/api/v1/referrals", params={"view": "closed"}).json()
    check("closed view holds closed, declined and withdrawn", {x["status"] for x in cl} <= {"CLOSED", "DECLINED", "CANCELLED"} and len(cl) >= 3, str([x["status"] for x in cl]))
    check("stage filter works", all(x["status"] == "GIVEN" for x in u2.get("/api/v1/referrals", params={"stage": "given"}).json()))
    check("bad view is rejected", u2.get("/api/v1/referrals", params={"view": "everything"}).status_code == 422)
    check("page size is capped", u2.get("/api/v1/referrals", params={"limit": 1000}).status_code == 422)

    # ---------- admin reporting ----------
    r = u1.get("/api/admin/referrals/stats")
    check("members cannot read admin referral stats", r.status_code == 401, str(r.status_code))
    r = admin.get("/api/admin/referrals/stats")
    st_a = r.json() if r.status_code == 200 else {}
    check("admin sees referral totals, status mix and conversion", st_a.get("total", 0) >= 9 and st_a.get("converted") == 2 and st_a.get("conversion_rate") is not None and "by_category" in st_a, str(st_a)[:300])
    check("admin stats expose no prospect contact data", "+91" not in r.text and "priya@" not in r.text)

    # ---------- performance ----------
    def timed(fn, n=15):
        xs = []
        for _ in range(n):
            t = _time.perf_counter()
            fn()
            xs.append((_time.perf_counter() - t) * 1000)
        xs.sort()
        return xs[len(xs) // 2], xs[-1]

    s_med, s_max = timed(lambda: search(u1, q="sec"))
    l_med, _ = timed(lambda: u2.get("/api/v1/referrals", params={"limit": 20}))
    print(f"  PERF  member search median {s_med:.0f} ms (max {s_max:.0f}); referral list median {l_med:.0f} ms; referral create {create_ms:.0f} ms")
    check("member search is fast (median < 150 ms)", s_med < 150, f"{s_med:.0f} ms")
    check("referral submit does not wait on email (< 500 ms)", create_ms < 500, f"{create_ms:.0f} ms")

    # ---------- notifications ----------
    r = u1.get("/api/v1/notifications")
    types = [n["type"] for n in r.json()]
    check("giver notified when referral accepted", "referral_accepted" in types, str(types))
    check("status-change notification created", "referral_status_changed" in types, str(types))

    r = u2.get("/api/v1/notifications")
    u2_notifs = r.json()
    types2 = [n["type"] for n in u2_notifs]
    check("receiver notified of referral received", "referral_received" in types2, str(types2))
    unread_before = u2.get("/api/v1/status").json().get("unread_notifications")
    check("unread count reflects notifications", unread_before == sum(1 for n in u2_notifs if n["read_at"] is None), f"{unread_before}")

    first_unread = next((n for n in u2_notifs if n["read_at"] is None), None)
    if first_unread:
        r = u1.post(f"/api/v1/notifications/{first_unread['id']}/read", headers={"X-CSRF-Token": customer_csrf(u1)})
        check("cannot mark another user's notification read", r.status_code == 404, str(r.status_code))
        r = u2.post(f"/api/v1/notifications/{first_unread['id']}/read", headers={"X-CSRF-Token": customer_csrf(u2)})
        check("mark-one-read works", r.status_code == 200 and r.json()["read_at"] is not None, r.text[:200])
    u2.post("/api/v1/notifications/read-all", headers={"X-CSRF-Token": customer_csrf(u2)})
    unread_after = u2.get("/api/v1/status").json().get("unread_notifications")
    check("mark-all-read works", unread_after == 0, str(unread_after))

    # ---------- privacy / role confusion ----------
    r = admin.get("/api/v1/networking/members")
    check("admin session is not a customer session", r.status_code == 401, str(r.status_code))

    admin_token = admin.cookies.get("tgl_session") or ""
    u1.cookies.set("tgl_customer_session", admin_token)
    r = u1.get("/api/v1/auth/me")
    check("admin JWT cannot authenticate as a customer", r.status_code == 401, str(r.status_code))
    u1.cookies.clear()  # drop the injected cookie, then re-establish a real session
    r = u1.post("/api/v1/auth/login", json={"email": "founder1@example.com", "password": PASSWORD})
    check("customer re-login after cookie reset works", r.status_code == 200, r.text[:200])

    r = u2.get("/api/v1/status")
    check("status is scoped to the requesting user", r.json().get("user", {}).get("email") == "founder2@example.com", r.text[:200])

    # ---------- expired membership loses access ----------
    async def expire_u1_membership() -> None:
        from sqlalchemy import select, update

        async with SessionLocal() as db:
            await db.execute(
                update(TGLMembership)
                .where(TGLMembership.user_id == u1_id)
                .values(expires_at=utcnow() - timedelta(days=1))
            )
            await db.commit()

    asyncio.run(expire_u1_membership())
    r = u1.get("/api/v1/networking/members")
    check("registration keeps directory access after membership expiry", r.status_code == 200, str(r.status_code))
    r = u1.post(
        "/api/v1/referrals",
        json=rp(u2_me["id"], "Expired member should not get in to the referrals"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("registration keeps referral access after membership expiry", r.status_code == 201, str(r.status_code))

    async def restore_u1_membership() -> None:
        from sqlalchemy import update

        async with SessionLocal() as db:
            await db.execute(
                update(TGLMembership).where(TGLMembership.user_id == u1_id).values(expires_at=utcnow() + timedelta(days=60))
            )
            await db.commit()

    asyncio.run(restore_u1_membership())

    # ---------- admin deletes an account ----------
    r = admin.get("/api/admin/customers", params={"search": "lockout@example.com"})
    items = r.json().get("items", [])
    check("admin Accounts list returns name and phone", bool(items) and items[0].get("full_name") == "Test User" and items[0].get("phone") == "9876543210", r.text[:300])
    victim_id = items[0]["id"] if items else "missing"
    r = admin.delete(f"/api/admin/customers/{victim_id}")
    check("account delete without CSRF is refused", r.status_code == 403, str(r.status_code))
    r = new_client().delete(f"/api/admin/customers/{victim_id}")
    check("account delete requires an admin session", r.status_code == 401, str(r.status_code))
    r = u1.delete(f"/api/admin/customers/{victim_id}", headers={"X-CSRF-Token": customer_csrf(u1)})
    check("a customer session cannot delete accounts", r.status_code == 401, str(r.status_code))
    r = admin.delete(f"/api/admin/customers/{victim_id}", headers={"X-CSRF-Token": admin_csrf})
    check("admin deletes an account", r.status_code == 204, str(r.status_code))
    r = admin.get("/api/admin/customers", params={"search": "lockout@example.com"})
    check("deleted account leaves the Accounts list", r.json().get("total") == 0, r.text[:200])
    r = admin.delete(f"/api/admin/customers/{victim_id}", headers={"X-CSRF-Token": admin_csrf})
    check("deleting a missing account is 404", r.status_code == 404, str(r.status_code))
    reset("customer-login:testclient")
    r = new_client().post("/api/v1/auth/login", json={"email": "lockout@example.com", "password": PASSWORD})
    check("deleted account can no longer log in", r.status_code == 401, str(r.status_code))

    # ---------- public-form registrant (no membership row) ----------
    r = register_season1(new_client(), email="walkin@example.com", name="Walk In", business="Walk Biz")
    check("anonymous public registration succeeds", r.status_code == 201, r.text[:200])
    walk = new_client()
    verify_email(walk, signup(walk, "walkin@example.com"))
    st = walk.get("/api/v1/status").json()
    check(
        "finale completed: public-form registrant sees an ACTIVE membership with dates",
        st["networking_access"] is True and st["membership"]["status"] == "ACTIVE" and st["membership"]["expires_at"] is not None,
        str(st.get("membership")),
    )
    check("public-form registrant flagged as registered", st["has_registration"] is True, str(st.get("has_registration")))

    # ---------- undo the Grand Finale ----------
    r = admin.get("/api/admin/events/season-1")
    check("finale state reports completed with access count", r.status_code == 200 and r.json()["event"]["completed_at"] is not None and r.json()["members_with_access"] >= 3, r.text[:300])
    r = admin.post("/api/admin/events/season-1/undo-complete")
    check("undo without CSRF is refused", r.status_code == 403, str(r.status_code))
    r = new_client().post("/api/admin/events/season-1/undo-complete")
    check("undo requires an admin session", r.status_code == 401, str(r.status_code))
    r = admin.post("/api/admin/events/season-1/undo-complete", headers={"X-CSRF-Token": admin_csrf})
    res = r.json() if r.status_code == 200 else {}
    check("undo reverts the activated memberships", r.status_code == 200 and res.get("reverted") == 3 and res.get("was_completed") is True, r.text[:300])
    check("undo clears the event completion", res.get("event", {}).get("completed_at") is None, r.text[:300])
    r = u1.get("/api/v1/networking/members")
    check("registered member is locked out again after undo", r.status_code == 403, str(r.status_code))
    st = walk.get("/api/v1/status").json()
    check("public-form registrant is locked and has no membership after undo", st["networking_access"] is False and st["membership"] is None, str(st.get("membership")))
    st = u1.get("/api/v1/status").json()
    check(
        "undo returns membership to PENDING with no dates",
        st["membership"]["status"] == "PENDING" and st["membership"]["starts_at"] is None and st["membership"]["expires_at"] is None and st["networking_access"] is False,
        str(st.get("membership")),
    )
    types = [n["type"] for n in u1.get("/api/v1/notifications").json()]
    check("undo removes the membership-activated notification", "membership_activated" not in types, str(types))
    r = admin.post("/api/admin/events/season-1/undo-complete", headers={"X-CSRF-Token": admin_csrf})
    check("undo twice is a harmless no-op", r.status_code == 200 and r.json().get("reverted") == 0 and r.json().get("was_completed") is False, r.text[:200])
    r = admin.post("/api/admin/events/season-1/complete", headers={"X-CSRF-Token": admin_csrf})
    check("completing again after undo re-activates everyone", r.status_code == 200 and r.json().get("activated") == 3, r.text[:200])
    r = u1.get("/api/v1/networking/members")
    check("member regains access after re-completing", r.status_code == 200, str(r.status_code))
    types = [n["type"] for n in u1.get("/api/v1/notifications").json()]
    check("re-completing leaves exactly one activation notification", types.count("membership_activated") == 1, str(types))

    # ---------- performance budgets: DB round trips per request ----------
    # In production every statement is a network round trip (measured ~90 ms
    # Render->Supabase), so query count IS latency. These caps sit just above
    # today's counts; a regression to per-item lookups fails here.
    from sqlalchemy import event as _event

    def queries(fn):
        n = [0]
        def _count(*_a, **_k):
            n[0] += 1
        _event.listen(engine.sync_engine, "before_cursor_execute", _count)
        try:
            r = fn()
        finally:
            _event.remove(engine.sync_engine, "before_cursor_execute", _count)
        return r, n[0]

    budgets = [
        ("GET /status (every page change)", 4, lambda: u1.get("/api/v1/status")),
        ("GET /auth/session", 1, lambda: u1.get("/api/v1/auth/session")),
        ("GET /networking/members", 4, lambda: u1.get("/api/v1/networking/members")),
        ("GET /notifications", 6, lambda: u1.get("/api/v1/notifications")),
        ("GET /referrals", 6, lambda: u1.get("/api/v1/referrals")),  # +2: meeting confirmations and live closures for the page
        ("GET /networking/needs", 3, lambda: u1.get("/api/v1/networking/needs")),
        ("PUT /profile/personal", 4, lambda: save_personal(u1, full_name="Founder One", city="Bengaluru")),
        # POST /networking/connections: +2 queries since Phase A (the member-pair lock and the history read), was 8
        ("POST /networking/connections", 10, lambda: u2.post("/api/v1/networking/connections", json={"target_user_id": u1_id, "note": "budget"}, headers={"X-CSRF-Token": customer_csrf(u2)})),
    ]
    for label, cap, fn in budgets:
        r, n = queries(fn)
        check(f"perf budget: {label} uses <= {cap} queries", r.status_code < 400 and n <= cap, f"{n} queries, HTTP {r.status_code}")

    # ---------- Argon2 parameters: OWASP minimum, old hashes upgraded on login ----------
    from argon2 import PasswordHasher as _PH

    async def plant_old_hash() -> None:
        from sqlalchemy import update as _update
        from app.models import User as _User
        old = _PH(time_cost=3, memory_cost=64 * 1024, parallelism=2).hash("LegacyPass123!")
        async with SessionLocal() as db:
            await db.execute(_update(_User).where(_User.email == "founder2@example.com").values(password_hash=old))
            await db.commit()

    async def stored_hash(email: str) -> str:
        from sqlalchemy import select as _select
        from app.models import User as _User
        async with SessionLocal() as db:
            return await db.scalar(_select(_User.password_hash).where(_User.email == email))

    check("new password hashes use OWASP Argon2id params (m=19456,t=2,p=1)", "m=19456,t=2,p=1" in asyncio.run(stored_hash("founder1@example.com")), "")
    asyncio.run(plant_old_hash())
    reset("customer-login:testclient")
    r = new_client().post("/api/v1/auth/login", json={"email": "founder2@example.com", "password": "LegacyPass123!"})
    check("account with an old (64 MiB) hash still logs in", r.status_code == 200, r.text[:120])
    check("old hash is upgraded to the new parameters at login", "m=19456,t=2,p=1" in asyncio.run(stored_hash("founder2@example.com")), "")
    reset("customer-login:testclient")
    r = new_client().post("/api/v1/auth/login", json={"email": "founder2@example.com", "password": "LegacyPass123!"})
    check("login still works after the upgrade", r.status_code == 200, r.text[:120])
    reset("customer-login:testclient")
    r = new_client().post("/api/v1/auth/login", json={"email": "founder2@example.com", "password": "wrong-password"})
    check("wrong password still rejected after the upgrade", r.status_code == 401, str(r.status_code))
    st = walk.get("/api/v1/status").json()
    check("public-form registrant is ACTIVE again after re-completing", st["networking_access"] is True and st["membership"]["status"] == "ACTIVE", str(st.get("membership")))
    wtypes = [n["type"] for n in walk.get("/api/v1/notifications").json()]
    check("public-form registrant is notified once that Networking is open", wtypes.count("membership_activated") == 1, str(wtypes))
    admin.post("/api/admin/events/season-1/complete", headers={"X-CSRF-Token": admin_csrf})
    wtypes = [n["type"] for n in walk.get("/api/v1/notifications").json()]
    check("completing twice does not duplicate the notification", wtypes.count("membership_activated") == 1, str(wtypes))

    # ---------- registrant badge + directory reach (public-form registrant) ----------
    r = register_season1(new_client(), email="walkin2@example.com", name="Walk Two", business="Walk Two Biz")
    check("second anonymous registration succeeds", r.status_code == 201, r.text[:200])
    w2 = full_member("walkin2@example.com", name="Walk Two", business="Walk Two Biz", category="04", city="Mysuru")
    st = w2.get("/api/v1/status").json()
    check(
        "unpaid registration does NOT carry the TGL Verified badge",
        st["business"]["tgl_verified"] is False and st["business"]["verified_via_registration"] is False,
        str(st.get("business")),
    )
    w2_reg_id = admin.get("/api/admin/registrations", params={"search": "walkin2@example.com"}).json()["items"][0]["id"]
    r = admin.patch(f"/api/admin/registrations/{w2_reg_id}/verify", json={"verified": True}, headers={"X-CSRF-Token": admin_csrf})
    check("admin verifies the walk-in's payment", r.status_code == 200, r.text[:200])
    st = w2.get("/api/v1/status").json()
    check(
        "payment-verified registrant automatically carries the TGL Verified badge",
        st["business"]["tgl_verified"] is True and st["business"]["verification_status"] == "VERIFIED" and st["business"]["verified_via_registration"] is True,
        str(st.get("business")),
    )
    check("registrant gets a networking profile on arrival", st.get("networking_profile") is not None, str(st.get("networking_profile")))
    r = w2.post("/api/v1/business/verification/start", headers={"X-CSRF-Token": customer_csrf(w2)})
    check("registrant 'start verification' stays VERIFIED (no PENDING review)", r.status_code == 200 and r.json()["verification_status"] == "VERIFIED", r.text[:200])
    w2_id = st["user"]["id"]
    listing = u1.get("/api/v1/networking/members").json()
    w2_row = next((m for m in listing if m["user_id"] == w2_id), None)
    check("public-form registrant appears in the member directory", w2_row is not None, str([m["business_name"] for m in listing]))
    check("directory shows the registrant's TGL Verified badge", bool(w2_row and w2_row["tgl_verified"]), str(w2_row))
    check("directory lists each member once", len({m["user_id"] for m in listing}) == len(listing), str(len(listing)))
    r = u1.get(f"/api/v1/networking/members/{w2_row['member_id'] if w2_row else 'x'}")
    check("registrant's member page opens", r.status_code == 200 and r.json().get("tgl_verified") is True, r.text[:200])
    r = u1.post(
        "/api/v1/referrals",
        json=rp(w2_id, "Packaging partner for a growing food brand"),
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("a member can refer a public-form registrant", r.status_code == 201, r.text[:200])
    r = u1.post("/api/v1/networking/connections", json={"target_user_id": w2_id}, headers={"X-CSRF-Token": customer_csrf(u1)})
    check("a member can connect with a public-form registrant", r.status_code == 201, r.text[:200])
    r = u1.post(
        "/api/v1/networking/referral-requests",
        json={"target_user_id": w2_id, "note": "Looking for a packaging supplier intro"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("a member can ask a registrant for a referral", r.status_code == 204, r.text[:200])
    notes = {n["type"]: n for n in w2.get("/api/v1/notifications").json()}
    u1_name = u1.get("/api/v1/status").json()["personal_profile"]["full_name"]
    conn_n, ref_n, req_n = notes.get("connection_request"), notes.get("referral_received"), notes.get("referral_requested")
    check("connection notification names who sent it", bool(conn_n) and conn_n["actor"]["name"] == u1_name and u1_name in conn_n["title"], str(conn_n)[:300])
    check("connection notification links to the sender's member page", bool(conn_n) and conn_n["actor"]["member_id"] is not None and conn_n["actor"]["business_name"], str(conn_n)[:300])
    check("referral notification carries the business need", bool(ref_n) and ref_n["detail"]["business_need"] == "Packaging partner for a growing food brand" and ref_n["actor"]["name"] == u1_name, str(ref_n)[:300])
    check("referral-request notification names the requester and their note", bool(req_n) and req_n["actor"]["name"] == u1_name and req_n["detail"]["note"] == "Looking for a packaging supplier intro", str(req_n)[:300])
    check("member notifications link to their source entity", all(n and n["related_entity_id"] for n in (conn_n, ref_n, req_n)), "")
    check("notification actor exposes no email or phone", all("email" not in (n or {}).get("actor", {}) and "phone" not in (n or {}).get("actor", {}) for n in (conn_n, ref_n, req_n)), "")
    r = admin.get("/api/admin/customers", params={"search": "walkin2@example.com"})
    check("admin Accounts shows registrant as VERIFIED", r.json()["items"][0]["verification_status"] == "VERIFIED", r.text[:300])
    r = admin.patch(f"/api/admin/registrations/{w2_reg_id}/verify", json={"verified": False}, headers={"X-CSRF-Token": admin_csrf})
    st = w2.get("/api/v1/status").json()
    check("un-verifying the payment removes the badge", r.status_code == 200 and st["business"]["tgl_verified"] is False, str(st.get("business")))
    admin.patch(f"/api/admin/registrations/{w2_reg_id}/verify", json={"verified": True}, headers={"X-CSRF-Token": admin_csrf})

    # ---------- profile edits: links + founder story, nothing wiped ----------
    r = save_business(w2, business_name="Walk Two Biz", category="04", city="Mysuru", founder_story="Started in a garage.", website="walktwo.com", instagram="https://instagram.com/walktwo", linkedin="https://linkedin.com/company/walktwo")
    check("business save accepts founder story and links", r.status_code == 200 and r.json()["founder_story"] == "Started in a garage." and r.json()["website"] == "walktwo.com", r.text[:300])
    r = w2.put("/api/v1/business", json={"business_name": "Walk Two Biz", "category": "04", "description": "We make handcrafted products for everyday use.", "city": "Mysuru", "employee_band": "1-3", "business_age": "lt6", "business_stage": "Early"}, headers={"X-CSRF-Token": customer_csrf(w2)})
    check("saving without the optional fields keeps them (no data wipe)", r.status_code == 200 and r.json()["founder_story"] == "Started in a garage." and r.json()["instagram"] == "https://instagram.com/walktwo", r.text[:300])
    r = save_business(w2, business_name="Walk Two Biz", category="04", city="Mysuru", website="javascript:alert(1)")
    check("non-web link schemes are rejected", r.status_code == 422, str(r.status_code))
    r = save_business(w2, business_name="Walk Two Biz", category="04", city="Mysuru", instagram=None)
    check("an optional link can be cleared explicitly", r.status_code == 200 and r.json()["instagram"] is None, r.text[:200])

    outsider = full_member("outsider@example.com", name="Out Sider", business="Outside Biz")

    # ---------- profile photos ----------
    from PIL import Image as _Image

    def jpeg_with_gps(size=(1200, 900)) -> bytes:
        img = _Image.new("RGB", size, (200, 120, 40))
        exif = _Image.Exif()
        exif[0x8825] = {1: "N", 2: (12.0, 58.0, 0.0), 3: "E", 4: (77.0, 35.0, 0.0)}  # GPS IFD: Bengaluru
        exif[0x010F] = "PhoneMaker"
        out = io.BytesIO()
        img.save(out, format="JPEG", exif=exif)
        return out.getvalue()

    raw = jpeg_with_gps()
    check("test photo really carries GPS EXIF", bool(_Image.open(io.BytesIO(raw)).getexif().get_ifd(0x8825)))
    up = lambda c, data, name="me.jpg", ctype="image/jpeg", csrf=True: c.post(  # noqa: E731
        "/api/v1/profile/photo", files={"photo": (name, io.BytesIO(data), ctype)},
        headers={"X-CSRF-Token": customer_csrf(c)} if csrf else {})
    check("photo upload needs CSRF", up(u1, raw, csrf=False).status_code == 403)
    check("photo upload needs a login", up(new_client(), raw, csrf=False).status_code in (401, 403))
    r = up(u1, raw)
    check("member uploads a profile photo", r.status_code == 200 and "/api/v1/members/" in r.json().get("photo_url", ""), r.text[:200])
    photo_url = r.json().get("photo_url", "")
    st = u1.get("/api/v1/status").json()
    check("status carries the member's photo_url", st["user"].get("photo_url") == photo_url, str(st["user"].get("photo_url")))
    r = u1.get(photo_url)
    check("owner can view their photo", r.status_code == 200 and r.headers["content-type"] == "image/jpeg")
    served = _Image.open(io.BytesIO(r.content))
    check("photo is re-encoded to 512x512 JPEG", served.format == "JPEG" and served.size == (512, 512), str((served.format, served.size)))
    check("all metadata (incl. GPS) is stripped", len(served.getexif()) == 0 and not served.info.get("exif"), str(dict(served.getexif())))
    check("photo response is locked down + cacheable per version", r.headers.get("x-content-type-options") == "nosniff" and "immutable" in r.headers.get("cache-control", "") and "private" in r.headers.get("cache-control", ""))
    check("another member with Networking access can view it", u2.get(photo_url).status_code == 200)
    check("an account without Networking access cannot (404)", outsider.get(photo_url).status_code == 404)
    check("signed-out visitors cannot", new_client().get(photo_url).status_code == 401)
    listing = u2.get("/api/v1/networking/members").json()
    me = next((m for m in listing if m["user_id"] == u1_id), {})
    check("directory shows the photo", me.get("photo_url") == photo_url, str(me.get("photo_url")))
    detail = u2.get(f"/api/v1/networking/members/{me.get('member_id')}").json()
    check("member page shows the photo", detail.get("photo_url") == photo_url)
    u1.post("/api/v1/networking/connections", json={"target_user_id": u2_me["id"], "note": "photo test"}, headers={"X-CSRF-Token": customer_csrf(u1)})
    actors = [n["actor"] for n in u2.get("/api/v1/notifications").json() if n.get("actor") and n["actor"]["user_id"] == u1_id]
    check("notifications show the sender's photo", bool(actors) and actors[0].get("photo_url") == photo_url, str(actors[:1]))

    old_files = set(os.listdir(f"{TMP}/uploads/photos"))
    r = up(u1, PNG_REAL, name="new.png", ctype="image/png")
    new_url = r.json().get("photo_url", "")
    check("replacing the photo changes its versioned URL", r.status_code == 200 and new_url != photo_url, r.text[:120])
    check("the replaced photo file is deleted (no orphans)", len(os.listdir(f"{TMP}/uploads/photos")) == 1 and not (set(os.listdir(f"{TMP}/uploads/photos")) & old_files))
    check("HTML disguised as an image is refused", up(u1, b"<html><script>alert(1)</script>", name="x.png", ctype="image/png").status_code == 415)
    check("a GIF is refused (PNG/JPG/WEBP only)", up(u1, b"GIF89a" + b"\0" * 64, name="x.gif", ctype="image/gif").status_code == 415)
    big_ok = io.BytesIO()
    _Image.frombytes("RGB", (1400, 1400), os.urandom(1400 * 1400 * 3)).save(big_ok, format="PNG")  # ~5.6 MB of noise
    big_ok = big_ok.getvalue()
    mid = io.BytesIO()
    _Image.frombytes("RGB", (1000, 1000), os.urandom(1000 * 1000 * 3)).save(mid, format="PNG")  # ~3 MB
    check("a ~3 MB phone-sized photo is accepted", len(mid.getvalue()) > 2_600_000 and up(u1, mid.getvalue(), name="mid.png", ctype="image/png").status_code == 200, str(len(mid.getvalue())))
    check("over 5 MB is refused", len(big_ok) > 5 * 1024 * 1024 and up(u1, big_ok, name="big.png", ctype="image/png").status_code == 413, str(len(big_ok)))
    bomb = io.BytesIO()
    _Image.new("1", (10000, 10000)).save(bomb, format="PNG")  # 100 MP, tiny file
    check("decompression bomb is refused", up(u1, bomb.getvalue(), name="bomb.png", ctype="image/png").status_code == 415)
    r = u1.delete("/api/v1/profile/photo", headers={"X-CSRF-Token": customer_csrf(u1)})
    check("member can remove their photo", r.status_code == 204 and u1.get("/api/v1/status").json()["user"]["photo_url"] is None)
    check("removed photo is gone (404) and its file deleted", u1.get(new_url).status_code == 404 and os.listdir(f"{TMP}/uploads/photos") == [])
    up(u1, raw)  # keep one for the rest of the run
    st = outsider.get("/api/v1/status").json()
    check("non-registrant has no automatic badge", st["business"]["tgl_verified"] is False and st["business"]["verified_via_registration"] is False, str(st.get("business")))
    outsider_id = st["user"]["id"]
    r = u1.post("/api/v1/networking/connections", json={"target_user_id": outsider_id}, headers={"X-CSRF-Token": customer_csrf(u1)})
    check("non-member cannot be a connection target", r.status_code == 400, str(r.status_code))
    listing = u1.get("/api/v1/networking/members").json()
    check("non-member is not in the directory", all(m["user_id"] != outsider_id for m in listing), "")

    # ---------- connections: request -> accept / decline, withdraw, remove ----------
    H = lambda c: {"X-CSRF-Token": customer_csrf(c)}  # noqa: E731
    u2_id = u2_me["id"]
    pair_of = lambda c, a, b: [x for x in c.get("/api/v1/networking/connections").json() if {x["requester_user_id"], x["target_user_id"]} == {a, b}]  # noqa: E731
    kinds = lambda c, k: [n for n in c.get("/api/v1/notifications").json() if n["type"] == k]  # noqa: E731

    rows = pair_of(u1, u1_id, u2_id)
    check("crossed requests connect the pair (one accepted row, not two pending)", len(rows) == 1 and rows[0]["status"] == "ACCEPTED", str(rows))
    r = u1.post("/api/v1/networking/connections", json={"target_user_id": u2_id}, headers=H(u1))
    check("asking someone you are already connected with is refused", r.status_code == 409 and "already connected" in r.text, r.text[:160])
    check("the member whose request was crossed is told it was accepted", bool(kinds(u2, "connection_accepted")), str([n["title"] for n in u2.get("/api/v1/notifications").json()][:4]))
    check("both members see the connection", len(pair_of(u2, u1_id, u2_id)) == 1)

    r = u2.delete(f"/api/v1/networking/connections/{rows[0]['id']}", headers=H(u2))
    check("either member can remove a connection", r.status_code == 204 and not pair_of(u1, u1_id, u2_id) and not pair_of(u2, u1_id, u2_id), str(r.status_code))

    r = u1.post("/api/v1/networking/connections", json={"target_user_id": u2_id, "note": "hello again"}, headers=H(u1))
    req = r.json()
    check("a fresh request starts pending", r.status_code == 201 and req["status"] == "PENDING" and req["responded_at"] is None, r.text[:200])
    check("the recipient sees it as an invitation", any(x["id"] == req["id"] and x["target_user_id"] == u2_id for x in u2.get("/api/v1/networking/connections").json()))
    check("the sender cannot accept their own request", u1.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "accept"}, headers=H(u1)).status_code == 404)
    check("a third member cannot answer it (404)", w2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "accept"}, headers=H(w2)).status_code == 404)
    check("a third member cannot withdraw it (404)", w2.delete(f"/api/v1/networking/connections/{req['id']}", headers=H(w2)).status_code == 404)
    check("the recipient cannot 'withdraw' it - they decline", u2.delete(f"/api/v1/networking/connections/{req['id']}", headers=H(u2)).status_code == 403)
    check("an unknown request id is a 404", u2.patch("/api/v1/networking/connections/nope", json={"action": "accept"}, headers=H(u2)).status_code == 404)
    check("a bad action is refused", u2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "marry"}, headers=H(u2)).status_code == 422)
    check("answering needs the CSRF header", u2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "accept"}).status_code in (401, 403))

    before = len(u1.get("/api/v1/notifications").json())
    r = u2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "decline"}, headers=H(u2))
    check("declining marks the request declined", r.status_code == 200 and r.json()["status"] == "DECLINED" and r.json()["responded_at"], r.text[:200])
    check("declining is silent (the sender is not notified)", len(u1.get("/api/v1/notifications").json()) == before)
    r = u1.post("/api/v1/networking/connections", json={"target_user_id": u2_id}, headers=H(u1))
    check("a declined request cannot simply be re-sent", r.status_code == 409 and "already sent" in r.text, r.text[:160])

    n_acc = len(kinds(u1, "connection_accepted"))
    r = u2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "accept"}, headers=H(u2))
    check("accepting connects the two members", r.status_code == 200 and r.json()["status"] == "ACCEPTED", r.text[:200])
    got = kinds(u1, "connection_accepted")
    check("the sender is notified of the acceptance, by name", len(got) == n_acc + 1 and got[0]["actor"]["user_id"] == u2_id, str(got[:1]))
    check("accepting twice is a 409, not a second notification", u2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "accept"}, headers=H(u2)).status_code == 409 and len(kinds(u1, "connection_accepted")) == n_acc + 1)
    check("declining an accepted connection is refused", u2.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "decline"}, headers=H(u2)).status_code == 409)
    check("removing it clears both directions", u1.delete(f"/api/v1/networking/connections/{req['id']}", headers=H(u1)).status_code == 204 and not pair_of(u2, u1_id, u2_id))

    r = u1.post("/api/v1/networking/connections", json={"target_user_id": u2_id}, headers=H(u1))
    wid = r.json()["id"]
    check("the sender can withdraw a pending request", u1.delete(f"/api/v1/networking/connections/{wid}", headers=H(u1)).status_code == 204 and not pair_of(u2, u1_id, u2_id))
    r = u1.post("/api/v1/networking/connections", json={"target_user_id": u2_id}, headers=H(u1))
    check("after withdrawing, they can ask again", r.status_code == 201 and r.json()["status"] == "PENDING", r.text[:160])
    r = u2.post("/api/v1/networking/connections", json={"target_user_id": u1_id}, headers=H(u2))
    check("asking someone who already asked you accepts their request", r.status_code == 201 and r.json()["status"] == "ACCEPTED" and r.json()["requester_user_id"] == u1_id, r.text[:200])
    check("...and leaves a single connection row", len(pair_of(u1, u1_id, u2_id)) == 1)
    check("an unauthenticated visitor cannot read connections", new_client().get("/api/v1/networking/connections").status_code == 401)
    check("an account without Networking access cannot answer", outsider.patch(f"/api/v1/networking/connections/{req['id']}", json={"action": "accept"}, headers=H(outsider)).status_code in (403, 404))

    # ---------- password reset signs out existing sessions ----------
    async def plant_reset_token(email: str, raw: str) -> None:
        from sqlalchemy import select as _select
        from app.models import User, UserVerificationToken
        from app.services import token_hash

        async with SessionLocal() as db:
            uid = await db.scalar(_select(User.id).where(User.email == email))
            db.add(UserVerificationToken(user_id=uid, token_hash=token_hash(raw), purpose="PASSWORD_RESET", expires_at=utcnow() + timedelta(minutes=30)))
            await db.commit()

    asyncio.run(plant_reset_token("outsider@example.com", "reset-token-one"))
    asyncio.run(plant_reset_token("outsider@example.com", "reset-token-two"))
    check("outsider session works before reset", outsider.get("/api/v1/auth/me").status_code == 200)
    r = new_client().post("/api/v1/auth/reset-password", json={"token": "reset-token-one", "new_password": "BrandNewPass123!"})
    check("password reset succeeds", r.status_code == 204, r.text[:200])
    check("password reset signs out existing sessions", outsider.get("/api/v1/auth/me").status_code == 401)
    r = new_client().post("/api/v1/auth/reset-password", json={"token": "reset-token-two", "new_password": "AnotherPass123!"})
    check("other outstanding reset links die with the reset", r.status_code == 400, str(r.status_code))
    reset("customer-login:testclient")
    r = new_client().post("/api/v1/auth/login", json={"email": "outsider@example.com", "password": "BrandNewPass123!"})
    check("login works with the new password", r.status_code == 200, r.text[:200])

    # ---------- OTP login ----------
    otp_user = new_client()
    signup(otp_user, "otpuser@example.com")  # never verified via the signup code
    oc = new_client()
    r = oc.post("/api/v1/auth/otp/request", json={"email": "otpuser@example.com"})
    code = r.json().get("dev_otp")
    r = oc.post("/api/v1/auth/otp/verify", json={"email": "otpuser@example.com", "code": code})
    check("OTP login succeeds", r.status_code == 200, r.text[:200])
    check("OTP login proves the email (marks it verified)", r.json().get("email_verified_at") is not None, r.text[:200])
    oc.post("/api/v1/auth/otp/request", json={"email": "otpuser@example.com"})
    codes = []
    for i in range(9):
        reset("otp-verify:testclient")  # simulate attempts spread over many IPs
        codes.append(new_client().post("/api/v1/auth/otp/verify", json={"email": "otpuser@example.com", "code": f"{i:06d}"}).status_code)
    check("OTP guessing is capped per account, not just per IP", codes[-1] == 429, str(codes))
    r = u1.get("/api/v1/networking/members")
    check("restored membership regains access", r.status_code == 200, str(r.status_code))

    # ---------- calendar-month arithmetic (unit) ----------
    jan31 = datetime(2025, 1, 31, 12, 0, tzinfo=timezone.utc)
    check("month-end clamps to Feb 28", add_calendar_months(jan31, 1).day == 28, str(add_calendar_months(jan31, 1)))
    leap = datetime(2024, 1, 31, 12, 0, tzinfo=timezone.utc)
    check("month-end clamps to Feb 29 in a leap year", add_calendar_months(leap, 1).day == 29, str(add_calendar_months(leap, 1)))
    dec15 = datetime(2026, 12, 15, 10, 30, tzinfo=timezone.utc)
    plus3 = add_calendar_months(dec15, 3)
    check("+3 months keeps day and time", (plus3.month, plus3.day, plus3.hour) == (3, 15, 10), str(plus3))

    # ---------- legacy public surface still works ----------
    r = anon.post(
        "/api/registrations",
        data={
            "name": "Legacy Founder",
            "business": "Legacy Biz",
            "email": "legacy@example.com",
            "phone": "9876543210",

            "category": "03",
            "employees": "1-3",
            "age": "lt6",
            "city": "Bengaluru",
            "agree": "true",
            "mediaConsent": "true",
        },
        files={"paymentProof": ("proof.png", io.BytesIO(PNG), "image/png")},
    )
    check("legacy public registration endpoint still works", r.status_code == 201, r.text[:200])
    r = anon.get("/api/categories/availability")
    check("public availability endpoint still works", r.status_code == 200, str(r.status_code))

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print()
    for ok, name in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
