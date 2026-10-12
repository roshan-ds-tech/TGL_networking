"""Growth Points economy model v2: corrected subscription terms.

Corrects the v1 assumption that every plan is a 3-month "season".  The real plans are

    Connect  Rs 3,000  3 months     Growth  Rs 5,000  6 months     Elite  Rs 10,000  12 months

Everything in docs/GROWTH_POINTS_ECONOMY_RECALCULATION.md and in the corrected
GROWTH_POINTS_FINAL_SPEC.md comes from this file.  It is deterministic (no randomness) and has no
dependencies:

    python3 economy_v2.py            # prints every table as Markdown
    python3 economy_v2.py --check    # asserts the engine reproduces the v1 numbers when given v1's inputs

Nothing here is application code and nothing here is a forecast: activity, plan mix and redemption
behaviour are ASSUMPTIONS carried over from v1 (and listed in section A of the output).
"""
from __future__ import annotations

import sys

# ----------------------------------------------------------------------------- inputs
PV = 0.10                      # rupees per point (10 points = Re 1)
CAP = 0.15                     # contractual redemption ceiling, share of the plan price, once per invoice
PLANS = {                      # name: (price in rupees, term in months)
    "Connect": (3_000, 3),
    "Growth": (5_000, 6),
    "Elite": (10_000, 12),
}
MIX = {"Connect": .55, "Growth": .35, "Elite": .10}     # ASSUMPTION (no subscription data exists)
N = 400                                                  # 10 categories x 40 slots (backend settings.slots_per_category)
SEG = {"Low": 240, "Average": 100, "High": 40, "Top": 20}
PROPENSITY = {"Low": .3, "Average": .7, "High": .9, "Top": 1.0}   # share who redeem at an invoice (v1 assumption)
POOL = [300, 750, 1500, 2100, 2700]    # closure points per deal by band: <25k, 25k-1L, 1L-5L, 5L-10L, 10L+
REF_SHARE = .70
BAND_MIX = {"Low": [.4, .4, .15, .05, 0], "Average": [.4, .4, .15, .05, 0],
            "High": [.2, .35, .30, .10, .05], "Top": [.10, .25, .35, .15, .15]}
QUALITY_BONUS_SHARE = .6
# Expected activity per member per 3 MONTHS (v1 "season").  Activity is assumed to be the same per month for every plan.
ACT = {
    "Low":     dict(acc_ref=.6, recv_acc=.3, contacted=.2, meet_ref=.1, meet_recv=.1, deals_ref=0,   deals_recv=0,   events=.5, profile=.6, intros=0, intro_meet=0,  need=.1, mentor=0, invite=0),
    "Average": dict(acc_ref=2,  recv_acc=2,  contacted=1.8, meet_ref=1.2, meet_recv=1.2, deals_ref=.25, deals_recv=.25, events=1.5, profile=.9, intros=.5, intro_meet=.1, need=.5, mentor=0, invite=.1),
    "High":    dict(acc_ref=6,  recv_acc=5,  contacted=4.5, meet_ref=4, meet_recv=4,   deals_ref=1.0, deals_recv=1.0, events=2.5, profile=1, intros=2, intro_meet=.5,  need=2, mentor=1, invite=.3),
    "Top":     dict(acc_ref=12, recv_acc=8,  contacted=8,   meet_ref=8, meet_recv=8,   deals_ref=3.0, deals_recv=3.0, events=3, profile=1, intros=5, intro_meet=2,   need=4, mentor=3, invite=1),
}
SUBSHARE = dict(process=.25, closure=.60, other=.20)   # sub-ceilings as a share of the cycle ceiling (v1: 1,500 / 3,600 / 1,200 of 6,000)
MONTHLY_CEILING = 3_000                                # points per calendar month (unchanged)


def r5(x: float) -> int:
    return int(round(x / 5.0) * 5)


def inr(x: float, d: int = 0) -> str:
    return f"₹{x:,.{d}f}"


def pts(x: float) -> str:
    return f"{int(round(x)):,}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def md(headers, rows, align: str | None = None) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(("---:" if (align and align[i] == "r") else "---") for i in range(len(headers))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ----------------------------------------------------------------------------- earning rules (the models under test)
