"""Admin analytics for the shadow period. Read-only.

Three things are kept strictly apart in every view, because mixing them is how a shadow experiment gets mistaken for money:

    shadow_earning            points recorded in the shadow ledger
    hypothetical_redemption   what members WOULD be able to redeem if redemption existed (never applied)
    real_financial_cost       what Growth Points ACTUALLY cost TGL: measured from the invoices, and ALWAYS 0 in Phase 1

No prospect phone or email, no evidence, and no exact deal value leaves this module except in an aggregate.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..models import (
    BusinessReferral, DealClosure, GrowthPointCycle, GrowthPointRedemptionLot, GrowthPointFlag, GrowthPointLedger, GrowthPointRenewal, Invoice, PersonalProfile, Plan, Subscription, TGLMembership, User, utcnow,
)
from . import ledger, model, rules

MIN_MEMBER_MONTHS = 1.0            # a per-member-month rate over less than a member-month of data is noise, so it is shown as "not enough data"
L = GrowthPointLedger
NET = ("EARN", "VOID", "REVERSAL")
TIERS = (("Low", 0, 5), ("Average", 5, 25), ("High", 25, 75), ("Top", 75, 1_000_000))     # share of the cycle ceiling, in percent
DISCLAIMER = "SHADOW MODE: every figure below is a simulation. Growth Points have no monetary effect; the real financial cost is measured from the invoices and is 0."


def _i(x) -> int:
    return int(x or 0)


async def real_financial_cost(db: AsyncSession) -> dict:
    """Measured, not asserted: the sum of every invoice discount, and the number of invoices charged less than their list price."""
    discount = _i(await db.scalar(select(func.coalesce(func.sum(Invoice.discount_minor), 0))))
    reduced = _i(await db.scalar(select(func.count(Invoice.id)).where(or_(Invoice.amount_due_minor != Invoice.list_price_minor, Invoice.discount_minor != 0))))
    from ..models import GrowthPointRedemption
    recorded = _i(await db.scalar(select(func.coalesce(func.sum(GrowthPointRedemption.discount_paise), 0)).where(GrowthPointRedemption.entry_type == "REDEEM")))
    recorded_n = _i(await db.scalar(select(func.count(GrowthPointRedemption.id)).where(GrowthPointRedemption.entry_type == "REDEEM")))
    return {"inr_minor": discount, "invoices_reduced": reduced, "recorded_redemption_discount_minor": recorded,
            "note": "Invoice discounts actually given. In shadow mode this must read 0; once real redemption is open every paisa must be explained by a redemption record.",
            "ok": discount == recorded and reduced == recorded_n}


async def _lot_rows(db: AsyncSession, now: datetime, member_ids=None) -> list[tuple]:
    """(member_id, cycle_id, event_type, remaining, available_at, expires_at) for every lot with points left."""
    child = aliased(L)
    R = GrowthPointRedemptionLot
    real = select(R.lot_id.label("lot_id"), func.sum(R.delta).label("delta")).group_by(R.lot_id).subquery()
    q = (select(L.member_id, L.cycle_id, L.event_type, L.points_delta + func.coalesce(func.sum(child.points_delta), 0) + func.coalesce(func.max(real.c.delta), 0), L.available_at, L.expires_at)
         .outerjoin(child, child.parent_id == L.id).outerjoin(real, real.c.lot_id == L.id).where(L.entry_type == "EARN", L.points_delta > 0)
         .group_by(L.id, L.member_id, L.cycle_id, L.event_type, L.points_delta, L.available_at, L.expires_at))
    if member_ids is not None:
        q = q.where(L.member_id.in_(list(member_ids)))
    return [r for r in (await db.execute(q)).all() if _i(r[3]) > 0]


def _state(available_at, expires_at, now: datetime) -> str:
    if expires_at is not None and rules.aware(expires_at) <= now:
        return "EXPIRED"
    if available_at is not None and rules.aware(available_at) > now:
        return "PENDING"
    return "AVAILABLE"


async def _current_cycles(db: AsyncSession, now: datetime) -> dict[str, GrowthPointCycle]:
    """Each member's latest cycle that is still in its term or its renewal grace (where points can still be used)."""
    cycles = (await db.execute(select(GrowthPointCycle).where(GrowthPointCycle.starts_at <= now, GrowthPointCycle.grace_ends_at > now)
                               .order_by(GrowthPointCycle.starts_at))).scalars().all()
    return {c.member_id: c for c in cycles}


