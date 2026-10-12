# Phase 1: shadow go-live checklist

**Status: READY FOR CONTROLLED SHADOW LAUNCH.** The business decisions are locked (section 0). The real-member observation period has **not** been started and must not start until management explicitly authorises it and the launch prerequisites in section 6 are done.

**Real financial effect = ₹0.** No discount, no payment change, no subscription-price change, no redemption, no cash value, no transfer. Shadow ledger only.
**Member preview is OFF** (`GROWTH_POINTS_MEMBER_PREVIEW=false`) and stays off for the whole initial observation period. Admin analytics are enabled.

Evidence is from `backend/test_phase1.py` (**366/366 on SQLite, 367/367 on PostgreSQL 17**), a PostgreSQL statement trace, and the migration rehearsals in the implementation report. Nothing is committed or pushed.

---

## 0. Locked business decisions (recorded from management's instruction)

| # | Decision | Implemented as | Tested |
|---|---|---|---|
| 1 | 1 point = ₹0.10 | `PAISE_PER_POINT = 10` | yes |
| 2 | Redemption ceiling 15 % of the subscription price | hypothetical only: ₹450 / ₹750 / ₹1,500 | yes |
| 3 | Earning ceiling 12 % per subscription cycle | 3,600 / 6,000 / 12,000 points | yes |
| 4 | Terms: Connect ₹3,000 / 3 mo, Growth ₹5,000 / 6 mo, Elite ₹10,000 / 12 mo | read from the invoice's frozen price and term | yes |
| 5 | Daily ceiling 500, Option C | `requested → awarded → capped`, `capped_by = DAILY_CEILING`, reward table unchanged | yes |
| 6 | **Plan change: only at renewal** (replaces the earlier "Option A") | no mid-cycle upgrade or downgrade; the renewal chooses the next plan; old points stay in their cycle, never move into the new cycle, are not deleted; **eligible old-cycle points may be used (hypothetically) against the NEW renewal invoice, up to 15 % of the NEW plan's price, FIFO**; the new cycle starts with zero transferred earning points. See `PHASE_1_SUBSCRIPTION_RENEWAL_RULE.md` | yes |
| 7 | Late false deals | 0–60 days normal reversal; after 60 days an OPEN admin review flag, no automatic reversal; an approved reversal is a new append-only row | yes |
| 8 | Member preview | OFF; admin analytics on | yes |
| 9 | Pair exceptions | **programme owner only** (see section 0.1) | yes |
| 10 | Fraud thresholds | observation/review thresholds; flag → inspect → record outcome → tune; **no automatic reduction or suspension from a fraud signal** | yes |
| 11 | Profile completion | strict server-side definition, one-time, system-verified, not repeatable, not claimable | yes |
| 12 | Reconciliation | owned by the programme owner (section 0.2) | n/a |

`DAILY_CEILING` is the name used in the ledger (consistent with `MONTHLY_CEILING` and `CYCLE_CEILING`). The only automatic reductions are the spec's own pair rules and ceilings; each is recorded on the row.

### 0.1 Pair-exception approval (the role)

The project has no admin-roles table, so the strongest appropriate role is the **programme owner**: the admin account(s) listed in the `PROGRAMME_OWNER_EMAILS` environment variable (comma-separated). **It is empty by default, and empty means nobody can approve an exception** (fail closed). An ordinary admin, a member, an anonymous visitor, or a request without the CSRF token is refused (HTTP 401/403). Ordinary admins can still read the exception list.

Each approved exception writes an audit entry `growth_points.pair_exception` (readable at `GET /api/admin/growth-points/exceptions`) holding: **approver** (admin id), **reason**, **pair**, **event**, **timestamp**, the **original cap** (per member: requested, awarded, capped, capped_by) and the **approved amount** (per member). The ledger rows it adds are new rows (`created_by` = the approver); the original zero-point row stays. The approved amount is still bounded by every ceiling (e.g. the monthly 3,000).

### 0.2 Responsibilities (all held by the programme owner role)

| Responsibility | Owner | Cadence |
|---|---|---|
| Daily reconciliation (admin "Reconcile"; no drift, no violations; "real financial cost" tile = ₹0) | programme owner | every day of the observation period |
| Fraud-flag queue (inspect each OPEN flag; record the outcome: reviewed or dismissed, with a reason) | programme owner | at least every working day |
| Late-reversal flags (`REVERSAL_NEEDS_REVIEW`): decide dismiss or reverse | programme owner | as they appear |
| Pair-exception approvals | programme owner | on request |
| Escalation (any drift, any real financial cost above ₹0, repeated hook failures in the `tgl.rewards` log) | programme owner → management; **disable shadow mode first** (section 5) | immediately |

