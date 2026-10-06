"""Email outbox: enqueue in the request's transaction, send in the background.

Why: signup, OTP login, resend and password reset used to call Resend inline,
so the user's click waited for an external API (and failed with it). Now the
endpoint writes an `email_outbox` row in the same transaction as the code it
carries and returns at once; this worker delivers it moments later.

Reliability:
  * persistent — rows live in Postgres, so a Render restart or sleep loses
    nothing; pending rows are picked up again on the next boot.
  * retries with exponential backoff (transient network/429/5xx errors),
    up to MAX_ATTEMPTS, then FAILED with the reason recorded.
  * no duplicates — each row's id is sent as Resend's Idempotency-Key, and a
    row is claimed (status SENDING) before sending; a row stuck in SENDING
    (process died mid-send) is re-claimed after STUCK_AFTER and re-sent with
    the same key, which Resend de-duplicates.
  * bodies (which can contain one-time codes) are erased once sent/failed.

Single process by design (Render runs one instance); on Postgres the claim also
uses FOR UPDATE SKIP LOCKED, so a second instance would not double-claim.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import email_service
from .database import SessionLocal
from .models import EmailOutbox, utcnow

logger = logging.getLogger("tgl.outbox")

MAX_ATTEMPTS = 8
BATCH = 10
IDLE_POLL_SECONDS = 30  # safety net; normally a kick() wakes the worker at once
STUCK_AFTER = timedelta(minutes=5)

_wake = asyncio.Event()
_task: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None


def enqueue(db: AsyncSession, kind: str, to_email: str, message: tuple[str, str, str]) -> EmailOutbox:
    """Add an email to the caller's transaction. Call kick() after commit."""
    subject, html, text = message
    row = EmailOutbox(kind=kind, to_email=to_email, subject=subject, html=html, text=text)
    db.add(row)
    return row


def kick() -> None:
    """Wake the worker now (after the enqueuing transaction committed).
    Thread-safe: the worker's loop is woken via call_soon_threadsafe."""
    if _loop is not None and not _loop.is_closed():
        _loop.call_soon_threadsafe(_wake.set)


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(15 * 2 ** (attempts - 1), 3600))  # 15s, 30s, 1m, 2m … ≤1h


async def _claim(db: AsyncSession) -> list[EmailOutbox]:
    now = utcnow()
    q = (
        select(EmailOutbox)
        .where(
            or_(
                (EmailOutbox.status == "PENDING") & (EmailOutbox.next_attempt_at <= now),
                (EmailOutbox.status == "SENDING") & (EmailOutbox.claimed_at < now - STUCK_AFTER),
            )
        )
        .order_by(EmailOutbox.created_at)
        .limit(BATCH)
    )
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    rows = list((await db.execute(q)).scalars().all())
    for row in rows:
        row.status = "SENDING"
        row.claimed_at = now
        row.attempts += 1
    await db.commit()
    return rows


async def process_due() -> int:
    """Send everything that is due. Returns how many rows were handled."""
    async with SessionLocal() as db:
        rows = await _claim(db)
        for row in rows:
            result = await email_service.deliver(row.to_email, row.subject, row.html or "", row.text or "", row.id)
            if result in ("sent", "skipped"):
                row.status = "SENT" if result == "sent" else "SKIPPED"
                row.sent_at = utcnow()
                row.html = row.text = None
                row.last_error = None
            elif result == "retry" and row.attempts < MAX_ATTEMPTS:
                row.status = "PENDING"
                row.next_attempt_at = utcnow() + _backoff(row.attempts)
                row.last_error = "transient delivery error"
            else:
                row.status = "FAILED"
                row.html = row.text = None
                row.last_error = "rejected by email provider" if result == "failed" else "gave up after retries"
                logger.error("Email %s (%s) permanently failed: %s", row.id, row.kind, row.last_error)
            await db.commit()
        return len(rows)


async def _run() -> None:
    while True:
        try:
            while await process_due():
                pass  # drain: keep going while there is work
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Email outbox worker error; retrying shortly")
        try:
            await asyncio.wait_for(_wake.wait(), timeout=IDLE_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass
        _wake.clear()


def start() -> None:
    global _task, _wake, _loop
    _loop = asyncio.get_running_loop()
    _wake = asyncio.Event()  # bound to the running loop
    _task = asyncio.create_task(_run(), name="email-outbox")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
