"""From verified networking state to shadow rewards.

Everything here is STATE-DRIVEN and idempotent: `sync_referral`, `sync_closure` and `sync_profile` look at what the database now
says (the Phase 0 verified records), decide which rewards should exist, and issue only the missing ones. So a retry after a
timeout, a replayed request, a double click, a backfill and a concurrent call all converge on exactly one reward per
(member, event, reference). Nothing here trusts a client: points, bands, levels and roles come from the stored, verified rows.

Specification: docs/GROWTH_POINTS_FINAL_SPEC.md section 5 (reward table) and section 2 (Pair Assurance Rule).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import verification as phase0
from ..models import (
    AuditLog, Business, BusinessReferral, DealClosure, GrowthPointLedger, PersonalProfile, ReferralConfirmation, User, utcnow,
)
from . import cycles, engine, fraud, ledger, rules
from .engine import AwardRequest

CLOSED_REFERRAL_STATES = ("DECLINED", "CANCELLED", "CLOSED")
CLOSURE_INVALID_STATES = ("DISPUTED", "INVALIDATED", "REJECTED", "CANCELLED")
CLOSURE_EVENTS = ("BUSINESS_CLOSED", "REPEAT_BUSINESS")


def prospect_key(phone: str | None) -> str | None:
    """A truncated hash of the prospect's phone: enough to see 'the same prospect again', never the number itself."""
    return hashlib.sha256(phone.encode()).hexdigest()[:16] if phone else None


async def _audit_exists(db: AsyncSession, resource_id: str, action: str, contains: str | None = None) -> bool:
    q = select(func.count(AuditLog.id)).where(AuditLog.resource_id == resource_id, AuditLog.action == action)
    if contains:
        q = q.where(AuditLog.after_json.like(f"%{contains}%"))
    return bool(await db.scalar(q))


async def meeting_verified(db: AsyncSession, referral_id: str) -> bool:
    roles = set((await db.execute(select(ReferralConfirmation.role).where(
        ReferralConfirmation.referral_id == referral_id, ReferralConfirmation.kind == phase0.MEETING))).scalars().all())
    return roles >= {"giver", "receiver"}


# ----------------------------------------------------------------------------------------------- retiring lots
async def retire(db: AsyncSession, lots: list[ledger.Lot], *, reason: str, available: str, now: datetime, created_by: str = "system",
                 flag: tuple | None = None) -> int:
    """Pending lots are VOIDED. Lots already usable are, per `available`: 'reverse' (REVERSAL, only within the 60-day window,
    otherwise a review flag), or 'flag' (left in place, queued for an admin). Returns the number of adjustments written."""
    n = 0
    for lot in lots:
        if lot.remaining <= 0 or lot.state == "EXPIRED":
            continue
        if lot.state == "PENDING":
            n += bool(await engine.adjust(db, lot, "VOID", reason, created_by))
        elif available == "reverse" and (now - rules.aware(lot.row.created_at)) <= timedelta(days=rules.REVERSAL_WINDOW_DAYS):
            n += bool(await engine.adjust(db, lot, "REVERSAL", reason, created_by))
        else:
            await fraud.raise_flag(
                db, "REVERSAL_NEEDS_REVIEW", "HIGH", member_id=lot.row.member_id, pair_key=lot.row.pair_key, reference_type=lot.row.reference_type,
                reference_id=lot.row.reference_id, dedupe=f"reversal-review:{lot.row.id}",
                details={"lot_id": lot.row.id, "reason": reason, "points": lot.remaining, "status": lot.state,
                         "why": "points already usable and outside the automatic 60-day window" if available == "reverse" else "points already usable"},
            )
    return n


async def still_invalid(db: AsyncSession, lot: ledger.Lot) -> bool:
    """Is the thing behind these points still disputed / invalidated / closed? A late reversal is only applied while it is."""
    kind, rid = lot.row.reference_type, lot.row.reference_id
    if kind == "deal_closure":
        closure = await db.get(DealClosure, rid)
        return closure is None or closure.status in CLOSURE_INVALID_STATES
    if kind == "referral":
        ref = await db.get(BusinessReferral, rid)
        if ref is None or ref.status in CLOSED_REFERRAL_STATES:
            return True
        if lot.row.event_type == "MEETING_COMPLETED":
            return not await meeting_verified(db, rid) or await _audit_exists(db, rid, "referral.meeting_disputed")
    return False


