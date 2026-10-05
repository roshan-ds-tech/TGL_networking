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
results: list[tuple[bool, str]] = []

# Several users are signed up below; the default ceiling of 10/hour per IP is
# close enough to matter once helpers re-run, so widen it for the test run.
app_settings.register_max_per_hour = 1000
app_settings.login_max_attempts = 5




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
        json={"receiver_user_id": "no-such-user", "business_need": "Introduce a packaging supplier"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("referral to unknown receiver is refused", r.status_code == 404, str(r.status_code))

    # u4 exists (account only, no membership)
    r = u4.get("/api/v1/auth/me")
    u4_id = r.json().get("id") if r.status_code == 200 else ""
    r = u1.post(
        "/api/v1/referrals",
        json={"receiver_user_id": u4_id, "business_need": "Introduce a packaging supplier"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("referral to a non-active member is refused", r.status_code == 400, str(r.status_code))

    r = u1.post(
        "/api/v1/referrals",
        json={"receiver_user_id": u1_id, "business_need": "Introduce myself to myself"},
        headers={"X-CSRF-Token": customer_csrf(u1)},
    )
    check("self-referral is refused", r.status_code == 400, str(r.status_code))

    r = u1.post(
        "/api/v1/referrals",
        json={"receiver_user_id": "founder2@example.com", "business_need": "Introduce a packaging supplier", "note": "They need eco packaging."},
    )
    check("referral mutation without CSRF is blocked", r.status_code == 403, str(r.status_code))

    r = u1.post(
        "/api/v1/referrals",
        json={"receiver_user_id": u2_me["id"], "business_need": "Introduce a packaging supplier", "note": "They need eco packaging."},
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
    check("referral can progress to MEETING_DONE", r.status_code == 200, str(r.status_code))
    r = u2.patch(
        f"/api/v1/referrals/{ref_id}",
        json={"status": "BUSINESS_CLOSED"},
        headers={"X-CSRF-Token": customer_csrf(u2)},
    )
    check("referral can progress to BUSINESS_CLOSED", r.status_code == 200, str(r.status_code))
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
        json={"receiver_user_id": u2_me["id"], "business_need": "Second opinion on pricing"},
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
        json={"receiver_user_id": u2_me["id"], "business_need": "Expired member should not get in"},
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
        json={"receiver_user_id": w2_id, "business_need": "Packaging partner"},
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
    check("referral notification carries the business need", bool(ref_n) and ref_n["detail"]["business_need"] == "Packaging partner" and ref_n["actor"]["name"] == u1_name, str(ref_n)[:300])
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
    st = outsider.get("/api/v1/status").json()
    check("non-registrant has no automatic badge", st["business"]["tgl_verified"] is False and st["business"]["verified_via_registration"] is False, str(st.get("business")))
    outsider_id = st["user"]["id"]
    r = u1.post("/api/v1/networking/connections", json={"target_user_id": outsider_id}, headers={"X-CSRF-Token": customer_csrf(u1)})
    check("non-member cannot be a connection target", r.status_code == 400, str(r.status_code))
    listing = u1.get("/api/v1/networking/members").json()
    check("non-member is not in the directory", all(m["user_id"] != outsider_id for m in listing), "")

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
