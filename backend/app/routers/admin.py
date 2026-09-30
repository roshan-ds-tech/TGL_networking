"""Authenticated admin data endpoints."""
from __future__ import annotations

import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Admin, Business, EventRegistration, PersonalProfile, Registration, TGLMembership, User, utcnow
from ..schemas import (
    BusinessVerificationUpdate,
    CategoryCount,
    CustomerListItem,
    CustomerPage,
    RegistrationOut,
    RegistrationPage,
    StatsOut,
    VerifyRequest,
    FinaleCompleteOut,
)
from ..security import get_current_admin, require_csrf
from ..services import activate_memberships_for_event, confirm_event_registration, get_or_create_season_1
from ..storage import delete_proof, resolve_proof
from .public import invalidate_availability_cache

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger("tgl")


def _to_out(reg: Registration) -> RegistrationOut:
    return RegistrationOut(
        id=reg.id,
        full_name=reg.full_name,
        business_name=reg.business_name,
        email=reg.email,
        phone=reg.phone,
        category=reg.category,
        employees=reg.employees,
        business_age=reg.business_age,
        city=reg.city,
        proof_mime=reg.proof_mime,
        proof_bytes=reg.proof_bytes,
        agreed_terms=reg.agreed_terms,
        media_consent=reg.media_consent,
        verified=reg.verified,
        verified_at=reg.verified_at,
        verified_by_email=reg.verified_by.email if reg.verified_by else None,
        created_at=reg.created_at,
    )


