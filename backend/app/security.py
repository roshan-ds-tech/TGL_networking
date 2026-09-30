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

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .config import settings
from .database import get_db
from .models import Admin, TGLMembership, User, utcnow

SESSION_COOKIE = "tgl_session"
CSRF_COOKIE = "tgl_csrf"
CUSTOMER_SESSION_COOKIE = "tgl_customer_session"
CUSTOMER_CSRF_COOKIE = "tgl_customer_csrf"
CSRF_HEADER = "x-csrf-token"
ALGORITHM = "HS256"

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

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


def burn_timing() -> None:
    """Spend the same work as a real verify, for unknown-user login attempts."""
    try:
        _hasher.verify(_DUMMY_HASH, "wrong")
    except Exception:
        pass


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


async def require_active_networking_member(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    now = utcnow()
    result = await db.execute(
        select(TGLMembership).where(
            TGLMembership.user_id == user.id,
            TGLMembership.membership_type == "NETWORKING",
            TGLMembership.status == "ACTIVE",
            TGLMembership.starts_at.is_not(None),
            TGLMembership.expires_at.is_not(None),
            TGLMembership.expires_at > now,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active Networking membership required")
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
