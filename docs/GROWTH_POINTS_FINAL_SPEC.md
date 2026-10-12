# TGL Growth Points: Final Specification and Roadmap (v3)

**Status:** specification for management sign-off. **No Growth Points code has been written** and none should be until the Phase 0 gate below is met. This document supersedes `GROWTH_POINTS_ECONOMY_REPORT.md` wherever the two differ; that report remains the reference for the audit, the reward values and the first model comparison. The working behind every number in this version is in `GROWTH_POINTS_ECONOMY_RECALCULATION.md`, produced by `growth_points_model/economy_v2.py`.

Nothing here is legal or accounting advice. Items for professional review are listed in section 11.

> **v3 correction (business).** v1 and v2 of this specification treated Connect, Growth and Elite as three prices for the same 3-month "season". The real terms are **Connect ₹3,000 / 3 months, Growth ₹5,000 / 6 months, Elite ₹10,000 / 12 months**. "Season" is therefore no longer a unit. It is replaced by the **subscription cycle** (for money limits: earning, redemption, expiry) and the **calendar quarter** (for behavioural and anti-collusion limits). The flat 6,000-point ceiling, the 6-month expiry and the practical limits of ₹450 / ₹600 / ₹600 are retired; the 400-member figures are recalculated on annualised revenue. What did **not** change: the point value, the 15% contractual cap, every reward value, the Pair Assurance Rule's structure, verification, reversals, the floors, and the gates.

**Terms used in this document**

| Term | Meaning |
|---|---|
| **Subscription cycle** | The paid term of one subscription invoice (3, 6 or 12 months), from its start date to the day before the next term starts. A Season 1 complimentary term counts as one 3-month cycle |
| **Calendar quarter** | January-March, April-June, July-September, October-December |
| **Renewal window** | Opens 30 days before the term ends and closes 30 days after it (the 30 days after are the grace period) |
| **Low-assurance / verified points** | Verification levels L1-L2 / L3-L4 (section 2) |

---

## 1. Locked parameters (Model B, corrected for 3 / 6 / 12-month terms)

| Parameter | Value |
|---|---|
| Point value | **1 Growth Point = ₹0.10** (10 points = ₹1) |
| Subscription terms | **Connect ₹3,000 / 3 months · Growth ₹5,000 / 6 months · Elite ₹10,000 / 12 months** (to be confirmed in writing, section 8) |
| Contractual redemption ceiling | **15% of the price of the plan being purchased**, once per subscription invoice: **₹450 / ₹750 / ₹1,500** (4,500 / 7,500 / 15,000 points) |
| Earning ceilings | **500 points per day** (low-assurance points only) · **3,000 per calendar month** · **per subscription cycle, 12% of the plan price in points: 3,600 / 6,000 / 12,000** (₹360 / ₹600 / ₹1,200) |
| Cycle sub-ceilings | Referral process **25%** · closed business **60%** · all other **20%** of the cycle ceiling (900 / 1,500 / 720 for Connect; 1,500 / 3,600 / 1,200 for Growth; 3,000 / 7,200 / 2,400 for Elite, in the order process / closed business / other) |
| Expiry | **Points are valid at the renewal that closes the cycle they were earned in, plus a 30-day grace period; then they expire.** 30-day reminder before the grace ends; unconfirmed pending points lapse at 60 days |
| Redemption timing | **Only against a subscription invoice**: the renewal invoice (window opens 30 days before the term ends) or a re-subscription within grace. Once per invoice. Never during a term. *(Amended by the management decision lock: there is no separate "upgrade invoice"; a plan changes only at renewal, see `PHASE_1_SUBSCRIPTION_RENEWAL_RULE.md`.)* |
| Carry-forward | **None**, except that points earned after the member has paid the renewal invoice count toward the next cycle |
| Transfer between members | **None** |
| Cash conversion / cash refund | **None** |
| Use | **Discount on an eligible TGL subscription invoice only** |
| Combined-discount floor | Points plus any coupon may not take the invoice below **80%** of the plan price; points alone never below **85%** |
| Referral created | **0 points** |
| Views, likes, logins, connections, posting or replying to a need | **0 points** |

