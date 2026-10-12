# TGL Growth Points: Business Analysis and Economic Model

> **Superseded in part: read this first.**
>
> 1. **The subscription terms in this report are wrong.** It treats Connect, Growth and Elite (₹3,000 / ₹5,000 / ₹10,000) as three prices for the same 3-month "season". The real terms are **₹3,000 / 3 months, ₹5,000 / 6 months, ₹10,000 / 12 months**. Everything below that is expressed "per season", "per 3-month season" or as a percentage of "season revenue" (₹1,760,000) rests on that error: the redemption-cap tables (sections 6-7), the earning ceilings (section 8), the plan mix revenue (section 12), the three financial models (section 13), the member scenarios (section 14), the 400-member simulation (section 15), the expiry analysis (section 16) and the ROI (section 23). The corrected model is **`GROWTH_POINTS_ECONOMY_RECALCULATION.md`**, and the corrected rules are in **`GROWTH_POINTS_FINAL_SPEC.md` (v3)**. The calculator is `growth_points_model/economy_v2.py`; the model that produced the numbers below is kept as `growth_points_model/economy_v1_superseded.py`.
> 2. The "1,500 points per pair per season" ceiling is replaced by the *Pair Assurance Rule* in the final specification.
>
> This report remains the reference for the **audit** (sections 1-5), the **interaction map and reward values** (sections 2-5, 25), the **anti-gaming, reversal and dashboard design** (sections 17-22) and the **legal and architecture questions** (sections 24, 28-32). What stays valid from the economics: 1 point = ₹0.10 and the 15% contractual cap. What does not: every rupee total and every "per season" limit.

*Status: analysis for management review. **No Growth Points code has been written.** Every number below is produced by a reproducible model (assumptions are listed in section 12 and flagged wherever they matter). Nothing here is legal or accounting advice.*

---

## 0. Executive summary

**Recommendation (corrected, v3): Model B parameters, recalculated for 3 / 6 / 12-month plans.** The table that follows replaces the original; the original is kept below for traceability only.

