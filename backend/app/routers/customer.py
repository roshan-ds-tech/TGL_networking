"""Authenticated customer/product API for the P0 TGL slice."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..config import settings
from ..database import get_db
from ..models import (
    Business,
    BusinessNeed,
    BusinessReferral,
    Connection,
    EventRegistration,
    NeedHelpOffer,
    NetworkingProfile,
    Notification,
    PersonalProfile,
    Registration,
    ReferralRequest,
    Subscription,
    TGLMembership,
    User,
    UserVerificationToken,
    photo_url_for,
    utcnow,
)
from ..ratelimit import client_ip, enforce, reset
from .. import community
from ..schemas import (
    CATEGORY_NAMES,
    AuthOut,
    BusinessIn,
    BusinessNeedCreate,
    BusinessNeedOut,
    NeedOfferCreate,
    BusinessOut,
    ConnectionCreate,
    ConnectionOut,
    ConnectionRespond,
    CustomerLogin,
    CustomerOut,
    CustomerSignup,
    ForgotPasswordIn,
    MemberDetail,
    MemberListItem,
    MemberSearchItem,
    MemberSearchOut,
    MembershipOut,
    MyStatusOut,
    NetworkingProfileOut,
    NotificationActor,
    NotificationOut,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    PersonalProfileIn,
    PersonalProfileOut,
    ReferralRequestCreate,
    ResetPasswordIn,
)
from ..security import (
    CSRF_HEADER,
    CUSTOMER_CSRF_COOKIE,
    CUSTOMER_SESSION_COOKIE,
    burn_timing_async,
    create_customer_session_token,
    get_current_user,
    get_optional_user,
    get_user_by_email,
    finale_window,
    active_member_clause,
    access_flags,
    has_networking_access,
    networking_access_from,
    has_registration,
    is_active_member,
    has_verified_registration,
    verified_registrant_ids,
    hash_password_async,
    needs_rehash,
    new_csrf_token,
    require_active_networking_member,
    require_customer_csrf,
    require_verified_user,
    verify_password_async,
)
from .. import legacy_sync, outbox
from ..rewards import hooks as reward_hooks
from ..storage import delete_profile_photo, read_profile_photo, save_profile_photo
from ..email_service import login_otp_email, password_reset_email, verification_email
from ..services import ensure_networking_profile, get_or_create_season_1, season_1, new_reset_token, new_verification_token, notify, token_hash

router = APIRouter(prefix="/api/v1", tags=["customer"])

_GENERIC = "Invalid email or password."


def _set_customer_cookies(response: Response, token: str, csrf: str) -> None:
    common = {
        "secure": settings.cookie_secure,
        "samesite": "strict",
        "path": "/",
        "max_age": settings.session_hours * 3600,
    }
    response.set_cookie(CUSTOMER_SESSION_COOKIE, token, httponly=True, **common)
    response.set_cookie(CUSTOMER_CSRF_COOKIE, csrf, httponly=False, **common)


def _membership_out(m: TGLMembership | None) -> MembershipOut | None:
    if m is None:
        return None
    return MembershipOut(
        id=m.id,
        status=m.status,
        membership_type=m.membership_type,
        pathway=m.pathway,
        starts_at=m.starts_at,
        expires_at=m.expires_at,
    )


def _people_query(user_ids):
    """One query: name, business, city and member-page id for each account."""
    b2 = aliased(Business)
    primary_business_id = (
        select(b2.id).where(b2.user_id == User.id).order_by(b2.created_at.asc()).limit(1)
    ).correlate(User).scalar_subquery()
    return (
        select(User.id, User.full_name, PersonalProfile.full_name, PersonalProfile.city,
               Business.business_name, Business.city, NetworkingProfile.id, User.photo_key)
        .select_from(User)
        .outerjoin(PersonalProfile, PersonalProfile.user_id == User.id)
        .outerjoin(Business, Business.id == primary_business_id)
        .outerjoin(NetworkingProfile, NetworkingProfile.user_id == User.id)
        .where(User.id.in_(list(user_ids)))
    )


async def _people(db: AsyncSession, user_ids) -> dict[str, NotificationActor]:
    if not user_ids:
        return {}
    out = {}
    for uid, account_name, profile_name, profile_city, business_name, business_city, member_id, photo_key in (
        await db.execute(_people_query(user_ids))
    ).all():
        out[uid] = NotificationActor(
            user_id=uid,
            name=profile_name or account_name or "A TGL member",
            business_name=business_name,
            city=profile_city or business_city,
            member_id=member_id,
            photo_url=photo_url_for(uid, photo_key),
        )
    return out


async def _who(db: AsyncSession, user_id: str) -> str:
    """'Asha Rao (Asha Bakes)' — how a member is named in notification text."""
    person = (await _people(db, {user_id})).get(user_id)
    name = person.name if person else "A member"
    return f"{name} ({person.business_name})" if person and person.business_name else name


def _business_out(business: Business | None, paid_registrant: bool) -> BusinessOut | None:
    """Registrants whose payment an admin has verified carry the TGL Verified
    badge automatically. It is derived (not written to the row) so it follows
    the registration: un-verify or delete it and the badge goes, while a badge
    earned through the separate KYB review is untouched."""
    if business is None:
        return None
    out = BusinessOut.model_validate(business)
    if paid_registrant and not out.tgl_verified:
        out = out.model_copy(update={"tgl_verified": True, "verification_status": "VERIFIED", "verified_via_registration": True})
    return out


async def _primary_business(db: AsyncSession, user_id: str) -> Business | None:
    result = await db.execute(
        select(Business).where(Business.user_id == user_id).order_by(Business.created_at.asc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _current_registration(db: AsyncSession, user_id: str) -> EventRegistration | None:
    event = await get_or_create_season_1(db)
    result = await db.execute(
        select(EventRegistration).where(EventRegistration.user_id == user_id, EventRegistration.event_id == event.id)
    )
    return result.scalar_one_or_none()


async def _current_membership(db: AsyncSession, user_id: str) -> TGLMembership | None:
    result = await db.execute(
        select(TGLMembership)
        .where(TGLMembership.user_id == user_id, TGLMembership.membership_type == "NETWORKING")
        .order_by(TGLMembership.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/auth/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: CustomerSignup,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthOut:
    ip = client_ip(request)
    enforce(f"customer-register:{ip}", settings.register_max_per_hour, 3600, "Too many signup attempts. Please try again later.")
    email = str(payload.email).lower().strip()
    if await get_user_by_email(db, email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email,
        password_hash=await hash_password_async(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
    )
    db.add(user)
    await db.flush()
    raw = new_verification_token()
    db.add(
        UserVerificationToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    # Queued in this transaction, sent by the background worker: the signup
    # response no longer waits on the email provider.
    outbox.enqueue(db, "verify_email", user.email, verification_email(raw))
    await db.commit()
    outbox.kick()
    reset(f"customer-register:{ip}")
    _set_customer_cookies(response, create_customer_session_token(user), new_csrf_token())
    return AuthOut(user=user, dev_verification_token=raw if settings.expose_dev_codes else None)


@router.post("/auth/login", response_model=CustomerOut)
async def login(
    payload: CustomerLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    ip = client_ip(request)
    enforce(f"customer-login:{ip}", settings.login_max_attempts, settings.login_window_seconds, "Too many login attempts. Please try again later.")
    user = await get_user_by_email(db, payload.email)
    if user is None:
        await burn_timing_async()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)
    now = datetime.now(timezone.utc)
    locked_until = user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until and user.locked_until.tzinfo is None else user.locked_until
    if locked_until and locked_until > now:
        await burn_timing_async()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)
    if not user.is_active or not await verify_password_async(payload.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_attempts = 0
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)
    user.failed_attempts = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        # Transparent upgrade to the current Argon2 parameters (we have the
        # plaintext only now, at a successful login).
        user.password_hash = await hash_password_async(payload.password)
    await db.commit()
    reset(f"customer-login:{ip}")
    _set_customer_cookies(response, create_customer_session_token(user), new_csrf_token())
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    _: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
) -> Response:
    response.delete_cookie(CUSTOMER_SESSION_COOKIE, path="/", samesite="strict")
    response.delete_cookie(CUSTOMER_CSRF_COOKIE, path="/", samesite="strict")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/session")
async def session(user: User | None = Depends(get_optional_user)) -> dict:
    """Is anyone signed in? Always 200 — public pages ask this on every visit,
    and for an anonymous visitor (the normal case) "no" is an answer, not an
    error. Protected endpoints keep returning 401."""
    if user is None:
        return {"authenticated": False}
    return {"authenticated": True, "user": CustomerOut.model_validate(user).model_dump(mode="json")}


@router.get("/auth/me", response_model=CustomerOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/auth/verify-email", response_model=CustomerOut)
async def verify_email(
    token: str = Form(...),
    user: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> User:
    # The code is only 6 digits (1-in-a-million), so guessing it needs a hard
    # cap independent of the 10-minute expiry.
    enforce(f"verify-email:{user.id}", 8, 600, "Too many attempts. Please request a new code and try again.")
    hashed = token_hash(token.strip())
    result = await db.execute(
        select(UserVerificationToken).where(
            UserVerificationToken.user_id == user.id,
            UserVerificationToken.token_hash == hashed,
            UserVerificationToken.purpose == "EMAIL_VERIFY",
            UserVerificationToken.used_at.is_(None),
            UserVerificationToken.expires_at > utcnow(),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification code.")
    row.used_at = utcnow()
    user.email_verified_at = user.email_verified_at or utcnow()
    await db.commit()
    reset(f"verify-email:{user.id}")
    return user


@router.post("/auth/resend-verification", response_model=AuthOut)
async def resend_verification(
    user: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> AuthOut:
    if user.email_verified_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already verified.")
    enforce(f"resend-verification:{user.id}", 3, 600, "Too many requests. Please wait a few minutes and try again.")
    raw = new_verification_token()
    db.add(
        UserVerificationToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            expires_at=utcnow() + timedelta(minutes=10),
        )
    )
    outbox.enqueue(db, "verify_email", user.email, verification_email(raw))
    await db.commit()
    outbox.kick()
    return AuthOut(user=user, dev_verification_token=raw if settings.expose_dev_codes else None)


@router.post("/auth/otp/request", response_model=OtpRequestOut)
async def request_login_otp(
    payload: OtpRequestIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> OtpRequestOut:
    ip = client_ip(request)
    enforce(f"otp-request:{ip}", settings.login_max_attempts, settings.login_window_seconds, "Too many attempts. Please try again later.")
    email = str(payload.email).lower().strip()
    user = await get_user_by_email(db, email)
    dev_otp = None
    # Same response whether or not the account exists — an OTP-request
    # endpoint that varies its reply would let an attacker enumerate emails.
    if user is not None and user.is_active:
        raw = new_verification_token()
        db.add(UserVerificationToken(user_id=user.id, token_hash=token_hash(raw), purpose="LOGIN_OTP", expires_at=utcnow() + timedelta(minutes=10)))
        outbox.enqueue(db, "login_otp", user.email, login_otp_email(raw))
        await db.commit()
        outbox.kick()
        dev_otp = raw if settings.expose_dev_codes else None
    return OtpRequestOut(dev_otp=dev_otp)


@router.post("/auth/otp/verify", response_model=CustomerOut)
async def verify_login_otp(
    payload: OtpVerifyIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    ip = client_ip(request)
    enforce(f"otp-verify:{ip}", settings.login_max_attempts, settings.login_window_seconds, "Too many attempts. Please try again later.")
    email = str(payload.email).lower().strip()
    # Per-account cap as well as per-IP: a 6-digit code must not be guessable
    # by spreading attempts across many IPs.
    enforce(f"otp-verify-email:{email}", 8, 600, "Too many attempts. Please request a new code and try again.")
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active:
        await burn_timing_async()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code.")
    hashed = token_hash(payload.code.strip())
    result = await db.execute(
        select(UserVerificationToken).where(
            UserVerificationToken.user_id == user.id,
            UserVerificationToken.token_hash == hashed,
            UserVerificationToken.purpose == "LOGIN_OTP",
            UserVerificationToken.used_at.is_(None),
            UserVerificationToken.expires_at > utcnow(),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code.")
    row.used_at = utcnow()
    # The code arrived in this inbox, so the address is proven.
    user.email_verified_at = user.email_verified_at or utcnow()
    user.failed_attempts = 0
    user.locked_until = None
    await db.commit()
    reset(f"otp-verify:{ip}")
    reset(f"otp-verify-email:{email}")
    _set_customer_cookies(response, create_customer_session_token(user), new_csrf_token())
    return user


@router.post("/auth/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    ip = client_ip(request)
    enforce(f"forgot-password:{ip}", 5, 3600, "Too many attempts. Please try again later.")
    email = str(payload.email).lower().strip()
    user = await get_user_by_email(db, email)
    if user is not None and user.is_active:
        raw = new_reset_token()
        origin = settings.public_origins[0] if settings.public_origins else settings.public_origin.rstrip("/")
        db.add(UserVerificationToken(user_id=user.id, token_hash=token_hash(raw), purpose="PASSWORD_RESET", expires_at=utcnow() + timedelta(minutes=30)))
        outbox.enqueue(db, "password_reset", user.email, password_reset_email(f"{origin}/reset-password?token={raw}"))
        await db.commit()
        outbox.kick()
    # Always 204 regardless of whether the email exists.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    ip = client_ip(request)
    enforce(f"reset-password:{ip}", 8, 3600, "Too many attempts. Please try again later.")
    hashed = token_hash(payload.token.strip())
    result = await db.execute(
        select(UserVerificationToken).where(
            UserVerificationToken.token_hash == hashed,
            UserVerificationToken.purpose == "PASSWORD_RESET",
            UserVerificationToken.used_at.is_(None),
            UserVerificationToken.expires_at > utcnow(),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link.")
    user = await db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset link.")
    user.password_hash = await hash_password_async(payload.new_password)
    user.failed_attempts = 0
    user.locked_until = None
    # Sign out every existing session — including one an attacker may hold
    # (e.g. someone who pre-registered this email before its owner did).
    user.token_version += 1
    now = utcnow()
    row.used_at = now
    others = await db.execute(
        select(UserVerificationToken).where(
            UserVerificationToken.user_id == user.id,
            UserVerificationToken.purpose == "PASSWORD_RESET",
            UserVerificationToken.used_at.is_(None),
        )
    )
    for other in others.scalars().all():
        other.used_at = now
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/status", response_model=MyStatusOut)
async def status_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyStatusOut:
    """Everything the member app needs about this account. Called on every
    page change, so it is built from as few round trips as possible: the event
    comes from memory, the account's rows from ONE joined query, and the
    access flags from one more (was 14 sequential queries)."""
    event = await season_1(db)
    # Aliases: the outer query also joins Business / TGLMembership, and the
    # subqueries must pick "the primary one" independently of that join.
    b2, m2 = aliased(Business), aliased(TGLMembership)
    primary_business_id = (
        select(b2.id).where(b2.user_id == User.id).order_by(b2.created_at.asc()).limit(1)
    ).correlate(User).scalar_subquery()
    latest_membership_id = (
        select(m2.id)
        .where(m2.user_id == User.id, m2.membership_type == "NETWORKING")
        .order_by(m2.created_at.desc())
        .limit(1)
    ).correlate(User).scalar_subquery()
    unread_count = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.recipient_user_id == User.id, Notification.read_at.is_(None))
    ).correlate(User).scalar_subquery()
    row = (
        await db.execute(
            select(PersonalProfile, Business, NetworkingProfile, EventRegistration, TGLMembership, unread_count)
            .select_from(User)
            .outerjoin(PersonalProfile, PersonalProfile.user_id == User.id)
            .outerjoin(Business, Business.id == primary_business_id)
            .outerjoin(NetworkingProfile, NetworkingProfile.user_id == User.id)
            .outerjoin(
                EventRegistration,
                (EventRegistration.user_id == User.id) & (EventRegistration.event_id == event.id),
            )
            .outerjoin(TGLMembership, TGLMembership.id == latest_membership_id)
            .where(User.id == user.id)
        )
    ).one()
    profile, business, networking_profile, reg, membership, unread = row
    flags = await access_flags(db, user)
    registered, paid = flags["registered"], flags["paid"]
    if user.email_verified_at is not None and not paid:
        # Maybe they registered (or were verified) on tgl.skykeen.in moments
        # ago: ask for a fresh copy of the legacy registrations (non-blocking,
        # rate-limited) so the next page load sees it.
        legacy_sync.kick()
    window = await finale_window(db)

    # Once the Finale is completed, a registered email's membership is the
    # Finale window itself — even when the registration came through the public
    # form and so has no membership row of its own.
    out_membership = _membership_out(membership)
    if flags["active_membership"] and (out_membership is None or out_membership.status != "ACTIVE"):
        # No membership row, but an active paid subscription is one.
        sub = await db.scalar(
            select(Subscription).where(
                Subscription.user_id == user.id, Subscription.status == "ACTIVE", Subscription.expires_at > utcnow()
            ).order_by(Subscription.expires_at.desc()).limit(1)
        )
        if sub is not None:
            out_membership = MembershipOut(
                id=sub.id, status="ACTIVE", membership_type="NETWORKING", pathway="SUBSCRIPTION",
                starts_at=sub.starts_at, expires_at=sub.expires_at,
            )
    if registered and window is not None and (out_membership is None or out_membership.status != "ACTIVE"):
        out_membership = MembershipOut(
            id=window[0].id,
            status="ACTIVE",
            membership_type="NETWORKING",
            pathway="EVENT_REGISTRATION",
            starts_at=window[1],
            expires_at=window[2],
        )
    access = networking_access_from(flags, window)
    if access and networking_profile is None:
        # Public-form registrants have no profile row until they first arrive
        # with access; without one they would be missing from the directory.
        networking_profile = await ensure_networking_profile(db, user.id)
        await db.commit()
    return MyStatusOut(
        user=user,
        personal_profile=profile,
        business=_business_out(business, paid),
        event=event,
        event_registration=None
        if reg is None
        else {"id": reg.id, "status": reg.status, "payment_status": reg.payment_status, "submitted_at": reg.submitted_at, "confirmed_at": reg.confirmed_at},
        membership=out_membership,
        networking_profile=networking_profile,
        networking_access=access,
        has_registration=registered,
        registration_verified=paid,
        unread_notifications=unread or 0,
    )


@router.post("/profile/photo")
async def upload_profile_photo(
    photo: UploadFile = File(...),
    user: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set or replace the member's profile photo. Allowed before email
    verification so it can be part of signup; nobody else can see an
    account's photo until it has Networking access."""
    enforce(f"profile-photo:{user.id}", 10, 3600, "Too many photo uploads. Please try again later.")
    new_key = await save_profile_photo(photo)
    old_key = user.photo_key
    user.photo_key = new_key
    try:
        await db.commit()
    except Exception:
        await delete_profile_photo(new_key)  # don't leak an unreferenced file
        raise
    await delete_profile_photo(old_key)  # only after the new one is committed
    await reward_hooks.profile_changed(user.id)
    return {"photo_url": photo_url_for(user.id, new_key)}


