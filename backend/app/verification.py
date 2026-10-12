"""Business rules for verifying referral outcomes (Phase 0).

Pure functions and constants only, so the rules live in one place and are
easy to test. Nothing here awards, calculates or applies Growth Points.

Money is stored in integer paise (1 rupee = 100 paise), never floats.
"""
from __future__ import annotations

from .config import settings

RUPEE = 100  # paise

# ---- deal value bands (derived by the server from the ACTUAL closed value) ----
# Lower bound inclusive, upper bound exclusive: exactly Rs 1,00,000 is in "1L_5L".
BAND_UNDER_25K = "UNDER_25K"
BAND_25K_1L = "25K_1L"
BAND_1L_5L = "1L_5L"
BAND_5L_10L = "5L_10L"
BAND_10L_PLUS = "10L_PLUS"
BANDS = (BAND_UNDER_25K, BAND_25K_1L, BAND_1L_5L, BAND_5L_10L, BAND_10L_PLUS)
BAND_LABEL = {
    BAND_UNDER_25K: "Under ₹25,000",
    BAND_25K_1L: "₹25,000 – ₹1,00,000",
    BAND_1L_5L: "₹1,00,000 – ₹5,00,000",
    BAND_5L_10L: "₹5,00,000 – ₹10,00,000",
    BAND_10L_PLUS: "₹10,00,000+",
}
_BAND_EDGES = ((25_000 * RUPEE, BAND_UNDER_25K), (100_000 * RUPEE, BAND_25K_1L), (500_000 * RUPEE, BAND_1L_5L), (1_000_000 * RUPEE, BAND_5L_10L))

MIN_VALUE_MINOR = 1 * RUPEE                # Rs 1
MAX_VALUE_MINOR = 1_000_000_000 * RUPEE    # Rs 100 crore: a typo guard, not a business limit
MAX_EVIDENCE_PER_CLOSURE = 5


# The thresholds below are CONFIGURATION (app.config), not constants, and are AWAITING
# MANAGEMENT CONFIRMATION (settings.deal_thresholds_confirmed). They are read at call
# time and the outcome is frozen onto each closure when it is reported, so changing
# them later never rewrites an existing record.
def evidence_from_minor() -> int:
    return settings.deal_evidence_threshold_inr * RUPEE


def admin_approval_from_minor() -> int:
    return settings.deal_admin_approval_threshold_inr * RUPEE


def quick_close_hours() -> int:
    """A closure reported sooner than this after the referral was accepted is flagged for review."""
    return settings.deal_quick_close_hours


def value_band(minor: int) -> str:
    for edge, band in _BAND_EDGES:
        if minor < edge:
            return band
    return BAND_10L_PLUS


def evidence_required(minor: int) -> bool:
    return minor >= evidence_from_minor()


def admin_approval_required(minor: int) -> bool:
    return minor >= admin_approval_from_minor()


# ---- verification levels (infrastructure only; they map to nothing financial) ----
L0_SELF_REPORTED = 0   # one party said so
L1_COUNTERPARTY = 1    # the other party confirmed a single step
L2_BOTH_CONFIRMED = 2  # both parties confirmed
L3_EVIDENCE = 3        # supporting evidence was verified
L4_ADMIN = 4           # an admin verified the outcome
LEVEL_LABEL = {
    0: "Self-reported",
    1: "Confirmed by the other member",
    2: "Confirmed by both members",
    3: "Evidence verified",
    4: "Verified by TGL",
}

# ---- closure lifecycle ----
AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"  # reported by the recipient; the referrer has not answered
AWAITING_EVIDENCE = "AWAITING_EVIDENCE"          # both confirmed; evidence required and not yet usable
UNDER_REVIEW = "UNDER_REVIEW"                    # evidence submitted; an admin has not finished
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
DISPUTED = "DISPUTED"
CANCELLED = "CANCELLED"
INVALIDATED = "INVALIDATED"                      # a verified outcome later found wrong, refunded or withdrawn
CLOSURE_STATUSES = (AWAITING_CONFIRMATION, AWAITING_EVIDENCE, UNDER_REVIEW, VERIFIED, REJECTED, DISPUTED, CANCELLED, INVALIDATED)
CLOSURE_ENDED = frozenset({REJECTED, CANCELLED, INVALIDATED})
CLOSURE_LABEL = {
    AWAITING_CONFIRMATION: "Awaiting the referrer's confirmation",
    AWAITING_EVIDENCE: "Awaiting evidence",
    UNDER_REVIEW: "Under review by TGL",
    VERIFIED: "Verified",
    REJECTED: "Rejected",
    DISPUTED: "Disputed",
    CANCELLED: "Cancelled",
    INVALIDATED: "Invalidated",
}

# status -> statuses an ordinary transition may reach. Enforced in the router
# and asserted in tests; the live-closure unique index backs it in the database.
CLOSURE_TRANSITIONS = {
    AWAITING_CONFIRMATION: {AWAITING_EVIDENCE, VERIFIED, DISPUTED, CANCELLED, REJECTED},
    AWAITING_EVIDENCE: {UNDER_REVIEW, DISPUTED, CANCELLED, INVALIDATED, REJECTED},
    UNDER_REVIEW: {VERIFIED, REJECTED, AWAITING_EVIDENCE, DISPUTED, INVALIDATED},
    VERIFIED: {DISPUTED, INVALIDATED},
    DISPUTED: {AWAITING_CONFIRMATION, AWAITING_EVIDENCE, UNDER_REVIEW, VERIFIED, REJECTED, INVALIDATED},
    REJECTED: set(),
    CANCELLED: set(),
    INVALIDATED: set(),
}

EVIDENCE_TYPES = ("INVOICE", "PAYMENT_PROOF", "OTHER")
EVIDENCE_PENDING, EVIDENCE_VERIFIED, EVIDENCE_REJECTED = "PENDING", "VERIFIED", "REJECTED"

# ---- meeting confirmation ----
MEETING = "MEETING"
# A meeting can only be confirmed once the referral has been accepted.
MEETING_CONFIRMABLE_STATUSES = frozenset({"ACCEPTED", "CONTACTED"})