def ceilings(model: str, plan: str) -> dict:
    """Cycle earning ceiling and its sub-ceilings (points per SUBSCRIPTION CYCLE) for an earning model."""
    price, term = PLANS[plan]
    q = term / 3                                        # number of 3-month quarters in the cycle
    if model == "v1":                                   # 6,000 per 3-month season, every plan assumed 3 months
        total = 6_000
    elif model == "A":                                  # 6,000 per subscription cycle, whatever its length
        total = 6_000
    elif model == "B":                                  # 6,000 per calendar quarter -> per cycle = 6,000 x quarters
        total = 6_000 * q
    elif model == "C":                                  # monthly ceiling only, no cycle ceiling
        total = MONTHLY_CEILING * term
    elif model == "T":                                  # 1,000 points per month of membership, same for every plan
        total = 1_000 * term
    elif model.startswith("D"):                         # ceiling = x% of the plan price, in points
        total = price * int(model[1:]) / 100 / PV
    else:
        raise ValueError(model)
    if model in ("A", "v1"):
        sub = dict(process=1_500, closure=3_600, other=1_200)
    elif model in ("B", "C"):
        sub = dict(process=1_500 * q, closure=3_600 * q, other=1_200 * q)
    else:
        sub = {k: v * total for k, v in SUBSHARE.items()}
    return dict(total=total, **sub)


def raw_quarter(seg: str, act_factor: float = 1.0) -> dict:
    """Points per member per 3 months before any ceiling (the v1 reward values; per-quarter count limits applied)."""
    a = {k: (v * act_factor if k != "profile" else v) for k, v in ACT[seg].items()}
    ref_acc = a["acc_ref"] * (30 + QUALITY_BONUS_SHARE * 15)
    recv = a["recv_acc"] * 15 + a["contacted"] * 15 + a["meet_recv"] * 60
    meet_ref = a["meet_ref"] * 45
    process = ref_acc + recv + meet_ref
    closure = 0.0
    for p, share in zip(POOL, BAND_MIX[seg]):
        closure += a["deals_ref"] * share * p * REF_SHARE + a["deals_recv"] * share * p * (1 - REF_SHARE)
    other = (min(a["events"], 3) * 45 + a["intros"] * 75 + a["intro_meet"] * 150 + min(a["need"], 4) * 60
             + min(a["mentor"], 3) * 90 + min(a["invite"], 3) * 225)
    return dict(process=process, closure=closure, other=other, profile=a["profile"] * 75)


def cycle_points(seg: str, plan: str, model: str, first: bool = True, act_factor: float = 1.0, term: int | None = None) -> dict:
    """Points earned in one subscription cycle after the sub-ceilings, the monthly ceiling and the cycle ceiling."""
    price, t = PLANS[plan]
    t = term or t
    c = ceilings(model, plan)
    rq = raw_quarter(seg, act_factor)
    k = t / 3
    process, closure = rq["process"] * k, rq["closure"] * k
    other = rq["other"] * k + (rq["profile"] if first else 0)            # profile completion is a one-off reward
    capped = min(process, c["process"]) + min(closure, c["closure"]) + min(other, c["other"])
    total = min(capped, c["total"], MONTHLY_CEILING * t)
    return dict(process=r5(process), closure=r5(closure), other=r5(other), raw=r5(process + closure + other), earned=r5(total), ceiling=c["total"])


def redeemable(points: float, plan: str) -> float:
    """Rupees redeemed on one invoice: the smaller of the points' value and the contractual ceiling."""
    return min(points * PV, PLANS[plan][0] * CAP)


def annual_member(seg: str, plan: str, model: str, act_factor: float = 1.0) -> dict:
    """One member for 12 months (profile completion counted once, in the first cycle).  Redeems at every renewal."""
    price, term = PLANS[plan]
    cycles = 12 // term
    earned = redeemed = 0.0
    first = None
    for i in range(cycles):
        e = cycle_points(seg, plan, model, first=(i == 0), act_factor=act_factor)["earned"]
        first = e if first is None else first
        earned += e
        redeemed += redeemable(e, plan)
    return dict(cycles=cycles, earned=earned, redeemed=redeemed, first=first, annual_price=price * cycles)