| Decision | Corrected recommendation |
|---|---|
| Point value | **1 point = ₹0.10** (unchanged) |
| Redemption cap | **15% of the plan price, once per subscription invoice** (unchanged) |
| Max discount (contractual) | **₹450** (₹3,000 / 3 months) · **₹750** (₹5,000 / 6 months) · **₹1,500** (₹10,000 / 12 months) |
| Earning ceiling | **500 a day (low-assurance points), 3,000 a month, 12% of the plan price per subscription cycle: 3,600 / 6,000 / 12,000 points** |
| What a member can actually save | **₹360 / ₹600 / ₹1,200** (12% of each plan's price) |
| Minimum the member still pays | **₹2,640 / ₹4,400 / ₹8,800** (never below 85% of the price; 80% if coupons are stacked) |
| Expiry | **Valid at the renewal that closes the cycle the points were earned in, plus a 30-day grace**, then they expire |
| Redemption timing | **At the renewal invoice** (window opens 30 days before the term ends); never mid-term |
| Cash value | **None.** Not transferable, not refundable, not convertible; only usable against a TGL subscription invoice |
| Expected cost (400 members) | **≈ ₹83,006 per year (1.9% of annualised revenue ₹4,440,000)** |
| Worst case (all 400 maximise) | **₹532,800 per year (12.0%)**; contractual bound ₹666,000 (15.0%) |

<details>
<summary>Original (v1) table: superseded, assumes every plan is a 3-month season</summary>

| Decision | Recommendation |
|---|---|
| Point value | **1 point = ₹0.10** (10 points = ₹1, 1,000 points = ₹100) |
| Redemption cap | **15% of the plan price, once per 3-month season invoice** |
| Max discount | **₹450** (₹3,000 plan) · **₹750** (₹5,000) · **₹1,500** (₹10,000), further limited by the earning ceiling below |
| Earning ceiling | **6,000 points (₹600) per season**, 3,000 per month, 500 per day |
| What a member can actually save | **₹450 / ₹600 / ₹600** (the ceiling binds for the two higher plans) |
| Minimum the member still pays | **₹2,550 / ₹4,400 / ₹9,400** (never below 85%; 80% if coupons are stacked) |
| Expiry | **6 months from the day points are earned**, oldest first, with a 30-day warning |
| Cash value | **None.** Not transferable, not refundable, not convertible; only usable against a TGL subscription invoice |
| Expected cost (400 members) | **≈ ₹25,386 per season (1.4% of subscription revenue)** |
| Worst case (all 400 maximise) | **₹207,000 per season (11.8% of revenue)**, and no member ever pays less than 80–85% |


</details>

The four business tests (section 27) passed for the v1 model; they were re-run on the corrected model in `GROWTH_POINTS_ECONOMY_RECALCULATION.md` (section 12) and still pass. The most important finding of the audit is different, though:

> **Growth Points do not exist yet.** The database has a `growth_points` column and the UI shows it, but *no code ever adds to it*. It is always 0. And there is **no subscription, invoice or payment system** to redeem points against, and **no way to verify a meeting or a deal value**. Those three gaps have to be closed first (section 31, Phase 0). Designing rewards on top of today's single-party "mark as done" buttons would be unsafe.

---

## 1. Existing TGL Networking feature audit

Audited: frontend (`src/`), backend (`backend/app/`), database models and migrations, admin dashboard, tests. "Exists" means working code was found.

### 1.1 Frontend

| Area | What exists | Reward-relevant fact |
|---|---|---|
| Networking Overview | Stats band, People to meet, Open needs, Referral pipeline, Recent activity, connection requests | Shows `growth_points` straight from the database (always 0) |
| Members directory + profile | Search, filters, connect state, trust tier, Growth Points figure | Metric labelled "populate from live activity"; nothing populates it |
| My Network (connections) | Request → accept / ignore / withdraw / remove (built this session) | A mutual acceptance is a real, confirmable event |
| Referrals | 5-step "Give a referral" wizard (recipient, prospect, opportunity, introduction, review), stage pipeline, accept / contacted / meeting / closed / revenue actions | The richest reward source, but see 1.3 for the verification gap |
| Need Board | Post a need, "I can help" | Offer of help only sends a notification; there is **no record of who helped or whether it was resolved** |
| Events | "My registrations" status page (registration, payment, Finale, networking) | **No attendance tracking.** One event, one season |
| Subscription page | Three plans, **₹3,000 Connect, ₹5,000 Growth, ₹10,000 Elite**, "3-month Season 1 membership" | **Product copy only.** "No payment gateway is wired up yet"; choosing a plan shows a toast |
| Notifications | In-app list, 10 types | No reward notifications |
| Vertex | Static provider directory with an enquiry dialog | Not part of the networking economy |
| Copy that already promises points | Subscription plan list, Overview ("From referrals and closed business"), referral stage help ("Growth Points are earned"), Locked page, Module modal | **Members are already told points exist.** Launch or soften this copy |

### 1.2 Backend and database

| Capability | Status |
|---|---|
| `networking_profiles.growth_points`, `trust_score` | Columns exist; **read-only in practice, never written** |
| Referral lifecycle (`business_referrals`) | Exists: GIVEN → ACCEPTED → CONTACTED → MEETING_DONE → BUSINESS_CLOSED → REVENUE_GENERATED, plus DECLINED / CANCELLED / CLOSED. Unique index stops duplicate live referrals of the same prospect (same referrer, recipient, phone). `quality` is derived server-side (CONTACT_ONLY, WARM_REFERRAL, DIRECT_INTRO, MEETING_ARRANGED). Timestamps for every stage |
| Referral value | Only `value_range` (UNKNOWN, <₹25k, ₹25k–1L, ₹1L–5L, ₹5L+): **an estimate typed by the referrer at creation**. **No actual deal value is captured at closure** |
| Connections | `status` PENDING / ACCEPTED / DECLINED (migration 0007) |
| Meetings | **No meeting entity.** `MEETING_DONE` is a status flag either member can set alone |
| Introductions (A introduces B to C) | **Does not exist** |
| Mentoring | Two profile flags (`open_to_mentoring`, `seeking_mentor`). No sessions |
| Member invitations | **Does not exist** (registration only) |
| Testimonials / recommendations | **Does not exist** |
| Events | One `events` row with `completed_at`; **no attendance or check-in** |
| Subscription / invoice / payment tables | **None.** Only `event_registrations` with a manual payment-proof review by an admin; memberships are created from event registrations (`source_event_registration_id` is mandatory) |
| Audit log | **None** (only request timing logs and notifications) |
| Ledger / transactions | **None** |
| Rate limiting | In-process sliding window. Fine for one server; **not shared across instances** |
| Idempotency | Present for referral creation (unique index). Not generalised |
| Admin panel | Registration verification, customer list, finale control, capacity stats, and `GET /api/admin/referrals/stats` (counts only). **No UI** for referral management, member rewards or revenue |
| Capacity | 10 categories × 40 slots = **400 members** (`slots_per_category`) |

### 1.3 Gaps that block a safe reward system

1. **Single-party confirmation.** Either member can move a referral to MEETING_DONE or BUSINESS_CLOSED alone. Two colluding accounts can "close" unlimited fake deals.
2. **No deal value at closure**, and nothing to prove it.
3. **No subscription/invoice system** to apply a discount to.
4. **No audit trail** and **no ledger**.
5. **Reward-bearing features that don't exist yet:** introductions, matching, mentoring sessions, invitations, event check-in, need resolution.

---

## 2. Complete interaction map

Legend: *Verify* = Can the system verify it today? Reversible = should a reward be clawed back if it later proves false?

| # | Action | Performed by | Who benefits | Business value | Who earns | When paid | Abuse risk | Verify today? | Fixed / variable | Reversible | In code? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Give a referral | Referrer (A) | Recipient (B) | Lead supplied | **Nobody yet** | n/a | **High** (spam, fakes) | System can check uniqueness only | 0 | n/a | Yes |
| 2 | Referral accepted | Recipient (B) | A, B | Signals a real, wanted lead | A (+bonus for quality), B | After acceptance, held 7 days | Medium (colluding accept) | By B alone: L1 | Fixed | Yes | Yes |
| 3 | Prospect contacted | B | A, prospect | Speed to lead | B | After acceptance | Medium (B says so) | L1 | Fixed (bonus only within 72h) | Yes | Yes (`CONTACTED`) |
| 4 | Meeting completed | A and B | Both | Real conversation | A and B | When **both** confirm | **High** | **No** (single flag) | Fixed | Yes | Partial: needs two-party confirmation |
| 5 | Proposal / discussion | B | B | Progress | **Nobody** (no independent proof) | n/a | High | No | 0 | n/a | No |
| 6 | **Business closed** | B reports, A confirms | Both (B earns revenue) | **Real revenue** | A (larger share), B | After verification, tiered | **Highest** | **No** (no value, no proof) | Tiered by band, hard cap | Yes (60 days) | Partial: needs value + confirmation + evidence |
| 7 | Repeat business via same prospect | B | Both | Retention of the lead | A and B | Verified | High | No | 50% of the original band, once per prospect per season | Yes | No |
| 8 | Receive a referral | B | B | n/a | **No separate reward** (acceptance is the event) | n/a | n/a | n/a | n/a | n/a | n/a |
| 9 | Introduce two members (A introduces B and C) | Connector (A) | B, C | Relationship created | A | Both confirm; bonus if a meeting follows | Medium | No | Fixed | Yes | **No (future)** |
| 10 | Match a need with a member | Helper | Poster | Need solved | Helper | Poster confirms "resolved by X" | Medium | No | Fixed | Yes | **Partial:** offer exists, resolution does not |
| 11 | Attend an event | Member | Member, community | Community strength | Member | After admin check-in | Medium | **No** | Fixed | Yes | **No (future)** |
| 12 | Host an activity | Member | Community | Value to others | Member | Admin approves | Low | No | Fixed (once per season) | Yes | **No (future)** |
| 13 | Mentor another member | Mentor | Mentee | Knowledge | Mentor | Mentee confirms session | Medium | No | Fixed | Yes | **No (future)** (flags only) |
| 14 | Invite a legitimate new member | Inviter | TGL | New revenue | Inviter | New member's payment verified and 30 days active | **High** (fake accounts) | Yes once payment exists | Fixed | Yes | **No (future)** |
| 15 | Complete profile | Member | Member, directory | Better matching | Member | System check | Low | **Yes** | Fixed, once | No | Yes |
| 16 | Post a business need | Member | Community | Demand signal | **Nobody** (spam risk, and the helper is the one who creates value) | n/a | High | n/a | 0 | n/a | Yes |
| 17 | Respond to a need | Responder | Poster | Offer only | **Nobody** until resolved (row 10) | n/a | High | n/a | 0 | n/a | Yes |
| 18 | Accept a connection | Target | Both | Network edge | **Nobody** (no business value on its own) | n/a | High (fake accounts) | Yes | 0 | n/a | Yes |
| 19 | Testimonial / recommendation | Member | Recipient | Social proof | Optional later: admin-approved, small | Admin approval | Medium | No | Fixed, 2 per season | Yes | **No** |
| 20 | Collaboration / partnership | Both | Both | Joint business | **Treat as a closed deal** (row 6) with both parties confirming | Verified | High | No | Tiered | Yes | No |
| 21 | View a profile, open a notification, refresh, like | Anyone | n/a | None | **0 points. Never.** | | | | | | |

---

## 3. Recommended reward events

Philosophy: **value created > activity count.** Rewards follow a ladder: *intent* earns nothing, *counterparty confirmation* earns little, *both-party confirmation* earns more, *verified business* earns the most, and everything sits under hard ceilings.

- **Zero:** creating a referral, posting a need, replying to a need, accepting a connection, viewing, liking, logging in.
- **Pays:** accepted referrals, confirmed meetings, verified closed business, confirmed introductions, resolved needs, checked-in events, confirmed mentoring, activated invited members, a completed profile.
- **Built today:** referral stages and profile completion. **Needs new features first:** introductions, need resolution, event check-in, mentoring sessions, invitations (see roadmap).

---

## 4. Roles

Every referral has **three** parties and the points must never mix them up:

| Role | Who | Example | Earns |
|---|---|---|---|
| **Referrer** (A) | The signed-in member who gives the referral | Roshan | Mostly on **quality and outcome** |
| **Recipient** (B) | The TGL member who receives it | Arjun, Arjun Digital Solutions | On **action**: accept fast, contact, meet, close |
| **Prospect** (C) | The outside customer. **Not a TGL member.** Never earns anything | Priya, XYZ Restaurant | Nothing. Their contact details never appear in rewards, feeds or announcements |

The existing schema already keeps this separation (`giver_user_id`, `receiver_user_id`, and `prospect_*` columns).

---

## 5. Referral reward lifecycle

| Stage | Referrer (A) | Recipient (B) | Proof required | Reversible? |
|---|---:|---:|---|---|
| Created | **0** | 0 | System: unique, valid, rate-limited | n/a |
| Accepted | **30** (+15 if the referrer arranged the introduction: `DIRECT_INTRO` or `MEETING_ARRANGED`) | **15** | B accepts (L1) | Yes, if declined or cancelled before release |
| Prospect contacted | 0 | **15** (only within 72 hours of acceptance) | B marks it; A can dispute within 7 days (L1) | Yes |
| Meeting completed | **45** | **60** | **Both confirm** (L2) | Yes |
| Proposal / discussion | 0 | 0 | No independent proof exists | n/a |
| Business closed | **70% of the band pool** | **30% of the band pool** | Both confirm. Over ₹1L needs evidence; over ₹5L needs admin check (L3 / L4) | Yes, 60 days |
| Repeat business, same prospect | 50% of the original pool, once per season | same | As above | Yes |

Why creation pays 0: if the *act of sending* paid anything, then "send 100 referrals" beats "send one good one". The referrer's first reward arrives only when a real member accepts it.

Why the numbers: they come from a ceiling-first design (sections 6 to 9). The per-action values were chosen so that a **top performer reaches the season ceiling with roughly three to four verified mid-sized deals plus ordinary activity**, an **average member earns about ₹70**, and no single deal can pay more than ₹270 in total.

---

## 6. Point-to-rupee economy (Phase 5)

Points needed for a given discount, under three unit values:

| Discount | ₹0.05 / pt (20 pts = ₹1) | ₹0.10 / pt (10 pts = ₹1) | ₹0.20 / pt (5 pts = ₹1) |
|---|---:|---:|---:|
| ₹100 | 2,000 | 1,000 | 500 |
| ₹250 | 5,000 | 2,500 | 1,250 |
| ₹500 | 10,000 | 5,000 | 2,500 |
| ₹1,000 | 20,000 | 10,000 | 5,000 |
| ₹2,000 | 40,000 | 20,000 | 10,000 |
| ₹3,000 | 60,000 | 30,000 | 15,000 |
| ₹5,000 | 100,000 | 50,000 | 25,000 |
| ₹10,000 | 200,000 | 100,000 | 50,000 |

Models D and E in the brief are the same as ₹0.05 and ₹0.10 per point. Model F (percentage discounts) was rejected: points would mean a different rupee amount on each plan, so a member could never answer "what are my points worth?".

**Recommendation: ₹0.10 per point.** 10 points = ₹1 and 1,000 = ₹100, so the arithmetic is easy; the smallest meaningful action (15 points) is ₹1.50; balances stay in the hundreds and thousands rather than tens of thousands. At ₹0.05 the numbers are twice as large with no benefit; at ₹0.20 rewards get too coarse (the ₹1.50 acceptance reward would be 7.5 points).

> The unit does **not** protect TGL. What protects TGL is the **rupee ceiling** (cap on redemption, cap on earning). Changing the unit without changing those changes nothing financially.

---

## 7. Redemption cap comparison (Phases 6, 7, 16)

Prices are per 3-month season (as shown on the Subscription page). The maximum discount a points system could ever give:

| Plan (per 3-month season) | 10% | 15% | 20% | 25% |
|---|---|---|---|---|
| ₹3,000 | ₹300 → pay ₹2,700 | ₹450 → pay ₹2,550 | ₹600 → pay ₹2,400 | ₹750 → pay ₹2,250 |
| ₹5,000 | ₹500 → pay ₹4,500 | ₹750 → pay ₹4,250 | ₹1,000 → pay ₹4,000 | ₹1,250 → pay ₹3,750 |
| ₹10,000 | ₹1,000 → pay ₹9,000 | ₹1,500 → pay ₹8,500 | ₹2,000 → pay ₹8,000 | ₹2,500 → pay ₹7,500 |

In points (at ₹0.10):

| Plan | 10% cap (points) | 15% | 20% | 25% |
|---|---:|---:|---:|---:|
| ₹3,000 | 3,000 | 4,500 | 6,000 | 7,500 |
| ₹5,000 | 5,000 | 7,500 | 10,000 | 12,500 |
| ₹10,000 | 10,000 | 15,000 | 20,000 | 25,000 |

Financial exposure for a 400-member network (revenue ₹1,760,000 per season on an assumed plan mix, section 12):

| Cap | Worst case: every member redeems the full cap | % of season revenue | Worst case with the 6,000-pt earning ceiling | % of revenue | Expected (Model B behaviour) | % of revenue |
|---|---:|---:|---:|---:|---:|---:|
| 10% | ₹176,000 | 10.0% | ₹160,000 | 9.1% | ₹23,036 | 1.3% |
| 15% | ₹264,000 | 15.0% | ₹207,000 | 11.8% | ₹25,386 | 1.4% |
| 20% | ₹352,000 | 20.0% | ₹240,000 | 13.6% | ₹27,036 | 1.5% |
| 25% | ₹440,000 | 25.0% | ₹240,000 | 13.6% | ₹27,036 | 1.5% |

What this says:
- **The earning ceiling is a stronger safeguard than the percentage.** With a 6,000-point ceiling, going from 20% to 25% adds no exposure at all, because nobody can earn enough to use the extra room.
- 10% is the safest but gives the ₹3,000 member at most ₹300. 20% costs +₹33k in the worst case over 15% for a modest gain. 25% adds nothing beyond 20% under this ceiling and should be rejected on principle.
- **15% is recommended.** It is meaningful (₹450 on the entry plan), keeps the member paying at least 85%, and keeps the worst case at 11.8% of revenue.

### Payment floor (Phase 7)

| Plan | Min pay @85% | Min pay @80% | Min pay @75% | Max discount @85% floor | @80% floor | @75% floor |
|---|---:|---:|---:|---:|---:|---:|
| ₹3,000 | ₹2,550 | ₹2,400 | ₹2,250 | ₹450 | ₹600 | ₹750 |
| ₹5,000 | ₹4,250 | ₹4,000 | ₹3,750 | ₹750 | ₹1,000 | ₹1,250 |
| ₹10,000 | ₹8,500 | ₹8,000 | ₹7,500 | ₹1,500 | ₹2,000 | ₹2,500 |

Recommendation: the floor is **85% for points alone**, and an **80% floor on all discounts combined** (points plus any coupon). 75% is rejected: it would let a stacked coupon take 25% off and defeat the cap. The server must enforce the floor at checkout, not just the UI.

---

## 8. Earning ceilings (Phase 8)

Recommended (Model B): **500 points per day, 3,000 per month, 6,000 per season (₹600).** Sub-ceilings per season: referral process (accepted, contacted, meeting) 1,500; closed business 3,600; everything else 1,200. The anti-collusion limit between two members is set out in the final specification (*Pair Assurance Rule*): low-assurance points are capped at 1,500 per pair per season, while evidence-verified closures are rewarded in full under a concentration rule.

Why a ceiling is as important as the redemption cap: points above what can be redeemed are pure liability. 20,000 earned and 2,000 redeemable leaves 18,000 sitting on the books. The ceiling keeps earning close to what can be spent: a ₹3,000-plan member can redeem 4,500 points (₹450) per season and earn at most 6,000.

Expected earning by member type (Model B), 3-month season:

| Member type | Members | Referral-process pts | Closed-business pts | Other pts | Earned per season | Worth |
|---|---:|---:|---:|---:|---:|---:|
| Low | 240 | 40 | 0 | 75 | 115 | ₹12 |
| Average | 100 | 260 | 190 | 240 | 690 | ₹69 |
| High | 40 | 795 | 1,120 | 690 | 2,605 | ₹260 |
| Top | 20 | 1,550 | 4,390 | 1,620 | 6,000 (ceiling) | ₹600 |

Assumed activity per member per season is in section 12. "Top" members exceed the ceiling on raw activity and are capped at 6,000; **that is the design working**.

---

## 9. Rewarding big deals without a big liability (Phase 9)

Four ways to reward closed business, shown for the midpoint of each deal band:

| Deal band (midpoint used) | 1 · Fixed | 3 · Base + value bonus (cap 1,800) | 2 · Tiered pool, hard-capped (recommended) | 4 · 0.25% of deal value, capped 2,500 | Model 4 worth |
|---|---:|---:|---:|---:|---:|
| Under ₹25k (mid ₹15,000) | 1,000 | 158 | 300 | 375 | ₹38 |
| ₹25k–₹1L (mid ₹60,000) | 1,000 | 180 | 750 | 1,500 | ₹150 |
| ₹1L–₹5L (mid ₹250,000) | 1,000 | 275 | 1,500 | 2,500 | ₹250 |
| ₹5L–₹10L (mid ₹700,000) | 1,000 | 500 | 2,100 | 2,500 | ₹250 |
| ₹10L+ (mid ₹1,500,000) | 1,000 | 900 | 2,700 | 2,500 | ₹250 |

- **Fixed** pays ₹100 for a ₹15,000 job and the same for a ₹15 lakh one: wrong signal.
- **Percentage-based** (even at 0.25%) reaches the ceiling fast and ties TGL's cost to *someone else's* deal value, which is not under TGL's control or verifiable.
- **Base + bonus** barely rewards small and mid deals.
- **Tiered pool with a hard cap (recommended):** a ₹10L+ deal and a ₹5L deal differ by ₹60. **No deal, however large, costs TGL more than ₹270 in points.**

Recommended closure pools, split 70% referrer / 30% recipient:

| Deal band | Pool (pts) | Pool worth | Referrer 70% | Receiver 30% | Pool as % of deal value | Pool as % of a ₹3,000 plan |
|---|---:|---:|---:|---:|---:|---:|
| Under ₹25k | 300 | ₹30 | 210 | 90 | 0.20% | 1.0% |
| ₹25k–₹1L | 750 | ₹75 | 525 | 225 | 0.12% | 2.5% |
| ₹1L–₹5L | 1,500 | ₹150 | 1,050 | 450 | 0.06% | 5.0% |
| ₹5L–₹10L | 2,100 | ₹210 | 1,470 | 630 | 0.03% | 7.0% |
| ₹10L+ | 2,700 | ₹270 | 1,890 | 810 | 0.02% | 9.0% |

The pool is **at most 0.2% of any deal's value** (0.02% on a ₹10L+ deal) and never above 9% of one entry-level plan, and each member is still bound by the season ceiling.

---

## 10. Referrer versus recipient (Phase 10)

The recipient earns the actual revenue from the deal; the referrer earns nothing from it. So the points should favour the referrer on outcome while the recipient is paid for *behaviour* (responding, contacting, meeting).

| Closure split (referrer / receiver) | Referrer closure pts (₹1L–₹5L deal) | Receiver closure pts | Referrer whole-lifecycle pts | Receiver whole-lifecycle pts | Lifecycle share |
|---|---:|---:|---:|---:|---:|
| 60 / 40 | 900 | 600 | 984 | 690 | 59% / 41% |
| 70 / 30 | 1,050 | 450 | 1,134 | 540 | 68% / 32% |
| 75 / 25 | 1,125 | 375 | 1,209 | 465 | 72% / 28% |
| 80 / 20 | 1,200 | 300 | 1,284 | 390 | 77% / 23% |

**Recommendation: 70 / 30 on the closure pool**, with the recipient earning the larger share of the *process* rewards (meeting 60 vs 45, plus acceptance and contact). Across the whole lifecycle that comes to about **68% / 32%**. 60/40 over-pays the party who is already being paid by the customer; 80/20 makes recipients indifferent.

---

## 11. Verification levels (Phase 11)

| Level | Meaning | Points | Release |
|---|---|---|---|
| **L0** | Self-reported, no counterparty | **0** | never |
| **L1** | Counterparty confirms a single step | Small (15 to 30) | `PENDING` for 7 days (dispute window), then `AVAILABLE` |
| **L2** | **Both parties confirm** (meeting, introduction, need resolved, closed deal up to ₹1L) | Moderate (45 to 750) | Pending 7 days |
| **L3** | System- or evidence-verified (event check-in by admin, invoice/UPI proof for a deal over ₹1L, activated member payment) | Higher | After verification |
| **L4** | Admin / business verification (deals over ₹5L, any flagged deal, anything public) | Highest (up to 2,700) | After admin approval |

Hard rules: **the frontend never supplies points, deal value, role, user id, or status. It only sends *intent*** (for example "I confirm this meeting happened"). The server reads the referral, checks who is calling, checks the other side's confirmation and looks up the rule.

---

## 12. Assumptions used in every number

These are **assumptions, not facts from the project**. The model should be re-run when real data exists.

1. Plans are priced **per 3-month season** (Subscription page: "3-month Season 1 membership"). If TGL bills monthly instead, the percentage caps still hold; the rupee figures scale accordingly. The brief's "monthly redemption ceiling" is therefore applied **per subscription invoice** (one season). **Management must confirm.**
2. **400 members**, from capacity (10 categories × 40 slots).
3. **Plan mix 55% ₹3,000 / 35% ₹5,000 / 10% ₹10,000** (no subscription data exists). Average ₹4,400, season revenue ₹1,760,000.
4. Member behaviour mix (as in the brief): 60% low (240), 25% average (100), 10% high (40), 5% top (20).
5. Activity per member per season (small amounts of introductions, need help and profile completion are also included in the model): Low 0.6 accepted referrals, no closed deals; Average 2 accepted referrals given, 2 received, 1.2 meetings, 0.25 closed deals as referrer; High 6 and 5 referrals, 4 meetings, 1 closed deal, 2.5 events; Top 12 and 8 referrals, 8 meetings, 3 closed deals including ₹10L+ ones, 3 events, 3 mentoring sessions, 1 invitation.
6. Share who actually redeem: Low 30%, Average 70%, High 90%, Top 100%.
7. Deal value bands use their midpoints for ROI.
8. GST and payment-gateway charges are ignored (see section 24).

---

## 13. The three financial models (Phase 15)

|  | A · Very conservative | B · Balanced (recommended) | C · High reward |
|---|---|---|---|
| Point value | ₹0.10 | ₹0.10 | ₹0.10 |
| Reward scale vs Model B table | ×0.5 | ×1.0 | ×1.5 |
| Valid referral accepted (referrer / receiver) | 15 / 8 pts | 30 / 15 pts | 45 / 22 pts |
| Meeting confirmed by both (referrer / receiver) | 22 / 30 pts | 45 / 60 pts | 68 / 90 pts |
| Closed business, ₹1L–₹5L (total pool) | 750 pts (₹75) | 1,500 pts (₹150) | 2,250 pts (₹225) |
| Closed business, ₹10L+ (hard max pool) | 1,350 pts (₹135) | 2,700 pts (₹270) | 4,050 pts (₹405) |
| Event attendance | 22 pts (max 3/season) | 45 pts (max 3/season) | 68 pts (max 3/season) |
| Earning ceiling: day / month / season | 250 / 1,500 / 3,000 pts | 500 / 3,000 / 6,000 pts | 800 / 5,000 / 10,000 pts |
| Max season earning in rupees | ₹300 | ₹600 | ₹1,000 |
| Redemption cap (of plan price) | 10% | 15% | 20% |
| Max discount ₹3,000 / ₹5,000 / ₹10,000 | ₹300 / ₹300 / ₹300 (after earning ceiling) | ₹450 / ₹600 / ₹600 (after earning ceiling) | ₹600 / ₹1,000 / ₹1,000 (after earning ceiling) |
| Minimum the member pays (₹3,000 / 5,000 / 10,000) | ₹2,700 / ₹4,700 / ₹9,700 | ₹2,550 / ₹4,400 / ₹9,400 | ₹2,400 / ₹4,000 / ₹9,000 |
| Expiry | 3 months | 6 months | 12 months |
| Expected realised cost / season (400 members) | ₹13,491 (0.8%) | ₹25,386 (1.4%) | ₹38,127 (2.2%) |
| Worst-case liability / season (all 400 maximise) | ₹120,000 (6.8%) | ₹207,000 (11.8%) | ₹312,000 (17.7%) |
| Abuse risk | Lowest | Low–moderate (controls below) | Moderate–high |
| Complexity | Lowest | Moderate | Moderate |
| Member attractiveness | Weak: an average member earns ~₹35 | Good: a high performer earns ~₹260, a top performer reaches the cap | Strongest, but cost and fraud incentive rise ~50% |

**Model A** protects TGL most, but an average member would earn ~₹35 per season, which does not feel like a reward. **Model C** is attractive but raises worst-case exposure to 17.7% of revenue and gives fraudsters a 50% bigger prize per fake action. **Model B** keeps expected cost around 1.4% of revenue with a top-performer reward that is clearly noticeable.

---

## 14. Member scenarios on the real plans (Phases 16, 17, 30), Model B

| Scenario | Plan | Points earned / season | Worth | Redeemed (after cap) | Discount % | Member still pays |
|---|---|---:|---:|---:|---:|---:|
| 1. Normal active | ₹3,000 | 690 | ₹69 | ₹69 | 2.3% | ₹2,931 |
| 1. Normal active | ₹5,000 | 690 | ₹69 | ₹69 | 1.4% | ₹4,931 |
| 1. Normal active | ₹10,000 | 690 | ₹69 | ₹69 | 0.7% | ₹9,931 |
| 2. Highly active | ₹3,000 | 2,605 | ₹260 | ₹260 | 8.7% | ₹2,740 |
| 2. Highly active | ₹5,000 | 2,605 | ₹260 | ₹260 | 5.2% | ₹4,740 |
| 2. Highly active | ₹10,000 | 2,605 | ₹260 | ₹260 | 2.6% | ₹9,740 |
| 3. Top performer | ₹3,000 | 6,000 | ₹600 | ₹450 | 15.0% | ₹2,550 |
| 3. Top performer | ₹5,000 | 6,000 | ₹600 | ₹600 | 12.0% | ₹4,400 |
| 3. Top performer | ₹10,000 | 6,000 | ₹600 | ₹600 | 6.0% | ₹9,400 |
| 4. Maximiser (hits every ceiling) | ₹3,000 | 6,000 | ₹600 | ₹450 | 15.0% | ₹2,550 |
| 4. Maximiser (hits every ceiling) | ₹5,000 | 6,000 | ₹600 | ₹600 | 12.0% | ₹4,400 |
| 4. Maximiser (hits every ceiling) | ₹10,000 | 6,000 | ₹600 | ₹600 | 6.0% | ₹9,400 |

Reading this table: even the maximiser who hits every ceiling saves **₹450 on the ₹3,000 plan, ₹600 on ₹5,000, ₹600 on ₹10,000**, and the ₹10,000 member would have to earn the ceiling about **17 times** in one season to reach their price.

---

## 15. Network-level simulation, 400 members (Phases 17 and 18)

Members: 240 low, 100 average, 40 high, 20 top. Plan mix as in section 12.

| Model | Points issued / season | Worth | Expected redeemed (realised cost) | % of revenue | Points outstanding (before expiry) | Outstanding worth | Max potential liability (all maximise) | % of revenue |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A · Very conservative | 159,700 | ₹15,970 | ₹13,491 | 0.8% | 24,790 | ₹2,479 | ₹120,000 | 6.8% |
| B · Balanced | 320,800 | ₹32,080 | ₹25,386 | 1.4% | 66,940 | ₹6,694 | ₹207,000 | 11.8% |
| C · High reward | 500,500 | ₹50,050 | ₹38,127 | 2.2% | 119,230 | ₹11,923 | ₹312,000 | 17.7% |

Stress scenarios 5 and 6:

| Model | Scenario | Points issued | Worth | Redeemed (cost) | % of revenue |
|---|---|---:|---:|---:|---:|
| A | 5. 10% (40 members) at ceiling, rest 70/30 low/avg | 171,120 | ₹17,112 | ₹15,024 | 0.9% |
| A | 6. All 400 maximise | 1,200,000 | ₹120,000 | ₹120,000 | 6.8% |
| B | 5. 10% (40 members) at ceiling, rest 70/30 low/avg | 343,500 | ₹34,350 | ₹26,786 | 1.5% |
| B | 6. All 400 maximise | 2,400,000 | ₹240,000 | ₹207,000 | 11.8% |
| C | 5. 10% (40 members) at ceiling, rest 70/30 low/avg | 554,620 | ₹55,462 | ₹40,310 | 2.3% |
| C | 6. All 400 maximise | 4,000,000 | ₹400,000 | ₹312,000 | 17.7% |

Interpretation (Model B):
- **Realistic cost:** about ₹25,386 per season (1.4% of revenue).
- **Points outstanding at the end of a season** (before expiry): 66,940 points (₹6,694), mostly low and average members who never redeem, plus maxed-out entry-plan members whose earnings exceed their ₹450 cap.
- **Maximum potential liability** is ₹207,000 (11.8% of revenue) and requires every one of 400 members to hit every ceiling and redeem. It is a cap, not a forecast.
- **TGL's worst-case position stays survivable**: even then 88.2% of revenue is collected.

---

## 16. Expiry policy (Phase 13)

What happens to a ₹3,000-plan member who earns the full 6,000 points every season and redeems the 4,500-point maximum (so 1,500 are left over each season), after 3 years:

| Expiry | Unredeemed points after 3 years (₹3,000 member who earns the ceiling every season) | Worth | % of one plan | Peak balance |
|---|---:|---:|---:|---:|
| 3 months | 1,500 | ₹150 | 5% | 1,500 |
| 6 months | 7,500 | ₹750 | 25% | 7,500 |
| 12 months | 18,000 | ₹1,800 | 60% | 18,000 |
| No expiry | 18,000 | ₹1,800 | 60% | 18,000 |

**Recommendation: points expire 6 months after the day they were earned, oldest first (FIFO).** That caps a maxed-out member's carried balance at about ₹750 (25% of a plan) rather than ₹1,800 (60%) and still gives two renewal windows. Also:
- Warn members 30 days before points expire ("100 points expire soon").
- **Pending** points that are never confirmed lapse after 60 days.
- Points are void on suspension for fraud.
- 3 months is too harsh (a member who earns in month 1 of a season has one chance to use them); 12 months or none builds a liability close to a full plan.

---

## 17. Transfer, cash and redemption rules (Phases 14, 20, 21)

| Rule | Decision |
|---|---|
| Transfer between members | **No** |
| Sell / trade | **No** |
| Convert to cash, cash refund, pay another member | **No** |
| Usable for | **Eligible TGL subscription invoices only** |
| Frequency | **Once per invoice**, up to the cap and floor |
| Stacking with coupons | **Only if the combined discount stays ≤ 20%** (floor 80%). Otherwise points and coupons are mutually exclusive |
| Upgrades | Allowed. The 15% cap is computed on the **new plan's price**, once per season; no re-use by downgrading after purchase |
| After cancellation | Points are **frozen**, still expire on schedule, and are usable only if the member re-subscribes before expiry |
| Refunds | Only **cash actually paid** is refunded. Points used are re-credited only for a refund within 7 days and only if not yet expired |
| Rounding | Whole rupees; the member sees the calculation before confirming |

Worked examples (₹0.10 per point, 15% cap, Model B):

| Member | Plan | Points | Worth | Cap (15%) | Redeemed | Member pays |
|---|---|---:|---:|---:|---:|---:|
| Priya | ₹3,000 | 4,800 | ₹480 | ₹450 | **₹450** (4,500 pts; 300 stay for next time) | **₹2,550** |
| Arjun | ₹3,000 | 2,300 | ₹230 | ₹450 | **₹230** | **₹2,770** |
| Meera | ₹5,000 | 50,000* | ₹5,000 | ₹750 | **₹750** | **₹4,250** |

\*50,000 points cannot occur under the earning ceiling; it is shown to prove the cap holds even if an error or bug creates a huge balance. **The cap and floor must be enforced at redemption, not just at earning.**

---

## 18. Anti-gaming system (Phase 12)

| Attack | Defence |
|---|---|
| Same referral submitted repeatedly | **Already enforced:** unique index per referrer, recipient and prospect phone for live referrals. Rewards also keyed by `(event, referral, member)` so retries never pay twice |
| Referral spam | Creation pays 0; acceptance pays. Referrers with an acceptance rate under 30% over 10+ referrals earn half on process rewards. At most 10 rewarded acceptances per month |
| Self-referral | Blocked server-side (referrer ≠ recipient). Referring a prospect whose phone/email matches a member's own is flagged |
| Circular referrals (A→B→A) | **Pair Assurance Rule** (final spec): 1,500-point budget per pair for low-assurance points; verified closures exempt but limited to two full-reward closures per pair per season, reciprocal closures need admin approval and pay 50% |
| Fake meetings | Both parties must confirm; a meeting cannot be confirmed before the referral has been accepted; a minimum time gap after acceptance |
| Fake / inflated deal values | Deal value bands are captured **at closure** (not at creation) and confirmed by both; over ₹1L needs evidence; over ₹5L needs admin approval. Points are by band, so a 5% change in value rarely changes the reward |
| Fake accounts / collusion | Rewards need a verified, active, paid membership on **both** sides; invitation rewards only after the invitee's payment is verified and 30 days active; pair rule, daily, monthly and season ceilings |
| Event attendance manipulation | Admin check-in only; one reward per member per event; 3 per season |
| Duplicate API calls / race conditions | Unique `(member, event_type, reference_type, reference_id)` constraint; transactions; the reward is written in the same transaction as the state change |
| Forged IDs, points, status or deal value | The server derives everything from the stored referral and the session; the request carries only intent |
| Suspicious patterns | Daily job flags: same two members repeating, closed deals with no prior contact, deals closing within minutes of acceptance, many closures at the same value band |
| Reversal | Negative ledger entries; clawback window 60 days after verification |
| Audit | Append-only ledger plus an audit log of every admin action |

---

## 19. Reversals

| Trigger | Effect |
|---|---|
| Referral declined, cancelled or closed before release | Pending points voided |
| Meeting confirmation withdrawn or disputed within 7 days | Pending points voided |
| Deal disputed, refunded or found false within 60 days | Negative ledger entry for both parties; unredeemed points reduced; if already redeemed, the case goes to an admin (T&C must allow action; no automatic cash recovery) |
| Fraud confirmed | Void all points from that interaction, apply a ceiling reduction or suspension, admin note |
| Admin adjustment | Always a ledger entry with reason and admin id |

---

## 20. Community milestone notification (Phase 23)

Recommended model:
- **Who sees it:** signed-in Networking members only (not public), shown in the activity feed, not as a push.
- **When:** only after Level 3/4 verification, for deals in the ₹1L+ bands, with a 24-hour delay so a dispute can stop it. An admin can suppress any one.
- **What it shows:** *"TGL Growth Milestone: two members generated business worth approximately ₹1L–₹5L through the network."* Names only when **both** members opt in at the closing step ("Share this win with the community"). Otherwise it is anonymous.
- **Never shown:** prospect name, phone, email, company, exact deal value, or the recipient's business if they did not opt in.
- Members can turn announcements off in settings.

Showing ranges, not exact values, protects commercial privacy and avoids members being asked "what did you earn?".

---

## 21. Member dashboard (Phase 24)

```
GROWTH POINTS                     APPROXIMATE VALUE
1,250                              ₹125
Available                          Toward your next subscription

THIS MONTH      +300      PENDING  +200 (released after 7 days)
EXPIRING SOON   100 pts on 14 Dec 2026

MAXIMUM DISCOUNT ON YOUR PLAN (₹3,000, 15% cap):  ₹450
You can use up to 4,500 points. You would pay at least ₹2,550.

HOW YOU EARNED THEM
Referral accepted ........ +45      Meeting completed ...... +45
Verified business closed . +1,050   Subscription redemption  -250
```

Also show: the earning ceiling used this season (e.g. "3,200 of 6,000"), a plain-language "what counts" page, and the exact calculation before any redemption.

---

## 22. Admin and management dashboard (Phase 25)

Totals: points **issued, redeemed, expired, reversed, outstanding**; **outstanding INR-equivalent**; average points per member; top earners; top referral contributors; business generated by band; conversion (accepted → meeting → closed); renewal rate for members who redeemed versus those who did not; points-to-business ratio.

Two figures must be shown **side by side and never merged**:

| | Definition |
|---|---|
| **Maximum potential subscription liability** | Σ over active members of min(unexpired points × ₹0.10, cap% × the member's next invoice). The most TGL could be asked to give up |
| **Realised reward cost** | Σ of actual redemptions (₹ discounts applied on invoices) |

Plus: a fraud queue (flagged patterns), pending verification queue (deals waiting for admin), and a manual-adjustment form that always writes a ledger entry.

---

## 23. ROI (Phase 26)

Growth Points are a **retention and engagement expense**, not revenue. Two views:

**Business created per rupee of reward** (modelled: 125 referrer-closed deals per season, ₹3.84 crore):

| Model | Business generated through the network / season | Value | Realised reward cost | Business per ₹1 of reward |
|---|---|---:|---:|---:|
| A | modelled business | ₹38,362,500 | ₹13,491 | 2,844× |
| A | 25% of modelled (sceptical) | ₹9,590,625 | ₹13,491 | 711× |
| B | modelled business | ₹38,362,500 | ₹25,386 | 1,511× |
| B | 25% of modelled (sceptical) | ₹9,590,625 | ₹25,386 | 378× |
| C | modelled business | ₹38,362,500 | ₹38,127 | 1,006× |
| C | 25% of modelled (sceptical) | ₹9,590,625 | ₹38,127 | 252× |

This ratio is large because rewards are tiny against deal values; it is **not TGL revenue**: that business belongs to the members.

**The test that matters: retention.** TGL breaks even if rewards raise the renewal probability of redeeming members by:

| Model | Assumed margin on a subscription | Avg cost per redeeming member | Avg plan price | Renewal uplift needed to break even |
|---|---:|---:|---:|---:|
| A | 50% | ₹68 | ₹4,400 | 3.1% |
| A | 70% | ₹68 | ₹4,400 | 2.2% |
| B | 50% | ₹128 | ₹4,400 | 5.8% |
| B | 70% | ₹128 | ₹4,400 | 4.2% |
| C | 50% | ₹193 | ₹4,400 | 8.8% |
| C | 70% | ₹193 | ₹4,400 | 6.3% |

Model B needs about a **4 to 6 percentage-point** improvement in renewals among members who redeem to break even. Because redeemers are by definition the most engaged members, this is plausible but **unproven**, so run the first season in shadow mode (section 31) and measure.

---

## 24. Accounting and legal questions (Phase 27)

*Questions for professional accounting/legal review. Not conclusions.*

1. How should unredeemed points be recorded: a contingent liability, a provision, or a deferred discount? Does it depend on the expiry policy?
2. Are points a **promotional discount** or deferred consideration under applicable rules? Does that change when points are earned by third-party business outcomes?
3. **GST:** is the taxable value of the subscription the discounted price or the list price? How must the invoice show a points redemption?
4. What happens, for accounting and GST, when points **expire** unredeemed?
5. What happens on **cancellation, refund or chargeback** of a subscription paid partly with points?
6. Do points constitute a "loyalty programme" needing specific terms, disclosures or consumer-law compliance?
7. Is any additional regulation triggered because points are earned from **other members' payments or business**?
8. What **member consent** and Terms are required: right to change or end the programme, expiry, forfeiture on fraud, dispute process, data use for the community milestone feed?
9. How should **data about prospects** (phone, email) be handled under data-protection rules, given their details are collected without their direct consent?

---

## 25. Recommended final reward table (Phase 28), Model B, ₹0.10 per point

| Action | Recipient | Points | Verification | Limit |
|---|---|---:|---|---|
| Referral created | – | **0** | System | Rate limited |
| Referral accepted | Referrer | **30** (+15 for a direct introduction or arranged meeting) | Recipient (L1) | 10 rewarded per month |
| Referral accepted | Recipient | **15** | Self (L1) | Once per referral |
| Prospect contacted within 72h | Recipient | **15** | Recipient, referrer may dispute (L1) | Once per referral |
| Meeting completed | Referrer | **45** | Both confirm (L2) | Once per referral; 8 per month |
| Meeting completed | Recipient | **60** | Both confirm (L2) | Once per referral |
| Business closed: under ₹25k | Referrer / Recipient | **210 / 90** | Both confirm (L2) | Once per referral |
| ₹25k–₹1L | Referrer / Recipient | **525 / 225** | Both confirm (L2) | Once per referral |
| ₹1L–₹5L | Referrer / Recipient | **1,050 / 450** | Both + evidence (L3) | Once per referral |
| ₹5L–₹10L | Referrer / Recipient | **1,470 / 630** | Both + admin (L4) | Once per referral |
| ₹10L+ | Referrer / Recipient | **1,890 / 810** (hard max) | Both + admin (L4) | Once per referral |
| Repeat business, same prospect | Both | 50% of the band | As above | Once per prospect per season |
| Profile completed | Member | **75** | System (L3) | Once |
| Event attended *(future)* | Member | **45** | Admin check-in (L3) | Per event; 3 per season |
| Successful introduction *(future)* | Connector | **75** (+**150** if a meeting follows) | Both introduced members confirm (L2) | 4 per season; once per pair |
| Need resolved *(future)* | Helper | **60** | Poster confirms (L2) | 4 per season |
| Mentoring session *(future)* | Mentor | **90** | Mentee confirms (L2) | 3 per season |
| New member invited and active *(future)* | Inviter | **225** | Payment verified + 30 days (L3) | 3 per season |
| Views, likes, logins, connections, posting a need, replying to a need | – | **0** | – | – |

**Global ceilings:** 500 per day · 3,000 per month · **6,000 per season** · pair rule: 1,500 low-assurance points per pair per season, verified closures governed by the concentration rule (final spec) · sub-ceilings: referral process 1,500, closed business 3,600, other 1,200.

Maximum one referral can ever pay: referrer 30 + 15 + 45 + 1,890 = **1,980**, recipient 15 + 15 + 60 + 810 = **900**.

---

## 26. Final economic model (Phase 29)

| # | Item | Recommendation |
|---|---|---|
| 1 | Point value | **₹0.10** |
| 2 | Maximum redemption | **15% of plan price per invoice** |
| 3 | Max discount, ₹3,000 plan | **₹450** |
| 4 | Max discount, ₹5,000 plan | **₹750 by the cap; ₹600 in practice** (earning ceiling) |
| 5 | Max discount, ₹10,000 plan | **₹1,500 by the cap; ₹600 in practice** |
| 6 | Minimum the member pays | **₹2,550 / ₹4,400 / ₹9,400** (never below 85%; 80% with coupons) |
| 7 | Earning ceiling | **500 / day, 3,000 / month, 6,000 / season** |
| 8 | Referral rewards | Accept 30(+15) / 15; contacted 15; max across one referral's process steps: referrer 90, recipient 90 |
| 9 | Meeting rewards | 45 referrer / 60 recipient, both confirm, 8 per month |
| 10 | Max closed-business reward | **2,700-point pool (₹270) per deal**, split 70/30 |
| 11 | Expiry | **6 months from earning, FIFO**, 30-day warning, pending lapses at 60 days |
| 12 | Transfer | **None** |
| 13 | Cash conversion | **None**; no refunds; subscription only |
| 14 | Reversals | Voids pending; 60-day clawback of verified deals; admin adjustments always audited |
| 15 | Fraud prevention | Section 18 |
| 16 | Verification | L0 to L4 (section 11); backend-only calculation |

---

## 27. Final business test (Phase 30)

| Question | Answer | Evidence |
|---|---|---|
| Could a member earn points equal to a full ₹3,000 / ₹5,000 / ₹10,000 plan in a season? | **NO** | Ceiling is 6,000 points = ₹600: **20% / 12% / 6%** of the three plans |
| Could a highly active member redeem the whole subscription? | **NO** | Redemption cap is 15%, the floor 85%; and the maximum is ₹450 / ₹600 / ₹600 |
| Does the reward still feel meaningful? | **YES, for the members it is meant for** | Top performers save ₹450 to ₹600; a high performer ~₹260 (≈ 9% of an entry plan); an average member ~₹70. Average members will find it modest, which is intended |
| Does it encourage actions that create business? | **YES** | 0 for activity; points flow only to accepted, met and verified-closed referrals and confirmed helpful acts |

---

## 28. Recommended database architecture (Phase 19)

New tables (names indicative). **`networking_profiles.growth_points` stays only as a cached projection of the ledger, never written directly.**

**`growth_point_ledger`** (append-only; the single source of truth)

| Column | Notes |
|---|---|
| `id` | UUID |
| `member_id` | user id |
| `event_type` | e.g. `REFERRAL_ACCEPTED`, `BUSINESS_CLOSED`, `REDEMPTION`, `EXPIRY`, `REVERSAL`, `ADMIN_ADJUSTMENT` |
| `reference_type`, `reference_id` | the referral, event, invoice etc. |
| `points_delta` | signed integer |
| `reason` | text |
| `status` | `PENDING` / `AVAILABLE` / `VOIDED` / `REDEEMED` / `EXPIRED` |
| `created_at`, `created_by` | `created_by` = system or admin id |
| `balance_after` | member's available balance after this row |
| *`remaining`, `expires_at`* | for earn rows, to support FIFO expiry |
| *`rule_version`, `verification_level`, `idempotency_key`* | audit and safety |

Constraint: **`UNIQUE (member_id, event_type, reference_type, reference_id)`** so one event can never pay twice.

Supporting tables: `reward_rules` (versioned point values, caps, ceilings, expiry, editable by admin and audited); `referral_confirmations` (who confirmed which step and when; the two-party record); `deal_outcomes` (referral id, band, evidence file, verification level, verified by); `subscription_invoices` (**prerequisite**: plan, list price, discounts, amount paid, status); `growth_point_redemptions` (invoice, points, rupees, **the cap and floor calculation snapshot**); `reward_period_totals` (per member per day / month / season counters used by ceilings); `audit_log` (every admin action); `member_reward_flags` (suspension, reduced ceiling).

---

## 29. Recommended backend architecture (Phases 31, 32)

```
 NETWORKING EVENT  (referral stage change, confirmation, check-in …)
        │            written in the same DB transaction as the state change
        ▼
 REWARD EVENT  → idempotency key checked against the ledger
        ▼
 VERIFICATION  → level L0..L4, counterparty / evidence / admin as the rule requires
        ▼
 REWARD RULE ENGINE   (one module, `app/rewards/`, reads `reward_rules`)
        │   applies: base value, verification, per-pair / daily / monthly / season ceilings
        ▼
 GROWTH POINT LEDGER  (append-only; PENDING → AVAILABLE after the dispute window)
        ▼
 MEMBER BALANCE  (derived; cached on the profile; nightly reconciliation)
        ▼
 REDEMPTION ENGINE  (cap % , 85% floor, combined-discount floor, lots FIFO)
        ▼
 SUBSCRIPTION DISCOUNT  (invoice line item, GST-ready)
```

Rules:
- **No reward maths in controllers.** Routes only call `rewards.award(event)`.
- **The server is authoritative** for points, deal values, ids, status and redemption amounts.
- Everything in database transactions; unique constraints plus idempotency keys; `SELECT … FOR UPDATE` on the member's period totals under Postgres; the ledger is never updated or deleted, only appended to.
- Scheduled jobs: release pending points, expire lots, flag suspicious patterns, **reconcile ledger totals against the cached balance**, and alert on drift.
- Shared rate limiting (Redis) before multiple servers are used; the current limiter is per-process.

---

## 30. Testing plan (Phase 33)

- **Reward events:** each of the table in section 25, including that views/likes/connections pay 0.
- **Duplicates:** same referral twice, double click, repeated API call, replayed webhook, two simultaneous confirmations (race).
- **Financial:** ₹3,000, ₹5,000, ₹10,000 plans; exactly at the cap; one point over; balances above the cap; 85% / 80% floors; coupon stacking; upgrade; refund; expiry on the boundary day; FIFO order.
- **Fraud:** forged user id, forged points or deal value in the request body, self-referral, A→B→A circular, pair ceiling, closure before acceptance, one-sided confirmation, non-member recipient, suspended account.
- **Reversals:** cancelled referral, disputed meeting, refunded deal, admin reversal, clawback after redemption.
- **Reconciliation:** ledger sum equals cached balance after a random sequence of 10,000 operations.

---

## 31. Implementation roadmap

| Phase | Work | Why this order |
|---|---|---|
| **0. Prerequisites** | Subscription and invoice tables with a real purchase flow; **two-party confirmation** for meetings and closures; **deal-value band captured at closure** with evidence upload; audit log; admin referral screen | Without these, points either can't be redeemed or can be farmed |
| **1. Ledger and engine** | Ledger, rules table, idempotency, referral lifecycle rewards, profile completion; **no redemption yet**; run in **shadow mode** (points computed and shown as "pending launch") for one season | Measures real behaviour and fraud before any money is at stake |
| **2. Member dashboard and admin analytics** | Section 21 and 22 screens; the liability and realised-cost figures | Transparency before value |
| **3. Redemption** | Cap, floor, FIFO lots, invoice line item; accountant sign-off first | The only phase with financial impact |
| **4. New earners** | Event check-in, introductions, need resolution, mentoring, invitations | Each needs its own feature and verification |
| **5. Community milestones** | Opt-in announcements | Privacy design is easier once volumes are known |
| **6. Recalibrate** | Replace the assumptions in section 12 with real data; re-run the model; adjust values and ceilings | Keeps the economy honest |

---

## 32. Decisions needed from management

1. Confirm that ₹3,000 / ₹5,000 / ₹10,000 are **per 3-month season** (the Subscription page says so).
2. Approve **Model B** (or choose A or C).
3. Approve the **15% cap**, **6,000-point season ceiling** and **6-month expiry**.
4. Approve building **Phase 0** first (subscriptions/invoices, two-party confirmation, deal value capture).
5. Decide whether to **soften existing copy** that already promises Growth Points (Subscription page, Overview, referral help text) until launch.
6. Commission the **accounting/legal review** in section 24 before Phase 3.

---

*Reproducibility: the figures come from a deterministic model (rewards table, assumed activity, plan mix and ceilings listed in section 12). Re-run it when the assumptions change.*
