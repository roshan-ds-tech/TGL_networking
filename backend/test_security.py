"""End-to-end security + behaviour checks.

Run:  .venv/Scripts/python.exe test_security.py

Uses a throwaway SQLite DB and upload dir so it never touches real data.
"""
from __future__ import annotations

import asyncio
import io
import os
import pathlib
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="tgl-test-")
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-definitely-long-enough-123456"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP}/test.db".replace("\\", "/")
os.environ["UPLOAD_DIR"] = f"{TMP}/uploads"
os.environ["ADMIN_DIST_DIR"] = f"{TMP}/nonexistent"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin  # noqa: E402
from app.security import CSRF_COOKIE, SESSION_COOKIE, hash_password  # noqa: E402

PASSWORD = "CorrectHorse123!"
EMAIL = "admin@tglseason.com"

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
results: list[tuple[bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((condition, f"{name}{(' — ' + detail) if detail and not condition else ''}"))


async def seed() -> None:
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        db.add(Admin(email=EMAIL, password_hash=hash_password(PASSWORD)))
        await db.commit()
    await engine.dispose()


def form(**over) -> dict:
    data = {
        "name": "Test Founder",
        "business": "Test Biz",
        "email": "founder@example.com",
        "phone": "9876543210",
        "category": "01",
        "employees": "1-3",
        "age": "lt6",
        "city": "Bengaluru",
        "agree": "true",
        "mediaConsent": "true",
    }
    data.update(over)
    return data


def main() -> int:
    asyncio.run(seed())

    with TestClient(app) as c:
        # ---------- public registration ----------
        r = c.post(
            "/api/registrations",
            data=form(),
            files={"paymentProof": ("proof.png", io.BytesIO(PNG), "image/png")},
        )
        check("public registration accepts valid submission", r.status_code == 201, r.text[:200])

        # server-side validation must not trust the client
        r = c.post(
            "/api/registrations",
            data=form(phone="123"),
            files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")},
        )
        check("rejects bad phone server-side", r.status_code == 422, str(r.status_code))

        r = c.post(
            "/api/registrations",
            data=form(category="99"),
            files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")},
        )
        check("rejects out-of-range category", r.status_code == 422, str(r.status_code))

        r = c.post(
            "/api/registrations",
            data=form(mediaConsent="false"),
            files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")},
        )
        check("rejects missing media consent", r.status_code == 422, str(r.status_code))

        # content-type spoofing: declares PNG, bytes are a script
        r = c.post(
            "/api/registrations",
            data=form(),
            files={"paymentProof": ("x.png", io.BytesIO(b"<?php system($_GET[0]); ?>"), "image/png")},
        )
        check("blocks spoofed content-type upload", r.status_code == 415, str(r.status_code))

        # ---------- auth ----------
        r = c.get("/api/admin/registrations")
        check("admin list requires auth", r.status_code == 401, str(r.status_code))

        r = c.get("/api/admin/stats")
        check("admin stats requires auth", r.status_code == 401, str(r.status_code))

        r = c.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-password"})
        check("rejects wrong password", r.status_code == 401, str(r.status_code))

        r = c.post("/api/auth/login", json={"email": "nobody@nowhere.example", "password": "x"})
        check("unknown user gives same 401", r.status_code == 401, str(r.status_code))
        check(
            "no user-enumeration in message",
            "Invalid email or password" in r.text,
            r.text[:120],
        )

        r = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        check("valid login succeeds", r.status_code == 200, r.text[:200])

        cookies = r.cookies
        check("session cookie is HttpOnly", "httponly" in r.headers.get("set-cookie", "").lower())
        check(
            "session cookie is SameSite=Strict",
            "samesite=strict" in r.headers.get("set-cookie", "").lower(),
        )
        csrf = c.cookies.get(CSRF_COOKIE)
        check("csrf cookie issued", bool(csrf))

        # password must never come back in any response
        check("login response omits password hash", "password_hash" not in r.text and "$argon2" not in r.text)

        # ---------- authorised reads ----------
        r = c.get("/api/admin/registrations")
        check("authorised list works", r.status_code == 200, r.text[:200])
        body = r.json()
        check("list returns the seeded registration", body["total"] >= 1, str(body.get("total")))
        reg_id = body["items"][0]["id"]

        r = c.get("/api/admin/stats")
        check("stats works", r.status_code == 200 and "by_category" in r.text)

        # ---------- CSRF ----------
        r = c.patch(f"/api/admin/registrations/{reg_id}/verify", json={"verified": True})
        check("mutation without CSRF header is blocked", r.status_code == 403, str(r.status_code))

        r = c.patch(
            f"/api/admin/registrations/{reg_id}/verify",
            json={"verified": True},
            headers={"X-CSRF-Token": "forged-value"},
        )
        check("mutation with forged CSRF is blocked", r.status_code == 403, str(r.status_code))

        r = c.patch(
            f"/api/admin/registrations/{reg_id}/verify",
            json={"verified": True},
            headers={"X-CSRF-Token": csrf},
        )
        check("verify with valid CSRF succeeds", r.status_code == 200, r.text[:200])
        check("verify flag persisted", r.json()["verified"] is True)
        check("verify records who did it", r.json()["verified_by_email"] == EMAIL)

        r = c.patch(
            f"/api/admin/registrations/{reg_id}/verify",
            json={"verified": False},
            headers={"X-CSRF-Token": csrf},
        )
        check("un-verify works (mistake recovery)", r.json()["verified"] is False)

        # ---------- proof access control ----------
        r = c.get(f"/api/admin/registrations/{reg_id}/proof")
        check("proof served to authed admin", r.status_code == 200, str(r.status_code))
        check("proof sends nosniff", r.headers.get("x-content-type-options") == "nosniff")
        check("proof is not cached", "no-store" in r.headers.get("cache-control", ""))

        # path traversal via the id parameter
        for probe in ["../../../etc/passwd", "..%2f..%2fetc%2fpasswd", "....//....//x"]:
            rr = c.get(f"/api/admin/registrations/{probe}/proof")
            check(f"path traversal blocked ({probe[:18]})", rr.status_code in (404, 400, 422), str(rr.status_code))

        # SQL injection probes through the search filter
        for probe in ["' OR '1'='1", "'; DROP TABLE registrations;--", "%' UNION SELECT 1--"]:
            rr = c.get("/api/admin/registrations", params={"search": probe})
            ok = rr.status_code == 200 and rr.json()["total"] == 0
            check(f"SQLi neutralised ({probe[:16]})", ok, f"{rr.status_code} {rr.text[:80]}")

        # table still intact after injection attempts
        rr = c.get("/api/admin/registrations")
        check("table intact after SQLi probes", rr.status_code == 200 and rr.json()["total"] >= 1)

        # ---------- delete a registration ----------
        # Create a throwaway row so the checks below don't consume the seeded one.
        r = c.post(
            "/api/registrations",
            data=form(email="deleteme@example.com", business="Delete Me Ltd"),
            files={"paymentProof": ("proof.png", io.BytesIO(PNG), "image/png")},
        )
        check("registration created for delete test", r.status_code == 201, r.text[:200])

        rows = c.get("/api/admin/registrations", params={"search": "delete me"}).json()
        del_id = rows["items"][0]["id"] if rows.get("items") else None
        check("delete-test row is findable", del_id is not None)

        # The proof file must exist on disk before we assert it gets removed.
        uploads = pathlib.Path(TMP) / "uploads"
        before = {p.name for p in uploads.iterdir()} if uploads.is_dir() else set()

        # Auth and CSRF are both required, exactly like the verify mutation.
        bare = TestClient(app)
        r = bare.delete(f"/api/admin/registrations/{del_id}")
        check("delete rejected without auth", r.status_code == 401, str(r.status_code))

        r = c.delete(f"/api/admin/registrations/{del_id}", headers={"X-CSRF-Token": "wrong"})
        check("delete rejected with forged CSRF", r.status_code == 403, str(r.status_code))

        r = c.delete(
            f"/api/admin/registrations/{del_id}",
            headers={"X-CSRF-Token": c.cookies.get("tgl_csrf", "")},
        )
        check("delete succeeds with valid CSRF", r.status_code == 204, str(r.status_code))

        rows = c.get("/api/admin/registrations", params={"search": "delete me"}).json()
        check("deleted row is gone from the list", rows.get("total") == 0, str(rows.get("total")))

        r = c.get(f"/api/admin/registrations/{del_id}/proof")
        check("deleted row's proof 404s", r.status_code == 404, str(r.status_code))

        after = {p.name for p in uploads.iterdir()} if uploads.is_dir() else set()
        check(
            "deleting a row removes its proof file from disk",
            len(after) == len(before) - 1,
            f"before={len(before)} after={len(after)}",
        )

        r = c.delete(
            f"/api/admin/registrations/{del_id}",
            headers={"X-CSRF-Token": c.cookies.get("tgl_csrf", "")},
        )
        check("deleting an already-deleted row 404s", r.status_code == 404, str(r.status_code))

        # A traversal-shaped id must not reach the filesystem.
        r = c.delete(
            "/api/admin/registrations/..%2f..%2fetc%2fpasswd",
            headers={"X-CSRF-Token": c.cookies.get("tgl_csrf", "")},
        )
        check("delete with traversal-shaped id is refused", r.status_code == 404, str(r.status_code))

        # ---------- session invalidation ----------
        r = c.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        check("logout succeeds", r.status_code == 204, str(r.status_code))
        r = c.get("/api/admin/registrations")
        check("session rejected after logout", r.status_code == 401, str(r.status_code))

        # tampered JWT must not authenticate
        c.cookies.set(SESSION_COOKIE, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.bogus")
        r = c.get("/api/admin/registrations")
        check("forged JWT rejected", r.status_code == 401, str(r.status_code))
        c.cookies.clear()

        # ---------- brute force ----------
        codes = [
            c.post("/api/auth/login", json={"email": EMAIL, "password": f"bad{i}"}).status_code
            for i in range(8)
        ]
        check("login rate limiting kicks in", 429 in codes, str(codes))

        # ---------- public slot availability ----------
        # Aggregate counts are intentionally public; registrant data must not be.
        r = c.get("/api/categories/availability")
        check("availability is readable without auth", r.status_code == 200, r.text[:200])

        body = r.json() if r.status_code == 200 else {}
        cats = body.get("categories", [])
        check("availability lists all 10 categories", len(cats) == 10, str(len(cats)))
        check(
            "availability covers every category code",
            {c_["category"] for c_ in cats} == {f"{i:02d}" for i in range(1, 11)},
        )
        check(
            "availability counts the seeded registration",
            any(c_["category"] == "01" and c_["filled"] >= 1 for c_ in cats),
            str(cats[:1]),
        )
        check(
            "availability totals are consistent",
            body.get("total_filled") == sum(c_["filled"] for c_ in cats)
            and body.get("total_capacity") == sum(c_["capacity"] for c_ in cats),
        )
        check(
            "availability never exceeds capacity",
            all(c_["filled"] <= c_["capacity"] for c_ in cats),
        )
        # The whole point of a public aggregate endpoint is that it leaks nothing else.
        raw = r.text.lower()
        check(
            "availability leaks no registrant data",
            not any(t in raw for t in ("founder@example.com", "test biz", "9876543210", "proof")),
        )

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
