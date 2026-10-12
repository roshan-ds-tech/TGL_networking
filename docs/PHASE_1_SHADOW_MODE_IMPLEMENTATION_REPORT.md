# Phase 1: Growth Points, SHADOW MODE: implementation report

**REAL FINANCIAL EFFECT = ₹0.**
No member receives a discount, no money is saved, no invoice is reduced, no payment amount changes, nothing can be redeemed,
and no member balance is used as currency. Growth Points exist as a *recorded simulation* only.

Rule version: `growth-points-v3`. Sources of truth: `docs/GROWTH_POINTS_FINAL_SPEC.md` (v3) and
`docs/GROWTH_POINTS_ECONOMY_RECALCULATION.md`. Nothing is committed or pushed; all work is in the working tree.

---

## 1. Status and scope

| | |
|---|---|
| Phase 1 gate | **PASS**, then hardened (see "Pre-shadow hardening" at the end): technically ready for a controlled shadow launch, with management approvals still open (`docs/PHASE_1_SHADOW_GO_LIVE_CHECKLIST.md`) |
| Mode | Shadow only. `GROWTH_POINTS_SHADOW_MODE` defaults **false**; `GROWTH_POINTS_REDEMPTION_ENABLED` is **false** and the application *refuses to start* if it is set to true |
| Not done (by instruction) | Redemption, financial rewards, any change to invoices/payments/subscriptions, commit, push |
| Not redone | Phase 0 (subscriptions, invoices, payments, meeting/deal verification, evidence, admin referral management) is reused as is |

## 2. What was built