@router.get("/registrations", response_model=RegistrationPage)
async def list_registrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    category: str | None = Query(None, max_length=8),
    verified: bool | None = Query(None),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> RegistrationPage:
    filters = []
    if search:
        # Parameterised LIKE - values are bound, never string-concatenated.
        needle = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Registration.full_name).like(needle),
                func.lower(Registration.business_name).like(needle),
                func.lower(Registration.email).like(needle),
                Registration.phone.like(needle),
            )
        )
    if category:
        filters.append(Registration.category == category)
    if verified is not None:
        filters.append(Registration.verified == verified)

    total = await db.scalar(
        select(func.count()).select_from(Registration).where(*filters)
    ) or 0

    rows = await db.execute(
        select(Registration)
        .where(*filters)
        .order_by(Registration.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_to_out(r) for r in rows.unique().scalars().all()]

    return RegistrationPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/customers", response_model=CustomerPage)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> CustomerPage:
    """TGL product-app accounts — who has an account, independent of whether
    they registered/paid for Season 1 (see /registrations for that)."""
    filters = []
    if search:
        needle = f"%{search.strip().lower()}%"
        filters.append(func.lower(User.email).like(needle))

    total = await db.scalar(select(func.count()).select_from(User).where(*filters)) or 0

    rows = await db.execute(
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = rows.scalars().all()
    user_ids = [u.id for u in users]

    profiles: dict[str, PersonalProfile] = {}
    businesses: dict[str, Business] = {}
    if user_ids:
        profile_rows = await db.execute(select(PersonalProfile).where(PersonalProfile.user_id.in_(user_ids)))
        profiles = {p.user_id: p for p in profile_rows.scalars().all()}
        # Same "earliest business is primary" rule as the customer API.
        business_rows = await db.execute(
            select(Business).where(Business.user_id.in_(user_ids)).order_by(Business.created_at.asc())
        )
        for b in business_rows.scalars().all():
            businesses.setdefault(b.user_id, b)

    items = [
        CustomerListItem(
            id=u.id,
            email=u.email,
            email_verified_at=u.email_verified_at,
            is_active=u.is_active,
            created_at=u.created_at,
            full_name=profiles[u.id].full_name if u.id in profiles else None,
            business_name=businesses[u.id].business_name if u.id in businesses else None,
            business_id=businesses[u.id].id if u.id in businesses else None,
            verification_status=businesses[u.id].verification_status if u.id in businesses else None,
            personal_profile_complete=u.id in profiles,
            business_profile_complete=u.id in businesses,
        )
        for u in users
    ]

    return CustomerPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


_VERIFICATION_STATUSES = {"NOT_STARTED", "PENDING", "NEEDS_INFO", "VERIFIED", "REJECTED"}


@router.patch("/customers/{user_id}/verification", response_model=CustomerListItem)
async def update_business_verification(
    user_id: str,
    payload: BusinessVerificationUpdate,
    _: Admin = Depends(get_current_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> CustomerListItem:
    new_status = payload.status.upper()
    if new_status not in _VERIFICATION_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid verification status.")
    business = (
        await db.execute(select(Business).where(Business.user_id == user_id).order_by(Business.created_at.asc()).limit(1))
    ).scalar_one_or_none()
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This account has no business profile.")
    business.verification_status = new_status
    business.tgl_verified = new_status == "VERIFIED"
    business.tgl_verified_at = utcnow() if new_status == "VERIFIED" else None
    user = await db.get(User, user_id)
    profile = await db.get(PersonalProfile, user_id)
    await db.commit()
    return CustomerListItem(
        id=user_id,
        email=user.email,
        email_verified_at=user.email_verified_at,
        is_active=user.is_active,
        created_at=user.created_at,
        full_name=profile.full_name if profile else None,
        business_name=business.business_name,
        business_id=business.id,
        verification_status=business.verification_status,
        personal_profile_complete=profile is not None,
        business_profile_complete=True,
    )


@router.get("/stats", response_model=StatsOut)
async def stats(
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> StatsOut:
    total = await db.scalar(select(func.count()).select_from(Registration)) or 0
    verified = await db.scalar(
        select(func.count()).select_from(Registration).where(Registration.verified.is_(True))
    ) or 0

    rows = await db.execute(
        select(
            Registration.category,
            func.count().label("total"),
            func.sum(func.cast(Registration.verified, Integer)).label("verified"),
        ).group_by(Registration.category).order_by(Registration.category)
    )
    by_category = [
        CategoryCount(category=c, total=t, verified=int(v or 0)) for c, t, v in rows.all()
    ]

    return StatsOut(
        total=total,
        verified=verified,
        pending=total - verified,
        by_category=by_category,
        capacity_per_category=settings.slots_per_category,
    )


@router.patch("/registrations/{registration_id}/verify", response_model=RegistrationOut)
async def set_verified(
    registration_id: str,
    payload: VerifyRequest,
    admin: Admin = Depends(get_current_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> RegistrationOut:
    reg = await db.get(Registration, registration_id)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")

    reg.verified = payload.verified
    reg.verified_at = utcnow() if payload.verified else None
    reg.verified_by_id = admin.id if payload.verified else None
    if reg.event_registration_id:
        event_reg = await db.get(EventRegistration, reg.event_registration_id)
        if event_reg is not None:
            if payload.verified:
                await confirm_event_registration(db, event_reg, admin.id)
            else:
                event_reg.status = "PAYMENT_REVIEW"
                event_reg.payment_status = "REVIEW"
                event_reg.confirmed_at = None
                event_reg.admin_verified_at = None
                event_reg.admin_verified_by_id = None
                membership = await db.scalar(
                    select(TGLMembership).where(TGLMembership.source_event_registration_id == event_reg.id)
                )
                if membership is not None and membership.status != "ACTIVE":
                    membership.status = "PENDING"
    await db.commit()
    await db.refresh(reg)
    return _to_out(reg)


@router.post("/events/season-1/complete", response_model=FinaleCompleteOut)
async def complete_season_1(
    admin: Admin = Depends(get_current_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> FinaleCompleteOut:
    event = await get_or_create_season_1(db)
    result = await activate_memberships_for_event(db, event, utcnow())
    await db.commit()
    await db.refresh(event)
    logger.warning(
        "Season 1 Grand Finale completed by %s activated=%s already_active=%s",
        admin.email,
        result["activated"],
        result["already_active"],
    )
    return FinaleCompleteOut(event=event, activated=result["activated"], already_active=result["already_active"])


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registration(
    registration_id: str,
    admin: Admin = Depends(get_current_admin),
    __: None = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Permanently remove a registration and its payment screenshot.

    Irreversible by design (there is no soft-delete column, and no migration
    tooling to add one). The proof file goes with the row so the upload
    directory does not accumulate unreachable files.
    """
    reg = await db.get(Registration, registration_id)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")

    proof_filename = reg.proof_filename
    business = reg.business_name

    await db.delete(reg)
    await db.commit()

    # Only after the row is durably gone — if the commit fails we must not have
    # destroyed the evidence for a registration that still exists.
    removed = delete_proof(proof_filename)

    logger.warning(
        "Registration deleted: id=%s business=%r by=%s proof_removed=%s",
        registration_id,
        business,
        admin.email,
        removed,
    )
    # The public slot counters are now stale.
    invalidate_availability_cache()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/registrations/{registration_id}/proof")
async def get_proof(
    registration_id: str,
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    reg = await db.get(Registration, registration_id)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")

    path = resolve_proof(reg.proof_filename)
    return FileResponse(
        path,
        media_type=reg.proof_mime,
        headers={
            # Render inline in the dashboard, but never let the browser guess a
            # different (potentially executable) type, and never cache to disk.
            "Content-Disposition": f'inline; filename="proof-{reg.id[:8]}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; object-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )
