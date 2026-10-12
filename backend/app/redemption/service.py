"""Renewal redemption: old-cycle points become a discount on the NEW renewal invoice. Backend-authoritative, transactional, idempotent.

Rules (docs/PHASE_1_SUBSCRIPTION_RENEWAL_RULE.md, GROWTH_POINTS_FINAL_SPEC.md):
  * 1 point = 10 paise. redeemable = MIN(eligible old-cycle points, 15 % of the NEW plan price in points). The old cycle decides how many
    points exist; the new plan decides how many can be used. Nothing is ever added to the new cycle's earning balance.
  * Only points earned on or after GROWTH_POINTS_REDEEMABLE_FROM are redeemable (empty = none). Oldest lots first. Expired points are never used.
  * Points alone leave at least 85 % payable (the 15 % cap); with any other discount the amount due never falls below 80 % of the list price.
    (No other discount exists in the product yet; the 80 % floor is nevertheless enforced here and by a database CHECK.)
  * A cycle's points are used on one renewal invoice. A refunded or cancelled renewal restores them (a NEW reverse record), only up to their
    original expiry; expired points are never resurrected. Nothing is edited or deleted; nothing becomes cash.
  * Every number is recomputed here from the database. The client only CONFIRMS the figures it was shown; if they changed, nothing happens.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit
from .. import demo
from ..config import REQUIRED_APPROVALS, parse_cutoff, settings
from ..models import (
    GrowthPointControl, GrowthPointCycle, GrowthPointLedger, GrowthPointRedemption, GrowthPointRedemptionEpoch, GrowthPointRedemptionLot, Invoice, Payment, Plan, Subscription, User, utcnow,
)
from ..rewards import cycles, engine as reward_engine, firewall, gates, renewal, rules
from ..subscriptions import build_purchase, plan_is_purchasable

KILL_KEY = "redemption_kill"
POINTS_ONLY_FLOOR_PERCENT = 85            # the 15 % cap, seen from the payer's side
COMBINED_FLOOR_PERCENT = 80               # no combination of discounts may take the amount due below this share of the list price
_GATE_A_TTL = 600
_gate_a_cache: dict = {"at": 0.0, "passed": False}


# ----------------------------------------------------------------------------------------------- switches and gates
async def killed(db: AsyncSession) -> bool:
    row = await db.scalar(select(GrowthPointControl).where(GrowthPointControl.key == KILL_KEY).order_by(GrowthPointControl.created_at.desc(), GrowthPointControl.id.desc()).limit(1))
    return bool(row and row.value == "on")


async def set_kill(db: AsyncSession, on: bool, actor_id: str, reason: str) -> None:
    """Stop (or resume) NEW redemptions at once, without a restart. Existing invoices, redemptions, points and history are untouched."""
    db.add(GrowthPointControl(key=KILL_KEY, value="on" if on else "off", actor_id=actor_id, reason=reason[:240]))
    await db.flush()


async def _gate_a_passed(db: AsyncSession) -> bool:
    """Gate A (real data review) from the objective gates, cached briefly because it is a heavy report."""
    if time.monotonic() - _gate_a_cache["at"] > _GATE_A_TTL:
        _gate_a_cache.update(at=time.monotonic(), passed=bool((await gates.evaluate(db))["gate_a"]["passed"]))
    return bool(_gate_a_cache["passed"])


def in_rollout(user: User) -> bool:
    email, stage = user.email.strip().lower(), settings.growth_points_rollout_stage
    owners = settings.programme_owners()
    cohort = {e.strip().lower() for e in settings.growth_points_rollout_emails.split(",") if e.strip()}
    if stage == "all":
        return True
    if stage == "cohort":
        return email in owners or email in cohort
    return email in owners                                              # "internal" and anything unrecognised: the safest stage


async def allowed(db: AsyncSession, user: User) -> tuple[bool, str]:
    """Is REAL redemption open for this member right now? Every gate, in order; the first closed one is the reason."""
    if not firewall.redemption_enabled():
        return False, "redemption_disabled"
    if REQUIRED_APPROVALS - settings.growth_points_approval_codes():
        return False, "approvals_missing"
    if not gates.REDEMPTION_ENGINE_BUILT:
        return False, "engine_not_released"
    if await killed(db):
        return False, "kill_switch"
    if not await _gate_a_passed(db):
        return False, "gate_a_not_passed"
    if not in_rollout(user):
        return False, "not_in_rollout"
    cutoff, why = await cutoff_status(db)
    if cutoff is None:
        return False, why                      # shadow-period points never carry over: with no recorded, matching cutoff nothing is redeemable
    return True, "open"


async def cutoff_status(db: AsyncSession) -> tuple[datetime | None, str]:
    """The effective eligibility cutoff and why. Shadow-period points (event_at BEFORE it) are never redeemable. It only exists when the environment
    value is readable AND equals the cutoff recorded once, immutably, in the database; every other situation fails safe to 'nothing is redeemable'."""
    raw = (settings.growth_points_redeemable_from or "").strip()
    if not raw:
        return None, "cutoff_not_configured"
    try:
        env_cutoff = parse_cutoff(raw)
    except ValueError:
        return None, "cutoff_unreadable"
    row = await db.scalar(select(GrowthPointRedemptionEpoch).limit(1))
    if row is None:
        return None, "cutoff_not_recorded"
    if rules.aware(row.cutoff_at) != env_cutoff:
        return None, "cutoff_mismatch"
    return env_cutoff, "ok"


def simulation_allowed(user: User) -> bool:
    """A rolled-back redemption SIMULATION for synthetic demo members, development and test environments only. It never runs for a real member,
    never in production, never without the explicit demo cutoff, and nothing it does is ever committed."""
    if settings.environment.strip().lower() == "production" or not demo.is_synthetic_email(user.email):
        return False
    try:
        parse_cutoff(settings.growth_points_demo_cutoff)
    except ValueError:
        return False
    return True


async def _lot_filter(db: AsyncSession, simulate: bool = False):
    if simulate:
        cutoff = parse_cutoff(settings.growth_points_demo_cutoff)
    else:
        cutoff, _ = await cutoff_status(db)
    return (lambda lot: False) if cutoff is None else (lambda lot: rules.aware(lot.row.event_at) >= cutoff)


# ----------------------------------------------------------------------------------------------- the calculation
async def _plan(db: AsyncSession, plan_code: str) -> Plan:
    plan = await db.scalar(select(Plan).where(Plan.code == plan_code))
    if plan is None or not plan_is_purchasable(plan):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That plan is not available.")
    return plan


async def _renewed_term(db: AsyncSession, user_id: str) -> Subscription | None:
    """The paid term being renewed: the member's latest ACTIVE (or just-expired) subscription that is not itself still waiting."""
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id, Subscription.status.in_(("ACTIVE", "EXPIRED")), Subscription.expires_at.is_not(None))
                           .order_by(Subscription.expires_at.desc()).limit(1))


