"""The ONE reward engine. Routes never do reward arithmetic; they report that something changed (hooks.py) and this module
decides what shadow points that is worth.

    verified event -> base reward -> pair rules -> category sub-ceiling -> daily -> monthly -> cycle ceiling -> shadow ledger row

Every step that reduces a reward is recorded (`capped_by` = the first rule that reduced it, `cap_trace` = all of them in
order, `requested_points`, `capped_points`) so the economy can be analysed. A reward reduced to nothing is still a row.

Shadow mode: nothing here reads or writes an invoice, a payment, a price or a subscription (cycles.py only reads them),
and firewall.guard() makes any attempt to write one raise.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import and_, case, event, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..models import GrowthPointBalance, GrowthPointCycle, GrowthPointLedger, GrowthPointRuleVersion, utcnow
from . import cycles, ledger, rules


class RuleDrift(RuntimeError):
    """The code's parameters differ from those stored for the same rule version: bump RULE_VERSION instead of editing it."""


_verified_versions: set[str] = set()


async def ensure_rule_version(db: AsyncSession) -> None:
    """Record this version's parameters once; refuse to run if the code has drifted from what is stored for it."""
    if rules.RULE_VERSION in _verified_versions:
        return
    row = await db.get(GrowthPointRuleVersion, rules.RULE_VERSION)
    if row is None:
        db.add(GrowthPointRuleVersion(version=rules.RULE_VERSION, parameters_json=rules.parameters_json(), sha256=rules.parameters_hash()))
        await db.flush()
    elif row.sha256 != rules.parameters_hash():
        raise RuleDrift(f"Rule version {rules.RULE_VERSION} is stored with different parameters than the code now has. Create a new RULE_VERSION.")
    _verified_versions.add(rules.RULE_VERSION)


# Per-transaction caches kept in `session.info` (cleared when the transaction ends, because the row locks end with it).
_LOCKED = "gp_locked"


@event.listens_for(Session, "after_transaction_end")
def _forget_locks(session, transaction):           # noqa: ARG001 - SQLAlchemy hook signature
    """A commit or rollback releases the row locks, so what this session remembers about them (and the cycles it resolved) is stale."""
    if transaction.parent is None:
        for key in (_LOCKED, cycles.CANDIDATES_KEY, cycles.RESOLVED_KEY):
            session.info.pop(key, None)


