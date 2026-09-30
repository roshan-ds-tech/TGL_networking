"""Authenticated customer/product API for the P0 TGL slice."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import (
    Business,
    BusinessNeed,
    BusinessReferral,
    Connection,
    EventRegistration,
    NetworkingProfile,
    Notification,
    PersonalProfile,
    ReferralRequest,
    TGLMembership,
    User,
    UserVerificationToken,
    utcnow,
)
from ..ratelimit import client_ip, enforce, reset
from ..schemas import (
    AuthOut,
    BusinessIn,
    BusinessNeedCreate,
    BusinessNeedOut,
    BusinessOut,
    ConnectionCreate,
    ConnectionOut,
    CustomerLogin,
    CustomerOut,
    CustomerSignup,
    ForgotPasswordIn,
    MemberDetail,
    MemberListItem,
    MembershipOut,
    MyStatusOut,
    NetworkingProfileOut,
    NotificationOut,
    OtpRequestIn,
    OtpRequestOut,
    OtpVerifyIn,
    PersonalProfileIn,
    PersonalProfileOut,
    ReferralCreate,
    ReferralOut,
    ReferralRequestCreate,
    ReferralTransition,
    ResetPasswordIn,
)
from ..security import (
    CSRF_HEADER,
    CUSTOMER_CSRF_COOKIE,
    CUSTOMER_SESSION_COOKIE,
    burn_timing,
    create_customer_session_token,
    get_current_user,
    get_user_by_email,
    hash_password,
    new_csrf_token,
    require_active_networking_member,
    require_customer_csrf,
    require_verified_user,
    verify_password,
)
from ..email_service import send_login_otp_email, send_password_reset_email, send_verification_email
from ..services import get_or_create_season_1, new_reset_token, new_verification_token, notify, token_hash

router = APIRouter(prefix="/api/v1", tags=["customer"])

_GENERIC = "Invalid email or password."
_REFERRAL_TRANSITIONS = {
    "GIVEN": {"ACCEPTED", "DECLINED", "CANCELLED"},
    "ACCEPTED": {"MEETING_DONE", "CANCELLED"},
    "MEETING_DONE": {"BUSINESS_CLOSED", "CANCELLED"},
    "BUSINESS_CLOSED": {"REVENUE_GENERATED"},
    "REVENUE_GENERATED": set(),
    "DECLINED": set(),
    "CANCELLED": set(),
}


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
    user = User(email=email, password_hash=hash_password(payload.password))
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
    await db.commit()
    await db.refresh(user)
    reset(f"customer-register:{ip}")
    await send_verification_email(user.email, raw)
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
        burn_timing()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)
    now = datetime.now(timezone.utc)
    locked_until = user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until and user.locked_until.tzinfo is None else user.locked_until
    if locked_until and locked_until > now:
        burn_timing()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)
    if not user.is_active or not verify_password(payload.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_attempts = 0
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)
    user.failed_attempts = 0
    user.locked_until = None
    await db.commit()
    await db.refresh(user)
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
    await db.refresh(user)
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
    await db.commit()
    await send_verification_email(user.email, raw)
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
        await db.commit()
        await send_login_otp_email(user.email, raw)
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
    user = await get_user_by_email(db, email)
    if user is None:
        burn_timing()
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
    await db.commit()
    reset(f"otp-verify:{ip}")
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
        db.add(UserVerificationToken(user_id=user.id, token_hash=token_hash(raw), purpose="PASSWORD_RESET", expires_at=utcnow() + timedelta(minutes=30)))
        await db.commit()
        origin = settings.public_origins[0] if settings.public_origins else settings.public_origin.rstrip("/")
        await send_password_reset_email(user.email, f"{origin}/reset-password?token={raw}")
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
    user.password_hash = hash_password(payload.new_password)
    user.failed_attempts = 0
    user.locked_until = None
    row.used_at = utcnow()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/status", response_model=MyStatusOut)
async def status_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyStatusOut:
    event = await get_or_create_season_1(db)
    profile = await db.get(PersonalProfile, user.id)
    business = await _primary_business(db, user.id)
    reg = await _current_registration(db, user.id)
    membership = await _current_membership(db, user.id)
    networking_profile = await db.scalar(select(NetworkingProfile).where(NetworkingProfile.user_id == user.id))
    unread = await db.scalar(
        select(func.count()).select_from(Notification).where(Notification.recipient_user_id == user.id, Notification.read_at.is_(None))
    ) or 0
    return MyStatusOut(
        user=user,
        personal_profile=profile,
        business=business,
        event=event,
        event_registration=None
        if reg is None
        else {"id": reg.id, "status": reg.status, "payment_status": reg.payment_status, "submitted_at": reg.submitted_at, "confirmed_at": reg.confirmed_at},
        membership=_membership_out(membership),
        networking_profile=networking_profile,
        unread_notifications=unread,
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
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
        profile.completed_at = profile.completed_at or utcnow()
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/business", response_model=BusinessOut)
async def upsert_business(
    payload: BusinessIn,
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Business:
    business = await _primary_business(db, user.id)
    if business is None:
        business = Business(user_id=user.id, **payload.model_dump())
        db.add(business)
    else:
        for key, value in payload.model_dump().items():
            setattr(business, key, value)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/networking/members", response_model=list[MemberListItem])
async def member_directory(
    q: str | None = None,
    category: str | None = None,
    city: str | None = None,
    open_to_mentoring: bool | None = None,
    _: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[MemberListItem]:
    filters = [TGLMembership.status == "ACTIVE", TGLMembership.expires_at > utcnow()]
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
        select(NetworkingProfile, Business, PersonalProfile)
        .join(Business, Business.id == NetworkingProfile.business_id)
        .join(PersonalProfile, PersonalProfile.user_id == NetworkingProfile.user_id)
        .join(TGLMembership, TGLMembership.user_id == NetworkingProfile.user_id)
        .where(*filters)
        .order_by(Business.business_name.asc())
        .limit(50)
    )
    return [
        MemberListItem(
            member_id=p.id,
            user_id=p.user_id,
            founder_name=profile.full_name,
            business_name=b.business_name,
            category=b.category,
            city=p.city or b.city,
            headline=p.headline,
            tgl_verified=b.tgl_verified,
            open_to_mentoring=p.open_to_mentoring,
            trust_score=p.trust_score,
        )
        for p, b, profile in rows.all()
    ]


@router.get("/networking/members/{member_id}", response_model=MemberDetail)
async def member_detail(
    member_id: str,
    _: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> MemberDetail:
    row = (
        await db.execute(
            select(NetworkingProfile, Business, PersonalProfile)
            .join(Business, Business.id == NetworkingProfile.business_id)
            .join(PersonalProfile, PersonalProfile.user_id == NetworkingProfile.user_id)
            .join(TGLMembership, TGLMembership.user_id == NetworkingProfile.user_id)
            .where(NetworkingProfile.id == member_id, TGLMembership.status == "ACTIVE", TGLMembership.expires_at > utcnow())
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    p, b, profile = row
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
        tgl_verified=b.tgl_verified,
        open_to_mentoring=p.open_to_mentoring,
        business_description=b.description,
        founder_story=p.founder_story,
        interests=p.interests,
        seeking_mentor=p.seeking_mentor,
        trust_score=p.trust_score,
        growth_points=p.growth_points,
        referrals_given=given,
        referrals_received=received,
    )


@router.get("/referrals", response_model=list[ReferralOut])
async def list_referrals(
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[ReferralOut]:
    rows = await db.execute(
        select(BusinessReferral)
        .where(or_(BusinessReferral.giver_user_id == user.id, BusinessReferral.receiver_user_id == user.id))
        .order_by(BusinessReferral.created_at.desc())
    )
    refs = rows.scalars().all()
    party_ids = {uid for r in refs for uid in (r.giver_user_id, r.receiver_user_id)}
    names: dict[str, tuple[str, str]] = {}
    if party_ids:
        party_rows = await db.execute(
            select(PersonalProfile, Business)
            .join(Business, Business.user_id == PersonalProfile.user_id)
            .where(PersonalProfile.user_id.in_(party_ids))
            .order_by(Business.created_at.asc())
        )
        for profile, business in party_rows.all():
            names.setdefault(profile.user_id, (profile.full_name, business.business_name))
    return [
        ReferralOut(
            id=r.id,
            giver_user_id=r.giver_user_id,
            receiver_user_id=r.receiver_user_id,
            giver_name=names.get(r.giver_user_id, (None, None))[0],
            giver_business=names.get(r.giver_user_id, (None, None))[1],
            receiver_name=names.get(r.receiver_user_id, (None, None))[0],
            receiver_business=names.get(r.receiver_user_id, (None, None))[1],
            business_need=r.business_need,
            note=r.note,
            status=r.status,
            accepted_at=r.accepted_at,
            meeting_done_at=r.meeting_done_at,
            business_closed_at=r.business_closed_at,
            revenue_generated_at=r.revenue_generated_at,
            cancelled_at=r.cancelled_at,
            declined_at=r.declined_at,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in refs
    ]


@router.post("/referrals", response_model=ReferralOut, status_code=status.HTTP_201_CREATED)
async def create_referral(
    payload: ReferralCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> BusinessReferral:
    if payload.receiver_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot refer yourself.")
    receiver = await db.get(User, payload.receiver_user_id)
    if receiver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receiver not found")
    active = await db.scalar(
        select(func.count())
        .select_from(TGLMembership)
        .where(
            TGLMembership.user_id == receiver.id,
            TGLMembership.status == "ACTIVE",
            TGLMembership.expires_at > utcnow(),
        )
    )
    if not active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Receiver is not an active Networking member.")
    ref = BusinessReferral(giver_user_id=user.id, receiver_user_id=payload.receiver_user_id, business_need=payload.business_need, note=payload.note)
    db.add(ref)
    notify(db, payload.receiver_user_id, "referral_received", "New referral received", payload.business_need, "business_referral", ref.id)
    await db.commit()
    await db.refresh(ref)
    return ref


@router.patch("/referrals/{referral_id}", response_model=ReferralOut)
async def transition_referral(
    referral_id: str,
    payload: ReferralTransition,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> BusinessReferral:
    ref = await db.get(BusinessReferral, referral_id)
    if ref is None or user.id not in {ref.giver_user_id, ref.receiver_user_id}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Referral not found")
    next_status = payload.status.upper()
    if next_status not in _REFERRAL_TRANSITIONS.get(ref.status, set()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid referral transition.")
    ref.status = next_status
    stamp = utcnow()
    if next_status == "ACCEPTED":
        ref.accepted_at = stamp
    elif next_status == "MEETING_DONE":
        ref.meeting_done_at = stamp
    elif next_status == "BUSINESS_CLOSED":
        ref.business_closed_at = stamp
    elif next_status == "REVENUE_GENERATED":
        ref.revenue_generated_at = stamp
    elif next_status == "CANCELLED":
        ref.cancelled_at = stamp
    elif next_status == "DECLINED":
        ref.declined_at = stamp
    recipient = ref.giver_user_id if user.id == ref.receiver_user_id else ref.receiver_user_id
    notify(db, recipient, "referral_status_changed", "Referral status updated", f"Referral status changed to {next_status}.", "business_referral", ref.id)
    if next_status == "ACCEPTED":
        notify(db, ref.giver_user_id, "referral_accepted", "Referral accepted", "Your referral was accepted.", "business_referral", ref.id)
    await db.commit()
    await db.refresh(ref)
    return ref


@router.get("/networking/needs", response_model=list[BusinessNeedOut])
async def list_needs(
    _: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[BusinessNeedOut]:
    rows = await db.execute(
        select(BusinessNeed, Business, PersonalProfile)
        .join(Business, Business.id == BusinessNeed.business_id)
        .join(PersonalProfile, PersonalProfile.user_id == BusinessNeed.user_id)
        .where(BusinessNeed.status == "OPEN")
        .order_by(BusinessNeed.created_at.desc())
        .limit(100)
    )
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
        )
        for n, b, profile in rows.all()
    ]


@router.post("/networking/needs", response_model=BusinessNeedOut, status_code=status.HTTP_201_CREATED)
async def create_need(
    payload: BusinessNeedCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> BusinessNeedOut:
    business = await _primary_business(db, user.id)
    if business is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete your business profile first.")
    profile = (
        await db.execute(select(PersonalProfile).where(PersonalProfile.user_id == user.id))
    ).scalar_one_or_none()
    need = BusinessNeed(user_id=user.id, business_id=business.id, title=payload.title, category=payload.category, description=payload.description)
    db.add(need)
    await db.commit()
    await db.refresh(need)
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
    )


@router.post("/networking/needs/{need_id}/help", status_code=status.HTTP_204_NO_CONTENT)
async def help_need(
    need_id: str,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    need = await db.get(BusinessNeed, need_id)
    if need is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found")
    if need.user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot offer help on your own need.")
    helper_business = await _primary_business(db, user.id)
    helper_name = helper_business.business_name if helper_business else "A member"
    notify(db, need.user_id, "need_help_offered", "Someone can help with your need", f"{helper_name} can help with: {need.title}", "business_need", need.id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/networking/connections", response_model=list[ConnectionOut])
async def list_connections(
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[Connection]:
    rows = await db.execute(select(Connection).where(Connection.requester_user_id == user.id))
    return rows.scalars().all()


@router.post("/networking/connections", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Connection:
    if payload.target_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot connect with yourself.")
    active = await db.scalar(
        select(func.count()).select_from(TGLMembership).where(
            TGLMembership.user_id == payload.target_user_id,
            TGLMembership.status == "ACTIVE",
            TGLMembership.expires_at > utcnow(),
        )
    )
    if not active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Target is not an active Networking member.")
    existing = await db.scalar(
        select(func.count()).select_from(Connection).where(
            Connection.requester_user_id == user.id, Connection.target_user_id == payload.target_user_id
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already sent a connection request to this member.")
    conn = Connection(requester_user_id=user.id, target_user_id=payload.target_user_id, note=payload.note)
    db.add(conn)
    notify(db, payload.target_user_id, "connection_request", "New connection request", payload.note or "Someone wants to connect with you.", "connection", conn.id)
    await db.commit()
    await db.refresh(conn)
    return conn


@router.post("/networking/referral-requests", status_code=status.HTTP_204_NO_CONTENT)
async def create_referral_request(
    payload: ReferralRequestCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if payload.target_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot request a referral from yourself.")
    active = await db.scalar(
        select(func.count()).select_from(TGLMembership).where(
            TGLMembership.user_id == payload.target_user_id,
            TGLMembership.status == "ACTIVE",
            TGLMembership.expires_at > utcnow(),
        )
    )
    if not active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Target is not an active Networking member.")
    req = ReferralRequest(requester_user_id=user.id, target_user_id=payload.target_user_id, note=payload.note)
    db.add(req)
    notify(db, payload.target_user_id, "referral_requested", "Referral requested", payload.note or "A member requested a referral from you.", "referral_request", req.id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/business/verification/start", response_model=BusinessOut)
async def start_verification(
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> Business:
    business = await _primary_business(db, user.id)
    if business is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete your business profile first.")
    if business.verification_status in ("NOT_STARTED", "REJECTED"):
        business.verification_status = "PENDING"
        business.verification_submitted_at = utcnow()
        await db.commit()
        await db.refresh(business)
    return business


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Notification]:
    rows = await db.execute(
        select(Notification).where(Notification.recipient_user_id == user.id).order_by(Notification.created_at.desc()).limit(100)
    )
    return rows.scalars().all()


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
    await db.refresh(item)
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
