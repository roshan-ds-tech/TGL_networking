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
from ..models import Admin, Registration, utcnow
from ..schemas import (
    CategoryCount,
    RegistrationOut,
    RegistrationPage,
    StatsOut,
    VerifyRequest,
)
from ..security import get_current_admin, require_csrf
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
        utr=reg.utr,
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
                # Verifying a payment usually starts from the reference on the
                # bank statement, so it needs to be searchable. Stored
                # uppercase, so match against the upper-cased needle.
                Registration.utr.like(needle.upper()),
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
    await db.commit()
    await db.refresh(reg)
    return _to_out(reg)


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
