"""REFERENCE MODEL of the PROPOSED Community rewards. CANDIDATE RULES: NOT APPROVED, NOT THE REWARD ENGINE, NOT A RULE VERSION.

Purpose: make the proposal's cap order DETERMINISTIC and TESTABLE before anything is built, and let the genuine Phase A data be replayed through it
(backend/scripts/community_candidate_evaluation.py) to estimate HYPOTHETICAL exposure. It is a pure function over a list of events: no database, no
ledger, no table, no side effect. A result of this model is never a Growth Point, never a balance and never redeemable.

The values and limits below are copied from docs/GROWTH_POINTS_BUSINESS_POLICY_PROPOSAL.md (revision 2) and are proposals. The ceilings come from the
approved growth-points-v3 module (app.rewards.rules), so a change to an approved number moves this model with it. Run from backend/.

THE CAP ORDER (a reward is cut by the FIRST rule that reduces it; every cut is recorded; `requested` is never changed):
   1 idempotency       the same event id is ignored
   2 prerequisite      a meeting bonus is paid only when its introduction was itself rewarded (it never outlives a capped introduction)
   3 pair rules        pair-once (connections) -> reciprocal 50% -> community pair budget (150 / pair / quarter) -> v3 low-assurance pair budget (1,500 / quarter)
   4 frequency limits  per member per calendar month or quarter (business time, UTC+05:30)
   5 participation     connection, need published, poster close: at most 5% of the cycle ceiling
   6 community pool    those plus confirmed help: at most 12% of the cycle ceiling
   7 category ceiling  PROCESS 25% / CLOSURE 60% / OTHER 20% (the pool is NESTED inside OTHER)
   8 daily             500 a day, low-assurance points only
   9 monthly           3,000 a month, all points
  10 cycle ceiling     12% of the plan price: always LAST, so no combination can exceed it
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.rewards import rules

_IST = timezone(timedelta(minutes=330))

# ---------------------------------------------------------------- PROPOSED values (revision 2). Points.
VALUES = {
    "CONNECTION_ACCEPTED": 10,          # each of the two members, first-ever acceptance of the pair
    "NEED_PUBLISHED": 20,               # poster
    "NEED_HELP_CONFIRMED": 25,          # helper
    "NEED_CLOSED": 10,                  # poster, when a resolution is confirmed with a credited helper
    "NEED_RESOLVED": 45,                # helper (approved v3 future value was 60; proposed 45)
    "SUCCESSFUL_INTRODUCTION": 30,      # connector
    "INTRODUCTION_MEETING": 45,         # connector, when the two introduced members confirm a meeting within 60 days
    "BUSINESS_VERIFIED": 75,            # once
}
PARTICIPATION_KINDS = ("CONNECTION_ACCEPTED", "NEED_PUBLISHED", "NEED_CLOSED")
POOL_KINDS = PARTICIPATION_KINDS + ("NEED_HELP_CONFIRMED",)
COMMUNITY_KINDS = POOL_KINDS + ("NEED_RESOLVED", "SUCCESSFUL_INTRODUCTION", "INTRODUCTION_MEETING")
POOL_PERCENT, PARTICIPATION_PERCENT = 12, 5
PAIR_COMMUNITY_BUDGET = 150             # per pair per calendar quarter, both members and both directions combined
RECIPROCAL_FACTOR_PERCENT, RECIPROCAL_WINDOW_DAYS = 50, 60
MONTHLY_LIMIT = {"CONNECTION_ACCEPTED": 6, "NEED_PUBLISHED": 2, "NEED_HELP_CONFIRMED": 8, "NEED_CLOSED": 2}
QUARTERLY_LIMIT = {"NEED_RESOLVED": 4, "SUCCESSFUL_INTRODUCTION": 2}
PAIR_QUARTER_LIMIT = {"NEED_HELP_CONFIRMED": 2, "NEED_RESOLVED": 1}      # rewarded events per (member, counterparty) per calendar quarter
ONCE_PER_PAIR = ("CONNECTION_ACCEPTED",)
RECIPROCAL_KINDS = ("NEED_HELP_CONFIRMED", "NEED_RESOLVED", "SUCCESSFUL_INTRODUCTION")
# existing approved events, only as far as the cap pipeline needs to know them
CATEGORY = {"REFERRAL_ACCEPTED": "PROCESS", "PROSPECT_CONTACTED": "PROCESS", "MEETING_COMPLETED": "PROCESS", "BUSINESS_CLOSED": "CLOSURE", "REPEAT_BUSINESS": "CLOSURE",
            "PROFILE_COMPLETED": "OTHER", **{k: "OTHER" for k in VALUES}}
ORDER = ("IDEMPOTENCY", "PREREQUISITE", "PAIR_ONCE", "PAIR_RECIPROCAL", "PAIR_COMMUNITY", "PAIR_LOW_ASSURANCE", "FREQUENCY_LIMIT", "COMMUNITY_PARTICIPATION", "COMMUNITY_POOL",
         "CATEGORY_SUBCEILING", "DAILY_CEILING", "MONTHLY_CEILING", "CYCLE_CEILING")


@dataclass(frozen=True)
class Event:
    id: str                              # the idempotency key
    member: str                          # who would earn it
    kind: str
    at: datetime
    points: int | None = None            # requested points; None = the proposed value for a community kind
    counterparty: str | None = None      # the other member, when there is one (it defines the pair)
    level: int = 1                       # verification level 1-4 (1-2 low assurance, 3-4 verified)


@dataclass
class Decision:
    event: Event
    requested: int
    awarded: int
    capped_by: str | None
    trace: list[tuple[str, int, int]] = field(default_factory=list)       # (rule, from, to), in the order applied


def _local(dt: datetime) -> datetime:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(_IST)


def day_key(dt: datetime) -> str:
    return _local(dt).strftime("%Y-%m-%d")


def month_key(dt: datetime) -> str:
    return _local(dt).strftime("%Y-%m")


def quarter_key(dt: datetime) -> str:
    d = _local(dt)
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def pair_of(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


class Cycle:
    """One member's subscription cycle. All state lives here, so the whole model is a pure function of the event list."""

    def __init__(self, price_minor: int):
        self.price_minor = price_minor
        self.ceiling = rules.cycle_ceiling_points(price_minor)
        self.sub = rules.category_ceilings(price_minor)
        self.total = 0
        self.by_category = {"PROCESS": 0, "CLOSURE": 0, "OTHER": 0}
        self.pool = 0
        self.participation = 0
        self.by_day: dict[str, int] = {}
        self.by_month: dict[str, int] = {}
        self.counts: dict[tuple, int] = {}