* **Central reward engine** `backend/app/rewards/`: `rules.py` (every number, one place), `engine.py` (cap pipeline + award/adjust), `events.py` (verified state → rewards), `cycles.py` (the member's real paid term), `ledger.py`, `firewall.py`, `fraud.py`, `simulation.py`, `jobs.py` (expiry/sweep, CLI `python -m app.rewards.jobs`), `hooks.py`, `reconcile.py`, `analytics.py`, `model.py` (400-member model).
* **Append-only shadow ledger** `growth_point_ledger` (+ `growth_point_rule_versions`, `growth_point_cycles`, `growth_point_balances`, `growth_point_flags`), migration `0010`.
* **Routes**: member `GET /api/v1/growth-points/preview` and an always-refused `POST /api/v1/growth-points/redeem`; admin read endpoints, CSV/JSON export, and five audited write actions under `/api/admin/growth-points/*`.
* **UI**: member "Growth Points: coming soon" shadow card on the Membership page (off unless `GROWTH_POINTS_MEMBER_PREVIEW=true`); admin dashboard tab "Growth Points (shadow)".
* **Docs/tests**: this report, `backend/test_phase1.py` (225 checks, 226 on PostgreSQL), migration rehearsal script extended to 0010.

## 3. Reward engine

Rewards are **state-driven and idempotent**. After a Phase 0 transaction commits, a hook (`rewards/hooks.py`) re-reads the *stored, verified* referral, closure or profile and issues only the rewards that should exist but do not. The client never supplies points, bands, levels, roles or pools; the closed-business band comes from the server-derived `value_band` of the *actual* value.

Hooks run **after** the business commit, in their own session, so a reward failure can never fail or roll back a member's request. A failure is logged and healed by the next sweep/backfill (`POST /api/admin/growth-points/sweep`, or the CLI).

| Event | Referrer | Recipient | Level | Notes |
|---|---|---|---|---|
| Referral created | 0 | 0 | n/a | creating a referral earns nothing |
| REFERRAL_ACCEPTED | 30 (+15 direct introduction / arranged meeting) | 15 | L1 | referrer ≤ 10 rewarded / month |
| PROSPECT_CONTACTED | n/a | 15 | L1 | within 72 h of accepting, else recorded as 0 `OUTSIDE_WINDOW` |
| MEETING_COMPLETED | 45 | 60 | L2 | only when **both** members confirmed; referrer ≤ 8 / month |
| BUSINESS_CLOSED | 70 % of band pool | 30 % | L3/L4 | pools 300 / 750 / 1,500 / 2,100 / 2,700; floor to referrer, remainder to recipient (no point lost or invented) |
| REPEAT_BUSINESS | 50 % of the band pool | | L3/L4 | same prospect (hashed), once per prospect per quarter |
| PROFILE_COMPLETED | 75 once | | L3 | personal + business (founder story, online link) + photo |

Points for views, likes, logins, connections, posting or replying to a need, or arbitrary clicks: **none exist** (`ZERO_POINT_ACTIONS` is data, and a test proves no event or hook issues them).
Five approved-but-unbuildable events (event attendance, introductions, need resolved, mentoring, invitations) are in the catalogue **disabled**, because the features do not exist yet.

Cap pipeline, in specification order, each step recording `requested`, `awarded`, `capped`, `capped_by` and a JSON `cap_trace`:
pair rules → frequency / repeat limits → category sub-ceiling → daily (500, low-assurance only) → monthly (3,000) → cycle ceiling.

## 4. Shadow ledger

Columns (all required ones present): id, created_at, event_at, member_id, counterparty_id, pair_key, entry_type (EARN / VOID / REVERSAL / EXPIRY), event_type, category, role, reference_type/id, parent_id, cycle_id, prospect_key (hash), points_delta, requested_points, capped_points, capped_by, cap_trace, status (PENDING / AVAILABLE / CAPPED / VOIDED / REVERSED / EXPIRED), assurance, verification_level, available_at, expires_at, remaining, balance_after, reason, details, created_by, rule_version, idempotency_key (unique), shadow, day_key / month_key / quarter_key.

* **Append-only** at three layers: ORM guard, database triggers (UPDATE/DELETE on both engines, TRUNCATE on PostgreSQL), and no API that writes a row directly.
* **Database CHECKs**: `shadow = true` (a non-shadow row cannot exist), `REDEMPTION` is not an allowed event type, a level-0 (self-reported) row cannot carry points, sign/parent/remaining rules.
* **Reversals are new rows** (`VOID` before points are usable, `REVERSAL` after, `EXPIRY` at the end of grace), each pointing at the lot (`parent_id`). The original row is never touched; remaining points and PENDING/AVAILABLE are derived.
* **Idempotency key** `event:reference_type:reference_id:member(+suffix)`, unique in the database.
* **Cached balance** `growth_point_balances` is derived data, updated in the same transaction, and used as the per-member lock (`SELECT … FOR UPDATE`; both parties locked in sorted order, so no deadlock).
* **Rule versioning**: every row stores `rule_version`. The parameters of a version are stored with a SHA-256; the engine refuses to run if code and stored parameters differ for the same version, so history stays explainable. A rule change therefore *requires* a new version.
* **Privacy**: prospects are stored as a truncated hash, never a phone/email; the exact deal value is never written to the ledger (only the band); exports and admin ledger rows contain ids, points, rules and bands only.

## 5. Plan-aware rules (3 / 6 / 12-month cycles)

A **cycle** is the member's actual paid term, read from `subscriptions` + the invoice's frozen price/term (never today's plan row). It freezes its own ceilings in `growth_point_cycles`.

| Plan | Price | Term | Cycle ceiling (12 %) | Process 25 % | Closed business 60 % | Other 20 % | Contractual cap (15 %), hypothetical |
|---|---|---|---|---|---|---|---|
| Connect | ₹3,000 | 3 mo | 3,600 | 900 | 2,160 | 720 | ₹450 = 4,500 pts |
| Growth | ₹5,000 | 6 mo | 6,000 | 1,500 | 3,600 | 1,200 | ₹750 = 7,500 pts |
| Elite | ₹10,000 | 12 mo | 12,000 | 3,000 | 7,200 | 2,400 | ₹1,500 = 15,000 pts |

* The closed-business sub-ceiling is **per subscription cycle and does not reset every 3 months on Elite** (tested: 7,200 across a 12-month cycle, still refused in the last quarter).
* Daily (500, low-assurance only) and monthly (3,000) ceilings use **business time** (IST, UTC+05:30): a UTC evening on 31 Dec is already next quarter.
* A Season 1 complimentary term counts as one 3-month cycle with Connect's ceilings.
* Sub-ceilings and the cycle ceiling can never be exceeded however they are reached (partial awards are recorded: e.g. 720 requested, 540 awarded, 180 capped by `CYCLE_CEILING`).

## 6. Pair Assurance Rule (per calendar quarter)

* **P1** Low-assurance (L1/L2) points between two members, both directions combined: **1,500 per quarter**, then 0 recorded as `PAIR_LOW_ASSURANCE`. The pair key is order-independent. Verified (L3/L4) closures are exempt.
* **P3** The first two verified closures between a pair pay in full; a *reciprocal* closure needs level 4 and pays 50 % (`PAIR_RECIPROCAL_NEEDS_L4` → 0 until an admin raises it; then `PAIR_RECIPROCAL`); a third or later pays 0 (`PAIR_CONCENTRATION`).
* **P4** Review flags (frequency, concentration, reciprocal, same prospect across pairs, rapid closure). Flags never auto-punish.
* An admin can record a **reasoned exception** (`POST …/closures/{id}/reevaluate?pair_exception=true`): it adds a new shadow row (still bounded by every ceiling), requires a reason and is audited.

### Daily ceiling decision (Option C, implemented)
The referrer's 70 % of the ₹25K–1L pool is 525 points, above the 500-a-day ceiling that applies to **low-assurance** points. A closure confirmed by both members (level 2) is low assurance, so it is recorded as `requested 525 / awarded 500 / capped 25 / capped_by DAILY_CEILING` (the ceiling is a **total** for the day, across all low-assurance points). The reward table is unchanged; the reduction is visible on the row. A closure with verified evidence (level 3+) is not low assurance and pays the full 525 (the spec: "a verified closure reward is not split across days"). The cut 25 points are not carried to another day. See the go-live checklist for the comparison with Options A and B.

## 7. Expiry and subscription changes

* Renewal window: 30 days before the term ends to 30 days after (end of grace). Unused points **expire at the end of grace**; **no carry-forward**; points earned after the renewal invoice is paid belong to the **new** cycle (the later-started term wins).
* Every expiry is a shadow `EXPIRY` row (tested: not before the grace ends, once only, idempotent).
* A cancelled/refunded term ends when it was cancelled; later events earn 0 with `NO_ACTIVE_CYCLE`; events after the term earn 0.
* **Plan change (shadow rule, pending management approval): Option A.** Points stay attached to the cycle they were earned in (not deleted, not reset, not moved); the new plan starts a clean cycle with its own frozen ceilings; each cycle's ceilings count only its own points; old points expire at the end of the *old* cycle's grace. No self-service plan change exists in Phase 0 (a second subscription is refused while one is live); today the only way out of a live plan is an admin refund and a new subscription, which is exactly what the test exercises. Transfer (B) and freezing (C) were rejected, see the checklist.

## 8. Reversals

* Pending points on a disputed meeting or cancelled/declined referral → `VOID` rows for both members.
* A verified closure that is disputed/invalidated **within 60 days** → `REVERSAL` rows (negative, new). A restored closure earns again through a *new* lot.
* **Outside the 60-day window nothing is reversed automatically** (official shadow policy, retained; changing it needs approval). A `REVERSAL_NEEDS_REVIEW` flag per lot is queued: `OPEN` is the admin review state. An admin either dismisses it (the points stand) or calls `POST /api/admin/growth-points/flags/{id}/apply-reversal` with a reason, which adds a **new** `REVERSAL` row (`created_by` = that admin, `parent_id` = the original lot) and an audit entry. The original row is never modified; the call is refused if the deal or referral is valid again, if nothing is left to reverse, or if the flag was already reviewed.

## 9. Shadow redemption simulation, member preview, admin analytics

* **Simulation** (`rewards/simulation.py`) is read-only: estimated value (points × ₹0.10), `min(available value, 15 % cap)` as the *hypothetical* discount, and what would apply if pending were released. Output is labelled `SHADOW ONLY` / `HYPOTHETICAL`; `invoice_change_minor` is always 0.
* **Member preview**: own data only, labelled *Shadow · Preview · Not redeemable · Not currently active*, with the line "Today this changes what you pay by ₹0". Off by default (`GROWTH_POINTS_MEMBER_PREVIEW=false` → only "coming soon"). **A product decision is needed before enabling it for members**; until then it is effectively admin-visible only.
* **Admin analytics** keep three things apart: *shadow earning*, *hypothetical redemption* (outstanding, value, liability, maximum potential liability) and *real financial cost* (measured as the sum of invoice discounts and count of reduced invoices; must read ₹0).
  Breakdowns: by event type, capped/voided/reversed, pair-rule reductions, capped-by rule, distribution of cycles by share of ceiling, by plan and by cycle length (normalised per member-month and per year), unit economics (points per referral / meeting / closed deal / ₹1 lakh verified), members (paginated, searchable), ledger (filterable), flags, reconciliation, export.
* **Modelled vs actual** (`GET /economics`): the 400-member model on the approved mix gives expected ₹83,006 and worst case ₹532,800 a year against ₹44,40,000 revenue (1.87 % / 12.0 %); it is checked against the reference script `docs/growth_points_model/economy_v2.py` for the base, 2× activity and all-redeem scenarios. Modelled and actual are always shown side by side, never mixed.

## 10. Fraud and gaming signals

Flag-only review items (deduplicated; a second scan adds nothing): pair concentration, pair frequency (≥3 in 30 days), reciprocal referrals, same prospect across pairs, rapid closure (<24 h), high-value closure, low acceptance rate, repeated same band, one member holding a large share of points, reversals needing review. Thresholds are analysis thresholds, not business rules, and none changes a member's points.

## 11. Financial firewall

Defence in depth, each layer tested:

1. `GROWTH_POINTS_REDEMPTION_ENABLED=true` makes the app refuse to start; `firewall.redeem()` always raises; `POST /redeem` always returns 409 `redemption_disabled` (audited, rate-limited, CSRF-protected).
2. While the reward engine runs, a ContextVar guard plus a SQLAlchemy `before_cursor_execute` listener **refuse any write to `invoices`, `payments`, `subscriptions` or `plans`** (raw SQL, ORM, update/delete/insert). Tested with eight statements and an ORM write.
3. Static scan: no module in `app/rewards` writes a financial table; only the analytics measurement *reads* invoice discounts.
4. The ledger rejects non-shadow rows and a `REDEMPTION` event type at the database.
5. Phase 0's invoice CHECK still forces `discount_minor = 0` and `amount_due = list price`; every invoice in the test run has discount 0; `SUBSCRIPTION_PRICING_CONFIRMED` is still false.
6. The legacy `networking_profiles.growth_points` column is never written and is **not** the source of truth (summed = 0 in every suite).
7. `DELETE /api/admin/customers/{id}` now also refuses accounts with Growth Points history (database FK is `RESTRICT` as well).

## 12. Tests

| Suite | SQLite | PostgreSQL 17 |
|---|---|---|
| `test_phase1.py` | **262/262** | **263/263** (adds the TRUNCATE refusal) |
| `test_phase0.py` (last run before the hardening pass) | 245/245 | 245/245 |
| `test_phase0_hardening.py` | 242/242 | 242/242 |
| `test_plan_terms.py` | 51/51 | 51/51 |
| `test_production.py` | 91/91 | n/a (SQLite-only suite) |

`test_phase1.py` covers: rule constants; flags and kill switch; creation = 0; accepted / contacted / meeting (one-sided, duplicate, dispute, never-accepted); closed business by band and level (including forged client fields); idempotency (5 sequential replays, 8 concurrent hooks, 6 simultaneous events, double PATCH); Pair Assurance (budget, verified exemption, quarter reset, order independence, concentration, reciprocal, admin exception); plan-aware ceilings (3,600 / 6,000 / 12,000 and sub-ceilings, daily, monthly, frequency); repeat business; reversal and restore; append-only (raw SQL and ORM); cycle boundaries and expiry; cancellation; shadow redemption; the firewall; shadow mode off / on + sweep; member preview; admin analytics, export and economics; fraud signals; security (anonymous, member vs admin, CSRF, reason, no write endpoints, audit on every admin write route); reconciliation; model vs reference; rule drift; performance.

Existing Phase 0 assertions that said "no Growth Points tables/code exist" were narrowed (not deleted): they now assert there is **no redemption, voucher, coupon, discount or reward table, no redemption code, no write to the legacy column**, while allowing only the five `growth_point_*` shadow tables and `app/rewards`.

## 13. Performance, reconciliation, migration

* **No per-request ledger recompute** and no N+1: balances are cached (derived, reconcilable); admin pages are fixed-query (a page of 100 members costs the same 5 queries as a page of 5).
* Measured on **PostgreSQL** (statement trace of the hook, `before_cursor_execute`): a referral-accepted reward event (two ledger rows) cost **47 statements cold / ~37 warm** and a request that earned paid **+41** over the same request without shadow mode; after the hardening pass it costs **31 cold / 21 warm**, **+20 to +22 per request**, a replay costs **5** (was 16), a meeting event **25** (was 52). The work runs after the member's commit, off the response path. Preview 9, admin summary 9. Details in the go-live checklist, section "Query cost".
* Indexes on member, cycle, reference, pair/quarter, day/month keys, expiry, status and event type (migration `0010`).
* **Reconciliation**: `SUM(ledger) = cached balance` for every member and no ceiling/budget exceeded, verified after 400 random awards with voids/reversals/expiry/cap pressure over 5 members of mixed plans; a deliberately corrupted cache is detected as drift and repaired from the ledger.
* **Migration `0010`** rehearsed on SQLite and PostgreSQL from empty, 0007, 0008 and 0009 copies (with a member present): older tables unchanged column by column, the five tables created, RLS on, constraints/triggers present; downgrade works while the ledger is empty and is **refused** while it holds rows (override `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1`, export first); upgrade again recreates an empty ledger.

## 14. Business decisions

Status after the pre-shadow hardening pass (nothing here changes a number in the approved reward table):

| # | Topic | Position | Needs |
|---|---|---|---|
| 1 | Daily 500 vs the 525 closure reward | Option C implemented (section 6) | confirm |
| 2 | Plan change mid-cycle | Option A, shadow rule (section 7) | **approval** |
| 3 | Late false deal (after 60 days) | admin review, never automatic (section 8) | confirm |
| 4 | Member preview | **off**; enabling needs management approval after the observation model is validated | **approval** |
| 5 | Who approves a pair exception | any signed-in admin today (reason + audit); no separate role exists | **decision** |
| 6 | Fraud thresholds | analysis defaults (section 10) | **approval** |
| 7 | "Profile completed" | the spec does not define it; implemented as personal profile + business with founder story + an online link + photo | confirm |
| 8 | Complimentary Season 1 term | one 3-month cycle with Connect ceilings | confirm |
| 9 | Five future events | disabled until their features exist | none |

## 15. How to operate

| Task | How |
|---|---|
| Start shadow recording | `GROWTH_POINTS_SHADOW_MODE=true` (backend env), restart. Nothing is recorded while false; turn it on and run the sweep to backfill what was missed (exactly once) |
| Stop | set it to `false`; recorded rows stay |
| Keep redemption off | `GROWTH_POINTS_REDEMPTION_ENABLED` must stay `false` (true = refuse to boot) |
| Member preview | `GROWTH_POINTS_MEMBER_PREVIEW=true` only after a product decision |
| Sweep / expiry | admin "Sweep" button, `POST /api/admin/growth-points/sweep`, or `python -m app.rewards.jobs` from a scheduler (idempotent) |
| Export | `GET /api/admin/growth-points/export?format=csv|json` (no emails, phones, evidence or exact values) |
| Check health | admin "Reconcile"; real-cost tile must read ₹0 |
| Migrate | `python -m app.migrate` (0010 is additive) |

## 16. Gate and next steps

**REAL FINANCIAL EFFECT = ₹0**, measured (invoice discounts = 0, reduced invoices = 0) and enforced by four independent mechanisms.

*Before moving on:* run a **shadow observation period** with real members, review the analytics against the model (modelled vs actual), tune fraud thresholds, and answer the decisions in section 14.
*Conditions for a later Phase 2* (redemption, not started here): management signs off the economics and the section 14 decisions; subscription pricing is confirmed (`SUBSCRIPTION_PRICING_CONFIRMED`); the invoice discount constraint and the firewall are deliberately redesigned and re-tested; the shadow ledger reconciles cleanly over the observation period.

**Known limits of this verification:** the new admin tab and member card were built and linted (`vite build`, `oxlint` – only the existing warning pattern) but not exercised in a browser; the 43-query overhead figure is from SQLite and was not load-tested on PostgreSQL; migrations were rehearsed on local copies, not on staging.

---

## Pre-shadow hardening pass (after the first Phase 1 report)

* **Daily ceiling**: Option C confirmed and tested (`requested 525 / awarded 500 / capped 25`, level 3 pays 525, nothing carried over, total per day).
* **Query cost**: one transaction now locks a member once, resolves their cycle once, and reads every ceiling in a single aggregate query; fraud signals run only when something was newly rewarded. Correctness is unchanged (all Phase 1 tests pass on SQLite and PostgreSQL).
* **Plan change**: Option A as a documented shadow rule, with tests.
* **Late false deal**: explicit `apply-reversal` admin action, new-row-only, tested; no automatic claw-back.
* **Safety invariants**: hash of every invoice, payment, subscription and plan unchanged across earning, sweeping, expiry, scans, reconciliation, preview, a refused redemption and every admin view; every ledger row is shadow; no shadow table can hold cash/transfer/refund/payment columns; no financial module touches the rewards package; route inventory is closed.
* Member preview remains `GROWTH_POINTS_MEMBER_PREVIEW=false`.

## Management decision lock (after the hardening pass)

The business decisions are now locked and recorded in `docs/PHASE_1_SHADOW_GO_LIVE_CHECKLIST.md` section 0. Implementation changes made to match them:
* Pair exceptions are restricted to the **programme owner** (`PROGRAMME_OWNER_EMAILS`, empty = nobody) and write a full record (approver, reason, pair, event, time, original cap, approved amount), readable at `GET /api/admin/growth-points/exceptions`.
* New `GET /api/admin/growth-points/observation` and admin "Observation" tab: the success metrics and modelled-vs-actual comparison for the observation period; aggregates only, no end date.
* Tests added for the owner gate, the exception record, strict one-time profile completion and the observation metrics (`test_phase1.py` 282/282 SQLite, 283/283 PostgreSQL).
* Section 14's table above is superseded by the checklist: all open items there are decided, except those listed as deliberately open.

## Renewal-based plan change (management lock, final)

Plan changes happen only at renewal; old-cycle points stay in their cycle and may be used (hypothetically) against the NEW renewal invoice up to 15 % of the NEW plan's price, FIFO; the new cycle starts with zero transferred points. Built as `app/rewards/renewal.py`, the `growth_point_renewals` table and `SIM_REDEEM` ledger rows (migration 0010 edited in place), the sweep step, admin `renewal-preview` and `renewals`, reconciliation of every record to its ledger rows, and observation metrics 17-20. The earlier "Option A" wording in section 7 is superseded by `PHASE_1_SUBSCRIPTION_RENEWAL_RULE.md`. Also added: the Gate A review pack (`rewards/review.py`, `GET /api/admin/growth-points/review`).
