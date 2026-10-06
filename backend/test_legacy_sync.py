"""Legacy (PythonAnywhere) registration mirroring — app/legacy_sync.py.

Runs against a local stand-in for the legacy admin API (same login + paginated
/api/admin/registrations shape as the real one; also verified against the
real legacy code). Run from backend/:
    .venv/bin/python test_legacy_sync.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid

TMP = tempfile.mkdtemp(prefix="tgl-legacy-")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
os.environ.update(
    ENVIRONMENT="development",
    SECRET_KEY="test-secret-key-that-is-definitely-long-enough-123456",
    DB_NULL_POOL="true",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{TMP}/t.db",
    UPLOAD_DIR=f"{TMP}/uploads",
    ADMIN_DIST_DIR=f"{TMP}/x",
    SITE_DIST_DIR=f"{TMP}/x",
    RESEND_API_KEY="",
    LEGACY_REGISTRATIONS_URL=f"http://127.0.0.1:{PORT}",
    LEGACY_ADMIN_EMAIL="sync-bot@example.com",
    LEGACY_ADMIN_PASSWORD="SyncBotPass123!",
    LEGACY_SYNC_SECONDS="3600",
)

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request, Response  # noqa: E402

legacy = FastAPI()
ROWS: list[dict] = []
STATE = {"fail_list": False}


def _row(email: str, verified: bool = False, category: str = "03") -> dict:
    return {
        "id": str(uuid.uuid4()), "full_name": "Legacy Person", "business_name": f"Biz {email}", "email": email,
        "phone": "9876543210", "category": category, "employees": "1-3", "business_age": "lt6", "city": "Bengaluru",
        "proof_mime": "image/png", "proof_bytes": 100, "agreed_terms": True, "media_consent": True,
        "verified": verified, "verified_at": "2026-10-01T10:00:00Z" if verified else None,
        "verified_by_email": None, "created_at": "2026-09-30T10:00:00Z",
    }


@legacy.post("/api/auth/login")
async def _login(request: Request):
    body = await request.json()
    if body == {"email": "sync-bot@example.com", "password": "SyncBotPass123!"}:
        r = Response('{"id":"a","email":"sync-bot@example.com"}', media_type="application/json")
        r.set_cookie("tgl_session", "ok")
        return r
    return Response(status_code=401)


@legacy.get("/api/admin/registrations")
async def _list(request: Request, page: int = 1, page_size: int = 25):
    if request.cookies.get("tgl_session") != "ok":
        return Response(status_code=401)
    if STATE["fail_list"] and page == 2:
        return Response(status_code=500)  # fails mid-way through paging
    pages = max(1, -(-len(ROWS) // page_size))
    return {"items": ROWS[(page - 1) * page_size: page * page_size], "total": len(ROWS), "page": page, "page_size": page_size, "pages": pages}


server = uvicorn.Server(uvicorn.Config(legacy, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(100):
    if server.started:
        break
    time.sleep(0.05)

from fastapi.testclient import TestClient  # noqa: E402

from app import legacy_sync  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

settings.register_max_per_hour = 1000
results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, f"{name}{(' — ' + detail) if detail and not ok else ''}"))


async def reset_db() -> None:
    async with engine.begin() as c:
        if c.dialect.name == "postgresql":
            await c.exec_driver_sql("DROP SCHEMA public CASCADE")
            await c.exec_driver_sql("CREATE SCHEMA public")
        else:
            await c.run_sync(Base.metadata.drop_all)


def filled(c) -> int:
    return c.get("/api/categories/availability").json()["total_filled"]


def main() -> int:
    asyncio.run(reset_db())
    # 130 rows: more than one page of 100, to exercise paging.
    # Spread over all 10 categories (each holds at most 40).
    ROWS.extend(_row(f"legacy{i}@example.com", category=f"{i % 10 + 1:02d}") for i in range(129))
    ROWS.append(_row("member@example.com", verified=True))
    with TestClient(app) as c:
        # The app syncs on startup by itself (background task).
        for _ in range(100):
            if filled(c) == 130:
                break
            time.sleep(0.1)
        check("startup sync copies every legacy registration (2 pages)", filled(c) == 130, str(filled(c)))
        check("mirrored rows count toward slot availability", filled(c) == 130, str(filled(c)))
        res = asyncio.run(legacy_sync.sync_once())
        check("second sync with no changes is a true no-op (no rewrites)", res["added"] == res["updated"] == res["removed"] == 0, str(res))

        m = TestClient(app)
        r = m.post("/api/v1/auth/register", json={"full_name": "Member", "email": "member@example.com", "phone": "9876543210", "password": "MemberPass123!"})
        m.post("/api/v1/auth/verify-email", data={"token": r.json()["dev_verification_token"]}, headers={"X-CSRF-Token": m.cookies.get("tgl_customer_csrf")})
        st = m.get("/api/v1/status").json()
        check("account with a legacy-registered email is recognised", st["has_registration"] is True)
        check("payment verified in the legacy system → verified here", st["registration_verified"] is True)

        ROWS[0]["verified"] = True
        ROWS[0]["verified_at"] = "2026-10-02T09:00:00Z"
        del ROWS[1]
        res = asyncio.run(legacy_sync.sync_once())
        check("changes in the legacy system sync (1 updated, 1 removed)", res["updated"] == 1 and res["removed"] == 1, str(res))

        STATE["fail_list"] = True
        try:
            asyncio.run(legacy_sync.sync_once())
            check("a failed fetch raises", False)
        except Exception:
            check("a failed fetch changes nothing (no partial deletes)", filled(c) == 129, str(filled(c)))
        STATE["fail_list"] = False

        saved = list(ROWS)
        ROWS.clear()
        asyncio.run(legacy_sync.sync_once())
        check("an empty legacy list never wipes our copies", filled(c) == 129, str(filled(c)))
        ROWS.extend(saved)

        settings.legacy_admin_password = "wrong"
        try:
            asyncio.run(legacy_sync.sync_once())
            check("wrong credentials raise", False)
        except Exception:
            check("wrong legacy credentials: nothing changes", filled(c) == 129)
        settings.legacy_admin_password = "SyncBotPass123!"

    server.should_exit = True
    shutil.rmtree(TMP, ignore_errors=True)
    failed = [m for ok, m in results if not ok]
    for ok, m in results:
        print(("  PASS  " if ok else "  FAIL  ") + m)
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
