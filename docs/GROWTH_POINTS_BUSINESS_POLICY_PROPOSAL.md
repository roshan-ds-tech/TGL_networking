# TGL Growth Points: Business Policy Proposal (v4 candidate), revision 2

> ## DRAFT BUSINESS POLICY — NOT APPROVED FOR PRODUCTION
> A proposal for management review. It changes **no** code, constant, schema, migration, environment variable or data. `docs/GROWTH_POINTS_FINAL_SPEC.md` (v3) and rule version `growth-points-v3` remain the only approved rules. Every figure is labelled **M** (mathematical maximum or bound that follows from the rules), **E** (modelled expectation under stated assumptions) or **H** (hypothetical scenario). **No figure in this document is measured TGL usage.**
>
> **Standing safeguards this proposal does not touch:** shadow-period points are permanently historical and ineligible for redemption; `GROWTH_POINTS_REDEEMABLE_FROM` stays empty and no redemption epoch is recorded until a precise cutoff has written management approval; real redemption stays disabled; no invoice or payment is altered; synthetic demo members never count toward the genuine-member observation gate; `GROWTH_POINTS_DEMO_CUTOFF` is a local demo setting unrelated to the real eligibility cutoff.

**Revision 2** is the result of a critical review of revision 1. The review found the first draft *directionally right but not consistent*: it contained one financial design error (it reduced the guaranteed headroom for verified closures), several values that did not respect the value ladder, and several statements about the ledger and the code that were imprecise. Section 3 lists every defect and its resolution; section 15 summarises what changed.

---

## 1. Executive summary

**Verdict on revision 1.** Not fully consistent. The new Community category added 8% *on top of* the existing sub-ceilings, which cut the guaranteed room for closed business below the largest single closure reward on the Connect plan (1,692 points left, against a 1,890-point ₹10L+ referrer reward). Other defects: a one-click connection reward valued above its evidence, an introduction path that could out-earn a referral meeting, a verified-business reward below profile completion, a pair budget (₹150 a quarter) too generous for 10–45-point rewards, a "release sweep" the engine does not have, and two anti-abuse checks the architecture cannot support.

**Recommended policy (one policy).** Keep every existing reward, ceiling, limit and the redemption rules exactly as approved. Add a small, capped **Community layer** paid only for *mutual or confirmed* contributions, **nested inside the existing 20% `OTHER` allowance** so that the non-closure total stays at 45% and closed business keeps its full 55% headroom.

| Action | Recipient | Points | ≈ ₹ | Change from revision 1 |
|---|---|---:|---:|---|
| Connection **accepted** (first time ever for the pair) | both | **10 each** | 1.00 | 15 → 10 |
| **Valid need** published (survives 7 days) | poster | **20** | 2.00 | none |
| Response confirmed **helpful** by the poster | helper | **25** | 2.50 | none |
| **Introduction** to a TGL member, confirmed by both | helper | **30** (+**45** when the two confirm a meeting ≤ 60 days) | 3.00 (+4.50) | 40 / +60 → 30 / +45 |
| Need **resolved** with a credited helper, confirmed by both | helper / poster | **45** / **10** | 4.50 / 1.00 | helper 60 → 45 |
| **TGL Verified** business (admin approval, once) | member | **75** | 7.50 | 50 → 75 |
| All existing referral, meeting, closure, repeat and profile rewards | as today | **unchanged** | | none |

**Limits.** Community pool (connection, need published, poster close, confirmed help) **12%** of the cycle ceiling (432 / 720 / 1,440 points), of which participation (connection, need published, poster close) is at most **5%** (180 / 300 / 600), all *inside* the existing `OTHER` 20%. New community pair budget of **150 points per pair per quarter**. Introductions 2 a quarter.

**Verified economics** (section 8, reproducible script in Appendix A). Maximum liability is **unchanged: 12% of subscription revenue, ₹532,800 a year on the approved 400-member model (M)**. On the approved model's own assumptions the expected annual cost moves from ₹83,006 (1.87% of revenue) to **₹88,677 (2.00%)** (E), and the "everyone redeems" case from ₹100,135 (2.26%) to **₹110,108 (2.48%)** (E). These **replace** revision 1's ₹93,934 and ₹117,225, which were overstated because they added a separate category on top of the existing ones. The proposed 3% go/no-go threshold is **not** guaranteed by the design: the approved v3 itself reaches 3.26% if everyone redeems and activity doubles.

---

## 2. Current implementation findings (verified in code)

### 2.1 What exists

| Area | Finding | Source |
|---|---|---|
| Rules | One versioned module, `growth-points-v3`; every ledger row records its version; `ensure_rule_version` refuses to run if the code differs from the stored hash | `rewards/rules.py`, `engine.py` |
| Enabled events | `REFERRAL_ACCEPTED` 30 (+15 direct intro or arranged meeting) / 15; `PROSPECT_CONTACTED` 15 (≤ 72 h); `MEETING_COMPLETED` 45 / 60; `BUSINESS_CLOSED` pools 300 / 750 / 1,500 / 2,100 / 2,700 split 70 / 30; `REPEAT_BUSINESS` 50%; `PROFILE_COMPLETED` 75 | `rules.EVENTS` |
| Disabled events (feature missing) | `EVENT_ATTENDED` 45, `SUCCESSFUL_INTRODUCTION` 75 (+150), `NEED_RESOLVED` 60, `MENTORING_SESSION` 90, `MEMBER_INVITED` 225 | `rules.EVENTS` |
| Explicit zeros | `REFERRAL_CREATED`, `PROFILE_VIEW`, `LIKE`, `LOGIN`, `CONNECTION`, `NEED_POSTED`, `NEED_REPLIED`; `test_phase1` asserts none is a reward event | `rules.ZERO_POINT_ACTIONS` |
| Triggers | After-commit, state-driven, idempotent hooks for referral, closure, profile and renewals; they read stored rows, never client values | `rewards/hooks.py`, `events.py` |
| Ledger | Append-only (ORM guard + triggers), `shadow = true` CHECK, `requested_points` / `points_delta` / `capped_points` / `capped_by` / `cap_trace`, unique `idempotency_key` = event + reference type + reference id + member (+ suffix) | `models.GrowthPointLedger`, `engine.award` |
| Cap order | pair rules → frequency → category sub-ceiling → daily (low assurance only) → monthly → cycle ceiling; every cut recorded | `engine.award` |
| Pending | Not a stored status: `available_at = event + 7 days` for L1/L2, status is derived from time. There is **no "release" step** | `engine.award`, `analytics._state` |
| Void / reversal / expiry | `retire()`: pending → `VOID` row; usable and ≤ 60 days old → `REVERSAL`; older → `REVERSAL_NEEDS_REVIEW` flag; `EXPIRED` lots are skipped; ceilings count `EARN + VOID + REVERSAL`, so a void frees the cap | `events.retire`, `engine._NET` |
| Fraud | pair concentration / frequency / volume, reciprocal referrals, same prospect across pairs, rapid and high-value closure, repeatedly capped; flags only | `rewards/fraud.py` |
| Synthetic exclusion | Gate A, the review and analytics count genuine members only (reserved demo email domain) | `app/demo.py` |

### 2.2 Figures you supplied, checked

| Figure | Verified | Note |
|---|---|---|
| 1 point = ₹0.10 | Yes | `PAISE_PER_POINT = 10` |
| ₹3,000 / 3 mo, ₹5,000 / 6 mo, ₹10,000 / 12 mo | Yes | `model.PLANS`, migration 0009 |
| Cycle ceilings 3,600 / 6,000 / 12,000 | Yes | `price × 12% ÷ ₹0.10` |
| Daily 500 | Yes, **low-assurance (L1/L2) only** | verified closures are not split across days |
| Monthly 3,000 | Yes, all points; never binds (Connect cycle total is 3,600) | |
| Closed business 60% | Yes. Other sub-ceilings: process 25%, other 20% | sum is **105%**, see 8.3 |
| Redemption 15% of the **new renewal invoice** | Yes (renewal only, per the management lock) | the earning ceiling (12%) is deliberately lower |

### 2.3 What the workflows actually persist (checked, not assumed)

| Workflow | Route exists | What is stored | Consequence |
|---|---|---|---|
| Connections | `POST/PATCH/DELETE /networking/connections` | One row per direction, `PENDING → ACCEPTED/DECLINED`; **`DELETE` hard-deletes the pair**; no `accepted_at` history beyond `responded_at`; no rate limit | No durable history, so "first time ever for this pair" cannot be proven; remove-and-reconnect is invisible |
| Needs | `GET/POST /networking/needs` only | `BusinessNeed` with title ≥ 4 characters, category, optional description, `status` that is **always `OPEN`**; no edit, delete, resolve or admin route (`grep`: no other reference to `BusinessNeed`); no limits | Nothing to moderate, resolve, deduplicate or reward |
| "I can help" | `POST /networking/needs/{id}/help` | Only a **notification row** to the poster (`need_help_offered`), repeatable, cascades away with the user; no offer record | A reward cannot be tied to a stored offer |
| Resolve / confirm help | none | none | Must be built |
| Introductions | none | none | Must be built |
| TGL Verified | admin route sets `tgl_verified` on `VERIFIED`; paid registrants get a *derived* badge that is not an event | `Business.verification_status`, `tgl_verified_at` | Reward only the stored admin approval |
| Hooks into the ledger | referral, closure, profile, renewals only | | New reference types also need a branch in `events.still_invalid` and `jobs.resync_pending`, or pending community points would never be re-checked |
| Alternate-account signals | | `users.phone` (not unique, not verified); an IP hash exists only on public event registrations (`registrations.submitter_ip_hash`), not on member accounts | Phone match is a weak, flag-only signal; IP/device on accounts is new data |

