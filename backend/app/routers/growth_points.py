"""Growth Points for members, Phase 1: a labelled SHADOW PREVIEW and a redemption endpoint that always refuses.

There is no way to spend Growth Points. `POST /redeem` exists only so that an attempt is refused loudly and recorded;
it never reads or writes an invoice, a payment or a subscription.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit
from ..database import get_db
from ..models import User, utcnow
from ..ratelimit import enforce
from ..redemption import service as redemption_service
from ..rewards import firewall, rules, simulation
from ..security import require_active_networking_member, require_customer_csrf

router = APIRouter(prefix="/api/v1/growth-points", tags=["growth-points-shadow"])

NOT_ACTIVE = "Growth Points are coming soon. They are not active yet and cannot be redeemed."


@router.get("/preview")
async def preview(user: User = Depends(require_active_networking_member), db: AsyncSession = Depends(get_db)) -> dict:
    """The caller's OWN shadow points, clearly labelled. Off unless management decides members should see it."""
    if not firewall.member_preview_enabled():
        return {"enabled": False, "message": NOT_ACTIVE}
    snap = await simulation.member_snapshot(db, user.id)
    cycle = snap["cycle"]
    open_for_me, _ = await redemption_service.allowed(db, user)
    return {
        "enabled": True, "shadow": True, "redeemable": False, "redemption_open": open_for_me,
        "title": "Growth Points: coming soon",
        "disclaimer": "This is a simulation only. Growth Points are not currently active and cannot be redeemed. Nothing here changes what you pay.",
        "labels": ["Shadow", "Preview", "Not redeemable", "Not currently active"],
        "shadow_balance_points": snap["shadow_total_points"], "pending_points": snap["pending_points"], "available_points": snap["available_points"],
        "estimated_value_paise": snap["estimated_value_paise"], "expiring_points": snap["expiring_within_30_days"],
        "this_cycle_points": cycle["earned_this_cycle"] if cycle else 0, "cycle_ceiling_points": cycle["ceiling_points"] if cycle else None,
        "potential_maximum_discount_paise": cycle["maximum_discount_paise"] if cycle else None,
        "potential_next_subscription_benefit_paise": snap["hypothetical_redemption"]["hypothetical_discount_paise"] if snap["hypothetical_redemption"] else 0,
        "invoice_change_paise": 0,
        "cycle": {"plan": cycle["plan"], "term_months": cycle["term_months"], "ends_at": cycle["ends_at"]} if cycle else None,
        "rule_version": rules.RULE_VERSION,
    }


EARN_GUIDE = [
    {"key": "REFERRAL_ACCEPTED", "title": "A referral is accepted", "points": "30 for you (45 if you introduced them by email or call, or arranged a meeting), 15 for the member who accepts", "icon": "send",
     "detail": "You earn when the other member accepts the referral you gave. Creating a referral earns nothing on its own: it has to be accepted."},
    {"key": "PROSPECT_CONTACTED", "title": "A prospect is contacted", "points": "15 for the member who contacts them", "icon": "phone",
     "detail": "The member you referred to contacts the prospect within 72 hours of accepting."},
    {"key": "MEETING_COMPLETED", "title": "A meeting takes place", "points": "45 for the referrer, 60 for the recipient", "icon": "calendar",
     "detail": "Both of you confirm the meeting happened. One confirmation is not enough."},
    {"key": "BUSINESS_CLOSED", "title": "Business is closed", "points": "From 210 up to 1,890 for the referrer, plus a share for the recipient", "icon": "briefcase",
     "detail": "Paid on a verified closed deal, by the size of the deal. Larger deals are checked with evidence and an admin review before anything is paid."},
    {"key": "REPEAT_BUSINESS", "title": "Repeat business", "points": "Half of the closed-business reward", "icon": "repeat",
     "detail": "More verified business from a prospect who already produced a rewarded deal (once per prospect per quarter)."},
    {"key": "PROFILE_COMPLETED", "title": "Complete your profile", "points": "75, once", "icon": "user",
     "detail": "Personal profile, business profile with your founder story and an online link, and a profile photo."},
]
NOT_EARNING = ["Creating a referral", "Viewing profiles, likes or logins", "Connecting with members", "Posting or replying to a need"]
EVENT_LABEL = {g["key"]: g["title"] for g in EARN_GUIDE}
CAP_LABEL = {"DAILY_CEILING": "the daily limit (500 points a day for quick-to-earn rewards)", "MONTHLY_CEILING": "the monthly limit (3,000 points)", "CYCLE_CEILING": "your subscription's earning limit",
             "CATEGORY_SUBCEILING": "the limit for this kind of reward", "PAIR_LOW_ASSURANCE": "the limit between the same two members", "PAIR_CONCENTRATION": "the limit on repeated deals between the same two members",
             "PAIR_RECIPROCAL": "the rule for reciprocal deals", "PAIR_RECIPROCAL_NEEDS_L4": "the rule for reciprocal deals (needs admin approval)", "FREQUENCY_LIMIT": "the monthly count limit for this reward",
             "REPEAT_LIMIT": "the once-per-quarter limit for repeat business", "OUTSIDE_WINDOW": "the 72-hour contact window", "NO_ACTIVE_CYCLE": "not being in an active subscription term"}


