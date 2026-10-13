"""Resilience: when the database can not be reached, the API answers 503 + Retry-After (a temporary outage the frontend already treats as
"starting up, try again"), never a stack trace, never a misleading 500, and the liveness / readiness probes tell the truth.

Run:  .venv/bin/python test_resilience.py        (no database needed: it points the app at a closed local port on purpose)
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="tgl-resilience-")
with socket.socket() as s_:                       # a port that is certainly closed: bind, read the number, release it
    s_.bind(("127.0.0.1", 0))
    CLOSED_PORT = s_.getsockname()[1]
os.environ.update(ENVIRONMENT="development", SECRET_KEY="test-secret-key-that-is-definitely-long-enough-123456", UPLOAD_DIR=f"{TMP}/uploads",
                  DATABASE_URL=f"postgresql+asyncpg://nobody@127.0.0.1:{CLOSED_PORT}/nothing", AUTO_CREATE_SCHEMA="false", DB_NULL_POOL="true",
                  RESEND_API_KEY="", LEGACY_REGISTRATIONS_URL="", ADMIN_DIST_DIR=f"{TMP}/x", SITE_DIST_DIR=f"{TMP}/x")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import _dependency_unreachable, app  # noqa: E402
from sqlalchemy.exc import DBAPIError, OperationalError  # noqa: E402

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), name + (f" — {detail}" if detail and not ok else "")))


def main() -> int:
    c = TestClient(app, raise_server_exceptions=False)
    live, ready = c.get("/api/health"), c.get("/api/health/db")
    check("liveness /api/health stays 200 (the process is up)", live.status_code == 200)
    check("readiness /api/health/db says 503 'unavailable' when the database is unreachable", ready.status_code == 503 and ready.json() == {"status": "unavailable"}, ready.text)
    for method, path, body in (("GET", "/api/categories/availability", None), ("POST", "/api/v1/auth/login", {"email": "a@example.com", "password": "Wrong-password-123"})):
        r = c.request(method, path, json=body)
        check(f"{method} {path}: 503 with Retry-After (temporary outage), not 500", r.status_code == 503 and r.headers.get("retry-after") == "5", f"{r.status_code} {r.text[:120]}")
        check(f"{method} {path}: the body is generic: no stack trace, errno, host, port or driver name", not any(x in r.text for x in ("Traceback", "Errno", "127.0.0.1", str(CLOSED_PORT), "asyncpg", "Connection refused")), r.text[:200])
    # classification is narrow: only reachability problems become 503
    check("a refused / reset / timed-out connection is classified as an outage", all(_dependency_unreachable(e) for e in (ConnectionRefusedError(), ConnectionResetError(), TimeoutError(), socket.gaierror())))
    wrapped = OperationalError("SELECT 1", {}, ConnectionRefusedError())
    check("an OperationalError caused by a refused connection is an outage", _dependency_unreachable(wrapped))
    check("ordinary bugs and data errors are NOT hidden as outages (they stay 500 / 422)", not any(_dependency_unreachable(e) for e in (ValueError("x"), KeyError("k"), DBAPIError("x", {}, ValueError("bad value")))))
    failed = [n for ok, n in results if not ok]
    for ok, n in results:
        print(("  PASS  " if ok else "  FAIL  ") + n)
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
