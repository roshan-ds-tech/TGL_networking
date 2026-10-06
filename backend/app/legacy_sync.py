"""Read-only copy of event registrations from the legacy system.

Season 1 registrations are taken by tgl.skykeen.in, whose backend is the
PythonAnywhere deployment of this app's predecessor. That system stays the
source of truth; this module mirrors its registrations into our database so
the member rules that depend on them — Networking access for a registered
email, the TGL Verified badge, slot counts — see real registrations.

How:
  * logs in to the legacy admin API with a dedicated admin account
    (LEGACY_ADMIN_EMAIL / LEGACY_ADMIN_PASSWORD — environment only) and reads
    /api/admin/registrations page by page. It never writes there.
  * upserts each row into `registrations` with source="pythonanywhere"
    (same id), updating fields that changed (e.g. payment verified there);
  * removes our copy of rows deleted there — but only after a COMPLETE,
    successful fetch, so a network error can never wipe registrations;
  * runs every LEGACY_SYNC_SECONDS, at startup, and on demand (kick()) when a
    member with a verified email isn't matched yet — e.g. someone who just
    registered on tgl.skykeen.in and signed up here a minute later.
Payment-proof files stay in the legacy system; the admin dashboard points
there for those rows.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select, true
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import SessionLocal
from .models import Registration

logger = logging.getLogger("tgl.legacy_sync")

SOURCE = "pythonanywhere"
PAGE_SIZE = 100
KICK_COOLDOWN_SECONDS = 60

_wake = asyncio.Event()
_task: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None
_last_run = 0.0
last_result: dict = {}


class LegacyAuthError(Exception):
    """The legacy admin refused our credentials (401/403)."""


class LegacyRateLimited(Exception):
    """The legacy admin is rate-limiting logins (429)."""


# Set after a refused login: stop trying until the process restarts (saving new
# credentials in Render restarts it). Retrying wrong credentials would trip
# the legacy admin's lockout (5 failures -> account locked for 15 minutes).
_auth_failed = False


def enabled() -> bool:
    return bool(settings.legacy_registrations_url and settings.legacy_admin_email and settings.legacy_admin_password)


def kick() -> None:
    """Ask for a sync soon (rate-limited; thread-safe, never blocks)."""
    if not enabled() or _auth_failed or _loop is None or _loop.is_closed():
        return
    if time.monotonic() - _last_run < KICK_COOLDOWN_SECONDS:
        return
    _loop.call_soon_threadsafe(_wake.set)


def _same(a, b) -> bool:
    """Equality that ignores naive-vs-aware datetimes (SQLite returns naive
    UTC; the legacy API sends aware) — otherwise every sync would rewrite
    every verified row."""
    if isinstance(a, datetime) and isinstance(b, datetime):
        a = a if a.tzinfo else a.replace(tzinfo=timezone.utc)
        b = b if b.tzinfo else b.replace(tzinfo=timezone.utc)
    return a == b


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


async def _fetch_all() -> list[dict]:
    base = settings.legacy_registrations_url.rstrip("/")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        r = await client.post(
            f"{base}/api/auth/login",
            json={"email": settings.legacy_admin_email, "password": settings.legacy_admin_password},
        )
        if r.status_code in (401, 403):
            raise LegacyAuthError(f"HTTP {r.status_code}")
        if r.status_code == 429:
            raise LegacyRateLimited("HTTP 429")
        if r.status_code != 200:
            raise RuntimeError(f"legacy admin login failed (HTTP {r.status_code})")
        items, page = [], 1
        while True:
            r = await client.get(f"{base}/api/admin/registrations", params={"page": page, "page_size": PAGE_SIZE})
            r.raise_for_status()
            body = r.json()
            items += body["items"]
            if page >= body.get("pages", 1):
                return items
            page += 1


async def sync_once() -> dict:
    """One full sync. Returns counts; raises on fetch failure (nothing changed)."""
    global _last_run
    _last_run = time.monotonic()
    remote = await _fetch_all()
    by_id = {item["id"]: item for item in remote}
    added = updated = removed = 0
    async with SessionLocal() as db:
        existing = {
            r.id: r
            for r in (await db.execute(select(Registration).where(Registration.id.in_(list(by_id))))).scalars().all()
        } if by_id else {}
        for rid, item in by_id.items():
            fields = {
                "full_name": item["full_name"],
                "business_name": item["business_name"],
                "email": item["email"].lower(),
                "phone": item["phone"],
                "category": item["category"],
                "employees": item["employees"],
                "business_age": item["business_age"],
                "city": item.get("city"),
                "proof_mime": item.get("proof_mime") or "application/octet-stream",
                "proof_bytes": int(item.get("proof_bytes") or 0),
                "agreed_terms": bool(item.get("agreed_terms", True)),
                "media_consent": bool(item.get("media_consent", False)),
                "verified": bool(item.get("verified")),
                "verified_at": _dt(item.get("verified_at")),
            }
            row = existing.get(rid)
            if row is None:
                db.add(Registration(id=rid, source=SOURCE, proof_filename="", created_at=_dt(item["created_at"]), **fields))
                added += 1
            elif row.source == SOURCE:
                changed = False
                for key, value in fields.items():
                    if _same(getattr(row, key), value):
                        continue
                    setattr(row, key, value)
                    changed = True
                updated += changed
            # a "local" row with the same id would be a collision; leave it alone
        with db.no_autoflush:
            stale = (
                await db.execute(
                    select(Registration.id).where(Registration.source == SOURCE, Registration.id.not_in(list(by_id)) if by_id else true())
                )
            ).scalars().all()
        if stale and not by_id:
            # An empty list while we hold copies is more likely an anomaly on
            # the other side than "every registration deleted" — keep them.
            logger.warning("legacy sync: remote returned no registrations; keeping %d local copies", len(stale))
            stale = []
        if stale:
            await db.execute(delete(Registration).where(Registration.id.in_(stale)))
            removed = len(stale)
        try:
            await db.commit()
        except IntegrityError:
            # Another sync inserted the same rows first (e.g. a kick racing the
            # timer). Nothing is lost — the next run reconciles.
            await db.rollback()
            logger.info("legacy registrations sync: concurrent run detected, skipped")
            return {"remote": len(remote), "added": 0, "updated": 0, "removed": 0, "skipped": True}
    if added or updated or removed:
        from .routers.public import invalidate_availability_cache

        invalidate_availability_cache()  # slot counters include these rows
    result = {"remote": len(remote), "added": added, "updated": updated, "removed": removed}
    logger.info("legacy registrations sync: %s", result)
    last_result.clear()
    last_result.update(result, ok=True, at=time.time())
    return result


async def _run() -> None:
    global _auth_failed
    while True:
        wait = settings.legacy_sync_seconds
        try:
            await sync_once()
        except asyncio.CancelledError:
            raise
        except LegacyAuthError as exc:
            _auth_failed = True
            last_result.update(ok=False, at=time.time(), error="login refused")
            logger.error(
                "legacy registrations sync STOPPED: the legacy admin refused the login (%s) for "
                "LEGACY_ADMIN_EMAIL at %s. Check that you can sign in at %s/admin with exactly those "
                "credentials, then save them again in Render (that restarts the sync). Not retrying, "
                "so wrong credentials can't lock that admin account.",
                exc, settings.legacy_registrations_url, settings.legacy_registrations_url.rstrip("/"),
            )
            return
        except LegacyRateLimited:
            wait = max(wait, 900)
            logger.warning("legacy registrations sync: legacy admin is rate-limiting logins; retrying in 15 min")
        except Exception as exc:  # nothing is changed on failure
            logger.warning("legacy registrations sync failed: %s: %s", type(exc).__name__, str(exc)[:200])
            last_result.update(ok=False, at=time.time())
        try:
            await asyncio.wait_for(_wake.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass
        _wake.clear()


def start() -> None:
    global _task, _wake, _loop
    if not enabled():
        return
    _loop = asyncio.get_running_loop()
    _wake = asyncio.Event()
    _task = asyncio.create_task(_run(), name="legacy-registrations-sync")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