No alerting system is built (none exists in the project): monitoring is the daily manual check above plus the `tgl.rewards` log. That is an accepted limitation for the observation period.

---

## 1. Decision records

### 1.1 The 525 / 500 conflict: **Option C** (decided; locked decision 5)

Facts: the referrer's 70 % of the ₹25K–1L pool is 525; the daily ceiling for **low-assurance** points (levels 1–2) is 500. A ₹25K–1L closure confirmed by both members is level 2, so it is low assurance. Verified closures (level 3+, evidence checked) are exempt from the daily ceiling by the spec ("a verified closure reward is not split across days").

| | Member experience | Economic impact | Rule simplicity | Verdict |
|---|---|---|---|---|
| **A** keep 525, let a single event exceed the daily ceiling | Best: gets the table value | +25 points (₹2.50 hypothetical) per such closure; but the daily ceiling then has an exception, and the spec's "no pair rule can raise any member above 500 a day" no longer holds | Worse: a ceiling with a carve-out | no |
| **B** make the reward exactly 500 | Hidden: the member never learns 25 points were not paid | Changes the approved table (pool 750 split 70/30 would become 500/225) and the 70/30 rule | Changes a business rule, and is invisible in the ledger | no |
| **C** keep 525, daily ceiling is a total cap, record `requested 525 / awarded 500 / capped 25` | Visible and explainable ("daily limit"); a verified (level 3) closure pays the full 525, which rewards uploading evidence | ≤ 25 points (₹2.50 hypothetical) per low-assurance closure in that band; the daily financial ceiling holds | Best: one rule, no exception, table untouched | **chosen** |

