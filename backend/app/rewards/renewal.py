"""Shadow RENEWAL redemption: what a member's old-cycle points WOULD be worth against the renewal invoice. Hypothetical only.

The rule (docs/PHASE_1_SUBSCRIPTION_RENEWAL_RULE.md):

  * A plan changes ONLY at renewal. There is no mid-cycle upgrade or downgrade. Renewal creates the next cycle.
  * Points stay attached to the cycle they were earned in. They are never moved into the new cycle: not into its earning balance,
    not into its ceiling. The new cycle starts with ZERO transferred earning points and its own ceilings.
  * Eligible points of the OLD cycle may be used against the NEW invoice:  redeemable = MIN(eligible old-cycle points, 15 % of the
    NEW plan's price in points). The old cycle decides how many points exist; the new plan decides how many may be used.
  * Eligible = still alive (unexpired, available, not voided or reversed) and the invoice was raised inside the renewal window
    (30 days before the old term ends to 30 days after). They are consumed oldest-first (FIFO).
  * Anything else (a replacement outside the window, for example after an admin refund) is NOT a renewal and redeems nothing, so an
    administrative replacement can never become a way to cash points. Points of a refunded cycle are never eligible.

Nothing here reads for writing, or writes, an invoice, a payment, a subscription or a plan; the firewall guards the whole run.
Each use is a new SIM_REDEEM ledger row per lot consumed (the earning rows are never touched) plus one growth_point_renewals record.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GrowthPointCycle, GrowthPointLedger, GrowthPointRenewal, Invoice, Plan, Subscription, utcnow
from . import cycles, engine, fraud, ledger, rules

LABEL = "HYPOTHETICAL / SHADOW ONLY: nothing is applied to any invoice or payment."


async def _previous_term(db: AsyncSession, member_id: str, exclude_subscription_id: str | None, before: datetime | None) -> dict | None:
    """The member's most recent earlier term (a paid subscription, or the Season 1 complimentary term): the one being renewed."""
    best = None
    for start, kind, row, ends in await cycles._candidates(db, member_id):
        if row.id == exclude_subscription_id:
            continue
        if before is not None and start >= before:
            continue
        if best is None or ends > best["ends"]:
            best = {"kind": kind, "row": row, "start": start, "ends": ends}
    return best


async def _plan_code_of(db: AsyncSession, term: dict) -> str:
    if term["kind"] == "MEMBERSHIP":
        return "complimentary"
    plan = await db.get(Plan, term["row"].plan_id)
    return plan.code if plan else "unknown"


