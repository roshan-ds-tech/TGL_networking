# Phase 0 — Technical Reference

Companion to `PHASE_0_IMPLEMENTATION_REPORT.md`. How each Phase 0 mechanism works **as implemented**.
Nothing here awards, calculates, stores or redeems Growth Points.

Conventions: money is integer **paise** (₹1 = 100). Timestamps are UTC. "Implementation note" marks a
fact about the code; "Business decision" marks a rule that management owns (see the report's list of
decisions still required). This document never changes a business rule.

> **Corrections to the first version of this document** (found while verifying against the code):
> subscription states are `PENDING / ACTIVE / EXPIRED / CANCELLED` (not `PENDING_PAYMENT`); invoice states are
> `DRAFT / ISSUED / PENDING / PAID / FAILED / CANCELLED / REFUNDED` (there is no `VOID`); a legacy referral is sent
> back to `CONTACTED`, not `MEETING_DONE`; the thresholds are configuration, not constants.

---

## 1. Plan → subscription → invoice → payment → admin verification → access

Tables `plans`, `subscriptions`, `invoices`, `payments`. Code: `app/subscriptions.py`, `app/routers/subscriptions.py`.

```
PLAN (server row: price_minor, currency, period_months, effective dates)
  │  POST /subscriptions {plan_code}   ← the ONLY client input; price/period/currency/status come from the plan row
  ▼
SUBSCRIPTION PENDING  +  INVOICE ISSUED (discount 0)  +  PAYMENT PENDING        (one transaction)
  │  member uploads proof (private file)
  ▼
PAYMENT SUBMITTED · INVOICE PENDING · SUBSCRIPTION PENDING                      ← still NO access
  │            │                                   │
  │  admin verify (reason)             admin reject (reason)           member cancel
  ▼            ▼                                   ▼                         ▼
PAYMENT VERIFIED          PAYMENT FAILED · INVOICE FAILED          SUBSCRIPTION CANCELLED
INVOICE PAID              (member may resubmit a proof)            INVOICE CANCELLED · PAYMENT FAILED
SUBSCRIPTION ACTIVE  ◀── access starts here: starts_at = now, expires_at = now + period_months calendar months
  │ period ends                    │ admin refund (reason)
  ▼                                ▼
SUBSCRIPTION EXPIRED               PAYMENT REFUNDED · INVOICE REFUNDED · SUBSCRIPTION CANCELLED (access ends)
```

* **The plans.** **Connect ₹3,000 / 3 months, Growth ₹5,000 / 6 months, Elite ₹10,000 / 12 months** (paise 300000 / 500000 / 1000000; `period_months` 3 / 6 / 12; `currency = INR`).
  *Implementation note:* the only place these are written down is `DEFAULT_PLANS` in `app/subscriptions.py`; the database holds them in the plan row and each invoice snapshots price and term at purchase.
  Expiry is computed from the plan's `period_months` (`add_calendar_months`, UTC; e.g. 2026-10-01 → 2027-01-01 / 2027-04-01 / 2027-10-01) and the member UI shows what the API returns; no code or screen
  contains a duration. There is no `billing_period` label any more (migration 0009 removed it): the term is `period_months`, constrained to 3, 6 or 12 (`ck_plan_period_allowed`).
  **"Season" is not a subscription duration.** *Business decision:* management has not yet confirmed these prices and terms in writing (see the report).
  *Correction history:* migration 0008 first seeded all three plans as 3-month "SEASON" plans; migration 0009 corrected the plan rows without touching any invoice, payment or subscription.
  Verification refuses an invoice whose term differs from its plan's (409), so a subscription never receives a term the invoice did not state.
* **Who sets what.** The invoice amount is copied from the plan row at purchase. A client cannot send a price, discount, status, currency, period or "verified"
  flag (extra body fields are ignored; there is no member route that verifies or activates anything; the admin routes need an admin session, CSRF and a reason).
* **One live subscription per member**: partial unique index `uq_subscription_live_user` on `PENDING`/`ACTIVE`. A double click or a replay hits the index (409).
* **Access** (`security._active_membership_exists`): an `ACTIVE` subscription with `starts_at` set and `expires_at > now`. `ck_subscription_active_dates` makes an
  `ACTIVE` row without dates impossible. `TGLMembership` is untouched.
* **Expiry — decision: no background job.** Access always tests `expires_at > now`, so a stale `ACTIVE` row grants nothing (tested by forcing a past `expires_at`).
  `subscriptions.expire_stale()` flips lapsed rows to `EXPIRED` (audited) whenever the member reads their subscription or tries to buy, so the stored status is truthful
  and renewal is never blocked. A job would only tidy reports; it adds no safety. Revisit if reporting needs a truthful status for members who never log in.
