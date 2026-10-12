"""Database models.

Primary keys are UUIDs rather than sequential integers so registration IDs
cannot be enumerated by an attacker who obtains one valid ID.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
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

    # "local" = submitted through this backend's form; "pythonanywhere" = copied
    # read-only from the legacy registration system (legacy_sync.py), which
    # stays the source of truth for those rows.
    source: Mapped[str] = mapped_column(String(16), default="local", server_default="local", nullable=False)

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
    # Stored name of the member's profile photo (storage.py), e.g.
    # "3f2c….jpg". On the account, not the personal profile, so it can be set
    # at signup before that profile exists.
    photo_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def photo_url(self) -> str | None:
        return photo_url_for(self.id, self.photo_key)


def photo_url_for(user_id: str, photo_key: str | None) -> str | None:
    """Same-origin URL of a member's photo. The version (part of the stored
    name) changes on every upload, so browsers may cache each URL forever."""
    if not photo_key:
        return None
    return f"/api/v1/members/{user_id}/photo?v={photo_key.split('.')[0][:12]}"


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
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Three parties: giver_user_id (referrer, from the session) refers the
    # prospect below to receiver_user_id (a TGL member). The prospect is NOT a
    # member, so their details are a snapshot taken at submission time.
    # Nullable only because rows created before migration 0006 have none; the
    # API requires them for every new referral.
    prospect_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prospect_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)  # E.164, e.g. +919876543210
    prospect_email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # lower-cased
    prospect_company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prospect_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prospect_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_contact_method: Mapped[str | None] = mapped_column(String(12), nullable=True)
    relationship: Mapped[str | None] = mapped_column(String(24), nullable=True)
    relationship_other: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # business_need stays the short headline (list rows, notifications);
    # this is the full description the referrer wrote.
    opportunity_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)  # VALID_CATEGORIES code
    urgency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    value_range: Mapped[str | None] = mapped_column(String(16), nullable=True)
    intro_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    intro_call_preference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_permission: Mapped[str | None] = mapped_column(String(16), nullable=True)
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Derived server-side from what the referrer supplied, never client-set.
    quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Admin review marker (Phase 0): set by an admin, or automatically when a
    # closure shows a risk signal (see verification.py). It only queues the
    # referral for review; it has no financial effect.
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), index=True, nullable=False)
    flag_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flagged_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # admin id, or NULL for the system

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ref_receiver_created", "receiver_user_id", "created_at"),
        Index("ix_ref_giver_created", "giver_user_id", "created_at"),
        Index("ix_ref_receiver_phone", "receiver_user_id", "prospect_phone"),
        # The same referrer cannot have two live referrals of the same prospect
        # to the same member, even under a double-click / concurrent requests.
        Index(
            "uq_ref_live_giver_receiver_phone",
            "giver_user_id", "receiver_user_id", "prospect_phone",
            unique=True,
            sqlite_where=text("status IN ('GIVEN','ACCEPTED','CONTACTED','MEETING_DONE','BUSINESS_CLOSED') AND prospect_phone IS NOT NULL"),
            postgresql_where=text("status IN ('GIVEN','ACCEPTED','CONTACTED','MEETING_DONE','BUSINESS_CLOSED') AND prospect_phone IS NOT NULL"),
        ),
    )


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requester_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PENDING -> ACCEPTED (the two members are connected) or DECLINED (the target
    # ignored it; the requester is not told). A withdrawn request is deleted.
    # A connection is mutual: it exists once either direction is ACCEPTED.
    status: Mapped[str] = mapped_column(String(12), default="PENDING", server_default="PENDING", index=True, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Phase A (migration 0013): the sorted pair, hashed. Set on every NEW row; rows that predate it keep NULL. It backs the partial unique index below,
    # which stops two requests that cross in flight from leaving two live rows for one pair, whatever the database or the number of workers.
    pair_key: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("requester_user_id", "target_user_id", name="uq_connection_pair"),
        Index("uq_connection_pair_live", "pair_key", unique=True,
              sqlite_where=text("pair_key IS NOT NULL AND status IN ('PENDING','ACCEPTED')"), postgresql_where=text("pair_key IS NOT NULL AND status IN ('PENDING','ACCEPTED')")),
    )


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

    # Phase A (migration 0013): the lifecycle of a need. All nullable so every need that predates it stays valid.
    # status: OPEN (published and open) -> RESOLVED | CANCELLED (the poster) | REMOVED (an admin; may be restored). Legacy rows are OPEN.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)      # plain id, no FK: moderation history must outlive an admin account
    removed_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    resolved_offer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)        # the help offer the poster credited, if any (a fact, not a reward)
    title_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)               # hash of the normalised title / description: duplicate detection only
    description_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publish_month_key: Mapped[str | None] = mapped_column(String(7), nullable=True)         # calendar month of publication in business time (UTC+05:30)
    # A TRACKED policy field, never a reward: whether this post would count toward the proposed "two qualifying posts a month" limit.
    qualifies_for_future_reward: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    quality_note: Mapped[str | None] = mapped_column(String(24), nullable=True)             # why it does not qualify (MONTHLY_LIMIT), if it does not

    __table_args__ = (
        # The backstop for the duplicate check: two identical live needs from one member (a double click) can not both be stored. Rows that predate
        # Phase A have no title_hash and are outside it.
        Index("uq_need_live_title", "user_id", "title_hash", unique=True,
              sqlite_where=text("title_hash IS NOT NULL AND status IN ('OPEN','RESOLVED')"), postgresql_where=text("title_hash IS NOT NULL AND status IN ('OPEN','RESOLVED')")),
    )


NEED_OFFER_STATUSES = ("OFFERED", "ACCEPTED", "DECLINED", "WITHDRAWN", "CONFIRMED_HELPFUL", "NOT_HELPFUL")


class NeedHelpOffer(Base):
    """A member's offer to help with a need. It records that the offer was made and what the poster did with it. It is NOT evidence that help was
    given, and it earns nothing: Phase A records facts only."""

    __tablename__ = "need_help_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    need_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_needs.id", ondelete="CASCADE"), index=True, nullable=False)
    helper_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # OFFERED -> ACCEPTED | DECLINED | WITHDRAWN ; ACCEPTED -> CONFIRMED_HELPFUL | NOT_HELPFUL | WITHDRAWN. The other four are final.
    status: Mapped[str] = mapped_column(String(20), default="OFFERED", server_default="OFFERED", index=True, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)      # accepted or declined by the poster
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)        # the poster's helpful / not-helpful decision

    __table_args__ = (
        UniqueConstraint("need_id", "helper_user_id", name="uq_need_offer_helper"),                    # one offer per helper per need, even under concurrent clicks
        CheckConstraint("status IN ('OFFERED','ACCEPTED','DECLINED','WITHDRAWN','CONFIRMED_HELPFUL','NOT_HELPFUL')", name="ck_need_offer_status"),
    )


COMMUNITY_DOMAINS = ("CONNECTION", "NEED", "HELP", "SIGNAL")


class CommunityEvent(Base):
    """Append-only history of connections, needs and help offers (Phase A). Rows are only ever added: an ORM guard and database triggers refuse
    UPDATE and DELETE. It holds ids, a kind and a reason code, never a note, a message, a name or an e-mail. Ids are plain strings with no foreign
    keys on purpose: history must survive the removal of the current-state row (a removed connection) and of an account.
    It is an ACTIVITY record. It creates no Growth Points and has no financial meaning."""

    __tablename__ = "community_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    domain: Mapped[str] = mapped_column(String(12), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    subject_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)      # the other party, when there is one
    pair_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)            # sha256 of the two sorted ids, so a pair can be followed without listing it
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    need_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    offer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reconnection: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)                    # JSON of counts and flags only

    __table_args__ = (
        CheckConstraint("domain IN ('CONNECTION','NEED','HELP','SIGNAL')", name="ck_community_event_domain"),
        Index("ix_community_domain_kind_created", "domain", "kind", "created_at"),
        Index("ix_community_actor_created", "actor_user_id", "created_at"),
        Index("ix_community_pair_created", "pair_hash", "created_at"),
        Index("ix_community_need", "need_id"),
    )


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


# ============================================================================
# Phase 0 foundations: subscriptions, invoices, payments, verified referral
# outcomes, and an append-only audit log. Nothing here awards or applies
# Growth Points; see docs/PHASE_0_IMPLEMENTATION_REPORT.md.
# ============================================================================


class Plan(Base):
    """An official, priced plan. Prices are integer paise: never floats."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True, nullable=False)  # connect / growth / elite
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    # The plan's paid term, stored on the plan and snapshotted on every invoice: Connect 3, Growth 6, Elite 12.
    # There is no default on purpose: no code path may assume a duration. Expiry = start + period_months.
    period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    season_slug: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", index=True, nullable=False)  # ACTIVE / ARCHIVED
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_plan_status"),
        CheckConstraint("price_minor > 0", name="ck_plan_price_positive"),
        CheckConstraint("period_months > 0", name="ck_plan_period_positive"),
        # A plan term is a financial fact: the terms TGL sells are 3, 6 and 12 months. Adding one is a reviewed migration.
        CheckConstraint("period_months IN (3, 6, 12)", name="ck_plan_period_allowed"),
    )


class Subscription(Base):
    """Financial records (subscriptions, invoices, payments, deal closures and their evidence) reference the
    member, referral and closure they belong to with ON DELETE RESTRICT: an account or referral that has
    them cannot be hard-deleted, in the database as well as in the admin API. They are the record of money paid and of outcomes a future reward could rest on."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id", ondelete="RESTRICT"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", index=True, nullable=False)  # PENDING / ACTIVE / EXPIRED / CANCELLED
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    # The subscription this one renews. A renewal may be raised in the last 30 days of the running term (it then starts when that term ends)
    # or up to 30 days after it, only through the renewal endpoint. NULL for an ordinary purchase.
    renews_subscription_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','ACTIVE','EXPIRED','CANCELLED')", name="ck_subscription_status"),
        CheckConstraint("status <> 'ACTIVE' OR (starts_at IS NOT NULL AND expires_at IS NOT NULL AND activated_at IS NOT NULL)", name="ck_subscription_active_dates"),
        # One live purchase per member: a double click or replay cannot open a second.
        Index(
            "uq_subscription_live_user", "user_id", unique=True,
            sqlite_where=text("status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NULL"),
            postgresql_where=text("status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NULL"),
        ),
        # ... and one live renewal per subscription being renewed (so a double click or a replay can not open two).
        Index(
            "uq_subscription_live_renewal", "renews_subscription_id", unique=True,
            sqlite_where=text("status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NOT NULL"),
            postgresql_where=text("status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NOT NULL"),
        ),
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscriptions.id", ondelete="RESTRICT"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False)
    season_slug: Mapped[str | None] = mapped_column(String(60), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    # A snapshot of the plan at purchase time, so a later price change never rewrites history.
    plan_name: Mapped[str] = mapped_column(String(60), nullable=False)
    period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    list_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_before_discount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    # The only discount that exists is the Growth Points discount at a renewal (`points_discount_minor`); the CHECKs below keep it at
    # 1 point = 10 paise, at most 15 % of the list price, and the amount due at least 80 % of it. It is 0 on every invoice
    # unless the (disabled by default, approval-gated) redemption service created it.
    discount_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_redeemed: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    points_discount_minor: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    discount_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount_due_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="ISSUED", index=True, nullable=False)  # DRAFT / ISSUED / PENDING / PAID / FAILED / CANCELLED / REFUNDED
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','ISSUED','PENDING','PAID','FAILED','CANCELLED','REFUNDED')", name="ck_invoice_status"),
        CheckConstraint("status <> 'PAID' OR amount_paid_minor = amount_due_minor", name="ck_invoice_paid_matches"),
        CheckConstraint("amount_paid_minor <= amount_due_minor", name="ck_invoice_paid_not_over"),
        CheckConstraint("discount_minor = points_discount_minor", name="ck_invoice_discount_is_points"),
        CheckConstraint("points_discount_minor = points_redeemed * 10", name="ck_invoice_points_value"),
        CheckConstraint("points_discount_minor * 100 <= list_price_minor * 15", name="ck_invoice_points_cap"),
        CheckConstraint("amount_due_minor * 100 >= list_price_minor * 80", name="ck_invoice_payment_floor"),
        CheckConstraint("amount_due_minor = amount_before_discount_minor - discount_minor", name="ck_invoice_amount_due"),
        CheckConstraint("amount_paid_minor >= 0 AND amount_due_minor >= 0 AND list_price_minor > 0", name="ck_invoice_amounts"),
    )


class Payment(Base):
    """A payment against an invoice. Today: a manual payment proof that an admin verifies."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="RESTRICT"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(24), default="MANUAL_PROOF", nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", index=True, nullable=False)  # PENDING / SUBMITTED / VERIFIED / FAILED / REFUNDED
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    proof_filename: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proof_mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proof_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','SUBMITTED','VERIFIED','FAILED','REFUNDED')", name="ck_payment_status"),
        CheckConstraint("status NOT IN ('VERIFIED','REFUNDED') OR verified_at IS NOT NULL", name="ck_payment_verified_stamp"),CheckConstraint("amount_minor > 0", name="ck_payment_amount_positive"),)