async def hypothetical(db: AsyncSession, now: datetime) -> dict:
    lots = await _lot_rows(db, now)
    cycles = await _current_cycles(db, now)
    per: dict[str, dict] = defaultdict(lambda: {"pending": 0, "available": 0, "lapsed": 0})
    for member, _cid, _ev, remaining, avail, exp in lots:
        per[member][{"PENDING": "pending", "AVAILABLE": "available", "EXPIRED": "lapsed"}[_state(avail, exp, now)]] += _i(remaining)
    discount = potential = 0
    redeemers = 0
    for member, p in per.items():
        c = cycles.get(member)
        if c is None:
            continue
        cap = rules.redemption_cap_paise(c.price_minor)
        d = min(rules.points_to_paise(p["available"]), cap)
        discount += d
        potential += min(rules.points_to_paise(p["available"] + p["pending"]), cap)
        redeemers += int(d > 0)
    pending = sum(p["pending"] for p in per.values())
    available = sum(p["available"] for p in per.values())
    return {
        "outstanding_points": pending + available, "pending_points": pending, "available_points": available, "lapsed_unswept_points": sum(p["lapsed"] for p in per.values()),
        "outstanding_value_paise": rules.points_to_paise(pending + available),
        "hypothetical_redemption_liability_paise": discount, "maximum_potential_liability_paise": potential, "members_who_could_redeem": redeemers,
        "label": "HYPOTHETICAL: what members would be able to redeem if redemption existed. Nothing is applied to any invoice.",
    }


