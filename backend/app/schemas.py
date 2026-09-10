"""Pydantic request/response models.

All validation is re-done server side; the browser's checks are treated purely
as UX and never trusted.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator


def _ensure_utc(v: datetime | None) -> datetime | None:
    """Tag naive timestamps as UTC.

    Everything is written with `datetime.now(timezone.utc)`, but SQLite has no
    native timestamp type and hands values back with `tzinfo` stripped. Without
    this, the API would serialise "2026-09-03T18:10:08" with no offset, and the
    browser would read that as *local* time — showing an IST admin 18:10 for a
    registration actually submitted at 23:40. Postgres returns aware values and
    is left untouched.
    """
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


# Serialises with an explicit "Z"/offset, so `new Date(...)` in the browser
# converts to the viewer's local zone instead of guessing.
UtcDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]

# Mirrors the ten Season 1 categories offered by the public form.
VALID_CATEGORIES = {f"{i:02d}" for i in range(1, 11)}
VALID_EMPLOYEES = {"1-3", "4-6", "7-10"}
VALID_AGES = {"lt6", "6-12", "1-3y", "3y+"}

_PHONE_RE = re.compile(r"^\d{10}$")

# A UPI UTR is 12 digits, but the same field is used to paste references from
# bank apps (IMPS/NEFT), which run longer and can include letters. Accepting
# 12-22 alphanumerics covers both without letting obvious junk through.
_UTR_RE = re.compile(r"^[A-Z0-9]{12,22}$")


class LoginRequest(BaseModel):
    """Login deliberately does NOT use EmailStr.

    Strict address parsing would make malformed input return 422 while a wrong
    password returns 401 — a needless signal about the shape of stored
    credentials — and would reject perfectly valid internal admin domains. The
    value is only ever used in a parameterised equality lookup.
    """

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class AdminOut(BaseModel):
    id: str
    email: EmailStr
    last_login_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}


class RegistrationCreate(BaseModel):
    """Parsed from multipart form fields (the file is handled separately)."""

    full_name: str = Field(min_length=2, max_length=120)
    business_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str
    category: str
    employees: str
    business_age: str
    city: str | None = Field(default=None, max_length=120)
    utr: str = Field(max_length=40)
    agreed_terms: bool
    media_consent: bool

    @field_validator("full_name", "business_name", "city")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v or "")
        # Accept the ways an Indian mobile is actually written — bare ten
        # digits, with the +91 country code, or with a trunk 0 — and store the
        # bare ten. Rejecting "+91 98765 43210" outright meant a registrant who
        # had *already paid* hit a validation error at the last step.
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if not _PHONE_RE.match(digits):
            raise ValueError("Enter a valid 10-digit mobile number.")
        return digits

    @field_validator("utr")
    @classmethod
    def _utr(cls, v: str) -> str:
        # People copy this straight out of a payment app, so spaces and hyphens
        # come along with it. Normalise before validating, and store the
        # normalised form so two spellings of one reference can't both be used.
        cleaned = re.sub(r"[\s-]", "", v or "").upper()
        if not _UTR_RE.match(cleaned):
            raise ValueError(
                "Enter the UTR / UPI reference number from your payment app "
                "(usually 12 digits)."
            )
        return cleaned

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError("Select a valid category.")
        return v

    @field_validator("employees")
    @classmethod
    def _employees(cls, v: str) -> str:
        # "10+" is a real option on the form, but Season 1 eligibility is capped
        # at 10 employees — so say why rather than "invalid selection".
        if v == "10+":
            raise ValueError(
                "Season 1 is open to businesses with 10 or fewer employees."
            )
        if v not in VALID_EMPLOYEES:
            raise ValueError("Select a valid team size.")
        return v

    @field_validator("business_age")
    @classmethod
    def _age(cls, v: str) -> str:
        if v not in VALID_AGES:
            raise ValueError("Select how long you have been operating.")
        return v

    @field_validator("agreed_terms", "media_consent")
    @classmethod
    def _must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("This acknowledgement is required.")
        return v


class RegistrationOut(BaseModel):
    id: str
    full_name: str
    business_name: str
    email: EmailStr
    phone: str
    category: str
    employees: str
    business_age: str
    city: str | None
    # None for registrations taken before the field existed.
    utr: str | None = None
    proof_mime: str
    proof_bytes: int
    agreed_terms: bool
    media_consent: bool
    verified: bool
    verified_at: UtcDatetime | None
    verified_by_email: str | None = None
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class RegistrationPage(BaseModel):
    items: list[RegistrationOut]
    total: int
    page: int
    page_size: int
    pages: int


class VerifyRequest(BaseModel):
    verified: bool


class CategoryCount(BaseModel):
    category: str
    total: int
    verified: int


class StatsOut(BaseModel):
    total: int
    verified: int
    pending: int
    by_category: list[CategoryCount]
    # Same value the /api/categories/availability and registration-intake
    # capacity check use — the dashboard reads this instead of hardcoding a
    # number, so it can never drift from what's actually enforced.
    capacity_per_category: int


class CategoryAvailability(BaseModel):
    """One category's public slot counter."""

    category: str
    filled: int
    capacity: int


class AvailabilityOut(BaseModel):
    """Public, aggregate-only view of how full the season is.

    Deliberately contains no per-registration data — only counts — so it is safe
    to serve unauthenticated to the marketing site.
    """

    capacity_per_category: int
    total_capacity: int
    total_filled: int
    categories: list[CategoryAvailability]
    # Served so the site closes at the same instant the API refuses at, rather
    # than each holding its own copy of the date and drifting apart.
    registration_closes_at: UtcDatetime
    registration_open: bool