class ReferralConfirmation(Base):
    """One member's confirmation of one step of one referral (today: the meeting).

    The unique key is what makes a repeat, a replay and a double click harmless."""

    __tablename__ = "referral_confirmations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    referral_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_referrals.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # MEETING
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)  # giver / receiver, derived by the server
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('MEETING')", name="ck_confirmation_kind"),
        CheckConstraint("role IN ('giver','receiver')", name="ck_confirmation_role"),UniqueConstraint("referral_id", "kind", "user_id", name="uq_referral_confirmation"),)


class DealClosure(Base):
    """The actual business outcome of a referral. Separate from the referral so the
    creation-time estimate (business_referrals.value_range) is never mistaken for it."""

    __tablename__ = "deal_closures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    referral_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_referrals.id", ondelete="RESTRICT"), index=True, nullable=False)
    reported_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    actual_value_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    value_band: Mapped[str] = mapped_column(String(12), index=True, nullable=False)  # derived by the server from actual_value_minor
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="AWAITING_CONFIRMATION", index=True, nullable=False)
    verification_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0..4, see verification.py
    confirmed_by_receiver_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_referrer_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_referrer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by_admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    dispute_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disputed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_before_dispute: Mapped[str | None] = mapped_column(String(24), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('AWAITING_CONFIRMATION','AWAITING_EVIDENCE','UNDER_REVIEW','VERIFIED','REJECTED','DISPUTED','CANCELLED','INVALIDATED')", name="ck_closure_status"),
        CheckConstraint("value_band IN ('UNDER_25K','25K_1L','1L_5L','5L_10L','10L_PLUS')", name="ck_closure_band"),
        CheckConstraint("status <> 'VERIFIED' OR verification_level >= 2", name="ck_closure_verified_level"),
        CheckConstraint("actual_value_minor > 0", name="ck_closure_value_positive"),
        CheckConstraint("verification_level BETWEEN 0 AND 4", name="ck_closure_level_range"),
        # One live closure per referral. A rejected, cancelled or invalidated one may be reported again.
        Index(
            "uq_closure_live_referral", "referral_id", unique=True,
            sqlite_where=text("status NOT IN ('REJECTED','CANCELLED','INVALIDATED')"),
            postgresql_where=text("status NOT IN ('REJECTED','CANCELLED','INVALIDATED')"),
        ),
    )


