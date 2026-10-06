"""Admin login / logout / session introspection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Admin, utcnow
from ..ratelimit import client_ip, enforce, reset
from ..schemas import AdminOut, LoginRequest
from ..security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    burn_timing_async,
    create_session_token,
    get_admin_by_email,
    get_current_admin,
    new_csrf_token,
    require_csrf,
    hash_password_async,
    needs_rehash,
    verify_password_async,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOCKOUT_MINUTES = 15
# Single generic message: never reveal whether the email exists or the account
# is locked, which would otherwise be a user-enumeration oracle.
_GENERIC = "Invalid email or password."


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    common = {
        "secure": settings.cookie_secure,
        "samesite": "strict",
        "path": "/",
        "max_age": settings.session_hours * 3600,
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)
    # Readable by JS on purpose: the SPA echoes it back in the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)


@router.post("/login", response_model=AdminOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Admin:
    ip = client_ip(request)
    enforce(
        f"login:{ip}",
        settings.login_max_attempts,
        settings.login_window_seconds,
        "Too many login attempts. Please try again later.",
    )

    admin = await get_admin_by_email(db, payload.email)

    if admin is None:
        await burn_timing_async()  # keep response time indistinguishable from a real miss
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)

    now = datetime.now(timezone.utc)
    locked_until = admin.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > now:
        await burn_timing_async()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)

    if not admin.is_active or not await verify_password_async(payload.password, admin.password_hash):
        admin.failed_attempts += 1
        if admin.failed_attempts >= settings.login_max_attempts:
            admin.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            admin.failed_attempts = 0
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC)

    admin.failed_attempts = 0
    admin.locked_until = None
    admin.last_login_at = utcnow()
    if needs_rehash(admin.password_hash):
        admin.password_hash = await hash_password_async(payload.password)  # upgrade Argon2 params
    await db.commit()

    reset(f"login:{ip}")
    _set_session_cookies(response, create_session_token(admin), new_csrf_token())
    return admin


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    _: Admin = Depends(get_current_admin),
    __: None = Depends(require_csrf),
) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", samesite="strict")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AdminOut)
async def me(admin: Admin = Depends(get_current_admin)) -> Admin:
    return admin