@router.delete("/profile/photo", status_code=status.HTTP_204_NO_CONTENT)
async def remove_profile_photo(
    user: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    old_key = user.photo_key
    user.photo_key = None
    await db.commit()
    await delete_profile_photo(old_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/members/{user_id}/photo")
async def member_photo(
    user_id: str,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """A member's photo. Visible to its owner, and to members with Networking
    access when the photo's owner is also an active member — the same rule
    as the directory. Everything else is a 404 (no hint the account exists)."""
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    if user_id != viewer.id:
        if not await has_networking_access(db, viewer) or not await is_active_member(db, user_id):
            raise not_found
    key = await db.scalar(select(User.photo_key).where(User.id == user_id))
    if not key:
        raise not_found
    data = await read_profile_photo(key)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            # The URL carries the photo's version (?v=), so it never changes
            # content: cache it in this browser only, for good.
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.put("/profile/personal", response_model=PersonalProfileOut)
async def upsert_personal_profile(
    payload: PersonalProfileIn,
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> PersonalProfile:
    profile = await db.get(PersonalProfile, user.id)
    if profile is None:
        profile = PersonalProfile(user_id=user.id, **payload.model_dump())
        db.add(profile)
    else:
        # exclude_unset: a field the form didn't send (e.g. profile_photo_url)
        # keeps its value instead of being reset to the schema default.
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(profile, key, value)
        profile.completed_at = profile.completed_at or utcnow()
    await db.commit()
    await reward_hooks.profile_changed(user.id)
    return profile


@router.put("/business", response_model=BusinessOut)
async def upsert_business(
    payload: BusinessIn,
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> BusinessOut:
    business = await _primary_business(db, user.id)
    if business is None:
        business = Business(user_id=user.id, **payload.model_dump())
        db.add(business)
    else:
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(business, key, value)
    await db.commit()
    await reward_hooks.profile_changed(user.id)
    return _business_out(business, await has_verified_registration(db, user))


@router.get("/networking/members", response_model=list[MemberListItem])
async def member_directory(
    q: str | None = None,
    category: str | None = None,
    city: str | None = None,
    open_to_mentoring: bool | None = None,
    _: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[MemberListItem]:
    filters = [await active_member_clause(db, NetworkingProfile.user_id)]
    if category:
        filters.append(Business.category == category)
    if city:
        filters.append(func.lower(Business.city).like(f"%{city.lower().strip()}%"))
    if open_to_mentoring is not None:
        filters.append(NetworkingProfile.open_to_mentoring == open_to_mentoring)
    if q:
        needle = f"%{q.lower().strip()}%"
        filters.append(or_(func.lower(Business.business_name).like(needle), func.lower(PersonalProfile.full_name).like(needle)))
    rows = await db.execute(
        select(NetworkingProfile, Business, PersonalProfile, User.photo_key)
        .join(Business, Business.id == NetworkingProfile.business_id)
        .join(PersonalProfile, PersonalProfile.user_id == NetworkingProfile.user_id)
        .join(User, User.id == NetworkingProfile.user_id)
        .where(*filters)
        .order_by(Business.business_name.asc())
        .limit(50)
    )
    found = rows.all()
    registrants = await verified_registrant_ids(db, {p.user_id for p, _, _, _ in found})
    return [
        MemberListItem(
            member_id=p.id,
            user_id=p.user_id,
            founder_name=profile.full_name,
            business_name=b.business_name,
            category=b.category,
            city=p.city or b.city,
            headline=p.headline,
            tgl_verified=b.tgl_verified or p.user_id in registrants,
            open_to_mentoring=p.open_to_mentoring,
            trust_score=p.trust_score,
            photo_url=photo_url_for(p.user_id, photo_key),
        )
        for p, b, profile, photo_key in found
    ]


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/networking/members/search", response_model=MemberSearchOut)
async def member_search(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=8, ge=1, le=20),
    offset: int = Query(default=0, ge=0, le=500),
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> MemberSearchOut:
    """Typeahead for choosing who receives a referral. Server-side filtered and
    paged; returns only what is needed to recognise a member, never contact
    details. Excludes the caller and anyone who is not an active member."""
    enforce(f"member-search:{user.id}", 240, 60, "Searching too fast. Please wait a moment.")
    filters = [
        await active_member_clause(db, NetworkingProfile.user_id),
        NetworkingProfile.user_id != user.id,
        User.is_active.is_(True),
    ]
    terms = q.lower().split()[:5]
    for term in terms:
        like = f"%{_like_escape(term)}%"
        codes = [c for c, name in CATEGORY_NAMES.items() if term in name.lower()]
        options = [
            func.lower(PersonalProfile.full_name).like(like, escape="\\"),
            func.lower(Business.business_name).like(like, escape="\\"),
            func.lower(PersonalProfile.role).like(like, escape="\\"),
            func.lower(func.coalesce(NetworkingProfile.city, Business.city)).like(like, escape="\\"),
        ]
        if codes:
            options.append(Business.category.in_(codes))
        filters.append(or_(*options))

    if terms:
        # Best matches first: name/business starts with the first word, then a
        # whole-word hit in name/business/profession, then everything else
        # (city or category-name matches).
        starts, word = f"{_like_escape(terms[0])}%", f"% {_like_escape(terms[0])}%"
        fields = (PersonalProfile.full_name, Business.business_name)
        rank = case(
            *[(func.lower(f).like(starts, escape="\\"), 0) for f in fields],
            *[(func.lower(f).like(word, escape="\\"), 1) for f in (*fields, PersonalProfile.role)],
            else_=2,
        )
        order = [rank, Business.business_name.asc()]
    else:
        # Suggestions: members I have referred to before come first.
        last = (
            select(func.max(BusinessReferral.created_at))
            .where(BusinessReferral.giver_user_id == user.id, BusinessReferral.receiver_user_id == NetworkingProfile.user_id)
            .correlate(NetworkingProfile)
            .scalar_subquery()
        )
        order = [last.desc().nulls_last(), Business.business_name.asc()]
    rows = (await db.execute(
        select(NetworkingProfile.id, NetworkingProfile.user_id, PersonalProfile.full_name, PersonalProfile.role,
               Business.business_name, Business.category, func.coalesce(NetworkingProfile.city, Business.city), User.photo_key)
        .join(Business, Business.id == NetworkingProfile.business_id)
        .join(PersonalProfile, PersonalProfile.user_id == NetworkingProfile.user_id)
        .join(User, User.id == NetworkingProfile.user_id)
        .where(*filters)
        .order_by(*order, NetworkingProfile.id)
        .limit(limit + 1).offset(offset)
    )).all()
    return MemberSearchOut(
        has_more=len(rows) > limit,
        items=[
            MemberSearchItem(
                member_id=mid, user_id=uid, name=name, business_name=biz, profession=role, category=cat,
                category_name=CATEGORY_NAMES.get(cat), city=city, photo_url=photo_url_for(uid, photo_key),
            )
            for mid, uid, name, role, biz, cat, city, photo_key in rows[:limit]
        ],
    )


@router.get("/networking/members/{member_id}", response_model=MemberDetail)
async def member_detail(
    member_id: str,
    _: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> MemberDetail:
    row = (
        await db.execute(
            select(NetworkingProfile, Business, PersonalProfile, User.photo_key)
            .join(Business, Business.id == NetworkingProfile.business_id)
            .join(PersonalProfile, PersonalProfile.user_id == NetworkingProfile.user_id)
            .join(User, User.id == NetworkingProfile.user_id)
            .where(NetworkingProfile.id == member_id, await active_member_clause(db, NetworkingProfile.user_id))
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    p, b, profile, photo_key = row
    given = await db.scalar(select(func.count()).select_from(BusinessReferral).where(BusinessReferral.giver_user_id == p.user_id)) or 0
    received = await db.scalar(select(func.count()).select_from(BusinessReferral).where(BusinessReferral.receiver_user_id == p.user_id)) or 0
    return MemberDetail(
        member_id=p.id,
        user_id=p.user_id,
        founder_name=profile.full_name,
        business_name=b.business_name,
        category=b.category,
        city=p.city or b.city,
        headline=p.headline,
        tgl_verified=b.tgl_verified or bool(await verified_registrant_ids(db, {p.user_id})),
        open_to_mentoring=p.open_to_mentoring,
        business_description=b.description,
        founder_story=p.founder_story,
        interests=p.interests,
        seeking_mentor=p.seeking_mentor,
        trust_score=p.trust_score,
        growth_points=p.growth_points,
        referrals_given=given,
        referrals_received=received,
        photo_url=photo_url_for(p.user_id, photo_key),
    )


async def _need_rows(db: AsyncSession, viewer: User, mine: bool) -> list[BusinessNeedOut]:
    # the offer figures ride along in the same single query (correlated sub-selects), so the board costs no more round trips than before
    offers_count = select(func.count(NeedHelpOffer.id)).where(NeedHelpOffer.need_id == BusinessNeed.id).correlate(BusinessNeed).scalar_subquery()
    my_offer_id = select(NeedHelpOffer.id).where(NeedHelpOffer.need_id == BusinessNeed.id, NeedHelpOffer.helper_user_id == viewer.id).correlate(BusinessNeed).scalar_subquery()
    my_offer_status = select(NeedHelpOffer.status).where(NeedHelpOffer.need_id == BusinessNeed.id, NeedHelpOffer.helper_user_id == viewer.id).correlate(BusinessNeed).scalar_subquery()
    q = (
        select(BusinessNeed, Business, PersonalProfile, User.photo_key, offers_count, my_offer_id, my_offer_status)
        .join(Business, Business.id == BusinessNeed.business_id)
        .join(PersonalProfile, PersonalProfile.user_id == BusinessNeed.user_id)
        .join(User, User.id == BusinessNeed.user_id)
    )
    if mine:
        q = q.where(BusinessNeed.user_id == viewer.id)           # my own needs, whatever their status (a resolved or cancelled need leaves the board)
    else:
        q = q.where(BusinessNeed.status == "OPEN")
    rows = (await db.execute(q.order_by(BusinessNeed.created_at.desc()).limit(100))).all()
    return [
        BusinessNeedOut(
            id=n.id,
            title=n.title,
            category=n.category,
            description=n.description,
            status=n.status,
            poster_user_id=n.user_id,
            poster_name=profile.full_name,
            business_name=b.business_name,
            city=profile.city or b.city,
            created_at=n.created_at,
            poster_photo_url=photo_url_for(n.user_id, photo_key),
            offers_count=int(count or 0) if n.user_id == viewer.id else None,
            my_offer_id=oid,
            my_offer_status=ost,
            resolved_offer_id=n.resolved_offer_id if n.user_id == viewer.id else None,
        )
        for n, b, profile, photo_key, count, oid, ost in rows
    ]


@router.get("/networking/needs", response_model=list[BusinessNeedOut])
async def list_needs(
    mine: bool = Query(default=False),
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[BusinessNeedOut]:
    return await _need_rows(db, user, mine)


@router.post("/networking/needs", response_model=BusinessNeedOut, status_code=status.HTTP_201_CREATED)
async def create_need(
    payload: BusinessNeedCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> BusinessNeedOut:
    enforce(f"need-publish:{user.id}", 10, 3600, "You are posting needs too quickly. Please try again later.")
    business = await _primary_business(db, user.id)
    if business is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete your business profile first.")
    profile = (
        await db.execute(select(PersonalProfile).where(PersonalProfile.user_id == user.id))
    ).scalar_one_or_none()
    user_id, business_id = user.id, business.id            # plain values: a rejected publication may roll the session back
    try:
        need = await community.publish_need(db, user, business_id, payload.title, payload.category, payload.description)
    except community.NeedRejected as rejected:
        # the rejection is itself a recorded fact (it is how quality attempts are measured), committed on its own before the error is returned
        community.record(db, "NEED", "REJECTED", actor=user_id, reason=rejected.code, details={"description_chars": len((payload.description or "").strip())})
        await db.commit()
        raise HTTPException(rejected.http_status, rejected.message)
    await db.commit()
    return BusinessNeedOut(
        id=need.id,
        title=need.title,
        category=need.category,
        description=need.description,
        status=need.status,
        poster_user_id=user.id,
        poster_name=profile.full_name if profile else "Member",
        business_name=business.business_name,
        city=(profile.city if profile else None) or business.city,
        created_at=need.created_at,
        poster_photo_url=user.photo_url,
        offers_count=0,
    )


@router.post("/networking/needs/{need_id}/help", status_code=status.HTTP_204_NO_CONTENT)
async def help_need(
    need_id: str,
    payload: NeedOfferCreate | None = None,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """"I can help": now a stored OFFER (who offered, when, and what the poster did with it), not only a notification. It records an offer, which is
    not evidence that help was given, and it earns nothing. Repeating the call changes nothing and notifies nobody twice."""
    enforce(f"help-offer:{user.id}", 30, 3600, "You are offering help too quickly. Please try again later.")
    need = await db.get(BusinessNeed, need_id)
    if need is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found")
    if need.user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot offer help on your own need.")
    if need.status != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, "This need is no longer open.")
    offer, created = await community.create_offer(db, need, user, payload.message if payload else None)
    if created:
        notify(
            db,
            need.user_id,
            "need_help_offered",
            f"{await _who(db, user.id)} can help with your need",
            f"Your need: {need.title}",
            "business_need",
            need.id,
            actor_user_id=user.id,
        )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/networking/connections", response_model=list[ConnectionOut])
async def list_connections(
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[Connection]:
    """Every connection row the member is part of, in either direction. The
    caller works out each pair's state: ACCEPTED = connected; PENDING/DECLINED as
    requester = "requested"; PENDING as target = an invitation waiting on them."""
    rows = await db.execute(
        select(Connection)
        .where(or_(Connection.requester_user_id == user.id, Connection.target_user_id == user.id))
        .order_by(Connection.created_at.desc())
    )
    return rows.scalars().all()


@router.post("/networking/connections", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Connection:
    enforce(f"connect:{user.id}", 30, 3600, "You are sending connection requests too quickly. Please try again later.")
    if payload.target_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot connect with yourself.")
    if not await is_active_member(db, payload.target_user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Target is not an active Networking member.")
    # Both members are locked (always in the same order) BEFORE the pair is read, so two crossing requests, or a double click, are serialised; the
    # partial unique index on the hashed pair is the backstop that holds on every database and worker. A request that loses a race sees the winner
    # on its second pass (and then accepts it, or reports a duplicate).
    me_id, target_id = user.id, payload.target_user_id          # plain values: a rolled-back session expires the ORM objects
    pair_key = community.pair_hash(me_id, target_id)
    for attempt in (1, 2):
        await community.lock_users(db, [me_id, target_id])
        pair = (await db.execute(
            select(Connection).where(or_(
                and_(Connection.requester_user_id == me_id, Connection.target_user_id == target_id),
                and_(Connection.requester_user_id == target_id, Connection.target_user_id == me_id),
            )).execution_options(populate_existing=True)
        )).scalars().all()
        mine = next((c for c in pair if c.requester_user_id == me_id), None)
        theirs = next((c for c in pair if c.requester_user_id == target_id), None)
        if (mine and mine.status == "ACCEPTED") or (theirs and theirs.status == "ACCEPTED"):
            raise HTTPException(status.HTTP_409_CONFLICT, "You are already connected with this member.")
        if mine:
            raise HTTPException(status.HTTP_409_CONFLICT, "You already sent a connection request to this member.")
        if theirs:
            # They already asked me (or I had set their request aside): asking them back is
            # the same as accepting, so the two become connected instead of crossing requests.
            theirs_id, theirs_requester = theirs.id, theirs.requester_user_id
            if not await community.move_connection(db, theirs_id, ("PENDING", "DECLINED"), "ACCEPTED"):
                await db.rollback()              # someone else already answered it: look again, once
                if attempt == 2:
                    raise HTTPException(status.HTTP_409_CONFLICT, "You are already connected with this member.")
                continue
            await community.connection_event(db, "REQUESTED", me_id, target_id, actor=me_id, connection_id=theirs_id, extra={"crossing": True})
            await community.connection_event(db, "ACCEPTED", me_id, target_id, actor=me_id, connection_id=theirs_id, extra={"via": "crossing_request"})
            notify(
                db,
                theirs_requester,
                "connection_accepted",
                f"{await _who(db, me_id)} accepted your connection request",
                "You are now connected.",
                "connection",
                theirs_id,
                actor_user_id=me_id,
            )
            await db.commit()
            return await db.scalar(select(Connection).where(Connection.id == theirs_id).execution_options(populate_existing=True))
        conn = Connection(requester_user_id=me_id, target_user_id=target_id, note=payload.note, pair_key=pair_key)
        db.add(conn)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()          # a crossing request won the race: look again, once
            if attempt == 2:
                raise HTTPException(status.HTTP_409_CONFLICT, "A connection request between you and this member already exists.")
            continue
        await community.connection_event(db, "REQUESTED", me_id, target_id, actor=me_id, connection_id=conn.id)
        notify(
            db,
            target_id,
            "connection_request",
            f"{await _who(db, me_id)} wants to connect",
            payload.note or "No message was added.",
            "connection",
            conn.id,
            actor_user_id=me_id,
        )
        await db.commit()
        return conn


@router.patch("/networking/connections/{connection_id}", response_model=ConnectionOut)
async def respond_to_connection(
    connection_id: str,
    payload: ConnectionRespond,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Connection:
    """The member a request was sent to accepts or declines it. Only the target
    may answer; anyone else gets a 404 (no hint the request exists)."""
    conn = await db.get(Connection, connection_id)
    if conn is None or conn.target_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection request not found.")
    await community.lock_users(db, [conn.requester_user_id, conn.target_user_id])
    conn = await db.scalar(select(Connection).where(Connection.id == connection_id).execution_options(populate_existing=True))      # re-read under the lock
    if conn is None or conn.target_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection request not found.")      # withdrawn while this request waited
    if conn.status == "ACCEPTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already connected with this member.")
    if payload.action == "decline":
        if conn.status == "DECLINED":
            return conn  # already set aside; repeating it changes nothing
        if not await community.move_connection(db, conn.id, ("PENDING",), "DECLINED"):      # silent: the requester is not notified
            raise HTTPException(status.HTTP_409_CONFLICT, "This request was just answered.")
        await community.connection_event(db, "DECLINED", conn.requester_user_id, conn.target_user_id, actor=user.id, connection_id=conn.id)
        await db.commit()
        await db.refresh(conn)
        return conn
    if not await is_active_member(db, conn.requester_user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That member is no longer an active Networking member.")
    if not await community.move_connection(db, conn.id, ("PENDING", "DECLINED"), "ACCEPTED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already connected with this member.")
    await community.connection_event(db, "ACCEPTED", conn.requester_user_id, conn.target_user_id, actor=user.id, connection_id=conn.id)
    notify(
        db,
        conn.requester_user_id,
        "connection_accepted",
        f"{await _who(db, user.id)} accepted your connection request",
        "You are now connected.",
        "connection",
        conn.id,
        actor_user_id=user.id,
    )
    await db.commit()
    await db.refresh(conn)
    return conn


@router.delete("/networking/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_connection(
    connection_id: str,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Withdraw a request you sent, or remove an existing connection (either side
    may). Silent either way. A pending request can only be taken back by the one
    who sent it; the recipient uses decline. The current-state row goes, as before;
    the HISTORY stays: a withdrawal or removal is recorded as an event, so a pair
    that was connected is remembered and a later request is a reconnection."""
    conn = await db.get(Connection, connection_id)
    if conn is None or user.id not in {conn.requester_user_id, conn.target_user_id}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found.")
    await community.lock_users(db, [conn.requester_user_id, conn.target_user_id])
    conn = await db.scalar(select(Connection).where(Connection.id == connection_id).execution_options(populate_existing=True))
    if conn is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)      # already removed by the other member: the end state is the one asked for
    if conn.status != "ACCEPTED" and conn.requester_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the sender can withdraw a request.")
    requester_id, target_id_, conn_id, was = conn.requester_user_id, conn.target_user_id, conn.id, conn.status
    if was == "ACCEPTED":
        # A connection is mutual and an old mutual request can leave a row each way:
        # remove the whole pair, or the two would still read as connected.
        pair = or_(
            and_(Connection.requester_user_id == requester_id, Connection.target_user_id == target_id_),
            and_(Connection.requester_user_id == target_id_, Connection.target_user_id == requester_id),
        )
        removed = (await db.execute(delete(Connection).where(pair))).rowcount
        if removed:        # only the request that actually removed it records it, so two simultaneous removals write one event
            await community.connection_event(db, "REMOVED", requester_id, target_id_, actor=user.id, connection_id=conn_id,
                                             extra={"removed_by": "requester" if user.id == requester_id else "target"})
    else:
        removed = (await db.execute(delete(Connection).where(Connection.id == conn_id))).rowcount
        if removed:
            await community.connection_event(db, "WITHDRAWN", requester_id, target_id_, actor=user.id, connection_id=conn_id, extra={"from_status": was})
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/networking/referral-requests", status_code=status.HTTP_204_NO_CONTENT)
async def create_referral_request(
    payload: ReferralRequestCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if payload.target_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot request a referral from yourself.")
    if not await is_active_member(db, payload.target_user_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Target is not an active Networking member.")
    req = ReferralRequest(requester_user_id=user.id, target_user_id=payload.target_user_id, note=payload.note)
    db.add(req)
    await db.flush()
    notify(
        db,
        payload.target_user_id,
        "referral_requested",
        f"{await _who(db, user.id)} is asking you for a referral",
        payload.note or "No details were added.",
        "referral_request",
        req.id,
        actor_user_id=user.id,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/business/verification/start", response_model=BusinessOut)
async def start_verification(
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> BusinessOut:
    business = await _primary_business(db, user.id)
    if business is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete your business profile first.")
    if await has_verified_registration(db, user):
        # Already verified by virtue of a payment-verified Season 1
        # registration — nothing to submit, and a PENDING row would only
        # confuse the admin.
        return _business_out(business, True)
    if business.verification_status in ("NOT_STARTED", "REJECTED"):
        business.verification_status = "PENDING"
        business.verification_submitted_at = utcnow()
        await db.commit()
    return business


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    rows = await db.execute(
        select(Notification).where(Notification.recipient_user_id == user.id).order_by(Notification.created_at.desc()).limit(100)
    )
    items = rows.scalars().all()

    # Context per notification, from the entity it points at. Every lookup is
    # scoped to entities the recipient is a party to, so a notification can
    # never be used to read someone else's connection or referral.
    details: dict[str, dict] = {}
    actors: dict[str, str] = {}
    # Batch-load every linked entity per type (one IN query each) instead of
    # one lookup per notification.
    wanted: dict[str, set[str]] = {}
    for n in items:
        if n.related_entity_id and n.related_entity_type:
            wanted.setdefault(n.related_entity_type, set()).add(n.related_entity_id)
    by_type = {"connection": Connection, "referral_request": ReferralRequest, "business_referral": BusinessReferral, "business_need": BusinessNeed}
    loaded: dict[str, dict] = {}
    for kind, ids in wanted.items():
        model = by_type.get(kind)
        if model is not None:
            loaded[kind] = {e.id: e for e in (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()}
    get = lambda kind, entity_id: loaded.get(kind, {}).get(entity_id)  # noqa: E731
    for n in items:
        if n.actor_user_id:
            actors[n.id] = n.actor_user_id
        if not n.related_entity_id:
            continue
        if n.related_entity_type == "connection":
            c = get("connection", n.related_entity_id)
            if c and c.target_user_id == user.id:
                details[n.id] = {"note": c.note, "connection_status": c.status}
                actors.setdefault(n.id, c.requester_user_id)
        elif n.related_entity_type == "referral_request":
            r = get("referral_request", n.related_entity_id)
            if r and r.target_user_id == user.id:
                details[n.id] = {"note": r.note}
                actors.setdefault(n.id, r.requester_user_id)
        elif n.related_entity_type == "business_referral":
            r = get("business_referral", n.related_entity_id)
            if r and user.id in {r.giver_user_id, r.receiver_user_id}:
                details[n.id] = {
                    "business_need": r.business_need,
                    "note": r.note,
                    "prospect_company": r.prospect_company,
                    "urgency": r.urgency,
                    "status": r.status,
                    "you_are": "receiver" if r.receiver_user_id == user.id else "giver",
                }
                actors.setdefault(n.id, r.giver_user_id if r.receiver_user_id == user.id else r.receiver_user_id)
        elif n.related_entity_type == "business_need":
            need = get("business_need", n.related_entity_id)
            if need and need.user_id == user.id:
                details[n.id] = {"need_title": need.title, "need_description": need.description, "need_status": need.status}

    # All senders in one query (deleted accounts simply don't come back).
    actor_out = await _people(db, set(actors.values()))

    return [
        NotificationOut(
            id=n.id,
            type=n.type,
            title=n.title,
            body=n.body,
            related_entity_type=n.related_entity_type,
            related_entity_id=n.related_entity_id,
            read_at=n.read_at,
            created_at=n.created_at,
            actor=actor_out.get(actors.get(n.id, "")),
            detail=details.get(n.id),
        )
        for n in items
    ]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Notification:
    item = await db.get(Notification, notification_id)
    if item is None or item.recipient_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    item.read_at = item.read_at or utcnow()
    await db.commit()
    return item


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    user: User = Depends(get_current_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    rows = await db.execute(select(Notification).where(Notification.recipient_user_id == user.id, Notification.read_at.is_(None)))
    now = utcnow()
    for item in rows.scalars().all():
        item.read_at = now
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
