"""Create or reset an admin account.

Usage:
    python create_admin.py                      # interactive (password hidden)
    python create_admin.py --email a@b.com      # prompts for password only

The password is never echoed, never passed as an argv value (which would leak
into shell history and the process list), and only ever stored as an Argon2id
hash.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys

from app.database import Base, SessionLocal, engine
from app.models import Admin
from app.security import get_admin_by_email, hash_password

MIN_LENGTH = 12
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _check_password(pw: str) -> list[str]:
    problems = []
    if len(pw) < MIN_LENGTH:
        problems.append(f"must be at least {MIN_LENGTH} characters")
    if not re.search(r"[A-Za-z]", pw):
        problems.append("must contain a letter")
    if not re.search(r"\d", pw):
        problems.append("must contain a digit")
    return problems


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create or reset a TGL admin user")
    parser.add_argument("--email", help="Admin email address")
    args = parser.parse_args()

    email = (args.email or input("Admin email: ")).strip().lower()
    if not EMAIL_RE.match(email):
        print("error: that does not look like a valid email address", file=sys.stderr)
        return 1

    password = getpass.getpass("Password: ")
    problems = _check_password(password)
    if problems:
        print("error: password " + "; ".join(problems), file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirm password: "):
        print("error: passwords do not match", file=sys.stderr)
        return 1

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        existing = await get_admin_by_email(db, email)
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_active = True
            existing.failed_attempts = 0
            existing.locked_until = None
            # Invalidate any sessions issued against the old password.
            existing.token_version += 1
            await db.commit()
            print(f"Password reset for existing admin: {email}")
        else:
            db.add(Admin(email=email, password_hash=hash_password(password)))
            await db.commit()
            print(f"Admin created: {email}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
