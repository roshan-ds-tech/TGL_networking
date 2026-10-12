"""Pydantic request/response models.

All validation is re-done server side; the browser's checks are treated purely
as UX and never trusted.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Literal

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
    proof_mime: str
    proof_bytes: int
    agreed_terms: bool
    media_consent: bool
    verified: bool
    verified_at: UtcDatetime | None
    verified_by_email: str | None = None
    created_at: UtcDatetime
    source: str = "local"

    model_config = {"from_attributes": True}


class RegistrationPage(BaseModel):
    items: list[RegistrationOut]
    total: int
    page: int
    page_size: int
    pages: int
    # Admin of the legacy system that mirrored rows come from (for links).
    legacy_admin_url: str | None = None


class VerifyRequest(BaseModel):
    verified: bool


class CustomerListItem(BaseModel):
    """A TGL product-app account — separate from Season 1 event registration.

    Signing up, verifying email, and completing a profile does not register
    anyone for Season 1 or take a payment; this is purely "does this person
    have an account."
    """

    id: str
    email: str
    email_verified_at: UtcDatetime | None
    is_active: bool
    created_at: UtcDatetime
    full_name: str | None = None
    phone: str | None = None
    business_name: str | None = None
    business_id: str | None = None
    verification_status: str | None = None
    personal_profile_complete: bool
    business_profile_complete: bool


class BusinessVerificationUpdate(BaseModel):
    status: str


class CustomerPage(BaseModel):
    items: list[CustomerListItem]
    total: int
    page: int
    page_size: int
    pages: int


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


class CustomerSignup(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Enter your full name.")
        return v

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) != 10:
            raise ValueError("Enter a valid 10-digit mobile number.")
        return digits


class CustomerLogin(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class CustomerOut(BaseModel):
    id: str
    email: EmailStr
    email_verified_at: UtcDatetime | None
    is_active: bool
    full_name: str | None = None
    phone: str | None = None

    photo_url: str | None = None
    model_config = {"from_attributes": True}


class AuthOut(BaseModel):
    user: CustomerOut
    dev_verification_token: str | None = None


class OtpRequestIn(BaseModel):
    email: EmailStr


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class OtpRequestOut(BaseModel):
    dev_otp: str | None = None


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class ConnectionCreate(BaseModel):
    target_user_id: str
    note: str | None = Field(default=None, max_length=2000)


class ConnectionRespond(BaseModel):
    action: Literal["accept", "decline"]


class ConnectionOut(BaseModel):
    id: str
    requester_user_id: str
    target_user_id: str
    note: str | None
    status: str = "PENDING"
    responded_at: UtcDatetime | None = None
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class ReferralRequestCreate(BaseModel):
    target_user_id: str
    note: str | None = Field(default=None, max_length=2000)


class PersonalProfileIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str
    city: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=120)
    short_bio: str = Field(min_length=10, max_length=1000)
    profile_photo_url: str | None = Field(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return RegistrationCreate._phone(v)


class PersonalProfileOut(PersonalProfileIn):
    user_id: str
    completed_at: UtcDatetime

    model_config = {"from_attributes": True}


class BusinessIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=160)
    category: str
    description: str = Field(min_length=10, max_length=2000)
    city: str = Field(min_length=2, max_length=120)
    employee_band: str
    business_age: str
    website: str | None = Field(default=None, max_length=300)
    instagram: str | None = Field(default=None, max_length=300)
    linkedin: str | None = Field(default=None, max_length=300)
    logo_url: str | None = Field(default=None, max_length=500)
    founder_story: str | None = Field(default=None, max_length=2000)
    business_stage: str = Field(min_length=2, max_length=80)

    @field_validator("website", "instagram", "linkedin")
    @classmethod
    def _link(cls, v: str | None) -> str | None:
        # Rendered as links on profiles, so only web addresses are accepted —
        # never javascript:, data: or other schemes. A bare "mybiz.com" is fine.
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if re.match(r"^[a-z][a-z0-9+.-]*:", v, re.I) and not re.match(r"^https?://", v, re.I):
            raise ValueError("Enter a web address starting with https://")
        if re.search(r"\s", v):
            raise ValueError("Links can't contain spaces.")
        return v

    @field_validator("founder_story")
    @classmethod
    def _story(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        return RegistrationCreate._category(v)

    @field_validator("employee_band")
    @classmethod
    def _employees(cls, v: str) -> str:
        return RegistrationCreate._employees(v)

    @field_validator("business_age")
    @classmethod
    def _age(cls, v: str) -> str:
        return RegistrationCreate._age(v)


class BusinessOut(BusinessIn):
    id: str
    user_id: str
    tgl_verified: bool
    tgl_verified_at: UtcDatetime | None
    verification_status: str
    verification_submitted_at: UtcDatetime | None = None
    # True when the badge comes from a Season 1 registration rather than KYB.
    verified_via_registration: bool = False

    model_config = {"from_attributes": True}


class NetworkingProfileOut(BaseModel):
    trust_score: int
    growth_points: int
    open_to_mentoring: bool
    seeking_mentor: bool

    model_config = {"from_attributes": True}


class MembershipOut(BaseModel):
    id: str | None = None
    status: str | None = None
    membership_type: str = "NETWORKING"
    pathway: str | None = None
    starts_at: UtcDatetime | None = None
    expires_at: UtcDatetime | None = None


class EventOut(BaseModel):
    id: str
    slug: str
    name: str
    grand_finale_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    registration_open: bool
    registration_closes_at: UtcDatetime
    membership_duration_months: int

    model_config = {"from_attributes": True}


class MyStatusOut(BaseModel):
    user: CustomerOut
    personal_profile: PersonalProfileOut | None = None
    business: BusinessOut | None = None
    event: EventOut
    event_registration: dict | None = None
    membership: MembershipOut | None = None
    networking_profile: NetworkingProfileOut | None = None
    # networking_access: Networking is open (registered email + Grand Finale
    # completed, or an active membership). has_registration: the email is on
    # file as a Season 1 registrant, so a locked account is "waiting for the
    # Finale" rather than "needs to subscribe".
    networking_access: bool = False
    has_registration: bool = False
    registration_verified: bool = False
    unread_notifications: int = 0


class MemberListItem(BaseModel):
    member_id: str
    user_id: str
    founder_name: str
    business_name: str
    category: str
    city: str | None
    headline: str | None
    tgl_verified: bool
    open_to_mentoring: bool
    trust_score: int
    photo_url: str | None = None


class MemberDetail(MemberListItem):
    business_description: str | None
    founder_story: str | None
    interests: str | None
    seeking_mentor: bool
    trust_score: int
    growth_points: int
    referrals_given: int
    referrals_received: int


# ---------------------------------------------------------------- referrals --
# Three parties: the referrer (the logged-in member, never in the payload), the
# recipient (a TGL member, chosen by id) and the prospect (an outsider whose
# details the referrer types in).

CATEGORY_NAMES = {
    "01": "Fashion, Apparel & Textile Businesses",
    "02": "Food, Bakery & Beverage Businesses",
    "03": "Handmade, Craft & Artisan Businesses",
    "04": "Jewellery & Accessories Businesses",
    "05": "Home Decor, Lifestyle & Interior Businesses",
    "06": "Kids Products, Toys & Parenting Brands",
    "07": "Beauty, Personal Care & Wellness Businesses",
    "08": "Fitness, Sports & Health Businesses",
    "09": "Business, Professional & Digital Services",
    "10": "Emerging, Innovative & Unique Businesses",
}

ReferralRelationship = Literal[
    "EXISTING_CLIENT", "FRIEND", "FAMILY", "BUSINESS_CONTACT", "PREVIOUS_CUSTOMER",
    "PROFESSIONAL_NETWORK", "CONTACTED_ME", "OTHER",
]
ReferralUrgency = Literal["HOT", "WARM", "DEVELOPING", "UNSURE"]
ReferralValueRange = Literal["UNDER_25K", "25K_1L", "1L_5L", "OVER_5L", "UNKNOWN"]
ReferralIntroMethod = Literal["EMAIL", "CALL", "SHARE_DETAILS", "ALREADY_KNOWS", "OTHER"]
ReferralPermission = Literal["EXPECTING", "CAREFULLY", "ASK_FIRST", "UNSURE"]
ReferralContactMethod = Literal["PHONE", "WHATSAPP", "EMAIL"]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(v: str | None, multiline: bool = False) -> str | None:
    """Strip control characters and collapse whitespace; '' becomes None."""
    if v is None:
        return None
    v = _CONTROL_CHARS.sub("", v.replace("\r\n", "\n").replace("\r", "\n"))
    v = re.sub(r"[ \t]+", " ", v)
    v = re.sub(r"\n{3,}", "\n\n", v) if multiline else re.sub(r"\s+", " ", v)
    v = "\n".join(line.strip() for line in v.split("\n")).strip() if multiline else v.strip()
    return v or None


def normalize_phone(raw: str) -> str:
    """Return E.164. Indian numbers (the default) may be written 98765 43210,
    +91 98765-43210, 91…, or 098…; any other country needs an explicit +CC."""
    raw = (raw or "").strip()
    if len(raw) > 25 or re.search(r"[^\d\s+()\-.]", raw):
        raise ValueError("Enter a valid phone number, for example +91 98765 43210.")
    digits = re.sub(r"\D", "", raw)
    international = raw.startswith("+") or raw.startswith("00")
    if raw.startswith("00"):
        digits = digits[2:]
    if not international:
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Enter a valid 10-digit Indian mobile number, or include the country code (+44…).")
        digits = "91" + digits
    elif digits.startswith("91"):
        if not re.fullmatch(r"91[6-9]\d{9}", digits):
            raise ValueError("Indian mobile numbers have 10 digits and start with 6, 7, 8 or 9.")
    elif not re.fullmatch(r"[1-9]\d{7,14}", digits):
        raise ValueError("Enter a valid phone number with its country code.")
    if len(set(digits[-10:])) == 1:
        raise ValueError("That doesn't look like a real phone number.")
    return f"+{digits}"


class ReferralCreate(BaseModel):
    # extra=forbid: a forged giver_user_id / status / referrer name is rejected
    # outright rather than silently ignored.
    model_config = {"extra": "forbid"}

    receiver_user_id: str = Field(min_length=1, max_length=36)

    prospect_name: str = Field(min_length=2, max_length=120)
    prospect_phone: str
    prospect_email: EmailStr | None = None
    prospect_company: str | None = Field(default=None, max_length=160)
    prospect_role: str | None = Field(default=None, max_length=120)
    prospect_location: str | None = Field(default=None, max_length=120)
    preferred_contact_method: ReferralContactMethod | None = None

    relationship: ReferralRelationship
    relationship_other: str | None = Field(default=None, max_length=120)

    opportunity_description: str = Field(min_length=30, max_length=1000)
    category: str | None = None
    urgency: ReferralUrgency = "UNSURE"
    value_range: ReferralValueRange | None = None

    intro_method: ReferralIntroMethod
    intro_call_preference: str | None = Field(default=None, max_length=120)
    contact_permission: ReferralPermission
    note: str | None = Field(default=None, max_length=1000)

    consent_confirmed: bool
    confirm_duplicate: bool = False

    @field_validator("prospect_email", mode="before")
    @classmethod
    def _blank_email(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("prospect_name", "prospect_company", "prospect_role", "prospect_location", "relationship_other", "intro_call_preference")
    @classmethod
    def _single_line(cls, v: str | None) -> str | None:
        return _clean_text(v)

    @field_validator("prospect_name")
    @classmethod
    def _name_has_letters(cls, v: str | None) -> str:
        if not v or len(v) < 2 or not re.search(r"[^\W\d_]", v):
            raise ValueError("Enter the contact person's full name.")
        return v

    @field_validator("opportunity_description", "note")
    @classmethod
    def _multi_line(cls, v: str | None, info) -> str | None:
        v = _clean_text(v, multiline=True)
        if info.field_name == "opportunity_description" and (v is None or len(v) < 30):
            raise ValueError("Describe the opportunity in at least 30 characters so the member has useful context.")
        return v

    @field_validator("prospect_phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("category")
    @classmethod
    def _category(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError("Choose one of the listed categories.")
        return v

    @field_validator("consent_confirmed")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Please confirm you may share these contact details.")
        return v


class ReferralTransition(BaseModel):
    model_config = {"extra": "forbid"}

    status: str = Field(min_length=1, max_length=24)


class ReferralOut(BaseModel):
    """What both parties see in lists. No prospect phone/email here."""

    id: str
    giver_user_id: str
    receiver_user_id: str
    my_role: str | None = None
    giver_name: str | None = None
    giver_business: str | None = None
    giver_photo_url: str | None = None
    receiver_name: str | None = None
    receiver_business: str | None = None
    receiver_photo_url: str | None = None
    business_need: str
    prospect_name: str | None = None
    prospect_company: str | None = None
    category: str | None = None
    urgency: str | None = None
    intro_method: str | None = None
    quality: str | None = None
    status: str
    accepted_at: UtcDatetime | None = None
    contacted_at: UtcDatetime | None = None
    meeting_done_at: UtcDatetime | None = None
    business_closed_at: UtcDatetime | None = None
    revenue_generated_at: UtcDatetime | None = None
    cancelled_at: UtcDatetime | None = None
    declined_at: UtcDatetime | None = None
    closed_at: UtcDatetime | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    last_action_at: UtcDatetime | None = None
    # Phase 0: where the two-party meeting confirmation and the verified business outcome stand.
    meeting: dict | None = None
    closure: dict | None = None
    # Statuses the *requesting* member may move this referral to right now.
    allowed_actions: list[str] = []

    model_config = {"from_attributes": True}


class ReferralDetail(ReferralOut):
    """Single-referral view, for the two participants only."""

    prospect_phone: str | None = None
    prospect_email: str | None = None
    prospect_role: str | None = None
    prospect_location: str | None = None
    preferred_contact_method: str | None = None
    relationship: str | None = None
    relationship_other: str | None = None
    opportunity_description: str | None = None
    value_range: str | None = None
    intro_call_preference: str | None = None
    contact_permission: str | None = None
    note: str | None = None


class ReferralSummary(BaseModel):
    total: int
    awaiting_response: int  # received referrals the member hasn't accepted or declined yet
    sent: int
    received: int
    in_progress: int
    converted: int
    closed: int
    by_status: dict[str, int]


class MemberSearchItem(BaseModel):
    """Deliberately small: enough to recognise a member, nothing private."""

    member_id: str
    user_id: str
    name: str
    business_name: str
    profession: str | None = None
    category: str
    category_name: str | None = None
    city: str | None = None
    photo_url: str | None = None


class MemberSearchOut(BaseModel):
    items: list[MemberSearchItem]
    has_more: bool


class BusinessNeedCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    category: str
    description: str | None = Field(default=None, max_length=2000)


class BusinessNeedOut(BaseModel):
    id: str
    title: str
    category: str
    description: str | None
    status: str
    poster_user_id: str
    poster_name: str
    business_name: str
    city: str | None
    created_at: UtcDatetime

    poster_photo_url: str | None = None
    # Phase A (all optional, so existing clients keep working): the poster sees how many offers arrived; a helper sees the state of their own offer.
    offers_count: int | None = None
    my_offer_id: str | None = None
    my_offer_status: str | None = None
    resolved_offer_id: str | None = None
    model_config = {"from_attributes": True}


class NeedOfferCreate(BaseModel):
    message: str | None = Field(default=None, max_length=1000)


class NeedOfferAction(BaseModel):
    action: Literal["accept", "decline", "withdraw", "confirm_helpful", "not_helpful"]


class NeedResolve(BaseModel):
    offer_id: str | None = Field(default=None, max_length=36)       # the offer the poster credits; it must already be confirmed helpful


class NeedOfferOut(BaseModel):
    id: str
    need_id: str
    status: str
    message: str | None
    created_at: UtcDatetime
    helper_user_id: str | None = None
    helper_name: str | None = None
    helper_business: str | None = None
    mine: bool = False


class NotificationActor(BaseModel):
    """Who caused a notification — enough to recognise them and open their
    member page. Only what the directory already shows members."""

    user_id: str
    name: str
    business_name: str | None = None
    city: str | None = None
    member_id: str | None = None
    photo_url: str | None = None


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: str
    related_entity_type: str | None
    related_entity_id: str | None
    read_at: UtcDatetime | None
    created_at: UtcDatetime
    actor: NotificationActor | None = None
    # Type-specific context for the detail view: the connection/referral
    # request note, the referral's business need and status, the need's title.
    detail: dict | None = None

    model_config = {"from_attributes": True}


class FinaleStateOut(BaseModel):
    event: EventOut
    registrations: int
    members_with_access: int


class FinaleUndoOut(BaseModel):
    event: EventOut
    reverted: int
    was_completed: bool


class FinaleCompleteOut(BaseModel):
    event: EventOut
    activated: int
    already_active: int
    registrations: int = 0
    members_with_access: int = 0
