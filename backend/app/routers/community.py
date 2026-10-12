"""Member API for the need lifecycle and help offers (Phase A). Records facts: nothing here awards or requests Growth Points.

Every state change is authorised by the session and CSRF, restricted to the member who owns that part of the workflow, validated against an
explicit transition table under a row lock, and written together with its history event in ONE transaction.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import community
from ..database import get_db
from ..models import Business, BusinessNeed, NeedHelpOffer, PersonalProfile, User, utcnow
from ..ratelimit import enforce
from ..schemas import NeedOfferAction, NeedOfferOut, NeedResolve
from ..security import require_active_networking_member, require_customer_csrf
from ..services import notify

router = APIRouter(prefix="/api/v1/networking", tags=["community"])


def _offer_out(o: NeedHelpOffer, viewer: User, poster_id: str, helper_name: str | None = None, helper_business: str | None = None) -> NeedOfferOut:
    is_poster = viewer.id == poster_id
    return NeedOfferOut(id=o.id, need_id=o.need_id, status=o.status, message=o.message, created_at=o.created_at,
                        helper_user_id=o.helper_user_id if is_poster else None, helper_name=helper_name if is_poster else None,
                        helper_business=helper_business if is_poster else None, mine=o.helper_user_id == viewer.id)


@router.post("/needs/{need_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_need(need_id: str, user: User = Depends(require_active_networking_member), __: None = Depends(require_customer_csrf),
                      db: AsyncSession = Depends(get_db)) -> Response:
    """The poster withdraws their own need. It leaves the board but stays in the history; open offers are left as they were (frozen)."""
    enforce(f"need-state:{user.id}", 30, 3600, "Too many changes. Please try again later.")
    need = await community.need_for_update(db, need_id)
    if need.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found")                 # no hint that it exists
    if need.status != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, f"A need that is {need.status.lower()} can not be cancelled.")
    if not await community.move_need(db, need.id, ("OPEN",), status="CANCELLED", cancelled_at=utcnow()):
        raise HTTPException(status.HTTP_409_CONFLICT, "This need was just updated. Refresh and try again.")
    community.record(db, "NEED", "CANCELLED", actor=user.id, need_id=need.id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/needs/{need_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_need(need_id: str, payload: NeedResolve, user: User = Depends(require_active_networking_member), __: None = Depends(require_customer_csrf),
                       db: AsyncSession = Depends(get_db)) -> Response:
    """The poster says the need is resolved, optionally crediting ONE help offer. Only the poster can say so. A credited offer must already be
    confirmed helpful by the poster, so attribution is never a first, unconfirmed claim. This records who the poster says helped; it is not a reward."""
    enforce(f"need-state:{user.id}", 30, 3600, "Too many changes. Please try again later.")
    need = await community.need_for_update(db, need_id)
    if need.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found")
    if need.status != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, f"A need that is {need.status.lower()} can not be resolved.")
    credited = None
    if payload.offer_id:
        credited = await db.scalar(select(NeedHelpOffer).where(NeedHelpOffer.id == payload.offer_id, NeedHelpOffer.need_id == need.id))
        if credited is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That offer does not belong to this need.")
        if credited.status != "CONFIRMED_HELPFUL":
            raise HTTPException(status.HTTP_409_CONFLICT, "Confirm that the help was useful before crediting it.")
    now = utcnow()
    if not await community.move_need(db, need.id, ("OPEN",), status="RESOLVED", resolved_at=now, resolved_offer_id=credited.id if credited else None):
        raise HTTPException(status.HTTP_409_CONFLICT, "This need was just updated. Refresh and try again.")
    community.record(db, "NEED", "RESOLVED", actor=user.id, subject=credited.helper_user_id if credited else None, need_id=need.id, offer_id=credited.id if credited else None,
                     pair=community.pair_hash(user.id, credited.helper_user_id) if credited else None, details={"credited_helper": bool(credited)})
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/needs/{need_id}/offers", response_model=list[NeedOfferOut])
async def need_offers(need_id: str, user: User = Depends(require_active_networking_member), db: AsyncSession = Depends(get_db)) -> list[NeedOfferOut]:
    """The poster sees every offer on their need; anyone else sees only their own offer (an empty list if they made none)."""
    need = await db.get(BusinessNeed, need_id)
    if need is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found")
    q = (select(NeedHelpOffer, PersonalProfile.full_name, Business.business_name)
         .outerjoin(PersonalProfile, PersonalProfile.user_id == NeedHelpOffer.helper_user_id)
         .outerjoin(Business, Business.user_id == NeedHelpOffer.helper_user_id).where(NeedHelpOffer.need_id == need_id).order_by(NeedHelpOffer.created_at))
    if need.user_id != user.id:
        q = q.where(NeedHelpOffer.helper_user_id == user.id)
    seen, out = set(), []
    for o, name, biz in (await db.execute(q)).all():
        if o.id not in seen:                      # a member may own several businesses: one row per offer
            seen.add(o.id)
            out.append(_offer_out(o, user, need.user_id, name, biz))
    return out


@router.patch("/needs/offers/{offer_id}", response_model=NeedOfferOut)
async def act_on_offer(offer_id: str, payload: NeedOfferAction, user: User = Depends(require_active_networking_member), __: None = Depends(require_customer_csrf),
                       db: AsyncSession = Depends(get_db)) -> NeedOfferOut:
    """accept / decline / confirm_helpful / not_helpful: the poster. withdraw: the helper. Anything else is refused (see community.OFFER_TRANSITIONS)."""
    enforce(f"need-state:{user.id}", 60, 3600, "Too many changes. Please try again later.")
    offer = await community.transition_offer(db, offer_id, payload.action, user)
    need = await db.get(BusinessNeed, offer.need_id)
    if payload.action == "accept":
        notify(db, offer.helper_user_id, "need_offer_accepted", "Your offer of help was accepted", f"Need: {need.title}", "business_need", need.id, actor_user_id=user.id)
    await db.commit()
    return _offer_out(offer, user, need.user_id)