The earning ceiling (12%) is deliberately **below** the cap (15%). Whatever a member can earn in a cycle can be spent at that cycle's renewal, so no point is ever stranded by the cap and no roll-forward is needed.

---

## 2. The pair ceiling versus the ₹10L+ closure reward (corrected)

### 2.1 The contradiction

The first report capped points between any two members at **1,500 per quarter**, yet a verified ₹10L+ closure pays a **2,700-point pool** (referrer 1,890, recipient 810). A legitimate high-value deal could therefore never be rewarded in full. That is wrong: the cap was protecting against *cheap, unverified* farming, but it also blocked the most valuable and most heavily verified activity.

### 2.2 Why not simply remove it

Collusion is cheap exactly where verification is weak. Two accounts can generate referrals, acceptances, "meetings" and small "closures" between themselves at no real cost. The pair limit must stay for that kind of activity. What must change is *which points it counts*.

### 2.3 The corrected rule: the Pair Assurance Rule

Points are classified by how strongly they were verified:

- **Low-assurance points:** verification level L1 or L2. That is acceptance, contact, meetings confirmed by both members, introductions, need help, and closures up to ₹1L confirmed by both members without evidence.
- **Verified points:** verification level L3 or L4. That is a closure with **evidence that has passed verification** (invoice or payment proof, checked by the system and an admin) or **admin approval** (always required above ₹5L).

A *pair* is an unordered pair of members (A, B). Points count toward a pair only when they come from an interaction *between those two members* (in either direction).

| Rule | Statement |
|---|---|
| **P1. Low-assurance pair budget** | Low-assurance points earned by A and B **from each other**, both members and both directions combined, are capped at **1,500 per calendar quarter**. Anything above is recorded in the ledger as `CAPPED` with value 0. |
| **P2. Verified closures are exempt from P1** | A closure that reaches L3/L4 pays its full band pool, and does **not** use up the P1 budget. |
| **P3. Concentration rule for verified closures** | Per pair per calendar quarter: the **first two** verified closures pay in full. A **reciprocal** closure (the second one flows in the opposite direction, B→A after A→B) needs **L4 admin approval and pays 50%** of its band pool. A **third or later** verified closure pays **0** unless an admin records a reasoned exception. |
| **P4. Review triggers (no points effect)** | A pair with 3 or more rewarded interactions in 30 days; a member whose closed-business points in a calendar quarter come more than 50% from one counterparty; a closure within 24 hours of acceptance; the same prospect phone or email appearing in referrals across different pairs. Each creates an admin review item. |
| **P5. Everything else still applies** | The closed-business sub-ceiling (60% of the cycle ceiling) and the 500 / 3,000 / cycle member ceilings apply on top, in this order: validity → verification level → pair rules → sub-ceilings → daily / monthly / cycle ceilings. A reduced row records which rule reduced it (`capped_by`). |

**Evidence upgrade path:** a member can upgrade a smaller deal (₹1L or less) to L3 by uploading evidence that passes verification. It is then a verified closure and no longer uses the pair budget. This keeps real, documented small deals rewardable without opening a hole for unverified farming.

### 2.4 Worked cases