# ----------------------------------------------------------------------------------------------- referral events
async def sync_referral(db: AsyncSession, referral_id: str, now: datetime | None = None) -> dict:
    """Issue / void the rewards that follow from a referral's current verified state. Returns a small summary."""
    now = now or utcnow()
    ref = await db.get(BusinessReferral, referral_id, populate_existing=True)
    summary = {"awarded": 0, "voided": 0}
    if ref is None:
        return summary
    giver, receiver = ref.giver_user_id, ref.receiver_user_id
    await engine.lock_members(db, [giver, receiver])
    existing = await ledger.lots(db, reference_type="referral", reference_id=ref.id, now=now)

    if ref.status in CLOSED_REFERRAL_STATES:
        # a declined, cancelled or closed referral voids pending points; points already usable are left for review
        summary["voided"] = await retire(db, existing, reason=f"Referral {ref.status.lower()}", available="flag", now=now)
        return summary

    async def give(event: str, member: str, other: str, role: str, points: int, level: int, at: datetime, *, ineligible=None, details=None) -> None:
        res = await engine.award(db, AwardRequest(
            member_id=member, counterparty_id=other, role=role, event_type=event, reference_type="referral", reference_id=ref.id, requested=points,
            level=level, event_at=at, ineligible=ineligible, details=details or {}, reason=rules.EVENTS[event]["note"]), now)
        summary["awarded"] += int(res.created)

    if ref.accepted_at is not None and ref.status != "GIVEN":
        spec = rules.EVENTS["REFERRAL_ACCEPTED"]
        bonus = spec["referrer_bonus"] if ref.quality in spec["referrer_bonus_quality"] else 0
        at = ref.accepted_at
        await give("REFERRAL_ACCEPTED", giver, receiver, "referrer", spec["referrer"] + bonus, spec["level"], at, details={"quality": ref.quality})
        await give("REFERRAL_ACCEPTED", receiver, giver, "recipient", spec["recipient"], spec["level"], at)

    if ref.contacted_at is not None and ref.accepted_at is not None and await _audit_exists(db, ref.id, "referral.status_changed", '"CONTACTED"'):
        spec = rules.EVENTS["PROSPECT_CONTACTED"]
        within = rules.aware(ref.contacted_at) - rules.aware(ref.accepted_at) <= timedelta(hours=spec["window_hours"])
        await give("PROSPECT_CONTACTED", receiver, giver, "recipient", spec["recipient"], spec["level"], ref.contacted_at,
                   ineligible=None if within else (rules.CAP_OUTSIDE_WINDOW, "Contacted more than 72 hours after accepting"))

    meeting_lots = [l for l in existing if l.row.event_type == "MEETING_COMPLETED"]
    if ref.meeting_done_at is not None and ref.status in ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED") \
            and await meeting_verified(db, ref.id) and not await _audit_exists(db, ref.id, "referral.meeting_disputed"):
        spec = rules.EVENTS["MEETING_COMPLETED"]
        await give("MEETING_COMPLETED", giver, receiver, "referrer", spec["referrer"], spec["level"], ref.meeting_done_at)
        await give("MEETING_COMPLETED", receiver, giver, "recipient", spec["recipient"], spec["level"], ref.meeting_done_at)
    elif meeting_lots:
        # the meeting is no longer verified, or was disputed: pending meeting points are voided, usable ones go to review
        summary["voided"] += await retire(db, meeting_lots, reason="Meeting disputed or no longer verified", available="flag", now=now)

    if summary["awarded"]:                                     # review signals are evaluated when something was newly rewarded, not on every replay
        await fraud.after_referral(db, ref, now)
    return summary


# ----------------------------------------------------------------------------------------------- closure events
async def _prior_verified_closures(db: AsyncSession, pair: str, quarter: str, exclude_closure: str, before: datetime | None) -> list[tuple]:
    """Verified closures already rewarded for this pair in this calendar quarter: [(closure_id, referrer_id)], earliest first."""
    q = (
        select(GrowthPointLedger.reference_id, func.min(GrowthPointLedger.created_at), BusinessReferral.giver_user_id)
        .join(DealClosure, DealClosure.id == GrowthPointLedger.reference_id)
        .join(BusinessReferral, BusinessReferral.id == DealClosure.referral_id)
        .where(GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.event_type.in_(CLOSURE_EVENTS), GrowthPointLedger.pair_key == pair,
               GrowthPointLedger.quarter_key == quarter, GrowthPointLedger.assurance == "VERIFIED", GrowthPointLedger.reference_id != exclude_closure,
               DealClosure.status == phase0.VERIFIED)
        .group_by(GrowthPointLedger.reference_id, BusinessReferral.giver_user_id)
        .order_by(func.min(GrowthPointLedger.created_at))
    )
    rows = (await db.execute(q)).all()
    return [(r[0], r[2]) for r in rows if before is None or rules.aware(r[1]) < rules.aware(before)]