Implemented as it already behaved; now locked in by tests. Consequences to be aware of: (1) the 500 is a *total* for the day, so a closure on a day that already had other low-assurance points is cut by more than 25 (e.g. after 90 process points it is 410); (2) the 25 cut points are lost, not carried over; (3) `capped_by` is `DAILY_CEILING` (the spec's term, consistent with `MONTHLY_CEILING` and `CYCLE_CEILING`), not `DAILY_LIMIT`.

### 1.2 Plan change: **only at renewal** (decided; locked decision 6; supersedes the earlier Option A below)

Today there is no self-service upgrade or downgrade: a second subscription is refused while one is live; the only route is an admin refund followed by a new subscription. The rule below defines what shadow mode does and what a future flow must follow.

| | Fairness | Abuse | Simplicity | Financial exposure |
|---|---|---|---|---|
| **A** points stay in the old cycle until its expiry; the new plan starts a clean cycle | Nothing is lost or reset; each plan earns only against its own ceilings | Cannot raise a ceiling by upgrading and moving points | Simplest: the cycle is the unit | Bounded by each cycle's own 12 % ceiling |
| **B** points transfer to the new cycle with the new ceiling | Generous | Buy the cheap plan, earn, upgrade, inherit a larger ceiling: ceilings no longer bound the points | Needs a transfer rule and re-capping | Highest |
| **C** points frozen until the next eligible renewal | Harsh: points idle for months | Low | More states (frozen, thawed) | Lowest but delays all value |

Chosen: **A**. Tested: old points keep their old cycle, are not deleted or reset, expire at the end of the *old* cycle's grace, and the new cycle has its own ceilings (Growth 6,000 → Elite 12,000). Known consequence for a later phase: if the old term was refunded, its cycle (and grace) can end earlier than the original term; how old points are then redeemed (Phase 2) must be decided with this rule.

### 1.3 Late false deal (after 60 days): **keep the admin review policy**

Within 60 days a disputed or invalidated deal reverses automatically (new `REVERSAL` rows). After 60 days the engine does **nothing automatic**: it raises an `OPEN` `REVERSAL_NEEDS_REVIEW` flag per lot (the admin review state). An admin either dismisses it (points stand) or applies a reversal with a reason (`POST /api/admin/growth-points/flags/{id}/apply-reversal`): a **new** row, `created_by` = that admin, original untouched, audited, refused if the deal is valid again. Tested. The policy is decided (locked decision 7).

### 1.4 Member preview: stays **off**

`GROWTH_POINTS_MEMBER_PREVIEW=false` in code and `.env.example`. Admin analytics are available regardless. Enabling the preview for members requires management approval after the observation model has been validated.

---

## 2. Query cost (PostgreSQL 17, one reward event)

Measured with a `before_cursor_execute` trace of the hook (`hooks.referral_changed`) on PostgreSQL, two ledger rows per event (referrer and recipient). The trace script is not part of the repository; the figures are reproducible through the `reward_overhead_queries` line printed by `test_phase1.py`.

### CURRENT QUERY BREAKDOWN (before optimization)

| Statement group | Cold event (first ever for the pair) | Why |
|---|---|---|
| SELECT `growth_point_ledger` | 15 | idempotency key ×2, one aggregate **per rule** ×2 members (pair budget, sub-ceiling, daily, monthly, cycle, frequency = up to 6 each), lots, fraud pair count |
| SELECT `growth_point_balances` | 6 (+3 `FOR UPDATE`) | the same two balance rows read and locked again by **every** award |
| SELECT `business_referrals` | 3 | the referral, plus two fraud checks |
| SELECT subscriptions / memberships / invoices / plans / cycles | 2 / 2 / 2 / 2 / 2 | the member's terms, invoice and plan **re-read for every award**, the cycle looked up again |
| SELECT/INSERT rule version | 1 + 1 | first use only |
| INSERT ledger / balances / cycles | 2 / 2 / 2 | the rows themselves (balances and cycles first use only) |
| UPDATE balances | 2 | cached balance |
| **Total** | **47** (38 SELECT, 7 INSERT, 2 UPDATE) | warm ≈ 37 (cold minus the 10 first-use statements); a request that earned paid **+41** over the same request without shadow mode |

Other events before: replay of an already-rewarded referral **16** statements; meeting event **52**. Reconciliation queries are **not** on the event path (reconciliation runs only from the admin button). Repeated rule lookups: one per process (cached), not per event.

### OPTIMIZED QUERY PLAN (implemented)

Correctness-preserving only; no validation moved anywhere else.

1. **One lock query per transaction** (`engine.lock_members`): a member already locked in the transaction is not re-read or re-locked (the lock lasts until commit; the cache is dropped at commit or rollback). Saves ~8.
2. **One usage query instead of up to six** (`engine._usage`): pair budget, category sub-ceiling, daily, monthly, cycle and monthly frequency are read together with conditional sums. The same numbers, read once, applied in the same spec order. Saves ~10.
3. **Cycle resolved once per transaction** (`cycles.resolve_cycle`): the member's terms are read once; a cycle already frozen for a term is found by its unique `(source_type, source_id)`; invoice and plan are read only the first time a term becomes a cycle. Saves ~8.
4. **Fraud/gaming signals run only when something was newly rewarded**, not on every replay (they are deduplicated review items; the batch scan still covers everything). Saves ~4 on each replay.
5. Closure rewards read both members' existing rows in one query.

| Measure (PostgreSQL) | Before | After |
|---|---|---|
| Referral-accepted hook, cold (2 rows) | 47 | **31** |
| Referral-accepted hook, warm (2 rows) | ≈ 37 | **21** |
| Replay of an already-rewarded event | 16 | **5** |
| Meeting-completed hook (2 rows) | 52 | **25** |
| Closure replay | 8 | **7** |
| Extra statements on a whole earning request | **41** | **20–22** |

Further reductions (not done, to avoid risk): merging the per-member term/cycle lookups across a pair (-2), and skipping the idempotency read by `INSERT … ON CONFLICT` (-2 per award). The work runs after the member's request has committed, in its own session, so it adds no latency to the request and its failure cannot fail it.

The cache is per transaction; on SQLite (development only) the existing write-lock/retry behaviour still applies, and PostgreSQL row locks are unchanged in effect (the same rows, in the same sorted order, held to commit).

---

## 3. Checklist

### TECHNICAL

- [x] PostgreSQL reward tests pass (367/367 on PostgreSQL 17; 366/366 on SQLite)
- [x] reward event idempotency works
- [x] pair assurance works (budget, verified exemption, quarter reset, concentration, reciprocal, programme-owner exception with full record)
- [x] cycle ceilings work (500 daily, 3,000 monthly, 12 % cycle, 60 % closed-business sub-ceiling; plan-aware)
- [x] expiry works (cycle-relative, end of grace)
- [x] reversal works (void, reversal, late-dispute review, admin-applied reversal as a new row)
- [x] financial firewall works
- [x] query cost is acceptable (section 2)
- [x] reconciliation works
- [x] no member preview unless explicitly enabled (OFF)
- [x] plan changes only at renewal: mid-cycle upgrade, downgrade and member cancellation rejected; renewal into the same, a higher and a lower plan tested; old points stay in their cycle; new cycle starts at zero; eligible old points used (hypothetically) FIFO against the NEW invoice up to 15 % of the NEW price; admin refund-and-replace creates no loophole
- [x] profile completion is strict, one-time and not claimable (tested end to end)
- [x] observation analytics available for every success metric (section 4)

### BUSINESS (decided: section 0)

- [x] B1 12 % earning ceiling · [x] B2 15 % redemption ceiling · [x] B3 3/6/12-month terms · [x] B4 expiry/renewal policy (cycle-relative, 30 days before to 30 days after, no carry-forward)
- [x] B5 upgrade/downgrade: Option A · [x] B6 60-day late-dispute policy · [x] B7 pair-exception approver: programme owner
- [x] B8 fraud thresholds: observation/review thresholds, no automatic punishment · [x] B9 daily ceiling: Option C · [x] B10 profile completion: strict definition kept

Still open, deliberately and not blocking shadow launch: (a) whether and when members ever see the preview, which also decides when members can see the renewal calculation (the master plan wants the member to see it before confirming, but the preview is OFF); (b) what happens to a shadow-used renewal that is later refunded (flag only in Phase 1); (c) early renewal in the 30 days before the term ends is not supported by the Phase 0 subscription flow; (d) points of a refunded term are treated as never eligible; (e) the Season 1 complimentary term (one 3-month cycle with Connect ceilings).

### OPERATIONAL

- [x] monitoring defined: manual daily check by the programme owner (reconcile, real-cost tile, flag queue, `tgl.rewards` log); no alerting system, by decision
- [x] admin review process defined (section 0.2)
- [x] shadow analytics available · [x] export works (`GET /api/admin/growth-points/export`) · [x] rollback/disable procedure documented (section 5)

---

## 4. Observation period: what is recorded and how it is judged

The admin tab **Growth Points (shadow) → Observation** and `GET /api/admin/growth-points/observation` (admin only; aggregates only; nothing public; no email, phone, member id or deal value) report:

| # | Success metric | Where |
|---|---|---|
| 1–2 | Average and median points per member | `success_metrics.points_per_member` |
| 3–4 | P90 and P95 points per member | same |
| 5 | Top 1 % of members: their points and share of all points | same |
| 6 | Points per rewarded referral | `points_per_referral` |
| 7 | Points per meeting | `points_per_meeting` |
| 8 | Points per verified closed deal | `points_per_verified_closed_deal` |
| 9 | Points by subscription plan | `points_by_plan` (also normalised per member-year) |
| 10 | Points by cycle length (3 / 6 / 12 months) | `points_by_cycle_length` (per member-month) |
| 11 | Hypothetical redemption cost | now, maximum potential, projected annual, worst-case annual (all labelled hypothetical) |
| 12 | Hypothetical reward cost as % of subscription revenue | projected, worst case, outstanding now |
| 13 | Number of capped rewards | `ledger.capped_rewards`, `fully_capped_rewards`, points capped, and by rule on the Overview tab |
| 14 | Number of fraud flags | `fraud_flags` (total, open, by kind) |
| 15 | Number of reversed rewards | `ledger.reversed_rewards`, voided, expired lots and points |
| 16 | Repeat / circular referral patterns | reciprocal pairs, pairs with two or more rewarded closures, top pair's share of closed-business points, related flag counts |

Also recorded: points earned, capped, expired, reversed; points by event; pair concentration; hypothetical redemption and annual liability (Overview, Economics and Observation tabs). Percentiles are nearest-rank over the active members, members with no points counting as 0.

**Modelled vs actual** (`modelled_vs_actual`): plan mix (55/35/10), accepted referrals, meetings and verified deals per member-month, points per member-month, expected annual cost per member and as % of revenue (modelled 1.87 % expected, 12 % worst case). They are compared per member-month, never as raw totals, because the member counts differ.

| 17–20 | Renewal redemption by plan; average old-cycle points used at renewal; points stranded by non-renewal; points expired before redemption | `success_metrics.renewals` |

The **Gate A review** (`GET /api/admin/growth-points/review`, admin tab Observation, `python -m app.rewards.review`) adds the activity, reward, risk and economic dashboard blocks, the modelled-vs-actual comparison (including conversion), **proposed model changes** (never applied; each with current rule, observed behaviour, financial impact and recommended change) and the ten exit-criteria questions with their evidence. Its status is only ever a suggestion (`INSUFFICIENT DATA` until at least 30 active members and 30 days); management decides PASS or RECALIBRATE and the move to Phase 2.

**No fixed end date.** The period is not ended after a number of days. The management review happens when there is enough real data; `sufficiency` reports what exists (observed days, active members, whether all three plans are present, member-months, rewarded referrals, meetings and verified deals, whether a projection is available) and the review must at minimum report: observed active members, observed plan mix, observed networking activity, observed points, observed hypothetical liability, observed fraud and capping patterns.

---

## 5. Starting, observing and stopping (nothing here has been run)

**Disable (also the escalation action):** set `GROWTH_POINTS_SHADOW_MODE=false` and restart. Every hook becomes a no-op at once (tested); members and payments are unaffected; recorded rows stay and the analytics remain readable. Turning it back on and sweeping issues what was missed exactly once.

**Remove entirely (rare):** export first. The migration downgrade of 0010 is **refused** while the ledger holds rows; it needs `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1`.

**There is no money to stop:** no code path applies points to an invoice or payment, and the application refuses to start with `GROWTH_POINTS_REDEMPTION_ENABLED=true`.

## 6. Launch prerequisites (all must be done before management authorises the start)

1. Management's explicit authorisation to start the observation period.
2. `PROGRAMME_OWNER_EMAILS` set to the real programme-owner admin account(s) (empty = nobody can approve a pair exception).
3. `GROWTH_POINTS_REDEMPTION_ENABLED=false` and `GROWTH_POINTS_MEMBER_PREVIEW=false` confirmed in the target environment; `SUBSCRIPTION_PRICING_CONFIRMED` unchanged.
4. Migration 0010 (now also creating `growth_point_renewals`; edited in place because it has not been deployed anywhere) run on **staging** and verified with `scripts/verify_phase0_migration.py` (it has so far been rehearsed on local SQLite and PostgreSQL copies only), then production (`python -m app.migrate`; additive).
5. The programme owner has seen the admin tab in a browser. (The new tabs were built and linted but not yet exercised in one.)
6. A baseline recorded before switching on: "real financial cost" = ₹0 and reconcile clean.
7. Then, and only then: `GROWTH_POINTS_SHADOW_MODE=true`, restart, run the sweep once to backfill, re-check the baseline.

## 7. Statements

* **REAL FINANCIAL EFFECT = ₹0.** Verified by a hash of every invoice, payment, subscription and plan row before and after all reward activity; every invoice has zero discount; every payment equals its invoice; no shadow table has a cash, transfer, refund, payment or invoice column; no financial module references the rewards package; the route inventory contains no transfer, cash-out or apply-to-invoice endpoint; redemption always refuses.
* **Member preview is OFF.**
* **The observation period has not been started.**

## 8. Gate A preparation: what was actually done and what is blocked

| Item | Result |
|---|---|
| member preview OFF | **done and tested** (default false in code and `.env.example`; a gate item reads the live flag) |
| `PROGRAMME_OWNER_EMAILS` configured safely | the variable and the fail-closed rule are built and tested; **the real owner account must be set by whoever deploys** (empty = nobody can approve an exception) |
| designated high-trust role for pair exceptions | **done and tested** (ordinary admin refused) |
| migration 0010 applied to staging, staging verification | **NOT DONE: external blocker.** No staging or production credentials exist in this environment (only the local development database), and a real database must not be migrated without them. Verified instead on local SQLite and PostgreSQL 17 copies from empty, 0007, 0008 and 0009 |
| admin Growth Points dashboard tested in a real browser | **done** (local throwaway server, synthetic data used only to look at the screens): login, the Growth Points tab, Overview, Observation with the Gate A dashboard, exit criteria, modelled vs actual, renewal-preview and renewals through the admin session, member preview endpoint refused. It found two real defects (absurd per-member-year figures from under one member-month of data; reconciliation not part of the review), both fixed and tested |
| renewal-preview / review functionality | **confirmed** in the browser session and by tests |
| no member sees shadow monetary values | **tested** (preview returns only "coming soon"; a member session gets 401 on every admin route) |
| financial safeguards active | **tested** (firewall, closed route inventory, hash of every invoice/payment/subscription/plan unchanged, discount 0) |
| launch prerequisites documented | section 6 above, `GROWTH_POINTS_PRODUCTION_RUNBOOK.md`, objective gates (`python -m app.rewards.gates`) |

**The real-member observation period has not been started and was not simulated.** Turning shadow processing on in a real environment needs that environment's credentials and the steps in section 6; until then Phase 1 is recorded as **INSUFFICIENT DATA / NOT READY** (`docs/PHASE_1_SHADOW_REVIEW.md`), and Phases 2 and 3 remain blocked.

## 9. Phase 2 note

Real redemption is now built and rehearsed (`PHASE_2_REDEMPTION_READINESS.md`) but **disabled**: the shadow observation above is unchanged, still has no real data, and Gate A still gates everything. The shadow renewal simulation stops running once real redemption is enabled (the real records replace it). Migrations: 0010 (shadow) and 0011 (redemption infrastructure, additive) both need the staging rehearsal in section 8 before any real database.