### 2.4 Activity map

**Rewarded today:** referral accepted → `REFERRAL_ACCEPTED` (L1, pending 7 days) · contacted → `PROSPECT_CONTACTED` (L1) · both confirm meeting → `MEETING_COMPLETED` (L2) · deal verified → `BUSINESS_CLOSED` / `REPEAT_BUSINESS` (L2–L4) · profile complete → `PROFILE_COMPLETED` (L3). Each: member action → server validation of stored rows → `engine.award` (caps recorded) → `EARN` ledger row → shown on the member's Growth Points page when preview or redemption is on.

**Not rewarded, and not rewardable today:** connect/accept, post a need, "I can help", ask for a referral (no reward event, no ledger entry; listed under "does not earn points").

---

## 3. Critical review: contradictions found and how they are resolved

| # | Contradiction or defect | Evidence | Resolution in this revision |
|---|---|---|---|
| 1 | **A new 8% Community category would cut closure headroom below the largest closure reward.** v3 non-closure maximum is 25% + 20% = 45%, so closure keeps 55% = 1,980 points on Connect (≥ 1,890). Revision 1 made it 53% → 1,692 < 1,890 | Appendix A, section 1 | **Nest Community inside `OTHER`.** Non-closure stays 45%; headroom stays 1,980 / 3,300 / 6,600 |
| 2 | The 105% sum looked like a defect | `SUBCEILING_PERCENT` | Intentional in effect and safe: they are per-category **maxima**, the cycle ceiling is enforced last. It is inherited (25 / 60 / 20 of the original 6,000-point ceiling = 1,500 / 3,600 / 1,200) and never explained as 105%; explained in 8.3 |
| 3 | Revision 1 said a "sweep releases the 7-day rewards" | `engine.award` derives pending from `available_at` | No release step exists or is needed: issue the row at event time with `available_at = +7 days`; the sweep only **voids** (removed, disputed) |
| 4 | "Reward after the need survives 7 days" versus the engine issuing the row immediately | same | Issue immediately as `PENDING`; a removal inside 7 days writes a `VOID` row that frees the caps |
| 5 | "Removal of the activity" versus the append-only ledger, plus connections are hard-deleted | `remove_connection` | Never edit or delete ledger rows: removal is a **state change in a durable fact table**, and the sweep writes `VOID` / `REVERSAL` rows. Connections must stop being hard-deleted (7.1) |
| 6 | Connect → disconnect → reconnect | idempotency key is per reference | Key community connection rewards on the **pair** (hash, 32 hex), not the connection row. A voided first reward is final for that pair |
| 7 | 60-day automatic reversal window versus 10–75-point rewards | `retire()` raises a HIGH review flag for any usable lot older than 60 days | Add a v4 parameter `REVIEW_MIN_POINTS` (proposed 100): community lots below it are **not** individually queued after 60 days, only if part of a flagged pattern |
| 8 | Expiry versus cancellation | `retire()` skips `EXPIRED` | Unchanged: cancelling an activity after its points expired changes nothing |
| 9 | Pair budget 1,500 points a quarter versus 10–45-point rewards | `PAIR_LOW_ASSURANCE_BUDGET` | Add a **community pair budget of 150 points a quarter** (combined, both directions); the 1,500 budget keeps governing the referral chain |
| 10 | Reciprocal help versus the concentration rule | P3 covers verified closures only | Reciprocal help, resolution and introduction: second direction within 60 days pays **50%**, a third pays 0, review flag |
| 11 | Draft introduction (40 + 60 = 100) out-earned a referral that reaches a meeting (30 + 45 = 75, or 90 with the +15 quality bonus) | values | Introduction **30 + 45 = 75**. Rule: no confirmed-only community path may pay more than the minimal referrer path |
| 12 | Helper path 25 + 60 = 85 exceeded the minimal referrer path (75) | values | `NEED_RESOLVED` helper 60 → **45** (path 70). The approved v3 future value (60) therefore changes; flagged for approval |
| 13 | TGL Verified (admin, L4) 50 < profile completion (system, L3) 75 | values | Verified **75**: the strongest evidence among one-off rewards should not pay less |
| 14 | Connection 15 each pays the *target* for a click, with no engagement signal in TGL (there is no messaging) | `respond_to_connection` | **10 each**; participation sub-limit 5% so connections cannot starve confirmed help |
| 15 | Small acts consumed the Community allowance before the more valuable ones (a heavy helper exhausted a single pool before a resolution or introduction arrived) | observed while testing a single-pool design (a heavy helper exhausted the pool before any resolution arrived) | Two levels: confirmed help may use the whole Community pool, participation is capped at 5% of it, and resolutions / introductions are **outside** the pool (still inside `OTHER`) |
| 16 | One response could be paid as help **and** as an introduction | draft H2 / H3 | One response, **one** confirmed-help reward (the higher applicable one) |
| 17 | A need resolved through a linked referral paid `NEED_RESOLVED` and then the whole referral chain | draft | `NEED_RESOLVED` pays 0 when the resolution is a linked referral that reached `ACCEPTED` |
| 18 | "Refuse same business or same payer reference" | `Business` belongs to one user; `payments.reference` is TGL's own code, not the payer's account | **Dropped.** Same phone becomes a flag only (non-unique, unverified) |
| 19 | "IP / device hashing" presented as a control | only public registrations store an IP hash | Moved to *requires privacy approval*; not assumed |
| 20 | "Stores nothing" for "I can help" | a notification row exists | Corrected: the only trace is a notification, not an offer record |
| 21 | Shadow-period ineligibility versus future redemption | the epoch is a time instant, independent of rule version | Unchanged and explicit: any point with `event_at` before the approved cutoff, under v3 or v4, is historical and never redeemable; v4 must be approved **before** the cutoff is set, so points earned after the cutoff are under approved rules |
| 22 | Draft claimed the expected cost stays "below the 3% threshold" | model | True only at ×1 activity. The approved v3 itself reaches 3.26% (all redeem, ×2). The threshold is a **measured** go/no-go, not a design guarantee (8.5) |
| 23 | Draft figures ₹93,934 / ₹117,225 | recalculated | Replaced by **₹88,677 / ₹110,108** (8.4) |

---

## 4. Reward values: relative-value review and recommendation

### 4.1 The value ladder (the test every value must pass)

1. **Tier 1, one party or one click** (≤ ₹2.50): connection 10, need published 20, poster closing the loop 10, confirmed help 25.
2. **Tier 2, two-party confirmed or admin one-off** (₹3 – ₹7.50): introduction 30 (+45), resolved 45, meeting 45 / 60, profile 75, TGL Verified 75.
3. **Tier 3, evidence and admin verification:** closures 90 – 1,890.

Three guard rails: (a) **no community path may pay a helper more than the minimal referrer path** (referral accepted 30 + meeting 45 = 75): confirmed help + resolution = 25 + 45 = 70, introduction + meeting = 30 + 45 = 75; (b) **the largest single community act (75) is below the smallest closure payout** (90 recipient, 210 referrer); (c) **the whole Community pool is smaller than one mid-size closure** (Connect pool 432 < one ₹1L–₹5L referrer reward 1,050).

### 4.2 Value-by-value verdict

| Value | Intended incentive | Verdict | Recommendation |
|---|---|---|---|
| Connection 15 each | Grow useful mutual connections | Too high for a click with no engagement signal; pays the accepter | **10 each**, 6 a month, pair-once for life |
| Need published 20 | Publish specific, genuine needs | Right: above a click, below a confirmed act | **Keep 20**, 2 a month, 80-character minimum |
| Confirmed helpful 25 | Reward useful help | Right: counterparty-confirmed, in line with referral accepted (30 / 15) | **Keep 25** |
| Introduction 40 + 60 | Create member-to-member relationships | Out-earned a referral meeting | **30 + 45**, 2 a quarter |
| Resolved 60 / 10 | Close the loop with the helper credited | Total help path exceeded the referrer path | **45 / 10** |
| TGL Verified 50 | Real business verification | Below profile completion despite stronger evidence | **75** once |
| Referral accepted 30 (+15) / 15 | Existing | Counterparty click; the +15 depends on what the referrer declares (`DIRECT_INTRO`, `MEETING_ARRANGED`), not on evidence | **Keep**; watch-list |
| Prospect contacted 15 | Existing | Self-reported by the recipient; the weakest event | **Keep**; first candidate to remove on poor reversal data |
| Meeting 45 / 60 | Existing | Two-party confirmation | **Keep** |
| Closures, repeat business | Existing | Evidence plus admin; the dominant earner | **Keep** |
| Profile 75 | Existing | System-verified, one-off | **Keep** |