| Case | What happens | Points |
|---|---|---:|
| **1. One legitimate ₹10L+ deal** (A refers, B closes) | Process points (accept, contact, meeting) are low-assurance and use about 180 of the 1,500 budget. The verified closure pays the full pool of 2,700 (A 1,890, B 810). It fits inside every plan's closed-business ceiling (2,160 on Connect is the smallest). **No contradiction** | A 1,980 · B 900 (the per-referral maximum) |
| **2. Two legitimate ₹10L+ deals, same direction, same quarter** | Both verified closures pay in full under P3, then A's closed-business ceiling applies: A's closure points are 3,780 before it | A closure points: **Connect 2,160 · Growth 3,600 · Elite 3,780** · B 1,620 · process about 360 |
| **3. A third verified closure between the same two members** | Pays 0 unless an admin records an exception | 0 |
| **4. Reciprocal ₹10L+ deals** (A→B, then B→A) | First pays in full. Second needs admin approval and pays 50% (pool 1,350: B 945, A 405) | A 2,295 (held at 2,160 on Connect) · B 1,755 · process about 360 |
| **5. Two accounts farming small fake referrals and meetings** | All low-assurance. The pair stops earning at the budget | **1,500 combined per quarter (₹150)** |
| **6. A forged ₹10L+ closure** | Cannot reach L3/L4 without both confirmations, valid evidence and admin sign-off. If discovered later, a 60-day clawback and suspension apply | At most one pool (₹270) at risk |

### 2.5 Effect on the earlier calculations

| Quantity | Before | After | Note |
|---|---|---|---|
| Maximum points between any two members in a quarter | 1,500 (₹150) | **Low-assurance 1,500, plus verified closures: hard maximum 6,900 (₹690)** | 6,900 = 1,500 budget + 3,780 (A: two ₹10L+ closures, possible only on Elite; Growth 3,600, Connect 2,160) + 1,620 (B), and only if two ₹10L+ closures pass evidence and admin review |
| Maximum for one referral | Referrer 1,980, recipient 900 | **Unchanged, and reachable on every plan** | |
| Per-member ceiling | 6,000 per season | **12% of the plan price per cycle: 3,600 / 6,000 / 12,000 (hard)** | The pair rule only ever *removes* points; it never lets a member exceed their own ceilings |
| 400-member expected cost and worst case | ₹25,386 · ₹207,000 per "season" | **₹83,006 · ₹532,800 per year** | Recalculated on the real terms and annualised revenue (section 4). The simulation does not model pair limits, which can only lower totals |
| Business-test results | All pass | **All pass**, re-run on the corrected model (section 12 of the recalculation) | |

---

## 3. Contractual ceiling versus practical limit

Two different limits exist and must never be conflated, in the Terms, the dashboards or the engine.

| | Contractual redemption ceiling | Practical discount limit |
|---|---|---|
| What it is | **15% of the plan price**: the most TGL has agreed a member may redeem on one invoice | What a member can actually reach, because the **cycle earning ceiling (12% of the plan price)** stops balances growing larger |
| Who sets it | Terms and conditions | Operational parameter that management can change, with re-modelling |
| ₹3,000 / 3 months | **₹450** | **₹360** (12%) |
| ₹5,000 / 6 months | **₹750** | **₹600** (12%) |
| ₹10,000 / 12 months | **₹1,500** | **₹1,200** (12%) |
| Member pays at least (contractual / practical) | ₹2,550 / ₹4,250 / ₹8,500 | ₹2,640 / ₹4,400 / ₹8,800 |

Rules:
1. The engine always applies **min(contractual ceiling, value of available points)**. It never trusts the earning ceiling to have prevented a large balance (a bug or data error could create one).
2. Terms state the contractual 15% as "up to", subject to the points the member has earned and the cycle earning limit.
3. The member dashboard shows both: "Maximum discount on your plan: ₹600 (cap ₹750)" and "You can earn up to ₹600 in a 6-month term."
4. **If management ever raises the earning ceiling** (for example to 15%), the practical limit moves to the contractual one and the exposure rises with it. The contractual bound on the assumed plan mix is **₹666,000 a year (15.0% of ₹4,440,000)**. The practical bound today is **₹532,800 (12.0%)**. Any ceiling change must be re-modelled and approved.
5. Because the ceiling is proportional to price, **both limits are the same percentage on every plan**, whatever its term.

---

## 4. The ₹83,006 figure is a model output, not a forecast

**The expected cost of ₹83,006 a year (1.9% of annualised subscription revenue of ₹4,440,000) is the output of a model built on assumptions. It is not a real-world forecast and must not be quoted to anyone as the expected cost of the programme.** It depends on things nobody knows yet:

