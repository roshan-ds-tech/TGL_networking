"""Database models.

Primary keys are UUIDs rather than sequential integers so registration IDs
cannot be enumerated by an attacker who obtains one valid ID.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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

    agreed_terms: Mapped[bool] = mapped_column(Boolean, nullable=False)
    media_consent: Mapped[bool] = mapped_column(Boolean, nullable=False)

    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )
    verified_by: Mapped[Admin | None] = relationship(lazy="joined")

    # Authenticated P0 registration bridge. Nullable so legacy public rows
    # remain valid and no destructive migration is needed.
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    business_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True)
    event_registration_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_registrations.id", ondelete="SET NULL"), nullable=True
    )

    # Salted hash, not the raw IP — enough to spot abuse without storing PII.
    submitter_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    __table_args__ = (
        # Backs the dashboard's default "newest first, filtered by status" query.
        Index("ix_reg_verified_created", "verified", "created_at"),
        Index("ix_reg_category_created", "category", "created_at"),
        # Every /status and networking request asks "is this email on a
        # registration?" by lower(email). Measured on realistic volume: the
        # directory's account<->registration join went 8.3 ms -> 0.7 ms.
        Index("ix_registrations_lower_email", func.lower(email)),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Collected on the signup form so the admin Accounts view has them from
    # the moment the account exists. Nullable for accounts created before.
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class UserVerificationToken(Base):
    __tablename__ = "user_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # EMAIL_VERIFY (signup OTP) | LOGIN_OTP (passwordless login) | PASSWORD_RESET.
    # Discriminates the token's purpose so a code issued for one flow can't be
    # replayed against another endpoint.
    purpose: Mapped[str] = mapped_column(String(24), default="EMAIL_VERIFY", nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PersonalProfile(Base):
    __tablename__ = "personal_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    short_bio: Mapped[str] = mapped_column(Text, nullable=False)
    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    employee_band: Mapped[str] = mapped_column(String(16), nullable=False)
    business_age: Mapped[str] = mapped_column(String(16), nullable=False)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(300), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(300), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    founder_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_stage: Mapped[str] = mapped_column(String(80), nullable=False)
    tgl_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tgl_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # KYB submission workflow state, separate from the tgl_verified badge it
    # ultimately sets. NOT_STARTED|PENDING|NEEDS_INFO|VERIFIED|REJECTED.
    verification_status: Mapped[str] = mapped_column(String(16), default="NOT_STARTED", nullable=False)
    verification_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (Index("ix_business_user_created", "user_id", "created_at"),)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    grand_finale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registration_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    membership_duration_months: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    legacy_registration_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PAYMENT_REVIEW", index=True, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(32), default="REVIEW", index=True, nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    admin_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin_verified_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("event_id", "user_id", "business_id", name="uq_event_registration_user_business"),)


class TGLMembership(Base):
    __tablename__ = "tgl_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    membership_type: Mapped[str] = mapped_column(String(32), default="NETWORKING", nullable=False)
    pathway: Mapped[str] = mapped_column(String(40), default="EVENT_REGISTRATION", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True, nullable=False)
    source_event_registration_id: Mapped[str] = mapped_column(String(36), ForeignKey("event_registrations.id", ondelete="CASCADE"), unique=True, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (Index("ix_membership_user_status", "user_id", "status"),)


class NetworkingProfile(Base):
    __tablename__ = "networking_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    headline: Mapped[str | None] = mapped_column(String(180), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    founder_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    interests: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_to_mentoring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seeking_mentor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_phone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trust_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    growth_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class BusinessReferral(Base):
    __tablename__ = "business_referrals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    giver_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    receiver_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    business_need: Mapped[str] = mapped_column(String(240), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="GIVEN", index=True, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revenue_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requester_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("requester_user_id", "target_user_id", name="uq_connection_pair"),)


class ReferralRequest(Base):
    __tablename__ = "referral_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requester_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BusinessNeed(Base):
    __tablename__ = "business_needs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    recipient_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # The member whose action caused this (requester, referrer, helper). NULL
    # for system notifications (registration, membership).
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    __table_args__ = (
        # Backs the "unread count + newest-first per recipient" queries.
        Index("ix_notification_recipient_read", "recipient_user_id", "read_at"),
    )


class EmailOutbox(Base):
    """Transactional email waiting to be sent (outbox pattern).

    Written in the SAME transaction as whatever the email is about (e.g. the
    verification code), so the two can never disagree; sent afterwards by the
    background worker in outbox.py, which retries with backoff. Bodies are
    erased once sent — they may contain one-time codes.
    """

    __tablename__ = "email_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    html: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PENDING -> SENDING -> SENT | FAILED (| SKIPPED when no email provider is configured)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The worker's "what is due?" query.
        Index("ix_email_outbox_due", "status", "next_attempt_at"),
    )
