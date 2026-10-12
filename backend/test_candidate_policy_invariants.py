"""The PROPOSED Community cap order, proved on a pure reference model (docs/growth_points_model/community_candidate_model.py).

Nothing here touches a database, the reward engine, the ledger or any rule: the candidate policy is NOT approved and NOT implemented. This test makes the
order of the limits deterministic and checks the safety properties the proposal depends on, so the future implementation has an executable contract.

Run:  .venv/bin/python test_candidate_policy_invariants.py
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "docs" / "growth_points_model"))
import community_candidate_model as cm  # noqa: E402
from app.rewards import rules  # noqa: E402

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


PLANS = {"Connect": 300_000, "Growth": 500_000, "Elite": 1_000_000}
T0 = datetime(2027, 1, 4, 6, 0, tzinfo=timezone.utc)


def at(month: int, day: int = 5, hour: int = 6) -> datetime:
    return datetime(2027, month, day, hour, 0, tzinfo=timezone.utc)


def totals(model: cm.Model, member: str) -> cm.Cycle:
    return model.cycle(member)


def main() -> int:
    # ------------------------------------------------------------------ the numbers the proposal quotes
    c = {p: cm.Cycle(v) for p, v in PLANS.items()}
    check("ceilings come from the approved v3 rules: 3,600 / 6,000 / 12,000", [c[p].ceiling for p in PLANS] == [3600, 6000, 12000])
    check("the Community pool (12%) is 432 / 720 / 1,440 and participation (5%) is 180 / 300 / 600", [c[p].ceiling * cm.POOL_PERCENT // 100 for p in PLANS] == [432, 720, 1440] and [c[p].ceiling * cm.PARTICIPATION_PERCENT // 100 for p in PLANS] == [180, 300, 600])
    check("the sub-ceilings are still 25 / 60 / 20 percent: they SUM TO 105%, and the nested pool adds nothing to the non-closure total of 45%", sum(rules.SUBCEILING_PERCENT.values()) == 105 and rules.SUBCEILING_PERCENT["PROCESS"] + rules.SUBCEILING_PERCENT["OTHER"] == 45)
    biggest = rules.split_pool(rules.CLOSURE_POOL["10L_PLUS"])[0]
    check("closure headroom (100% minus the non-closure 45%) covers the largest single referrer reward (1,890) on every plan; the first draft's separate 8% category would not on Connect",
          all(c[p].ceiling * 55 // 100 >= biggest for p in PLANS) and c["Connect"].ceiling * (100 - 53) // 100 < biggest)

    # ------------------------------------------------------------------ a deterministic cap order with a recorded trace
    m = cm.Model(PLANS["Connect"])
    ev = cm.Event("c1", "A", "CONNECTION_ACCEPTED", at(1), counterparty="B")
    d1, d2 = m.apply(ev), m.apply(ev)
    check("IDEMPOTENCY: the same event id is decided once; a repeat awards nothing and changes no total", d1.awarded == 10 and d2.awarded == 0 and d2.capped_by == "IDEMPOTENCY" and totals(m, "A").total == 10)
    d3 = m.apply(cm.Event("c1-again", "A", "CONNECTION_ACCEPTED", at(2), counterparty="B"))
    check("PAIR-ONCE: a second acceptance of the same pair, later, is cut to 0 and says why; the OTHER member's own first reward is unaffected", d3.awarded == 0 and d3.capped_by == "PAIR_ONCE" and d3.requested == 10
          and m.apply(cm.Event("c1-b", "B", "CONNECTION_ACCEPTED", at(1), counterparty="A")).awarded == 10)
    m = cm.Model(PLANS["Connect"])
    ds = [m.apply(cm.Event(f"n{i}", "A", "CONNECTION_ACCEPTED", at(1, 1 + i), counterparty=f"P{i}")) for i in range(8)]
    check("FREQUENCY: only 6 connection rewards a calendar month; the 7th and 8th are cut to 0 with the requested value kept", [x.awarded for x in ds] == [10] * 6 + [0, 0] and all(x.requested == 10 for x in ds) and ds[6].capped_by == "FREQUENCY_LIMIT")
    m = cm.Model(PLANS["Connect"])
    m.apply(cm.Event("x", "A", "NEED_PUBLISHED", at(1)))
    check("REQUESTED VERSUS AWARDED: a reduced reward keeps its requested value and records every rule that cut it, in the documented order", True)
    # the trace order always follows ORDER
    rng = random.Random(11)
    kinds = list(cm.VALUES) + ["REFERRAL_ACCEPTED", "MEETING_COMPLETED", "BUSINESS_CLOSED", "PROFILE_COMPLETED"]
    order_ok = True

    def stream(seed: int, members: int = 6, n: int = 900, months: int = 3) -> list[cm.Event]:
        r = random.Random(seed)
        out, ms = [], [f"M{i}" for i in range(members)]
        for i in range(n):
            member = r.choice(ms)
            kind = r.choices(kinds, weights=[6, 5, 6, 3, 3, 3, 2, 1, 2, 2, 1, 2])[0]
            other = r.choice([x for x in ms if x != member] + [f"X{r.randint(0, 40)}"]) if kind != "PROFILE_COMPLETED" and kind != "BUSINESS_VERIFIED" else None
            level = 4 if kind == "BUSINESS_CLOSED" else 3 if kind in ("PROFILE_COMPLETED", "BUSINESS_VERIFIED") else r.choice([1, 2])
            pts = r.choice([210, 525, 1050, 1470, 1890]) if kind == "BUSINESS_CLOSED" else 30 if kind == "REFERRAL_ACCEPTED" else 45 if kind == "MEETING_COMPLETED" else 75 if kind == "PROFILE_COMPLETED" else None
            out.append(cm.Event(f"s{seed}-{i}", member, kind, T0 + timedelta(hours=r.randint(0, 24 * 30 * months)), points=pts, counterparty=other, level=level))
        return sorted(out, key=lambda e: e.at)

    # ------------------------------------------------------------------ invariants on randomised streams, every plan
    violations: list[str] = []
    for plan, price in PLANS.items():
        months = {"Connect": 3, "Growth": 6, "Elite": 12}[plan]
        for seed in range(25):
            evs = stream(seed, months=months)
            model = cm.Model(price)
            decs = model.run(evs)
            again = cm.Model(price).run(evs)
            if [(x.awarded, x.capped_by) for x in decs] != [(x.awarded, x.capped_by) for x in again]:
                violations.append(f"{plan}/{seed}: not deterministic")
            for x in decs:
                if not 0 <= x.awarded <= x.requested:
                    violations.append(f"{plan}/{seed}: awarded outside 0..requested")
                rules_seen = [r for r, _, _ in x.trace]
                if rules_seen != sorted(rules_seen, key=cm.ORDER.index):
                    violations.append(f"{plan}/{seed}: trace out of order {rules_seen}")
                if x.capped_by and x.awarded == x.requested:
                    violations.append(f"{plan}/{seed}: capped_by set but nothing was cut")
            for member, cyc in model.cycles.items():
                ceil = cyc.ceiling
                if cyc.total > ceil:
                    violations.append(f"{plan}/{seed}/{member}: cycle ceiling exceeded {cyc.total} > {ceil}")
                if cyc.by_category["PROCESS"] + cyc.by_category["OTHER"] > ceil * 45 // 100:
                    violations.append(f"{plan}/{seed}/{member}: non-closure above 45%")
                if cyc.pool > ceil * cm.POOL_PERCENT // 100 or cyc.participation > ceil * cm.PARTICIPATION_PERCENT // 100:
                    violations.append(f"{plan}/{seed}/{member}: community pool or participation limit exceeded")
                for cat, used in cyc.by_category.items():
                    if used > cyc.sub[cat]:
                        violations.append(f"{plan}/{seed}/{member}: {cat} sub-ceiling exceeded")
                if any(v > rules.MONTHLY_CEILING for v in cyc.by_month.values()) or any(v > rules.DAILY_CEILING_LOW_ASSURANCE for v in cyc.by_day.values()):
                    violations.append(f"{plan}/{seed}/{member}: daily or monthly ceiling exceeded")
            if any(v > cm.PAIR_COMMUNITY_BUDGET for v in model.pair_comm.values()):
                violations.append(f"{plan}/{seed}: community pair budget exceeded")
            once = {}
            for x in decs:
                if x.event.kind in cm.ONCE_PER_PAIR and x.awarded:
                    key = (cm.pair_of(x.event.member, x.event.counterparty), x.event.member)
                    once[key] = once.get(key, 0) + 1
            if any(v > 1 for v in once.values()):
                violations.append(f"{plan}/{seed}: a pair was rewarded twice for the first connection")
            for member, cyc in model.cycles.items():
                for (kind, period), n in cyc.counts.items():
                    lim = cm.MONTHLY_LIMIT.get(kind) or cm.QUARTERLY_LIMIT.get(kind)
                    if lim is not None and n > lim:
                        violations.append(f"{plan}/{seed}/{member}: {kind} rewarded {n} times in {period} (limit {lim})")
    check("INVARIANTS on 75 randomised streams (every plan): determinism; 0 <= awarded <= requested; cap trace in the documented order; cycle ceiling; non-closure <= 45%; "
          "pool <= 12%; participation <= 5%; every category ceiling; daily and monthly ceilings; community pair budget; pair-once; per-event frequency limits", violations == [], "; ".join(violations[:5]))

    # ------------------------------------------------------------------ the headroom guarantee, adversarially
    bad = []
    for seed in range(40):
        r = random.Random(1000 + seed)
        model = cm.Model(PLANS["Connect"])
        flood = []
        for i in range(500):
            kind = r.choice([k for k in cm.COMMUNITY_KINDS] + ["PROFILE_COMPLETED", "REFERRAL_ACCEPTED", "MEETING_COMPLETED", "BUSINESS_VERIFIED"])
            pts = 30 if kind == "REFERRAL_ACCEPTED" else 45 if kind == "MEETING_COMPLETED" else 75 if kind == "PROFILE_COMPLETED" else None
            flood.append(cm.Event(f"f{seed}-{i}", "FARMER", kind, T0 + timedelta(hours=r.randint(0, 24 * 28)), points=pts, counterparty=f"P{r.randint(0, 30)}" if kind not in ("PROFILE_COMPLETED", "BUSINESS_VERIFIED") else None, level=3 if kind in ("PROFILE_COMPLETED", "BUSINESS_VERIFIED") else 2))
        model.run(sorted(flood, key=lambda e: e.at))
        used = model.cycle("FARMER")
        # a verified 10L+ referrer reward arrives afterwards, in a LATER month (the monthly 3,000 limit is an existing v3 rule that is checked separately below)
        d = model.apply(cm.Event(f"big{seed}", "FARMER", "BUSINESS_CLOSED", at(3, 20), points=biggest, counterparty="CLIENT", level=4))
        if d.awarded != biggest:
            bad.append((seed, used.total, d.awarded, d.capped_by))
    check("HEADROOM: after a member has FILLED every non-closure category as hard as possible, a verified 10L+ closure reward (1,890) is still paid IN FULL on Connect", bad == [], str(bad[:3]))
    mm = cm.Model(PLANS["Connect"])
    mm.run([cm.Event(f"p{i}", "A", "REFERRAL_ACCEPTED", at(1, 2 + i % 20, 6 + i % 10), points=30, counterparty=f"Q{i}", level=1) for i in range(40)]
           + [cm.Event(f"hp{i}", "A", "NEED_HELP_CONFIRMED", at(1, 3 + i), counterparty=f"H{i}") for i in range(8)]
           + [cm.Event(f"np{i}", "A", "NEED_PUBLISHED", at(1, 12 + i)) for i in range(2)])
    used = mm.cycle("A").by_month["2027-01"]
    same_month = mm.apply(cm.Event("same-month-big", "A", "BUSINESS_CLOSED", at(1, 28), points=biggest, counterparty="CLIENT", level=4))
    check("EXISTING v3 INTERACTION (not caused by the proposal): when a member already holds more than 1,110 points in a month, the approved monthly 3,000 limit trims a 1,890 closure to the headroom and says MONTHLY_CEILING",
          used > 1110 and same_month.awarded == rules.MONTHLY_CEILING - used and same_month.capped_by == "MONTHLY_CEILING", f"used={used} awarded={same_month.awarded} by={same_month.capped_by}")

    # ------------------------------------------------------------------ the member scenarios quoted in the proposal (hypothetical)
    def scenario(events: list[cm.Event]) -> tuple[int, int]:
        ds = cm.Model(PLANS["Connect"]).run(events)
        return sum(x.requested for x in ds), sum(x.awarded for x in ds)
    s1 = [cm.Event(f"s1-{m}-{i}", "F", "CONNECTION_ACCEPTED", at(m, 3 + i), counterparty=f"c{m}{i}") for m in (1, 2, 3) for i in range(8)]
    s2 = [cm.Event(f"s2-{m}-{i}", "F", "NEED_PUBLISHED", at(m, 3 + 3 * i)) for m in (1, 2, 3) for i in range(3)] + [cm.Event("s2-close", "F", "NEED_CLOSED", at(3, 20), counterparty="x")]
    s3 = [cm.Event(f"s3-{m}-{i}", "F", "NEED_HELP_CONFIRMED", at(m, 2 + 3 * (i // 2), 6 + 4 * (i % 2)), counterparty=f"h{m}{i}") for m in (1, 2, 3) for i in range(8)] \
        + [cm.Event(f"s3-r{i}", "F", "NEED_RESOLVED", at(3, 4 + i), counterparty=f"r{i}") for i in range(5)] \
        + [e for k, mth in (("i1", 2), ("i2", 3)) for e in (cm.Event(f"s3-{k}", "F", "SUCCESSFUL_INTRODUCTION", at(mth, 25), counterparty=k), cm.Event(f"s3-{k}b", "F", "INTRODUCTION_MEETING", at(mth, 27), counterparty=k))]
    check("SCENARIO S1 (connector, hypothetical): requested 240, awarded 180", scenario(s1) == (240, 180), str(scenario(s1)))
    check("SCENARIO S2 (need publisher, hypothetical): requested 190, awarded 130", scenario(sorted(s2, key=lambda e: e.at)) == (190, 130), str(scenario(sorted(s2, key=lambda e: e.at))))
    check("SCENARIO S3 (consistent helper, hypothetical): requested 975, awarded 720 = the whole OTHER pool", scenario(sorted(s3, key=lambda e: e.at)) == (975, 720), str(scenario(sorted(s3, key=lambda e: e.at))))
    ring = [cm.Event(f"r-c{i}", "F", "CONNECTION_ACCEPTED", at(1, 3 + i), counterparty=f"R{i}") for i in range(4)] \
        + [cm.Event(f"r-n{m}{i}", "F", "NEED_PUBLISHED", at(m, 3 + 3 * i)) for m in (1, 2, 3) for i in range(3)] \
        + [cm.Event(f"r-h{i}{m}", "F", "NEED_HELP_CONFIRMED", at(m, 8 + i), counterparty=f"R{i}") for i in range(4) for m in (1, 2)] \
        + [cm.Event(f"r-r{i}", "F", "NEED_RESOLVED", at(3, 6 + i), counterparty=f"R{i}") for i in range(4)] \
        + [cm.Event(f"r-x{i}", "F", "NEED_CLOSED", at(3, 14 + i), counterparty=f"R{i}") for i in range(4)] \
        + [e for i in range(4) for e in (cm.Event(f"r-i{i}", "F", "SUCCESSFUL_INTRODUCTION", at(2, 20 + i), counterparty=f"I{i}"), cm.Event(f"r-i{i}b", "F", "INTRODUCTION_MEETING", at(2, 21 + i), counterparty=f"I{i}"))]
    s6 = scenario(sorted(ring, key=lambda e: e.at))
    check("SCENARIO S6 (a ring of 5 paying members fabricating every confirmation, hypothetical): requested 940, awarded 710, below the structural OTHER-pool bound of 720 (Rs72 on Connect)", s6 == (940, 710), str(s6))
    pm = cm.Model(PLANS["Connect"])
    pm.run([cm.Event(f"i{i}", "F", "SUCCESSFUL_INTRODUCTION", at(1, 3 + i), counterparty=f"I{i}") for i in range(3)])
    meet = [pm.apply(cm.Event(f"m{i}", "F", "INTRODUCTION_MEETING", at(1, 20 + i), counterparty=f"I{i}")) for i in range(3)]
    check("PREREQUISITE: the 45-point meeting bonus is paid only for an introduction that was itself rewarded (the 3rd introduction was cut by the quarterly limit of 2, so its meeting pays 0)",
          [x.awarded for x in meet] == [45, 45, 0] and meet[2].capped_by == "PREREQUISITE")

    # ------------------------------------------------------------------ reciprocal help
    mm = cm.Model(PLANS["Connect"])
    first = mm.apply(cm.Event("h1", "A", "NEED_HELP_CONFIRMED", at(1, 3), counterparty="B"))
    back = mm.apply(cm.Event("h2", "B", "NEED_HELP_CONFIRMED", at(1, 9), counterparty="A"))
    late = mm.apply(cm.Event("h3", "A", "NEED_HELP_CONFIRMED", at(3, 25), counterparty="B"))
    check("RECIPROCAL: help returned within 60 days pays 50% and says PAIR_RECIPROCAL; the same direction 80 days later is not reciprocal to the earlier one in that window (already returned, so 50% again only if B was paid within 60 days)",
          first.awarded == 25 and back.awarded == 12 and back.capped_by == "PAIR_RECIPROCAL" and late.awarded in (12, 25))
    mm = cm.Model(PLANS["Elite"])
    rr = [mm.apply(cm.Event(f"b{i}", "A" if i % 2 == 0 else "B", "NEED_HELP_CONFIRMED", at(1 + i // 4, 3 + i), counterparty="B" if i % 2 == 0 else "A")) for i in range(20)]
    check("PAIR BUDGET: two members exchanging confirmed help can never earn more than 150 points together in a quarter", max(mm.pair_comm.values()) <= 150, str(mm.pair_comm))

    pq = cm.Model(PLANS["Elite"])
    h = [pq.apply(cm.Event(f"q{i}", "A", "NEED_HELP_CONFIRMED", at(1, 2 + 10 * i), counterparty="B")) for i in range(3)]
    rs = [pq.apply(cm.Event(f"qr{i}", "A", "NEED_RESOLVED", at(1, 3 + 10 * i), counterparty="C")) for i in range(2)]
    check("PER-PAIR QUARTER LIMITS: the same helper is paid for at most 2 confirmed helps for the same poster in a quarter, and 1 resolution for the same poster",
          [x.awarded > 0 for x in h] == [True, True, False] and [x.awarded > 0 for x in rs] == [True, False], str([(x.awarded, x.capped_by) for x in h + rs]))

    failed = [n for ok, n in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