async def summary(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or utcnow()
    earn = case((L.entry_type == "EARN", L.points_delta), else_=0)
    out: dict = {"disclaimer": DISCLAIMER, "rule_version": rules.RULE_VERSION, "generated_at": now}

    by_event = []
    for ev, rewards, issued, capped, voided, expired in (await db.execute(
        select(L.event_type, func.sum(case((L.entry_type == "EARN", 1), else_=0)), func.sum(earn), func.sum(case((L.entry_type == "EARN", L.capped_points), else_=0)),
               func.sum(case((L.entry_type.in_(("VOID", "REVERSAL")), -L.points_delta), else_=0)), func.sum(case((L.entry_type == "EXPIRY", -L.points_delta), else_=0)))
        .group_by(L.event_type).order_by(L.event_type))).all():
        by_event.append({"event_type": ev, "rewards_recorded": _i(rewards), "points_issued": _i(issued), "points_capped": _i(capped),
                         "points_voided_or_reversed": _i(voided), "points_expired": _i(expired)})
    issued_total = sum(e["points_issued"] for e in by_event)
    capped_by = [{"capped_by": cb, "rewards": _i(n), "points_capped": _i(p)} for cb, n, p in (await db.execute(
        select(L.capped_by, func.count(L.id), func.sum(L.capped_points)).where(L.entry_type == "EARN", L.capped_points > 0).group_by(L.capped_by).order_by(L.capped_by))).all()]

    # members: net points issued per member, and their place against their own cycle ceiling
    per_member = {m: _i(t) for m, t in (await db.execute(select(L.member_id, func.sum(L.points_delta)).where(L.entry_type.in_(NET)).group_by(L.member_id))).all()}
    totals = sorted(per_member.values())
    cycle_rows = (await db.execute(
        select(GrowthPointCycle, func.coalesce(func.sum(L.points_delta), 0)).outerjoin(L, and_(L.cycle_id == GrowthPointCycle.id, L.entry_type.in_(NET)))
        .group_by(GrowthPointCycle.id))).all()
    tiers = {name: 0 for name, _, _ in TIERS}
    for c, net in cycle_rows:
        share = _i(net) * 100 / c.ceiling_points if c.ceiling_points else 0
        for name, lo, hi in TIERS:
            if lo <= share < hi:
                tiers[name] += 1
                break
    by_plan: dict[str, dict] = {}
    by_term: dict[int, dict] = {}
    for c, net in cycle_rows:
        months = max(0.0, (min(now, rules.aware(c.ends_at)) - rules.aware(c.starts_at)).total_seconds() / (86400 * 30.4375))
        for bucket, key in ((by_plan, c.plan_code), (by_term, c.term_months)):
            b = bucket.setdefault(key, {"cycles": 0, "members": set(), "points_net": 0, "member_months": 0.0, "ceiling_points": 0})
            b["cycles"] += 1
            b["members"].add(c.member_id)
            b["points_net"] += _i(net)
            b["member_months"] += months
            b["ceiling_points"] += c.ceiling_points

    def tidy(bucket: dict) -> list[dict]:
        return [{"key": k, "cycles": v["cycles"], "members": len(v["members"]), "points_net": v["points_net"],
                 "points_per_member_month": round(v["points_net"] / v["member_months"], 1) if v["member_months"] >= MIN_MEMBER_MONTHS else None,
                 "share_of_ceiling_used_percent": round(v["points_net"] * 100 / v["ceiling_points"], 1) if v["ceiling_points"] else None}
                for k, v in sorted(bucket.items(), key=lambda kv: str(kv[0]))]

    out["shadow_earning"] = {
        "points_issued": issued_total, "by_event_type": by_event, "capped": {"points": sum(e["points_capped"] for e in by_event), "by_rule": capped_by},
        "pair_rule_reductions": [c for c in capped_by if (c["capped_by"] or "").startswith("PAIR")],
        "members_with_points": len(per_member), "average_points_per_member": round(statistics.fmean(totals), 1) if totals else 0,
        "median_points_per_member": statistics.median(totals) if totals else 0, "max_points_one_member": totals[-1] if totals else 0,
        "distribution_of_cycles_by_share_of_ceiling": tiers, "by_plan": tidy(by_plan), "by_cycle_length_months": tidy(by_term),
        "tier_definition": "share of the member's own cycle ceiling: Low <5%, Average 5-25%, High 25-75%, Top 75%+",
    }
    out["hypothetical_redemption"] = await hypothetical(db, now)
    out["real_financial_cost"] = await real_financial_cost(db)
    return out


async def economics(db: AsyncSession, now: datetime | None = None) -> dict:
    """The management view: the MODELLED economy (400 members, approved assumptions) next to the ACTUAL shadow data."""
    now = now or utcnow()
    m = model.network()
    out: dict = {"disclaimer": DISCLAIMER, "rule_version": rules.RULE_VERSION, "generated_at": now}
    out["modelled"] = {
        "assumptions": "400 members; plan mix 55% Connect / 35% Growth / 10% Elite; the approved activity mix; 12% cycle ceiling; the approved reward values",
        "expected_annual_reward_cost_paise": round(m["expected_annual_paise"]), "worst_case_annual_reward_cost_paise": round(m["worst_annual_paise"]),
        "annual_subscription_revenue_paise": m["revenue_annual_paise"], "contractual_bound_annual_paise": m["contractual_bound_annual_paise"],
        "points_issued_per_year": round(m["points_issued_year"]),
        "expected_percent_of_revenue": round(m["expected_annual_paise"] * 100 / m["revenue_annual_paise"], 2),
        "worst_case_percent_of_revenue": round(m["worst_annual_paise"] * 100 / m["revenue_annual_paise"], 2),
    }
    first = await db.scalar(select(func.min(L.created_at)))
    observed_days = (now - rules.aware(first)).days if first else 0
    cycle_rows = (await db.execute(
        select(GrowthPointCycle, func.coalesce(func.sum(L.points_delta), 0)).outerjoin(L, and_(L.cycle_id == GrowthPointCycle.id, L.entry_type.in_(NET)))
        .where(GrowthPointCycle.starts_at <= now, GrowthPointCycle.ends_at > now).group_by(GrowthPointCycle.id))).all()
    worst = expected = 0.0
    plan_rows: dict[str, dict] = {}
    for c, net in cycle_rows:
        net = _i(net)
        elapsed = max((now - rules.aware(c.starts_at)).total_seconds() / (86400 * 30.4375), 0.0)
        cap = rules.redemption_cap_paise(c.price_minor)
        per_invoice_worst = min(rules.points_to_paise(min(c.ceiling_points, rules.MONTHLY_CEILING * c.term_months)), cap)
        invoices_per_year = 12 / c.term_months
        worst += per_invoice_worst * invoices_per_year
        if elapsed >= 1:                                   # needs a month of data before a rate means anything
            projected_points = min(net / elapsed * c.term_months, c.ceiling_points)
            expected += min(rules.points_to_paise(projected_points), cap) * invoices_per_year
        p = plan_rows.setdefault(c.plan_code, {"members": 0, "term_months": c.term_months, "price_minor": c.price_minor, "points": 0, "member_months": 0.0,
                                               "ceiling": c.ceiling_points, "worst_per_invoice": per_invoice_worst})
        p["members"] += 1
        p["points"] += net
        p["member_months"] += elapsed
    active_revenue = sum(c.price_minor * (12 // c.term_months) for c, _ in cycle_rows)
    out["actual_shadow"] = {
        "observed_days": observed_days, "confidence": "none" if not first else ("low: under 90 days of data" if observed_days < 90 else "usable"),
        "active_cycles": len(cycle_rows), "annualised_subscription_revenue_of_active_cycles_paise": active_revenue,
        "worst_case_annual_reward_cost_paise": round(worst), "projected_expected_annual_reward_cost_paise": round(expected) if observed_days >= 30 else None,
        "projection_note": "the points earned so far, at the same monthly rate, capped by each plan's ceiling and the 15% cap; only shown after 30 days of data",
    }
    out["hypothetical_redemption"] = await hypothetical(db, now)
    out["real_financial_cost"] = await real_financial_cost(db)

    # what a unit of business earns
    refs = _i(await db.scalar(select(func.count(func.distinct(L.reference_id))).where(L.entry_type == "EARN", L.reference_type == "referral", L.points_delta > 0)))
    ref_pts = _i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type.in_(NET), L.reference_type == "referral")))
    mtg = _i(await db.scalar(select(func.count(func.distinct(L.reference_id))).where(L.entry_type == "EARN", L.event_type == "MEETING_COMPLETED", L.points_delta > 0)))
    mtg_pts = _i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type.in_(NET), L.event_type == "MEETING_COMPLETED")))
    deals = _i(await db.scalar(select(func.count(func.distinct(L.reference_id))).where(L.entry_type == "EARN", L.reference_type == "deal_closure", L.points_delta > 0)))
    deal_pts = _i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type.in_(NET), L.reference_type == "deal_closure")))
    value = _i(await db.scalar(select(func.coalesce(func.sum(DealClosure.actual_value_minor), 0)).where(
        DealClosure.id.in_(select(L.reference_id).where(L.entry_type == "EARN", L.reference_type == "deal_closure", L.points_delta > 0)))))
    out["unit_economics"] = {
        "points_per_rewarded_referral": round(ref_pts / refs, 1) if refs else None, "points_per_meeting": round(mtg_pts / mtg, 1) if mtg else None,
        "points_per_closed_deal": round(deal_pts / deals, 1) if deals else None,
        "points_per_rs_100000_of_verified_business": round(deal_pts * 10_000_000 / value, 1) if value else None,
        "rewarded_referrals": refs, "rewarded_meetings": mtg, "rewarded_closed_deals": deals,
    }
    out["plan_comparison"] = [
        {"plan": plan, "term_months": v["term_months"], "price_paise": v["price_minor"], "active_cycles": v["members"], "points_net": v["points"],
         "points_per_member_month": round(v["points"] / v["member_months"], 1) if v["member_months"] >= MIN_MEMBER_MONTHS else None,
         "points_per_member_per_year_normalised": round(v["points"] / v["member_months"] * 12, 1) if v["member_months"] >= MIN_MEMBER_MONTHS else None,
         "cycle_ceiling_points": v["ceiling"], "worst_case_per_invoice_paise": v["worst_per_invoice"],
         "worst_case_percent_of_price": round(v["worst_per_invoice"] * 100 / v["price_minor"], 1)}
        for plan, v in sorted(plan_rows.items(), key=lambda kv: kv[1]["term_months"])
    ]
    return out


