"""Request and response shapes for the Phase 0 foundations (subscriptions,
verified meetings and closures, admin referral review)."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from .schemas import UtcDatetime
from .verification import EVIDENCE_TYPES, MAX_VALUE_MINOR, MIN_VALUE_MINOR


# ------------------------------ subscriptions ------------------------------

class PlanOut(BaseModel):
    code: str
    name: str
    price_minor: int
    currency: str
    period_months: int
    season_slug: str | None = None

    model_config = {"from_attributes": True}


class PaymentInstructionsOut(BaseModel):
    configured: bool
    instructions: str | None = None  # plain text; never HTML


class InvoiceOut(BaseModel):
    id: str
    number: str
    plan_name: str
    period_months: int
    currency: str
    list_price_minor: int
    amount_before_discount_minor: int
    discount_minor: int
    amount_due_minor: int
    amount_paid_minor: int
    status: str
    issued_at: UtcDatetime | None = None
    paid_at: UtcDatetime | None = None
    refunded_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    id: str
    method: str
    status: str
    amount_minor: int
    reference: str
    has_proof: bool = False
    submitted_at: UtcDatetime | None = None
    verified_at: UtcDatetime | None = None
    rejection_reason: str | None = None
    refunded_at: UtcDatetime | None = None


class SubscriptionOut(BaseModel):
    id: str
    status: str
    plan: PlanOut
    starts_at: UtcDatetime | None = None
    expires_at: UtcDatetime | None = None
    activated_at: UtcDatetime | None = None
    created_at: UtcDatetime
    is_renewal: bool = False
    invoice: InvoiceOut | None = None
    payment: PaymentOut | None = None


class SubscriptionCreate(BaseModel):
    plan_code: str = Field(min_length=2, max_length=24, pattern=r"^[a-z][a-z0-9_-]*$")


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=240)


class AdminPerson(BaseModel):
    id: str
    email: str
    name: str | None = None


class AdminSubscriptionItem(BaseModel):
    id: str
    status: str
    effective_status: str
    user: AdminPerson
    plan_code: str
    plan_name: str
    invoice_number: str | None = None
    invoice_status: str | None = None
    amount_due_minor: int | None = None
    amount_paid_minor: int | None = None
    payment_status: str | None = None
    payment_reference: str | None = None
    has_proof: bool = False
    submitted_at: UtcDatetime | None = None
    created_at: UtcDatetime
    expires_at: UtcDatetime | None = None


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class AdminSubscriptionPage(Page):
    items: list[AdminSubscriptionItem]


# ------------------------- meetings, closures, evidence -------------------------

class MeetingState(BaseModel):
    """Where the two-party meeting confirmation stands, from the caller's point of view."""

    state: str  # NOT_AVAILABLE / WAITING_FOR_YOU / WAITING_FOR_OTHER / CONFIRMED_BY_BOTH / NOT_VERIFIED (legacy)
    you_confirmed: bool = False
    other_confirmed: bool = False
    you_confirmed_at: UtcDatetime | None = None
    other_confirmed_at: UtcDatetime | None = None


class DealRulesOut(BaseModel):
    evidence_from_minor: int
    admin_approval_from_minor: int


class EvidenceOut(BaseModel):
    id: str
    evidence_type: str
    mime: str
    size_bytes: int
    note: str | None = None
    uploaded_at: UtcDatetime
    uploaded_by_you: bool
    status: str
    rejection_reason: str | None = None
    verified_at: UtcDatetime | None = None


class ClosureOut(BaseModel):
    id: str
    referral_id: str
    status: str
    status_label: str
    verification_level: int
    verification_label: str
    actual_value_minor: int
    currency: str
    value_band: str
    value_band_label: str
    evidence_required: bool
    admin_approval_required: bool
    note: str | None = None
    reported_by_you: bool
    confirmed_by_receiver_at: UtcDatetime | None = None
    confirmed_by_referrer_at: UtcDatetime | None = None
    submitted_at: UtcDatetime
    verified_at: UtcDatetime | None = None
    rejection_reason: str | None = None
    dispute_reason: str | None = None
    can_confirm: bool = False      # you are the referrer and it awaits you
    can_dispute: bool = False
    can_edit: bool = False         # you reported it and nobody has confirmed yet
    can_cancel: bool = False
    can_add_evidence: bool = False
    evidence: list[EvidenceOut] = []


