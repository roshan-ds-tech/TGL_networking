"""Reconciliation: does the shadow economy add up, and did it obey its own rules?

Two kinds of check, both read-only (except the optional rebuild of the balance CACHE, which is derived data):

  * DRIFT: for every member, SUM(ledger points) must equal the cached shadow balance, and no lot may have negative remaining points
    or a child entry pointing at a missing / different-member parent.
  * INVARIANTS: no cycle, category, day, month or pair budget may exceed its ceiling. A violation means a bug or a bypass.

Any finding is returned (and shown to admins); nothing is silently corrected except the cache.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..models import GrowthPointBalance, GrowthPointCycle, GrowthPointLedger, GrowthPointRedemption, GrowthPointRedemptionLot, GrowthPointRenewal, Invoice, Subscription, utcnow
from . import ledger, rules

NET = ("EARN", "VOID", "REVERSAL")
REVERSAL_SWEEP_GRACE = timedelta(hours=1)        # how long a refunded or cancelled renewal may wait for the sweep to give its points back before it is a finding


async def reconcile(db: AsyncSession, repair_cache: bool = False) -> dict:
    L = GrowthPointLedger
    drift: list[dict] = []
    violations: list[dict] = []

    sums = {m: int(t or 0) for m, t in (await db.execute(select(L.member_id, func.sum(L.points_delta)).group_by(L.member_id))).all()}
    for m, t in (await db.execute(select(GrowthPointRedemptionLot.member_id, func.sum(GrowthPointRedemptionLot.delta)).group_by(GrowthPointRedemptionLot.member_id))).all():
        sums[m] = sums.get(m, 0) + int(t or 0)                      # real redemptions (negative) and restorations (positive)
    balances = {b.member_id: b for b in (await db.execute(select(GrowthPointBalance))).scalars().all()}
    for member in sorted(set(sums) | set(balances)):
        have = balances[member].total_points if member in balances else None
        want = sums.get(member, 0)
        if have != want:
            drift.append({"member_id": member, "ledger_sum": want, "cached_balance": have})
            if repair_cache and member in balances:
                balances[member].total_points = want
    for lot in await ledger.lots(db):
        if lot.remaining < 0:
            drift.append({"lot_id": lot.id, "member_id": lot.row.member_id, "problem": "a lot has negative remaining points", "remaining": lot.remaining})
    parent = aliased(L)
    orphans = (await db.execute(
        select(L.id, L.member_id, parent.member_id).outerjoin(parent, parent.id == L.parent_id).where(L.parent_id.is_not(None), (parent.id.is_(None)) | (parent.member_id != L.member_id))
    )).all()
    for rid, member, pmember in orphans:
        drift.append({"entry_id": rid, "member_id": member, "problem": "a child entry has no parent, or a parent that belongs to another member", "parent_member": pmember})

    # invariants: the ceilings
    cycles = {c.id: c for c in (await db.execute(select(GrowthPointCycle))).scalars().all()}
    for cycle_id, total in (await db.execute(select(L.cycle_id, func.sum(L.points_delta)).where(L.entry_type.in_(NET), L.cycle_id.is_not(None)).group_by(L.cycle_id))).all():
        if cycle_id in cycles and int(total) > cycles[cycle_id].ceiling_points:
            violations.append({"rule": "cycle ceiling", "cycle_id": cycle_id, "points": int(total), "ceiling": cycles[cycle_id].ceiling_points})
    for cycle_id, category, total in (await db.execute(select(L.cycle_id, L.category, func.sum(L.points_delta)).where(L.entry_type.in_(NET), L.cycle_id.is_not(None)).group_by(L.cycle_id, L.category))).all():
        c = cycles.get(cycle_id)
        limit = {"PROCESS": c.process_ceiling, "CLOSURE": c.closure_ceiling, "OTHER": c.other_ceiling}[category] if c else None
        if c and int(total) > limit:
            violations.append({"rule": "category sub-ceiling", "cycle_id": cycle_id, "category": category, "points": int(total), "ceiling": limit})
    for pair, quarter, total in (await db.execute(select(L.pair_key, L.quarter_key, func.sum(L.points_delta)).where(L.entry_type.in_(NET), L.assurance == "LOW", L.pair_key.is_not(None)).group_by(L.pair_key, L.quarter_key))).all():
        if int(total) > rules.PAIR_LOW_ASSURANCE_BUDGET:
            violations.append({"rule": "pair low-assurance budget", "pair": pair, "quarter": quarter, "points": int(total), "ceiling": rules.PAIR_LOW_ASSURANCE_BUDGET})
    for member, day, total in (await db.execute(select(L.member_id, L.day_key, func.sum(L.points_delta)).where(L.entry_type.in_(NET), L.assurance == "LOW").group_by(L.member_id, L.day_key))).all():
        if int(total) > rules.DAILY_CEILING_LOW_ASSURANCE:
            violations.append({"rule": "daily ceiling", "member_id": member, "day": day, "points": int(total), "ceiling": rules.DAILY_CEILING_LOW_ASSURANCE})
    for member, month, total in (await db.execute(select(L.member_id, L.month_key, func.sum(L.points_delta)).where(L.entry_type.in_(NET)).group_by(L.member_id, L.month_key))).all():
        if int(total) > rules.MONTHLY_CEILING:
            violations.append({"rule": "monthly ceiling", "member_id": member, "month": month, "points": int(total), "ceiling": rules.MONTHLY_CEILING})
    # invariants: the hypothetical renewal redemptions
    used = {rid: int(-t) for rid, t in (await db.execute(
        select(L.reference_id, func.sum(L.points_delta)).where(L.entry_type == "SIM_REDEEM").group_by(L.reference_id))).all()}
    seen = set()
    for r in (await db.execute(select(GrowthPointRenewal))).scalars().all():
        seen.add(r.id)
        if used.get(r.id, 0) != r.redeemed_points:
            violations.append({"rule": "renewal record vs ledger", "renewal_id": r.id, "recorded": r.redeemed_points, "ledger": used.get(r.id, 0)})
        if r.redeemed_points > min(r.eligible_points, rules.redemption_cap_points(r.new_price_minor)):
            violations.append({"rule": "renewal redemption ceiling (15 % of the NEW plan)", "renewal_id": r.id, "redeemed": r.redeemed_points})
        if r.hypothetical_discount_paise != rules.points_to_paise(r.redeemed_points) or r.hypothetical_payable_paise != r.new_price_minor - r.hypothetical_discount_paise:
            violations.append({"rule": "renewal amounts", "renewal_id": r.id})
    for rid in set(used) - seen:
        violations.append({"rule": "a SIM_REDEEM row has no renewal record", "renewal_id": rid})
    # invariants: REAL redemptions = invoice discounts = lot lines (nothing here is ever repaired automatically)
    R, LOT = GrowthPointRedemption, GrowthPointRedemptionLot
    line_sums = {rid: int(t or 0) for rid, t in (await db.execute(select(LOT.redemption_id, func.sum(LOT.delta)).group_by(LOT.redemption_id))).all()}
    invoices = {i.id: i for i in (await db.execute(select(Invoice).where((Invoice.points_discount_minor != 0) | Invoice.id.in_(select(R.invoice_id))))).scalars().all()}
    redeemed_invoices = set()
    cancelled_unreversed: set[str] = set()
    reversal_of: set[str] = set()
    now = utcnow()
    subs = {s.id: s for s in (await db.execute(select(Subscription).where(Subscription.id.in_(select(R.subscription_id))))).scalars().all()}
    for r in (await db.execute(select(R))).scalars().all():
        if r.entry_type == "REDEEM":
            redeemed_invoices.add(r.invoice_id)
            if line_sums.get(r.id, 0) != -r.points:
                violations.append({"rule": "redemption vs its lot lines", "redemption_id": r.id, "points": r.points, "lines": line_sums.get(r.id, 0)})
            inv = invoices.get(r.invoice_id)
            if inv is None or (inv.points_redeemed, inv.points_discount_minor, inv.discount_minor, inv.amount_due_minor) != (r.points, r.discount_paise, r.discount_paise, r.amount_due_minor):
                violations.append({"rule": "redemption vs invoice discount", "redemption_id": r.id, "invoice_id": r.invoice_id})
            sub = subs.get(r.subscription_id)
            if sub is not None and sub.status == "CANCELLED" and now - rules.aware(r.created_at) > REVERSAL_SWEEP_GRACE:
                cancelled_unreversed.add(r.id)                             # cleared below if a REVERSE exists
        else:
            if line_sums.get(r.id, 0) != r.restored_points:
                violations.append({"rule": "reversal vs its lot lines", "redemption_id": r.id, "restored": r.restored_points, "lines": line_sums.get(r.id, 0)})
            reversal_of.add(r.reverses_id)
    for rid in sorted(cancelled_unreversed - reversal_of):
        violations.append({"rule": "a refunded or cancelled renewal still holds redeemed points (no reversal)", "redemption_id": rid})
    for inv_id, inv in invoices.items():
        if inv.points_discount_minor and inv_id not in redeemed_invoices:
            violations.append({"rule": "an invoice carries a points discount with no redemption record", "invoice_id": inv_id})
    for lot_line, lot in (await db.execute(select(LOT, GrowthPointLedger).join(GrowthPointLedger, GrowthPointLedger.id == LOT.lot_id).where(LOT.delta < 0))).all():
        red = await db.get(R, lot_line.redemption_id)
        if lot.expires_at is not None and rules.aware(lot.expires_at) <= rules.aware(red.created_at):
            violations.append({"rule": "an expired lot was redeemed", "redemption_id": red.id, "lot_id": lot.id})
        if lot.cycle_id != red.old_cycle_id or lot.member_id != red.member_id:
            violations.append({"rule": "a redemption used another cycle's or another member's lot", "redemption_id": red.id, "lot_id": lot.id})
    if repair_cache:
        await db.flush()
    return {"members_checked": len(set(sums) | set(balances)), "drift": drift, "violations": violations, "ok": not drift and not violations,
            "cache_repaired": bool(repair_cache and drift)}