* **Races.** Every member and admin action takes a row lock on the subscription (`SELECT … FOR UPDATE`) and every status change is also a compare-and-set
  (`UPDATE … WHERE status = expected`). Cancel racing an admin verification ends fully cancelled or fully active, never mixed; two admins verifying the same payment: one wins, one gets 409.
* **Payment instructions.** `SUBSCRIPTION_PAYMENT_INSTRUCTIONS` (plain text, ≤1000 chars). Empty by default. `GET /api/v1/subscriptions/payment-instructions` →
  `{configured, instructions}`. Text containing a placeholder marker (`TODO`, `TBD`, `XXXX`, `example`, `<`…) is treated as *not configured*. When not configured the invoice
  page says the instructions are pending and shows no payment details. No bank or UPI detail exists anywhere in the code (a test scans for them).
  *Business decision:* the official instruction text. (The only QR image in the project is the Season 1 *registration* QR; it is not reused.)

## 2. Invoice details

| Field | Notes |
|---|---|
| `number` | `INV-YYYYMMDD-XXXXXXXX` (random), unique |
| `list_price_minor`, `amount_before_discount_minor`, `discount_minor`, `amount_due_minor`, `amount_paid_minor` | `discount_minor` = **0** (`ck_invoice_no_discount_phase0`); `amount_due = before − discount`; `PAID ⇒ amount_paid = amount_due`; `amount_paid ≤ amount_due` |
| `plan_name`, `period_months`, `currency`, `season_slug` | snapshot of the plan at purchase |
| `payment_reference` (on the payment) | `TGLS-XXXXXXXX`, unique; the member quotes it |
| proof | uploaded through `storage.save_document` (sniffed type, size-capped, UUID key, SHA-256). Replacing a proof deletes the previous file and records `replaced_previous_proof` and the new hash in the audit entry |

Manual proof is the only payment method; no gateway exists or is implied.

## 3. The pricing gate (`SUBSCRIPTION_PRICING_CONFIRMED`)

`app/pricing_gate.py` is the **only** code allowed to read the setting. `require_pricing_confirmed(feature)` raises `PricingNotConfirmed` unless it is `true`.

* Default `false`; an unparseable value stops the app starting (it never reads as true).
* `test_phase0_hardening.py` fails if any other module reads the setting.
* Even with the flag `true`, nothing can discount an invoice: the CHECK `ck_invoice_no_discount_phase0` must be replaced by a reviewed migration.
* A future redemption feature must call `require_pricing_confirmed(...)` as its first line **and** write a reviewed migration; either alone changes nothing.
* *Residual risk:* a developer could write a redemption feature that never calls the gate. The scan only prevents *reading the flag elsewhere*; code review must require the gate call. The CHECK constraint is the backstop that makes a bypass fail loudly.

## 4. Referral verification lifecycle

```
GIVEN → ACCEPTED → CONTACTED ──(both members confirm)──▶ MEETING_DONE ──(referrer confirms a reported value)──▶ BUSINESS_CLOSED → REVENUE_GENERATED
   └→ DECLINED / CANCELLED / CLOSED                         (REVENUE_GENERATED needs a VERIFIED closure)
```

Writers of `MEETING_DONE` / `BUSINESS_CLOSED` (an AST scan test fails if another function writes them):
`closures.confirm_meeting`, `closures.confirm_closure`, `closures.revert_referral_after_closure_ended` (back to `MEETING_DONE`). The member PATCH transition table cannot reach either; the admin
correction list cannot set either (or `REVENUE_GENERATED`). The set of routes that can change a referral is pinned in a test; adding one fails the test until reviewed.

*Implementation note:* `BUSINESS_CLOSED` is set when the referrer confirms the reported value (level 2), which can precede evidence and admin review. A reward system must use
`deal_closures.status = 'VERIFIED'` and `verification_level`, never the referral status.

### Legacy records (compatibility path)

Referrals advanced to `MEETING_DONE`/`BUSINESS_CLOSED`/`REVENUE_GENERATED` by the old one-member flow have no confirmation rows. They are called **legacy-unverified**:

* shown to members as "Recorded before meetings needed both members" (never "Confirmed by both"); `report closure` refuses them;
* flagged `legacy_unverified` in the admin list (filterable) and detail;
* an admin can move one **back** to an earlier stage (typically `CONTACTED`) with a reason; both members then confirm properly. An admin can **never set** `MEETING_DONE`, so this path cannot fabricate a verified meeting, cannot reach `BUSINESS_CLOSED`, and has no financial effect;
* moving a *verified* referral back deletes its confirmations (the deleted rows are preserved inside the audit entry) so the members can confirm again;
* audited as `referral.status_corrected` with `legacy_unverified`, `meeting_verified` and `removed_meeting_confirmations`.