def network(model: str, act_factor: float = 1.0, mix: dict | None = None, propensity: dict | None = None,
            all_redeem: bool = False, term_override: dict | None = None) -> dict:
    """400-member network.  Costs per one invoice per member ("wave") and per 12 months."""
    mix = mix or MIX
    prop = {k: 1.0 for k in SEG} if all_redeem else (propensity or PROPENSITY)
    wave = annual = pts_year = 0.0
    revenue_wave = revenue_year = 0.0
    for plan, w in mix.items():
        price, term = PLANS[plan]
        revenue_wave += N * w * price
        revenue_year += N * w * price * (12 // term)
        for seg, n in SEG.items():
            members = n * w
            am = annual_member(seg, plan, model, act_factor)
            wave += members * prop[seg] * redeemable(am["first"], plan)
            annual += members * prop[seg] * am["redeemed"]
            pts_year += members * am["earned"]
    worst_wave = worst_year = 0.0
    for plan, w in mix.items():
        price, term = PLANS[plan]
        ceil_pts = ceilings(model, plan)["total"]
        per_invoice = redeemable(min(ceil_pts, MONTHLY_CEILING * term), plan)
        worst_wave += N * w * per_invoice
        worst_year += N * w * per_invoice * (12 // term)
    return dict(wave=wave, annual=annual, pts_year=pts_year, revenue_wave=revenue_wave, revenue_year=revenue_year,
                worst_wave=worst_wave, worst_year=worst_year, contractual_year=revenue_year * CAP)


# ----------------------------------------------------------------------------- expiry options (FIFO lots, month by month)
EXPIRY = {
    "A": "Fixed 6 months from earning",
    "B": "Fixed 12 months from earning",
    "C": "One subscription term from earning (3 / 6 / 12 months)",
    "D": "Valid at the renewal that closes the cycle it was earned in, plus a 30-day grace; then it expires",
}


def expiry_sim(per_cycle_points: float, plan: str, option: str, months: int = 48, redeems: bool = True) -> dict:
    """A member earns `per_cycle_points` evenly through every cycle and redeems at every renewal.
    Returns value earned / redeemed / expired / outstanding.  All values in rupees."""
    price, term = PLANS[plan]
    cap = CAP * price
    lots: list[list[float]] = []            # [earned_at, points, cycle]
    earned = redeemed = expired = 0.0
    outstanding = []
    peak = 0.0
    for m in range(1, months + 1):
        cycle = (m - 1) // term + 1
        lots.append([m - .5, per_cycle_points / term, cycle])
        earned += per_cycle_points / term * PV
        # expire (checked at the end of month m, i.e. time m)
        keep = []
        for lot in lots:
            age = m - lot[0]
            if option == "A":
                ok = age <= 6
            elif option == "B":
                ok = age <= 12
            elif option == "C":
                ok = age <= term
            else:                                   # D: until 1 month (grace) after its own cycle's renewal
                ok = m <= lot[2] * term + 1
            if ok:
                keep.append(lot)
            else:
                expired += lot[1] * PV
        lots = keep
        if m % term == 0:                           # renewal at the end of the cycle
            balance = sum(l[1] for l in lots)
            peak = max(peak, balance * PV)           # the highest the books get is the moment before redemption
            take = min(balance * PV, cap) if redeems else 0.0
            redeemed += take
            need = take / PV
            for lot in lots:                        # oldest first
                use = min(lot[1], need)
                lot[1] -= use
                need -= use
            lots = [l for l in lots if l[1] > 1e-9]
        val = sum(l[1] for l in lots) * PV
        outstanding.append(val)
        peak = max(peak, val)
    left = sum(l[1] for l in lots) * PV
    expired = earned - redeemed - left
    return dict(earned=earned, redeemed=redeemed, expired=expired, usable=redeemed / earned if earned else 0,
                avg_out=sum(outstanding) / len(outstanding), peak_out=peak)


# ----------------------------------------------------------------------------- tables
def sec_assumptions() -> str:
    rows = []
    for plan, (price, term) in PLANS.items():
        rows.append([plan, inr(price), f"{term} months", f"{12 // term}", inr(price * 12 // term), inr(price / term), f"{MIX[plan]:.0%}"])
    return md(["Plan", "Price per cycle", "Term", "Invoices per year", "Annualised price", "Price per month", "Assumed mix"], rows, "lrrrrrr")


def sec_cap() -> str:
    rows = []
    for plan, (price, term) in PLANS.items():
        cap = price * CAP
        rows.append([plan, inr(price), f"{term} months", inr(cap), pts(cap / PV), inr(price - cap), inr(cap * 12 / term), pct(CAP, 0)])
    return md(["Plan", "Price", "Term", "15% cap per invoice", "Points needed for the cap", "Member still pays (cap used)", "Cap per year if redeemed every invoice", "% of annualised price"], rows, "lrrrrrrr")


def sec_revenue() -> str:
    r = network("D12")
    rows = [
        ["Revenue of ONE invoice from each of the 400 members (a mixed-length wave, not a time period)", inr(r["revenue_wave"])],
        ["Annualised revenue (3-month members pay 4 times, 6-month twice, 12-month once)", inr(r["revenue_year"])],
        ["Normalised per quarter (annualised ÷ 4)", inr(r["revenue_year"] / 4)],
        ["Normalised per month", inr(r["revenue_year"] / 12)],
    ]
    by = []
    for plan, (price, term) in PLANS.items():
        members = N * MIX[plan]
        by.append([plan, f"{members:.0f}", inr(members * price), inr(members * price * 12 / term), f"{(members * price * 12 / term) / r['revenue_year']:.1%}"])
    return md(["", "Amount"], rows) + "\n\n" + md(["Plan", "Members", "Revenue per cycle", "Annualised revenue", "Share of annual revenue"], by, "lrrrr")


def sec_ceilings() -> str:
    rows = []
    for model, label in [("A", "A. 6,000 per subscription cycle"), ("B", "B. 6,000 per calendar quarter"), ("C", "C. Monthly ceiling only"),
                         ("T", "D. 1,000 points per month of membership"), ("D10", "D. 10% of plan price"), ("D12", "D. 12% of plan price"), ("D15", "D. 15% of plan price")]:
        cells = [label]
        for plan, (price, term) in PLANS.items():
            c = ceilings(model, plan)["total"]
            cells.append(f"{pts(c)} ({inr(c * PV)}, {pct(c * PV / price, 0)})")
        rows.append(cells)
    return md(["Earning model", "Connect 3 mo: points per cycle (worth, % of price)", "Growth 6 mo", "Elite 12 mo"], rows)


def sec_models() -> str:
    rows = []
    for model, label in [("A", "A. 6,000 per cycle"), ("B", "B. 6,000 per calendar quarter"), ("C", "C. Monthly only"),
                         ("T", "D. 1,000 per month of membership"), ("D10", "D. 10% of price"), ("D12", "D. 12% of price"), ("D15", "D. 15% of price")]:
        r = network(model)
        practical = []
        annual_pct = []
        surplus = []
        for plan, (price, term) in PLANS.items():
            ceil_pts = min(ceilings(model, plan)["total"], MONTHLY_CEILING * term)
            d = redeemable(ceil_pts, plan)
            practical.append(f"{inr(d)} ({pct(d / price, 0)})")
            annual_pct.append(pct(d * (12 // term) / (price * (12 // term)), 0))
            surplus.append(pts(max(0, ceil_pts - price * CAP / PV)))
        rows.append([label, " / ".join(practical), " / ".join(surplus), inr(r["worst_year"]), pct(r["worst_year"] / r["revenue_year"]),
                     inr(r["annual"]), pct(r["annual"] / r["revenue_year"])])
    return md(["Earning model", "Practical maximum per invoice (Connect / Growth / Elite)", "Points a maximiser earns beyond the cap, per cycle", "Worst case per year (400 members)", "% of annual revenue",
               "Expected cost per year", "% of annual revenue"], rows, "lrrrrrr")


def sec_plan_table(model: str = "D12") -> str:
    rows = []
    for plan, (price, term) in PLANS.items():
        c = ceilings(model, plan)["total"]
        practical = redeemable(min(c, MONTHLY_CEILING * term), plan)
        pts_needed = price * CAP / PV
        exp_e = sum(SEG[s] * cycle_points(s, plan, model, first=False)["earned"] for s in SEG) / N
        exp_r = sum(SEG[s] * PROPENSITY[s] * redeemable(cycle_points(s, plan, model, first=False)["earned"], plan) for s in SEG) / N
        rows.append([plan, inr(price), f"{term} months", inr(price * CAP), pts(pts_needed), pts(c), inr(practical), inr(price - practical), inr(price - price * CAP),
                     pts(exp_e), inr(exp_r)])
    return md(["Plan", "Price", "Term", "15% contractual cap", "Points needed for the cap", "Earning ceiling per cycle (points)", "Practical maximum discount",
               "Member still pays (practical)", "Member still pays (contractual floor)", "Expected points per cycle (avg member)", "Expected redemption per invoice (avg member)"], rows, "lrrrrrrrrrr")


def sec_liability_per_member(model: str = "D12") -> str:
    rows = []
    for plan, (price, term) in PLANS.items():
        c = ceilings(model, plan)["total"]
        d = redeemable(min(c, MONTHLY_CEILING * term), plan)
        rows.append([plan, inr(d), inr(d * 12 / term), pct(d / price), pct(d * (12 // term) / (price * (12 // term))), inr(d / term, 0), inr(price / term, 0)])
    return md(["Plan", "Worst case per invoice", "Worst case per year", "% of cycle price", "% of annual spend", "Worst case per member-month", "Price per member-month"], rows, "lrrrrrr")


def sec_scenarios(model: str = "D12") -> str:
    rows = []
    for label, seg in [("Low activity", "Low"), ("Average", "Average"), ("High", "High"), ("Top performer", "Top")]:
        for plan, (price, term) in PLANS.items():
            cp = cycle_points(seg, plan, model)
            am = annual_member(seg, plan, model)
            red = redeemable(cp["earned"], plan)
            rows.append([label, f"{plan} {inr(price)} / {term} mo", pts(cp["raw"]), pts(cp["earned"]) + (" (ceiling)" if cp["raw"] > cp["ceiling"] else ""), inr(cp["earned"] * PV), inr(red),
                         pct(red / price), inr(price - red), inr(am["redeemed"]), pct(am["redeemed"] / am["annual_price"])])
    for plan, (price, term) in PLANS.items():
        c = min(ceilings(model, plan)["total"], MONTHLY_CEILING * term)
        red = redeemable(c, plan)
        cycles = 12 // term
        rows.append(["Maximiser (hits every ceiling)", f"{plan} {inr(price)} / {term} mo", "-", pts(c) + " (ceiling)", inr(c * PV), inr(red), pct(red / price), inr(price - red),
                     inr(red * cycles), pct(red / price)])
    return md(["Scenario", "Plan / term", "Raw points per cycle", "Earned per cycle", "Worth", "Redeemed at the renewal", "Discount % of cycle price", "Member pays",
               "Redeemed per 12 months", "% of annual spend"], rows, "llrrrrrrrr")


def sec_scenarios_compare() -> str:
    rows = []
    for label, seg in [("Average", "Average"), ("High", "High"), ("Top performer", "Top")]:
        for model, mlabel in [("A", "A: 6,000/cycle"), ("B", "B: 6,000/quarter"), ("D12", "D12: 12% of price")]:
            cells = [label, mlabel]
            for plan, (price, term) in PLANS.items():
                am = annual_member(seg, plan, model)
                cells.append(f"{inr(am['redeemed'])} ({pct(am['redeemed'] / am['annual_price'])})")
            rows.append(cells)
    return md(["Member", "Earning model", "Connect 3 mo: redeemed per year (% of annual spend)", "Growth 6 mo", "Elite 12 mo"], rows)


def sec_network(model: str = "D12") -> str:
    rows = []
    totals = dict(n=0, e=0, red=0, wave=0, ann=0)
    for seg, n in SEG.items():
        wave = ann = e = 0.0
        for plan, w in MIX.items():
            am = annual_member(seg, plan, model)
            wave += n * w * PROPENSITY[seg] * redeemable(am["first"], plan)
            ann += n * w * PROPENSITY[seg] * am["redeemed"]
            e += n * w * am["earned"]
        rows.append([seg, n, f"{PROPENSITY[seg]:.0%}", pts(e / n), inr(wave), inr(ann)])
    r = network(model)
    rows.append(["**Total**", N, "", pts(r["pts_year"] / N), f"**{inr(r['wave'])}**", f"**{inr(r['annual'])}**"])
    return md(["Member type", "Members", "Redeem at an invoice", "Points earned per member per year", "Expected cost: one invoice from each (wave)", "Expected cost per year"], rows, "lrrrrr")


def sec_plan_network(model: str = "D12") -> str:
    rows = []
    for plan, (price, term) in PLANS.items():
        members = N * MIX[plan]
        exp = sum(members * PROPENSITY[seg] * (SEG[seg] / N) * annual_member(seg, plan, model)["redeemed"] for seg in SEG)
        worst = members * redeemable(min(ceilings(model, plan)["total"], MONTHLY_CEILING * term), plan) * (12 // term)
        rev = members * price * (12 // term)
        rows.append([plan, f"{members:.0f}", inr(rev), inr(exp), pct(exp / rev), inr(worst), pct(worst / rev)])
    tot_rev = sum(N * MIX[p] * PLANS[p][0] * (12 // PLANS[p][1]) for p in PLANS)
    r = network(model)
    rows.append(["**Total**", N, inr(tot_rev), f"**{inr(r['annual'])}**", pct(r["annual"] / tot_rev), f"**{inr(r['worst_year'])}**", pct(r["worst_year"] / tot_rev)])
    return md(["Plan", "Members", "Annual revenue", "Expected cost per year", "% of that revenue", "Worst case per year", "% of that revenue"], rows, "lrrrrrr")


def sec_books(model: str = "D12", option: str = "D") -> str:
    """Points outstanding on the books (value) for the whole network, including members who never redeem."""
    rows = []
    tot_avg = tot_peak = 0.0
    for plan, (price, term) in PLANS.items():
        avg = peak = 0.0
        for seg, n in SEG.items():
            e = cycle_points(seg, plan, model, first=False)["earned"]
            sim = expiry_sim(e, plan, option)                      # a member who redeems at every renewal
            idle = expiry_sim(e, plan, option, redeems=False)       # a member who never redeems
            members = N * MIX[plan] * n / N
            q = PROPENSITY[seg]
            avg += members * (q * sim["avg_out"] + (1 - q) * idle["avg_out"])
            peak += members * (q * sim["peak_out"] + (1 - q) * idle["peak_out"])
        tot_avg += avg
        tot_peak += peak
        rows.append([plan, inr(avg), inr(peak)])
    rows.append(["**Total**", f"**{inr(tot_avg)}**", f"**{inr(tot_peak)}**"])
    return md(["Plan", "Average value of unexpired points on the books", "Highest (every member just before their renewal; upper bound)"], rows, "lrr")


def sec_books_all(model: str = "D12") -> str:
    """Whole-network value of unexpired points under each expiry option (members who never redeem included),
    plus the share of the value members earn that they can actually spend."""
    rows = []
    for opt in "ABCD":
        avg = peak = earned = redeemed = 0.0
        for plan in PLANS:
            for seg, n in SEG.items():
                e = cycle_points(seg, plan, model, first=False)["earned"]
                members = N * MIX[plan] * n / N
                q = PROPENSITY[seg]
                a, b = expiry_sim(e, plan, opt), expiry_sim(e, plan, opt, redeems=False)
                avg += members * (q * a["avg_out"] + (1 - q) * b["avg_out"])
                peak += members * (q * a["peak_out"] + (1 - q) * b["peak_out"])
                earned += members * q * a["earned"]
                redeemed += members * q * a["redeemed"]
        rows.append([f"{opt}. {EXPIRY[opt]}", inr(avg), inr(peak), pct(redeemed / earned, 0)])
    return md(["Expiry option", "Average value of unexpired points (400 members)", "Highest (upper bound)", "Share of the points of members who redeem that they can spend"], rows, "lrrr")


def sec_sensitivity(model: str = "D12") -> str:
    base = network(model)
    rows = [["As assumed", inr(base["annual"]), pct(base["annual"] / base["revenue_year"]), inr(base["worst_year"]), pct(base["worst_year"] / base["revenue_year"])]]

    def add(label, **kw):
        r = network(model, **kw)
        rows.append([label, inr(r["annual"]), pct(r["annual"] / r["revenue_year"]), inr(r["worst_year"]), pct(r["worst_year"] / r["revenue_year"])])
    for f in (.5, 2, 3):
        add(f"Activity ×{f:g}", act_factor=f)
    add("Every member redeems at every invoice", all_redeem=True)
    add("Every member redeems, activity ×3", all_redeem=True, act_factor=3)
    for plan in PLANS:
        add(f"Every member on {plan}", mix={plan: 1.0})
    return md(["Change", "Expected cost per year", "% of annual revenue", "Worst case per year", "% of annual revenue"], rows, "lrrrr")


def sec_commitment() -> str:
    """Longer-plan members might be more active.  Extra activity multiplier on Growth / Elite only."""
    rows = []
    for g, e_ in [(1, 1), (1.25, 1.5), (1.5, 2), (2, 3)]:
        wave = annual = 0.0
        rev = network("D12")["revenue_year"]
        for plan, w in MIX.items():
            f = {"Connect": 1, "Growth": g, "Elite": e_}[plan]
            for seg, n in SEG.items():
                am = annual_member(seg, plan, "D12", f)
                annual += n * w * PROPENSITY[seg] * am["redeemed"]
        rows.append([f"Growth ×{g:g}, Elite ×{e_:g}", inr(annual), pct(annual / rev)])
    return md(["Activity of longer-plan members relative to Connect", "Expected cost per year", "% of annual revenue"], rows, "lrr")


def sec_expiry() -> str:
    out = []
    profiles = [("Average member (D12 earning)", "Average", "D12"), ("Top performer (D12 earning)", "Top", "D12"), ("Maximiser (D12 ceiling)", None, "D12"), ("Maximiser under Model B (6,000 per quarter)", None, "B")]
    for label, seg, model in profiles:
        rows = []
        for plan, (price, term) in PLANS.items():
            if seg:
                e = cycle_points(seg, plan, model, first=False)["earned"]
            else:
                e = min(ceilings(model, plan)["total"], MONTHLY_CEILING * term)
            for opt in "ABCD":
                s = expiry_sim(e, plan, opt)
                rows.append([f"{plan} {inr(price)} / {term} mo", f"{opt}", pts(e), pct(s["usable"], 0), inr(s["earned"] / 4), inr(s["redeemed"] / 4), inr(s["expired"] / 4), inr(s["avg_out"]), inr(s["peak_out"])])
        out.append(f"**{label}**\n\n" + md(["Plan", "Expiry option", "Points earned per cycle", "Share of earned value that can be spent", "Earned per year", "Redeemed per year", "Lost to expiry per year",
                                              "Average points on the books", "Peak points on the books"], rows, "llrrrrrrr"))
    return "\n\n".join(out)


def sec_expiry_matrix() -> str:
    rows = []
    for opt in "ABCD":
        a = {plan: expiry_sim(cycle_points("Average", plan, "D12", first=False)["earned"], plan, opt) for plan in PLANS}
        t = {plan: expiry_sim(min(ceilings("B", plan)["total"], MONTHLY_CEILING * PLANS[plan][1]), plan, opt) for plan in PLANS}
        rows.append([f"{opt}. {EXPIRY[opt]}",
                     " / ".join(pct(a[p]["usable"], 0) for p in PLANS),
                     " / ".join(pct(t[p]["usable"], 0) for p in PLANS),
                     " / ".join(inr(t[p]["avg_out"]) for p in PLANS),
                     " / ".join(inr(t[p]["peak_out"]) for p in PLANS)])
    return md(["Expiry option", "Average member: share of earned value spendable (Connect / Growth / Elite)", "Maximiser under Model B: share spendable",
               "Maximiser under Model B: average points on the books", "Maximiser under Model B: peak points on the books"], rows)


def sec_closure() -> str:
    rows = []
    for plan, (price, term) in PLANS.items():
        c = ceilings("D12", plan)
        one = 1890 + 30 + 15 + 45
        rows.append([plan, pts(c["total"]), pts(c["closure"]), pts(c["process"]), pts(c["other"]), f"{c['closure'] / 1890:.1f}", pts(c["closure"] * 12 / term), inr(c["closure"] * PV * 12 / term),
                     pct(c["closure"] * PV * 12 / term / (price * 12 / term))])
    old = [["v1: every plan, per assumed 3-month season", "6,000", "3,600", "1,500", "1,200", f"{3600 / 1890:.1f}", "-", "-", "-"]]
    return md(["Plan", "Cycle ceiling", "Closed-business ceiling per cycle (60%)", "Referral-process ceiling (25%)", "Other (20%)", "Verified ₹10L+ closures (referrer share 1,890) that fit",
               "Closed-business points per year", "Worth per year", "% of annual spend"], old + rows, "lrrrrrrrr")


def sec_v1_compare() -> str:
    v1 = network("v1")
    new = network("D12")
    # v1 as published: every plan treated as one 3-month season
    rows = [
        ["Term of every plan", "3 months", "3 / 6 / 12 months"],
        ["Revenue base", "₹1,760,000 'per season'", f"{inr(new['revenue_wave'])} per invoice wave; {inr(new['revenue_year'])} per year"],
        ["Earning ceiling", "6,000 points per season for every plan", "12% of the plan price per cycle: 3,600 / 6,000 / 12,000 points"],
        ["Practical maximum discount", "₹450 / ₹600 / ₹600", "₹360 / ₹600 / ₹1,200"],
        ["Expected cost", "₹25,386 per 'season' (1.4%)", f"{inr(new['annual'])} per year ({pct(new['annual'] / new['revenue_year'])}); {inr(new['wave'])} per invoice wave"],
        ["Worst case", "₹207,000 per 'season' (11.8%)", f"{inr(new['worst_year'])} per year ({pct(new['worst_year'] / new['revenue_year'])})"],
    ]
    return md(["", "v1 (wrong term assumption)", "v2 (corrected)"], rows)


def sec_v1_reproduction() -> str:
    """Prove the v2 engine is the v1 engine: with v1's inputs it returns v1's published figures."""
    saved = dict(PLANS)
    try:
        PLANS.update({"Connect": (3_000, 3), "Growth": (5_000, 3), "Elite": (10_000, 3)})   # v1 treated every plan as 3 months
        wave = 0.0
        for plan, w in MIX.items():
            for seg, n in SEG.items():
                wave += n * w * PROPENSITY[seg] * redeemable(cycle_points(seg, plan, "v1")["earned"], plan)
        worst = sum(N * w * redeemable(6_000, p) for p, w in MIX.items())
    finally:
        PLANS.update(saved)
    return f"v1 inputs through the v2 engine: expected {inr(wave)} per 'season', worst case {inr(worst)} (published v1: ₹25,386 and ₹207,000)", wave, worst


def main() -> None:
    check = "--check" in sys.argv
    text, wave, worst = sec_v1_reproduction()
    if check:
        assert round(wave) == 25_386, wave
        assert round(worst) == 207_000, worst
        r = network("D12")
        assert round(r["worst_year"]) == 532_800, r["worst_year"]
        assert round(r["revenue_year"]) == 4_440_000, r["revenue_year"]
        print("ok:", text)
        return
    sections = [
        ("A. Inputs: plans, terms and assumptions", sec_assumptions()),
        ("B. The 15% contractual cap, recalculated", sec_cap()),
        ("C. Revenue: per invoice wave versus annualised", sec_revenue()),
        ("D. Cycle earning ceilings under each model", sec_ceilings()),
        ("E. Earning models compared (400 members)", sec_models()),
        ("F. All three plans, recommended model (D12)", sec_plan_table("D12")),
        ("G. Worst-case liability per member, recommended model", sec_liability_per_member("D12")),
        ("H. Member scenarios, recommended model", sec_scenarios("D12")),
        ("I. Annual redemption by earning model", sec_scenarios_compare()),
        ("J. Expiry options", sec_expiry_matrix()),
        ("K. Expiry options in detail", sec_expiry()),
        ("L. 400-member simulation, recommended model", sec_network("D12")),
        ("L2. The same, by plan", sec_plan_network("D12")),
        ("L3. Points on the books under each expiry option", sec_books_all("D12")),
        ("M. Sensitivity, recommended model", sec_sensitivity("D12")),
        ("N. Do longer-plan members behave differently?", sec_commitment()),
        ("O. Closed-business ceiling", sec_closure()),
        ("P. Old model versus corrected model", sec_v1_compare()),
        ("Q. Engine check", text),
    ]
    for title, body in sections:
        print(f"### {title}\n\n{body}\n")


if __name__ == "__main__":
    main()