async def _live_renewal(db: AsyncSession, old_id: str) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.renews_subscription_id == old_id, Subscription.status.in_(("PENDING", "ACTIVE"))))


async def quote(db: AsyncSession, user: User, plan_code: str, now: datetime | None = None, simulate: bool = False) -> dict:
    """What renewing into `plan_code` would cost this member, with the points that would be used. No writes."""
    now = now or utcnow()
    plan = await _plan(db, plan_code)
    calc = await renewal.compute(db, user.id, to_plan=plan.code, new_price_minor=plan.price_minor, new_term_months=plan.period_months, at=now, lot_filter=await _lot_filter(db, simulate))
    out = renewal.public(calc)
    old = await _renewed_term(db, user.id)
    cutoff, why = (parse_cutoff(settings.growth_points_demo_cutoff), "simulation") if simulate else await cutoff_status(db)
    # How many of the member's otherwise-usable old-cycle points are excluded because they were earned BEFORE the cutoff (shadow-period points).
    everything = await renewal.compute(db, user.id, to_plan=plan.code, new_price_minor=plan.price_minor, new_term_months=plan.period_months, at=now, lot_filter=None) if calc["old_cycle_id"] else calc
    excluded = max(0, everything["eligible_old_cycle_points"] - calc["eligible_old_cycle_points"])
    out.update(old_subscription_id=old.id if old else None, old_term_ends_at=old.expires_at if old else None, redeemable_from=cutoff, eligibility_basis=why,
               list_price_minor=plan.price_minor, other_discount_minor=0, points_excluded_before_cutoff=excluded)
    if cutoff is None and calc["old_cycle_id"]:
        out["reason"] = "No points can be used yet: Growth Points redemption has not started, and points earned before it starts can never be redeemed."
    elif excluded and not calc["eligible_old_cycle_points"]:
        out["reason"] = "Your points were earned before Growth Points redemption began, so they can not be redeemed. Points earned from now on can."
    return out


async def _renewal_window_open(old: Subscription, now: datetime) -> bool:
    ends = rules.aware(old.expires_at)
    return ends - timedelta(days=rules.RENEWAL_WINDOW_BEFORE_DAYS) <= now <= ends + timedelta(days=rules.GRACE_DAYS)


def _fail(code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail=jsonable_encoder({"code": code, "message": message, **extra}))


