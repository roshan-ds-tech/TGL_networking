"""Member renewal: the calculation, the confirmation, and the member's own point history.

The calculation and the confirmation are the ONLY member path to a Growth Points discount, and the confirmation is refused unless every gate
in app/redemption/service.allowed() is open. The old POST /api/v1/growth-points/redeem stays a permanent refusal. Members see the calculation
only while the member preview is on or redemption is open; otherwise they get "coming soon". Fraud flags and other members are never exposed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import GrowthPointLedger, User
from ..ratelimit import enforce
from ..redemption import service
from ..rewards import firewall, rules
from ..security import require_customer_csrf, require_verified_user

router = APIRouter(prefix="/api/v1", tags=["renewal"])

NOT_ACTIVE = "Growth Points are coming soon. They are not active yet and cannot be redeemed."
TERMS = ("Growth Points are rewards earned for verified networking contribution. They may be used only as a discount against eligible TGL subscription renewals. "
         "They are not cash, cannot be transferred and cannot be refunded as money.")


class RenewalConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")                 # a forged points / amount / member / invoice field is a 422, never ignored
    plan_code: str = Field(pattern="^(connect|growth|elite)$")
    redeem: bool = False
    expected_points: int | None = Field(default=None, ge=0, le=1_000_000)           # what the member SAW; the server recomputes everything
    expected_discount_minor: int | None = Field(default=None, ge=0, le=100_000_000)


@router.get("/renewal/quote")
async def renewal_quote(plan_code: str, user: User = Depends(require_verified_user), db: AsyncSession = Depends(get_db)) -> dict:
    """The exact calculation the member will confirm. REAL when redemption is open for them, otherwise a labelled preview, otherwise nothing."""
    ok, why = await service.allowed(db, user)
    sim = (not ok) and service.simulation_allowed(user)
    if not ok and not sim and not firewall.member_preview_enabled():
        return {"enabled": False, "message": NOT_ACTIVE}
    q = await service.quote(db, user, plan_code, simulate=sim)
    q.update(enabled=True, mode="REAL" if ok else ("SIMULATION" if sim else "PREVIEW"), applies_to_invoice=ok, can_redeem=bool(ok and q["points_to_be_redeemed"] > 0), terms=TERMS,
             explanation="These points were earned during your previous subscription cycle and are being used against this renewal. They do not count toward your new cycle's earning limit.")
    if sim:
        q.update(label="SIMULATION (demo account): nothing is applied, no points are used and no invoice is created.", hypothetical_only=True, can_simulate=q["points_to_be_redeemed"] > 0)
    elif not ok:
        q.update(label="Preview only: Growth Points are not active yet. Nothing here changes what you pay.", hypothetical_only=True)
    return q


@router.post("/renewal/confirm", status_code=status.HTTP_201_CREATED)
async def renewal_confirm(payload: RenewalConfirm, user: User = Depends(require_verified_user), __: None = Depends(require_customer_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    enforce(f"renew:{user.id}", 10, 3600, "Too many attempts. Please try again later.")
    result = await service.confirm(db, user, payload.plan_code, redeem=payload.redeem, expected_points=payload.expected_points, expected_discount_minor=payload.expected_discount_minor)
    await db.commit()
    return result


@router.post("/renewal/simulate")
async def renewal_simulate(payload: RenewalConfirm, user: User = Depends(require_verified_user), __: None = Depends(require_customer_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """DEMO ONLY: runs the real redemption code for a synthetic (@example.test) member in development, then ALWAYS rolls back. Nothing is saved: no
    subscription, no invoice, no redemption, no point is used. It does not exist for real members or in production (404)."""
    if not service.simulation_allowed(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    enforce(f"renew-sim:{user.id}", 30, 3600, "Too many attempts. Please try again later.")
    try:
        result = await service.confirm(db, user, payload.plan_code, redeem=payload.redeem, expected_points=payload.expected_points, expected_discount_minor=payload.expected_discount_minor, simulate=True)
    finally:
        await db.rollback()                                               # unconditionally: a simulation is never committed
    return {"simulated": True, "applied": False, "points_would_be_used": result["points_redeemed"], "discount_minor": result["growth_points_discount_minor"],
            "plan_price_minor": result["plan_price_minor"], "amount_payable_minor": result["amount_due_minor"],
            "message": "SIMULATION ONLY. No points were used, no invoice was created and no payment changed."}


@router.get("/growth-points/history")
async def points_history(page: int = 1, user: User = Depends(require_verified_user), db: AsyncSession = Depends(get_db)) -> dict:
    """The member's OWN points: earned, pending, expired, reversed, with the reason. No other member, no counterparty, no fraud flag."""
    ok, _ = await service.allowed(db, user)
    if not ok and not firewall.member_preview_enabled():
        return {"enabled": False, "message": NOT_ACTIVE}
    page = max(1, min(page, 10_000))
    L = GrowthPointLedger
    q = select(L).where(L.member_id == user.id, L.entry_type != "SIM_REDEEM").order_by(L.created_at.desc(), L.id)
    total = int(await db.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = (await db.execute(q.limit(25).offset((page - 1) * 25))).scalars().all()
    label = {"REFERRAL_ACCEPTED": "Referral accepted", "PROSPECT_CONTACTED": "Prospect contacted", "MEETING_COMPLETED": "Meeting completed", "BUSINESS_CLOSED": "Business closed",
             "REPEAT_BUSINESS": "Repeat business", "PROFILE_COMPLETED": "Profile completed"}
    return {"enabled": True, "terms": TERMS, "total": total, "page": page,
            "items": [{"date": r.event_at, "kind": r.entry_type, "action": label.get(r.event_type, r.event_type), "points": r.points_delta, "status": r.status,
                       "reason": r.reason if r.entry_type == "EARN" else {"VOID": "Pending points cancelled", "REVERSAL": "Points reversed", "EXPIRY": "Points expired"}.get(r.entry_type), "usable_from": r.available_at, "expires_at": r.expires_at} for r in rows]}
