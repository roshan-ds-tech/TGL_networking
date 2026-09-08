"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine, sync_schema
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import public as public_router
from .storage import upload_root

logger = logging.getLogger("tgl")


@asynccontextmanager
async def lifespan(_: FastAPI):
    upload_root()
    Path(settings.upload_dir).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(sync_schema)
    yield
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

# Only the public marketing site needs cross-origin access: POST to submit a
# registration, GET to read the public slot-availability counters. The admin SPA
# is served same-origin, so it needs no CORS grant.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.public_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    # The proof endpoint sets its own stricter CSP; don't clobber it.
    if "Content-Security-Policy" not in response.headers and request.url.path.startswith(
        "/admin"
    ):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob: data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Log the detail server-side; never leak stack traces to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(auth_router.router)
app.include_router(public_router.router)
app.include_router(admin_router.router)


@app.get("/api/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok"}


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
