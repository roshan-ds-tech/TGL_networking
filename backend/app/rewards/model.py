"""The 400-member economic model (docs/GROWTH_POINTS_ECONOMY_RECALCULATION.md), reproducible inside the application.

Same assumptions, same rules (read from rules.py, so a rule change moves the model with it), integer paise where money is
involved. `test_phase1.py` checks it against the reference script docs/growth_points_model/economy_v2.py: expected cost
Rs 83,006 a year and worst case Rs 532,800 a year on annual revenue of Rs 4,440,000.

These are MODELLED numbers: assumptions (activity, plan mix, who redeems), not data. The admin economics view shows them
beside the ACTUAL shadow data so the two can be compared; they are never mixed.
"""
from __future__ import annotations

from . import rules

CAPACITY = 400                                   # 10 categories x 40 slots (settings.slots_per_category)
PLANS = {"Connect": (3_000, 3), "Growth": (5_000, 6), "Elite": (10_000, 12)}        # rupees, months: the canonical terms
MIX = {"Connect": .55, "Growth": .35, "Elite": .10}
SEGMENTS = {"Low": 240, "Average": 100, "High": 40, "Top": 20}
PROPENSITY = {"Low": .3, "Average": .7, "High": .9, "Top": 1.0}                      # share who redeem at an invoice
BAND_ORDER = ["UNDER_25K", "25K_1L", "1L_5L", "5L_10L", "10L_PLUS"]
BAND_MIX = {"Low": [.4, .4, .15, .05, 0], "Average": [.4, .4, .15, .05, 0], "High": [.2, .35, .30, .10, .05], "Top": [.10, .25, .35, .15, .15]}
QUALITY_BONUS_SHARE = .6
# activity per member per 3 months (assumed identical per month on every plan)
ACTIVITY = {
    "Low":     dict(acc_ref=.6, recv_acc=.3, contacted=.2, meet_ref=.1, meet_recv=.1, deals_ref=0,   deals_recv=0,   events=.5, profile=.6, intros=0, intro_meet=0,  need=.1, mentor=0, invite=0),
    "Average": dict(acc_ref=2,  recv_acc=2,  contacted=1.8, meet_ref=1.2, meet_recv=1.2, deals_ref=.25, deals_recv=.25, events=1.5, profile=.9, intros=.5, intro_meet=.1, need=.5, mentor=0, invite=.1),
    "High":    dict(acc_ref=6,  recv_acc=5,  contacted=4.5, meet_ref=4, meet_recv=4,   deals_ref=1.0, deals_recv=1.0, events=2.5, profile=1, intros=2, intro_meet=.5,  need=2, mentor=1, invite=.3),
    "Top":     dict(acc_ref=12, recv_acc=8,  contacted=8,   meet_ref=8, meet_recv=8,   deals_ref=3.0, deals_recv=3.0, events=3, profile=1, intros=5, intro_meet=2,   need=4, mentor=3, invite=1),
}


def _r5(x: float) -> int:
    return int(round(x / 5.0) * 5)


def _raw_quarter(seg: str, act_factor: float = 1.0) -> dict:
    a = {k: (v * act_factor if k != "profile" else v) for k, v in ACTIVITY[seg].items()}
    acc, rec, mtg = rules.EVENTS["REFERRAL_ACCEPTED"], rules.EVENTS["PROSPECT_CONTACTED"], rules.EVENTS["MEETING_COMPLETED"]
    process = (a["acc_ref"] * (acc["referrer"] + QUALITY_BONUS_SHARE * acc["referrer_bonus"]) + a["recv_acc"] * acc["recipient"]
               + a["contacted"] * rec["recipient"] + a["meet_recv"] * mtg["recipient"] + a["meet_ref"] * mtg["referrer"])
    closure = 0.0
    for band, share in zip(BAND_ORDER, BAND_MIX[seg]):
        pool = rules.CLOSURE_POOL[band]
        closure += a["deals_ref"] * share * pool * rules.REFERRER_SHARE_PERCENT / 100 + a["deals_recv"] * share * pool * (100 - rules.REFERRER_SHARE_PERCENT) / 100
    # the other approved events (some are future features) as the reference model counts them
    other = (min(a["events"], 3) * 45 + a["intros"] * 75 + a["intro_meet"] * 150 + min(a["need"], 4) * 60
             + min(a["mentor"], 3) * 90 + min(a["invite"], 3) * 225)
    return dict(process=process, closure=closure, other=other, profile=a["profile"] * rules.EVENTS["PROFILE_COMPLETED"]["member"])


