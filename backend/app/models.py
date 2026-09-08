"""Database models.

Primary keys are UUIDs rather than sequential integers so registration IDs
cannot be enumerated by an attacker who obtains one valid ID.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Bumping this invalidates every previously issued session token.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    business_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    employees: Mapped[str] = mapped_column(String(16), nullable=False)
    business_age: Mapped[str] = mapped_column(String(16), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Stored filename only (a server-generated UUID). Never a client-supplied path.
    proof_filename: Mapped[str] = mapped_column(String(80), nullable=False)
    proof_mime: Mapped[str] = mapped_column(String(64), nullable=False)
    proof_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    # UPI reference for the payment, stored normalised (uppercase, no spaces).
    # Indexed because verifying admins look rows up by it. Nullable only because
    # registrations taken before this field existed have none — the API requires
    # it on every new submission. See database.sync_schema for how the column is
    # added to databases that predate it.
    utr: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)

    agreed_terms: Mapped[bool] = mapped_column(Boolean, nullable=False)
    media_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)

    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    verified_by: Mapped[Admin | None] = relationship(lazy="joined")

    # Salted hash, not the raw IP — enough to spot abuse without storing PII.
    submitter_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    __table_args__ = (
        # Backs the dashboard's default "newest first, filtered by status" query.
        Index("ix_reg_verified_created", "verified", "created_at"),
        Index("ix_reg_category_created", "category", "created_at"),
    )