class DealEvidence(Base):
    """A document supporting a closure. Stored privately (see storage.py); this row
    is the only way to reach it, and only the referral's two members and admins can."""

    __tablename__ = "deal_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    closure_id: Mapped[str] = mapped_column(String(36), ForeignKey("deal_closures.id", ondelete="RESTRICT"), index=True, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(16), nullable=False)  # INVOICE / PAYMENT_PROOF / OTHER
    storage_name: Mapped[str] = mapped_column(String(80), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # spots one file reused across deals
    note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", index=True, nullable=False)  # PENDING / VERIFIED / REJECTED
    verified_by_admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','VERIFIED','REJECTED')", name="ck_evidence_status"),
        CheckConstraint("evidence_type IN ('INVOICE','PAYMENT_PROOF','OTHER')", name="ck_evidence_type"),
    )


class AuditLog(Base):
    """Append-only record of every sensitive change. Rows are never updated or deleted:
    the application has no code that does, an ORM guard refuses it, and database
    triggers (migration 0008 / database.install_audit_triggers) refuse it too."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(8), nullable=False)  # USER / ADMIN / SYSTEM
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # giver / receiver / member / admin / system
    action: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("actor_type IN ('USER','ADMIN','SYSTEM')", name="ck_audit_actor_type"),Index("ix_audit_resource", "resource_type", "resource_id", "created_at"),)


# ============================================================================
# Growth Points, Phase 1: SHADOW MODE. These tables record what points members
# WOULD have under the approved rules (app/rewards/rules.py). They have no
# monetary effect: nothing here references an invoice, a payment or a price
# that is ever written, and a CHECK constraint makes a non-shadow or REDEMPTION
# row impossible. See docs/PHASE_1_SHADOW_MODE_IMPLEMENTATION_REPORT.md.
# ============================================================================

GP_EVENT_TYPES = (
    "REFERRAL_ACCEPTED", "PROSPECT_CONTACTED", "MEETING_COMPLETED", "BUSINESS_CLOSED", "REPEAT_BUSINESS", "PROFILE_COMPLETED",
    "EVENT_ATTENDED", "SUCCESSFUL_INTRODUCTION", "NEED_RESOLVED", "MENTORING_SESSION", "MEMBER_INVITED",
)


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class GrowthPointRuleVersion(Base):
    """One row per rule version, written once: the exact parameters in force. A change of numbers is a new version."""

    __tablename__ = "growth_point_rule_versions"

    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GrowthPointCycle(Base):
    """A member's subscription cycle (the actual paid term) as the reward engine sees it, with its ceilings frozen
    from the price actually invoiced for it. Created when first needed."""

    __tablename__ = "growth_point_cycles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(12), nullable=False)       # SUBSCRIPTION / MEMBERSHIP (Season 1 complimentary term)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(24), nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    renewal_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    grace_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ceiling_points: Mapped[int] = mapped_column(Integer, nullable=False)
    process_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    closure_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    other_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_gp_cycle_source"),
        Index("ix_gp_cycle_member_start", "member_id", "starts_at"),
        CheckConstraint(_in("source_type", ("SUBSCRIPTION", "MEMBERSHIP")), name="ck_gp_cycle_source_type"),
        CheckConstraint("term_months > 0 AND price_minor > 0 AND ceiling_points >= 0", name="ck_gp_cycle_positive"),
    )


class GrowthPointLedger(Base):
    """The append-only SHADOW ledger. Rows are never updated or deleted (ORM guard + database triggers).

    EARN rows are lots of points; VOID / REVERSAL / EXPIRY rows are negative entries that point at the lot they act on
    (`parent_id`), so a lot's remaining points are its own plus its children's and nothing is ever edited.
    A reward reduced to nothing is still recorded (status CAPPED, 0 points) so the economy can be analysed."""

    __tablename__ = "growth_point_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)           # when the underlying event happened
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    counterparty_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pair_key: Mapped[str | None] = mapped_column(String(73), nullable=True)                       # the two member ids, sorted
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(8), nullable=False)
    role: Mapped[str | None] = mapped_column(String(10), nullable=True)                           # referrer / recipient / member
    reference_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cycle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prospect_key: Mapped[str | None] = mapped_column(String(16), nullable=True)                   # truncated hash of the prospect phone, never the phone
    points_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_points: Mapped[int] = mapped_column(Integer, nullable=False)
    capped_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capped_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cap_trace: Mapped[str | None] = mapped_column(Text, nullable=True)                            # JSON: every rule that reduced it, in order
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    assurance: Mapped[str | None] = mapped_column(String(10), nullable=True)                      # LOW / VERIFIED
    verification_level: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remaining: Mapped[int] = mapped_column(Integer, nullable=False)                               # the lot's remaining points right after this entry
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)                           # the member's shadow total right after this entry
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)                              # JSON; never a phone, an email or an exact deal value
    created_by: Mapped[str] = mapped_column(String(40), nullable=False, default="system")        # 'system' or an admin id
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    shadow: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)

    day_key: Mapped[str] = mapped_column(String(10), nullable=False)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    quarter_key: Mapped[str] = mapped_column(String(7), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_gp_ledger_idempotency"),
        Index("ix_gp_ledger_member_created", "member_id", "created_at"),
        Index("ix_gp_ledger_reference", "reference_type", "reference_id"),
        Index("ix_gp_ledger_pair_quarter", "pair_key", "quarter_key"),
        Index("ix_gp_ledger_cycle_category", "cycle_id", "category"),
        Index("ix_gp_ledger_expiry", "entry_type", "expires_at"),
        Index("ix_gp_ledger_member_month", "member_id", "month_key"),
        Index("ix_gp_ledger_member_day", "member_id", "day_key"),
        Index("ix_gp_ledger_parent", "parent_id"),
        CheckConstraint("shadow = true", name="ck_gp_ledger_shadow_only"),                       # a real (non-shadow) row cannot exist
        CheckConstraint(_in("entry_type", ("EARN", "VOID", "REVERSAL", "EXPIRY", "SIM_REDEEM")), name="ck_gp_ledger_entry_type"),
        CheckConstraint(_in("event_type", GP_EVENT_TYPES), name="ck_gp_ledger_event_type"),     # REDEMPTION is not an event type
        CheckConstraint(_in("category", ("PROCESS", "CLOSURE", "OTHER")), name="ck_gp_ledger_category"),
        CheckConstraint(_in("status", ("PENDING", "AVAILABLE", "CAPPED", "VOIDED", "REVERSED", "EXPIRED", "SIMULATED")), name="ck_gp_ledger_status"),
        CheckConstraint("assurance IS NULL OR assurance IN ('LOW', 'VERIFIED')", name="ck_gp_ledger_assurance"),
        CheckConstraint("(entry_type = 'EARN' AND points_delta >= 0) OR (entry_type <> 'EARN' AND points_delta <= 0)", name="ck_gp_ledger_sign"),
        CheckConstraint("entry_type = 'EARN' OR parent_id IS NOT NULL", name="ck_gp_ledger_parent"),
        CheckConstraint("verification_level BETWEEN 0 AND 4", name="ck_gp_ledger_level_range"),
        CheckConstraint("entry_type <> 'EARN' OR points_delta = 0 OR verification_level >= 1", name="ck_gp_ledger_l0_never_pays"),
        CheckConstraint("capped_points >= 0 AND requested_points >= 0 AND remaining >= 0", name="ck_gp_ledger_nonnegative"),
    )


class GrowthPointRenewal(Base):
    """The HYPOTHETICAL use of a member's old-cycle points at a renewal: one row per renewal subscription, written once.

    Shadow only. It records what the renewal invoice WOULD have shown: the old cycle, the new plan, how many old-cycle points were
    eligible, the new plan's 15 % ceiling, how many would be used, and the hypothetical discount and amount payable. It reads the
    renewal's subscription and invoice by id only (deliberately no foreign key to any financial table) and changes nothing there.
    The points themselves are consumed by SIM_REDEEM ledger rows that point back here (reference_type 'renewal')."""

    __tablename__ = "growth_point_renewals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    old_cycle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("growth_point_cycles.id", ondelete="RESTRICT"), index=True, nullable=True)
    new_subscription_id: Mapped[str] = mapped_column(String(36), nullable=False)
    new_invoice_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_plan: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_plan: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    new_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    new_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    eligible_points: Mapped[int] = mapped_column(Integer, nullable=False)
    redemption_cap_points: Mapped[int] = mapped_column(Integer, nullable=False)
    redeemed_points: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_points: Mapped[int] = mapped_column(Integer, nullable=False)
    hypothetical_discount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    hypothetical_payable_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    old_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    __table_args__ = (
        UniqueConstraint("new_subscription_id", name="uq_gp_renewal_subscription"),
        UniqueConstraint("idempotency_key", name="uq_gp_renewal_idempotency"),
        CheckConstraint("shadow = true", name="ck_gp_renewal_shadow_only"),
        CheckConstraint(_in("outcome", ("REDEEMED", "NOTHING_ELIGIBLE", "NOT_A_RENEWAL", "REFUNDED_CYCLE")), name="ck_gp_renewal_outcome"),
        CheckConstraint("redeemed_points >= 0 AND eligible_points >= 0 AND remaining_points >= 0 AND redemption_cap_points >= 0", name="ck_gp_renewal_nonnegative"),
        CheckConstraint("redeemed_points <= eligible_points AND redeemed_points <= redemption_cap_points", name="ck_gp_renewal_within_caps"),
        CheckConstraint("hypothetical_discount_paise >= 0 AND hypothetical_payable_paise >= 0", name="ck_gp_renewal_amounts"),
    )


class GrowthPointBalance(Base):
    """A member's shadow total (pending + available, unexpired), kept in step with the ledger in the same transaction.
    Also the row lock that serialises reward processing for a member. Reconciliation compares it with the ledger."""

    __tablename__ = "growth_point_balances"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (CheckConstraint("total_points >= 0", name="ck_gp_balance_nonnegative"),)


class GrowthPointFlag(Base):
    """A fraud / gaming signal queued for admin review. It has no automatic effect on any member."""

    __tablename__ = "growth_point_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(8), default="INFO", nullable=False)
    member_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    pair_key: Mapped[str | None] = mapped_column(String(73), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", index=True, nullable=False)
    reviewed_by_admin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(240), nullable=True)

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_gp_flag_dedupe"),
        CheckConstraint(_in("status", ("OPEN", "REVIEWED", "DISMISSED")), name="ck_gp_flag_status"),
        CheckConstraint(_in("severity", ("INFO", "WARN", "HIGH")), name="ck_gp_flag_severity"),
    )

class GrowthPointRedemption(Base):
    """REAL redemption of old-cycle points against a renewal invoice (Phase 2/3; created only by app/redemption, only when every gate
    is open). Append-only: a refund or a cancelled renewal adds a REVERSE row, nothing is edited or deleted. The earning rows in
    growth_point_ledger are never touched; the lots consumed are in growth_point_redemption_lots."""

    __tablename__ = "growth_point_redemptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(8), nullable=False)                  # REDEEM / REVERSE
    reverses_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("growth_point_redemptions.id", ondelete="RESTRICT"), nullable=True)
    old_cycle_id: Mapped[str] = mapped_column(String(36), ForeignKey("growth_point_cycles.id", ondelete="RESTRICT"), index=True, nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(36), ForeignKey("subscriptions.id", ondelete="RESTRICT"), index=True, nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(36), ForeignKey("invoices.id", ondelete="RESTRICT"), index=True, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    point_value_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    list_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_due_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_points: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_points: Mapped[int] = mapped_column(Integer, nullable=False)
    restored_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)    # REVERSE only: what could still be restored (not past its expiry)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_gp_redemption_idempotency"),
        Index("uq_gp_redemption_invoice", "invoice_id", unique=True, sqlite_where=text("entry_type = 'REDEEM'"), postgresql_where=text("entry_type = 'REDEEM'")),
        Index("uq_gp_redemption_reverse", "reverses_id", unique=True, sqlite_where=text("entry_type = 'REVERSE'"), postgresql_where=text("entry_type = 'REVERSE'")),
        CheckConstraint(_in("entry_type", ("REDEEM", "REVERSE")), name="ck_gp_redemption_type"),
        CheckConstraint("points > 0 AND point_value_paise > 0 AND discount_paise = points * point_value_paise", name="ck_gp_redemption_value"),
        CheckConstraint("discount_paise * 100 <= list_price_minor * 15", name="ck_gp_redemption_cap"),
        CheckConstraint("points <= cap_points AND points <= eligible_points", name="ck_gp_redemption_within_limits"),
        CheckConstraint("amount_due_minor = list_price_minor - discount_paise AND amount_due_minor * 100 >= list_price_minor * 80", name="ck_gp_redemption_amounts"),
        CheckConstraint("(entry_type = 'REDEEM' AND reverses_id IS NULL AND restored_points = 0) OR (entry_type = 'REVERSE' AND reverses_id IS NOT NULL AND restored_points >= 0 AND restored_points <= points)",
                        name="ck_gp_redemption_reverse_link"),
    )


class GrowthPointRedemptionLot(Base):
    """Which earning lots a redemption consumed (negative delta) or a reversal restored (positive delta)."""

    __tablename__ = "growth_point_redemption_lots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    redemption_id: Mapped[str] = mapped_column(String(36), ForeignKey("growth_point_redemptions.id", ondelete="RESTRICT"), index=True, nullable=False)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    lot_id: Mapped[str] = mapped_column(String(36), ForeignKey("growth_point_ledger.id", ondelete="RESTRICT"), index=True, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("redemption_id", "lot_id", name="uq_gp_redemption_lot"),
        CheckConstraint("delta <> 0", name="ck_gp_redemption_lot_delta"),
    )


class GrowthPointControl(Base):
    """Append-only operating switches (the redemption kill switch). The latest row per key wins; every change has an actor and a reason."""

    __tablename__ = "growth_point_controls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)


class GrowthPointRedemptionEpoch(Base):
    """The officially approved eligibility cutoff, recorded ONCE and never changed (append-only, singleton). Points whose event_at is before it are
    shadow-period points: historical records for analytics, audit, reconciliation and fraud review, permanently ineligible for redemption. This is
    the database-level line between history and eligible points; an environment variable can not move it."""

    __tablename__ = "growth_point_redemption_epoch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    singleton: Mapped[str] = mapped_column(String(8), default="ONLY", nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)

    __table_args__ = (
        UniqueConstraint("singleton", name="uq_gp_epoch_singleton"),
        CheckConstraint("singleton = 'ONLY'", name="ck_gp_epoch_singleton"),
        CheckConstraint("cutoff_at >= recorded_at", name="ck_gp_epoch_not_backdated"),
    )