async def compute(db: AsyncSession, member_id: str, *, to_plan: str, new_price_minor: int, new_term_months: int, at: datetime,
                  exclude_subscription_id: str | None = None, new_starts_at: datetime | None = None, from_plan: str | None = None, lot_filter=None) -> dict:
    """The renewal calculation, with no writes. `at` is the moment the renewal invoice was raised."""
    at = rules.aware(at)
    cap_points = rules.redemption_cap_points(new_price_minor)
    out = {
        "label": LABEL, "shadow": True, "invoice_change_minor": 0, "decided_at": at,
        "current_plan": from_plan, "new_plan": to_plan, "new_plan_price_minor": new_price_minor, "new_plan_term_months": new_term_months,
        "point_value_paise": rules.PAISE_PER_POINT, "new_plan_redemption_ceiling_points": cap_points,
        "new_plan_redemption_ceiling_paise": rules.points_to_paise(cap_points),
        "eligible_old_cycle_points": 0, "points_to_be_redeemed": 0, "remaining_old_cycle_points": 0,
        "hypothetical_discount_paise": 0, "hypothetical_amount_payable_paise": new_price_minor,
        "outcome": "NOT_A_RENEWAL", "reason": "", "old_cycle_id": None, "old_points_expire_at": None, "renewal_window": None, "allocations": [],
        "new_cycle_transferred_earning_points": 0,         # always: old points are never moved into the new cycle
    }
    prev = await _previous_term(db, member_id, exclude_subscription_id, new_starts_at)
    if prev is None:
        out["reason"] = "This is the member's first term: there is nothing to renew."
        return out
    out["current_plan"] = await _plan_code_of(db, prev)
    opens, closes = prev["ends"] - timedelta(days=rules.RENEWAL_WINDOW_BEFORE_DAYS), prev["ends"] + timedelta(days=rules.GRACE_DAYS)
    out["renewal_window"] = {"opens": opens, "closes": closes, "old_term_ends": prev["ends"]}
    out["old_points_expire_at"] = closes
    if prev["kind"] == "SUBSCRIPTION" and prev["row"].status == "CANCELLED":
        out.update(outcome="REFUNDED_CYCLE", reason="The previous term was cancelled or refunded, so its points are not eligible for renewal redemption.")
        return out
    if not (opens <= at <= closes):
        out["reason"] = ("Raised before the renewal window opened (an early replacement is not a renewal)." if at < opens
                         else "Raised after the renewal window closed: the old cycle's points have expired.")
        return out
    old = await db.scalar(select(GrowthPointCycle).where(GrowthPointCycle.source_type == prev["kind"], GrowthPointCycle.source_id == prev["row"].id))
    if old is None:
        out.update(outcome="NOTHING_ELIGIBLE", reason="The member earned no points in the previous cycle.")
        return out
    out["old_cycle_id"] = old.id
    out["old_points_expire_at"] = old.grace_ends_at
    lots = [l for l in await ledger.lots(db, member_id=member_id, now=at) if l.row.cycle_id == old.id and l.state == "AVAILABLE" and l.remaining > 0 and (lot_filter is None or lot_filter(l))]
    eligible = sum(l.remaining for l in lots)
    redeem = min(eligible, cap_points)
    out.update(eligible_old_cycle_points=eligible, points_to_be_redeemed=redeem, remaining_old_cycle_points=eligible - redeem,
               hypothetical_discount_paise=rules.points_to_paise(redeem), hypothetical_amount_payable_paise=new_price_minor - rules.points_to_paise(redeem))
    need = redeem
    for lot in lots:                                        # lots() is ordered earliest expiry first, then oldest first: FIFO
        if need <= 0:
            break
        take = min(lot.remaining, need)
        out["allocations"].append({"lot": lot, "lot_id": lot.id, "event_type": lot.row.event_type, "points": take, "lot_remaining_after": lot.remaining - take})
        need -= take
    if redeem:
        out.update(outcome="REDEEMED", reason="Eligible old-cycle points used against the renewal invoice, oldest first, up to 15 % of the new plan's price.")
    else:
        out.update(outcome="NOTHING_ELIGIBLE", reason="No eligible (available, unexpired) old-cycle points at the time of renewal.")
    return out


def public(calc: dict) -> dict:
    """The calculation without the in-memory lot objects (safe to return as JSON)."""
    out = {k: v for k, v in calc.items() if k != "allocations"}
    out["lots_consumed"] = [{k: v for k, v in a.items() if k != "lot"} for a in calc["allocations"]]
    return out


async def preview(db: AsyncSession, member_id: str, plan_code: str, at: datetime | None = None) -> dict | None:
    """What renewing into `plan_code` would look like for this member right now (or at `at`). No writes."""
    plan = await db.scalar(select(Plan).where(Plan.code == plan_code))
    if plan is None:
        return None
    calc = await compute(db, member_id, to_plan=plan.code, new_price_minor=plan.price_minor, new_term_months=plan.period_months, at=at or utcnow())
    return public(calc)


