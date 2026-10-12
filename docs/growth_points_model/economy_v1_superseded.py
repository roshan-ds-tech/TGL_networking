"""SUPERSEDED (kept for traceability). Growth Points economy model v1.

This model assumed every plan is a 3-month "season" at its list price. That was wrong: the plans are
3 / 6 / 12 months. Use economy_v2.py. The numbers in GROWTH_POINTS_ECONOMY_REPORT.md came from this file.
"""
from __future__ import annotations

PV = 0.10                       # recommended rupees per point
PRICES = [3000, 5000, 10000]
MIX = {3000: .55, 5000: .35, 10000: .10}   # ASSUMPTION: no subscription data exists yet
N = 400                         # 10 categories x 40 slots (backend settings.slots_per_category)
SEG = {'Low': 240, 'Average': 100, 'High': 40, 'Top': 20}
BANDS = [('Under ₹25k', 15_000), ('₹25k–₹1L', 60_000), ('₹1L–₹5L', 250_000), ('₹5L–₹10L', 700_000), ('₹10L+', 1_500_000)]
POOL = [300, 750, 1500, 2100, 2700]       # total closure points per deal, by band (model B scale)
REF_SHARE = 0.70
BAND_MIX = {'Low': [.4, .4, .15, .05, 0], 'Average': [.4, .4, .15, .05, 0],
            'High': [.2, .35, .30, .10, .05], 'Top': [.10, .25, .35, .15, .15]}
QUALITY_BONUS_SHARE = 0.6       # share of accepted referrals that are DIRECT_INTRO / MEETING_ARRANGED

MODELS = {
    'A': dict(name='Very conservative', scale=.5, cap=.10, floor=.90, ceil=3000, month=1500, day=250, expiry=3),
    'B': dict(name='Balanced',          scale=1.0, cap=.15, floor=.85, ceil=6000, month=3000, day=500, expiry=6),
    'C': dict(name='High reward',       scale=1.5, cap=.20, floor=.80, ceil=10000, month=5000, day=800, expiry=12),
}
# Expected activity per member per 3-month season (assumptions, stated in the report)
ACT = {
 'Low':     dict(acc_ref=.6, recv_acc=.3, contacted=.2, meet_ref=.1, meet_recv=.1, deals_ref=0,   deals_recv=0,   events=.5, profile=.6, intros=0, intro_meet=0, need=.1, mentor=0, invite=0),
 'Average': dict(acc_ref=2,  recv_acc=2,  contacted=1.8, meet_ref=1.2, meet_recv=1.2, deals_ref=.25, deals_recv=.25, events=1.5, profile=.9, intros=.5, intro_meet=.1, need=.5, mentor=0, invite=.1),
 'High':    dict(acc_ref=6,  recv_acc=5,  contacted=4.5, meet_ref=4, meet_recv=4,   deals_ref=1.0, deals_recv=1.0, events=2.5, profile=1, intros=2, intro_meet=.5, need=2, mentor=1, invite=.3),
 'Top':     dict(acc_ref=12, recv_acc=8,  contacted=8,   meet_ref=8, meet_recv=8,   deals_ref=3.0, deals_recv=3.0, events=3, profile=1, intros=5, intro_meet=2, need=4, mentor=3, invite=1),
}
PROPENSITY = {'Low': .3, 'Average': .7, 'High': .9, 'Top': 1.0}   # share who actually redeem


def r5(x):
    return int(round(x / 5.0) * 5)


def member_points(seg: str, m: dict, a: dict | None = None):
    s, a = m['scale'], a or ACT[seg]
    ref_acc = a['acc_ref'] * (30 + QUALITY_BONUS_SHARE * 15) * s
    recv = a['recv_acc'] * 15 * s + a['contacted'] * 15 * s + a['meet_recv'] * 60 * s
    meet_ref = a['meet_ref'] * 45 * s
    process = ref_acc + recv + meet_ref
    closure = 0.0
    for p, share in zip(POOL, BAND_MIX[seg]):
        closure += a['deals_ref'] * share * p * REF_SHARE * s + a['deals_recv'] * share * p * (1 - REF_SHARE) * s
    other = (a['profile'] * 75 + min(a['events'], 3) * 45 + a['intros'] * 75 + a['intro_meet'] * 150
             + min(a['need'], 4) * 60 + min(a['mentor'], 3) * 90 + min(a['invite'], 3) * 225) * s
    capped = min(process, .25 * m['ceil']) + min(closure, .60 * m['ceil']) + min(other, .20 * m['ceil'])
    total = min(capped, m['ceil'])
    return dict(process=r5(process), closure=r5(closure), other=r5(other), raw=r5(process + closure + other), earned=r5(total))


def tier_view(points: int, price: int, m: dict):
    value = points * PV
    cap_amt = price * m['cap']
    redeem = min(value, cap_amt)
    return dict(value=value, cap=cap_amt, redeem=redeem, pays=price - redeem, pct=redeem / price)


def revenue():
    return N * sum(p * w for p, w in MIX.items())


def simulate(mk: str):
    m = MODELS[mk]
    rows, tot_pts, exp_cost = {}, 0, 0.0
    for seg, n in SEG.items():
        mp = member_points(seg, m)
        avg_cost = sum(w * tier_view(mp['earned'], p, m)['redeem'] for p, w in MIX.items())
        rows[seg] = dict(n=n, **mp, avg_redeem=avg_cost)
        tot_pts += n * mp['earned']
        exp_cost += n * PROPENSITY[seg] * avg_cost
    # worst cases
    full = sum(w * min(m['ceil'] * PV, p * m['cap']) for p, w in MIX.items())
    return dict(rows=rows, pts=tot_pts, value=tot_pts * PV, expected=exp_cost, worst_all=N * full,
                theoretical=revenue() * m['cap'])


if __name__ == '__main__':
    for k in MODELS:
        r = simulate(k)
        print(k, MODELS[k]['name'], 'pts', r['pts'], 'value', round(r['value']), 'expected', round(r['expected']), 'worst', round(r['worst_all']), 'theory', round(r['theoretical']), 'rev', round(revenue()))
        for seg, v in r['rows'].items():
            print('   ', seg, {kk: vv for kk, vv in v.items() if kk != 'n'})