async def sync_closure(db: AsyncSession, closure_id: str, now: datetime | None = None, *, pair_exception: bool = False, reeval: bool = False,
                       created_by: str = "system", reason: str = "") -> dict:
    """Issue / reverse the rewards that follow from a deal closure's current verified state."""
    now = now or utcnow()
    closure = await db.get(DealClosure, closure_id, populate_existing=True)
    summary = {"awarded": 0, "reversed": 0}
    if closure is None:
        return summary
    ref = await db.get(BusinessReferral, closure.referral_id, populate_existing=True)
    if ref is None:
        return summary
    giver, receiver = ref.giver_user_id, ref.receiver_user_id
    await engine.lock_members(db, [giver, receiver])
    existing = await ledger.lots(db, reference_type="deal_closure", reference_id=closure.id, now=now)

    if closure.status in CLOSURE_INVALID_STATES:
        # a deal found false / refunded / disputed within 60 days is reversed; pending points are simply voided
        summary["reversed"] = await retire(db, existing, reason=f"Closed business {closure.status.lower()}", available="reverse", now=now, created_by=created_by)
        return summary
    if closure.status != phase0.VERIFIED:
        return summary                                         # no reward is ever issued from an unverified or self-reported closure

    level = int(closure.verification_level)
    if level < phase0.L2_BOTH_CONFIRMED or (closure.evidence_required and level < phase0.L3_EVIDENCE) \
            or (closure.admin_approval_required and level < phase0.L4_ADMIN):
        return summary                                         # defensive: the verification the amount requires has not happened

    pool = rules.CLOSURE_POOL.get(closure.value_band)           # the SERVER-derived band of the ACTUAL verified value
    if pool is None:
        return summary
    pair = ledger.pair_key(giver, receiver)
    at = closure.verified_at or closure.updated_at or now
    quarter = rules.quarter_key(at)
    pkey = prospect_key(ref.prospect_phone)

    # repeat business: this prospect already produced a rewarded, still-verified closure on ANOTHER referral
    event = "BUSINESS_CLOSED"
    if pkey:
        earlier = await db.scalar(
            select(func.count(GrowthPointLedger.id)).join(DealClosure, DealClosure.id == GrowthPointLedger.reference_id)
            .where(GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.points_delta > 0, GrowthPointLedger.event_type.in_(CLOSURE_EVENTS),
                   GrowthPointLedger.prospect_key == pkey, GrowthPointLedger.reference_id != closure.id, DealClosure.status == phase0.VERIFIED,
                   GrowthPointLedger.created_at < (min((l.row.created_at for l in existing), default=now))))
        if earlier:
            event = "REPEAT_BUSINESS"
    # Pair Assurance Rule for VERIFIED closures (level 3 or 4); low-assurance (level 2) closures use the pair budget in award()
    adjust: tuple[int, str] | None = None
    if rules.assurance_of(level) == "VERIFIED":
        first_row_at = min((l.row.created_at for l in existing), default=None)
        prior = await _prior_verified_closures(db, pair, quarter, closure.id, first_row_at)
        n = len(prior)
        if n >= rules.PAIR_FULL_VERIFIED_CLOSURES:
            adjust = (0, rules.CAP_PAIR_CONCENTRATION)
        elif n == 1 and prior[0][1] != giver:                                   # reciprocal: B -> A after A -> B
            adjust = (rules.PAIR_RECIPROCAL_FACTOR_PERCENT, rules.CAP_PAIR_RECIPROCAL) if level >= phase0.L4_ADMIN else (0, rules.CAP_PAIR_RECIPROCAL_NEEDS_L4)
        if adjust is not None and pair_exception:
            adjust = None                                                         # an admin recorded a reasoned exception
        if adjust is not None and adjust[0] == 0:
            await fraud.raise_flag(db, "PAIR_CONCENTRATION", "WARN", pair_key=pair, reference_type="deal_closure", reference_id=closure.id,
                                   dedupe=f"pair-concentration:{closure.id}:{adjust[1]}", details={"rule": adjust[1], "prior_closures": n})

    factor = rules.EVENTS[event].get("factor_percent", 100)
    ref_pts, rec_pts = rules.split_pool(pool, factor)
    details = {"value_band": closure.value_band, "pool": pool * factor // 100, "split": f"{rules.REFERRER_SHARE_PERCENT}/{100 - rules.REFERRER_SHARE_PERCENT}",
               "pair_exception": bool(pair_exception)}
    earned: dict[str, list[GrowthPointLedger]] = {giver: [], receiver: []}          # both members' rows for this closure, in one query
    for r in (await db.execute(select(GrowthPointLedger).where(
            GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.reference_type == "deal_closure", GrowthPointLedger.reference_id == closure.id,
            GrowthPointLedger.member_id.in_((giver, receiver))).order_by(GrowthPointLedger.created_at, GrowthPointLedger.id))).scalars().all():
        earned[r.member_id].append(r)
    for member, other, role, points in ((giver, receiver, "referrer", ref_pts), (receiver, giver, "recipient", rec_pts)):
        rows = earned[member]
        suffix = ""
        if rows:
            latest = rows[-1]
            if latest.points_delta > 0:
                lot = next((l for l in existing if l.id == latest.id), None)
                if lot is None or lot.remaining > 0 or lot.state == "EXPIRED":
                    continue                                    # still alive: nothing to do (this is what makes a retry harmless)
                kids = set((await db.execute(select(GrowthPointLedger.entry_type).where(GrowthPointLedger.parent_id == latest.id))).scalars().all())
                if "EXPIRY" in kids:
                    continue                                    # expired points are never reinstated
                # reversed or voided earlier (a dispute) and the deal is verified again: a NEW lot, the old one stays in the ledger
            elif not reeval:
                continue                                        # an earlier decision of 0 stands unless an admin re-evaluates
            suffix = f":v{len(rows)}"
        res = await engine.award(db, AwardRequest(
            member_id=member, counterparty_id=other, role=role, event_type=rows[0].event_type if rows else event, reference_type="deal_closure",
            reference_id=closure.id, requested=points, level=level, event_at=at, prospect_key=pkey, pair_adjust=adjust, key_suffix=suffix,
            details=details, created_by=created_by, reason=(reason or rules.EVENTS[event]["note"])), now)
        summary["awarded"] += int(res.created)

    if summary["awarded"]:
        await fraud.after_closure(db, ref, closure, now)
    return summary