1. How active members will actually be (referrals, meetings, closed deals): *assumed*, the same per month on every plan.
2. Which plans members will buy: *assumed 55% ₹3,000 / 35% ₹5,000 / 10% ₹10,000* (no subscription data exists).
3. How many members will redeem at an invoice: *assumed 30% / 70% / 90% / 100% by activity group*.
4. That every member renews each term: *assumed*, which makes the cost an upper bound.

**Revenue must be read per year.** One invoice from each of 400 members is ₹1,760,000, but those invoices cover 3, 6 and 12 months. Annualised, revenue is **₹4,440,000** (₹1,110,000 a quarter, ₹370,000 a month): Connect ₹2,640,000, Growth ₹1,400,000, Elite ₹400,000. Earlier reports compared costs with the ₹1,760,000 figure as though it were one period.

Sensitivity of the same model (400 members, per year):

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

What *is* a bound rather than an assumption: the **worst case never exceeds 15% of subscription revenue** (the contractual ceiling), and on the assumed mix it is ₹532,800 (12.0%) because of the earning ceiling. Because the ceiling is a percentage of price, the worst case is 12.0% for **every** plan mix. The expected cost will be replaced by **measured shadow-mode data** (section 8) before any redemption is allowed.

---

## 5. Final reward table (Model B, ₹0.10 per point)

Values are unchanged from the first report; the new column shows how the Pair Assurance Rule treats each reward. Frequency limits that were "per season" are now **per calendar quarter** (the same numbers). Money ceilings are per subscription cycle (section 1).

| Action | Recipient | Points | Verification | Limit | Pair rule |
|---|---|---:|---|---|---|
| Referral created | none | **0** | System | Rate limited | n/a |
| Referral accepted | Referrer | **30** (+15 if direct introduction or arranged meeting) | Recipient (L1) | 10 rewarded per month | Low-assurance (P1) |
| Referral accepted | Recipient | **15** | L1 | Once per referral | Low-assurance (P1) |
| Prospect contacted within 72h | Recipient | **15** | Recipient, referrer may dispute (L1) | Once per referral | Low-assurance (P1) |
| Meeting completed | Referrer | **45** | Both confirm (L2) | Once per referral; 8 per month | Low-assurance (P1) |
| Meeting completed | Recipient | **60** | Both confirm (L2) | Once per referral | Low-assurance (P1) |
| Closed: under ₹25k | Referrer / Recipient | **210 / 90** | Both confirm (L2) | Once per referral | Low-assurance unless evidence upgrade |
| Closed: ₹25k–₹1L | Referrer / Recipient | **525 / 225** | Both confirm (L2) | Once per referral | Low-assurance unless evidence upgrade |
| Closed: ₹1L–₹5L | Referrer / Recipient | **1,050 / 450** | Both + evidence (L3) | Once per referral | **Verified (P2, P3)** |
| Closed: ₹5L–₹10L | Referrer / Recipient | **1,470 / 630** | Both + evidence + admin (L4) | Once per referral | **Verified (P2, P3)** |
| Closed: ₹10L+ | Referrer / Recipient | **1,890 / 810** (hard maximum) | Both + evidence + admin (L4) | Once per referral | **Verified (P2, P3)** |
| Repeat business, same prospect | Both | 50% of the band pool | As above | Once per prospect per calendar quarter | As above |
| Profile completed | Member | **75** | System (L3) | Once | n/a (no counterparty) |
| Event attended *(future)* | Member | **45** | Admin check-in (L3) | 3 per calendar quarter | n/a |
| Successful introduction *(future)* | Connector | **75** (+150 if a meeting follows) | Both members confirm (L2) | 4 per calendar quarter; once per pair | Low-assurance (P1) |
| Need resolved *(future)* | Helper | **60** | Poster confirms (L2) | 4 per calendar quarter | Low-assurance (P1) |
| Mentoring session *(future)* | Mentor | **90** | Mentee confirms (L2) | 3 per calendar quarter | Low-assurance (P1) |
| New member invited and active *(future)* | Inviter | **225** | Payment verified + 30 days (L3) | 3 per calendar quarter | n/a |

