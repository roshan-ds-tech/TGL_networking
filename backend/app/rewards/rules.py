"""The Growth Points rules, in ONE place (rule version `growth-points-v3`).

Source of truth: docs/GROWTH_POINTS_FINAL_SPEC.md (v3) and docs/GROWTH_POINTS_ECONOMY_RECALCULATION.md.
Nothing outside this module may contain a point value, a ceiling or a percentage. Routes never do arithmetic.

Money is integer paise: 1 point = Rs 0.10 = 10 paise, so every conversion is integer arithmetic.

Changing a number here is a business change that needs management approval. It must come with a NEW `RULE_VERSION`
(the old version's parameters stay in the database, `growth_point_rule_versions`, and every ledger row records the version
it was computed under; history is never recomputed). `ensure_rule_version()` refuses to run if the code's parameters differ
from what is stored for the same version.

This is shadow mode: these rules decide what points a member WOULD have. They have no monetary effect.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

RULE_VERSION = "growth-points-v3"

# ---------------------------------------------------------------- value
PAISE_PER_POINT = 10                  # 1 point = Rs 0.10
REDEMPTION_CAP_PERMILLE = 150         # contractual: 15% of the plan price, once per invoice (hypothetical in Phase 1)
EARNING_CEILING_PERMILLE = 120        # practical: 12% of the plan price per subscription cycle

# ---------------------------------------------------------------- ceilings
SUBCEILING_PERCENT = {"PROCESS": 25, "CLOSURE": 60, "OTHER": 20}      # shares of the cycle ceiling
DAILY_CEILING_LOW_ASSURANCE = 500     # points per calendar day; low-assurance (L1/L2) points only
MONTHLY_CEILING = 3_000               # points per calendar month, all points

# ---------------------------------------------------------------- timing
PENDING_DAYS = 7                      # L1 / L2 points are PENDING this long, then AVAILABLE
RENEWAL_WINDOW_BEFORE_DAYS = 30       # the renewal window opens this long before the term ends ...
GRACE_DAYS = 30                       # ... and closes this long after it; unused points expire at the end of grace
REVERSAL_WINDOW_DAYS = 60             # a deal found false / refunded / disputed within this long is reversed automatically
CONTACT_WINDOW_HOURS = 72             # "prospect contacted" must follow acceptance within this long
BUSINESS_TZ_OFFSET_MINUTES = 330      # calendar days, months and quarters are Indian Standard Time (UTC+05:30, no DST)

# ---------------------------------------------------------------- closed business
CLOSURE_POOL = {"UNDER_25K": 300, "25K_1L": 750, "1L_5L": 1_500, "5L_10L": 2_100, "10L_PLUS": 2_700}   # points per deal, by server-derived band
REFERRER_SHARE_PERCENT = 70           # of the pool; the recipient receives the rest (30%)
REPEAT_FACTOR_PERCENT = 50            # repeat business from the same prospect pays half the band pool

# ---------------------------------------------------------------- Pair Assurance Rule (per calendar quarter)
PAIR_LOW_ASSURANCE_BUDGET = 1_500     # P1: low-assurance points between two members, both directions combined
PAIR_FULL_VERIFIED_CLOSURES = 2       # P3: the first two verified closures per pair pay in full ...
PAIR_RECIPROCAL_FACTOR_PERCENT = 50   # ... a reciprocal one needs L4 and pays this share; a third or later pays 0
LOW_ASSURANCE_MAX_LEVEL = 2           # L1, L2 = low assurance; L3, L4 = verified

# ---------------------------------------------------------------- event catalogue
# Every reward the engine can issue. `enabled=False` rows are in the approved table but their feature does not exist yet,
# so nothing can trigger them (specification section 5 marks them "future").
EVENTS: dict[str, dict] = {
    "REFERRAL_ACCEPTED": dict(
        enabled=True, category="PROCESS", level=1, once_per="referral",
        referrer=30, referrer_bonus_quality=("DIRECT_INTRO", "MEETING_ARRANGED"), referrer_bonus=15, recipient=15,
        monthly_limit={"referrer": 10},
        note="Recipient accepted; the referrer earns 30 (+15 for a direct introduction or an arranged meeting), the recipient 15",
    ),
    "PROSPECT_CONTACTED": dict(
        enabled=True, category="PROCESS", level=1, once_per="referral", recipient=15, window_hours=CONTACT_WINDOW_HOURS,
        note="Recipient contacted the prospect within 72 hours of accepting",
    ),
    "MEETING_COMPLETED": dict(
        enabled=True, category="PROCESS", level=2, once_per="referral", referrer=45, recipient=60, monthly_limit={"referrer": 8},
        note="Both members confirmed the meeting (Phase 0 two-party confirmation)",
    ),
    "BUSINESS_CLOSED": dict(
        enabled=True, category="CLOSURE", level=None, once_per="closure", pool=CLOSURE_POOL,
        note="A verified deal closure; points come from the server-derived band of the ACTUAL value, 70% referrer / 30% recipient",
    ),
    "REPEAT_BUSINESS": dict(
        enabled=True, category="CLOSURE", level=None, once_per="closure", pool=CLOSURE_POOL, factor_percent=REPEAT_FACTOR_PERCENT,
        note="A verified closure for a prospect who already produced a rewarded closure: 50% of the band pool, once per prospect per quarter",
    ),
    "PROFILE_COMPLETED": dict(
        enabled=True, category="OTHER", level=3, once_per="member", member=75,
        note="Personal profile, business profile with founder story and an online link, and a profile photo; once per member",
    ),
    # --- approved but not yet buildable: the features do not exist, so no code path can issue them
    "EVENT_ATTENDED": dict(enabled=False, category="OTHER", level=3, member=45, quarterly_limit=3, note="future: needs admin event check-in"),
    "SUCCESSFUL_INTRODUCTION": dict(enabled=False, category="OTHER", level=2, member=75, note="future: needs an introductions feature"),
    "NEED_RESOLVED": dict(enabled=False, category="OTHER", level=2, member=60, quarterly_limit=4, note="future: needs poster confirmation"),
    "MENTORING_SESSION": dict(enabled=False, category="OTHER", level=2, member=90, quarterly_limit=3, note="future: needs a mentoring feature"),
    "MEMBER_INVITED": dict(enabled=False, category="OTHER", level=3, member=225, quarterly_limit=3, note="future: needs invitations"),
}
ENABLED_EVENTS = tuple(k for k, v in EVENTS.items() if v["enabled"])
# Things that must NEVER earn points (specification section 1): kept as data so a test can prove no code issues them.
ZERO_POINT_ACTIONS = ("REFERRAL_CREATED", "PROFILE_VIEW", "LIKE", "LOGIN", "CONNECTION", "NEED_POSTED", "NEED_REPLIED")

# SIM_REDEEM is the HYPOTHETICAL use of old-cycle points against a renewal invoice. It is a shadow-ledger row only: it never touches an invoice.
ENTRY_TYPES = ("EARN", "VOID", "REVERSAL", "EXPIRY", "SIM_REDEEM")
STATUSES = ("PENDING", "AVAILABLE", "CAPPED", "VOIDED", "REVERSED", "EXPIRED", "SIMULATED")
RENEWAL_OUTCOMES = ("REDEEMED", "NOTHING_ELIGIBLE", "NOT_A_RENEWAL", "REFUNDED_CYCLE")
CATEGORIES = ("PROCESS", "CLOSURE", "OTHER")

# Names stored in `capped_by` (the first rule that reduced a reward) and in the cap trace.
CAP_PAIR_LOW_ASSURANCE = "PAIR_LOW_ASSURANCE"
CAP_PAIR_CONCENTRATION = "PAIR_CONCENTRATION"
CAP_PAIR_RECIPROCAL = "PAIR_RECIPROCAL"
CAP_PAIR_RECIPROCAL_NEEDS_L4 = "PAIR_RECIPROCAL_NEEDS_L4"
CAP_FREQUENCY = "FREQUENCY_LIMIT"
CAP_REPEAT = "REPEAT_LIMIT"
CAP_SUBCEILING = "CATEGORY_SUBCEILING"
CAP_DAILY = "DAILY_CEILING"
CAP_MONTHLY = "MONTHLY_CEILING"
CAP_CYCLE = "CYCLE_CEILING"
CAP_NO_CYCLE = "NO_ACTIVE_CYCLE"
CAP_OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
CAP_NOT_ELIGIBLE = "NOT_ELIGIBLE"


# ---------------------------------------------------------------- derived values (integer arithmetic only)
def points_to_paise(points: int) -> int:
    return points * PAISE_PER_POINT


def cycle_ceiling_points(price_minor: int) -> int:
    """12% of the plan price, in points: 3,600 / 6,000 / 12,000 for Rs 3,000 / 5,000 / 10,000."""
    return price_minor * EARNING_CEILING_PERMILLE // (1000 * PAISE_PER_POINT)


def redemption_cap_paise(price_minor: int) -> int:
    """The contractual ceiling: 15% of the plan price (hypothetical in Phase 1)."""
    return price_minor * REDEMPTION_CAP_PERMILLE // 1000


def redemption_cap_points(price_minor: int) -> int:
    return redemption_cap_paise(price_minor) // PAISE_PER_POINT


def category_ceilings(price_minor: int) -> dict[str, int]:
    total = cycle_ceiling_points(price_minor)
    return {k: total * pct // 100 for k, pct in SUBCEILING_PERCENT.items()}


def split_pool(pool: int, factor_percent: int = 100) -> tuple[int, int]:
    """(referrer, recipient) points of a closure pool. Floor for the referrer, the remainder to the recipient, so the total is exact."""
    total = pool * factor_percent // 100
    referrer = total * REFERRER_SHARE_PERCENT // 100
    return referrer, total - referrer


def assurance_of(level: int) -> str:
    return "LOW" if level <= LOW_ASSURANCE_MAX_LEVEL else "VERIFIED"


# ---------------------------------------------------------------- calendar (business time)
_IST = timezone(timedelta(minutes=BUSINESS_TZ_OFFSET_MINUTES))


def local(dt: datetime) -> datetime:
    """A moment in business time. Naive datetimes (SQLite) are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_IST)


