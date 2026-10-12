"""Member Growth Points page, the Season-1 finale members' points, and the admin demo-members list.

Targeted. Run:  .venv/bin/python test_growth_points_page.py      TEST_DATABASE_URL=postgresql+asyncpg://... .venv/bin/python test_growth_points_page.py
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys

os.environ["GROWTH_POINTS_SHADOW_MODE"] = "true"
os.environ["GROWTH_POINTS_MEMBER_PREVIEW"] = "true"
import test_phase0 as t0  # noqa: E402
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, app_settings, check, member_client, me, new_client, results, rows, scalar  # noqa: E402
from test_phase1 import referral_payload  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import demo, ratelimit  # noqa: E402
from app.main import app  # noqa: E402


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app):
        return body()


def body() -> int:
    clear = ratelimit._buckets.clear
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}

    # Two Season-1 registrants (finale access, NO subscription / membership row), plus one account that is on no registration at all.
    a, b, outsider = member_client("fin-a@example.com", "Fin Alpha"), member_client("fin-b@example.com", "Fin Beta"), member_client("fin-x@example.com", "Fin Outsider")
    for email, name in (("fin-a@example.com", "Fin Alpha"), ("fin-b@example.com", "Fin Beta")):
        r = new_client().post("/api/registrations", data={"name": name, "business": f"{name} Co", "email": email, "phone": "9876543210", "category": "01", "employees": "1-3", "age": "lt6", "agree": "true", "mediaConsent": "true"},
                              files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")})
        assert r.status_code == 201, r.text
    for reg in admin.get("/api/admin/registrations", params={"page_size": 50}).json()["items"]:
        assert admin.patch(f"/api/admin/registrations/{reg['id']}/verify", json={"verified": True}, headers=AH).status_code == 200
    assert admin.post("/api/admin/events/season-1/complete", headers=AH).status_code == 200
    a_id, b_id = me(a), me(b)
    for c in (a, b):
        assert c.get("/api/v1/status").json()["networking_access"] is True
    check("the finale registrants have access without any subscription or membership row", scalar("select count(*) from subscriptions") == 0 and scalar("select count(*) from tgl_memberships where user_id in (:a, :b)", a=a_id, b=b_id) == 0)

    # ---------------------------------------------------------------- the page before anything happens
    r = a.get("/api/v1/growth-points/overview")
    ov = r.json()
    check("OVERVIEW: a member with access can read it; it explains how points are earned and what does not earn", r.status_code == 200 and len(ov["ways_to_earn"]) >= 5 and len(ov["not_earning"]) >= 1 and ov["limits"]["daily"] == 500 and ov["limits"]["monthly"] == 3000, r.text[:300])
    check("OVERVIEW: before any activity the balance is 0", ov["visible"] is True and ov["balance"]["total"] == 0 and ov["activity"] == [] and ov["earned_by_activity"] == [], str(ov.get("balance")))
    check("OVERVIEW: a finale member has one complimentary 3-month term with the Connect ceiling (3,600)", ov["cycle"] is not None and ov["cycle"]["term_months"] == 3 and ov["cycle"]["ceiling"] == 3600, str(ov.get("cycle")))
    check("OVERVIEW: it needs a session", new_client().get("/api/v1/growth-points/overview").status_code == 401)
    check("OVERVIEW: a member without access is refused", outsider.get("/api/v1/growth-points/overview").status_code in (402, 403), str(outsider.get("/api/v1/growth-points/overview").status_code))

    # ---------------------------------------------------------------- THE BUG: referrals did not raise the points
    clear()
    n0 = scalar("select count(*) from growth_point_ledger")
    r = a.post("/api/v1/referrals", json=referral_payload(b_id), headers=H(a))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    check("CREATING a referral still earns nothing (points come only when it is accepted)", scalar("select count(*) from growth_point_ledger") == n0)
    clear()
    r = b.patch(f"/api/v1/referrals/{rid}", json={"status": "ACCEPTED"}, headers=H(b))
    check("the recipient accepts", r.status_code == 200, r.text[:200])
    pa = int(scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where member_id = :m and event_type = 'REFERRAL_ACCEPTED'", m=a_id))
    pb = int(scalar("select coalesce(sum(points_delta), 0) from growth_point_ledger where member_id = :m and event_type = 'REFERRAL_ACCEPTED'", m=b_id))
    check("FIX: an accepted referral now earns points for a Season-1 finale member (referrer 30, recipient 15)", (pa, pb) == (30, 15), f"{pa}, {pb}")
    ov = a.get("/api/v1/growth-points/overview").json()
    check("OVERVIEW: the balance, the by-activity breakdown and the feed show it", ov["balance"]["total"] == 30 and ov["earned_by_activity"] == [{"key": "REFERRAL_ACCEPTED", "title": ov["earned_by_activity"][0]["title"], "times": 1, "points": 30}]
          and len(ov["activity"]) == 1 and ov["activity"][0]["points"] == 30 and ov["cycle"]["earned"] == 30, str(ov)[:400])
    check("OVERVIEW: it never contains another member's id, email or internal rule trace", b_id not in str(ov) and "fin-b" not in str(ov) and "rule_version" not in str(ov) and "idempotency" not in str(ov))
    check("exactly one cycle per member (the complimentary term is not duplicated)", scalar("select count(*) from growth_point_cycles where member_id = :m", m=a_id) == 1)
    check("nothing financial changed: no invoice, payment or discount was created", scalar("select count(*) from invoices") == 0 and scalar("select count(*) from payments") == 0)

    # ---------------------------------------------------------------- visibility
    app_settings.growth_points_member_preview = False
    off = a.get("/api/v1/growth-points/overview").json()
    check("PREVIEW OFF: the page explains how it works but shows none of the member's numbers", off["visible"] is False and "balance" not in off and "activity" not in off and len(off["ways_to_earn"]) >= 5 and off["message"])
    app_settings.growth_points_member_preview = True

    # ---------------------------------------------------------------- admin: demo members
    dm = admin.get("/api/admin/growth-points/demo-members")
    check("ADMIN DEMO LIST: works outside production; with none seeded it says how to create them", dm.status_code == 200 and dm.json()["enabled"] is True and dm.json()["items"] == [] and "seed_demo_members" in dm.json()["how_to_create"], dm.text[:300])
    check("ADMIN DEMO LIST: needs an admin session", new_client().get("/api/admin/growth-points/demo-members").status_code == 401 and a.get("/api/admin/growth-points/demo-members").status_code in (401, 403))

    async def mk():
        from app.database import SessionLocal
        from app.models import User
        from app.security import hash_password
        async with SessionLocal() as s:
            s.add(User(email="demo-01@demo.example.com", full_name="Demo One", password_hash=hash_password(demo.DEMO_PASSWORD), email_verified_at=__import__("app.models", fromlist=["utcnow"]).utcnow()))
            await s.commit()
    asyncio.run(mk())
    item = admin.get("/api/admin/growth-points/demo-members").json()["items"]
    check("ADMIN DEMO LIST: shows each synthetic member with email and the shared local-only password; genuine members are never listed",
          len(item) == 1 and item[0]["email"] == "demo-01@demo.example.com" and item[0]["password"] == demo.DEMO_PASSWORD and all("fin-" not in i["email"] for i in item), str(item)[:300])
    prod = app_settings.environment
    object.__setattr__(app_settings, "environment", "production")
    try:
        pr = admin.get("/api/admin/growth-points/demo-members")
    finally:
        object.__setattr__(app_settings, "environment", prod)
    check("ADMIN DEMO LIST: in production it returns nothing and never a password", pr.status_code == 200 and pr.json()["enabled"] is False and pr.json()["items"] == [] and demo.DEMO_PASSWORD not in pr.text, pr.text[:200])

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