Closure pool split: **70% referrer / 30% recipient**. Maximum one referral can ever pay: referrer 30 + 15 + 45 + 1,890 = **1,980**; recipient 15 + 15 + 60 + 810 = **900**.

---

## 6. Verification, release and reversal

| Level | Meaning | Release |
|---|---|---|
| **L0** | Self-reported | Never pays |
| **L1** | Counterparty confirms one step | `PENDING` 7 days, then `AVAILABLE` |
| **L2** | Both parties confirm | `PENDING` 7 days |
| **L3** | Evidence or system verified | After verification |
| **L4** | Admin verified | After admin approval |

The client sends only intent ("I confirm this meeting happened"). The server derives who the caller is, what the stored referral says, the verification level, the rule and the points. **The frontend never supplies points, deal value, status, role or member id.**

Reversals: a declined, cancelled or closed referral voids pending points. A disputed meeting (7 days) voids pending points. A deal found false, refunded or disputed within **60 days** creates negative ledger rows for both parties; points already redeemed go to admin review (no automatic cash recovery). Confirmed fraud voids the interaction's points and may reduce a member's ceiling or suspend rewards. Every admin action is a ledger row plus an audit-log entry.

---

## 7. Redemption rules (specified now, built only after the Phase 3 gate)

- Redeemable **only against an eligible TGL subscription invoice**, at the **renewal invoice that closes the cycle in which the points were earned**. The renewal window opens 30 days before the term ends and runs 30 days past it (grace). There is no invoice during a term, so **no redemption happens mid-term**.
- A **re-subscription within the grace period** is treated as the renewal. A member who does not renew or re-subscribe by the end of grace **loses the unredeemed points**.
- **Once per invoice**; the member sees the exact calculation before confirming. In total no more than 15% of the price of the plan bought for that cycle.
- Amount = min(15% of the plan price, value of available points), then the 85% floor (points alone) and 80% floor (all discounts combined) are enforced **server-side at checkout**.
- Points are consumed **FIFO** by earliest expiry.
- **Carry-forward: none.** Points earned *after* the member has paid or redeemed on the renewal invoice belong to the next cycle. (Because the earning ceiling is below the cap, nothing a member earns in a cycle is ever left over by the cap.)
- **Plan changes:** only at renewal (amended by the management decision lock; there is no mid-cycle upgrade or downgrade). The member may renew into the same plan, an upgrade or a downgrade. Eligible points of the OLD cycle may be used against the NEW renewal invoice up to 15% of the NEW plan's price (`MIN(eligible old-cycle points, new-plan cap)`); the new cycle starts with zero transferred earning points and its own ceiling. Points above the new cap are not carried into the new cycle and follow the expiry rule. Details: `PHASE_1_SUBSCRIPTION_RENEWAL_RULE.md`.
- Cancellation: points freeze, still expire when the grace period ends, and are usable only if the member re-subscribes within it.
- Refunds: only **cash actually paid** is refunded; points used are re-credited only for a refund within 7 days and only if not expired.
- **No transfer. No sale. No cash conversion. No cash refund. No payment to another member.**

