# TGL Growth Points: Corrected Economic Model (v3)

**Status:** business recalculation for management sign-off. **No code, database migration, API or frontend was changed, and no Growth Points exist.** Every number below is produced by `docs/growth_points_model/economy_v2.py` (deterministic, no dependencies: `python3 economy_v2.py`; `--check` proves the engine reproduces the v1 numbers when given v1's inputs). The normative rules are in `GROWTH_POINTS_FINAL_SPEC.md` (v3); this document holds the working.

**The correction.** The previous reports treated Connect, Growth and Elite as three prices for the same 3-month "season". The real terms are:

| Plan | Price | Term |
|---|---:|---|
| Connect | ₹3,000 | **3 months** |
| Growth | ₹5,000 | **6 months** |
| Elite | ₹10,000 | **12 months** |

This changes more than the rupee figures. It changes what a "season" is, how often a member can redeem, whether points can expire before they can be used, and what revenue the 400-member simulation should be compared with.

---

## 1. What was wrong in v1

1. **Revenue was overstated.** v1 divided every cost by "₹1,760,000 per season" and called the result a percentage of revenue. That is one invoice from each of 400 members, but the invoices cover 3, 6 and 12 months. Annualised, the v1 reading implies a Growth member pays ₹20,000 a year and an Elite member ₹40,000; the real figures are ₹10,000 and ₹10,000. Real annual revenue on the assumed mix is **₹4,440,000**, not the ₹7,040,000 that four v1 "seasons" would imply.
2. **The earning ceiling was the same for every plan** (6,000 points a season). On a 12-month plan that is 6,000 points for a whole year (6% of the price), against 15% on the 3-month plan.
3. **Expiry of 6 months from earning** destroys half of what a 12-month member earns before their only renewal.
4. **"Per season" limits** (the closed-business ceiling, the pair budget, frequency limits) had no meaning for a member whose paid term is 6 or 12 months.
5. **Practical limits of ₹450 / ₹600 / ₹600** were an accident of one flat ceiling, not a design.

The engine check (`--check`) shows the corrected code, fed v1's inputs, returns exactly v1's ₹25,386 expected and ₹207,000 worst case, so the differences below come from the corrected terms and rules, not from a different calculator.

## 2. Terms and revenue, normalised

| Plan | Price per cycle | Term | Invoices per year | Annualised price | Price per month | Assumed mix |
|---|---:|---:|---:|---:|---:|---:|
| Connect | ₹3,000 | 3 months | 4 | ₹12,000 | ₹1,000 | 55% |
| Growth | ₹5,000 | 6 months | 2 | ₹10,000 | ₹833 | 35% |
| Elite | ₹10,000 | 12 months | 1 | ₹10,000 | ₹833 | 10% |

|  | Amount |
|---|---|
| Revenue of ONE invoice from each of the 400 members (a mixed-length wave, not a time period) | ₹1,760,000 |
| Annualised revenue (3-month members pay 4 times, 6-month twice, 12-month once) | ₹4,440,000 |
| Normalised per quarter (annualised ÷ 4) | ₹1,110,000 |
| Normalised per month | ₹370,000 |

| Plan | Members | Revenue per cycle | Annualised revenue | Share of annual revenue |
|---|---:|---:|---:|---:|
| Connect | 220 | ₹660,000 | ₹2,640,000 | 59.5% |
| Growth | 140 | ₹700,000 | ₹1,400,000 | 31.5% |
| Elite | 40 | ₹400,000 | ₹400,000 | 9.0% |

**How to read cost percentages from now on.** Cost is shown (a) **per year**, against annualised revenue, and (b) where useful **per invoice wave**, which is only a count of one renewal per member and is *not* a time period. Never compare a 3-month ₹3,000 invoice with a 12-month ₹10,000 invoice as if they covered the same time.

Per month of membership the plans cost ₹1,000 (Connect), ₹833 (Growth) and ₹833 (Elite): longer terms are already priced as a discount.

## 3. The 15% cap, recalculated

1 point = ₹0.10. The cap is 15% of the price of the plan being purchased, once per invoice.

| Plan | Price | Term | 15% cap per invoice | Points needed for the cap | Member still pays (cap used) | Cap per year if redeemed every invoice | % of annualised price |
|---|---:|---:|---:|---:|---:|---:|---:|
| Connect | ₹3,000 | 3 months | ₹450 | 4,500 | ₹2,550 | ₹1,800 | 15% |
| Growth | ₹5,000 | 6 months | ₹750 | 7,500 | ₹4,250 | ₹1,500 | 15% |
| Elite | ₹10,000 | 12 months | ₹1,500 | 15,000 | ₹8,500 | ₹1,500 | 15% |

Annualised, the 15% cap is 15% of annual spend on **every** plan (Connect ₹1,800 of ₹12,000; Growth and Elite ₹1,500 of ₹10,000). The cap is therefore already fair across terms in percentage terms. The earlier practical limits (₹450 / ₹600 / ₹600) are **retired**: they came from one flat 6,000-point ceiling and do not follow from the cap.

## 4. Clocks: what "season" is replaced by

Money and behaviour need different clocks.

| Clock | Definition | Used for |
|---|---|---|
| **Subscription cycle** | The paid term of one subscription invoice: 3, 6 or 12 months, from its start date to the day before the next term starts. A Season 1 complimentary term counts as one 3-month cycle | The **earning ceiling**, the **closed-business ceiling**, **redemption**, **expiry** |
| **Calendar day / month** | Midnight to midnight; calendar month | Burst limits: 500 per day (low-assurance points only), 3,000 per month |
| **Calendar quarter** | January-March, April-June, July-September, October-December | Behavioural and anti-collusion limits that used to be "per season": the pair budget and pair concentration rule, per-quarter frequency limits (events, introductions, needs, mentoring, invitations, repeat business) and review triggers |

A member's plan never changes their behavioural limits; it only changes the size of the money ceilings, in proportion to what they pay.

## 5. Redemption: when, how often, and what rolls forward

There is no invoice during a term, so **points can only be redeemed when a subscription invoice exists**. That is the whole redemption timing question.

| | Connect (3 mo) | Growth (6 mo) | Elite (12 mo) |
|---|---|---|---|
| Invoices a year | 4 | 2 | 1 |
| First time a new member can redeem | after 3 months, at the first renewal | after 6 months | after 12 months |
| Average wait from earning to redeeming | 1.5 months | 3 months | 6 months |
| Redeem during an active term? | No (no invoice exists) | No | No |
| Redemption happens at | renewal, re-subscription within grace, or an upgrade invoice | same | same |
| Annual discount if capped every invoice | ₹1,800 (15%) | ₹1,500 (15%) | ₹1,500 (15%) |

**Recommended rule.** Redemption happens at the **renewal invoice that closes the cycle in which the points were earned**. The renewal window opens 30 days before the term ends and runs 30 days past it (grace). The member sees the exact calculation, pays, and the balance is consumed oldest first. Rules around it:

* **Once per invoice**, and in total no more than 15% of the price of the plan bought for that cycle. An upgrade invoice in the same cycle may only top up to 15% of the new plan price, less what was already redeemed.
* **Points earned after the member has paid the renewal invoice** (the last days of the old term) count toward the **next** cycle.
* **No roll-forward of unused points** beyond the grace period. The earning ceiling (12% of price) is below the cap (15%), so **everything a member can earn in a cycle fits in that cycle's redemption**; a roll-forward would only create a stock of points nobody needs. (Section 6 shows what carrying them would cost.)
* A member who does not renew within grace loses the points. They are reminded when the window opens and 7 days before grace ends.
* One edge case for management: a member who **downgrades** at renewal (for example Elite to Connect) has earned more than the smaller plan's cap can use. By default the surplus expires. A one-cycle carry for downgrade surplus is a possible concession (decision 4 in the specification).

A helpful side effect: on a 12-month plan, points are redeemed up to a year after they were earned, long after the 60-day verification and reversal window, so almost no points are redeemed and then reversed.

## 6. Expiry: the four options

The old rule (6 months from earning) was tested against the real terms. Each option below is simulated month by month over four years for a member who earns evenly through every cycle and redeems at every renewal (first in, first out).

* **A.** Fixed 6 months from earning (the old rule)
* **B.** Fixed 12 months from earning
* **C.** One subscription term from earning (3 / 6 / 12 months)
* **D.** Valid at the renewal that closes the cycle the points were earned in, plus a 30-day grace, then expire

**Share of what a member earns that they can actually spend**

| Expiry option | Average member: share of earned value spendable (Connect / Growth / Elite) | Maximiser under Model B: share spendable | Maximiser under Model B: average points on the books | Maximiser under Model B: peak points on the books |
|---|---|---|---|---|
| A. Fixed 6 months from earning | 100% / 100% / 50% | 75% / 62% / 50% | ₹825 / ₹859 / ₹850 | ₹1,200 / ₹1,200 / ₹1,200 |
| B. Fixed 12 months from earning | 100% / 100% / 100% | 75% / 62% / 62% | ₹1,338 / ₹1,672 / ₹1,694 | ₹2,400 / ₹2,400 / ₹2,400 |
| C. One subscription term from earning (3 / 6 / 12 months) | 100% / 100% / 100% | 75% / 62% / 62% | ₹344 / ₹859 / ₹1,694 | ₹600 / ₹1,200 / ₹2,400 |
| D. Valid at the renewal that closes the cycle it was earned in, plus a 30-day grace; then it expires | 100% / 100% / 100% | 75% / 62% / 62% | ₹297 / ₹641 / ₹1,231 | ₹600 / ₹1,200 / ₹2,400 |

The 50% in option A for Elite is the failure the brief anticipated: an annual member's points from months 1-6 are gone before the only renewal at month 12.

**What each option leaves on TGL's books (400 members, members who never redeem included)**

| Expiry option | Average value of unexpired points (400 members) | Highest (upper bound) | Share of the points of members who redeem that they can spend |
|---|---:|---:|---:|
| A. Fixed 6 months from earning | ₹20,081 | ₹37,464 | 95% |
| B. Fixed 12 months from earning | ₹27,548 | ₹49,485 | 100% |
| C. One subscription term from earning (3 / 6 / 12 months) | ₹19,525 | ₹39,990 | 100% |
| D. Valid at the renewal that closes the cycle it was earned in, plus a 30-day grace; then it expires | ₹18,456 | ₹41,336 | 100% |

**Scorecard**

| Option | Member attractiveness | TGL liability (points on the books) | Simplicity | Abuse risk | Verdict |
|---|---|---|---|---|---|
| A. 6 months fixed | Fails for Elite: half of earnings lost; Growth only just fits | Low-medium (₹20,081 average) | Simplest: one number | Low | **Reject**: unfair to the longest plan |
| B. 12 months fixed | Good | **Highest** (₹27,548, +49% over D); a 3-month member keeps points across four renewals | Simple | Medium: hoarding, and surplus piles up if a ceiling is ever raised | Reject |
| C. One term from earning | Good | Medium (₹19,525) | Medium: three different lengths | Low-medium | Acceptable alternative |
| D. Cycle-relative with grace | Good: every plan can spend 100% of what it earns | **Lowest** (₹18,456) | Medium-high: "use your points at your renewal" | **Lowest**: nothing to hoard | **Recommend** |

**Recommendation: D.** It is the only rule that is the same promise on every plan ("what you earn in a term you can use at that term's renewal"), it keeps the liability lowest, and it removes hoarding. Its cost to the member is that points are lost if they neither renew nor re-subscribe within grace, which the reminders and the 30-day grace are there to soften.

## 7. Earning ceiling: the models

The objective is unchanged: **a member must never be able to earn or redeem an amount equal to the full subscription price.** All models below respect it (the largest is 36% of the cycle price). The question is fairness across terms and the size of the worst case.

* **A.** 500/day, 3,000/month, **6,000 per subscription cycle**
* **B.** 500/day, 3,000/month, **6,000 per calendar quarter** (so 6,000 / 12,000 / 24,000 per cycle)
* **C.** **Monthly ceiling only**, no cycle ceiling
* **D.** A ceiling **scaled to the plan**: 12% of the price in points (3,600 / 6,000 / 12,000), plus variants at 10% and 15% and a flat 1,000 points per month of membership

| Earning model | Connect 3 mo: points per cycle (worth, % of price) | Growth 6 mo | Elite 12 mo |
|---|---|---|---|
| A. 6,000 per subscription cycle | 6,000 (₹600, 20%) | 6,000 (₹600, 12%) | 6,000 (₹600, 6%) |
| B. 6,000 per calendar quarter | 6,000 (₹600, 20%) | 12,000 (₹1,200, 24%) | 24,000 (₹2,400, 24%) |
| C. Monthly ceiling only | 9,000 (₹900, 30%) | 18,000 (₹1,800, 36%) | 36,000 (₹3,600, 36%) |
| D. 1,000 points per month of membership | 3,000 (₹300, 10%) | 6,000 (₹600, 12%) | 12,000 (₹1,200, 12%) |
| D. 10% of plan price | 3,000 (₹300, 10%) | 5,000 (₹500, 10%) | 10,000 (₹1,000, 10%) |
| D. 12% of plan price | 3,600 (₹360, 12%) | 6,000 (₹600, 12%) | 12,000 (₹1,200, 12%) |
| D. 15% of plan price | 4,500 (₹450, 15%) | 7,500 (₹750, 15%) | 15,000 (₹1,500, 15%) |

| Earning model | Practical maximum per invoice (Connect / Growth / Elite) | Points a maximiser earns beyond the cap, per cycle | Worst case per year (400 members) | % of annual revenue | Expected cost per year | % of annual revenue |
|---|---:|---:|---:|---:|---:|---:|
| A. 6,000 per cycle | ₹450 (15%) / ₹600 (12%) / ₹600 (6%) | 1,500 / 0 / 0 | ₹588,000 | 13.2% | ₹84,372 | 1.9% |
| B. 6,000 per calendar quarter | ₹450 (15%) / ₹750 (15%) / ₹1,500 (15%) | 1,500 / 4,500 / 9,000 | ₹666,000 | 15.0% | ₹90,190 | 2.0% |
| C. Monthly only | ₹450 (15%) / ₹750 (15%) / ₹1,500 (15%) | 4,500 / 10,500 / 21,000 | ₹666,000 | 15.0% | ₹90,190 | 2.0% |
| D. 1,000 per month of membership | ₹300 (10%) / ₹600 (12%) / ₹1,200 (12%) | 0 / 0 / 0 | ₹480,000 | 10.8% | ₹79,742 | 1.8% |
| D. 10% of price | ₹300 (10%) / ₹500 (10%) / ₹1,000 (10%) | 0 / 0 / 0 | ₹444,000 | 10.0% | ₹76,484 | 1.7% |
| D. 12% of price | ₹360 (12%) / ₹600 (12%) / ₹1,200 (12%) | 0 / 0 / 0 | ₹532,800 | 12.0% | ₹83,006 | 1.9% |
| D. 15% of price | ₹450 (15%) / ₹750 (15%) / ₹1,500 (15%) | 0 / 0 / 0 | ₹666,000 | 15.0% | ₹90,190 | 2.0% |

**Reading the table**

* **A** (flat 6,000 per cycle) is unfair: an Elite member can redeem at most 6% of their price, against 15% on Connect, and annually ₹600 against ₹1,800.
* **B** (per calendar quarter) is fair by time but has a larger ceiling than any cap can use: the Elite maximiser earns 24,000 points a cycle and can spend 15,000. The unusable 9,000 points are perceived waste and a stock to carry.
* **C** has no cycle ceiling at all. The unusable surplus is 21,000 points per Elite cycle, and the fraud prize is the largest (₹3,600 a year per account).
* **D at 12%** gives every plan the same percentage of what it pays, nothing is unusable, and the practical worst case (12.0%) stays where the approved model had it (11.8%).
* **D at 15%** is the same design with the ceiling equal to the cap: simpler to explain, but the worst case rises to the full contractual 15% (₹666,000 a year, +₹133,200).
* **1,000 points per month** is a close second: identical to D at 12% for Growth and Elite, but Connect is cut to 10%.

**Annual redemption by member type and earning model**

| Member | Earning model | Connect 3 mo: redeemed per year (% of annual spend) | Growth 6 mo | Elite 12 mo |
|---|---|---|---|---|
| Average | A: 6,000/cycle | ₹255 (2.1%) | ₹255 (2.5%) | ₹255 (2.5%) |
| Average | B: 6,000/quarter | ₹255 (2.1%) | ₹255 (2.5%) | ₹255 (2.5%) |
| Average | D12: 12% of price | ₹255 (2.1%) | ₹255 (2.5%) | ₹255 (2.5%) |
| High | A: 6,000/cycle | ₹1,020 (8.5%) | ₹987 (9.9%) | ₹600 (6.0%) |
| High | B: 6,000/quarter | ₹1,020 (8.5%) | ₹1,020 (10.2%) | ₹1,019 (10.2%) |
| High | D12: 12% of price | ₹1,020 (8.5%) | ₹987 (9.9%) | ₹987 (9.9%) |
| Top performer | A: 6,000/cycle | ₹1,800 (15.0%) | ₹1,200 (12.0%) | ₹600 (6.0%) |
| Top performer | B: 6,000/quarter | ₹1,800 (15.0%) | ₹1,500 (15.0%) | ₹1,500 (15.0%) |
| Top performer | D12: 12% of price | ₹1,440 (12.0%) | ₹1,200 (12.0%) | ₹1,200 (12.0%) |

For ordinary members the model makes **no difference** (an average member redeems ₹255 a year on every plan). The ceiling only matters at the top, where model D gives every plan the same 12% and models A, B and C give very different results.

**Recommendation: Model D at 12% of the plan price**, cycle ceilings of **3,600 / 6,000 / 12,000 points** (₹360 / ₹600 / ₹1,200), with the contractual 15% cap kept in the Terms. Management may choose 15% (D15) if it wants Connect top performers to keep the ₹450 they had under v1; the cost is higher worst-case exposure.

The daily (500) and monthly (3,000) ceilings are unchanged. Two clarifications found while recalculating: (1) the 500-a-day ceiling applies to **low-assurance (L1/L2) points only**, otherwise a single verified ₹10L+ closure reward (1,890 points) could never be credited in one day; (2) on the 3-month plan the 3,000-a-month ceiling is 83% of the cycle ceiling, so it no longer smooths anything there, which is acceptable because every point is still bounded by the cycle ceiling.

## 8. All three plans (recommended model)

| Plan | Price | Term | 15% contractual cap | Points needed for the cap | Earning ceiling per cycle (points) | Practical maximum discount | Member still pays (practical) | Member still pays (contractual floor) | Expected points per cycle (avg member) | Expected redemption per invoice (avg member) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Connect | ₹3,000 | 3 months | ₹450 | 4,500 | 3,600 | ₹360 | ₹2,640 | ₹2,550 | 630 | ₹53 |
| Growth | ₹5,000 | 6 months | ₹750 | 7,500 | 6,000 | ₹600 | ₹4,400 | ₹4,250 | 1,188 | ₹99 |
| Elite | ₹10,000 | 12 months | ₹1,500 | 15,000 | 12,000 | ₹1,200 | ₹8,800 | ₹8,500 | 2,376 | ₹197 |

**Worst-case liability per member**

| Plan | Worst case per invoice | Worst case per year | % of cycle price | % of annual spend | Worst case per member-month | Price per member-month |
|---|---:|---:|---:|---:|---:|---:|
| Connect | ₹360 | ₹1,440 | 12.0% | 12.0% | ₹120 | ₹1,000 |
| Growth | ₹600 | ₹1,200 | 12.0% | 12.0% | ₹100 | ₹833 |
| Elite | ₹1,200 | ₹1,200 | 12.0% | 12.0% | ₹100 | ₹833 |

Per member-month the worst case is ₹120 on Connect and ₹100 on Growth and Elite, in proportion to the ₹1,000 and ₹833 they pay per month: **12% of what each member pays, on every plan.**

## 9. Member scenarios (recalculated)

Activity is the v1 behaviour per 3 months, scaled to the plan's term, and assumed identical per month on every plan.

| Scenario | Plan / term | Raw points per cycle | Earned per cycle | Worth | Redeemed at the renewal | Discount % of cycle price | Member pays | Redeemed per 12 months | % of annual spend |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Low activity | Connect ₹3,000 / 3 mo | 115 | 115 | ₹12 | ₹12 | 0.4% | ₹2,988 | ₹32 | 0.3% |
| Low activity | Growth ₹5,000 / 6 mo | 185 | 185 | ₹18 | ₹18 | 0.4% | ₹4,982 | ₹32 | 0.3% |
| Low activity | Elite ₹10,000 / 12 mo | 325 | 325 | ₹32 | ₹32 | 0.3% | ₹9,968 | ₹32 | 0.3% |
| Average | Connect ₹3,000 / 3 mo | 690 | 690 | ₹69 | ₹69 | 2.3% | ₹2,931 | ₹255 | 2.1% |
| Average | Growth ₹5,000 / 6 mo | 1,310 | 1,310 | ₹131 | ₹131 | 2.6% | ₹4,869 | ₹255 | 2.5% |
| Average | Elite ₹10,000 / 12 mo | 2,550 | 2,550 | ₹255 | ₹255 | 2.5% | ₹9,745 | ₹255 | 2.5% |
| High | Connect ₹3,000 / 3 mo | 2,605 | 2,605 | ₹260 | ₹260 | 8.7% | ₹2,740 | ₹1,020 | 8.5% |
| High | Growth ₹5,000 / 6 mo | 5,135 | 4,935 | ₹494 | ₹494 | 9.9% | ₹4,506 | ₹987 | 9.9% |
| High | Elite ₹10,000 / 12 mo | 10,190 | 9,870 | ₹987 | ₹987 | 9.9% | ₹9,013 | ₹987 | 9.9% |
| Top performer | Connect ₹3,000 / 3 mo | 7,555 | 3,600 (ceiling) | ₹360 | ₹360 | 12.0% | ₹2,640 | ₹1,440 | 12.0% |
| Top performer | Growth ₹5,000 / 6 mo | 15,035 | 6,000 (ceiling) | ₹600 | ₹600 | 12.0% | ₹4,400 | ₹1,200 | 12.0% |
| Top performer | Elite ₹10,000 / 12 mo | 29,995 | 12,000 (ceiling) | ₹1,200 | ₹1,200 | 12.0% | ₹8,800 | ₹1,200 | 12.0% |
| Maximiser (hits every ceiling) | Connect ₹3,000 / 3 mo | - | 3,600 (ceiling) | ₹360 | ₹360 | 12.0% | ₹2,640 | ₹1,440 | 12.0% |
| Maximiser (hits every ceiling) | Growth ₹5,000 / 6 mo | - | 6,000 (ceiling) | ₹600 | ₹600 | 12.0% | ₹4,400 | ₹1,200 | 12.0% |
| Maximiser (hits every ceiling) | Elite ₹10,000 / 12 mo | - | 12,000 (ceiling) | ₹1,200 | ₹1,200 | 12.0% | ₹8,800 | ₹1,200 | 12.0% |

## 10. The 400-member simulation

400 members (10 categories × 40 slots, the configured capacity), 55% Connect / 35% Growth / 10% Elite, behaviour mix 60% / 25% / 10% / 5% as before.

| Member type | Members | Redeem at an invoice | Points earned per member per year | Expected cost: one invoice from each (wave) | Expected cost per year |
|---|---:|---:|---:|---:|---:|
| Low | 240 | 30% | 325 | ₹1,156 | ₹2,340 |
| Average | 100 | 70% | 2,550 | ₹7,651 | ₹17,850 |
| High | 40 | 90% | 10,049 | ₹14,929 | ₹36,176 |
| Top | 20 | 100% | 13,320 | ₹10,560 | ₹26,640 |
| **Total** | 400 |  | 2,503 | **₹34,296** | **₹83,006** |

| Plan | Members | Annual revenue | Expected cost per year | % of that revenue | Worst case per year | % of that revenue |
|---|---:|---:|---:|---:|---:|---:|
| Connect | 220 | ₹2,640,000 | ₹47,131 | 1.8% | ₹316,800 | 12.0% |
| Growth | 140 | ₹1,400,000 | ₹27,903 | 2.0% | ₹168,000 | 12.0% |
| Elite | 40 | ₹400,000 | ₹7,972 | 2.0% | ₹48,000 | 12.0% |
| **Total** | 400 | ₹4,440,000 | **₹83,006** | 1.9% | **₹532,800** | 12.0% |

**Annualised TGL reward liability (recommended model).** Expected **₹83,006 a year (1.9% of ₹4,440,000)**; worst case **₹532,800 (12.0%)**; contractual bound ₹666,000 (15.0%). About 1.0 million points (₹100,000 at face value) are issued in a year. As in v1, **the expected figure is a model output, not a forecast.**

**Sensitivity**

| Change | Expected cost per year | % of annual revenue | Worst case per year | % of annual revenue |
|---|---:|---:|---:|---:|
| As assumed | ₹83,006 | 1.9% | ₹532,800 | 12.0% |
| Activity ×0.5 | ₹55,628 | 1.3% | ₹532,800 | 12.0% |
| Activity ×2 | ₹114,174 | 2.6% | ₹532,800 | 12.0% |
| Activity ×3 | ₹131,292 | 3.0% | ₹532,800 | 12.0% |
| Every member redeems at every invoice | ₹100,135 | 2.3% | ₹532,800 | 12.0% |
| Every member redeems, activity ×3 | ₹173,058 | 3.9% | ₹532,800 | 12.0% |
| Every member on Connect | ₹85,692 | 1.8% | ₹576,000 | 12.0% |
| Every member on Growth | ₹79,722 | 2.0% | ₹480,000 | 12.0% |
| Every member on Elite | ₹79,722 | 2.0% | ₹480,000 | 12.0% |

Even if every member redeemed at every invoice at three times the assumed activity, the cost is 3.9% of annual revenue and the worst case does not move: it is bounded by the ceilings.

**Do longer-plan members behave differently?** If Growth and Elite members were more active than Connect members (plausible for people who commit for longer):

| Activity of longer-plan members relative to Connect | Expected cost per year | % of annual revenue |
|---|---:|---:|
| Growth ×1, Elite ×1 | ₹83,006 | 1.9% |
| Growth ×1.25, Elite ×1.5 | ₹87,851 | 2.0% |
| Growth ×1.5, Elite ×2 | ₹91,800 | 2.1% |
| Growth ×2, Elite ×3 | ₹96,852 | 2.2% |

The effect is small because the ceilings bind first.

## 11. Closed-business reward ceiling

The old 3,600 closed-business points per "season" cannot survive: for a 3-month member it equals the whole cycle ceiling, and for a 12-month member it would cap a year of verified deals at 30% of their ceiling.

Options: per calendar period, per subscription cycle, or per year.

* **Per calendar quarter** would give a 3-month member a closed-business ceiling equal to their whole earning ceiling (no real sub-ceiling) and a 12-month member four times that.
* **Per year** (14,400) would exceed the total ceiling of the 6- and 12-month plans, so it would never bind.
* **Per subscription cycle, as 60% of that cycle's ceiling** keeps the sub-ceiling meaningful, scales with what the member pays, and is one rule instead of three.

| Plan | Cycle ceiling | Closed-business ceiling per cycle (60%) | Referral-process ceiling (25%) | Other (20%) | Verified ₹10L+ closures (referrer share 1,890) that fit | Closed-business points per year | Worth per year | % of annual spend |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v1: every plan, per assumed 3-month season | 6,000 | 3,600 | 1,500 | 1,200 | 1.9 | - | - | - |
| Connect | 3,600 | 2,160 | 900 | 720 | 1.1 | 8,640 | ₹864 | 7.2% |
| Growth | 6,000 | 3,600 | 1,500 | 1,200 | 1.9 | 7,200 | ₹720 | 7.2% |
| Elite | 12,000 | 7,200 | 3,000 | 2,400 | 3.8 | 7,200 | ₹720 | 7.2% |

**Recommendation: closed-business points are limited per subscription cycle to 60% of the cycle ceiling: 2,160 / 3,600 / 7,200.** Section 5 of the specification's reward values, the 70/30 split, the verification requirement and the hard cap per deal are unchanged, and there is still no percentage-of-deal-value reward.

Checks: one verified ₹10L+ closure always fits on every plan (referrer 1,890 ≤ 2,160, recipient 810), so the contradiction the pair-ceiling correction removed does not return. The maximum a single referral can ever pay is unchanged (referrer 1,980, recipient 900) and fits inside the smallest cycle ceiling. Per year, closed-business points are 7.2% of annual spend on every plan.

The pair rules keep their numbers but use the **calendar quarter**. With the new closed-business ceilings, the hard maximum between two members in a quarter is **6,900 points (₹690)**: the 1,500 low-assurance budget, 3,780 for the referrer (two verified ₹10L+ closures, possible only on the Elite plan) and 1,620 for the recipient. On Connect the referrer's second ₹10L+ closure in the same cycle pays only what is left under 2,160.

## 12. Fairness check

**Does a ₹10,000 / 12-month member get a reasonable opportunity compared with a ₹3,000 / 3-month member?** Yes. Ordinary members redeem the same ₹255 a year on every plan (table in section 7), and the ceiling is the same **12% of what each member pays**: ₹1,440 a year on ₹12,000 (Connect), ₹1,200 on ₹10,000 (Growth and Elite).

**Does the 12-month plan become worse because points expire before renewal?** Under the old 6-month rule, yes: half of an Elite member's earnings are lost (section 6). Under the recommended rule, no: 100% of what is earned in the term can be spent at the renewal.

**Does the 3-month plan become better because redemption is more frequent?** Not in value. The annual percentage ceiling is identical and ordinary members get the same rupees. What a 3-month member does get is **liquidity** (four chances a year; a 1.5-month average wait instead of 6) and ₹240 a year more at the very top, which is exactly 20% more, in proportion to paying 20% more a month. It is not a loophole: there is no way to spend points other than at a renewal, and each renewal can only use what was earned in that term.

**Does a longer subscription create excessive liability for TGL?** No. The worst case is 12.0% of annual revenue on every plan, and the expected cost is similar on all plans (1.8%, 2.0%, 2.0% of each plan's revenue). A longer plan carries its points for longer (average ₹550 outstanding for an Elite maximiser against ₹120 for Connect), but TGL has already received the full ₹10,000 up front, and the total on the books is the lowest of the four expiry options (₹18,456 for the network).

Nothing was problematic after the redesign, but the first test, carrying the v1 flat 6,000 ceiling and 6-month expiry forward, would have failed the first and second questions.

### The four business tests, re-run on the corrected model

| Question | Answer | Evidence |
|---|---|---|
| Could a member earn points equal to a full plan price in a cycle (or a year)? | **NO** | The ceiling is 12% of the price in points: ₹360 / ₹600 / ₹1,200 per cycle, 12% of annual spend on every plan. Even the most generous model tested (monthly ceiling only) stops at 36% |
| Could a highly active member redeem the whole subscription? | **NO** | Cap 15%, floor 85%; the practical maximum is ₹360 / ₹600 / ₹1,200 per invoice |
| Does the reward still feel meaningful? | **Yes, for the members it is meant for** | A top performer saves 12% of what they pay (₹1,200 to ₹1,440 a year); a high performer about 8.5-9.9% of spend; an average member about ₹255 a year on every plan (2.1-2.5%), which is modest by design |
| Does it encourage actions that create business? | **Yes** | Unchanged: 0 points for activity, points only for accepted, met and verified-closed referrals and confirmed helpful acts |

## 13. Old model versus corrected model

|  | v1 (wrong term assumption) | v2 (corrected) |
|---|---|---|
| Term of every plan | 3 months | 3 / 6 / 12 months |
| Revenue base | ₹1,760,000 'per season' | ₹1,760,000 per invoice wave; ₹4,440,000 per year |
| Earning ceiling | 6,000 points per season for every plan | 12% of the plan price per cycle: 3,600 / 6,000 / 12,000 points |
| Practical maximum discount | ₹450 / ₹600 / ₹600 | ₹360 / ₹600 / ₹1,200 |
| Expected cost | ₹25,386 per 'season' (1.4%) | ₹83,006 per year (1.9%); ₹34,296 per invoice wave |
| Worst case | ₹207,000 per 'season' (11.8%) | ₹532,800 per year (12.0%) |

## 14. Final recommendation

| # | Item | Recommendation |
|---|---|---|
| 1 | Point value | **1 point = ₹0.10** (unchanged) |
| 2 | Redemption cap | **15% of the plan price, once per invoice** (contractual ceiling, unchanged); never below the 85% floor (80% with coupons) |
| 3 | Earning ceiling | **500 a day (low-assurance points), 3,000 a month, and per subscription cycle 12% of the plan price in points: 3,600 / 6,000 / 12,000.** Sub-ceilings: referral process 25%, closed business 60%, other 20% of the cycle ceiling |
| 4 | Cycle definition | **The paid term of one invoice: 3, 6 or 12 months.** Calendar quarters are used only for behavioural and anti-collusion limits |
| 5 | Expiry | **Points are valid at the renewal that closes the cycle they were earned in, plus a 30-day grace; then they expire** (option D) |
| 6 | Redemption timing | **At the renewal invoice** (window opens 30 days before the term ends, runs 30 days past it), at a re-subscription within grace, or at an upgrade invoice; once per invoice |
| 7 | Carry-forward | **None**, except points earned after paying the renewal invoice, which belong to the next cycle. (Downgrade surplus: management decision) |
| 8 | Maximum discount, ₹3,000 plan | **₹360 practical (12%), ₹450 contractual (15%)** |
| 9 | Maximum discount, ₹5,000 plan | **₹600 practical (12%), ₹750 contractual** |
| 10 | Maximum discount, ₹10,000 plan | **₹1,200 practical (12%), ₹1,500 contractual** |
| 11 | Minimum member payment | **₹2,640 / ₹4,400 / ₹8,800** practical; **₹2,550 / ₹4,250 / ₹8,500** contractual floor |
| 12 | Closed-business reward ceiling | **60% of the cycle ceiling per subscription cycle: 2,160 / 3,600 / 7,200**; per-deal values, 70/30 split, evidence rules unchanged |
| 13 | 400-member expected cost | **₹83,006 a year (1.9% of ₹4,440,000)**; ₹34,296 per invoice wave (informational) |
| 14 | 400-member worst case | **₹532,800 a year (12.0%)**; contractual bound ₹666,000 (15.0%) |
| 15 | Annualised TGL reward liability | **Expected ₹83,006; worst case ₹532,800; average points on the books ₹18,456** |
| 16 | Why it is fair across 3/6/12 months | Every ceiling is a **percentage of what the member pays** (12% earning, 15% cap), so each plan has the same relative opportunity; expiry is **relative to the member's own cycle**, so no plan loses points before its renewal; ordinary members redeem the same rupees a year on every plan; the worst case is 12% of annual revenue on every plan |

## 15. What this changes in the specification, and what it does not

**Changed:** items 3-7 of the table above replace the flat 6,000 ceiling, the 6-month expiry and "per season" everywhere; the price-confirmation gate now confirms **terms as well as prices**; the 400-member figures, sensitivities and the pair-rule maximum are replaced; Phase 3 gate G4 no longer says "one full season".

**Unchanged:** the reward values per action, the Pair Assurance Rule's structure, verification levels, reversals, no transfer, no cash value, use only against a TGL subscription invoice, the floors, Phase 0 as the prerequisite, shadow mode first, and the rule that nothing is redeemable until gates G1-G5 are met.

## 16. Phase 0 plan data: corrected

The Phase 0 subscription foundation already stored the term per plan, so the correction needed no redesign. Its **seed data had been wrong** against the corrected terms (all three plans 3 months, a `billing_period` label allowing only `SEASON`). That has since been fixed in a separate, targeted change: migration `0009` and the canonical `DEFAULT_PLANS` now carry **Connect ₹3,000 / 3 months, Growth ₹5,000 / 6 months, Elite ₹10,000 / 12 months**, the billing-period label was removed (the term is the plan's `period_months`, allowed values 3, 6 and 12), and no invoice, payment or subscription was rewritten. "Season" is no longer used as a universal subscription duration; the subscription cycle in this model is the member's actual paid term. The confirmation required before redemption is of the **3 / 6 / 12-month terms and prices**, and `SUBSCRIPTION_PRICING_CONFIRMED` stays false until management gives it.

## 17. Assumptions that remain assumptions

Activity per member, the 60/25/10/5 behaviour mix, who redeems at an invoice (30% / 70% / 90% / 100%), the plan mix (55 / 35 / 10), and that every member renews each term (which makes the cost an upper bound: a member who does not renew costs nothing) are unchanged assumptions from v1 and must be replaced by measured data. The expiry simulation spreads earnings evenly through a cycle; real earnings are lumpy, which does not change the conclusions because the ceiling is below the cap. GST and gateway charges are ignored, as before.

## 18. Reproducing every number

```bash
cd docs/growth_points_model
python3 economy_v2.py --check   # engine reproduces the v1 numbers (₹25,386 and ₹207,000) from v1's inputs
python3 economy_v2.py           # every table above
```

`economy_v1_superseded.py` is the original model, kept for traceability only.