def cycle_points(seg: str, plan: str, first: bool = True, act_factor: float = 1.0) -> int:
    price, months = PLANS[plan]
    price_minor = price * 100
    caps = rules.category_ceilings(price_minor)
    total_cap = rules.cycle_ceiling_points(price_minor)
    k = months / 3
    rq = _raw_quarter(seg, act_factor)
    process, closure = rq["process"] * k, rq["closure"] * k
    other = rq["other"] * k + (rq["profile"] if first else 0)
    capped = min(process, caps["PROCESS"]) + min(closure, caps["CLOSURE"]) + min(other, caps["OTHER"])
    return _r5(min(capped, total_cap, rules.MONTHLY_CEILING * months))


def redeemable_paise(points: int, plan: str) -> int:
    price_minor = PLANS[plan][0] * 100
    return min(rules.points_to_paise(points), rules.redemption_cap_paise(price_minor))


def annual_member(seg: str, plan: str, act_factor: float = 1.0) -> dict:
    months = PLANS[plan][1]
    cycles_per_year = 12 // months
    earned = redeemed = 0
    first = None
    for i in range(cycles_per_year):
        e = cycle_points(seg, plan, first=(i == 0), act_factor=act_factor)
        first = e if first is None else first
        earned += e
        redeemed += redeemable_paise(e, plan)
    return dict(earned=earned, redeemed_paise=redeemed, first=first, annual_price_paise=PLANS[plan][0] * 100 * cycles_per_year)


def network(act_factor: float = 1.0, all_redeem: bool = False) -> dict:
    """Expected and worst-case annual cost (paise) for the 400-member network, plus annual revenue."""
    prop = {k: 1.0 for k in SEGMENTS} if all_redeem else PROPENSITY
    expected = 0.0
    points_year = 0.0
    revenue = 0
    worst = 0
    for plan, w in MIX.items():
        price, months = PLANS[plan]
        n_plan = CAPACITY * w
        revenue += int(round(n_plan * price * 100 * (12 // months)))
        for seg, n in SEGMENTS.items():
            am = annual_member(seg, plan, act_factor)
            members = n * w
            expected += members * prop[seg] * am["redeemed_paise"]
            points_year += members * am["earned"]
        ceiling = min(rules.cycle_ceiling_points(price * 100), rules.MONTHLY_CEILING * months)
        worst += n_plan * redeemable_paise(ceiling, plan) * (12 // months)
    return dict(expected_annual_paise=expected, worst_annual_paise=worst, revenue_annual_paise=revenue, points_issued_year=points_year,
                contractual_bound_annual_paise=revenue * rules.REDEMPTION_CAP_PERMILLE // 1000)


def modelled_conversion() -> dict:
    """The model's funnel: of accepted referrals, how many reach a meeting; of meetings, how many reach a verified closed deal."""
    acc = sum(n * ACTIVITY[seg]["acc_ref"] for seg, n in SEGMENTS.items())
    mtg = sum(n * ACTIVITY[seg]["meet_ref"] for seg, n in SEGMENTS.items())
    deals = sum(n * ACTIVITY[seg]["deals_ref"] for seg, n in SEGMENTS.items())
    return {"accepted_to_meeting": round(mtg / acc, 3), "meeting_to_verified_deal": round(deals / mtg, 3)}


def modelled_activity_per_member_month() -> dict:
    """The model's average member: accepted referrals given, meetings and verified closed deals per month (the referrer side, so each
    event is counted once). Used to compare the model with what the observation period actually records."""
    total = sum(SEGMENTS.values())
    def avg(key: str) -> float:
        return sum(n * ACTIVITY[seg][key] for seg, n in SEGMENTS.items()) / total / 3
    return {"accepted_referrals": round(avg("acc_ref"), 3), "meetings": round(avg("meet_ref"), 3), "verified_closed_deals": round(avg("deals_ref"), 3)}
