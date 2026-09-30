"""P0 domain services for Season 1 membership and notifications."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import (
    Business,
    Event,
    EventRegistration,
    NetworkingProfile,
    Notification,
    Registration,
    TGLMembership,
    User,
    utcnow,
)

SEASON_1_SLUG = "season-1-2026"


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_verification_token() -> str:
    """6-digit numeric OTP — short enough to type back on a phone."""
    return f"{secrets.randbelow(1_000_000):06d}"


def new_reset_token() -> str:
    """URL-safe token for a password-reset link — carried in a query string,
    not typed, so it doesn't need to be short like an OTP."""
    return secrets.token_urlsafe(32)


def add_calendar_months(value: datetime, months: int) -> datetime:
    """Add calendar months, clamping to the last day of the target month."""
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return value.replace(year=year, month=month, day=min(value.day, days[month - 1]))


async def get_or_create_season_1(db: AsyncSession) -> Event:
    result = await db.execute(select(Event).where(Event.slug == SEASON_1_SLUG))
    event = result.scalar_one_or_none()
    if event is not None:
        if event.membership_duration_months != 3:
            event.membership_duration_months = 3
        return event
    event = Event(
        slug=SEASON_1_SLUG,
        name="TGL Season 1",
        grand_finale_at=None,
        registration_open=settings.registration_open,
        registration_closes_at=settings.registration_closes_at,
        membership_duration_months=3,
    )
    db.add(event)
    await db.flush()
    return event


def notify(
    db: AsyncSession,
    user_id: str,
    kind: str,
    title: str,
    body: str,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
) -> Notification:
    item = Notification(
        recipient_user_id=user_id,
        type=kind,
        title=title,
        body=body,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    db.add(item)
    return item


async def ensure_pending_membership(db: AsyncSession, reg: EventRegistration) -> TGLMembership:
    result = await db.execute(
        select(TGLMembership).where(TGLMembership.source_event_registration_id == reg.id)
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        membership = TGLMembership(
            user_id=reg.user_id,
            membership_type="NETWORKING",
            pathway="EVENT_REGISTRATION",
            status="PENDING",
            source_event_registration_id=reg.id,
        )
        db.add(membership)
        await db.flush()
    elif membership.status not in {"ACTIVE", "CANCELLED"}:
        membership.status = "PENDING"
    return membership


async def link_registration_to_account(
    db: AsyncSession,
    *,
    event: Event,
    user: User,
    business: Business,
    legacy: Registration,
) -> tuple[EventRegistration, TGLMembership]:
    """Bridge a legacy (payment-proof) Registration row into the P0 customer
    domain, for a registrant who was logged in when they submitted the public
    form. Creates the event_registrations/tgl_memberships rows and notifies
    the account — same effect a dedicated in-app registration step would have
    had, without duplicating the payment-proof form inside the product app.
    """
    reg = EventRegistration(
        event_id=event.id,
        user_id=user.id,
        business_id=business.id,
        legacy_registration_id=legacy.id,
        status="PAYMENT_REVIEW",
        payment_status="REVIEW",
    )
    db.add(reg)
    await db.flush()
    legacy.event_registration_id = reg.id
    membership = TGLMembership(
        user_id=user.id,
        membership_type="NETWORKING",
        pathway="EVENT_REGISTRATION",
        status="PENDING",
        source_event_registration_id=reg.id,
    )
    db.add(membership)
    notify(
        db,
        user.id,
        "registration_submitted",
        "Season 1 registration submitted",
        "Your payment proof is under review.",
        "event_registration",
        reg.id,
    )
    return reg, membership


async def confirm_event_registration(
    db: AsyncSession,
    reg: EventRegistration,
    admin_id: str,
) -> TGLMembership:
    now = utcnow()
    reg.status = "CONFIRMED"
    reg.payment_status = "CONFIRMED"
    reg.admin_verified_at = now
    reg.admin_verified_by_id = admin_id
    reg.confirmed_at = reg.confirmed_at or now
    membership = await ensure_pending_membership(db, reg)
    notify(
        db,
        reg.user_id,
        "registration_confirmed",
        "Season 1 registration confirmed",
        "Your payment and Season 1 registration are confirmed. Networking membership remains pending until the Grand Finale is completed.",
        "event_registration",
        reg.id,
    )
    return membership


async def activate_memberships_for_event(db: AsyncSession, event: Event, completed_at: datetime) -> dict:
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    event.completed_at = event.completed_at or completed_at
    actual_start = event.completed_at

    regs = await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event.id,
            EventRegistration.status == "CONFIRMED",
            EventRegistration.payment_status == "CONFIRMED",
        )
    )
    activated = 0
    already_active = 0
    for reg in regs.scalars().all():
        membership = await ensure_pending_membership(db, reg)
        if membership.status == "ACTIVE":
            already_active += 1
            continue
        if membership.status in {"CANCELLED", "EXPIRED"}:
            continue
        membership.status = "ACTIVE"
        membership.starts_at = actual_start
        membership.expires_at = add_calendar_months(actual_start, event.membership_duration_months)
        business = await db.get(Business, reg.business_id)
        if business is not None:
            profile_result = await db.execute(
                select(NetworkingProfile).where(NetworkingProfile.user_id == reg.user_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile is None:
                db.add(
                    NetworkingProfile(
                        user_id=reg.user_id,
                        business_id=business.id,
                        headline=f"{business.business_name} founder",
                        bio=business.description,
                        founder_story=business.founder_story,
                        industry_tags=business.category,
                        business_stage=business.business_stage,
                        city=business.city,
                    )
                )
        notify(
            db,
            reg.user_id,
            "membership_activated",
            "Networking membership is active",
            "Your TGL Networking membership is now active for 3 months.",
            "membership",
            membership.id,
        )
        activated += 1
    return {"activated": activated, "already_active": already_active, "completed_at": actual_start}