@router.get("/overview")
async def overview(user: User = Depends(require_active_networking_member), db: AsyncSession = Depends(get_db)) -> dict:
    """Everything the member's Growth Points page needs. How points are earned is always shown; the member's own numbers only when Growth Points
    are visible to members (the preview, or real redemption). Own data only: no other member, no flag, no internal rule trace."""
    from sqlalchemy import func, select
    from ..models import GrowthPointLedger
    from ..rewards import cycles, ledger
    from ..redemption import service as redemption_service
    out: dict = {"ways_to_earn": EARN_GUIDE, "not_earning": NOT_EARNING, "recording": firewall.shadow_enabled(),
                 "limits": {"daily": rules.DAILY_CEILING_LOW_ASSURANCE, "monthly": rules.MONTHLY_CEILING, "per_cycle_percent_of_price": 12,
                            "expiry": "Points are valid for the subscription term they were earned in, plus a 30-day renewal window. After that they expire."},
                 "redemption": {"state": "NOT_ACTIVE", "explanation": "Growth Points will be usable only as a discount when you renew your subscription: at most 15% of the renewal price. They are not cash, can not be transferred and can not be refunded as money.",
                                "cap_percent": 15}}
    ok, _why = await redemption_service.allowed(db, user)
    visible = firewall.member_preview_enabled() or ok
    out["visible"] = visible
    if ok:
        out["redemption"]["state"] = "OPEN"
    if not visible:
        out["message"] = "Growth Points are coming soon. They are not being shown on your account yet."
        return out
    now = utcnow()
    lots = await ledger.lots(db, member_id=user.id, now=now)
    pending = sum(l.remaining for l in lots if l.state == "PENDING")
    available = sum(l.remaining for l in lots if l.state == "AVAILABLE")
    expiring = sum(l.remaining for l in lots if l.state in ("PENDING", "AVAILABLE") and l.row.expires_at is not None and rules.aware(l.row.expires_at) <= now + timedelta(days=30))
    cycle = await cycles.resolve_cycle(db, user.id, now, persist=False)
    earned_cycle = 0
    if cycle is not None and cycle.id:
        earned_cycle = int(await db.scalar(select(func.coalesce(func.sum(GrowthPointLedger.points_delta), 0)).where(GrowthPointLedger.cycle_id == cycle.id, GrowthPointLedger.entry_type.in_(("EARN", "VOID", "REVERSAL")))) or 0)
    L = GrowthPointLedger
    by_event = [{"key": k, "title": EVENT_LABEL.get(k, k), "times": int(n), "points": int(p)} for k, n, p in (await db.execute(
        select(L.event_type, func.count(L.id), func.sum(L.points_delta)).where(L.member_id == user.id, L.entry_type == "EARN", L.points_delta > 0).group_by(L.event_type))).all()]
    rows_ = (await db.execute(select(L).where(L.member_id == user.id, L.entry_type != "SIM_REDEEM").order_by(L.event_at.desc(), L.created_at.desc()).limit(30))).scalars().all()
    activity = []
    for r in rows_:
        row = {"date": r.event_at, "title": EVENT_LABEL.get(r.event_type, r.event_type), "kind": r.entry_type, "points": r.points_delta, "status": r.status, "usable_from": r.available_at, "expires_at": r.expires_at}
        if r.entry_type == "EARN" and r.capped_points > 0:
            row["note"] = f"Reduced from {r.requested_points:,} points by {CAP_LABEL.get(r.capped_by, 'a limit')}."
        elif r.entry_type == "VOID":
            row["note"] = "Cancelled before it became usable."
        elif r.entry_type == "REVERSAL":
            row["note"] = "Taken back because the underlying deal or referral did not stand."
        elif r.entry_type == "EXPIRY":
            row["note"] = "Not used within the renewal window."
        activity.append(row)
    out.update(
        balance={"total": pending + available, "pending": pending, "available": available, "expiring_within_30_days": expiring},
        cycle=None if cycle is None else {"plan": cycle.plan_code, "term_months": cycle.term_months, "earned": earned_cycle, "ceiling": cycle.ceiling_points, "ends_at": cycle.ends_at,
                                          "renewal_opens_at": cycle.renewal_opens_at, "grace_ends_at": cycle.grace_ends_at,
                                          "percent": min(100, round(earned_cycle * 100 / cycle.ceiling_points)) if cycle.ceiling_points else 0},
        earned_by_activity=by_event, activity=activity,
        label="Preview: Growth Points are not active yet. These are the points you would have earned. Nothing here changes what you pay." if not ok else "Growth Points are active on your account.",
        preview_only=not ok)
    return out


@router.post("/redeem", status_code=status.HTTP_409_CONFLICT)
async def redeem(user: User = Depends(require_active_networking_member), __: None = Depends(require_customer_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Always refused. Growth Points have no monetary value in Phase 1; nothing is applied to any invoice."""
    enforce(f"gp-redeem:{user.id}", 10, 3600, "Too many attempts.")
    try:
        firewall.redeem(user.id)
    except firewall.RedemptionDisabled:
        audit.record(db, actor=user, action="growth_points.redemption_refused", resource_type="member", resource_id=user.id, reason="Growth Points redemption does not exist (shadow mode)")
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "redemption_disabled", "message": NOT_ACTIVE})
    raise HTTPException(status.HTTP_409_CONFLICT, detail={"code": "redemption_disabled", "message": NOT_ACTIVE})  # unreachable: redeem() always raises
