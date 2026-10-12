"""A member's SUBSCRIPTION CYCLE as the reward engine sees it.

"Season" is not a unit any more. A cycle is the member's actual paid term: Connect 3 months, Growth 6, Elite 12 (the term
stored on the plan row and snapshotted on the invoice). Earning ceilings, the closed-business sub-ceiling, expiry and
(later) redemption are all per cycle. Different members have different cycles and different dates.

Cycles are read from `subscriptions` + `invoices` (and, for Season 1 registrants, `tgl_memberships`) and are only READ here:
nothing in this module writes a financial table. The cycle's own row (`growth_point_cycles`) freezes the ceilings computed
from the price that was actually invoiced.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GrowthPointCycle, Invoice, Plan, Subscription, TGLMembership
from . import rules


async def _freeze(db: AsyncSession, *, member_id: str, source_type: str, source_id: str, plan_code: str, price_minor: int,
                  term_months: int, starts_at, ends_at, persist: bool = True) -> GrowthPointCycle:
    existing = await db.scalar(select(GrowthPointCycle).where(GrowthPointCycle.source_type == source_type, GrowthPointCycle.source_id == source_id))
    if existing is not None:
        return existing
    caps = rules.category_ceilings(price_minor)
    cycle = GrowthPointCycle(
        member_id=member_id, source_type=source_type, source_id=source_id, plan_code=plan_code, price_minor=price_minor, term_months=term_months,
        starts_at=starts_at, ends_at=ends_at, renewal_opens_at=ends_at - timedelta(days=rules.RENEWAL_WINDOW_BEFORE_DAYS),
        grace_ends_at=ends_at + timedelta(days=rules.GRACE_DAYS), ceiling_points=rules.cycle_ceiling_points(price_minor),
        process_ceiling=caps["PROCESS"], closure_ceiling=caps["CLOSURE"], other_ceiling=caps["OTHER"], rule_version=rules.RULE_VERSION,
    )
    if persist:                                            # a read-only caller (the preview, the simulation) gets a transient, unsaved cycle
        db.add(cycle)
        await db.flush()
    return cycle


CANDIDATES_KEY, RESOLVED_KEY = "gp_cycle_candidates", "gp_cycles_resolved"      # per-transaction caches in `session.info` (cleared by engine.py when it ends)


async def _candidates(db: AsyncSession, member_id: str) -> list[tuple]:
    """Every term of this member that could cover some moment: [(starts_at, kind, row, ends_at)]. Read once per transaction."""
    cache = db.info.setdefault(CANDIDATES_KEY, {})
    if member_id in cache:
        return cache[member_id]
    out: list[tuple] = []
    subs = (await db.execute(
        select(Subscription).where(Subscription.user_id == member_id, Subscription.status.in_(("ACTIVE", "EXPIRED", "CANCELLED")),
                                   Subscription.starts_at.is_not(None), Subscription.expires_at.is_not(None))
    )).scalars().all()
    for s in subs:
        if s.status == "CANCELLED" and s.activated_at is None:
            continue                                           # cancelled before it was ever paid: no access, no cycle
        ends = rules.aware(s.expires_at)
        if s.status == "CANCELLED" and s.cancelled_at is not None:
            ends = min(ends, rules.aware(s.cancelled_at))       # a refunded term ends when it was cancelled
        start = rules.aware(s.starts_at)
        if s.renews_subscription_id and s.activated_at is not None and rules.aware(s.activated_at) < start:
            start = rules.aware(s.activated_at)    # an early renewal that is already paid: what is earned from the payment on belongs to the NEXT cycle
        out.append((start, "SUBSCRIPTION", s, ends))
    memberships = (await db.execute(
        select(TGLMembership).where(TGLMembership.user_id == member_id, TGLMembership.status.in_(("ACTIVE", "EXPIRED")),
                                    TGLMembership.starts_at.is_not(None), TGLMembership.expires_at.is_not(None))
    )).scalars().all()
    for m in memberships:
        out.append((rules.aware(m.starts_at), "MEMBERSHIP", m, rules.aware(m.expires_at)))
    if not any(kind == "MEMBERSHIP" for _s, kind, _r, _e in out):
        # Members whose Networking access is the Season 1 Finale window (a verified account whose email is on a registration) have no membership
        # ROW, but the specification gives them the same thing: ONE 3-month complimentary cycle. Without this they earned nothing at all.
        from ..models import Registration, User
        from ..security import finale_window
        user = await db.get(User, member_id)
        window = await finale_window(db) if user is not None and user.email_verified_at is not None else None
        if window is not None:
            reg = await db.scalar(select(Registration).where(func.lower(Registration.email) == user.email.lower()).order_by(Registration.created_at).limit(1))
            if reg is not None:
                out.append((rules.aware(window[1]), "MEMBERSHIP", reg, rules.aware(window[2])))
    cache[member_id] = out
    return out


async def resolve_cycle(db: AsyncSession, member_id: str, at, persist: bool = True) -> GrowthPointCycle | None:
    """The cycle that covers moment `at` for this member, or None (no active paid or complimentary term then).
    When two terms touch, the one that started later wins, so points earned after a renewal belong to the NEW cycle.

    Cost: the member's terms are read once per transaction; a cycle already frozen for a term is found by its unique
    (source_type, source_id) and the invoice and plan are only read the first time a term becomes a cycle."""
    at = rules.aware(at)
    covering = [c for c in await _candidates(db, member_id) if c[0] <= at < c[3]]
    if not covering:
        return None
    covering.sort(key=lambda c: c[0], reverse=True)
    start, kind, row, ends = covering[0]

    resolved = db.info.setdefault(RESOLVED_KEY, {})
    if (kind, row.id) in resolved:
        return resolved[(kind, row.id)]
    existing = await db.scalar(select(GrowthPointCycle).where(GrowthPointCycle.source_type == kind, GrowthPointCycle.source_id == row.id))
    if existing is not None:
        resolved[(kind, row.id)] = existing
        return existing

    if kind == "SUBSCRIPTION":
        invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == row.id).order_by(Invoice.created_at.desc()).limit(1))
        plan = await db.get(Plan, row.plan_id)
        if invoice is None or plan is None:
            return None
        price, term, code = invoice.list_price_minor, invoice.period_months, plan.code     # what was actually invoiced, not today's plan row
    else:
        # A Season 1 complimentary term counts as one 3-month cycle with the Connect plan's ceilings (specification: terms).
        connect = await db.scalar(select(Plan).where(Plan.code == "connect"))
        if connect is None:
            return None
        price, term, code = connect.price_minor, connect.period_months, "complimentary"

    cycle = await _freeze(db, member_id=member_id, source_type=kind, source_id=row.id, plan_code=code, price_minor=price,
                          term_months=term, starts_at=start, ends_at=ends, persist=persist)
    if persist:
        resolved[(kind, row.id)] = cycle
    return cycle
