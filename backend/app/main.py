"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from .config import settings
from .observability import timing_middleware
from . import http_client, legacy_sync, outbox
from .database import Base, SessionLocal, engine, install_audit_triggers, install_community_triggers, install_ledger_triggers, lock_down_postgres, sync_schema
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import customer as customer_router
from .routers import referrals as referrals_router
from .routers import closures as closures_router
from .routers import admin_referrals as admin_referrals_router
from .routers import subscriptions as subscriptions_router
from .routers import growth_points as growth_points_router
from .routers import admin_growth_points as admin_growth_points_router
from .routers import renewal as renewal_router
from .routers import community as community_router
from .routers import admin_community as admin_community_router
from . import rewards  # noqa: F401  (registers the shadow-ledger and financial-write guards)
from .routers import public as public_router
from .storage import init_storage
from .subscriptions import ensure_default_plans

logger = logging.getLogger("tgl")
# One plain line per event on stdout (Render captures it). Uvicorn configures
# only its own loggers, so ours need a handler for INFO lines to appear.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.is_production and not settings.resend_api_key:
        # Not fatal (the site still serves), but no signup, login or reset
        # code can be delivered until it is set.
        logger.error("RESEND_API_KEY is not set: account emails cannot be sent in production.")
    if settings.auto_create_schema:
        # Local dev / tests: build the schema on the fly. Production runs
        # migrations BEFORE starting (python -m app.migrate, see Dockerfile),
        # so a cold start does no schema work at all — measured at ~26-41 s
        # of round trips over the Render<->Supabase link.
        await init_storage()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(sync_schema)
            await conn.run_sync(install_audit_triggers)
            await conn.run_sync(install_ledger_triggers)
            await conn.run_sync(install_community_triggers)
            await conn.run_sync(lock_down_postgres)
        async with SessionLocal() as db:
            await ensure_default_plans(db)  # dev/tests only: production gets the plans from migration 0008
            await db.commit()
    outbox.start()  # sends queued emails in the background (outbox.py)
    legacy_sync.start()  # mirrors legacy (PythonAnywhere) registrations, if configured
    yield
    await legacy_sync.stop()
    await outbox.stop()
    await http_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="TGL Season 1 API",
    version="1.0.0",
    lifespan=lifespan,
    # Interactive docs expose the full API surface; keep them off in production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=500)

# The public marketing site reads availability and submits legacy registrations.
# The authenticated Vite app uses HttpOnly customer cookies during local
# development, so credentialed CORS is required for configured public origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.public_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)


# Member-app routes of the SPA (see src/main.jsx's Router). Everything else
# that isn't a real file or an API/admin path is a 404.
_PRODUCT_EXACT = {"/login", "/signup", "/verify-email", "/forgot-password", "/reset-password"}
_PRODUCT_PREFIXES = ("/app", "/onboarding")


def _is_product_path(path: str) -> bool:
    return path in _PRODUCT_EXACT or any(path == p or path.startswith(p + "/") for p in _PRODUCT_PREFIXES)


def _is_private_path(path: str) -> bool:
    return path.startswith(("/api", "/admin")) or _is_product_path(path)


# Largest legitimate request: a payment proof (max_upload_bytes) or a profile
# photo (5 MB, storage.PHOTO_UPLOAD_MAX_BYTES) plus a few form fields.
# Anything bigger is refused before it is read or parsed.
from .storage import PHOTO_UPLOAD_MAX_BYTES  # noqa: E402

_MAX_BODY_BYTES = max(settings.max_upload_bytes, PHOTO_UPLOAD_MAX_BYTES) + 512 * 1024


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length is not None:
        try:
            too_big = int(length) > _MAX_BODY_BYTES
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length."})
        if too_big:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request too large. Payment proofs must be under 2 MB and photos under 5 MB."},
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    # The API, the admin dashboard and the signed-in member app never belong
    # in search results; the public marketing pages served from this same
    # origin do. Sent as a header rather than via robots.txt on purpose:
    # robots.txt would stop the page being *crawled*, which also stops
    # crawlers ever seeing a noindex, so a linked-to admin URL could still
    # surface. This way they can fetch it and are told not to index.
    if _is_private_path(request.url.path):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    # The proof endpoint sets its own stricter CSP; don't clobber it.
    if "Content-Security-Policy" not in response.headers and not request.url.path.startswith(
        ("/admin", "/api")
    ):
        # Public site + member app. Inline style attributes are used
        # throughout the React tree, hence 'unsafe-inline' for styles only;
        # scripts are same-origin modules (the JSON-LD block is data, not
        # executed). Google Fonts is the only third-party origin.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob:; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
    elif "Content-Security-Policy" not in response.headers and request.url.path.startswith(
        "/admin"
    ):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob: data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
    return response