async def members_page(db: AsyncSession, page: int, page_size: int, search: str | None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    totals = (select(L.member_id.label("member_id"), func.sum(L.points_delta).label("total"),
                     func.sum(case((L.entry_type == "EARN", L.points_delta), else_=0)).label("issued"),
                     func.sum(case((L.entry_type == "EARN", L.capped_points), else_=0)).label("capped")).group_by(L.member_id).subquery())
    base = select(totals, User.email, PersonalProfile.full_name).join(User, User.id == totals.c.member_id).outerjoin(PersonalProfile, PersonalProfile.user_id == User.id)
    if search:
        like = f"%{search.strip().lower()}%"
        base = base.where(func.lower(User.email).like(like))
    total = _i(await db.scalar(select(func.count()).select_from(base.subquery())))
    rows = (await db.execute(base.order_by(totals.c.total.desc(), totals.c.member_id).limit(page_size).offset((page - 1) * page_size))).all()
    ids = [r.member_id for r in rows]
    lots = await _lot_rows(db, now, ids) if ids else []
    state: dict[str, dict] = defaultdict(lambda: {"PENDING": 0, "AVAILABLE": 0, "EXPIRED": 0})
    for member, _c, _e, remaining, avail, exp in lots:
        state[member][_state(avail, exp, now)] += _i(remaining)
    cycles = await _current_cycles(db, now)
    items = []
    for r in rows:
        c = cycles.get(r.member_id)
        s = state[r.member_id]
        items.append({
            "member_id": r.member_id, "email": r.email, "name": r.full_name, "shadow_total_points": _i(r.total), "points_issued": _i(r.issued), "points_capped": _i(r.capped),
            "pending_points": s["PENDING"], "available_points": s["AVAILABLE"], "plan": c.plan_code if c else None, "term_months": c.term_months if c else None,
            "cycle_ceiling_points": c.ceiling_points if c else None,
            "hypothetical_discount_paise": min(rules.points_to_paise(s["AVAILABLE"]), rules.redemption_cap_paise(c.price_minor)) if c else 0,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size)), "disclaimer": DISCLAIMER}


