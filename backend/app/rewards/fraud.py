"""Fraud and gaming signals for the shadow period.

Shadow mode exists partly to discover abuse. Every signal here only creates a review item (`growth_point_flags`) for an admin.
NOTHING is punished, blocked or reduced automatically in Phase 1 (the only automatic reductions are the approved Pair
Assurance Rule and the ceilings, which are recorded on the ledger itself).

The thresholds below are ANALYSIS thresholds: where an admin starts looking. They are not business rules and carry no money.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BusinessReferral, DealClosure, GrowthPointFlag, GrowthPointLedger, utcnow
from . import ledger, rules

PAIR_FREQUENCY_WINDOW_DAYS = 30          # P4 (specification): 3 or more rewarded interactions between a pair in 30 days
PAIR_FREQUENCY_THRESHOLD = 3
CONCENTRATION_SHARE_PERCENT = 50         # P4: closed-business points in a quarter coming more than 50% from one counterparty ...
CONCENTRATION_MIN_CLOSURES = 2           # ... once there are at least two closures (one closure is always 100%)
RAPID_CLOSURE_HOURS = 24                 # P4: a closure within 24 hours of acceptance
PROSPECT_WINDOW_DAYS = 90
LOW_ACCEPTANCE_MIN_REFERRALS = 5
LOW_ACCEPTANCE_RATE_PERCENT = 30
SAME_BAND_MIN_CLOSURES = 3
HIGH_CONCENTRATION_SHARE_PERCENT = 25    # one member holding more than this share of all shadow points issued
HIGH_CONCENTRATION_MIN_MEMBERS = 5
PAIR_VOLUME_WINDOW_DAYS = 90
PAIR_VOLUME_THRESHOLD = 10               # referrals between the same two members in 90 days
CAPPED_FREQUENCY_THRESHOLD = 5           # capped (reduced) rewards for one member in 30 days


async def raise_flag(db: AsyncSession, kind: str, severity: str = "INFO", *, member_id: str | None = None, pair_key: str | None = None,
                     reference_type: str | None = None, reference_id: str | None = None, dedupe: str, details: dict | None = None) -> bool:
    """Queue a review item once (the dedupe key makes a repeat harmless). Returns True if it was created."""
    key = f"{kind}:{dedupe}"[:160]
    if await db.scalar(select(GrowthPointFlag.id).where(GrowthPointFlag.dedupe_key == key)):
        return False
    db.add(GrowthPointFlag(kind=kind, severity=severity, member_id=member_id, pair_key=pair_key, reference_type=reference_type,
                           reference_id=reference_id, details=json.dumps(details, default=str) if details else None, dedupe_key=key))
    await db.flush()
    return True


async def after_referral(db: AsyncSession, ref: BusinessReferral, now: datetime | None = None) -> None:
    now = now or utcnow()
    pair = ledger.pair_key(ref.giver_user_id, ref.receiver_user_id)
    if ref.accepted_at is None:
        return
    if ref.prospect_phone:
        others = (await db.execute(
            select(BusinessReferral.giver_user_id, BusinessReferral.receiver_user_id).where(
                BusinessReferral.prospect_phone == ref.prospect_phone, BusinessReferral.id != ref.id,
                BusinessReferral.created_at >= now - timedelta(days=PROSPECT_WINDOW_DAYS)))).all()
        if any(ledger.pair_key(a, b) != pair for a, b in others):
            await raise_flag(db, "SAME_PROSPECT_ACROSS_PAIRS", "WARN", pair_key=pair, reference_type="referral", reference_id=ref.id, dedupe=f"{ref.id}",
                             details={"other_referrals": len(others)})
    reverse = await db.scalar(select(func.count(BusinessReferral.id)).where(
        BusinessReferral.giver_user_id == ref.receiver_user_id, BusinessReferral.receiver_user_id == ref.giver_user_id, BusinessReferral.accepted_at.is_not(None)))
    if reverse:
        await raise_flag(db, "RECIPROCAL_REFERRALS", "INFO", pair_key=pair, reference_type="referral", reference_id=ref.id, dedupe=f"{pair}")
    recent = int(await db.scalar(select(func.count(func.distinct(GrowthPointLedger.reference_id))).where(
        GrowthPointLedger.pair_key == pair, GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.points_delta > 0,
        GrowthPointLedger.created_at >= now - timedelta(days=PAIR_FREQUENCY_WINDOW_DAYS))) or 0)
    if recent >= PAIR_FREQUENCY_THRESHOLD:
        await raise_flag(db, "PAIR_FREQUENCY", "WARN", pair_key=pair, dedupe=f"{pair}:{rules.month_key(now)}", details={"rewarded_interactions_30d": recent})


async def after_closure(db: AsyncSession, ref: BusinessReferral, closure: DealClosure, now: datetime | None = None) -> None:
    now = now or utcnow()
    pair = ledger.pair_key(ref.giver_user_id, ref.receiver_user_id)
    if ref.accepted_at is not None and closure.submitted_at is not None:
        if rules.aware(closure.submitted_at) - rules.aware(ref.accepted_at) < timedelta(hours=RAPID_CLOSURE_HOURS):
            await raise_flag(db, "RAPID_CLOSURE", "WARN", pair_key=pair, reference_type="deal_closure", reference_id=closure.id, dedupe=closure.id,
                             details={"hours_after_acceptance": RAPID_CLOSURE_HOURS})
    if closure.value_band == "10L_PLUS":
        await raise_flag(db, "HIGH_VALUE_CLOSURE", "INFO", pair_key=pair, reference_type="deal_closure", reference_id=closure.id, dedupe=closure.id)
    quarter = rules.quarter_key(closure.verified_at or now)
    for member in (ref.giver_user_id, ref.receiver_user_id):
        rows = (await db.execute(
            select(GrowthPointLedger.pair_key, func.sum(GrowthPointLedger.points_delta), func.count(func.distinct(GrowthPointLedger.reference_id))).where(
                GrowthPointLedger.member_id == member, GrowthPointLedger.entry_type.in_(("EARN", "VOID", "REVERSAL")),
                GrowthPointLedger.event_type.in_(("BUSINESS_CLOSED", "REPEAT_BUSINESS")), GrowthPointLedger.quarter_key == quarter)
            .group_by(GrowthPointLedger.pair_key))).all()
        total = sum(int(r[1] or 0) for r in rows)
        closures = sum(int(r[2] or 0) for r in rows)
        if total > 0 and closures >= CONCENTRATION_MIN_CLOSURES:
            top = max(rows, key=lambda r: int(r[1] or 0))
            if int(top[1] or 0) * 100 > total * CONCENTRATION_SHARE_PERCENT:
                await raise_flag(db, "MEMBER_CLOSURE_CONCENTRATION", "WARN", member_id=member, pair_key=top[0], dedupe=f"{member}:{quarter}",
                                 details={"share_percent": int(top[1]) * 100 // total, "closures": closures})


async def scan(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Batch analysis over everything recorded so far (idempotent). Returns how many NEW flags each check raised."""
    now = now or utcnow()
    new: dict[str, int] = {}

    def bump(kind: str, created: bool) -> None:
        new[kind] = new.get(kind, 0) + int(created)

    # low acceptance rate among referrers
    rows = (await db.execute(
        select(BusinessReferral.giver_user_id, func.count(BusinessReferral.id), func.count(BusinessReferral.accepted_at))
        .group_by(BusinessReferral.giver_user_id))).all()
    for giver, total, accepted in rows:
        accepted = int(accepted or 0)
        if total >= LOW_ACCEPTANCE_MIN_REFERRALS and accepted * 100 < total * LOW_ACCEPTANCE_RATE_PERCENT:
            bump("LOW_ACCEPTANCE_RATE", await raise_flag(db, "LOW_ACCEPTANCE_RATE", "INFO", member_id=giver, dedupe=f"{giver}:{rules.quarter_key(now)}",
                                                         details={"referrals": total, "accepted": accepted}))
    # the same two members interacting unusually often
    pair_rows = (await db.execute(
        select(BusinessReferral.giver_user_id, BusinessReferral.receiver_user_id, func.count(BusinessReferral.id))
        .where(BusinessReferral.created_at >= now - timedelta(days=PAIR_VOLUME_WINDOW_DAYS))
        .group_by(BusinessReferral.giver_user_id, BusinessReferral.receiver_user_id))).all()
    volume: dict[str, int] = {}
    for a, b, n in pair_rows:
        volume[ledger.pair_key(a, b)] = volume.get(ledger.pair_key(a, b), 0) + int(n)
    for pair, n in volume.items():
        if n >= PAIR_VOLUME_THRESHOLD:
            bump("PAIR_VOLUME", await raise_flag(db, "PAIR_VOLUME", "WARN", pair_key=pair, dedupe=f"{pair}:{rules.quarter_key(now)}", details={"referrals_90d": n}))
    # one band, again and again
    band_rows = (await db.execute(
        select(BusinessReferral.giver_user_id, DealClosure.value_band, func.count(DealClosure.id))
        .join(BusinessReferral, BusinessReferral.id == DealClosure.referral_id).where(DealClosure.status == "VERIFIED")
        .group_by(BusinessReferral.giver_user_id, DealClosure.value_band))).all()
    for giver, band, n in band_rows:
        if n >= SAME_BAND_MIN_CLOSURES:
            bump("REPEATED_DEAL_BAND", await raise_flag(db, "REPEATED_DEAL_BAND", "INFO", member_id=giver, dedupe=f"{giver}:{band}", details={"band": band, "closures": n}))
    # reward concentration
    totals = (await db.execute(
        select(GrowthPointLedger.member_id, func.sum(GrowthPointLedger.points_delta)).where(GrowthPointLedger.entry_type.in_(("EARN", "VOID", "REVERSAL")))
        .group_by(GrowthPointLedger.member_id))).all()
    grand = sum(int(t[1] or 0) for t in totals)
    if len(totals) >= HIGH_CONCENTRATION_MIN_MEMBERS and grand > 0:
        top = max(totals, key=lambda t: int(t[1] or 0))
        if int(top[1]) * 100 > grand * HIGH_CONCENTRATION_SHARE_PERCENT:
            bump("HIGH_REWARD_CONCENTRATION", await raise_flag(db, "HIGH_REWARD_CONCENTRATION", "INFO", member_id=top[0], dedupe=f"{top[0]}:{rules.quarter_key(now)}",
                                                               details={"share_percent": int(top[1]) * 100 // grand}))
    # repeatedly capped rewards
    capped = (await db.execute(
        select(GrowthPointLedger.member_id, func.count(GrowthPointLedger.id)).where(
            GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.capped_points > 0, GrowthPointLedger.created_at >= now - timedelta(days=30))
        .group_by(GrowthPointLedger.member_id))).all()
    for member, n in capped:
        if n >= CAPPED_FREQUENCY_THRESHOLD:
            bump("REPEATEDLY_CAPPED", await raise_flag(db, "REPEATEDLY_CAPPED", "INFO", member_id=member, dedupe=f"{member}:{rules.month_key(now)}", details={"capped_rewards_30d": n}))
    return new