### 4.3 One underlying relationship, several rewards: the explicit justification

| Step | Who earns | Points | Why it is a separate contribution |
|---|---|---:|---|
| A and B connect | A, B | 10 + 10 (once per pair) | Each accepted a relationship |
| B posts a need | B | 20 | Created a legitimate opportunity (valid, deduplicated, moderated) |
| A's response is marked helpful | A | 25 | A did work B confirmed. If the response is an introduction, **30 instead**, not both |
| B resolves the need crediting A, A acknowledges | A / B | 45 / 10 | The outcome, confirmed by both. **0 / 0 for A's reward if resolved by a linked referral** (the referral chain pays) |
| A refers a prospect to B | A, B | 30 (+15) / 15 | A different act: a real third-party prospect |
| Prospect contacted, meeting confirmed | B / A, B | 15, 45 / 60 | Existing two-party steps |
| Deal verified | A, B | 210 – 1,890 / 90 – 810 | Evidence and admin verification |

Rules that stop the same act being paid twice: one response → one confirmed-help reward; one need → at most 3 rewarded helpers and one resolution; a need resolved by a linked referral does not also pay `NEED_RESOLVED`; the introduction meeting bonus never applies when the introduced pair's meeting is already a referral meeting; the connection reward is paid once per pair however the connection arose; closure points are paid **only** through the referral and closure workflow (links to a need or introduction are for analytics); all community points count toward the pair budgets.

---

## 5. The final recommended reward matrix

**Impl.:** **E** exists, **P** partial, **N** new workflow required, **F** future feature. IDs link the two tables. 1 point = ₹0.10.

### 5.1 Decisions, values and limits

| ID | Activity | Decision | Trigger | Recipient | Points | ≈ ₹ | Eligibility | Frequency limit | Impl. |
|---|---|---|---|---|---:|---:|---|---|---|
| C1 | Connection request sent | **Zero** | send | none | 0 | 0 | | rate limit (new) | E |
| C2 | Connection **accepted**, first ever for the pair | **Reward** | target accepts (or a crossing request auto-accepts) | both | **10 each** | 1.00 | Basic profile (photo, business profile, city) on both; ≥ 7 days of access; active term | Once per pair for life; 6 per member per month | P |
| C3 | Re-connection, already connected | **Zero** | any | none | 0 | 0 | | n/a | P |
| C4 | Declined, ignored, withdrawn | **Zero** | any | none | 0 | 0 | | n/a | E |
| N1 | Need **published**, valid | **Conditional reward** | passes validation; row issued as pending, void if removed ≤ 7 days | poster | **20** | 2.00 | ≥ 12 chars / 3 words title, ≥ **80-char** description, category, no contact data in title, not a duplicate, not re-posted after removal ≤ 30 days | 2 a month; 1 per category per 30 days; ≥ 3 days apart | P |
| N2 | Need viewed, "I can help" clicked | **Zero** | click | none | 0 | 0 | | notification rate limit | E |
| N3 | Duplicate, removed, spam need | **Zero** | any | none | 0 | 0 | | n/a | N |
| N4 | Need receives responses | **Zero** to poster | any | none | 0 | 0 | | n/a | N |
| H1 | Response posted, unconfirmed | **Zero** | post | none | 0 | 0 | | 10 responses a day | N |
| H2 | Response **confirmed helpful** | **Conditional reward** | poster marks Helpful ≤ 30 days | helper | **25** | 2.50 | ≥ 60 chars and ≥ 12 words; not self; one per helper per need | 8 a month; ≤ 3 helpers per need; ≤ 2 per poster→helper pair per quarter; reciprocal 50% | N |
| H3 | **Introduction** to a TGL member | **Conditional reward** | poster and introduced member confirm (replaces H2 for that response) | helper | **30**, **+45** if the two confirm a meeting ≤ 60 days | 3.00 (+4.50) | Distinct members, not already connected, no referral meeting for them | 2 a quarter; once per introduced pair | F |
| H4 | Need **resolved** with a credited helper | **Conditional reward** | poster resolves with note ≥ 40 chars, helper acknowledges | helper / poster | **45 / 10** | 4.50 / 1.00 | ≥ 1 confirmed helpful response; not resolved by a linked referral | Helper 4 a quarter; poster 2 a month; 1 per pair per quarter (reciprocal 50%) | N |
| H5 | Resolved with no credited helper, self-credit | **Zero** | any | none | 0 | 0 | | n/a | N |
| R1 | Referral created | **Zero** | create | none | 0 | 0 | | rate limited | E |
| R2 | Referral accepted | **Reward (unchanged)** | recipient accepts | referrer / recipient | **30 (+15) / 15** | 3.00 (+1.50) / 1.50 | existing | 10 a month (referrer) | E |
| R3 | Prospect contacted | **Reward (unchanged)** | recipient reports ≤ 72 h | recipient | **15** | 1.50 | existing | once per referral | E |
| R4 | Meeting completed | **Reward (unchanged)** | both confirm | referrer / recipient | **45 / 60** | 4.50 / 6.00 | existing | 8 a month (referrer) | E |
| R5 | "Qualified opportunity" stage | **Zero**, no stage | n/a | none | 0 | 0 | | n/a | not built |
| R6 | Verified closed business | **Reward (unchanged)** | verified at the required level | referrer / recipient | **210 / 90 · 525 / 225 · 1,050 / 450 · 1,470 / 630 · 1,890 / 810** | 21 / 9 … 189 / 81 | existing | once per referral; pair rule | E |
| R7 | Repeat business | **Reward (unchanged)** | verified repeat | referrer / recipient | **50% of pool** | | existing | once per prospect per quarter | E |
| R8 | Referral linked to a need | **Zero extra** | link | none | 0 | 0 | analytics only | n/a | N |
| O1 | Profile completed | **Reward (unchanged)** | strict profile complete | member | **75** | 7.50 | existing | once | E |
| O2 | **TGL Verified** | **Reward (new)** | admin sets `VERIFIED` | member | **75** | 7.50 | stored admin approval, not the derived badge | once | P |
| O3 | Expertise / portfolio completion | **Zero** (no feature) | n/a | none | 0 | 0 | | | F |
| O4 | Event registration | **Zero** | register | none | 0 | 0 | | | E |
| O5 | Event attended | **Future reward** | admin check-in | member | **45** | 4.50 | | 3 a quarter | F |
| O6 | Mentoring session | **Future reward** | mentee confirms | mentor | **90** | 9.00 | | 3 a quarter | F |
| O7 | Member invited and active | **Future reward** | invitee's payment verified + 30 days | inviter | **225** | 22.50 | | 3 a quarter | F |
| O8 | Login, view, search, notification read, referral request | **Zero** | any | none | 0 | 0 | | n/a | E |

### 5.2 Verification, protection, reversal, rationale

| ID | Verification | Abuse protection | Reversal | Rationale |
|---|---|---|---|---|
| C2 | Counterparty acceptance (L1), pending 7 days | Pair-once key; 6 a month; participation sub-limit; community pair budget; burst and closed-cluster flags | Removed ≤ 7 days → `VOID`; later → none | Cheapest honest network-growth signal; small and delayed |
| N1 | System validation (L1) + 7-day window; 10% sample and all flagged to moderation | Content rules, duplicate hash, re-post lock, limits | Removed ≤ 7 days → `VOID`; ≤ 60 days → `REVERSAL`; later → flag only if a pattern | Rewards a real opportunity without waiting for an outcome |
| H2 | Poster confirmation (L1); response text kept | Not self; pair limits; reciprocal 50%; instant-confirm flag | Withdrawn ≤ 7 days → `VOID`; response removed → void / reverse | Pays confirmed value, not replying |
| H3 | Both members (L2) | Distinct members; 2 a quarter; once per pair | Dispute ≤ 7 days → `VOID` | Creates the relationships TGL exists for |
| H4 | Both members (L2), note, 5% audit | Needs a confirmed response; linked-referral exclusion; limits | Dispute ≤ 7 days → `VOID`; fraud → `REVERSAL` ≤ 60 days | Closes the loop; gives TGL its missing data |
| R2–R7, O1 | Existing (L1–L4) | Existing | Existing | Approved and tested |
| O2 | Admin (L4) | Admin-controlled, once | Admin revokes → `REVERSAL` ≤ 60 days | A trust signal that already exists |

---

## 6. Limits and ceilings (recommended)

All existing limits remain: 500 a day (low-assurance), 3,000 a month, cycle ceiling 12% of price, pair budget 1,500 a quarter for low-assurance points, pair concentration for verified closures, redemption 15% of the new renewal invoice.

**Category structure in v4 (the non-closure total is unchanged at 45%):**

