"""The only things the rest of the application calls: "this changed", after its own transaction committed.

Each hook opens its OWN session and transaction, runs the idempotent, state-driven sync, and commits. So:
  * a reward can never roll back or delay a networking action, and a reward failure never fails the member's request
    (it is logged; the next sweep re-drives it);
  * the reward is computed from what the database now says, not from anything the client sent;
  * when shadow mode is off every hook returns immediately (stopping shadow mode is just turning the flag off).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.exc import IntegrityError, OperationalError

from . import events, firewall, jobs

log = logging.getLogger("tgl.rewards")


async def _run(label: str, fn) -> dict | None:
    if not firewall.shadow_enabled():
        return None
    from ..database import SessionLocal          # imported late: this package is imported by app.main before the engine exists in tests
    for attempt in range(3):
        try:
            async with SessionLocal() as db:
                with firewall.guard():
                    result = await fn(db)
                await db.commit()
                return result
        except (IntegrityError, OperationalError):
            await asyncio.sleep(0.01 * (attempt + 1))        # two requests raced (a unique key, or a briefly locked database): the retry sees theirs
        except Exception:                                    # noqa: BLE001 - a reward problem must never break a member's action
            log.exception("growth points (shadow): %s failed", label)
            return None
    log.error("growth points (shadow): %s kept colliding; the sweep will pick it up", label)
    return None


async def referral_changed(referral_id: str) -> dict | None:
    return await _run(f"referral {referral_id}", lambda db: events.sync_referral(db, referral_id))


async def closure_changed(closure_id: str) -> dict | None:
    return await _run(f"closure {closure_id}", lambda db: events.sync_closure(db, closure_id))


async def renewals_changed() -> dict | None:
    return await _run("renewals", lambda db: jobs.renewals(db))


async def profile_changed(user_id: str) -> dict | None:
    return await _run(f"profile {user_id}", lambda db: events.sync_profile(db, user_id))
