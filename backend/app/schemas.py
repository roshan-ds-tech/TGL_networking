"""Pydantic request/response models.

All validation is re-done server side; the browser's checks are treated purely
as UX and never trusted.
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

# Mirrors the ten Season 1 categories offered by the public form.
VALID_CATEGORIES = {f"{i:02d}" for i in range(1, 11)}
VALID_EMPLOYEES = {"1-3", "4-6", "7-10"}
VALID_AGES = {"lt6", "6-12", "1-3y", "3y+"}

_PHONE_RE = re.compile(r"^\d{10}$")


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
    last_login_at: datetime | None = None

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
        if not _PHONE_RE.match(digits):
            raise ValueError("Enter a valid 10-digit phone number.")
        return digits

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError("Select a valid category.")
        return v

    @field_validator("employees")
    @classmethod
    def _employees(cls, v: str) -> str:
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
    proof_mime: str
    proof_bytes: int
    agreed_terms: bool
    media_consent: bool
    verified: bool
    verified_at: datetime | None
    verified_by_email: str | None = None
    created_at: datetime

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