*Why it exists:* production may hold referrals created before Phase 0 whose meeting/closing was asserted by one member. They cannot be verified retroactively, and deleting or silently trusting them would both be wrong.

## 5. Meeting confirmation (two-party)

Table `referral_confirmations`, unique `(referral_id, kind, user_id)`. Routes: `POST /api/v1/referrals/{id}/meeting/confirm | withdraw | dispute`.

* Only the referrer or the recipient (others get 404); only from `ACCEPTED` / `CONTACTED`; the role is derived from the session, never the body.
* **Idempotent:** repeating a confirmation returns the current state (200) and adds no row, audit entry or notification.
* The referral is locked (`FOR UPDATE`) for the whole request. On PostgreSQL this is essential: without it two simultaneous confirmations each insert their own row, neither sees the other's uncommitted row, and the referral never advances (reproduced and fixed; a mutation test shows the suite catches its removal).
* Advance to `MEETING_DONE` is a compare-and-set on status; the audit entry records the true previous status.
* Either member can dispute after confirmation: flags the referral for admin review.

## 6. Deal closure verification

Table `deal_closures` (actual value, separate from the creation-time `value_range` estimate). Routes `GET|POST|PATCH /referrals/{id}/closure`, `/closure/confirm`, `/closure/dispute`, `/closure/cancel`, `GET /deal-rules`.

1. The **recipient** reports the actual value: `actual_value` is a **Decimal** (more than 2 decimal places is refused, never rounded); the server converts to exact paise, derives the band, and freezes `evidence_required` / `admin_approval_required` onto the record.
   The client cannot send a band, level, status, reporter, currency, reward or timestamps (ignored; tested).
2. The **referrer** confirms with `expected_value_minor` (anti-stale: 409 if the value changed). Level becomes 2.
3. Evidence (if required) → admin evidence review → `VERIFIED` (level 3), or admin approval (level 4) where required.

**Bands** (lower bound inclusive): `UNDER_25K`, `25K_1L`, `1L_5L`, `5L_10L`, `10L_PLUS`. Boundaries tested through the API: ₹24,999→`UNDER_25K`; ₹25,000 and ₹99,999→`25K_1L`; ₹1,00,000 and ₹4,99,999→`1L_5L`; ₹5,00,000 and ₹9,99,999→`5L_10L`; ₹10,00,000→`10L_PLUS`; plus `.99` paise variants.

**Thresholds are configuration, awaiting management confirmation** (`DEAL_EVIDENCE_THRESHOLD_INR` default 100000, `DEAL_ADMIN_APPROVAL_THRESHOLD_INR` default 500000, `DEAL_QUICK_CLOSE_HOURS` default 24, `DEAL_THRESHOLDS_CONFIRMED=false`).
They are read when a closure is reported and frozen on that record. The screens read them from `GET /deal-rules`. *Business decision:* the values and whether they are approved.

Verification levels: L0 self-reported · L1 one party · L2 both confirm · L3 evidence verified · L4 admin-approved. Stored in `deal_closures.verification_level` (CHECK 0–4; `VERIFIED ⇒ level ≥ 2`). **Nothing consumes them.**
Closure statuses and transitions: `app/verification.py::CLOSURE_TRANSITIONS`. A `VERIFIED` closure can become `DISPUTED` or `INVALIDATED`; the referral then reverts to `MEETING_DONE`. One live closure per referral (`uq_closure_live_referral`).

## 7. Evidence security

Table `deal_evidence` (types `INVOICE`, `PAYMENT_PROOF`, `OTHER`; max 5 live per closure).

* **Intake** — `storage.save_document`: the real bytes are sniffed (PNG/JPEG/WEBP/GIF/PDF only; HTML, SVG, scripts, executables, archives, plain text are refused 415), size is bounded while reading (413), empty files 400, the stored key is a server UUID with a sniffed extension, SHA-256 is computed over the exact bytes. A client filename or declared type is ignored.
* **Privacy** — stored on the private store (local `uploads/` or the private Supabase bucket), never under a public path; served only by authenticated endpoints (participants; admins) with `nosniff`, `Content-Security-Policy: default-src 'none'; sandbox`, `Cache-Control: private, no-store`. No API returns the storage key, path or hash (tested).
* **Reuse** — the same hash on a different closure flags the referral.
* **Audit** — upload, verify and reject are each audited with actor and reason. Members cannot delete or replace evidence; a "replacement" is a new row. If the database write fails after the file was stored, the file is deleted.
* *Implementation note:* a PDF can contain active content; it is served sandboxed and `nosniff`, and admins should open evidence in the browser's PDF viewer, not an external program.

