# Phase 0 — Implementation and Hardening Report

Scope: the foundations required **before** Growth Points (`GROWTH_POINTS_FINAL_SPEC.md` §9).
How each mechanism works: `PHASE_0_TECHNICAL_REFERENCE.md`. How to prove it on staging: `PHASE_0_STAGING_VERIFICATION.md`.

## Status

**PHASE 0 HARDENING: PASS — safe to migrate to staging and ready for management acceptance.**
It is **not yet cleared for production**: the staging verification (`PHASE_0_STAGING_VERIFICATION.md`) has not been run, and four management decisions (§14) are open.
No Growth Point is awarded, calculated, accumulated, redeemed or converted into a discount anywhere in the codebase (§12).

Acceptance gate (spec §21):

| Criterion | Result |
|---|---|
| PostgreSQL compatibility verified or documented as the remaining gate | **Verified on local PostgreSQL 17** (full suites + migration rehearsals). Supabase staging remains a gate (§3) |
| Migration 0008 safe on the real schema | Verified on a populated copy of the 0007 schema (22,499 rows), on a database created by the pre-Phase-0 code, and on a copy of the dev database. **The production database itself was not available**; staging must repeat it on a copy of production |
| Subscription / invoice / payment verification work | Yes (tests, browser) |
| Meeting confirmation two-party | Yes, idempotent, race-safe on PostgreSQL |
| Deal closure two-party; actual value captured | Yes (exact paise, server-derived band) |
| Evidence secure | Yes (§8) |
| Verification levels stored correctly | Yes (L0–L4, CHECK-constrained; nothing consumes them) |
| Admin referral workflow works | Yes (tests, browser) |
| Audit trail complete | Yes, including the pre-Phase-0 admin writes (§9) |
| IDOR / security / race / boundary tests pass | Yes |
| Existing functionality still passes | Yes (`test_wsgi_bridge` cannot run here: `werkzeug` is not installed, as before) |
| Misleading Growth Points copy corrected | Yes (§11) |
| No Growth Point financial behaviour | Confirmed (§12) |

> **Correction after this report: plan terms (migration 0009).** The plans are **Connect ₹3,000 / 3 months, Growth ₹5,000 / 6 months, Elite ₹10,000 / 12 months**. Where this report says the plans are "3-month" or "SEASON" plans (the seed data, the billing-period column), that was wrong and was corrected by migration `0009` and `DEFAULT_PLANS`; see `PHASE_0_TECHNICAL_REFERENCE.md` §1 and the Growth Points recalculation. "Season" is no longer used as a universal subscription duration. Test counts below predate the correction; the plan-term tests (`test_plan_terms.py`, 51 checks) and the affected Phase 0 suites were re-run after it.

## 1. Architecture (final)

* **Backend** FastAPI + async SQLAlchemy; SQLite for development, PostgreSQL (Supabase) for production; Alembic via `python -m app.migrate` (`HEAD = 0009`).
* **Subscriptions**: `plans` → `subscriptions` + `invoices` + `payments`; manual proof verified by an admin is the only payment method. Access = `ACTIVE` and `expires_at > now`.
* **Referral verification**: two `referral_confirmations` rows make a meeting; a `deal_closures` row holds the recipient-reported, referrer-confirmed **actual** value, its server-derived band and its verification level; `deal_evidence` holds private files.
* **Audit**: append-only `audit_log`, written in the caller's transaction, protected by ORM guard + database triggers.
* **Safety gates**: `app/pricing_gate.py` (financial gate, default closed); thresholds and payment instructions are configuration, empty or awaiting confirmation.
* **Frontends**: member app (React) and admin SPA (React, built into `backend/static/admin`).

## 2. What changed in this hardening pass

Defects found by attacking the Phase 0 build, all fixed and covered by tests:

| # | Finding | Fix |
|---|---|---|
| 1 | **PostgreSQL race**: two members confirming a meeting at the same moment could both succeed yet leave the referral stuck (each transaction missed the other's uncommitted row). SQLite hid it | Row lock (`SELECT … FOR UPDATE`) on the referral for every state change, on subscriptions for every payment action, plus compare-and-set. A mutation test (locks removed) fails on PostgreSQL |
| 2 | `GET /referrals/summary` crashed on PostgreSQL (GROUP BY on a bound-parameter expression); invisible on SQLite | Rewritten as a conditional sum. (Pre-existing code in the unfinished referral work, not Phase 0) |
| 3 | A NUL character in an id or field made PostgreSQL answer **500** | Any database "data exception" now answers 422 |
| 4 | **Migration 0008 did not enable row-level security on the 8 new tables** — on Supabase the public Data API could have exposed invoices, payments and the audit log | `lock_down()` in the migration; verified with Supabase-style `anon`/`authenticated` roles holding default grants (0 grants remain) |
| 5 | Deleting a member account **cascaded away** their subscriptions, invoices, payments and deal records | Admin delete refuses (409); the database refuses too (`ON DELETE RESTRICT`); tested |
| 6 | Rupee amounts were parsed as floating point | `Decimal`, more than 2 decimal places refused (never rounded); screens format paise with integer arithmetic |
| 7 | An admin could *set* `MEETING_DONE`, and the "legacy" path sent a referral to `MEETING_DONE`, fabricating a meeting; a legacy record displayed as "Confirmed by both" and could report a deal | Admin can no longer set `MEETING_DONE`/`BUSINESS_CLOSED`/`REVENUE_GENERATED`; legacy goes **back** to `CONTACTED`; unverified legacy records show as such, are flagged for admins, and cannot report a deal |
| 8 | The audit entry for advancing a meeting recorded the *new* status as "before" | Previous status captured before the bulk update; asserted |
| 9 | Pre-Phase-0 admin writes (registration verify/delete, finale complete/undo, business verification, account delete) left no audit record | All audited (they still take no reason; see §14) |
| 10 | A lapsed `ACTIVE` subscription blocked buying again until the member happened to read their status; cancel and admin-verify were not serialised | `expire_stale()` on read and on purchase; row locks |
| 11 | Repeating a meeting confirmation returned an error | Idempotent: same answer, nothing added |
| 12 | A failed database write after a file upload left an unreachable file | The file is deleted |
| 13 | Verify-payment took no reason | Reason required (the admin UI asks) |
| 14 | No status-domain constraints; an `ACTIVE` subscription could exist without dates; a `PAID` invoice could disagree with its amount | 17 new CHECK constraints (25 on the Phase 0 tables in all) |
| 15 | Downgrade of 0008 would silently drop financial and audit data | Refused while data exists unless `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1` |
| 16 | Deal thresholds hard-coded in code **and in the UI text**; subscription cards said "3-month" and used local fallback prices | Server configuration + `GET /deal-rules`; UI shows only server prices and period |
| 17 | The "Growth Points are earned" copy | §11 |

## 3. PostgreSQL status and migration verification

A throwaway PostgreSQL 17.11 was run locally and every suite was executed against it (§9). Migrations were rehearsed with `backend/scripts/verify_phase0_migration.py`, which also serves as the staging tool:

| Scenario | Checks |
|---|---|
| A. Empty PostgreSQL | 43/43 |
| B. Populated copy of schema 0007 (1,208 members, 906 registrations with proof records, 2,416 referrals, 8,305 notifications; 22,499 rows) | 45/45 — every pre-existing row byte-identical after upgrade, after a downgrade, and after re-upgrading |
| C. Database created by the pre-Phase-0 code with **no migration history** (stamp path) | 45/45 |
| D. Supabase-style roles `anon`/`authenticated` with default grants | 21/21; both roles lose all access to every table |
| E. SQLite: empty / copy of the real dev database in its pre-Phase-0 shape / dev database as-is | 17/17, 19/19, 8/8 |

What the script verifies: existing rows unchanged; tables; constraints exist **and are validated**; partial unique indexes; foreign-key targets and delete rules; indexes for the hot queries; RLS on every table; the three plans; the database refusing `UPDATE`/`DELETE`/`TRUNCATE` on `audit_log`; that a second run is a no-op; that a downgrade is refused while data exists and, with the override, restores the old tables exactly.

PostgreSQL-specific review of every Phase 0 query and migration: CHECK/UNIQUE/partial indexes (PG `WHERE` syntax verified), foreign keys, `timestamptz`, integer/bigint paise, `TEXT` JSON fields, transactions (`FOR UPDATE`, rollback leaves no audit row), triggers (row and statement level, `TRUNCATE` included), enum-like values (CHECKs), cascade (RESTRICT on money/deal rows).

**Not verified (staging must):** Supabase's pooler with row locks, the Data API with the real anon key, the app's actual database role, and the real production data. Procedure: `PHASE_0_STAGING_VERIFICATION.md`.

## 4. Subscription, invoice and payment review

Lifecycle and every state transition are in the technical reference §1. Verified by tests (unpaid, proof submitted, rejected, cancelled, refunded, expired, replayed, raced) that **no state other than a verified payment on an unexpired active subscription grants access**; the client cannot set a price, discount, status, currency, period or verification; one live subscription per member; two admins cannot both verify; refund ends access and cannot be repeated. Billing period is a plan column, never assumed in logic; the only "3" is the seed row (a data decision awaiting confirmation, §14).

**Pricing gate.** `SUBSCRIPTION_PRICING_CONFIRMED=false`. Only `app/pricing_gate.py` may read it (a test fails otherwise); an unparseable value stops the app. Future redemption code could still *forget to call the gate*, so review must require it; the invoice `discount = 0` CHECK is the backstop and must be replaced by a reviewed migration before any discount can exist.

**Expiry.** No background job is needed for safety: access tests `expires_at > now` directly; `expire_stale()` keeps the stored status truthful when members read or buy. Tested with a forced lapse. Decision recorded; revisit only for reporting.

## 5. Meetings

Referral must be accepted; each member confirms only as themselves (role from the session; forged body ids ignored); two rows needed; repeat is idempotent; the advance is one compare-and-set; races produce one advance (8/8 simultaneous pairs on PostgreSQL); either member can dispute; outsiders get 404; no legacy route bypasses it: an AST scan proves only two functions write `MEETING_DONE`/`BUSINESS_CLOSED` and the exact list of 21 referral-changing routes is pinned in a test.

**Legacy records** (advanced by the old one-member flow, no confirmations): shown as unverified, flagged to admins, unable to report a deal; an admin may send one **back** to an earlier stage with a reason so both members confirm properly. It cannot fabricate a verified meeting or reach `BUSINESS_CLOSED`, has no financial consequence and is audited with `legacy_unverified`.

## 6. Deals and money precision

Actual value is the recipient's report, the referrer's confirmed number (anti-stale `expected_value_minor`), stored as exact paise in a `BIGINT`, currency explicit, separate from the creation-time estimate. Client-supplied band, level, status, reporter, currency, reward and timestamps are ignored; another member's identity or confirmation cannot be supplied. No floating point: Decimal in, integer paise stored, integer arithmetic shown. Boundary values through the API: ₹24,999 → `UNDER_25K`; ₹25,000/₹99,999 → `25K_1L`; ₹1,00,000/₹4,99,999 → `1L_5L`; ₹5,00,000/₹9,99,999 → `5L_10L`; ₹10,00,000 → `10L_PLUS`; plus paise edges. Invalid values (0, negative, NaN, infinity, 3 decimals, booleans, lists, ₹100 crore+) are refused and store nothing.

## 7. Thresholds

Evidence from ₹1,00,000, admin approval from ₹5,00,000 and the 24-hour quick-close flag are now **configuration** (`DEAL_*` settings), frozen on each closure when reported, served to the screens by `GET /deal-rules`, and marked **awaiting management confirmation** (`DEAL_THRESHOLDS_CONFIRMED=false`). The defaults are the values in the Growth Points specification, which is itself not yet approved by management. Nothing computes a reward from them.

## 8. Evidence security

Private store; size cap (413); sniffed PNG/JPEG/WEBP/GIF/PDF only — HTML, SVG, PHP, shell, ZIP, ELF, Windows executable, plain text and a hostile filename/declared type are all refused or ignored (tested); UUID keys; participants and admins only; `nosniff`, sandbox CSP, `no-store`; no response contains a key, path or hash; not reachable under any public path; SHA-256 recorded and compared across closures; upload/verify/reject audited; members cannot delete or replace evidence. A PDF can carry active content; it is served sandboxed.

## 9. Tests

| Suite | SQLite | PostgreSQL 17 |
|---|---|---|
| `test_phase0.py` (features) | 245 | 245 |
| `test_phase0_hardening.py` (**new**: races, money, evidence abuse, audit tampering, IDOR matrix, route scans, constraints, expiry, gate, config, perf) | 242 | 245 |
| `test_p0.py` | 357 | 357 |
| `test_security.py` | 83 | 83 |
| `test_production.py` | 91 | 95 |
| `test_legacy_sync.py` | 11 | 11 |
| **Total passed / failed** | **1,029 / 0** | **1,036 / 0** |

Baseline reported before this pass: 772. The increase is +15 in `test_phase0` and +242 new hardening checks (PostgreSQL adds 3 database-level audit checks to the hardening suite and 4 RLS checks to `test_production`).
Also run: migration rehearsals (§3, 8 scenarios, all passing); `python -m compileall` and `import app.main` (the backend has no configured linter); frontend `oxlint` (no errors; only the project's existing `set-state-in-effect` / fast-refresh warnings); `npm run build` including prerender; admin build.
Real-browser smoke (built app + built admin on a throwaway backend): choose plan → invoice → "payment instructions pending" → proof upload → admin *Verify* with reason → member gains access until +3 months; meeting confirm; report ₹1,50,000.50; referrer confirm; evidence upload; admin verifies evidence with reason → closure *Verified*, level 3, full timeline. No failed API call other than the expected pre-login 401.

**Not run:** `test_wsgi_bridge.py` — `werkzeug` is not installed in this environment (unchanged from before; a PythonAnywhere-only path). Not fixed by installing packages. `test_production.py` has one timing-sensitive check on PostgreSQL ("outbox row marked SENT…") that fails intermittently **at the pre-Phase-0 commit as well** (reproduced 1 failure in 4 runs there); the final PostgreSQL run passed 95/95.

**Frontend automated tests:** the project has no browser-test framework (no Playwright/Vitest/Cypress); adding one only for Phase 0 was judged disproportionate. The seven high-risk flows were exercised by hand in a real browser (above). Recommended follow-up if the team wants regression protection: a small Playwright suite for these flows.

## 10. Performance

Queries per request (the same on both engines), measured by the suites and capped by assertions:

| Flow | Queries |
|---|---|
| plan list | 2 |
| subscription creation (subscription + invoice + payment) | 11 |
| payment-proof upload | 12 |
| current subscription | 6 |
| meeting confirmation: first / second (advances) | 11 / 13 |
| deal report / confirmation | 11 / 13 |
| evidence upload | 13 |
| member referral list (20) / detail | 6 / 7 |
| admin referral list (any page size) / detail | 3 / 9 |
| admin subscription list | 3 |

Admin lists are paginated (`page_size ≤ 100`; a page of 100 costs the same queries as a page of 5). No N+1, no repeated queries. Local PostgreSQL latency (loopback, so not representative of Supabase): p50 6–18 ms for every flow above. The only external call in these flows is the optional private-bucket storage write on upload; email goes through the existing outbox, never inline. Minor existing duplication unrelated to Phase 0: the app loads `/networking/connections` and `/auth/session` twice on page load.

## 11. Growth Points copy

Corrected everywhere a member or visitor could read it: referral stage help ("Growth Points are coming soon"), referral empty states, the Subscription plan features ("Growth Points: coming soon"), the Networking overview and member profile cards (always show **0** with "Coming soon. Not being awarded yet", never a stored balance), the locked-page and public module descriptions, the leaderboard and "earned badges" promises. The concept is kept. Stage help also now describes the two-member confirmation.

## 12. Final search: Growth Points / rewards / redemption

Search over the whole repository (excluding `node_modules`, build output, `.venv`, `.git`) for `growth_points`, `Growth Points`, `growth point`, `reward`, `reward_rules`, `reward engine`, `redemption`, `redeem`, `point_value`, `subscription_discount`, plus `discount`, `ledger`, `voucher`, `leaderboard`, `cashback`:

| Location | Purpose | Financial effect? |
|---|---|---|
| `backend/app/models.py` `NetworkingProfile.growth_points` (+ `0001_baseline_schema`) | pre-existing integer column, default 0; **nothing writes it** (a test scans for writes; all sums are 0) | NO |
| `backend/app/schemas.py`, `routers/customer.py:854` | return that column in a response | NO |
| `src/pages/networking/Home.jsx`, `Member.jsx` | display a literal **0** with "Coming soon" | NO |
| `src/lib/referralMeta.js`, `Referrals.jsx`, `Subscription.jsx`, `Locked.jsx`, `Home.jsx`, `components/ModuleModal.jsx` | copy saying Growth Points are *coming soon* / leaderboards *coming soon* | NO |
| `backend/app/pricing_gate.py`, `config.py`, `.env.example` | the closed financial gate (default off), documentation | NO |
| `backend/app/models.py` `Invoice.discount_minor`, `discount_reason`, migration `0008` | discount columns, held at 0 by `ck_invoice_no_discount_phase0` | NO |
| docstrings in `verification.py`, `closures.py`, `admin_referrals.py`, `subscriptions.py`, `0008` | state that nothing awards or applies points | NO |
| `backend/test_*.py`, `scripts/verify_phase0_migration.py` | assert absence (no table, no code, no sums, no discount) | NO |
| `docs/GROWTH_POINTS_*.md`, `docs/PHASE_0_*.md` | specification and these reports | NO |
| `docs/internal/website_architecture/*` (older design documents) | earlier concept text, including a proposed "redemption capped at 20–30%" — **not code** | NO (design only; superseded by the final spec) |
| `docs/P0_IMPLEMENTATION.md` | lists the Growth Points engine as out of scope | NO |

No class, table, route, job or function exists for ledgers, reward rules, a reward engine, awards, redemption, vouchers, expiry, a points dashboard, reward notifications, Growth Point admin controls, a leaderboard, or shadow calculation.
**Confirmed: no Growth Point is awarded, calculated, accumulated, redeemed or converted into a discount.**

## 13. Known limitations

* Not yet run on Supabase staging or on a copy of production (§3).
* The application connects to PostgreSQL as the table owner; an owner can disable the audit triggers. A least-privilege role is recommended and tested to work, but is an operations change not made here.
* Pre-Phase-0 admin writes are audited but take no reason (adding one would change the admin UI).
* Free-text reasons are stored as typed. The in-process rate limiter is per instance.
* `BUSINESS_CLOSED` is set when the referrer confirms (level 2), possibly before evidence review: a reward system must read the closure's `VERIFIED` status and level, never the referral status.
* Not implemented from the specification: GST-ready invoice fields (needs accounting input — invoice amounts are gross), random audit sampling of small closures, event-registration fees as invoices.
* A development database created before this pass (for example `backend/var/tgl.db`) keeps its old table definitions (no new CHECKs or RESTRICT), because `create_all` never alters tables. It is throwaway; recreate it to match.
* No backend linter is configured; no frontend browser tests (§9); `test_wsgi_bridge` cannot run here.
* The `REVENUE_GENERATED` stage and the older "log revenue" action remain as before and are unrelated to deal verification.

## 14. Management decisions still required

1. **Confirm in writing the plan prices and terms: ₹3,000 / 3 months, ₹5,000 / 6 months, ₹10,000 / 12 months**, then set `SUBSCRIPTION_PRICING_CONFIRMED=true` (spec gate G3, needed before any redemption; not needed for Phase 1 shadow mode).
2. **Provide the official subscription payment instructions** (`SUBSCRIPTION_PAYMENT_INSTRUCTIONS`). Until then members see "instructions are pending" and are told not to pay.
3. **Approve or change the deal thresholds** (₹1,00,000 evidence, ₹5,00,000 admin approval, 24-hour flag) and the five value bands; then set `DEAL_THRESHOLDS_CONFIRMED=true`.
4. **Decide how to handle legacy referrals** (admin-by-admin reset to "Prospect contacted", or leave unverified).
5. Whether to run the application as a least-privilege database role to protect the audit log from the application itself.
6. Whether admin actions that predate Phase 0 should also require a reason.
7. GST treatment of subscription invoices; whether event fees become invoices.
8. Account-deletion policy now that members with money or deal records can only be suspended.

## 15. Exact remaining gate

**Phase 0 is accepted when:** `PHASE_0_STAGING_VERIFICATION.md` passes on staging (rehearsal script on a copy of production, the four Supabase-only checks, the five smoke flows including the 5-run race) **and** management has decided §14 items 2 and 3 (and recorded 1, 4–8).

**Next gate: Phase 1 — shadow-mode reward engine.** Not started; it requires management's explicit authorization. Redemption stays prohibited until spec gates G1–G5.

## 16. Files

New: `backend/app/{audit,verification,referral_verification,subscriptions,pricing_gate}.py`, `routers/{closures,admin_referrals,subscriptions}.py`, `schemas_p0.py`, `migrations/versions/0008_phase0_foundations.py`, `migrations/versions/0009_plan_terms.py`, `scripts/verify_phase0_migration.py`, `test_plan_terms.py`, `test_phase0.py`, `test_phase0_hardening.py`, admin `Referrals.jsx`/`Subscriptions.jsx`/`ReasonModal.jsx`, member `ReferralVerification.jsx`, and these three documents.
Nothing is committed (the working tree also contains unrelated, unfinished referral-wizard and connection work).
