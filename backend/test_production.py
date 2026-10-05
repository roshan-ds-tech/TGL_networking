"""Production-shape checks: what changes between `uvicorn --reload` on a laptop
and the deployed Render + Supabase service.

  * the built site served from the API's origin (routing, 404s, caching,
    security headers, indexability)
  * rate limits that a spoofed X-Forwarded-For cannot dodge
  * payment proofs in a private Supabase Storage bucket (against a local fake
    of the Storage API — the real one needs credentials)
  * Supabase Data API lockdown (RLS + revoked grants), when run on Postgres
  * concurrent duplicate signups resolve to 409, never 500

Run from backend/ after `npm run build` at the repo root:
    .venv/bin/python test_production.py
    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/tgl_test .venv/bin/python test_production.py
"""
from __future__ import annotations

import asyncio
import io
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

TMP = tempfile.mkdtemp(prefix="tgl-prod-")
REPO = pathlib.Path(__file__).resolve().parent.parent
SITE = REPO / "dist"
if not (SITE / "index.html").is_file():
    sys.exit("Build the site first: (cd .. && npm run build)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


STORAGE_PORT = _free_port()
SERVICE_KEY = "sb_secret_test_only_not_a_real_key"

os.environ.update(
    ENVIRONMENT="development",
    SECRET_KEY="test-secret-key-that-is-definitely-long-enough-123456",
    DB_NULL_POOL="true",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{TMP}/test.db",
    UPLOAD_DIR=f"{TMP}/uploads",
    ADMIN_DIST_DIR=f"{TMP}/no-admin",
    SITE_DIST_DIR=str(SITE),
    RESEND_API_KEY="",
    TRUSTED_PROXY_HOPS="1",
    STORAGE_BACKEND="supabase",
    SUPABASE_URL=f"http://127.0.0.1:{STORAGE_PORT}",
    SUPABASE_SERVICE_ROLE_KEY=SERVICE_KEY,
    SUPABASE_STORAGE_BUCKET="payment-proofs",
)

# ---------------------------------------------------------------------------
# A minimal stand-in for Supabase Storage's REST API (the endpoints storage.py
# calls), so the supabase backend is exercised end to end over real HTTP.
from fastapi import FastAPI, Request, Response  # noqa: E402
import uvicorn  # noqa: E402

fake = FastAPI()
BUCKETS: dict[str, dict] = {}
OBJECTS: dict[str, tuple[bytes, str]] = {}
FAIL_UPLOADS = {"on": False}


def _authorised(request: Request) -> bool:
    return request.headers.get("apikey") == SERVICE_KEY


@fake.get("/storage/v1/bucket/{bucket}")
async def get_bucket(bucket: str, request: Request):
    if not _authorised(request):
        return Response(status_code=401)
    if bucket not in BUCKETS:
        return Response(status_code=404)
    return BUCKETS[bucket]


@fake.post("/storage/v1/bucket")
async def create_bucket(request: Request):
    if not _authorised(request):
        return Response(status_code=401)
    body = await request.json()
    BUCKETS[body["id"]] = body
    return {"name": body["id"]}


@fake.post("/storage/v1/object/{bucket}/{name}")
async def put_object(bucket: str, name: str, request: Request):
    if not _authorised(request) or bucket not in BUCKETS:
        return Response(status_code=401)
    if FAIL_UPLOADS["on"]:
        return Response(status_code=500)
    if name in OBJECTS and request.headers.get("x-upsert") != "true":
        return Response(status_code=409)
    OBJECTS[name] = (await request.body(), request.headers.get("content-type", ""))
    return {"Key": f"{bucket}/{name}"}


@fake.get("/storage/v1/object/{bucket}/{name}")
async def get_object(bucket: str, name: str, request: Request):
    if not _authorised(request):
        return Response(status_code=401)
    if name not in OBJECTS:
        return Response(status_code=404)
    data, ctype = OBJECTS[name]
    return Response(content=data, media_type=ctype)


@fake.delete("/storage/v1/object/{bucket}")
async def delete_objects(bucket: str, request: Request):
    if not _authorised(request):
        return Response(status_code=401)
    body = await request.json()
    gone = [{"name": n} for n in body.get("prefixes", []) if OBJECTS.pop(n, None) is not None]
    return gone


server = uvicorn.Server(uvicorn.Config(fake, host="127.0.0.1", port=STORAGE_PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(100):
    if server.started:
        break
    time.sleep(0.05)

# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.config import settings as app_settings  # noqa: E402
from app.models import Admin  # noqa: E402
from app.ratelimit import _buckets  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "CorrectHorse123!"
ADMIN_EMAIL = "admin@tglseason.com"
PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64
results: list[tuple[bool, str]] = []
app_settings.register_max_per_hour = 1000


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((ok, f"{name}{(' — ' + detail) if detail and not ok else ''}"))


async def reset_db() -> None:
    async with engine.begin() as c:
        if c.dialect.name == "postgresql":
            await c.exec_driver_sql("DROP SCHEMA public CASCADE")
            await c.exec_driver_sql("CREATE SCHEMA public")
            # What Supabase does for every new table in `public`: the Data API
            # roles get full grants by default. The app must take them away.
            for role in ("anon", "authenticated"):
                exists = (await c.exec_driver_sql(f"SELECT 1 FROM pg_roles WHERE rolname = '{role}'")).first()
                if not exists:
                    await c.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
                await c.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
                await c.exec_driver_sql(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role}")
        else:
            await c.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def seed_admin() -> None:
    async with SessionLocal() as db:
        db.add(Admin(email=ADMIN_EMAIL, password_hash=hash_password(PASSWORD)))
        await db.commit()


def form(**over) -> dict:
    data = {
        "name": "Prod Test", "business": "Prod Biz", "email": "prod@example.com", "phone": "9876543210",
        "category": "01", "employees": "1-3", "age": "lt6", "agree": "true", "mediaConsent": "true",
    }
    data.update(over)
    return data


def main() -> int:
    asyncio.run(reset_db())
    with TestClient(app) as c:  # runs lifespan: tables, RLS lockdown, bucket
        asyncio.run(seed_admin())

        # ---------------- site served from the API origin ----------------
        r = c.get("/")
        check("homepage serves the built site", r.status_code == 200 and "text/html" in r.headers["content-type"])
        check("homepage carries prerendered content", "The Growth League" in r.text and '<div id="root"></div>' not in r.text)
        check("homepage is indexable (no noindex header)", "x-robots-tag" not in r.headers, r.headers.get("x-robots-tag", ""))
        check("homepage sends a CSP", "default-src 'self'" in r.headers.get("content-security-policy", ""))
        check("homepage HTML is revalidated, not cached stale", r.headers.get("cache-control") == "no-cache")
        check("HEAD / works (uptime monitors)", c.head("/").status_code == 200)
        for path in ("/login", "/signup", "/app/networking", "/app/profile/membership", "/onboarding/business", "/reset-password"):
            r = c.get(path)
            check(f"deep link {path} serves the app shell", r.status_code == 200 and "<html" in r.text.lower(), str(r.status_code))
            check(f"member route {path} is noindex", "noindex" in r.headers.get("x-robots-tag", ""))
        for path in ("/does-not-exist", "/apple", "/app-store", "/index.php"):
            r = c.get(path)
            check(f"unknown path {path} is a real 404", r.status_code == 404, str(r.status_code))
        r = c.get("/api/does-not-exist")
        check("unknown API path is a JSON 404", r.status_code == 404 and r.headers["content-type"].startswith("application/json"))
        asset = next((SITE / "assets").glob("index-*.js")).name
        r = c.get(f"/assets/{asset}")
        check("fingerprinted asset served", r.status_code == 200 and "javascript" in r.headers["content-type"])
        check("fingerprinted asset cached immutably", "immutable" in r.headers.get("cache-control", ""))
        for path in ("/robots.txt", "/sitemap.xml", "/favicon.png", "/logo.png"):
            check(f"{path} served", c.get(path).status_code == 200)
        for path in ("/../backend/.env", "/%2e%2e/%2e%2e/etc/passwd", "/assets/../../backend/app/config.py"):
            r = c.get(path)
            check(f"no file escape via {path}", r.status_code == 404 or "SECRET_KEY" not in r.text, str(r.status_code))
        for path in ("/TGL_Web_App_Project_Proposal_Vertex_Networking.docx", "/website_architecture/00_Executive_Summary_and_Final_Architecture.md"):
            check(f"internal doc not published: {path}", c.get(path).status_code == 404)
        big = io.BytesIO(bytes.fromhex("89504e470d0a1a0a") + b"\0" * (6 * 1024 * 1024))
        r = c.post("/api/registrations", data=form(email="big@example.com"), files={"paymentProof": ("big.png", big, "image/png")})
        check("oversized request refused up front (413)", r.status_code == 413, str(r.status_code))
        # ---------------- DATABASE_URL as pasted from Supabase ----------------
        import ssl as _ssl
        from sqlalchemy.engine import make_url
        from app.database import _normalise_url
        url, args = _normalise_url("postgresql://postgres.ref:Pa@ss!w0rd@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")
        u = make_url(url)
        check("unencoded '@'/'!' in the password parse correctly", (u.username, u.password, u.host, u.database) == ("postgres.ref", "Pa@ss!w0rd", "aws-0-ap-south-1.pooler.supabase.com", "postgres"), str((u.username, u.host)))
        check("Supabase host gets TLS (encrypted, sslmode=require default)", isinstance(args.get("ssl"), _ssl.SSLContext) and args["ssl"].verify_mode == _ssl.CERT_NONE)
        check("pooler-safe: statement caches disabled", args.get("statement_cache_size") == 0 and args.get("prepared_statement_cache_size") == 0)
        u2 = make_url(_normalise_url("postgres://u:p%40ss@db.example.com/x?sslmode=verify-full")[0])
        check("encoded password + libpq params handled", u2.password == "p@ss" and "sslmode" not in str(u2), str(u2))
        # ---------------- free-tier safety: no silent SQLite on Render ----------------
        from app.config import Settings
        base = dict(environment="production", secret_key="k" * 48, storage_backend="supabase",
                    supabase_url="https://x.supabase.co", supabase_service_role_key="test-only")
        try:
            Settings(_env_file=None, database_url="sqlite+aiosqlite:////app/var/tgl.db", **base)
            check("production refuses SQLite when DATABASE_URL is missing on Render", False, "booted")
        except Exception as exc:
            check("production refuses SQLite when DATABASE_URL is missing on Render", "DATABASE_URL" in str(exc), str(exc)[:120])
        try:
            Settings(_env_file=None, database_url="postgresql://u:p@db.example.com/x", **base)
            check("production boots with a Postgres DATABASE_URL", True)
        except Exception as exc:
            check("production boots with a Postgres DATABASE_URL", False, str(exc)[:120])
        rs = Settings(_env_file=None, environment="development", render_external_url="https://tgl-abc.onrender.com")
        check("PUBLIC_ORIGIN unset -> Render's own URL is used", rs.public_origins == ["https://tgl-abc.onrender.com"], str(rs.public_origins))
        rs = Settings(_env_file=None, environment="development", public_origin="", render_external_url="https://tgl-abc.onrender.com")
        check("PUBLIC_ORIGIN left empty -> Render's own URL is used", rs.public_origins == ["https://tgl-abc.onrender.com"], str(rs.public_origins))
        rs = Settings(_env_file=None, environment="development", public_origin="https://tgl.skykeen.in", render_external_url="https://tgl-abc.onrender.com")
        check("explicit PUBLIC_ORIGIN (custom domain) wins", rs.public_origins == ["https://tgl.skykeen.in"], str(rs.public_origins))
        r = c.get("/api/health")
        check("health check", r.status_code == 200 and r.json() == {"status": "ok"})
        check("API responses stay noindex", "noindex" in r.headers.get("x-robots-tag", ""))

        # ---------------- rate limits vs spoofed X-Forwarded-For ----------------
        _buckets.clear()
        codes = [
            c.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "x"},
                headers={"X-Forwarded-For": f"10.9.8.{i}, 203.0.113.7"},  # spoofed left, real right
            ).status_code
            for i in range(7)
        ]
        check("spoofed X-Forwarded-For cannot dodge the login limit", codes[-1] == 429, str(codes))
        _buckets.clear()

        # ---------------- payment proofs in Supabase Storage ----------------
        check("private bucket created on boot", BUCKETS.get("payment-proofs", {}).get("public") is False, str(BUCKETS))
        r = c.post("/api/registrations", data=form(), files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")})
        check("registration with proof succeeds", r.status_code == 201, r.text[:200])
        check("proof stored in the bucket, not on disk", len(OBJECTS) == 1 and not pathlib.Path(f"{TMP}/uploads").exists(), str(list(OBJECTS)))
        stored_name = next(iter(OBJECTS), "")
        check("stored object has the sniffed type", OBJECTS.get(stored_name, (b"", ""))[1] == "image/png")

        c.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        csrf = c.cookies.get("tgl_csrf") or ""
        reg = c.get("/api/admin/registrations").json()["items"][0]
        r = c.get(f"/api/admin/registrations/{reg['id']}/proof")
        check("admin can view the proof from storage", r.status_code == 200 and r.content == PNG, str(r.status_code))
        check("proof response is locked down", r.headers.get("x-content-type-options") == "nosniff" and "sandbox" in r.headers.get("content-security-policy", ""))
        check("proof is not reachable without admin login", TestClient(app).get(f"/api/admin/registrations/{reg['id']}/proof").status_code == 401)

        FAIL_UPLOADS["on"] = True
        r = c.post("/api/registrations", data=form(email="down@example.com"), files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")})
        FAIL_UPLOADS["on"] = False
        check("storage outage -> friendly 503", r.status_code == 503 and "try again" in r.json().get("detail", "").lower(), r.text[:200])
        total = c.get("/api/admin/registrations").json()["total"]
        check("storage outage leaves no half-saved registration", total == 1, str(total))

        r = c.delete(f"/api/admin/registrations/{reg['id']}", headers={"X-CSRF-Token": csrf})
        check("admin delete succeeds", r.status_code == 204, str(r.status_code))
        check("deleting the registration deletes its stored proof", stored_name not in OBJECTS, str(list(OBJECTS)))

        # ---------------- duplicate registrations ----------------
        OBJECTS.clear()
        proof = lambda: {"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")}  # noqa: E731
        r1 = c.post("/api/registrations", data=form(email="dup@example.com", business="Dup Bakes"), files=proof())
        r2 = c.post("/api/registrations", data=form(email="DUP@example.com", business="  dup bakes "), files=proof())
        check("duplicate registration (same email + business) rejected", r1.status_code == 201 and r2.status_code == 409, f"{r1.status_code} {r2.status_code}")
        check("duplicate rejection explains itself", "already registered" in r2.text, r2.text[:200])
        check("rejected duplicate leaves no stored proof", len(OBJECTS) == 1, str(len(OBJECTS)))
        r3 = c.post("/api/registrations", data=form(email="dup@example.com", business="Dup Second Venture"), files=proof())
        check("same founder may register a different business", r3.status_code == 201, r3.text[:200])

        def dup_submit(_: int) -> int:
            return TestClient(app).post(
                "/api/registrations", data=form(email="racer@example.com", business="Racer Co"), files=proof()
            ).status_code

        with ThreadPoolExecutor(max_workers=6) as pool:
            codes = sorted(pool.map(dup_submit, range(6)))
        if engine.dialect.name == "postgresql":
            check("simultaneous duplicate submissions: exactly one accepted", codes.count(201) == 1 and codes.count(409) == 5, str(codes))
        else:
            check("simultaneous duplicate submissions never error", all(code in (201, 409) for code in codes), str(codes))

        # ---------------- concurrent duplicate signups ----------------
        def signup(_: int) -> int:
            return TestClient(app).post(
                "/api/v1/auth/register",
                json={"full_name": "Race Test", "phone": "9876543210", "email": "race@example.com", "password": PASSWORD},
            ).status_code

        with ThreadPoolExecutor(max_workers=6) as pool:
            codes = sorted(pool.map(signup, range(6)))
        check("concurrent duplicate signup: exactly one account", codes.count(201) == 1, str(codes))
        check("concurrent duplicate signup: losers get 409, never 500", all(code in (201, 409) for code in codes), str(codes))

        # ---------------- load: 130 simultaneous submissions ----------------
        # 70 valid entries race for category 02's 40 slots, alongside malformed
        # fields, spoofed files and an empty proof. The database and the bucket
        # must end up agreeing exactly: 40 rows, 40 objects, nothing orphaned.
        OBJECTS.clear()
        _buckets.clear()
        cap = app_settings.slots_per_category

        def submit(i: int) -> int:
            kind = i % 13
            ip = {"X-Forwarded-For": f"198.51.100.{i % 250}"}
            if kind == 11:  # malformed: bad email + phone
                data, files = form(email="not-an-email", phone="12", category="02"), {"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")}
            elif kind == 12:  # spoofed: HTML pretending to be a PNG
                data, files = form(email=f"spoof{i}@example.com", category="02"), {"paymentProof": ("p.png", io.BytesIO(b"<html><script>x</script>"), "image/png")}
            elif kind == 10:  # empty file
                data, files = form(email=f"empty{i}@example.com", category="02"), {"paymentProof": ("p.png", io.BytesIO(b""), "image/png")}
            else:
                data, files = form(email=f"load{i}@example.com", name=f"Load {i}", business=f"Load Biz {i}", category="02"), {"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")}
            return TestClient(app).post("/api/registrations", data=data, files=files, headers=ip).status_code

        with ThreadPoolExecutor(max_workers=16) as pool:
            codes = list(pool.map(submit, range(130)))
        valid = [codes[i] for i in range(130) if i % 13 < 10]
        check("load: no request failed with a server error", all(code < 500 for code in codes), str(sorted(set(codes))))
        check(f"load: exactly {cap} of {len(valid)} racing valid entries accepted", valid.count(201) == cap, f"{valid.count(201)} accepted")
        check("load: the rest are told the category is full (409)", valid.count(409) == len(valid) - cap, str(sorted(set(valid))))
        check("load: malformed and spoofed submissions rejected", all(codes[i] in (400, 409, 415, 422) for i in range(130) if i % 13 >= 10), str([codes[i] for i in range(130) if i % 13 >= 10]))
        rows = c.get("/api/admin/registrations", params={"category": "02", "page_size": 100}).json()
        check("load: database holds exactly the accepted rows", rows["total"] == cap, str(rows["total"]))
        check("load: bucket holds exactly one proof per row (no orphans)", len(OBJECTS) == cap, str(len(OBJECTS)))
        avail = c.get("/api/categories/availability").json()
        cat02 = next((x for x in avail.get("categories", []) if x.get("category") == "02"), None)
        check("load: public availability shows the category full", bool(cat02) and cat02["filled"] == cap == cat02["capacity"], str(cat02))

        # ---------------- Supabase Data API lockdown (Postgres only) ----------------
        if engine.dialect.name == "postgresql":
            async def probe() -> tuple[list, dict]:
                async with engine.connect() as conn:
                    rls = (await conn.exec_driver_sql(
                        "SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"
                    )).all()
                    outcomes = {}
                    for role in ("anon", "authenticated"):
                        await conn.exec_driver_sql(f"SET ROLE {role}")
                        try:
                            await conn.exec_driver_sql("SELECT email, password_hash FROM users")
                            outcomes[role] = "READABLE"
                        except Exception as exc:  # expected: permission denied
                            outcomes[role] = type(exc.orig).__name__ if hasattr(exc, "orig") else type(exc).__name__
                        await conn.rollback()
                await engine.dispose()
                return rls, outcomes

            rls, outcomes = asyncio.run(probe())
            check("every table has RLS enabled", rls and all(on for _, on in rls), str([t for t, on in rls if not on]))
            check("anon key cannot read users", outcomes.get("anon") != "READABLE", str(outcomes))
            check("authenticated role cannot read users", outcomes.get("authenticated") != "READABLE", str(outcomes))
            r = c.get("/api/v1/status")
            check("app itself still reads/writes normally under RLS", c.get("/api/health").status_code == 200)
        else:
            print("  (skipped RLS checks: run with TEST_DATABASE_URL pointing at Postgres)")

    server.should_exit = True
    shutil.rmtree(TMP, ignore_errors=True)
    failed = [m for ok, m in results if not ok]
    for ok, m in results:
        print(("  PASS  " if ok else "  FAIL  ") + m)
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