| Pool | Share of the cycle ceiling | Connect | Growth | Elite | Holds |
|---|---:|---:|---:|---:|---|
| `PROCESS` | 25% | 900 | 1,500 | 3,000 | referral accepted, contacted, meeting |
| `CLOSURE` | 60% | 2,160 | 3,600 | 7,200 | closures, repeat business |
| `OTHER` | 20% | 720 | 1,200 | 2,400 | **everything below** |
| ├ Community pool | 12% | 432 (₹43.20) | 720 (₹72) | 1,440 (₹144) | connection, need published, poster close, confirmed help |
| │  └ Participation sub-limit | 5% | 180 (₹18) | 300 (₹30) | 600 (₹60) | connection, need published, poster close |
| ├ Outcomes (outside the pool) | n/a | | | | need resolved, introductions |
| └ One-offs and future events | n/a | | | | profile 75, TGL Verified 75, events, mentoring, invitations |

New cut names recorded in `capped_by`: `COMMUNITY_POOL`, `COMMUNITY_PARTICIPATION`, `PAIR_COMMUNITY`, `PAIR_RECIPROCAL` (existing name reused), `FREQUENCY_LIMIT` (existing). **Order** (extends the existing one; made executable and tested in `docs/growth_points_model/community_candidate_model.py` and `backend/test_candidate_policy_invariants.py`, specified in `docs/GROWTH_POINTS_COMMUNITY_REWARDS_IMPLEMENTATION_SPEC.md`): idempotency → prerequisite (a meeting bonus needs its introduction rewarded) → pair-once → reciprocal 50% → community pair budget 150 → pair 1,500 → frequency limits (per member and per pair) → Community participation → Community pool → category sub-ceiling → daily → monthly → cycle ceiling (always last). A new cut name, `PREREQUISITE`, is added to the list above.

Per-event limits: connections 6 a month; needs published 2 a month; confirmed helps 8 a month; poster closes 2 a month; resolutions 4 a quarter (helper); introductions 2 a quarter. Community pair budget: **150 points per pair per quarter**, both directions combined.

**Trade-off to approve:** because Community shares the `OTHER` pool, a heavy helper can use the whole 20% (S3 below) and High / Top members in the approved model, whose `OTHER` is already near full, gain nothing in total: Community displaces the approved *future* events (attendance, mentoring, invitations) rather than adding to them. That is the price of keeping the 55% closure headroom.

---

## 7. Ledger mechanics (append-only), implementability and data model

### 7.1 How pending, void, reversal, expiry and removal work with the existing ledger

1. **Issue.** Every community reward is an `EARN` row written at the event, with `available_at = event + 7 days` (L1/L2). "Pending" is derived from the clock; **nothing is "released"** and nothing is edited.
2. **Cap cuts.** A reduced reward still writes a row: `requested_points` (the base value), `points_delta` (awarded, possibly 0 with status `CAPPED`), `capped_points`, `capped_by`, `cap_trace`. The reciprocal 50% rule is recorded as a cut (`PAIR_RECIPROCAL`), exactly like closures.
3. **Void.** If the underlying fact is removed, disputed or un-confirmed while the lot is pending, `retire()` writes a **new negative `VOID` row** pointing at the lot. Because ceilings count `EARN + VOID + REVERSAL`, the void frees the daily, monthly, pool and cycle room.
4. **Reversal.** After the pending window, a removed or fraudulent contribution ≤ 60 days old gets a `REVERSAL` row. Older lots become a review flag, except community lots below `REVIEW_MIN_POINTS` unless part of a flagged pattern (resolution 7).
5. **Expiry.** `EXPIRY` rows are written at the end of the renewal grace; expired lots are never reinstated; cancelling an activity after expiry changes nothing.
6. **Removal of the underlying activity.** Domain tables never hard-delete anything a reward points at. Removal sets a status and an `removed_at`; an append-only event record keeps the history; `events.still_invalid` gets a branch per new reference type; a missing reference counts as invalid (as it does for closures today). **No ledger row is ever deleted.**
7. **Re-instatement** (an admin restores a removed need): a new lot with a version suffix (`:v2`), as closures do.
8. **Idempotency and concurrency.** Unique key + member row lock, unchanged. Connection key = `CONNECTION_ACCEPTED:connection:{sha256(pair)[:32]}:{member}`; a voided first reward stays final for the pair.
9. **Eligibility.** Redeemability is decided by `event_at` against the approved cutoff, not by rule version. Candidate observations before v4 exists are not ledger rows and never redeemable.

### 7.2 Can every reward be triggered by a verifiable event? Minimum data model, validation and member flow

| Event | Exists today | Minimum data model | Backend validation | Audit trail | Member confirmation flow |
|---|---|---|---|---|---|
| C2 | Accept route; **no durable history** | Stop hard-deleting: `connections.status` gains `REMOVED` plus `accepted_at`, `removed_at`, `removed_by`; append-only `network_events(id, kind, pair_hash, actor_id, connection_id, created_at)`; allow a re-request by re-using the row | Both active, basic profiles, ≥ 7 days access, pair not previously rewarded, rate limits | `network_events` + `audit_log` for admin acts | Target presses Accept (existing) |
| N1 | Create route; **no states** | `business_needs`: `status` OPEN / RESOLVED / CLOSED / REMOVED, `published_at`, `title_norm_hash`, `removed_at`, `removed_by`, `removed_reason`; description **required ≥ 80 chars**; locked after first response | Length, duplicate hash and overlap, contact data, limits, 30-day re-post lock | `audit_log` for removals | None (system validation) |
| H2 | **None** (notification only) | `need_responses(id, need_id, responder_id, kind, body, body_hash, introduced_user_id?, status, confirmed_at, created_at)`, unique `(need_id, responder_id)` | Text rules, not self, one per helper, poster-only confirm ≤ 30 days, pair limits | `audit_log` for confirm / withdraw | Poster inbox: Helpful / Not helpful |
| H3 | **None** | `introduction_confirmations(response_id, user_id, role, confirmed_at)` for the introduced member and for the later meeting | Both confirm, distinct, not already connected | same | Introduced member confirms; both confirm the meeting |
| H4 | **None** | `need_resolutions(need_id UNIQUE, response_id, poster_note, helper_ack_at, created_at)` | Prior confirmed response, note ≥ 40 chars, helper acknowledgement, linked-referral check | same | Poster resolves and credits; helper acknowledges |
| O2 | Admin route exists | none new | admin sets `VERIFIED` | `audit_log` (exists) | none |

### 7.3 Safe implementation order

1. **Record and validate, no points.** Durable connection history; stateful needs; validation; rate limits; "I can help" recorded as an offer; analytics reading these facts.
2. **Build the missing workflows** with permissions, moderation and abuse controls: responses, Helpful, resolve-and-credit, introduction confirmations, admin moderation queue, new flags.
3. **Add the rules under an immutable new version** `growth-points-v4` (never edit v3), with a migration for the ledger's `event_type` check and the cycle ceiling columns.
4. **Observe in shadow:** a separate, non-financial candidate record first (no balances, no member visibility), then v4 in shadow once approved.
5. **Evaluate** real engagement and financial exposure (section 11).
6. **Management approval** before any production activation. Synthetic demo members are excluded from every observation metric (the same `synthetic_clause` used by Gate A).

---

## 8. Financial model (independently reproduced)

Reproduction script: **Appendix A** (read-only; imports `app.rewards.model` and `rules`; no database). It reproduces the approved figures exactly (₹83,006 expected, ₹100,135 all-redeem, ₹173,058 at ×3 all-redeem, worst ₹532,800).

### 8.1 Formulas and classification

| Quantity | Formula | Type | Result |
|---|---|:---:|---|
| Cycle ceiling | `price × 12% ÷ ₹0.10` | **M** | 3,600 / 6,000 / 12,000 points (₹360 / ₹600 / ₹1,200) |
| Redemption cap | `15% × price` | **M** | ₹450 / ₹750 / ₹1,500 (never reached: earning stops at 12%) |
| Daily / monthly | 500 low-assurance / 3,000 all | **M** | never bind a single cycle's total |
| Max liability per member per cycle | `min(ceiling, 15% × price)` | **M** | the ceiling: ₹360 / ₹600 / ₹1,200 (12% of price), **identical in v3 and v4** |
| Annual revenue, 400 members, mix 55 / 35 / 10 | `Σ n × price × (12 ÷ term)` | assumption (mix) | ₹4,440,000 |
| Max liability, network | `Σ n × ceiling × ₹0.10 × cycles a year` | **M** | **₹532,800 = 12.0%**; contractual bound 15% = ₹666,000 |
| Expected cost | approved model: segments 240 / 100 / 40 / 20, propensity 30 / 70 / 90 / 100% | **E** | v3 ₹83,006 (1.87%) |
| "Everyone redeems" | propensity 100% | **E** | v3 ₹100,135 (2.26%) |
| Community activity | listed in Appendix A | **H** | not usage data |

### 8.2 Community values and speed to the limits (all **M** unless stated)