# ----------------------------------------------------------------------------------------------- profile
async def profile_complete(db: AsyncSession, user_id: str) -> bool:
    """What "profile completed" means is NOT defined in the specification, so this is deliberately the strict reading of what the
    product collects (an open business decision, recorded in the Phase 1 report): a personal profile, a business profile with its
    founder story and at least one online presence (website, LinkedIn or Instagram), and a profile photo. The networking headline
    and bio are generated for every member, so they prove nothing and are not used."""
    user = await db.get(User, user_id)
    if user is None or not user.photo_key or await db.get(PersonalProfile, user_id) is None:
        return False
    biz = await db.scalar(select(Business).where(Business.user_id == user_id).order_by(Business.created_at.asc()).limit(1))
    if biz is None or not (biz.founder_story or "").strip():
        return False
    return any((v or "").strip() for v in (biz.website, biz.linkedin, biz.instagram))


async def sync_profile(db: AsyncSession, user_id: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    if not await profile_complete(db, user_id):
        return {"awarded": 0}
    if await db.get(User, user_id) is None:
        return {"awarded": 0}
    await engine.lock_members(db, [user_id])
    if await cycles.resolve_cycle(db, user_id, now) is None:
        return {"awarded": 0}                                  # no term yet: nothing recorded; the sweep retries once they have one
    spec = rules.EVENTS["PROFILE_COMPLETED"]
    res = await engine.award(db, AwardRequest(
        member_id=user_id, role="member", event_type="PROFILE_COMPLETED", reference_type="member", reference_id=user_id, requested=spec["member"],
        level=spec["level"], event_at=now, reason=spec["note"]), now)
    return {"awarded": int(res.created)}
