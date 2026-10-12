"""Read-only shadow views: a member's shadow balance and the HYPOTHETICAL redemption.

Nothing here writes anything. The hypothetical redemption answers "if Growth Points were financially active today, what
would this member be able to redeem?" and always carries `invoice_change_minor = 0`: no invoice, payment or subscription is
read for writing, and nothing is ever applied.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GrowthPointLedger, utcnow
from . import cycles, ledger, rules

LABEL = "SHADOW ONLY: a simulation. Growth Points are not redeemable and change no invoice or payment."


async def member_snapshot(db: AsyncSession, member_id: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    lots = await ledger.lots(db, member_id=member_id, now=now)
    pending = sum(l.remaining for l in lots if l.state == "PENDING")
    available = sum(l.remaining for l in lots if l.state == "AVAILABLE")
    lapsed = sum(l.remaining for l in lots if l.state == "EXPIRED")                       # past grace, not yet swept into an EXPIRY row
    soon = sum(l.remaining for l in lots if l.state in ("PENDING", "AVAILABLE") and l.row.expires_at is not None
               and rules.aware(l.row.expires_at) <= now + timedelta(days=rules.GRACE_DAYS))
    expired_total = int(await db.scalar(select(func.coalesce(-func.sum(GrowthPointLedger.points_delta), 0)).where(
        GrowthPointLedger.member_id == member_id, GrowthPointLedger.entry_type == "EXPIRY")) or 0)
    voided = int(await db.scalar(select(func.coalesce(-func.sum(GrowthPointLedger.points_delta), 0)).where(
        GrowthPointLedger.member_id == member_id, GrowthPointLedger.entry_type.in_(("VOID", "REVERSAL")))) or 0)
    cycle = await cycles.resolve_cycle(db, member_id, now, persist=False)
    out = {
        "shadow": True, "redeemable": False, "label": LABEL, "rule_version": rules.RULE_VERSION,
        "pending_points": pending, "available_points": available, "lapsed_points": lapsed, "expiring_within_30_days": soon,
        "expired_points": expired_total, "voided_or_reversed_points": voided, "shadow_total_points": pending + available,
        "value_per_point_paise": rules.PAISE_PER_POINT, "estimated_value_paise": rules.points_to_paise(pending + available),
        "cycle": None, "hypothetical_redemption": None, "invoice_change_minor": 0,
    }
    if cycle is not None:
        used = 0
        if cycle.id:
            used = int(await db.scalar(select(func.coalesce(func.sum(GrowthPointLedger.points_delta), 0)).where(
                GrowthPointLedger.cycle_id == cycle.id, GrowthPointLedger.entry_type.in_(("EARN", "VOID", "REVERSAL")))) or 0)
        cap_paise = rules.redemption_cap_paise(cycle.price_minor)
        value_available = rules.points_to_paise(available)
        out["cycle"] = {
            "plan": cycle.plan_code, "term_months": cycle.term_months, "starts_at": cycle.starts_at, "ends_at": cycle.ends_at,
            "renewal_opens_at": cycle.renewal_opens_at, "grace_ends_at": cycle.grace_ends_at, "earned_this_cycle": used,
            "ceiling_points": cycle.ceiling_points, "closed_business_ceiling_points": cycle.closure_ceiling,
            "maximum_discount_paise": min(rules.points_to_paise(cycle.ceiling_points), cap_paise),
            "contractual_cap_paise": cap_paise, "contractual_cap_points": rules.redemption_cap_points(cycle.price_minor),
        }
        out["hypothetical_redemption"] = {
            "available_value_paise": value_available, "contractual_cap_paise": cap_paise,
            "hypothetical_discount_paise": min(value_available, cap_paise),
            "if_pending_also_released_paise": min(rules.points_to_paise(available + pending), cap_paise),
            "at_renewal_window": {"opens": cycle.renewal_opens_at, "closes": cycle.grace_ends_at},
        }
    return out