Why this is the cleanest rule across 3 / 6 / 12 months: the same promise holds for every plan (what you earn in a term, you can use at that term's renewal); the longer plans lose nothing to expiry; there is nothing to hoard; and on a 12-month plan points are redeemed long after the 60-day reversal window has passed. Alternatives tested in the recalculation (6-month fixed, 12-month fixed, one term from earning) are worse: the first destroys half of an Elite member's points, the second leaves 49% more points on the books.

---

## 8. Term and price confirmation (required before Phase 3)

The Subscription page has shown the three prices as a "3-month Season 1 membership", and earlier versions of every calculation treated all three as per season. **That was wrong.** The terms now specified are:

| Plan | Price | Term |
|---|---:|---|
| Connect | ₹3,000 | 3 months |
| Growth | ₹5,000 | 6 months |
| Elite | ₹10,000 | 12 months |

**Required before Phase 3:** management confirms **in writing** these three prices **and** their terms. If any plan is billed monthly, or on another term, the ceilings, the cost model, the expiry rule and the floors must be recalculated and re-approved before redemption can be built. The redemption feature must refuse to be enabled while the confirmation flag is unset.

**Phase 0 plan data: corrected.** The Phase 0 subscription foundation stores the term per plan. Its seed data and one constraint had encoded the old assumption (all three plans 3 months, a billing-period label that allowed only `SEASON`); migration `0009` and the canonical `DEFAULT_PLANS` now carry **Connect 3, Growth 6, Elite 12 months**, the label is gone, and a plan term can only be 3, 6 or 12 months. Existing invoices and subscriptions keep the term they were issued with. The subscription cycle used by this specification is **the member's actual paid term**.

---

## 9. Phase 0 (mandatory, before any Growth Points code)

Each item is mandatory, with its acceptance criteria.

| # | Requirement | Acceptance criteria |
|---|---|---|
| 0.1 | **Subscription and invoice system** | Plans, purchases, invoices (list price, discount lines, amount paid, status), GST-ready fields, payment records. A member's plan is a stored fact, not product copy |
| 0.2 | **Two-party meeting confirmation** | A meeting is a stored record. It counts only when **both** the referrer and the recipient confirm; one-sided "mark done" no longer triggers anything that could earn points |
| 0.3 | **Two-party business-closure confirmation** | Closure needs the recipient's report and the referrer's confirmation; either can dispute |
| 0.4 | **Deal value capture at closure** | The deal-value **band** is entered at closure (not the creation-time estimate), by the recipient, confirmed by the referrer |
| 0.5 | **Evidence verification** | Invoice or payment proof upload for closures over ₹1L (and for the optional upgrade of smaller ones); system checks plus admin review; ≥₹5L always admin approved; random audits of the rest; flagged pairs always reviewed |
| 0.6 | **Audit log** | Append-only record of every admin action and every confirmation, who and when |
| 0.7 | **Admin referral management** | Screens to list referrals, see confirmations and evidence, approve or reject verifications, review flagged pairs and add reasoned exceptions |

Phase 0 is also valuable by itself: it makes referral statistics trustworthy.

---

## 10. Phase 1: shadow mode (exact scope)

**Goal:** calculate and record Growth Points internally while they **cannot reduce any real invoice**.

Build: the append-only **ledger** (`growth_point_ledger`), the **reward rules** table, the central **reward engine**, the referral-lifecycle and profile-completion rewards, idempotency, ceilings and the Pair Assurance Rule, reversals, expiry and reconciliation jobs.

Ledger additions required by this specification: `assurance_level` (L1–L4), `shadow` (true for the whole of Phase 1), `capped_by`, `pair_key` (sorted member ids), `rule_version`, `idempotency_key`, plus the columns in the first report (`id`, `member_id`, `event_type`, `reference_type`, `reference_id`, `points_delta`, `reason`, `status`, `created_at`, `created_by`, `balance_after`, `remaining`, `expires_at`).

Enforced guards (all must exist):
1. **No redemption code path is deployed**; the redemption service and invoice integration do not exist in Phase 1.
2. A configuration flag `GROWTH_POINTS_REDEMPTION` is **off** and has no UI to turn it on.
3. A database constraint rejects `REDEMPTION` ledger rows while `shadow = true`.
4. An automated test proves a redemption attempt is refused, and another proves a shadow ledger row can never appear as a deduction on an invoice.

Member visibility during shadow mode (management decision, see section 12): the recommended default is a clearly labelled **preview** ("Growth Points preview. Not redeemable yet."), so members are not told points are spendable when they are not. The existing copy that already promises Growth Points must be softened accordingly.

**What happens to shadow points when redemption launches** is a management decision. Recommended default: shadow-period points are **not** carried over into redeemable balances, so the first redeemable balance starts clean; a one-off founders' bonus, if wanted, is decided separately.

Measured during the shadow period: points issued per member, share of members at each ceiling, closure volumes by band, share of closures dual-confirmed and evidenced, admin verification turnaround, pair-rule hits and flagged patterns, and what the cost *would* have been under 100% redemption.

---

## 11. Phase 3 gate: no redemption until all of these are true

Redemption is **not implemented, and its flag cannot be enabled,** until every item is complete:

| # | Gate | Evidence required |
|---|---|---|
| G1 | **Management approves the financial model** | Written approval of the parameters in section 1, the pair rule and the sensitivity in section 4 |
| G2 | **Accounting and legal review completed** | Written answers to the review questions below |
| G3 | **Terms and prices confirmed** | The written confirmation in section 8 |
| G4 | **At least one full calendar quarter of real activity measured (two recommended)** | A calibration report built on shadow-ledger data that replaces the assumptions in section 4 with measured values and re-runs the model |
| G5 | **Phase 0 and Phase 1 working in production** | Ledger reconciliation shows zero drift for 60 days; fraud and review queues are being handled |

Suggested go/no-go thresholds for G4, **proposed for management to set or change**: simulated cost at 100% redemption on measured data at or below 3% of subscription revenue; no more than 10% of members at their cycle ceiling; at least 95% of closures confirmed by both parties; admin verification within 5 working days; no unresolved fraud flags.

**Questions for professional accounting/legal review (G2)**
1. How should unredeemed points be recorded (contingent liability, provision, deferred discount), and does expiry change it?
2. Are points a promotional discount or deferred consideration, given they are earned through other members' business?
3. GST: is the taxable value the discounted or the list price, and how should an invoice show a points redemption?
4. What are the accounting and GST effects of expiry, cancellation, refund and chargeback on a subscription part-paid with points?
5. Does the scheme fall under any loyalty-programme, consumer-law or disclosure rules?
6. What consent and terms are needed (right to change or end the scheme, expiry, forfeiture for fraud, disputes, use of deal information for community announcements)?
7. How should prospect data (phone, email) collected without the prospect's direct consent be handled under data-protection rules?

---

## 12. Implementation roadmap

| Phase | Work | Exit criteria | Money at stake |
|---|---|---|---|
| **0. Foundations (mandatory)** | Section 9: subscriptions and invoices, two-party meeting and closure confirmation, deal value at closure, evidence verification, audit log, admin referral management | All 0.1–0.7 acceptance criteria met in production | None |
| **1. Shadow ledger and engine** | Section 10. Points calculated and recorded internally; no redemption | Run for at least one full calendar quarter (two recommended); guards 1–4 tested; reconciliation clean | **None** (cannot reduce an invoice) |
| **2. Dashboards and admin analytics** | Member dashboard labelled as preview; admin dashboard with **maximum potential liability** and **realised cost** shown separately; fraud and pending queues | Management can see issued, pending, capped, reversed, expiring and outstanding points | None |
| **Gate G1–G5** | Section 11 | All five satisfied and recorded | |
| **3. Redemption** | Cap, floors, FIFO lots, invoice line item, GST-ready display, feature flag | Accountant sign-off; staged rollout; reconciliation of redemptions to invoices | **First real money** |
| **4. New earning features** | Event check-in, introductions, need resolution, mentoring sessions, invitations. Each with its own verification and tests | Each feature verified before its reward is enabled | Within the ceilings |
| **5. Community milestones** | Opt-in announcements: networking members only, value ranges not amounts, delayed 24 hours, both members must opt in to be named | Privacy review; opt-out in settings | None |
| **6. Recalibration** | Re-run the model every quarter on measured data; adjust values and ceilings only with approval | Written approval of any change | Controlled |

---

> **Implementation note (Phase 2).** Real redemption exists in code, disabled. **Item 6 below is DECIDED (final): shadow-period points do not carry over.** They are historical records only and are permanently ineligible; only points earned at or after the officially approved cutoff can ever be redeemed. See `GROWTH_POINTS_DEMO_DATA_AND_ELIGIBILITY.md`.

## 13. Decisions still needed from management

1. **Written confirmation of the terms and prices** (₹3,000 / 3 months, ₹5,000 / 6 months, ₹10,000 / 12 months), gate G3.
2. **Earning ceiling:** 12% of the plan price per cycle (recommended: ₹360 / ₹600 / ₹1,200), or 15% (₹450 / ₹750 / ₹1,500, worst case 15% of revenue instead of 12%).
3. **Expiry rule:** cycle-relative with a 30-day grace (recommended) or another option from the recalculation; and the length of the renewal window and grace.
4. **Downgrade surplus:** expire (default) or carry one cycle.
5. **Shadow-mode visibility:** show members a labelled preview, or keep points hidden until launch? (recommended: preview)
6. **Shadow points at launch:** carry over, partially carry over, or start clean? (recommended: start clean)
7. **Evidence accepted for closures over ₹1L** (tax invoice, payment proof, both?) and who in the team will verify, with a target turnaround.
8. Approval of the **go/no-go thresholds** in section 11, or alternatives.
9. Confirmation that the **pair concentration rule** (two full verified closures per pair per calendar quarter, reciprocal at 50% with admin approval) matches how TGL expects genuine repeat partners to behave.
10. ~~Authorise the Phase 0 plan-data correction~~ **Done** (migration 0009; Growth 6 months, Elite 12 months). Pending: the staging run of migrations 0008 and 0009.

---

## 14. Test additions for the Pair Assurance Rule

- A single ₹10L+ verified closure between a new pair pays the full 2,700 split 1,890 / 810 with the process points counted in the pair budget.
- Two verified closures in one direction both pay; the referrer's total is held at the 3,600 closed-business sub-ceiling.
- A third verified closure between the same pair pays 0 and creates an admin review item; an admin exception with a reason pays it and is audit-logged.
- A reciprocal closure pays 50% only after L4 admin approval.
- Low-assurance points between one pair stop at 1,500 and further rows are `CAPPED` with a recorded reason; verified closures are unaffected by that cap.
- The evidence upgrade moves a small deal out of the budget only after the evidence is verified; an unverified upload does not.
- Pair key is order-independent: (A, B) and (B, A) share one budget.
- Concurrent confirmations cannot award the same closure twice, or push a pair past its budget (transaction plus unique constraint).
- No pair rule can raise any member above 500 per day, 3,000 per month, or their cycle ceiling (3,600 / 6,000 / 12,000 by plan).

## 15. Test additions for subscription terms, cycles and expiry

- The cycle ceiling is derived from the plan price and the plan's stored term, never from a constant: 3,600 / 6,000 / 12,000 for the three plans.
- A member on the 12-month plan can spend 100% of the points earned in the cycle at the renewal; an expiry rule of 6 months from earning is rejected by a test that fails for the 12-month plan.
- Points expire at the end of the grace period of the renewal that closes their cycle, and not before; points earned after the renewal invoice was paid are assigned to the next cycle.
- Redemption is refused when no invoice exists, mid-term, a second time on one invoice, and above 15% of the price of the plan being bought (the cap is that of the NEW plan at renewal; there is no mid-cycle upgrade).
- A redemption is refused unless the term-and-price confirmation flag is set.
- A 3-month, a 6-month and a 12-month member with the same monthly activity redeem the same rupees a year unless a ceiling binds, and then the same percentage of the price.
- The closed-business ceiling is 60% of the cycle ceiling and one verified ₹10L+ closure (1,890 for the referrer) is paid in full on every plan.
- Daily 500 applies to low-assurance points only: a verified closure reward is not split across days.
