"""The admin finance view of REAL redemption. MODELLED, SHADOW, REALIZED and OUTSTANDING are kept apart and never summed.

  realized cost            discount actually given on renewal invoices (REDEEM minus REVERSE), from growth_point_redemptions
  outstanding potential    what unexpired points could still cost if every member redeemed at their next renewal (capped by 15 % of the plan)
  shadow cost / modelled   from the observation pack: hypothetical / the approved model; never realized money
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GrowthPointLedger, GrowthPointRedemption, Invoice, Plan, Subscription, utcnow
from ..rewards import analytics, rules

R = GrowthPointRedemption


def _i(v) -> int:
    return int(v or 0)


async def summary(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or utcnow()
    L = GrowthPointLedger
    sums = (await db.execute(select(
        func.coalesce(func.sum(case((L.entry_type == "EARN", L.points_delta), else_=0)), 0),
        func.coalesce(func.sum(case((L.entry_type == "EXPIRY", -L.points_delta), else_=0)), 0),
        func.coalesce(func.sum(case((L.entry_type.in_(("VOID", "REVERSAL")), -L.points_delta), else_=0)), 0)))).one()
    redeemed = _i(await db.scalar(select(func.coalesce(func.sum(R.points), 0)).where(R.entry_type == "REDEEM")))
    restored = _i(await db.scalar(select(func.coalesce(func.sum(R.restored_points), 0)).where(R.entry_type == "REVERSE")))
    discount = _i(await db.scalar(select(func.coalesce(func.sum(R.discount_paise), 0)).where(R.entry_type == "REDEEM")))
    reversed_discount = _i(await db.scalar(select(func.coalesce(func.sum(R.discount_paise), 0)).where(R.entry_type == "REVERSE")))
    count = _i(await db.scalar(select(func.count(R.id)).where(R.entry_type == "REDEEM")))
    reversed_count = _i(await db.scalar(select(func.count(R.id)).where(R.entry_type == "REVERSE")))
    by_plan = [{"plan": p, "redemptions": _i(n), "points": _i(pts), "discount_paise": _i(d), "average_discount_paise": round(_i(d) / _i(n)) if _i(n) else None}
               for p, n, pts, d in (await db.execute(
                   select(Plan.code, func.count(R.id), func.sum(R.points), func.sum(R.discount_paise)).join(Subscription, Subscription.id == R.subscription_id)
                   .join(Plan, Plan.id == Subscription.plan_id).where(R.entry_type == "REDEEM").group_by(Plan.code).order_by(Plan.code))).all()]
    by_member = [{"member_id": m, "redemptions": _i(n), "discount_paise": _i(d)} for m, n, d in (await db.execute(
        select(R.member_id, func.count(R.id), func.sum(R.discount_paise)).where(R.entry_type == "REDEEM").group_by(R.member_id).order_by(func.sum(R.discount_paise).desc()).limit(20))).all()]
    renewals = _i(await db.scalar(select(func.count(Subscription.id)).where(Subscription.renews_subscription_id.is_not(None), Subscription.status.in_(("ACTIVE", "EXPIRED", "PENDING")))))
    revenue = _i(await db.scalar(select(func.coalesce(func.sum(Invoice.amount_paid_minor), 0)).where(Invoice.status == "PAID")))
    hyp = await analytics.hypothetical(db, now)
    realized = discount - reversed_discount
    return {
        "realized": {"label": "REAL: discount actually given on renewal invoices (reversed renewals subtracted)", "realized_reward_cost_paise": realized, "redemptions": count - reversed_count,
                     "points_redeemed": redeemed, "points_restored": restored, "reversals": reversed_count, "gross_discount_paise": discount, "reversed_discount_paise": reversed_discount,
                     "average_discount_paise": round(discount / count) if count else None, "by_plan": by_plan, "top_members_by_discount": by_member,
                     "redemption_rate_percent_of_renewals": round(count * 100 / renewals, 1) if renewals else None,
                     "cost_percent_of_paid_subscription_revenue": round(realized * 100 / revenue, 2) if revenue else None, "paid_subscription_revenue_paise": revenue},
        "points": {"earned": _i(sums[0]), "expired": _i(sums[1]), "voided_or_reversed": _i(sums[2]), "redeemed_net": redeemed - restored,
                   "outstanding_pending": hyp["pending_points"], "outstanding_available": hyp["available_points"]},
        "outstanding_potential_liability": {"label": "POTENTIAL, not incurred: what unexpired points could cost at their next renewal, each capped at 15 % of that plan",
                                            "value_of_outstanding_points_paise": hyp["outstanding_value_paise"], "maximum_potential_liability_paise": hyp["maximum_potential_liability_paise"]},
        "separate_from": "Modelled cost, shadow (hypothetical) cost and realized cost are different things and are never added together.",
    }
