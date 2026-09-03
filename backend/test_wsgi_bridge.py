"""Proves the FastAPI app works correctly when driven through a WSGI adapter
— the exact shape PythonAnywhere's free tier requires (no native ASGI serving
on that platform). Uses Werkzeug's test client against the WSGI-wrapped app,
not FastAPI's own ASGI TestClient, so it genuinely exercises the bridge.

Run:  .venv/Scripts/python.exe test_wsgi_bridge.py
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="tgl-wsgi-test-")
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-definitely-long-enough-123456"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TMP}/test.db".replace("\\", "/")
os.environ["UPLOAD_DIR"] = f"{TMP}/uploads"
os.environ["ADMIN_DIST_DIR"] = f"{TMP}/nonexistent"

from a2wsgi import ASGIMiddleware  # noqa: E402
from werkzeug.test import Client  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin  # noqa: E402
from app.security import hash_password  # noqa: E402

EMAIL, PASSWORD = "admin@tglseason.com", "CorrectHorse123!"
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


def multipart_body(fields: dict, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----wsgibridgeboundary"
    parts = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="paymentProof"; '
        f'filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'
    )
    body = "".join(parts).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def check_cold_start() -> None:
    """The scenario that actually bites on a WSGI host: a brand-new database
    with no tables, served by a process where ASGI lifespan never runs.

    Spawned as a subprocess so it gets a clean interpreter and its own engine,
    exactly like PythonAnywhere loading the WSGI file for the first time.
    """
    import subprocess

    fresh = tempfile.mkdtemp(prefix="tgl-coldstart-")
    script = f'''
import os
os.environ.update(
    ENVIRONMENT="development",
    SECRET_KEY="test-secret-key-that-is-definitely-long-enough-123456",
    DATABASE_URL={f"sqlite+aiosqlite:///{fresh}/cold.db".replace(chr(92), "/")!r},
    UPLOAD_DIR={f"{fresh}/uploads"!r},
    ADMIN_DIST_DIR={f"{fresh}/none"!r},
)
# This mirrors deploy/pythonanywhere_wsgi.py exactly.
from app.database import init_db_sync
init_db_sync()
from a2wsgi import ASGIMiddleware
from app.main import app
application = ASGIMiddleware(app)

from werkzeug.test import Client
c = Client(application)
r = c.post("/api/auth/login", json={{"email": "nobody@example.com", "password": "x"}})
print("STATUS", r.status_code)
r2 = c.get("/api/admin/registrations")
print("STATUS2", r2.status_code)
'''
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120, cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        out = proc.stdout
        # 401 (not 500) means the tables exist and the query ran properly.
        check(
            "cold start on empty DB: no 500 from missing tables",
            "STATUS 401" in out,
            f"{out.strip()[:120]} {proc.stderr.strip()[-200:]}",
        )
        check(
            "cold start: subsequent request works in the serving loop",
            "STATUS2 401" in out,
            f"{out.strip()[:120]} {proc.stderr.strip()[-200:]}",
        )
    finally:
        shutil.rmtree(fresh, ignore_errors=True)


def main() -> int:
    asyncio.run(seed())

    # This is the same object PythonAnywhere's WSGI file would expose as
    # `application` — a plain WSGI callable, not an ASGI app.
    wsgi_app = ASGIMiddleware(app)
    client = Client(wsgi_app)

    fields = {
        "name": "Test Founder", "business": "Test Biz", "email": "founder@example.com",
        "phone": "9876543210", "category": "01", "employees": "1-3", "age": "lt6",
        "city": "Bengaluru", "agree": "true", "mediaConsent": "true",
    }
    body, content_type = multipart_body(fields, "proof.png", PNG)
    r = client.post("/api/registrations", data=body, content_type=content_type)
    check("registration works through the WSGI bridge", r.status_code == 201, f"{r.status_code} {r.get_data(as_text=True)[:200]}")

    r = client.get("/api/admin/registrations")
    check("auth gate works through the WSGI bridge", r.status_code == 401, str(r.status_code))

    r = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    check("login works through the WSGI bridge", r.status_code == 200, f"{r.status_code} {r.get_data(as_text=True)[:200]}")
    set_cookie = r.headers.get("Set-Cookie", "")
    check("session cookie set", "tgl_session=" in set_cookie)

    r = client.get("/api/admin/registrations")
    check("authorised list works through the WSGI bridge", r.status_code == 200, str(r.status_code))
    body_json = r.get_json()
    check("registration is visible", body_json is not None and body_json.get("total", 0) >= 1)
    reg_id = body_json["items"][0]["id"] if body_json else None

    csrf_cookie = client.get_cookie("tgl_csrf")
    csrf = csrf_cookie.value if csrf_cookie else None
    check("csrf cookie set", bool(csrf))

    if reg_id and csrf:
        r = client.patch(
            f"/api/admin/registrations/{reg_id}/verify",
            json={"verified": True},
            headers={"X-CSRF-Token": csrf},
        )
        check("verify works through the WSGI bridge", r.status_code == 200, f"{r.status_code} {r.get_data(as_text=True)[:200]}")

        r = client.get(f"/api/admin/registrations/{reg_id}/proof")
        check("proof download works through the WSGI bridge", r.status_code == 200, str(r.status_code))
        check("proof bytes match what was uploaded", r.get_data() == PNG)

    r = client.get("/api/health")
    check("plain GET works through the WSGI bridge", r.status_code == 200 and r.get_json() == {"status": "ok"})

    check_cold_start()

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