class Model:
    """Apply events in the order given (the engine's order of occurrence). Deterministic: the same list always gives the same decisions."""

    def __init__(self, price_minor_by_member: dict[str, int] | int):
        self._prices = price_minor_by_member
        self.cycles: dict[str, Cycle] = {}
        self.seen: set[str] = set()
        self.pair_once: set[tuple] = set()
        self.pair_comm: dict[tuple, int] = {}
        self.pair_low: dict[tuple, int] = {}
        self.pair_kind: dict[tuple, int] = {}
        self.paid_intro: set[tuple[str, str]] = set()                  # (connector, introduced counterparty) pairs whose introduction was rewarded
        self.paid_help: list[tuple[str, str, datetime]] = []          # (helper, poster, when): what makes a later reverse help reciprocal

    def cycle(self, member: str) -> Cycle:
        if member not in self.cycles:
            price = self._prices if isinstance(self._prices, int) else self._prices[member]
            self.cycles[member] = Cycle(price)
        return self.cycles[member]

    def apply(self, ev: Event) -> Decision:
        requested = ev.points if ev.points is not None else VALUES[ev.kind]
        d = Decision(ev, requested, requested, None)
        if ev.id in self.seen:                                                       # 1 idempotency: the first decision stands, nothing is added
            d.awarded, d.capped_by = 0, "IDEMPOTENCY"
            return d
        self.seen.add(ev.id)
        cyc = self.cycle(ev.member)
        category = CATEGORY[ev.kind]
        low = ev.level <= rules.LOW_ASSURANCE_MAX_LEVEL
        pair = pair_of(ev.member, ev.counterparty) if ev.counterparty else None
        allowed = max(0, requested)

        def cut(rule: str, value: int) -> None:
            nonlocal allowed
            value = max(0, min(allowed, value))
            if value < allowed:
                d.trace.append((rule, allowed, value))
                d.capped_by = d.capped_by or rule
                allowed = value

        if ev.kind == "INTRODUCTION_MEETING" and (ev.member, ev.counterparty) not in self.paid_intro:       # 2 prerequisite
            cut("PREREQUISITE", 0)
        if pair and ev.kind in ONCE_PER_PAIR:                                          # 3 pair rules
            if (ev.kind, pair, ev.member) in self.pair_once:
                cut("PAIR_ONCE", 0)
        if pair and ev.kind in RECIPROCAL_KINDS and any(h == ev.counterparty and p == ev.member and (ev.at - w) <= timedelta(days=RECIPROCAL_WINDOW_DAYS) and ev.at >= w
                                                         for h, p, w in self.paid_help):
            cut("PAIR_RECIPROCAL", allowed * RECIPROCAL_FACTOR_PERCENT // 100)
        q = quarter_key(ev.at)
        if pair and ev.kind in COMMUNITY_KINDS:
            cut("PAIR_COMMUNITY", PAIR_COMMUNITY_BUDGET - self.pair_comm.get((pair, q), 0))
        if pair and low:
            cut("PAIR_LOW_ASSURANCE", rules.PAIR_LOW_ASSURANCE_BUDGET - self.pair_low.get((pair, q), 0))
        if pair and ev.kind in PAIR_QUARTER_LIMIT and self.pair_kind.get((ev.kind, ev.member, ev.counterparty, q), 0) >= PAIR_QUARTER_LIMIT[ev.kind]:
            cut("FREQUENCY_LIMIT", 0)
        if ev.kind in MONTHLY_LIMIT and cyc.counts.get((ev.kind, month_key(ev.at)), 0) >= MONTHLY_LIMIT[ev.kind]:      # 3 frequency
            cut("FREQUENCY_LIMIT", 0)
        if ev.kind in QUARTERLY_LIMIT and cyc.counts.get((ev.kind, q), 0) >= QUARTERLY_LIMIT[ev.kind]:
            cut("FREQUENCY_LIMIT", 0)
        if ev.kind in PARTICIPATION_KINDS:                                             # 4, 5 nested community limits
            cut("COMMUNITY_PARTICIPATION", cyc.ceiling * PARTICIPATION_PERCENT // 100 - cyc.participation)
        if ev.kind in POOL_KINDS:
            cut("COMMUNITY_POOL", cyc.ceiling * POOL_PERCENT // 100 - cyc.pool)
        cut("CATEGORY_SUBCEILING", cyc.sub[category] - cyc.by_category[category])      # 6
        if low:                                                                        # 7
            cut("DAILY_CEILING", rules.DAILY_CEILING_LOW_ASSURANCE - cyc.by_day.get(day_key(ev.at), 0))
        cut("MONTHLY_CEILING", rules.MONTHLY_CEILING - cyc.by_month.get(month_key(ev.at), 0))        # 8
        cut("CYCLE_CEILING", cyc.ceiling - cyc.total)                                  # 9, always last
        d.awarded = allowed
        # record what was used (a zero still counts as a frequency attempt only when something was awarded, as the engine counts rewarded events)
        if allowed:
            cyc.total += allowed
            cyc.by_category[category] += allowed
            cyc.by_day[day_key(ev.at)] = cyc.by_day.get(day_key(ev.at), 0) + (allowed if low else 0)
            cyc.by_month[month_key(ev.at)] = cyc.by_month.get(month_key(ev.at), 0) + allowed
            if ev.kind in PARTICIPATION_KINDS:
                cyc.participation += allowed
            if ev.kind in POOL_KINDS:
                cyc.pool += allowed
            if ev.kind in MONTHLY_LIMIT:
                cyc.counts[(ev.kind, month_key(ev.at))] = cyc.counts.get((ev.kind, month_key(ev.at)), 0) + 1
            if ev.kind in QUARTERLY_LIMIT:
                cyc.counts[(ev.kind, q)] = cyc.counts.get((ev.kind, q), 0) + 1
            if pair and ev.kind in PAIR_QUARTER_LIMIT:
                self.pair_kind[(ev.kind, ev.member, ev.counterparty, q)] = self.pair_kind.get((ev.kind, ev.member, ev.counterparty, q), 0) + 1
            if pair and ev.kind in ONCE_PER_PAIR:
                self.pair_once.add((ev.kind, pair, ev.member))
            if pair and ev.kind in COMMUNITY_KINDS:
                self.pair_comm[(pair, q)] = self.pair_comm.get((pair, q), 0) + allowed
            if pair and low:
                self.pair_low[(pair, q)] = self.pair_low.get((pair, q), 0) + allowed
            if ev.kind == "SUCCESSFUL_INTRODUCTION":
                self.paid_intro.add((ev.member, ev.counterparty))
            if ev.kind in RECIPROCAL_KINDS and ev.counterparty:
                self.paid_help.append((ev.member, ev.counterparty, ev.at))
        return d

    def run(self, events: list[Event]) -> list[Decision]:
        return [self.apply(e) for e in events]
