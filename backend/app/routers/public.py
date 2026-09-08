"""Public (unauthenticated) registration intake."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Registration
from ..ratelimit import client_ip, enforce
from ..schemas import (
    VALID_CATEGORIES,
    AvailabilityOut,
    CategoryAvailability,
    RegistrationCreate,
)
from ..security import hash_ip
from ..storage import delete_proof, save_payment_proof

router = APIRouter(prefix="/api", tags=["public"])

# The availability counter is served to every visitor of the marketing site, so
# it is cached in-process for a short window. That keeps the DB cost O(1) per
# window no matter how much traffic the page gets, and a few seconds of
# staleness is irrelevant for a "slots filling up" indicator.
_AVAILABILITY_TTL_SECONDS = 30
_availability_cache: tuple[float, AvailabilityOut] | None = None


def invalidate_availability_cache() -> None:
    global _availability_cache
    _availability_cache = None


def _conflict(field: str, message: str) -> HTTPException:
    """A 409 carrying the same {field, message} shape the 422 path uses.

    Lets the SPA show a conflict against the input it belongs to — a full
    category on the category select, a reused UTR on the UTR box — instead of
    a generic banner that leaves the user hunting for what to change.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=[{"field": field, "message": message}],
    )


_UTR_TAKEN_MESSAGE = (
    "This UTR is already on another registration. Please check the reference "
    "number from your payment app, or contact us if you think this is a mistake."
)


async def _utr_taken(db: AsyncSession, utr: str, exclude_id: str | None = None) -> bool:
    """Is this UPI reference already attached to a registration?

    Compares the normalised form (schemas.RegistrationCreate uppercases and
    strips separators), so "4029 1234-5678" cannot be re-used as "402912345678".
    """
    query = select(func.count()).select_from(Registration).where(Registration.utr == utr)
    if exclude_id is not None:
        query = query.where(Registration.id != exclude_id)
    return bool(await db.scalar(query))


