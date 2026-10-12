"""Synthetic (demo) members: how they are recognised, and how they are kept out of every real-observation calculation.

A demo member is a user whose email is under the reserved `demo.example.com` domain (the seed script, scripts/seed_demo_members.py, is the only
thing that creates them, and refuses to run in production). That is the marker: it needs no schema change, it lives in the database row itself,
and it can not be mistaken for a real member's address. Synthetic activity may exist in a development or test database so the interface can be
inspected, but it must NEVER count as genuine observation: Gate A, the objective gates and the review's sufficiency numbers use `real_stats()`.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import GrowthPointLedger, Subscription, TGLMembership, User, utcnow

DEMO_PASSWORD = "Demo-Local-Only-2026!"      # development / test only: the seed refuses production, and the admin view never shows it there
SYNTHETIC_DOMAIN = "demo.example.com"      # reserved by RFC 2606 (a subdomain of example.com); the .test TLD is refused by the app's email validation


def is_synthetic_email(email: str | None) -> bool:
    return bool(email) and email.strip().lower().endswith("@" + SYNTHETIC_DOMAIN)


def synthetic_clause(column=User.email):
    """SQL condition: this user is a synthetic demo member."""
    return func.lower(column).like(f"%@{SYNTHETIC_DOMAIN}")


def real_clause(column=User.email):
    return ~synthetic_clause(column)


async def real_stats(db: AsyncSession) -> dict:
    """What the observation gates may count: GENUINE members only. Synthetic members and their activity are excluded and reported separately."""
    now = utcnow()
    active_real = set()
    for (uid,) in (await db.execute(select(Subscription.user_id).join(User, User.id == Subscription.user_id).where(
            Subscription.status == "ACTIVE", Subscription.starts_at <= now, Subscription.expires_at > now, real_clause()))).all():
        active_real.add(uid)
    for (uid,) in (await db.execute(select(TGLMembership.user_id).join(User, User.id == TGLMembership.user_id).where(
            TGLMembership.status == "ACTIVE", TGLMembership.starts_at <= now, TGLMembership.expires_at > now, real_clause()))).all():
        active_real.add(uid)
    # genuine members whose Networking access is the Season 1 Finale window (a verified account on a registration): they have no subscription or
    # membership row but are active members
    from .models import Registration
    from .security import finale_window
    if await finale_window(db) is not None:
        for (uid,) in (await db.execute(select(User.id).join(Registration, func.lower(Registration.email) == func.lower(User.email)).where(User.email_verified_at.is_not(None), real_clause()))).all():
            active_real.add(uid)
    first = await db.scalar(select(func.min(GrowthPointLedger.created_at)).join(User, User.id == GrowthPointLedger.member_id).where(real_clause()))
    rewards = int(await db.scalar(select(func.count(GrowthPointLedger.id)).join(User, User.id == GrowthPointLedger.member_id).where(
        real_clause(), GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.points_delta > 0)) or 0)
    synthetic_members = int(await db.scalar(select(func.count(User.id)).where(synthetic_clause())) or 0)
    synthetic_rows = int(await db.scalar(select(func.count(GrowthPointLedger.id)).join(User, User.id == GrowthPointLedger.member_id).where(synthetic_clause())) or 0)
    from .rewards import rules
    observed_days = (now - rules.aware(first)).days if first else 0
    return {"real_active_members": len(active_real), "real_observed_days": observed_days, "real_rewards_recorded": rewards,
            "synthetic_members_excluded": synthetic_members, "synthetic_ledger_rows_excluded": synthetic_rows}