async def confirm(db: AsyncSession, user: User, plan_code: str, *, redeem: bool, expected_points: int | None, expected_discount_minor: int | None, now: datetime | None = None,
                  simulate: bool = False) -> dict:
    """Create the renewal subscription and invoice (with the points discount when redeeming), in ONE transaction. The caller commits.
    simulate=True (synthetic demo members in development only) runs this exact code with the demo cutoff; the caller MUST roll back."""
    now = now or utcnow()
    plan = await _plan(db, plan_code)
    old = await _renewed_term(db, user.id)
    if old is None:
        raise _fail("nothing_to_renew", "You have no subscription to renew. Choose a plan from the plans page.")
    if not await _renewal_window_open(old, now):
        raise _fail("outside_renewal_window", "Renewal opens 30 days before your term ends and closes 30 days after it.")
    if simulate and not simulation_allowed(user):
        raise _fail("simulation_unavailable", "The simulation is not available.")
    if redeem and not simulate:
        ok, why = await allowed(db, user)
        if not ok:
            raise _fail("redemption_unavailable", "Using Growth Points is not available.", reason=why)
    balances = await reward_engine.lock_members(db, [user.id])               # one lock per member: two requests can not interleave
    live = await _live_renewal(db, old.id)
    if live is not None:                                                     # a replay / double click / refresh: the same answer, nothing new
        if (await db.get(Plan, live.plan_id)).code != plan.code:
            raise _fail("renewal_in_progress", "You already have a renewal in progress for a different plan.")
        return await _result(db, live, replay=True)
    calc = await renewal.compute(db, user.id, to_plan=plan.code, new_price_minor=plan.price_minor, new_term_months=plan.period_months, at=now, lot_filter=await _lot_filter(db, simulate))
    points = calc["points_to_be_redeemed"] if redeem else 0
    discount = rules.points_to_paise(points)
    if redeem and (expected_points != points or expected_discount_minor != discount):
        raise _fail("calculation_changed", "The calculation changed since you saw it. Please review it again.", current=renewal.public(calc))
    if discount * 100 > plan.price_minor * rules.REDEMPTION_CAP_PERMILLE // 10 or (plan.price_minor - discount) * 100 < plan.price_minor * COMBINED_FLOOR_PERCENT \
            or (plan.price_minor - discount) * 100 < plan.price_minor * POINTS_ONLY_FLOOR_PERCENT:
        raise RuntimeError("financial invariant violated: the discount exceeds the cap or the floor")      # never reached: compute() already enforces it

    sub, invoice, payment = build_purchase(user.id, plan)
    sub.renews_subscription_id = old.id
    db.add(sub)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _fail("renewal_in_progress", "A renewal is already in progress.")
    invoice.subscription_id = sub.id
    invoice.discount_minor = invoice.points_discount_minor = discount
    invoice.points_redeemed = points
    invoice.amount_due_minor = plan.price_minor - discount
    invoice.discount_reason = "Growth Points used at renewal" if points else None
    db.add(invoice)
    await db.flush()
    payment.invoice_id = invoice.id
    payment.amount_minor = invoice.amount_due_minor
    db.add(payment)
    audit.record(db, actor=user, action="subscription.created", resource_type="subscription", resource_id=sub.id,
                 after={"plan": plan.code, "price_minor": plan.price_minor, "period_months": plan.period_months, "status": "PENDING", "renews": old.id})
    audit.record(db, actor=user, action="invoice.issued", resource_type="invoice", resource_id=invoice.id,
                 after={"number": invoice.number, "amount_due_minor": invoice.amount_due_minor, "discount_minor": discount, "points_redeemed": points, "status": "ISSUED"})
    if points:
        await reward_engine.ensure_rule_version(db)
        redemption = GrowthPointRedemption(
            member_id=user.id, entry_type="REDEEM", old_cycle_id=calc["old_cycle_id"], subscription_id=sub.id, invoice_id=invoice.id, points=points,
            point_value_paise=rules.PAISE_PER_POINT, discount_paise=discount, list_price_minor=plan.price_minor, amount_due_minor=invoice.amount_due_minor,
            cap_points=calc["new_plan_redemption_ceiling_points"], eligible_points=calc["eligible_old_cycle_points"], rule_version=rules.RULE_VERSION, created_by=user.id,
            reason="Member confirmed the calculation", idempotency_key=f"redeem:{invoice.id}",
            details=json.dumps({"from_plan": calc["current_plan"], "to_plan": plan.code, "old_subscription_id": old.id, "remaining_old_cycle_points": calc["remaining_old_cycle_points"],
                                "old_points_expire_at": calc["old_points_expire_at"], "other_discount_minor": 0}, default=str),
        )
        db.add(redemption)
        await db.flush()
        for a in calc["allocations"]:
            db.add(GrowthPointRedemptionLot(redemption_id=redemption.id, member_id=user.id, lot_id=a["lot_id"], delta=-a["points"]))
        balances[user.id].total_points -= points
        if balances[user.id].total_points < 0:
            raise RuntimeError("financial invariant violated: negative point balance")
        await db.flush()
        audit.record(db, actor=user, action="growth_points.redeemed", resource_type="invoice", resource_id=invoice.id,
                     after={"redemption_id": redemption.id, "points": points, "discount_paise": discount, "amount_due_minor": invoice.amount_due_minor, "old_cycle_id": calc["old_cycle_id"],
                            "lots": [{"lot": a["lot_id"], "points": a["points"]} for a in calc["allocations"]]})
    return await _result(db, sub, replay=False)