@router.post("/registrations", status_code=status.HTTP_201_CREATED)
async def create_registration(
    request: Request,
    full_name: str = Form(..., alias="name"),
    business_name: str = Form(..., alias="business"),
    email: str = Form(...),
    phone: str = Form(...),
    category: str = Form(...),
    employees: str = Form(...),
    business_age: str = Form(..., alias="age"),
    city: str | None = Form(default=None),
    utr: str = Form(...),
    agreed_terms: bool = Form(..., alias="agree"),
    media_consent: bool = Form(..., alias="mediaConsent"),
    payment_proof: UploadFile = File(..., alias="paymentProof"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ip = client_ip(request)
    enforce(
        f"register:{ip}",
        settings.register_max_per_hour,
        3600,
        "Too many registration attempts from this network. Please try again later.",
    )

    try:
        data = RegistrationCreate(
            full_name=full_name,
            business_name=business_name,
            email=email,
            phone=phone,
            category=category,
            employees=employees,
            business_age=business_age,
            city=city,
            utr=utr,
            agreed_terms=agreed_terms,
            media_consent=media_consent,
        )
    except ValidationError as exc:
        # Surface field-level messages the SPA can map back onto inputs.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {"field": str(e["loc"][0]) if e["loc"] else "", "message": e["msg"]}
                for e in exc.errors()
            ],
        )

    # Fail fast on an already-full category before spending time on the
    # upload. This is a courtesy, not the enforcement point — a second
    # request can still race past it, which is why the real gate is below.
    filled = await db.scalar(
        select(func.count()).select_from(Registration).where(Registration.category == data.category)
    )
    if filled >= settings.slots_per_category:
        raise _conflict(
            "category", f"Category {data.category} is full. Please choose another category."
        )

    # A UTR identifies exactly one payment, so if it is already attached to
    # another registration it is not evidence for this one — either a repeat
    # submission or a reference copied from someone else's payment. Checked
    # before the upload so a duplicate fails fast, and again after the insert
    # below so it cannot slip through between the two.
    if await _utr_taken(db, data.utr):
        raise _conflict("utr", _UTR_TAKEN_MESSAGE)

    filename, mime, size = await save_payment_proof(payment_proof)

    registration = Registration(
        full_name=data.full_name,
        business_name=data.business_name,
        email=str(data.email).lower(),
        phone=data.phone,
        category=data.category,
        employees=data.employees,
        business_age=data.business_age,
        city=data.city or None,
        utr=data.utr,
        proof_filename=filename,
        proof_mime=mime,
        proof_bytes=size,
        agreed_terms=data.agreed_terms,
        media_consent=data.media_consent,
        submitter_ip_hash=hash_ip(ip),
    )
    db.add(registration)

    # Flush (not commit) so the INSERT runs now, inside this transaction, and
    # re-count in the same transaction before deciding whether to keep it.
    #
    # This closes the race the check above leaves open: SQLite — this app's
    # default and documented deployment target (see the "Postgres for
    # multi-instance" note in backend/README.md) — takes its single-writer
    # file lock on the first write in a transaction and holds it until
    # commit/rollback. A second concurrent request's flush() blocks on that
    # lock until this transaction finishes, so it always re-counts *after*
    # this one has either committed or rolled back — never in between. Two
    # submissions racing for the last slot in a category are therefore
    # serialised into "one wins, one gets 409", never "both get in". (This
    # argument is specific to SQLite's single-writer lock and a single
    # worker process — the same assumption the in-process rate limiter
    # already makes, see ratelimit.py. A multi-instance Postgres deployment
    # would need an explicit `SELECT ... FOR UPDATE` or advisory lock here
    # instead.)
    await db.flush()
    filled_after = await db.scalar(
        select(func.count()).select_from(Registration).where(Registration.category == data.category)
    )
    if filled_after > settings.slots_per_category:
        await db.rollback()
        # The row never committed, so its proof file would otherwise be an
        # orphan nobody can reach — remove it rather than leaking disk.
        delete_proof(filename)
        raise _conflict(
            "category",
            f"Category {data.category} just filled up. Please choose another category.",
        )

    # Same re-check for the UTR, inside the same transaction, excluding the row
    # just flushed. Covers a duplicate that landed after the fast-fail above.
    if await _utr_taken(db, data.utr, exclude_id=registration.id):
        await db.rollback()
        delete_proof(filename)
        raise _conflict("utr", _UTR_TAKEN_MESSAGE)

    await db.commit()

    # A new row changes the slot counters, so drop the cached snapshot.
    invalidate_availability_cache()

    # Deliberately minimal: no internal IDs leak to the public site.
    return {"status": "received", "name": data.full_name}


@router.get("/categories/availability", response_model=AvailabilityOut)
async def category_availability(db: AsyncSession = Depends(get_db)) -> AvailabilityOut:
    """How many of each category's slots are taken.

    Exposed publicly on purpose: the marketing site shows "12 of 40 filled" per
    category. Only aggregate counts are returned — never any registrant detail.
    """
    global _availability_cache

    now = time.monotonic()
    if _availability_cache is not None:
        cached_at, cached = _availability_cache
        if now - cached_at < _AVAILABILITY_TTL_SECONDS:
            return cached

    rows = await db.execute(
        select(Registration.category, func.count()).group_by(Registration.category)
    )
    counts = dict(rows.all())

    capacity = settings.slots_per_category
    categories = [
        CategoryAvailability(
            category=code,
            # Clamped: an over-subscribed category should read "40 of 40", not "43 of 40".
            filled=min(counts.get(code, 0), capacity),
            capacity=capacity,
        )
        for code in sorted(VALID_CATEGORIES)
    ]

    result = AvailabilityOut(
        capacity_per_category=capacity,
        total_capacity=capacity * len(categories),
        total_filled=sum(c.filled for c in categories),
        categories=categories,
    )
    _availability_cache = (now, result)
    return result