async def record(db: AsyncSession, subscription_id: str, now: datetime | None = None) -> tuple[GrowthPointRenewal | None, bool]:
    """Record the hypothetical redemption for a renewal subscription once. Idempotent: any number of calls, retries or races leave one
    record and one set of SIM_REDEEM rows. Returns (record, created); (None, False) if this is not a renewal context (first term)."""
    sub = await db.get(Subscription, subscription_id)
    if sub is None or sub.status != "ACTIVE":
        return None, False
    balances = await engine.lock_members(db, [sub.user_id])
    existing = await db.scalar(select(GrowthPointRenewal).where(GrowthPointRenewal.new_subscription_id == sub.id))
    if existing is not None:
        return existing, False
    invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.created_at.desc()).limit(1))
    plan = await db.get(Plan, sub.plan_id)
    if invoice is None or plan is None:
        return None, False
    at = rules.aware(invoice.created_at)
    calc = await compute(db, sub.user_id, to_plan=plan.code, new_price_minor=invoice.list_price_minor, new_term_months=invoice.period_months, at=at,
                         exclude_subscription_id=sub.id, new_starts_at=rules.aware(sub.starts_at) if sub.starts_at else None)
    if calc["renewal_window"] is None:
        return None, False                                                        # the member's first term
    await engine.ensure_rule_version(db)
    header = GrowthPointRenewal(
        member_id=sub.user_id, old_cycle_id=calc["old_cycle_id"], new_subscription_id=sub.id, new_invoice_id=invoice.id, from_plan=calc["current_plan"], to_plan=plan.code,
        new_term_months=invoice.period_months, new_price_minor=invoice.list_price_minor, outcome=calc["outcome"], eligible_points=calc["eligible_old_cycle_points"],
        redemption_cap_points=calc["new_plan_redemption_ceiling_points"], redeemed_points=calc["points_to_be_redeemed"], remaining_points=calc["remaining_old_cycle_points"],
        hypothetical_discount_paise=calc["hypothetical_discount_paise"], hypothetical_payable_paise=calc["hypothetical_amount_payable_paise"], decided_at=at,
        old_expires_at=calc["old_points_expire_at"], reason=calc["reason"], rule_version=rules.RULE_VERSION, idempotency_key=f"renewal:{sub.id}", shadow=True,
    )
    db.add(header)
    await db.flush()
    bal = balances[sub.user_id]
    for a in calc["allocations"]:
        lot = a["lot"]
        parent = lot.row
        bal.total_points -= a["points"]
        db.add(GrowthPointLedger(
            event_at=at, member_id=sub.user_id, counterparty_id=parent.counterparty_id, pair_key=parent.pair_key, entry_type="SIM_REDEEM", event_type=parent.event_type,
            category=parent.category, role=parent.role, reference_type="renewal", reference_id=header.id, parent_id=parent.id, cycle_id=parent.cycle_id,
            prospect_key=parent.prospect_key, points_delta=-a["points"], requested_points=0, capped_points=0, status="SIMULATED", assurance=parent.assurance,
            verification_level=parent.verification_level, available_at=parent.available_at, expires_at=parent.expires_at, remaining=0, balance_after=bal.total_points,
            reason="Hypothetical use of old-cycle points against the renewal invoice (shadow only)",
            details=json.dumps({"renewal_id": header.id, "from_plan": calc["current_plan"], "to_plan": plan.code, "lot_remaining_after": a["lot_remaining_after"]}),
            created_by="system", rule_version=rules.RULE_VERSION, idempotency_key=f"renewal:{sub.id}:{parent.id}", shadow=True,
            day_key=rules.day_key(at), month_key=rules.month_key(at), quarter_key=rules.quarter_key(at),
        ))
    if calc["allocations"]:
        await db.flush()
    if calc["outcome"] == "NOTHING_ELIGIBLE" and calc["reason"].startswith("No eligible") and calc["old_cycle_id"]:
        # points may have been swept to EXPIRY before this renewal was recorded: say so for an admin instead of hiding it
        expired = await db.scalar(select(GrowthPointLedger.id).where(GrowthPointLedger.cycle_id == calc["old_cycle_id"], GrowthPointLedger.entry_type == "EXPIRY",
                                                                    GrowthPointLedger.created_at > at).limit(1))
        if expired:
            await fraud.raise_flag(db, "RENEWAL_AFTER_EXPIRY", "WARN", member_id=sub.user_id, reference_type="renewal", reference_id=header.id, dedupe=header.id,
                                   details={"why": "old-cycle points were swept to expiry before this renewal was recorded"})
    return header, True