async def _result(db: AsyncSession, sub: Subscription, replay: bool) -> dict:
    invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.created_at.desc()).limit(1))
    return {"subscription_id": sub.id, "invoice_id": invoice.id, "invoice_number": invoice.number, "plan_price_minor": invoice.list_price_minor,
            "growth_points_discount_minor": invoice.points_discount_minor, "points_redeemed": invoice.points_redeemed, "amount_due_minor": invoice.amount_due_minor,
            "status": sub.status, "replay": replay}


# ----------------------------------------------------------------------------------------------- reversal
async def reverse(db: AsyncSession, redemption: GrowthPointRedemption, *, created_by: str, reason: str, now: datetime | None = None) -> GrowthPointRedemption | None:
    """A refunded or cancelled renewal gives its points back: a NEW reverse record, only up to each lot's original expiry. Idempotent."""
    now = now or utcnow()
    if redemption.entry_type != "REDEEM":
        return None
    key = f"reverse:{redemption.id}"
    if await db.scalar(select(GrowthPointRedemption.id).where(GrowthPointRedemption.idempotency_key == key)):
        return None
    balances = await reward_engine.lock_members(db, [redemption.member_id])
    lines = (await db.execute(select(GrowthPointRedemptionLot).where(GrowthPointRedemptionLot.redemption_id == redemption.id))).scalars().all()
    restorable: list[tuple[str, int]] = []
    for line in lines:
        lot = await db.get(GrowthPointLedger, line.lot_id)
        alive = lot.expires_at is None or rules.aware(lot.expires_at) > now
        if alive and -line.delta > 0:
            restorable.append((line.lot_id, -line.delta))
    restored = sum(p for _, p in restorable)
    rev = GrowthPointRedemption(
        member_id=redemption.member_id, entry_type="REVERSE", reverses_id=redemption.id, old_cycle_id=redemption.old_cycle_id, subscription_id=redemption.subscription_id,
        invoice_id=redemption.invoice_id, points=redemption.points, point_value_paise=redemption.point_value_paise, discount_paise=redemption.discount_paise,
        list_price_minor=redemption.list_price_minor, amount_due_minor=redemption.amount_due_minor, cap_points=redemption.cap_points, eligible_points=redemption.eligible_points,
        restored_points=restored, rule_version=rules.RULE_VERSION, created_by=created_by, reason=reason, idempotency_key=key,
        details=json.dumps({"expired_not_restored": redemption.points - restored}),
    )
    db.add(rev)
    await db.flush()
    for lot_id, pts in restorable:
        db.add(GrowthPointRedemptionLot(redemption_id=rev.id, member_id=redemption.member_id, lot_id=lot_id, delta=pts))
    balances[redemption.member_id].total_points += restored
    await db.flush()
    audit.record(db, actor=None, action="growth_points.redemption_reversed", resource_type="invoice", resource_id=redemption.invoice_id,
                 after={"reversal_id": rev.id, "restored_points": restored, "not_restored_because_expired": redemption.points - restored}, reason=reason)
    return rev


async def reverse_dead_renewals(db: AsyncSession, now: datetime | None = None) -> int:
    """Sweep: every redemption whose renewal was refunded or cancelled and has no reversal yet gets one."""
    done = (await db.execute(select(GrowthPointRedemption.reverses_id).where(GrowthPointRedemption.entry_type == "REVERSE"))).scalars().all()
    q = (select(GrowthPointRedemption).join(Subscription, Subscription.id == GrowthPointRedemption.subscription_id)
         .where(GrowthPointRedemption.entry_type == "REDEEM", Subscription.status == "CANCELLED"))
    n = 0
    for r in (await db.execute(q)).scalars().all():
        if r.id not in set(done) and await reverse(db, r, created_by="system", reason="The renewal was refunded or cancelled", now=now):
            n += 1
    return n
