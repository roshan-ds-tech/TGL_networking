"""Authentication, CSRF and hashing primitives.

Design notes (these are the bits that matter under a pentest):
  * Session token lives in an HttpOnly + SameSite=Strict cookie, so it is not
    readable by JavaScript (XSS cannot exfiltrate it) and is not attached to
    cross-site requests (CSRF is largely neutralised at the browser level).
  * A second, readable CSRF cookie must be echoed back in a header —
    double-submit — which covers the residual CSRF surface.
  * Argon2id for password hashing: memory-hard, and no 72-byte truncation
    footgun like bcrypt has.
  * Login failures are constant-work: an unknown email still performs a dummy
    hash verification so response timing does not reveal which emails exist.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, func, or_, select

from .config import settings
from .database import get_db
from .observability import timed
from .services import SEASON_1_SLUG, EventSnapshot, add_calendar_months, season_1  # noqa: F401
from .models import Admin, Event, Registration, TGLMembership, User, utcnow

SESSION_COOKIE = "tgl_session"
CSRF_COOKIE = "tgl_csrf"
CUSTOMER_SESSION_COOKIE = "tgl_customer_session"
CUSTOMER_CSRF_COOKIE = "tgl_customer_csrf"
CSRF_HEADER = "x-csrf-token"
ALGORITHM = "HS256"

# Argon2id at the OWASP Password Storage Cheat Sheet's recommended minimum:
# 19 MiB memory, 2 iterations, 1 lane. (Was 64 MiB / 3 / 2 — ~5x the work,
# measured at ~1.3 s per hash on Render Free's CPU.) Each stored hash records
# its own parameters, so older hashes still verify; they are upgraded to these
# parameters the next time their owner logs in (needs_rehash below).
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)

# Pre-computed hash used to equalise timing when an email does not exist.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-comparison")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, Exception):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True for a valid hash made with different (older) parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


def burn_timing() -> None:
    """Spend the same work as a real verify, for unknown-user login attempts."""
    try:
        _hasher.verify(_DUMMY_HASH, "wrong")
    except Exception:
        pass


# Argon2id is deliberately expensive (64 MiB, 3 passes). Run it in a worker
# thread: argon2-cffi releases the GIL, so the event loop keeps serving every
# other request instead of freezing for the duration of each hash. Same
# parameters, same security — it just stops one login from stalling the site.
async def hash_password_async(password: str) -> str:
    async with timed("hash"):
        return await anyio.to_thread.run_sync(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    async with timed("hash"):
        return await anyio.to_thread.run_sync(verify_password, password, password_hash)


async def burn_timing_async() -> None:
    async with timed("hash"):
        await anyio.to_thread.run_sync(burn_timing)


def hash_ip(ip: str) -> str:
    """Salted, non-reversible IP fingerprint for abuse tracking."""
    return hashlib.sha256(f"{settings.secret_key}:{ip}".encode()).hexdigest()


def create_session_token(admin: Admin) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin.id,
        "ver": admin.token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_hours)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_customer_session_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "typ": "customer",
        "ver": user.token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_hours)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _unauthorised() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
    )


async def get_current_admin(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    if not session:
        raise _unauthorised()
    try:
        payload = jwt.decode(
            session,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        raise _unauthorised()

    admin = await db.get(Admin, payload.get("sub"))
    if admin is None or not admin.is_active:
        raise _unauthorised()

    # Token issued before a credential change / forced logout.
    if int(payload.get("ver", -1)) != admin.token_version:
        raise _unauthorised()

    return admin


async def get_current_user(
    session: str | None = Cookie(default=None, alias=CUSTOMER_SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not session:
        raise _unauthorised()
    try:
        payload = jwt.decode(
            session,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        raise _unauthorised()

    if payload.get("typ") != "customer":
        raise _unauthorised()

    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise _unauthorised()
    if int(payload.get("ver", -1)) != user.token_version:
        raise _unauthorised()
    return user


async def get_optional_user(
    session: str | None = Cookie(default=None, alias=CUSTOMER_SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Same checks as get_current_user, but None instead of 401.

    For endpoints that work for both anonymous visitors and logged-in
    customers (the public registration form), where "not logged in" is a
    normal case, not an error.
    """
    if not session:
        return None
    try:
        payload = jwt.decode(
            session,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "customer":
        return None
    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        return None
    if int(payload.get("ver", -1)) != user.token_version:
        return None
    return user


async def require_verified_user(user: User = Depends(get_current_user)) -> User:
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required")
    return user


async def require_customer_csrf(
    request: Request,
    csrf_cookie: str | None = Cookie(default=None, alias=CUSTOMER_CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid")


async def has_registration(db: AsyncSession, user: User) -> bool:
    """The account's verified email matches a row in the registrations table.
    The email is the link — which is why the login page tells people to use
    the one they registered with. Unverified emails never match, so nobody can
    claim another person's registration just by typing their address."""
    if user.email_verified_at is None:
        return False
    found = await db.scalar(
        select(Registration.id).where(func.lower(Registration.email) == user.email.lower()).limit(1)
    )
    return found is not None


async def finale_window(db: AsyncSession) -> tuple["EventSnapshot", datetime, datetime] | None:
    """(event, starts, expires) while the completed-Finale membership window is
    open; None before the Finale is completed or after the window closes.
    Reads the in-memory event snapshot (services.season_1), not the DB."""
    event = await season_1(db)
    if event.completed_at is None:
        return None
    started = event.completed_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    expires = add_calendar_months(started, event.membership_duration_months)
    return (event, started, expires) if utcnow() < expires else None


def _registration_exists(user: User, verified_only: bool = False):
    q = select(Registration.id).where(func.lower(Registration.email) == user.email.lower())
    if verified_only:
        q = q.where(Registration.verified.is_(True))
    return exists(q)


def _active_membership_exists(user_id_col):
    return exists(
        select(TGLMembership.id).where(
            TGLMembership.user_id == user_id_col,
            TGLMembership.membership_type == "NETWORKING",
            TGLMembership.status == "ACTIVE",
            TGLMembership.starts_at.is_not(None),
            TGLMembership.expires_at.is_not(None),
            TGLMembership.expires_at > utcnow(),
        )
    )


async def access_flags(db: AsyncSession, user: User) -> dict:
    """registered / paid / active_membership for one account in ONE query
    (each used to be its own round trip)."""
    if user.email_verified_at is None:
        row = (await db.execute(select(_active_membership_exists(user.id)))).one()
        return {"registered": False, "paid": False, "active_membership": bool(row[0])}
    row = (
        await db.execute(
            select(
                _registration_exists(user),
                _registration_exists(user, verified_only=True),
                _active_membership_exists(user.id),
            )
        )
    ).one()
    return {"registered": bool(row[0]), "paid": bool(row[1]), "active_membership": bool(row[2])}


def networking_access_from(flags: dict, window) -> bool:
    return (flags["registered"] and window is not None) or flags["active_membership"]


async def has_networking_access(db: AsyncSession, user: User) -> bool:
    """Networking opens for a registered email once an admin completes the
    Grand Finale, and stays open for the event's membership window (3 months).
    An individually activated membership also grants access."""
    return networking_access_from(await access_flags(db, user), await finale_window(db))


async def active_member_clause(db: AsyncSession, user_id_col):
    """SQL condition: `user_id_col` belongs to someone with Networking access.

    The set-based twin of has_networking_access, for queries over *other*
    members (directory, member pages, referral/connection targets) — they must
    use the same rule, or a public-form registrant could get in but never
    appear in, or be reachable from, the community.
    """
    membership_ids = select(TGLMembership.user_id).where(
        TGLMembership.membership_type == "NETWORKING",
        TGLMembership.status == "ACTIVE",
        TGLMembership.starts_at.is_not(None),
        TGLMembership.expires_at > utcnow(),
    )
    clause = user_id_col.in_(membership_ids)
    if await finale_window(db) is not None:
        registrant_ids = (
            select(User.id)
            .join(Registration, func.lower(Registration.email) == User.email)
            .where(User.email_verified_at.is_not(None))
        )
        clause = or_(clause, user_id_col.in_(registrant_ids))
    return clause


async def verified_registrant_ids(db: AsyncSession, user_ids: list[str] | set[str]) -> set[str]:
    """Which of these accounts hold a registration whose payment an admin has
    verified. Those — and only those — carry the TGL Verified badge
    automatically; an unpaid or unreviewed registration does not."""
    if not user_ids:
        return set()
    rows = await db.execute(
        select(User.id)
        .join(Registration, func.lower(Registration.email) == User.email)
        .where(
            User.id.in_(list(user_ids)),
            User.email_verified_at.is_not(None),
            Registration.verified.is_(True),
        )
    )
    return set(rows.scalars().all())


async def has_verified_registration(db: AsyncSession, user: User) -> bool:
    return user.id in await verified_registrant_ids(db, {user.id})


async def is_active_member(db: AsyncSession, user_id: str) -> bool:
    clause = await active_member_clause(db, User.id)
    return await db.scalar(select(User.id).where(User.id == user_id, clause).limit(1)) is not None


async def require_active_networking_member(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not await has_networking_access(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Networking opens after the Grand Finale for registered participants.",
        )
    return user


async def require_csrf(
    request: Request,
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    """Double-submit CSRF check for every state-changing admin request."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid")


async def get_admin_by_email(db: AsyncSession, email: str) -> Admin | None:
    result = await db.execute(select(Admin).where(Admin.email == email.lower().strip()))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    return result.scalar_one_or_none()