async def lock_members(db: AsyncSession, member_ids) -> dict[str, GrowthPointBalance]:
    """Serialise reward processing for these members (and therefore for their pair): one row lock each, always in the same
    order so two events can not deadlock. Creates the balance row on first use. A member already locked in this transaction is
    not locked again (the lock is held until commit), so one reward event costs one lock query, not one per award."""
    ids = sorted({m for m in member_ids if m})
    held: dict[str, GrowthPointBalance] = db.info.setdefault(_LOCKED, {})
    missing = [m for m in ids if m not in held]
    if missing:
        found = (await db.execute(
            select(GrowthPointBalance).where(GrowthPointBalance.member_id.in_(missing)).order_by(GrowthPointBalance.member_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().all()
        held.update({r.member_id: r for r in found})
        new = [m for m in missing if m not in held]
        for m in new:                                  # first use: the inserted row is locked by this transaction until it ends
            row = GrowthPointBalance(member_id=m, total_points=0)
            db.add(row)
            held[m] = row
        if new:
            await db.flush()
    return {m: held[m] for m in ids}


@dataclass
class AwardRequest:
    member_id: str
    event_type: str
    reference_type: str
    reference_id: str
    requested: int                                  # the base reward, from rules, before any cap
    level: int                                      # verification level, from the verified event (never from a client)
    event_at: datetime
    role: str | None = None                         # referrer / recipient / member
    counterparty_id: str | None = None
    prospect_key: str | None = None
    pair_adjust: tuple[int, str] | None = None      # (factor percent, rule name): the closure concentration / reciprocal rule
    ineligible: tuple[str, str] | None = None       # (rule name, reason): record the event with 0 points
    key_suffix: str = ""
    reason: str = ""
    details: dict = field(default_factory=dict)
    created_by: str = "system"


@dataclass
class AwardResult:
    row: GrowthPointLedger
    created: bool


def idempotency_key(event_type: str, reference_type: str, reference_id: str, member_id: str, suffix: str = "") -> str:
    """member + event + reference: the same networking event can never be rewarded twice."""
    return f"{event_type}:{reference_type}:{reference_id}:{member_id}{suffix}"


_NET = ("EARN", "VOID", "REVERSAL")      # what counts toward a ceiling: points issued net of what was voided or reversed (not expiry)


async def _usage(db: AsyncSession, req: "AwardRequest", *, pair: str | None, cycle_id: str, category: str, assurance: str, day: str, month: str, quarter: str) -> dict[str, int]:
    """Everything the cap pipeline needs to know about what is already recorded, in ONE query: points used against the pair budget,
    the category sub-ceiling, today, this month and the cycle, and how many of this event the member was rewarded for this month.
    (The pipeline used to run one aggregate per rule; the numbers are the same, they are just read together.)"""
    L, pts, m = GrowthPointLedger, GrowthPointLedger.points_delta, req.member_id

    def used(*cond):
        return func.coalesce(func.sum(case((and_(*cond), pts), else_=0)), 0)

    cols = {
        "sub": used(L.cycle_id == cycle_id, L.category == category),
        "daily": used(L.member_id == m, L.day_key == day, L.assurance == "LOW"),
        "monthly": used(L.member_id == m, L.month_key == month),
        "cycle": used(L.cycle_id == cycle_id),
        "frequency": func.coalesce(func.sum(case((and_(L.entry_type == "EARN", pts > 0, L.member_id == m, L.event_type == req.event_type, L.month_key == month), 1), else_=0)), 0),
    }
    scope = L.member_id == m
    if pair:
        cols["pair"] = used(L.pair_key == pair, L.quarter_key == quarter, L.assurance == "LOW")
        scope = or_(scope, L.pair_key == pair)
    row = (await db.execute(select(*[c.label(k) for k, c in cols.items()]).where(L.entry_type.in_(_NET), scope))).one()
    return {k: int(row._mapping[k] or 0) for k in cols}


async def award(db: AsyncSession, req: AwardRequest, now: datetime | None = None) -> AwardResult:
    """Issue (or find) the shadow reward for one member for one event. Callers hold the member lock (lock_members)."""
    now = now or utcnow()
    spec = rules.EVENTS[req.event_type]
    if not spec["enabled"]:
        raise ValueError(f"{req.event_type} is not an enabled reward event")
    key = idempotency_key(req.event_type, req.reference_type, req.reference_id, req.member_id, req.key_suffix)
    # The member and the counterparty are locked BEFORE anything is read, so the pair budget, the ceilings and the idempotency
    # check below all see a consistent ledger (a no-op on SQLite, whose writers are already serialised).
    balances = await lock_members(db, [req.member_id, req.counterparty_id])
    existing = await db.scalar(select(GrowthPointLedger).where(GrowthPointLedger.idempotency_key == key))
    if existing is not None:
        return AwardResult(existing, False)
    await ensure_rule_version(db)

    category = spec["category"]
    assurance = rules.assurance_of(req.level)
    pair = ledger.pair_key(req.member_id, req.counterparty_id) if req.counterparty_id else None
    day, month, quarter = rules.day_key(req.event_at), rules.month_key(req.event_at), rules.quarter_key(req.event_at)
    cycle = None if req.ineligible else await cycles.resolve_cycle(db, req.member_id, req.event_at)

    allowed = max(0, int(req.requested))
    trace: list[dict] = []

    def cut(rule: str, new_value: int) -> None:
        nonlocal allowed
        new_value = max(0, min(allowed, new_value))
        if new_value < allowed:
            trace.append({"rule": rule, "from": allowed, "to": new_value})
            allowed = new_value

    if req.ineligible:
        cut(req.ineligible[0], 0)
    elif cycle is None:
        cut(rules.CAP_NO_CYCLE, 0)                      # no paid or complimentary term covered that moment: nothing is earned
    else:
        # --- pair rules (Pair Assurance Rule, per calendar quarter)
        if req.pair_adjust is not None:
            factor, name = req.pair_adjust
            cut(name, allowed * factor // 100)
        usage = await _usage(db, req, pair=pair, cycle_id=cycle.id, category=category, assurance=assurance, day=day, month=month, quarter=quarter)
        if pair and assurance == "LOW":
            cut(rules.CAP_PAIR_LOW_ASSURANCE, rules.PAIR_LOW_ASSURANCE_BUDGET - usage["pair"])
        # --- frequency limits (rewarded events per calendar month / once per prospect per quarter)
        limit = (spec.get("monthly_limit") or {}).get(req.role or "")
        if limit is not None and allowed > 0 and usage["frequency"] >= limit:
            cut(rules.CAP_FREQUENCY, 0)
        if req.event_type == "REPEAT_BUSINESS" and allowed > 0 and req.prospect_key:
            seen = await db.scalar(select(func.count(GrowthPointLedger.id)).where(
                GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.points_delta > 0, GrowthPointLedger.event_type == "REPEAT_BUSINESS",
                GrowthPointLedger.prospect_key == req.prospect_key, GrowthPointLedger.quarter_key == quarter,
                GrowthPointLedger.reference_id != req.reference_id))
            if seen:
                cut(rules.CAP_REPEAT, 0)
        # --- category sub-ceiling, then daily (low assurance only), monthly, cycle
        sub = {"PROCESS": cycle.process_ceiling, "CLOSURE": cycle.closure_ceiling, "OTHER": cycle.other_ceiling}[category]
        cut(rules.CAP_SUBCEILING, sub - usage["sub"])
        if assurance == "LOW":
            cut(rules.CAP_DAILY, rules.DAILY_CEILING_LOW_ASSURANCE - usage["daily"])
        cut(rules.CAP_MONTHLY, rules.MONTHLY_CEILING - usage["monthly"])
        cut(rules.CAP_CYCLE, cycle.ceiling_points - usage["cycle"])

    awarded = allowed
    capped = max(0, int(req.requested)) - awarded
    if awarded == 0:
        status, available_at, expires_at = "CAPPED", None, None
    else:
        available_at = req.event_at + timedelta(days=rules.PENDING_DAYS) if assurance == "LOW" else req.event_at
        expires_at = cycle.grace_ends_at
        status = "PENDING" if rules.aware(available_at) > now else "AVAILABLE"

    bal = balances[req.member_id]
    bal.total_points += awarded
    row = GrowthPointLedger(
        event_at=req.event_at, member_id=req.member_id, counterparty_id=req.counterparty_id, pair_key=pair, entry_type="EARN",
        event_type=req.event_type, category=category, role=req.role, reference_type=req.reference_type, reference_id=req.reference_id,
        cycle_id=cycle.id if cycle else None, prospect_key=req.prospect_key, points_delta=awarded, requested_points=max(0, int(req.requested)),
        capped_points=capped, capped_by=(trace[0]["rule"] if trace and capped > 0 else None),
        cap_trace=json.dumps(trace) if trace else None, status=status, assurance=assurance, verification_level=req.level,
        available_at=available_at, expires_at=expires_at, remaining=awarded, balance_after=bal.total_points, reason=req.reason or None,
        details=json.dumps(req.details, default=str) if req.details else None, created_by=req.created_by, rule_version=rules.RULE_VERSION,
        idempotency_key=key, shadow=True, day_key=day, month_key=month, quarter_key=quarter,
    )
    db.add(row)
    await db.flush()
    return AwardResult(row, True)


# --------------------------------------------------------------------------------------- adjustments (never edits)
_KIND = {"VOID": "VOIDED", "REVERSAL": "REVERSED", "EXPIRY": "EXPIRED"}


async def adjust(db: AsyncSession, lot: ledger.Lot, kind: str, reason: str, created_by: str = "system") -> GrowthPointLedger | None:
    """Take a lot's remaining points back with a NEW negative row that points at it. VOID: pending points that never became
    usable. REVERSAL: points already usable, taken back (a deal found false). EXPIRY: unused points past the end of grace."""
    if lot.remaining <= 0:
        return None
    parent = lot.row
    key = f"adjust:{kind}:{parent.id}"
    existing = await db.scalar(select(GrowthPointLedger).where(GrowthPointLedger.idempotency_key == key))
    if existing is not None:
        return None
    balances = await lock_members(db, [parent.member_id])
    bal = balances[parent.member_id]
    bal.total_points -= lot.remaining
    row = GrowthPointLedger(
        event_at=parent.event_at, member_id=parent.member_id, counterparty_id=parent.counterparty_id, pair_key=parent.pair_key, entry_type=kind,
        event_type=parent.event_type, category=parent.category, role=parent.role, reference_type=parent.reference_type, reference_id=parent.reference_id,
        parent_id=parent.id, cycle_id=parent.cycle_id, prospect_key=parent.prospect_key, points_delta=-lot.remaining, requested_points=0,
        capped_points=0, status=_KIND[kind], assurance=parent.assurance, verification_level=parent.verification_level, available_at=parent.available_at,
        expires_at=parent.expires_at, remaining=0, balance_after=bal.total_points, reason=reason, created_by=created_by, rule_version=rules.RULE_VERSION,
        idempotency_key=key, shadow=True, day_key=parent.day_key, month_key=parent.month_key, quarter_key=parent.quarter_key,
    )
    db.add(row)
    await db.flush()
    return row