| Event | Points | ₹ | Per month at the limit | Fills the Connect Community pool (432) in | Fills the participation limit (180) in |
|---|---:|---:|---:|---|---|
| Connection accepted | 10 | 1.00 | 60 | 43 connections | 18 connections (3 months) |
| Need published | 20 | 2.00 | 40 | 21.6 needs | 9 needs |
| Confirmed helpful | 25 | 2.50 | 200 | 17.3 helps | n/a (not participation) |
| Poster closes the loop | 10 | 1.00 | 20 | | 18 closes |
| Resolved (helper, outside the pool) | 45 | 4.50 | 60 | n/a | n/a |
| Introduction + meeting (outside the pool) | 75 | 7.50 | 50 | n/a | n/a |
| *Reference: one ₹25k–₹1L closure, referrer* | 525 | 52.50 | | 1.2× the whole Connect pool | |

Daily 500 would need about 50 connections or 20 helps in a single day, which the monthly limits prevent.

### 8.3 The 105%: how the allocation really works

`SUBCEILING_PERCENT = {PROCESS 25, CLOSURE 60, OTHER 20}` are per-category **maxima**, not slices of a budget. For every reward the engine computes `allowed = min(requested, category ceiling − category used)`, then the daily and monthly limits, then **`cycle ceiling − all points used`, last**. Therefore:

* The **total can never exceed 100%** whatever the categories do, so the 105% is **safe for liability**.
* The 105% is arithmetic inherited from the original 6,000-point season (1,500 + 3,600 + 1,200 = 6,300) and was never presented as a reservation.
* It means **no category is reserved**. What *is* guaranteed is a minimum for closed business: if every non-closure category is full, closure still has `100% − (25% + 20%) = 55%` = **1,980 / 3,300 / 6,600** points, which covers the largest single referrer reward (**1,890**) on every plan.
* Revision 1 broke that guarantee (non-closure 53% → 1,692 on Connect). **This revision restores it by nesting Community inside `OTHER`**, so non-closure remains 45%. Appendix A section 1 prints the three plans for both designs.

### 8.4 Verified before and after (annual, 400-member approved model)

| | v3 approved | v4 proposed | Type | Change from revision 1 |
|---|---:|---:|:---:|---|
| Max liability per member per cycle | ₹360 / 600 / 1,200 | **same** | M | none |
| Max liability, network | ₹532,800 (12.0%) | **same** | M | none |
| Expected cost | ₹83,006 (1.87%) | **₹88,677 (2.00%)** | E | was ₹93,934 (2.12%) |
| Increase | | **+₹5,671, +0.13 pp** | E | was +₹10,929 |
| Everyone redeems | ₹100,135 (2.26%) | **₹110,108 (2.48%)** | E | was ₹117,225 (2.64%) |
| Community pool, if every member filled it and redeemed it | n/a | **₹63,936 (1.44%)** | M | was ₹42,624 for a different pool |
| Whole `OTHER` pool, if every member filled it and redeemed it | ₹106,560 (2.4%) | **same** | M | (the bound on all non-process, non-closure farming) |

Per-member first-cycle totals (**E**, approved segments; Low 240, Average 100, High 40, Top 20 of 400; includes the one-off profile and, in v4, an assumed share earning TGL Verified):

| Plan | Segment | v3 pts (₹) | v4 pts (₹) | v4 % of ceiling |
|---|---|---:|---:|---:|
| Connect | Low | 115 (11.5) | 160 (16.0) | 4% |
| Connect | Average | 690 (69) | 845 (84.5) | 23% |
| Connect | High | 2,605 (260.5) | 2,635 (263.5) | 73% |
| Connect | Top | 3,600 (360) | 3,600 (360) | 100% |
| Growth | Low | 185 (18.5) | 265 (26.5) | 4% |
| Growth | Average | 1,310 (131) | 1,595 (159.5) | 27% |
| Growth | High / Top | 4,935 / 6,000 | 4,935 / 6,000 | 82% / 100% |
| Elite | Low | 325 (32.5) | 480 (48) | 4% |
| Elite | Average | 2,550 (255) | 3,105 (310.5) | 26% |
| Elite | High / Top | 9,870 / 12,000 | 9,870 / 12,000 | 82% / 100% |

Low and Average members gain a few rupees to tens of rupees a cycle (the point of the layer). High and Top gain nothing in total: the cycle or `OTHER` ceiling already binds.

### 8.5 Sensitivity and the 3% threshold (**E**, annual)

| Activity | v3 expected | v4 expected | v3 all redeem | v4 all redeem |
|---|---:|---:|---:|---:|
| ×0.5 | ₹55,628 (1.25%) | ₹60,300 (1.36%) | ₹64,720 (1.46%) | ₹71,866 (1.62%) |
| ×1 | ₹83,006 (1.87%) | ₹88,677 (2.00%) | ₹100,135 (2.26%) | ₹110,108 (2.48%) |
| **×2** | ₹114,174 (2.57%) | ₹123,083 (2.77%) | **₹144,762 (3.26%)** | **₹161,672 (3.64%)** |
| **×3** | ₹131,292 (2.96%) | ₹140,102 (3.16%) | **₹173,058 (3.90%)** | **₹191,815 (4.32%)** |

* The 3% figure comes from the specification's *proposed* go/no-go thresholds, which management has not approved. The model shows the approved v3 itself exceeds 3% when everyone redeems and activity doubles. **3% is therefore a test to apply to measured data, not something the design guarantees.** The only hard bound is 12% (M).
* If activity doubles or triples, the extra cost comes mostly from the existing referral and closure chain; the Community layer adds roughly +₹9,000 (×2) and +₹8,800 (×3) expected, because it is capped.
* The community pool (12%) is the dial: reduce it first if measured cost is too high.

**Retention break-even (H, margin is an assumption).** Average Connect member: +155 points = ₹15.50; at 70% redemption ₹10.85; against ₹1,500 contribution (50% of ₹3,000) the layer pays for itself if it lifts renewal probability by about **0.7 percentage points**. Growth Average about 0.8 points, Elite Average about 0.8. Replace the 50% margin with TGL's actual contribution margin.

**Budget questions.** *Small acts versus outcomes:* the Community pool is at most 12% of any member's ceiling while closure keeps 55% reserved headroom and is about 39% of issuance in the approved model. *Different plans:* the pool scales with price, so each plan allows the same share. *Connections and needs dominating:* participation is capped at 5% of the ceiling and cannot starve confirmed help.

---

## 9. Member scenarios (all **hypothetical**; Connect plan, one 3-month cycle, ceiling 3,600; one-off rewards excluded)

Computed with the small cap-order script in Appendix A (a re-implementation for illustration, not the engine).

| # | Scenario (hypothetical) | Qualifying activities | Requested | Awarded | ≈ ₹ | Limits and flags | Useful behaviour encouraged? |
|---|---|---|---:|---:|---:|---|---|
| S1 | **Connector, no referrals:** 8 accepted connections a month with 8 different members | 24 first-time accepted connections | 240 | **180** | 18.0 | Monthly limit cuts 6; participation limit exactly reached; no flag | Yes, modestly: encourages up to 6 relevant accepts a month and nothing beyond; weak engagement signal is why it is small |
| S2 | **Need publisher:** 3 distinct valid needs a month, closes one loop | 9 valid needs, 1 poster close | 190 | **130** | 13.0 | Monthly limit cuts 3 needs; duplicates would earn 0 and raise `NEED_DUPLICATE` | Yes: rewards specificity; no reward for volume or for responses received |
| S3 | **Consistent helper:** 8 confirmed helps a month for 8 posters, 5 resolutions, 2 introductions | 24 helps, 5 resolved, 2 introductions | 975 | **720** | 72.0 | Community pool cuts 7 helps; resolution limit cuts 1; `OTHER` ceiling trims one introduction; total equals the whole `OTHER` pool (20%) | Yes: the best-paid community behaviour, but only ~20% of the ceiling; further help earns 0, so a genuine helper still gets more from the referral chain |
| S4 | **Reciprocal pair A↔B:** connect, then each helps the other twice and resolves one need each way | 1 connection, 4 helps, 2 resolutions | 230 | **150** | 15.0 | Reciprocal rule: 230 → 176; pair budget: 176 → 150; flags `HELP_RECIPROCAL`, `HELP_PAIR_REPEAT` | Neutral to discouraging: pure exchange is worth ≤ ₹15 a pair a quarter |
| S5 | **Referrer with closed business:** 3 referrals accepted with direct intro, 3 confirmed meetings, one ₹25k–₹1L verified closure (existing rules) | 3 + 3 + 1 | 795 | **795** | 79.5 | None (process 270 ≤ 900, closure 525 ≤ 2,160); one closure alone is 525 | Yes: verified business remains the dominant earner (the closure is worth more than the whole Community pool) |
| S6 | **Farming ring** of 5 paying members fabricating every confirmation: 4 connections, 9 duplicate-ish needs, 8 helps, 4 resolutions, 4 closes, 4 introductions | all of the above, confirmed by accomplices | 940 | **710** | 71.0 | Monthly limits cut 7; `OTHER` pool is the structural ceiling (₹72); flags `CLOSED_CLUSTER`, `HELP_PAIR_REPEAT` ×4, `NEED_DUPLICATE`; a confirmed fake is reversed ≤ 60 days | No, by design: the best a fully coordinated ring can do is about ₹71 per member per Connect cycle, against ₹3,000 per membership; the loss is network quality, handled by flags, sampling and reversal |