# Outermost middleware (registered last): times the whole request, including
# the other middlewares, and tags it with a request ID.
app.middleware("http")(timing_middleware)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    # Two concurrent requests can both pass an "already exists?" check and then
    # collide on a unique constraint (same signup email, same connection pair).
    # That is a conflict, not a server fault — and the constraint text must
    # not reach the client.
    logger.warning("Integrity conflict on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=409, content={"detail": "This was already submitted. Please refresh and try again."})


def _dependency_unreachable(exc: BaseException) -> bool:
    """The database (or another dependency) could not be reached: refused, reset, timed out, DNS failure, a dropped
    connection. That is a temporary outage, not a bug, so it is answered with 503 + Retry-After, which the frontend
    already treats as "starting up, try again" instead of a broken page. Walks causes and exception groups."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, (ConnectionError, TimeoutError, socket.gaierror)):
            return True
        if isinstance(e, DBAPIError) and e.connection_invalidated:
            return True
        stack.extend([e.__cause__, e.__context__, getattr(e, "orig", None), *getattr(e, "exceptions", ())])
    return False


def _unavailable(request: Request) -> JSONResponse:
    logger.error("Dependency unreachable on %s %s", request.method, request.url.path, exc_info=True)
    return JSONResponse(status_code=503, content={"detail": "The service is temporarily unavailable. Please try again shortly."},
                        headers={"Retry-After": "5", "Cache-Control": "no-store"})


@app.exception_handler(DBAPIError)
async def database_error_handler(request: Request, exc: DBAPIError):
    if _dependency_unreachable(exc):
        return _unavailable(request)
    # SQLSTATE class 22 = "data exception": the client sent a value the database cannot store (PostgreSQL
    # rejects a NUL character in text, an out-of-range number, ...). SQLite stores such values, so only
    # Postgres shows it; it is the client's fault, not a server fault.
    cause = getattr(exc.orig, "__cause__", None) or exc.orig
    if str(getattr(cause, "sqlstate", "") or "").startswith("22"):
        logger.warning("Unstorable value on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=422, content={"detail": "The request contains a value that cannot be stored."})
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log the detail server-side; never leak stack traces to the client.
    if _dependency_unreachable(exc):
        return _unavailable(request)
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth_router.router)
app.include_router(public_router.router)
app.include_router(admin_router.router)
app.include_router(customer_router.router)
app.include_router(referrals_router.router)
app.include_router(closures_router.router)
app.include_router(subscriptions_router.router)
app.include_router(growth_points_router.router)
app.include_router(admin_growth_points_router.router)
app.include_router(renewal_router.router)
app.include_router(subscriptions_router.admin_router)
app.include_router(admin_referrals_router.router)
app.include_router(community_router.router)
app.include_router(admin_community_router.router)


@app.get("/api/health", tags=["ops"])
async def health() -> dict:
    """Liveness only (Render's deploy health check): no database round trip,
    so a database blip can't make Render restart a healthy process."""
    return {"status": "ok"}


@app.api_route("/api/health/db", methods=["GET", "HEAD"], tags=["ops"])
async def health_db() -> JSONResponse:
    """Readiness incl. the database — for an external uptime monitor
    (e.g. UptimeRobot every 5 min). One `SELECT 1`, 5 s cap. Keeps the Render
    service awake and gives Supabase regular database activity. Reveals
    nothing beyond up/down."""
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=5)
        return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})
    except Exception:
        logger.warning("health/db: database check failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"}, headers={"Cache-Control": "no-store"})


# ---- Admin SPA (same-origin so session cookies can stay SameSite=Strict) ----
_admin_dist = Path(settings.admin_dist_dir).resolve()

if _admin_dist.is_dir():
    assets = _admin_dist / "assets"
    if assets.is_dir():
        app.mount("/admin/assets", StaticFiles(directory=assets), name="admin-assets")

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{path:path}", include_in_schema=False)
    async def admin_spa(path: str = "") -> FileResponse:
        index = _admin_dist / "index.html"
        return FileResponse(index, headers={"Cache-Control": "no-store"})
else:  # pragma: no cover - only hit before the dashboard is built

    @app.get("/admin", include_in_schema=False)
    async def admin_not_built() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Admin dashboard is not built. Run: "
                    "cd admin-dashboard && npm install && npm run build"
                )
            },
        )


# ---- Public site + member app (same origin as the API) ----
# Registered last, so every /api and /admin route above wins. In local dev the
# directory doesn't exist and Vite serves the site on its own port instead.
_site_dist = Path(settings.site_dist_dir).resolve()

if _site_dist.is_dir() and (_site_dist / "index.html").is_file():
    _site_index = _site_dist / "index.html"

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def site(path: str = "") -> Response:
        if path.startswith(("api/", "admin/")) or path in {"api", "admin"}:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        candidate = (_site_dist / path).resolve()
        if path and candidate.is_file() and _site_dist in candidate.parents:
            # Vite fingerprints everything under /assets, so those are
            # immutable; other root files (logo, robots.txt…) revalidate daily.
            cache = (
                "public, max-age=31536000, immutable"
                if path.startswith("assets/")
                else "public, max-age=86400"
            )
            return FileResponse(candidate, headers={"Cache-Control": cache})
        known = path == "" or _is_product_path("/" + path)
        # Unknown paths still get the app shell (it renders the branded 404
        # page) but with a real 404 status, so crawlers don't index them.
        return FileResponse(
            _site_index,
            status_code=200 if known else 404,
            headers={"Cache-Control": "no-cache"},
        )