## 8. Admin verification

`app/routers/admin_referrals.py` (admin session + CSRF on every write; **a written reason on every Phase 0 action**, 422 without one; every action audited).

* `GET /api/admin/referrals` — filters: status, date range, referrer, recipient, closure status, level, band, flagged, legacy; `page_size ≤ 100`; **3 queries** whatever the page size.
* `GET /api/admin/referrals/{id}` — participants, both confirmations, closure, evidence, past closures, timeline from the audit log.
* Actions: evidence verify/reject, closure verify/reject/invalidate/resolve-dispute, flag/unflag, status correction, add note.
* Subscriptions: list/filters/pagination, view proof, payment verify (reason) / reject (reason) / refund (reason).
* `DELETE /api/admin/customers/{id}` refuses (409) an account with a subscription, invoice or closed-business record; the database refuses it too.
* The pre-Phase-0 admin writes (registration verify/delete, business verification, finale complete/undo, account delete) are now audited; they have no reason field in their request (changing them would break the admin UI), so they record actor, target and state only.

## 9. Audit log

Table `audit_log` (append-only). `audit.record()` adds the row to the **caller's session**: it commits or rolls back with the change. Columns: actor type/id/role, action, resource type/id, `before`, `after`, `reason`, `metadata`, `request_id`, `created_at`.

Layers: (1) code only inserts; (2) an ORM guard refuses update/delete; (3) database triggers refuse `UPDATE`/`DELETE` (and `TRUNCATE` on PostgreSQL) even for raw SQL; (4) *recommended, not done:* a least-privilege application role (see `PHASE_0_STAGING_VERIFICATION.md`).
Tested on PostgreSQL: all three statements refused; a role with only `SELECT, INSERT` is refused `UPDATE` by privilege; a rolled-back transaction leaves no audit row; a refused change writes none.
Redaction (`_clean`): keys matching password/secret/token/api key/authorization/cookie/card/otp/csrf/hash are replaced; long strings are truncated. Tested: no password, session cookie, CSRF token or storage key appears anywhere in the table.
*Known limit:* free-text `reason` is stored as typed.

## 10. Database integrity (PostgreSQL and SQLite)

* Status domains are CHECK constraints on every new table; amounts are positive; `discount = 0`; `ACTIVE ⇒ dates`; `PAID ⇒ paid = due`; `VERIFIED closure ⇒ level ≥ 2`; `VERIFIED/REFUNDED payment ⇒ verified_at`.
* Partial unique indexes: `uq_subscription_live_user`, `uq_closure_live_referral`.
* Foreign keys: money and deal rows use `ON DELETE RESTRICT` toward the member, plan, subscription, invoice, referral and closure they depend on. Confirmations cascade with their referral.
* Amounts are `INTEGER` paise (invoices, ≤ ₹2.1 crore) and `BIGINT` paise for deal values (≤ ₹100 crore); `currency` is a column on plan, invoice, payment and closure.
* Timestamps are `timestamptz` on PostgreSQL. JSON-like fields (`before_json`, `metadata_json`) are plain `TEXT`, so no JSON operators or dialect differences are involved.
* Every new table has row-level security on and no policies (the Supabase Data API is closed); migration `0008` calls the same `lock_down` helper as earlier migrations.
* Migration `0008`: re-runnable; its downgrade is **refused** while Phase 0 data exists unless `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1`.
* Migration `0009` (plan terms): sets the three plan terms, drops `plans.billing_period` and its CHECK, adds `ck_plan_period_allowed`. It never touches `invoices`, `payments` or `subscriptions` (history keeps the term it was issued with), reports pending subscriptions invoiced under the old data, and is not destructive; its downgrade restores the column and leaves the corrected terms.

## 11. Security controls (summary)

IDOR (non-participants get 404, tested with a matrix of 12 cross-member actions and malformed ids) · forged ids/roles/amounts ignored · CSRF on every write · replay/double-submit (idempotent confirm, unique indexes, compare-and-set) ·
races (row locks + CAS, tested with threads on PostgreSQL) · stale confirmation (`expected_value_minor`) · input bounds (Decimal, CHECKs) · upload hardening · reasons on admin actions · rate limits on confirm/report/upload/purchase (in-process) ·
PostgreSQL rejects NUL characters; the API answers 422 instead of 500 for any SQLSTATE class 22 error.