def ledger_item(r: GrowthPointLedger) -> dict:
    """A ledger row for an admin. Never includes a phone, an email, evidence or an exact deal value."""
    import json
    return {
        "id": r.id, "created_at": r.created_at, "event_at": r.event_at, "member_id": r.member_id, "counterparty_id": r.counterparty_id, "entry_type": r.entry_type,
        "event_type": r.event_type, "category": r.category, "role": r.role, "reference_type": r.reference_type, "reference_id": r.reference_id, "parent_id": r.parent_id,
        "cycle_id": r.cycle_id, "points_delta": r.points_delta, "requested_points": r.requested_points, "capped_points": r.capped_points, "capped_by": r.capped_by,
        "cap_trace": json.loads(r.cap_trace) if r.cap_trace else None, "status": r.status, "assurance": r.assurance, "verification_level": r.verification_level,
        "available_at": r.available_at, "expires_at": r.expires_at, "remaining": r.remaining, "balance_after": r.balance_after, "reason": r.reason,
        "details": json.loads(r.details) if r.details else None, "created_by": r.created_by, "rule_version": r.rule_version, "shadow": r.shadow,
        "idempotency_key": r.idempotency_key,
    }


async def ledger_page(db: AsyncSession, page: int, page_size: int, member_id: str | None = None, event_type: str | None = None,
                      status: str | None = None, capped_by: str | None = None, entry_type: str | None = None) -> dict:
    q = select(L)
    for col, val in ((L.member_id, member_id), (L.event_type, event_type), (L.status, status), (L.capped_by, capped_by), (L.entry_type, entry_type)):
        if val:
            q = q.where(col == val)
    total = _i(await db.scalar(select(func.count()).select_from(q.subquery())))
    rows = (await db.execute(q.order_by(L.created_at.desc(), L.id).limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [ledger_item(r) for r in rows], "total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size))}


async def flags_page(db: AsyncSession, page: int, page_size: int, status: str | None, kind: str | None, member_id: str | None = None) -> dict:
    import json
    q = select(GrowthPointFlag)
    if status:
        q = q.where(GrowthPointFlag.status == status)
    if kind:
        q = q.where(GrowthPointFlag.kind == kind)
    if member_id:
        q = q.where(GrowthPointFlag.member_id == member_id)
    total = _i(await db.scalar(select(func.count()).select_from(q.subquery())))
    rows = (await db.execute(q.order_by(GrowthPointFlag.created_at.desc(), GrowthPointFlag.id).limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [{"id": f.id, "created_at": f.created_at, "kind": f.kind, "severity": f.severity, "member_id": f.member_id, "pair_key": f.pair_key,
                       "reference_type": f.reference_type, "reference_id": f.reference_id, "details": json.loads(f.details) if f.details else None,
                       "status": f.status, "reviewed_at": f.reviewed_at, "review_note": f.review_note} for f in rows],
            "total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size)),
            "note": "Review items only. Nothing is blocked, reduced or punished automatically in Phase 1."}


def _pct(sorted_values: list[int], p: int) -> int:
    """Nearest-rank percentile of an already sorted list."""
    if not sorted_values:
        return 0
    return sorted_values[max(0, math.ceil(p / 100 * len(sorted_values)) - 1)]


async def observation(db: AsyncSession, now: datetime | None = None) -> dict:
    """The management review pack for the shadow OBSERVATION period: success metrics, and MODELLED next to ACTUAL.

    Counts and aggregates only: no member names, emails, phones, evidence or exact deal values. There is no end date: the period ends
    when management decides there is enough data, and `sufficiency` only reports how much data there is."""
    now = now or utcnow()
    m = model.network()
    first = await db.scalar(select(func.min(L.created_at)))
    started = rules.aware(first) if first else None
    observed_days = (now - started).days if started else 0

    # --- who is observed: members with a paid term running now (plus Season 1 complimentary terms), and their plan mix
    active: dict[str, dict] = {}
    for uid, code, price, months, starts in (await db.execute(
            select(Subscription.user_id, Plan.code, Plan.price_minor, Plan.period_months, Subscription.starts_at).join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.status == "ACTIVE", Subscription.starts_at <= now, Subscription.expires_at > now))).all():
        active[uid] = {"plan": code, "price": price, "months": months, "starts": rules.aware(starts)}
    for uid, starts in (await db.execute(select(TGLMembership.user_id, TGLMembership.starts_at).where(
            TGLMembership.status == "ACTIVE", TGLMembership.starts_at <= now, TGLMembership.expires_at > now))).all():
        active.setdefault(uid, {"plan": "complimentary", "price": 0, "months": 3, "starts": rules.aware(starts)})
    mix = defaultdict(int)
    for a in active.values():
        mix[a["plan"]] += 1
    n_active = len(active)
    revenue = sum(a["price"] * (12 // a["months"]) for a in active.values())

    # --- points in each active member's current cycle (a member with no points counts as 0)
    cur = {c.member_id: (c, _i(net)) for c, net in (await db.execute(
        select(GrowthPointCycle, func.coalesce(func.sum(L.points_delta), 0)).outerjoin(L, and_(L.cycle_id == GrowthPointCycle.id, L.entry_type.in_(NET)))
        .where(GrowthPointCycle.starts_at <= now, GrowthPointCycle.ends_at > now).group_by(GrowthPointCycle.id).order_by(GrowthPointCycle.starts_at))).all()}
    values = sorted(cur[u][1] if u in cur else 0 for u in active)
    total_points = sum(values)
    k = max(1, math.ceil(len(values) * 0.01)) if values else 0
    top = sum(values[-k:]) if k else 0
    dist = {
        "members": n_active, "average": round(total_points / n_active, 1) if n_active else 0, "median": statistics.median(values) if values else 0,
        "p90": _pct(values, 90), "p95": _pct(values, 95), "max": values[-1] if values else 0,
        "top_1_percent_members": k, "top_1_percent_points": top, "top_1_percent_share_of_points_percent": round(top * 100 / total_points, 1) if total_points else 0,
        "definition": "net points in each active member's current cycle; members with no points count as 0; nearest-rank percentiles; top 1% = the highest max(1, 1% of members)",
    }
    member_months = sum(max(0.0, (now - max(a["starts"], started or a["starts"])).total_seconds() / (86400 * 30.4375)) for a in active.values())

    # --- what happened (counts of rewarded things, capped, reversed, expired)
    def count(*where):
        return select(func.count(L.id)).where(*where)
    ledger_counts = {
        "rewards_recorded": _i(await db.scalar(count(L.entry_type == "EARN"))),
        "points_earned": _i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type == "EARN"))),
        "capped_rewards": _i(await db.scalar(count(L.entry_type == "EARN", L.capped_points > 0))),
        "fully_capped_rewards": _i(await db.scalar(count(L.entry_type == "EARN", L.status == "CAPPED"))),
        "points_capped": _i(await db.scalar(select(func.coalesce(func.sum(L.capped_points), 0)).where(L.entry_type == "EARN"))),
        "reversed_rewards": _i(await db.scalar(count(L.entry_type == "REVERSAL"))),
        "points_reversed": -_i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type == "REVERSAL"))),
        "voided_rewards": _i(await db.scalar(count(L.entry_type == "VOID"))),
        "points_voided": -_i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type == "VOID"))),
        "expired_lots": _i(await db.scalar(count(L.entry_type == "EXPIRY"))),
        "points_expired": -_i(await db.scalar(select(func.coalesce(func.sum(L.points_delta), 0)).where(L.entry_type == "EXPIRY"))),
    }
    flag_rows = (await db.execute(select(GrowthPointFlag.kind, GrowthPointFlag.status, func.count(GrowthPointFlag.id)).group_by(GrowthPointFlag.kind, GrowthPointFlag.status))).all()
    flags = {"total": sum(_i(n) for _, _, n in flag_rows), "open": sum(_i(n) for _, st, n in flag_rows if st == "OPEN"),
             "by_kind": {k_: sum(_i(n) for kk, _, n in flag_rows if kk == k_) for k_ in sorted({kk for kk, _, _ in flag_rows})}}

    # --- activity actually observed since the first recorded reward
    since = started or now
    referrals = _i(await db.scalar(select(func.count(BusinessReferral.id)).where(BusinessReferral.accepted_at.is_not(None), BusinessReferral.accepted_at >= since)))
    meetings = _i(await db.scalar(select(func.count(func.distinct(L.reference_id))).where(L.entry_type == "EARN", L.event_type == "MEETING_COMPLETED", L.points_delta > 0)))
    deals = _i(await db.scalar(select(func.count(func.distinct(L.reference_id))).where(L.entry_type == "EARN", L.reference_type == "deal_closure", L.points_delta > 0)))
    per_mm = lambda x: round(x / member_months, 3) if member_months >= 1 else None          # noqa: E731

    # --- circular / repeat patterns (counts only)
    pairs = {(g, r) for g, r in (await db.execute(select(BusinessReferral.giver_user_id, BusinessReferral.receiver_user_id).where(BusinessReferral.accepted_at.is_not(None)))).all()}
    reciprocal = sum(1 for g, r in pairs if (r, g) in pairs and g < r)
    pair_closures = (await db.execute(select(L.pair_key, func.count(func.distinct(L.reference_id)), func.sum(L.points_delta)).where(
        L.entry_type.in_(NET), L.reference_type == "deal_closure", L.pair_key.is_not(None)).group_by(L.pair_key))).all()
    closure_points = sum(_i(p) for _, _, p in pair_closures)
    patterns = {
        "pairs_with_accepted_referrals": len({frozenset(p) for p in pairs}), "reciprocal_pairs": reciprocal,
        "pairs_with_2_or_more_rewarded_closures": sum(1 for _, n, _ in pair_closures if _i(n) >= 2),
        "top_pair_share_of_closed_business_points_percent": round(max((_i(p) for _, _, p in pair_closures), default=0) * 100 / closure_points, 1) if closure_points else 0,
        "flags": {k_: v for k_, v in flags["by_kind"].items() if k_ in ("RECIPROCAL_REFERRALS", "PAIR_CONCENTRATION", "PAIR_FREQUENCY", "PAIR_VOLUME", "SAME_PROSPECT_ACROSS_PAIRS", "MEMBER_CLOSURE_CONCENTRATION")},
    }

    # --- renewals: the hypothetical use of old-cycle points at the renewal invoice (shadow only)
    R = GrowthPointRenewal
    by_plan_rows = (await db.execute(select(
        R.to_plan, func.count(R.id), func.sum(case((R.redeemed_points > 0, 1), else_=0)), func.coalesce(func.sum(R.redeemed_points), 0), func.coalesce(func.sum(R.eligible_points), 0),
        func.coalesce(func.sum(R.hypothetical_discount_paise), 0), func.coalesce(func.sum(R.remaining_points), 0), func.coalesce(func.sum(R.new_price_minor), 0)).group_by(R.to_plan).order_by(R.to_plan))).all()
    outcome_rows = {o: _i(n) for o, n in (await db.execute(select(R.outcome, func.count(R.id)).group_by(R.outcome))).all()}
    valid_cycles = {c for (c,) in (await db.execute(select(R.old_cycle_id).where(R.outcome.in_(("REDEEMED", "NOTHING_ELIGIBLE")), R.old_cycle_id.is_not(None)))).all()}
    expired_by_cycle = {c: _i(-p) for c, p in (await db.execute(select(L.cycle_id, func.sum(L.points_delta)).where(L.entry_type == "EXPIRY").group_by(L.cycle_id))).all()}
    redeemed_total = sum(_i(r[3]) for r in by_plan_rows)
    n_renewals = sum(_i(r[1]) for r in by_plan_rows)
    n_with_points = sum(_i(r[2]) for r in by_plan_rows)
    renewals = {
        "note": "HYPOTHETICAL. Old-cycle points that would have been used against the renewal invoice (up to 15% of the NEW plan's price). Nothing was applied to any invoice.",
        "renewals_recorded": n_renewals, "outcomes": outcome_rows, "renewals_that_used_points": n_with_points,
        "points_redeemed_hypothetically": redeemed_total, "hypothetical_discount_total_paise": sum(_i(r[5]) for r in by_plan_rows),
        "average_old_cycle_points_redeemed_per_renewal": round(redeemed_total / n_renewals, 1) if n_renewals else None,
        "average_old_cycle_points_redeemed_per_renewal_that_used_points": round(redeemed_total / n_with_points, 1) if n_with_points else None,
        "renewal_redemption_by_new_plan": [{"to_plan": r[0], "renewals": _i(r[1]), "renewals_that_used_points": _i(r[2]), "points_redeemed": _i(r[3]), "points_eligible": _i(r[4]),
                                            "hypothetical_discount_paise": _i(r[5]), "old_points_left_to_expire": _i(r[6]),
                                            "discount_percent_of_new_plan_invoices": round(_i(r[5]) * 100 / _i(r[7]), 2) if _i(r[7]) else None} for r in by_plan_rows],
        "points_expired_before_redemption": sum(expired_by_cycle.values()),
        "points_stranded_by_non_renewal": sum(p for c, p in expired_by_cycle.items() if c not in valid_cycles),
        "points_expired_after_a_partial_redemption": sum(p for c, p in expired_by_cycle.items() if c in valid_cycles),
    }
    created = _i(await db.scalar(select(func.count(BusinessReferral.id)).where(BusinessReferral.created_at >= since)))
    mod_conv = model.modelled_conversion()
    eco = await economics(db, now)
    unit = eco["unit_economics"]
    hyp = eco["hypothetical_redemption"]
    proj = eco["actual_shadow"]["projected_expected_annual_reward_cost_paise"]
    worst = eco["actual_shadow"]["worst_case_annual_reward_cost_paise"]
    pct = lambda x: round(x * 100 / revenue, 2) if (x is not None and revenue) else None          # noqa: E731
    mod_act = model.modelled_activity_per_member_month()
    return {
        "disclaimer": DISCLAIMER, "rule_version": rules.RULE_VERSION, "generated_at": now, "real_financial_cost": await real_financial_cost(db),
        "observed": {"observation_started": started, "observed_days": observed_days, "active_members": n_active, "plan_mix": dict(mix),
                     "plan_mix_percent": {k_: round(v * 100 / n_active, 1) for k_, v in mix.items()} if n_active else {}, "member_months": round(member_months, 1),
                     "accepted_referrals": referrals, "rewarded_meetings": meetings, "rewarded_verified_closed_deals": deals,
                     "annualised_subscription_revenue_of_active_members_paise": revenue},
        "success_metrics": {
            "points_per_member": dist,
            "points_per_referral": unit["points_per_rewarded_referral"], "points_per_meeting": unit["points_per_meeting"], "points_per_verified_closed_deal": unit["points_per_closed_deal"],
            "points_by_plan": eco["plan_comparison"], "points_by_cycle_length": (await summary(db, now))["shadow_earning"]["by_cycle_length_months"],
            "hypothetical_redemption_cost_now_paise": hyp["hypothetical_redemption_liability_paise"], "maximum_potential_redemption_cost_now_paise": hyp["maximum_potential_liability_paise"],
            "hypothetical_annual_liability_projected_paise": proj, "hypothetical_annual_liability_worst_case_paise": worst,
            "hypothetical_reward_cost_percent_of_subscription_revenue": {"projected": pct(proj), "worst_case": pct(worst), "outstanding_now": pct(hyp["hypothetical_redemption_liability_paise"])},
            "ledger": ledger_counts, "fraud_flags": flags, "repeat_and_circular_patterns": patterns, "renewals": renewals,
        },
        "modelled_vs_actual": {
            "note": "MODELLED = the approved 400-member model; ACTUAL = what the shadow ledger recorded. Compare per member-month, never raw totals: the member counts differ.",
            "plan_mix_percent": {"modelled": {k_: round(v * 100) for k_, v in model.MIX.items()}, "actual": {k_.capitalize(): v for k_, v in (
                {k_: round(v * 100 / n_active, 1) for k_, v in mix.items()} if n_active else {}).items()}},
            "accepted_referrals_per_member_month": {"modelled": mod_act["accepted_referrals"], "actual": per_mm(referrals)},
            "meetings_per_member_month": {"modelled": mod_act["meetings"], "actual": per_mm(meetings)},
            "verified_closed_deals_per_member_month": {"modelled": mod_act["verified_closed_deals"], "actual": per_mm(deals)},
            "points_per_member_month": {"modelled": round(m["points_issued_year"] / model.CAPACITY / 12, 1), "actual": per_mm(total_points)},
            "expected_annual_cost_per_member_paise": {"modelled": round(m["expected_annual_paise"] / model.CAPACITY), "actual_projected": round(proj / n_active) if (proj is not None and n_active) else None},
            "expected_cost_percent_of_revenue": {"modelled": round(m["expected_annual_paise"] * 100 / m["revenue_annual_paise"], 2), "actual_projected": pct(proj)},
            "worst_case_percent_of_revenue": {"modelled": round(m["worst_annual_paise"] * 100 / m["revenue_annual_paise"], 2), "actual": pct(worst)},
            "conversion": {"referral_created_to_accepted": {"modelled": None, "actual": round(referrals / created, 3) if created else None},
                           "accepted_to_meeting": {"modelled": mod_conv["accepted_to_meeting"], "actual": round(meetings / referrals, 3) if referrals else None},
                           "meeting_to_verified_deal": {"modelled": mod_conv["meeting_to_verified_deal"], "actual": round(deals / meetings, 3) if meetings else None}},
            "hypothetical_renewal_redemption_points": {"modelled": None, "actual": renewals["points_redeemed_hypothetically"]},
            "fraud_and_capping": {"capped_rewards": ledger_counts["capped_rewards"], "of_rewards_recorded": ledger_counts["rewards_recorded"], "open_flags": flags["open"]},
        },
        "sufficiency": {
            "note": "No automatic end date. The observation period ends when management decides there is enough data to compare MODELLED with ACTUAL.",
            "observed_days": observed_days, "active_members": n_active, "all_three_plans_observed": {"connect", "growth", "elite"} <= set(mix),
            "member_months": round(member_months, 1), "rewarded_referrals": referrals, "rewarded_meetings": meetings, "rewarded_verified_closed_deals": deals,
            "projection_available": proj is not None,
        },
    }