S4 arithmetic: connection 10 + 10 = 20; A→B helps 2 × 25 = 50; A's resolution 45 + poster close 10 = 55; B→A reciprocal helps requested 50, awarded 24; resolution requested 55, awarded 27; total requested 230, after reciprocal 176, after the 150 pair budget **150**.

---

## 10. Anti-abuse: what can be built now, what needs new workflows, what needs privacy approval

| Control | Applies to | Status |
|---|---|---|
| Idempotency key, member row lock, append-only ledger, cap trace | all | **Now** (existing engine) |
| Per-member, per-pair, monthly, pool, `OTHER`, daily, monthly, cycle limits; community pair budget | all | **Now** (small engine additions: `once_per="pair"`, pair-event limit, two nested pools) |
| Rate limits (`enforce`) on connect, need, help, referral request | C1, N1, H1 | **Now** (none exist today) |
| Content rules, duplicate title hash and overlap on stored needs | N1 | **Now** after Phase A adds the hash column |
| Existing flags, reconciliation, admin review, exceptions with reasons | all | **Now** |
| Same-phone match between accounts (`users.phone`, not unique, unverified) | C2, H2, H3 | **Now, flag only** (never refuses: shared office lines exist) |
| Durable connection and need history | C2, N1 | **New workflow** (Phase A) |
| Counterparty confirmations, response store, resolution flow, introduction confirmations | H2–H4 | **New workflow** (Phase B) |
| Moderation queue, 10% need sample, 5% resolution audit, admin removal | N1, H2, H4 | **New workflow** (Phase B) |
| New flags: `CONNECTION_BURST` (> 6 accepted in 24 h), `CLOSED_CLUSTER`, `NEED_DUPLICATE`, `NEED_SELF_ANSWERED`, `HELP_RECIPROCAL`, `HELP_PAIR_REPEAT`, `INSTANT_CONFIRM` (< 5 min, repeated), `RESOLVED_WITHOUT_CONTENT` | all community | **New**, built on `fraud.raise_flag` |
| Salted IP / device hash on **member accounts** | sybil detection | **Requires privacy approval** (precedent: public registrations store an IP hash; accounts do not) |
| Storing response and need text as evidence, retention period | N1, H2 | **Requires a retention and access decision** |
| Cluster analysis of who connects to whom | `CLOSED_CLUSTER` | **Requires a privacy note** (it profiles relationships; keep it aggregate, flag-only) |
| ~~Refuse same business~~, ~~refuse same payer reference~~ | | **Dropped:** unsupported (one business per user; `payments.reference` is TGL's own code) |

**Proportionality.** Rewards of 10–75 points do not justify evidence uploads or admin approval. The primary defences are the small sub-limits and structural ceilings (the worst fully coordinated ring earns about ₹71 per member per cycle). High-value rewards keep their existing evidence and admin verification.

---

## 11. Recommended frontend and backend changes, and how members see points

### 11.1 Events (route → event → idempotency → ledger)

| Event type | Origin → route | Idempotency key | Recipient / points | Reversal | Analytics |
|---|---|---|---|---|---|
| `CONNECTION_ACCEPTED` (new) | Connect / Accept → `POST/PATCH /networking/connections` | `…:connection:{sha256(pair)[:32]}:{member}` | both, 10 | removed ≤ 7 days → void | connections per member; connection → referral / meeting |
| `NEED_PUBLISHED` (new) | Post need → `POST /networking/needs` | `…:need:{need_id}:{poster}` | poster, 20 | removed → void / reverse | needs per member; response rate |
| `NEED_HELP_CONFIRMED` (new) | Offer help → `POST …/needs/{id}/responses`; Helpful → `POST …/responses/{rid}/helpful` | `…:need_response:{rid}:{helper}` | helper, 25 | withdraw ≤ 7 days → void | confirmed helps; time to first helpful |
| `NEED_RESOLVED` (exists, disabled) | Resolve and credit → `POST …/needs/{id}/resolve`; helper acknowledges | `…:need:{id}:{helper}` | helper, 45 | dispute ≤ 7 days → void | resolution rate; days to resolve |
| `NEED_CLOSED` (new) | same call | `…:need:{id}:{poster}` | poster, 10 | same | loop-closing rate |
| `SUCCESSFUL_INTRODUCTION` (exists, disabled) | Introduction response; two confirmations | `…:need_response:{rid}:{helper}` (+ `:meeting`) | helper, 30 (+45) | dispute → void | introductions → meetings |
| `BUSINESS_VERIFIED` (new) | Admin KYB approval route | `…:member:{user}:{user}` | member, 75 | revoke → reverse ≤ 60 days | verified share |

### 11.2 Backend

1. Phase A tables and states (7.2); rate limits.
2. `rules.py`: `growth-points-v4`, new events, nested pools, community pair budget, `REVIEW_MIN_POINTS`; `ZERO_POINT_ACTIONS` narrowed.
3. Migration (next revision): ledger `event_type` CHECK extended (the table is append-only with triggers: rebuild and re-verify them); `community_pool_ceiling` and `community_participation_ceiling` on `growth_point_cycles`. Cycles are frozen when created: v4 applies to cycles starting after the effective date, or the ceilings are derived from `ceiling_points` when the columns are empty.
4. Engine: `once_per="pair"`, pair-event quarterly limit, two nested pool limits, reciprocal factor via the existing `pair_adjust` mechanism.
5. Hooks and sync: `connection_changed`, `need_changed`, `response_changed`; branches in `events.still_invalid` and `jobs.resync_pending`.
6. Fraud flags (section 10); admin moderation queue; export includes the new types.
7. Tests: duplicate, concurrent, remove-and-reconnect, self / alternate, reciprocal, cap-order, reversal, demo-exclusion for each event; update the "nothing that must earn 0 is a reward event" test.

### 11.3 Frontend and member view

Need board: required description with live guidance, response composer, poster inbox (Helpful, Resolve and credit), helper acknowledgement; "I can help" becomes "Offer help" and says points follow confirmed help. Growth Points page: balance first (ready / pending / expiring); **earned by area** (Referrals and deals, Community with "x of 432 this term", Profile and trust, Events); per-row **why or why not** in plain words ("Waiting 7 days", "Already connected", "Limit reached", "Not confirmed yet"); a limits panel in the same words as the rules; pending items labelled with what they await; historical shadow-period points labelled *not redeemable*; estimated value shown as "if redemption opens: up to ₹x, set by your renewal invoice, at most 15%, never cash". No streaks, leaderboards or per-click animation; copy says points reward confirmed help and real business, not activity.

---

## 12. Measuring success

Points issued are not success. Layers: **participation quality** (mutual connections; connection → referral or meeting within 60 days; needs published; share with a response in 7 days ≥ 40%; confirmed helpful in 21 days ≥ 20%); **outcomes** (needs resolved; confirmed meetings and verified closures per 100 active members; share of closures sourced from a need or introduction); **retention** (renewal of participants versus matched non-participants, selection bias acknowledged, staggered rollout preferred); **programme health** (cost ÷ revenue expected and all-redeem; Community share of issuance, alert above 20%; cost per confirmed meeting and per verified closure); **integrity** (void and reversal rate < 5%, review above 10%; flags per 100 members; confirmations within 5 minutes; same-pair concentration).

**Decision rules after two quarters of measured data.** *Effective:* participants show higher conversion or renewal than baseline, reversal < 5%, cost inside budget. *Adjust:* flat outcome lift but clean integrity → cut the value 25–50% or tighten the limit; reversal 5–10% → tighten validation first. *Remove:* reversal > 10% or no lift in outcomes or retention; `PROSPECT_CONTACTED` is the first removal candidate.

**Observation without financial effect.** Phase A records facts only. Revision 2 proposed a separate append-only candidate record. That is **no longer needed**: `backend/scripts/community_candidate_evaluation.py` replays the genuine Phase A history through the reference model on demand, creates no table and no row, prints only labelled HYPOTHETICAL aggregates, and excludes synthetic members (the existing `synthetic_clause`) and backfilled history. It is a lower bound (it cannot see introductions or the Process/Closure points that share the monthly and cycle limits), is never counted in Gate A, and is not an award.

---

## 13. Risks and trade-offs

| Risk | Assessment |
|---|---|
| Reversing a v3 decision (connections, posting, replying earn 0) | Intentional; v3's concern was farming, which the new limits answer, but it needs sign-off |
| Rewards too small to motivate | Possible (₹1–₹7.50). Deliberate; raise values inside the 12% pool before widening it |
| Community displaces approved future events for High / Top members | Real; the cost of keeping 55% closure headroom (section 6) |
| Coordinated rings | Cannot be eliminated; bounded to ≈ ₹71 per member per Connect cycle, flagged, reversible ≤ 60 days |
| Moderation workload | New admin queue; size once volumes are known |
| Poster never confirms | Helpers unpaid; reminders, 30-day lapse, auto-prompt at day 7 |
| Changing an approved future value (resolved 60 → 45, introduction 75 / +150 → 30 / +45) | Needs explicit approval; the approved model counted the old values |
| Accounting and legal | Unchanged questions from specification section 11; points for activity rather than purchase should be named |

---

## 14. Phased plan and launch-readiness checklist

| Phase | Work | Money at stake | Exit criteria |
|---|---|---|---|
| **A. Record facts** | Durable connection history, stateful needs, validation, rate limits, offers recorded | none | Facts accumulating; no regressions |
| **B. Workflows** | Responses, Helpful, resolve-and-credit, introductions, moderation, flags | none | End-to-end and abuse tests pass |
| **C. Candidate observation** | Non-financial candidate record, section 12 analytics | none | ≥ 1 full calendar quarter (two preferred) |
| **D. Decision** | Management reviews measured data | none | Written approval of values, limits, pools |
| **E. v4 in shadow** | New rule version, migration, engine changes | none | Reconciliation clean 60 days; reversal < 5% |
| **F. Member preview** | Updated page and copy | none | Understanding checks |
| **G. Redemption** | Only through the existing Phase 3 gate, approved cutoff and written approvals | first real money | unchanged |

**Launch-readiness checklist (for the eventual implementation).**

1. Policy approved in writing, including each item in section 16.
2. Phase A facts recorded for ≥ 1 quarter; no connection is hard-deleted.
3. Every reward event has a stored, verifiable fact, a sync function, and a branch in `still_invalid` and `resync_pending`.
4. `growth-points-v4` is a new immutable version; v3 rows untouched; `ensure_rule_version` passes.
5. Ledger migration verified on a copy: constraints, append-only triggers, existing rows byte-identical.
6. Cap order tested end to end: reciprocal, pair-once, community pair budget, participation, pool, `OTHER`, daily, monthly, cycle.
7. Closure headroom test: with every non-closure category full, a ₹10L+ referrer reward (1,890) is paid in full on Connect.
8. Idempotency and concurrency tests for each new event; remove-and-reconnect pays once.
9. Void / reversal / expiry tests; no ledger row is edited or deleted.
10. Synthetic members and their activity excluded from every observation metric and from Gate A.
11. Moderation queue staffed with a stated response time (≤ 7 days, inside the pending window).
12. Privacy decisions recorded (IP / device hash, text retention, cluster analysis).
13. Member copy reviewed: estimated value versus actual discount; no promise of redeemability before the cutoff.
14. Real redemption disabled; `GROWTH_POINTS_REDEEMABLE_FROM` empty; no epoch recorded; the cutoff approved in writing is a separate act.

---

## 15. What changed from revision 1

| Item | Revision 1 | Revision 2 |
|---|---|---|
| Community structure | New category, 8% on top | **Nested in `OTHER`: pool 12%, participation 5%**; non-closure stays 45% |
| Connection | 15 each | **10 each** |
| Introduction | 40 + 60 | **30 + 45**, 2 a quarter |
| Need resolved (helper) | 60 | **45** (approved v3 future value, change flagged) |
| TGL Verified | 50 | **75** |
| Community pair budget | none (1,500 only) | **150 a quarter** |
| Expected cost | ₹93,934 (2.12%) | **₹88,677 (2.00%)** |
| Everyone redeems | ₹117,225 (2.64%) | **₹110,108 (2.48%)** |
| Closure headroom | 47% (1,692 on Connect) | **55% (1,980)**, unchanged from v3 |
| "Release sweep" | claimed | removed: pending is derived from `available_at` |
| Same-business / same-payer refusal | proposed | dropped |

---

## 16. Decisions that require explicit management approval

1. **Reverse the v3 zero rule** for connections and need posting; introduce confirmed-help rewards.
2. **Values:** connection 10 each; need published 20; helpful 25; introduction 30 (+45); resolved 45 / 10; TGL Verified 75.
3. **Changes to approved future values:** `NEED_RESOLVED` 60 → 45; `SUCCESSFUL_INTRODUCTION` 75 / +150 → 30 / +45.
4. **Structure:** Community nested in `OTHER` (pool 12%, participation 5%), accepting that it displaces the approved future events for High and Top members; community pair budget 150 a quarter; `REVIEW_MIN_POINTS`.
5. **Needs rules:** 80-character description, 2 rewarded needs a month, 7-day window, removal and 30-day re-post lock, moderation sampling.
6. **Anti-collusion:** reciprocal help at 50% then 0; same-phone as a flag; whether to add IP / device hashing and keep response text (privacy review).
7. **Effective date** and treatment of cycles that already exist.
8. **The 3% threshold:** keep, change or replace, knowing the approved v3 exceeds it at ×2 if everyone redeems; and whether community points count toward it.
9. **Eligibility cutoff (unchanged requirement):** no point, under any version, is redeemable before management approves a precise cutoff in writing; nothing here sets one.

### Consolidated decision register (one list; status of every item is **open** unless stated)

| # | Decision | Owner (to be named by management) | Evidence needed | Status |
|---|---|---|---|---|
| 1 | Reverse the v3 zero rule for connections and need posting | Management | this proposal; observation report | Open |
| 2 | Values: connection 10 each; need 20; helpful 25; introduction 30 (+45); resolved 45 / 10; TGL Verified 75 | Management | observation + shadow evaluator | Open |
| 3 | Changes to approved future values (resolved 60 → 45; introduction 75 / +150 → 30 / +45) | Management | financial model (Appendix A) | Open |
| 4 | Structure: Community nested in OTHER (pool 12%, participation 5%), pair budget 150, `REVIEW_MIN_POINTS`; accept displacement of future events for High/Top | Management | section 6, 8.4 | Open |
| 5 | Needs rules: block or track the 3rd monthly need; calendar month vs rolling 30 days; moderator-removed keeps its slot; category and spacing rules | Product + management | observation of how many members exceed 2 a month | Open (Phase A tracks, does not block) |
| 6 | Anti-collusion: reciprocal 50%; same-phone as flag | Product / risk | HELP_RECIPROCAL and HELP_PAIR_REPEAT signal counts | Open |
| 7 | **Privacy:** IP/device hash on accounts; retention of need and response text; relationship-cluster analysis | Data-protection owner | privacy review; none collected today | Open (not required for Phase A) |
| 8 | **Operations:** moderation queue staffed with a stated response time (≤ 7 days); report cadence and owner | Operations | named owner and cadence | Open |
| 9 | Effective date and treatment of existing cycles | Management | section 11.2 | Open |
| 10 | The 3% cost threshold: keep, change or replace; do community points count? | Finance + management | section 8.5 | Open |
| 11 | Accounting/legal wording for points earned for activity | Finance / legal | specification section 11 | Open |
| 12 | Redemption eligibility cutoff | Management, in writing | unchanged requirement | **Not set; nothing here sets one** |

---

## Appendix A. Reproduction scripts (read-only; no database)

### A.1 Economics. Save as `backend/model_check.py`, run from `backend/` with `.venv/bin/python model_check.py`

```python
"""Independent check of the Growth Points proposal economics. READ-ONLY: imports the approved model constants, touches no database.
Everything marked ASSUMPTION is a hypothetical input, not measured TGL usage."""
import sys; sys.path.insert(0, ".")
from app.rewards import model as M, rules

# 1. facts from the code (mathematical, not assumptions)
PLANS = M.PLANS                                   # {"Connect": (3000, 3), "Growth": (5000, 6), "Elite": (10000, 12)}
CEIL = {p: rules.cycle_ceiling_points(pr * 100) for p, (pr, _) in PLANS.items()}               # 12% of price in points
SUB = rules.SUBCEILING_PERCENT                                                                  # {"PROCESS": 25, "CLOSURE": 60, "OTHER": 20}
print("ceilings", CEIL, "| sub-ceiling shares", SUB, "sum =", sum(SUB.values()), "%")
for p, c in CEIL.items():                         # closure headroom = what is left when every NON-closure category is full
    headroom = c * (1 - (SUB["PROCESS"] + SUB["OTHER"]) / 100)
    draft = c * (1 - (SUB["PROCESS"] + SUB["OTHER"] + 8) / 100)                                  # revision 1: a NEW 8% category on top
    print(f"{p:8s} closure headroom v3 {headroom:6.0f}  revision-1 v4 {draft:6.0f}  largest single referrer reward {rules.split_pool(rules.CLOSURE_POOL['10L_PLUS'])[0]}")
rev = sum(M.CAPACITY * w * PLANS[p][0] * 100 * (12 // PLANS[p][1]) for p, w in M.MIX.items()) / 100
worst = sum(M.CAPACITY * w * CEIL[p] * 0.10 * (12 // PLANS[p][1]) for p, w in M.MIX.items())
print(f"annual revenue Rs{rev:,.0f}; worst case Rs{worst:,.0f} = {worst/rev:.1%}; contractual 15% bound Rs{rev*.15:,.0f}")

# 2. the proposal (final values) and the ASSUMED community activity
V = dict(conn=10, need_pub=20, help=25, close=10, intro=30, intro_meet=45, resolved=45)
LIM_Q = dict(conn=18, need_pub=6, help=24, close=6, intro=2, resolved=4)       # per-quarter limits (6/mo, 2/mo, 8/mo, 2/mo, 2/qtr, 4/qtr)
POOL_PCT, PART_PCT = 0.12, 0.05                # Community pool and its participation sub-limit, both NESTED inside the 20% OTHER pool
COMM = {   # ASSUMPTION: new community activity per member per quarter (the approved model's own need / intros / intro_meet are reused)
    "Low": dict(conn=2, need_pub=.3, help=.5, close=0), "Average": dict(conn=6, need_pub=1.5, help=3, close=.8),
    "High": dict(conn=12, need_pub=4, help=9, close=2), "Top": dict(conn=18, need_pub=6, help=15, close=4)}
VERIFIED_SHARE = {"Low": .1, "Average": .3, "High": .5, "Top": .7}             # ASSUMPTION: share earning the one-off TGL Verified reward

def cycle_points(seg, plan, first, f=1.0, v4=False):
    price, months = PLANS[plan]; pm = price * 100; k = months / 3
    caps, total = rules.category_ceilings(pm), rules.cycle_ceiling_points(pm)
    rq = M._raw_quarter(seg, f); process, closure = rq["process"] * k, rq["closure"] * k
    if not v4:
        other = rq["other"] * k + (rq["profile"] if first else 0)
    else:
        a = {x: y * f for x, y in M.ACTIVITY[seg].items()}; c = {x: y * f for x, y in COMM[seg].items()}
        stay = (min(a["events"], 3) * 45 + min(a["mentor"], 3) * 90 + min(a["invite"], 3) * 225) * k + ((rq["profile"] + VERIFIED_SHARE[seg] * 75) if first else 0)
        part = (min(c["conn"], LIM_Q["conn"]) * V["conn"] + min(c["need_pub"], LIM_Q["need_pub"]) * V["need_pub"] + min(c["close"], LIM_Q["close"]) * V["close"]) * k
        help_ = min(c["help"], LIM_Q["help"]) * V["help"] * k
        pool = min(min(part, PART_PCT * total) + help_, POOL_PCT * total)
        outcomes = (min(a["intros"], LIM_Q["intro"]) * V["intro"] + a["intro_meet"] * V["intro_meet"] + min(a["need"], LIM_Q["resolved"]) * V["resolved"]) * k
        other = stay + pool + outcomes
    capped = min(process, caps["PROCESS"]) + min(closure, caps["CLOSURE"]) + min(other, caps["OTHER"])
    return M._r5(min(capped, total, rules.MONTHLY_CEILING * months))

def network(f=1.0, all_redeem=False, v4=False):
    prop = {k: 1.0 for k in M.SEGMENTS} if all_redeem else M.PROPENSITY; exp = pts = 0
    for plan, w in M.MIX.items():
        months = PLANS[plan][1]
        for seg, n in M.SEGMENTS.items():
            red = earn = 0
            for i in range(12 // months):
                e = cycle_points(seg, plan, i == 0, f, v4); earn += e; red += M.redeemable_paise(e, plan)
            exp += n * w * prop[seg] * red; pts += n * w * earn
    return exp / 100, pts
for f in (0.5, 1, 2, 3):
    r = [network(f, False, False)[0], network(f, False, True)[0], network(f, True, False)[0], network(f, True, True)[0]]
    print(f"x{f}: v3 exp {r[0]:,.0f} ({r[0]/rev:.2%}) | v4 exp {r[1]:,.0f} ({r[1]/rev:.2%}) | v3 all-redeem {r[2]:,.0f} ({r[2]/rev:.2%}) | v4 all-redeem {r[3]:,.0f} ({r[3]/rev:.2%})")
for plan in PLANS:
    for seg in M.SEGMENTS:
        a, b = cycle_points(seg, plan, True, 1.0, False), cycle_points(seg, plan, True, 1.0, True)
        print(f"{plan:8s} {seg:8s} v3 {a:5d} -> v4 {b:5d} ({b/CEIL[plan]:.0%} of the ceiling)")
print("Community pool bound, network, all fill and redeem: Rs", sum(M.CAPACITY*w*.12*CEIL[p]*0.10*(12//PLANS[p][1]) for p,w in M.MIX.items()))
print("OTHER pool bound, network, all fill and redeem:     Rs", sum(M.CAPACITY*w*.20*CEIL[p]*0.10*(12//PLANS[p][1]) for p,w in M.MIX.items()))
```

### A.2 Member scenarios (hypothetical). Plain Python, no imports; run `python3 scen.py`

```python
"""Hypothetical member scenarios, Connect plan, ONE 3-month cycle (ceiling 3,600). A small re-implementation of the proposed cap order for
illustration; it is NOT the reward engine. Every scenario is hypothetical; none is TGL usage data."""
CEIL, OTHER, POOL, PART, PAIR_Q = 3600, 720, 432, 180, 150
V = dict(conn=10, need_pub=20, help=25, close=10, intro=75, resolved=45)       # intro = 30 + 45 meeting bonus, taken together
MONTH_LIM, QTR_LIM = dict(conn=6, need_pub=2, help=8, close=2), dict(intro=2, resolved=4)
POOL_K, PART_K, PAIR_K = ("conn", "need_pub", "close", "help"), ("conn", "need_pub", "close"), ("conn", "help", "resolved", "close", "intro")
def run(events):
    """events: (month, kind, pair, factor); factor = share left after the reciprocal rule (1.0 normally, 0.5 for the second direction)."""
    cm, cq, pair, pool, part, other, cyc, out, cuts = {}, {}, {}, 0, 0, 0, 0, {}, {}
    for month, kind, p, factor in events:
        req = V[kind]; got = req; why = None
        if kind in MONTH_LIM and cm.get((month, kind), 0) >= MONTH_LIM[kind]: got, why = 0, "FREQUENCY_LIMIT"
        if got and kind in QTR_LIM and cq.get(kind, 0) >= QTR_LIM[kind]: got, why = 0, "FREQUENCY_LIMIT"
        if got and kind == "conn" and ("conn", p) in pair: got, why = 0, "PAIR_ONCE"
        if got and factor < 1: got, why = int(got * factor), "PAIR_RECIPROCAL"
        if got and p and kind in PAIR_K:
            left = PAIR_Q - pair.get(("c", p), 0)
            if left < got: got, why = max(0, left), "PAIR_COMMUNITY"
        if got and kind in PART_K and part + got > PART: got, why = max(0, PART - part), "COMMUNITY_PARTICIPATION"
        if got and kind in POOL_K and pool + got > POOL: got, why = max(0, POOL - pool), "COMMUNITY_POOL"
        if got and other + got > OTHER: got, why = max(0, OTHER - other), "CATEGORY_SUBCEILING"
        if got and cyc + got > CEIL: got, why = max(0, CEIL - cyc), "CYCLE_CEILING"
        if got and kind in MONTH_LIM: cm[(month, kind)] = cm.get((month, kind), 0) + 1
        if got and kind in QTR_LIM: cq[kind] = cq.get(kind, 0) + 1
        if got and kind == "conn": pair[("conn", p)] = 1
        if got and p and kind in PAIR_K: pair[("c", p)] = pair.get(("c", p), 0) + got
        other += got; cyc += got; pool += got if kind in POOL_K else 0; part += got if kind in PART_K else 0
        o = out.setdefault(kind, [0, 0]); o[0] += req; o[1] += got
        if why and got < req: cuts[why] = cuts.get(why, 0) + 1
    return out, cuts
def show(name, events):
    out, cuts = run(events); r = sum(v[0] for v in out.values()); g = sum(v[1] for v in out.values())
    print(f"{name}: requested {r} -> awarded {g} (Rs{g/10:.1f}, {g/CEIL:.1%} of the ceiling) | {out} | cuts {cuts}")
M3 = (1, 2, 3)
show("S1 connector", [(m, "conn", f"c{m}{i}", 1) for m in M3 for i in range(8)])
show("S2 publisher", [(m, "need_pub", None, 1) for m in M3 for _ in range(3)] + [(3, "close", "x", 1)])
show("S3 helper", [(m, "help", f"h{m}{i}", 1) for m in M3 for i in range(8)] + [(3, "resolved", f"r{i}", 1) for i in range(5)] + [(2, "intro", "i1", 1), (3, "intro", "i2", 1)])
# S4 (reciprocal pair) is arithmetic, shown in section 9: the pair budget is combined over BOTH members.
ring = [(1, "conn", f"R{i}", 1) for i in range(4)] + [(m, "need_pub", None, 1) for m in M3 for _ in range(3)] \
     + [(m, "help", f"R{i}", 1) for i in range(4) for m in (1, 2)] + [(3, "resolved", f"R{i}", 1) for i in range(4)] + [(3, "close", f"R{i}", 1) for i in range(4)] \
     + [(2, "intro", f"I{i}", 1) for i in range(4)]
show("S6 ring of 5 paying members", ring)
```

Output used in this document: S1 240 → 180; S2 190 → 130; S3 975 → 720; S6 940 → 710.
