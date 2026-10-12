"""Admin API for Phase A community activity: moderate needs and read the observation report.

Moderation records WHO acted (the admin id), WHY (a required reason) and WHEN, in the need row, in the append-only community history and in the
audit log. Nothing here awards, requests or reverses Growth Points: Phase A records facts only.
"""
from __future__ import annotations

import math
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit, community, demo
from ..database import get_db
from ..models import Admin, BusinessNeed, NeedHelpOffer, PersonalProfile, User, utcnow
from ..schemas_p0 import ReasonIn
from ..security import get_current_admin, require_csrf

router = APIRouter(prefix="/api/admin/community", tags=["admin-community"])


@router.get("/needs")
async def list_needs(status_: str | None = Query(default=None, alias="status", max_length=12), page: int = Query(default=1, ge=1, le=100_000),
                     page_size: int = Query(default=25, ge=1, le=100), _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """Needs for moderation, with the poster's identity (admins only). Synthetic demo members are marked so they are never mistaken for genuine ones."""
    offers = select(func.count(NeedHelpOffer.id)).where(NeedHelpOffer.need_id == BusinessNeed.id).correlate(BusinessNeed).scalar_subquery()
    base = select(BusinessNeed, User.email, PersonalProfile.full_name, offers).join(User, User.id == BusinessNeed.user_id).outerjoin(PersonalProfile, PersonalProfile.user_id == BusinessNeed.user_id)
    if status_:
        if status_.upper() not in community.NEED_STATUSES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status")
        base = base.where(BusinessNeed.status == status_.upper())
    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (await db.execute(base.order_by(BusinessNeed.created_at.desc()).limit(page_size).offset((page - 1) * page_size))).all()
    items = [{"id": n.id, "title": n.title, "category": n.category, "description": n.description, "status": n.status, "created_at": n.created_at, "published_at": n.published_at,
              "poster_email": email, "poster_name": name, "synthetic": demo.is_synthetic_email(email), "offers": int(cnt or 0),
              "qualifies_for_future_reward": n.qualifies_for_future_reward, "quality_note": n.quality_note,
              "removed_at": n.removed_at, "removed_by_admin_id": n.removed_by_admin_id, "removed_reason": n.removed_reason} for n, email, name, cnt in rows]
    return {"items": items, "total": total, "page": page, "pages": max(1, math.ceil(total / page_size))}


@router.post("/needs/{need_id}/remove")
async def remove_need(need_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Take a need off the board. Allowed from OPEN or RESOLVED. The need, its offers and its history stay; the moderator and the reason are recorded."""
    need = await community.need_for_update(db, need_id)
    if need.status not in ("OPEN", "RESOLVED"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A need that is {need.status.lower()} can not be removed.")
    before, poster = need.status, need.user_id
    if not await community.move_need(db, need.id, ("OPEN", "RESOLVED"), status="REMOVED", removed_at=utcnow(), removed_by_admin_id=admin.id, removed_reason=payload.reason):
        raise HTTPException(status.HTTP_409_CONFLICT, "This need was just updated. Refresh and try again.")
    community.record(db, "NEED", "REMOVED", admin=admin.id, subject=poster, need_id=need_id, reason=None, details={"from": before})
    audit.record(db, actor=admin, action="community.need_removed", resource_type="business_need", resource_id=need_id, before={"status": before}, after={"status": "REMOVED"}, reason=payload.reason)
    await db.commit()
    return {"id": need_id, "status": "REMOVED"}


@router.post("/needs/{need_id}/restore")
async def restore_need(need_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Put a removed need back: RESOLVED if it had been resolved, otherwise OPEN. The removal stays in the history."""
    need = await community.need_for_update(db, need_id)
    if need.status != "REMOVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a removed need can be restored.")
    target = "RESOLVED" if need.resolved_at else "OPEN"
    if not await community.move_need(db, need.id, ("REMOVED",), status=target):
        raise HTTPException(status.HTTP_409_CONFLICT, "This need was just updated. Refresh and try again.")
    community.record(db, "NEED", "RESTORED", admin=admin.id, subject=need.user_id, need_id=need.id, details={"to": target})
    audit.record(db, actor=admin, action="community.need_restored", resource_type="business_need", resource_id=need.id, before={"status": "REMOVED"}, after={"status": target}, reason=payload.reason)
    await db.commit()
    return {"id": need.id, "status": target}


@router.get("/report")
async def activity_report(days: int | None = Query(default=None, ge=1, le=3650), _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """Read-only, aggregate and anonymous. Genuine members only (synthetic demo members excluded); raw activity is kept apart from outcomes."""
    return await community.report(db, since=(utcnow() - timedelta(days=days)) if days else None)