def day_key(dt: datetime) -> str:
    return local(dt).strftime("%Y-%m-%d")


def month_key(dt: datetime) -> str:
    return local(dt).strftime("%Y-%m")


def quarter_key(dt: datetime) -> str:
    d = local(dt)
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- versioning
def parameters() -> dict:
    """Every number of this version, as plain data (stored once per version, hashed to detect drift)."""
    return {
        "rule_version": RULE_VERSION, "paise_per_point": PAISE_PER_POINT, "redemption_cap_permille": REDEMPTION_CAP_PERMILLE,
        "earning_ceiling_permille": EARNING_CEILING_PERMILLE, "subceiling_percent": SUBCEILING_PERCENT,
        "daily_ceiling_low_assurance": DAILY_CEILING_LOW_ASSURANCE, "monthly_ceiling": MONTHLY_CEILING, "pending_days": PENDING_DAYS,
        "renewal_window_before_days": RENEWAL_WINDOW_BEFORE_DAYS, "grace_days": GRACE_DAYS, "reversal_window_days": REVERSAL_WINDOW_DAYS,
        "contact_window_hours": CONTACT_WINDOW_HOURS, "business_tz_offset_minutes": BUSINESS_TZ_OFFSET_MINUTES, "closure_pool": CLOSURE_POOL,
        "referrer_share_percent": REFERRER_SHARE_PERCENT, "repeat_factor_percent": REPEAT_FACTOR_PERCENT,
        "pair_low_assurance_budget": PAIR_LOW_ASSURANCE_BUDGET, "pair_full_verified_closures": PAIR_FULL_VERIFIED_CLOSURES,
        "pair_reciprocal_factor_percent": PAIR_RECIPROCAL_FACTOR_PERCENT, "low_assurance_max_level": LOW_ASSURANCE_MAX_LEVEL,
        "events": EVENTS,
    }


def parameters_json() -> str:
    return json.dumps(parameters(), sort_keys=True, default=list)


def parameters_hash() -> str:
    return hashlib.sha256(parameters_json().encode()).hexdigest()