class ClosureCreate(BaseModel):
    """What the recipient reports. Rupees as a decimal; the server converts to paise,
    derives the band and decides whether evidence is needed."""

    # Decimal, never float: a rupee amount is parsed exactly. More than 2 decimal places is
    # refused rather than rounded, so there is no rounding rule to get wrong.
    actual_value: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("actual_value")
    @classmethod
    def _bounds(cls, v: Decimal) -> Decimal:
        if not v.is_finite() or not (Decimal(MIN_VALUE_MINOR) <= v * 100 <= Decimal(MAX_VALUE_MINOR)):
            raise ValueError("Enter the actual value of the business in rupees (₹1 to ₹100 crore).")
        return v

    @property
    def actual_value_minor(self) -> int:
        """Exact paise: the value has at most 2 decimal places, so this is an integer."""
        return int(self.actual_value * 100)

    @field_validator("note")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class ClosureEdit(ClosureCreate):
    pass


class ClosureConfirm(BaseModel):
    """The value the referrer was shown. If it has changed since, the confirmation is refused."""

    expected_value_minor: int = Field(ge=1)


class ClosureDispute(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class EvidenceTypeIn(BaseModel):
    evidence_type: str

    @field_validator("evidence_type")
    @classmethod
    def _type(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in EVIDENCE_TYPES:
            raise ValueError("Evidence type must be INVOICE, PAYMENT_PROOF or OTHER.")
        return v


# ------------------------------ admin referrals ------------------------------

class AdminReferralItem(BaseModel):
    id: str
    status: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    referrer: AdminPerson
    recipient: AdminPerson
    prospect_company: str | None = None
    prospect_name: str | None = None
    estimated_value_range: str | None = None
    meeting_confirmations: int = 0
    closure_status: str | None = None
    closure_level: int | None = None
    closure_band: str | None = None
    actual_value_minor: int | None = None
    flagged: bool = False
    flag_reason: str | None = None
    legacy_unverified: bool = False


class AdminReferralPage(Page):
    items: list[AdminReferralItem]


class AdminEvidenceOut(BaseModel):
    id: str
    evidence_type: str
    mime: str
    size_bytes: int
    note: str | None = None
    uploaded_by: str
    uploaded_at: UtcDatetime
    status: str
    verified_at: UtcDatetime | None = None
    verified_by: str | None = None
    rejection_reason: str | None = None
    reused_in_other_closures: int = 0


class AdminClosureOut(BaseModel):
    id: str
    status: str
    status_label: str
    verification_level: int
    verification_label: str
    actual_value_minor: int
    currency: str
    value_band: str
    value_band_label: str
    evidence_required: bool
    admin_approval_required: bool
    note: str | None = None
    reported_by: str
    confirmed_by_receiver_at: UtcDatetime | None = None
    confirmed_by_referrer_at: UtcDatetime | None = None
    submitted_at: UtcDatetime
    verified_at: UtcDatetime | None = None
    verified_by: str | None = None
    rejection_reason: str | None = None
    dispute_reason: str | None = None
    disputed_by: str | None = None
    disputed_at: UtcDatetime | None = None
    invalidated_reason: str | None = None
    evidence: list[AdminEvidenceOut] = []


class AdminTimelineEntry(BaseModel):
    at: UtcDatetime
    actor_type: str
    actor: str | None = None
    actor_role: str | None = None
    action: str
    resource_type: str
    reason: str | None = None
    before: dict | None = None
    after: dict | None = None


class AdminMeetingConfirmation(BaseModel):
    user: AdminPerson
    role: str
    confirmed_at: UtcDatetime


class AdminReferralDetail(BaseModel):
    id: str
    status: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    accepted_at: UtcDatetime | None = None
    contacted_at: UtcDatetime | None = None
    meeting_done_at: UtcDatetime | None = None
    business_closed_at: UtcDatetime | None = None
    referrer: AdminPerson
    recipient: AdminPerson
    prospect_name: str | None = None
    prospect_company: str | None = None
    opportunity: str | None = None
    estimated_value_range: str | None = None
    quality: str | None = None
    flagged: bool = False
    flag_reason: str | None = None
    meeting_verified: bool = False
    legacy_unverified: bool = False
    meeting_confirmations: list[AdminMeetingConfirmation] = []
    closure: AdminClosureOut | None = None
    past_closures: list[AdminClosureOut] = []
    timeline: list[AdminTimelineEntry] = []


class AdminNoteIn(ReasonIn):
    pass


class AdminFlagIn(BaseModel):
    flagged: bool
    reason: str = Field(min_length=3, max_length=240)


class AdminStatusCorrection(BaseModel):
    status: str = Field(min_length=3, max_length=24)
    reason: str = Field(min_length=5, max_length=240)


class AdminDisputeResolution(BaseModel):
    outcome: str  # RESTORE / REJECT / INVALIDATE
    reason: str = Field(min_length=5, max_length=240)

    @field_validator("outcome")
    @classmethod
    def _o(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in {"RESTORE", "REJECT", "INVALIDATE"}:
            raise ValueError("Outcome must be RESTORE, REJECT or INVALIDATE.")
        return v
