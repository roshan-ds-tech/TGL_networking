# Phase 2: redemption readiness

**PHASE 2 BUILD: TECHNICALLY COMPLETE AND REHEARSED. REDEMPTION: DISABLED. REAL FINANCIAL EFFECT = ₹0.**
**Phase 3 status: BLOCKED** by objective gates that are not met (below). This document makes no accounting, GST or legal claim.

The build began on the user's explicit instruction to continue, **although Gate A had not passed** (there is no real-member observation data: `docs/PHASE_1_SHADOW_REVIEW.md`). That is recorded, not hidden: the engine is built behind gates that keep it closed until Gate A genuinely passes.

## What was built

| Area | Built |
|---|---|
| Real redemption | `app/redemption/service.py`: quote (read-only) and confirm. `redeemable = MIN(eligible old-cycle points, 15 % of the NEW plan's price in points)`, 1 point = 10 paise, oldest lots first, expired and unredeemable-date points never used, nothing added to the new cycle's earning balance. One transaction: renewal subscription + invoice with the points discount line + payment for the exact amount due + redemption record + lot lines + balance + audit |
| Early renewal | `POST /api/v1/renewal/confirm` is the only route that may raise a renewal while the term is live (last 30 days) or up to 30 days after it. The old route still refuses a second subscription (no mid-cycle plan change). Verification starts an early renewal when the old term ends (no overlapping time). Earnings after the renewal is paid belong to the next cycle |
| Invoice | `invoices.points_redeemed`, `points_discount_minor`; DB CHECKs: discount is only points, points are exactly 10 paise each, ≤ 15 % of list price, amount due ≥ 80 % of list price (the combined floor), amount due = list − discount, never negative. The service additionally enforces the points-only 85 % floor. No coupon exists in the product, so "other discount" is 0 |
| Financial ledger | `growth_point_redemptions` (REDEEM / REVERSE, append-only, DB triggers, CHECKs on value, cap, floor, links), `growth_point_redemption_lots` (which lots, append-only), `growth_point_controls` (kill switch history). Earning rows are never edited |
| Refund / cancellation | New REVERSE record; points restored only for lots whose original expiry has not passed; expired points never come back; no cash. Done by the sweep (`jobs.sweep`) so no existing financial router imports this code. A refund still waits for the sweep (hourly in the runbook); reconciliation flags a cancelled renewal that still holds points after an hour |
| Safety gates | In order: flag, every approval recorded, engine released, kill switch, **Gate A**, rollout stage. The app refuses to boot with the flag ON unless all approvals are recorded |
| Kill switch | `POST /api/admin/growth-points/redemption/kill` and `/resume` (programme owner only, reason, audit). Stops NEW redemptions at once, no restart; invoices, history and members' points untouched |
| Rollout | `GROWTH_POINTS_ROLLOUT_STAGE` = `internal` (programme owners) / `cohort` (+ listed emails) / `all`; same backend logic at every stage |
| Eligibility cutoff | **Decided: shadow-period points never carry over.** Enforced by an immutable database row (`growth_point_redemption_epoch`, migration 0012), the redemption service's lot filter, and `GROWTH_POINTS_REDEEMABLE_FROM` (ISO-8601 with an explicit offset, inclusive, must equal the recorded row; empty or mismatched = nothing redeemable). **No cutoff has been approved or set.** Details: `GROWTH_POINTS_DEMO_DATA_AND_ELIGIBILITY.md` |
| Member UX | Renewal panel on the Membership page: current plan and end date, plan choice, eligible points, point value, the 15 % ceiling, points used, discount, points left, amount payable, the required explanation, a confirm step ("You are using X Growth Points for a ₹Y subscription discount"). A labelled PREVIEW when redemption is not open; nothing when the preview is off. History: `GET /api/v1/growth-points/history` (own rows, no flags, no other member) |
| Admin | Finance (real) tab and `GET …/finance`: realized cost kept apart from modelled, shadow and outstanding-potential figures; redemptions by plan and member; kill switch buttons; `GET …/redemptions`, CSV `…/redemptions/export` (invoice fields for professional review) |
| Reconciliation | Ledger + real redemptions = balance; redemption = lot lines = invoice discount; every reversal complete; no expired lot redeemed; no cross-cycle or cross-member lot; mismatches raise HIGH alerts and are **never** auto-repaired |

## Rehearsal (all in `backend/test_phase2.py`, gates opened in-process only; PostgreSQL 17 and SQLite)

Eight transitions with exact amounts (Connect→Connect, Connect→Growth, Growth→Growth, Growth→Elite, Elite→Elite, Elite→Growth, Growth→Connect, Elite→Connect); 0, 100, 1,000, exactly the cap and cap + 1 points; expired points (window closed) and a mixed-expiry member (an old expired cycle is never touched); non-renewal; early renewal (starts at the old term's end, next cycle starts at zero); too early; renewal without points; double click, refresh, replay, a different plan while one is live, six concurrent renewals (one redemption); forged fields, a figure the member did not see, no CSRF, no session, unknown plan; refund then sweep; reversal after the points' expiry restores nothing; cancelled unpaid renewal restores and allows renewing again; kill switch (and that it changes nothing already done); rollout stages; flag off; the DB CHECKs; append-only; audit; the finance and accounting outputs; reconciliation including a deliberately corrupted balance (alert, no silent repair); static isolation (the shadow engine writes no financial table, the redemption service never edits an earning row, no existing financial module imports either package); and a **10,105-operation** simulation over 1,800 members (7,860 awards, 1,545 redemptions, 255 plain renewals, 445 reversals, 510 cancellations) ending with a clean reconciliation.

## Acceptance

| Required | State |
|---|---|
| renewal calculation, 3/6/12-month plans, FIFO, expiry, cap, invoice math, plan upgrade and downgrade at renewal | **passed** (rehearsal) |
| refund/reversal, idempotency, security (forged member, points, invoice, amount, plan; unauthorised kill switch; replay; concurrency), audit, reconciliation | **passed** |
| member UX | **checked in a real browser** (throwaway server and database on its own ports, synthetic data, gates opened in that process only): the renewal panel showed 4,800 eligible points, the Connect cap of 4,500 (₹450), amount payable ₹2,550 and 300 points left, with the required explanation; the confirm step read "You are using 4,500 Growth Points for a ₹450 subscription discount"; confirming created a pending renewal invoice of ₹2,550 with the payment-proof step. The check found one contradiction (the points card said "not active" while a discount was available), now fixed and tested |
| admin finance dashboard, emergency disable | **built and tested at the API level** (the admin shell was browser-checked before the Finance tab was added) |
| no unexplained accounting mismatch | **passed in the rehearsal** (invoice discounts = recorded redemptions to the paisa) |
| accounting / GST treatment of the discount, expired-point and refund treatment, point liability | **EXTERNAL REVIEW PENDING.** The technical outputs exist (finance summary, redemptions CSV with invoice fields); no professional conclusion is claimed |
| redemption feature flag OFF | **yes**; the application refuses to boot with it ON unless every approval is recorded |

## Why Phase 3 is blocked (objective: `python -m app.rewards.gates`)

Gate A not passed (no real-member data); no external approval recorded (management model, accounting/GST, backup, rollback test, member Terms, monitoring owner); migrations 0010 to 0013 (0012 the epoch table, 0013 Phase A community recording) not yet run on staging or production (no credentials here); kill switch and rollback not yet rehearsed on a real environment; member Terms/policy text not present; pilot not approved; the open decision on whether shadow points carry over. None of these is simulated.

**STATUS: PHASE 2 TECHNICALLY COMPLETE; READY FOR PHASE 3 = NO (BLOCKED by the gates above).**

## Community recording and redemption (added with Phase A)

Phase A community recording (`PHASE_A_COMMUNITY_ACTIVITY_RECORDING.md`) and the candidate Community rewards (`GROWTH_POINTS_COMMUNITY_REWARDS_IMPLEMENTATION_SPEC.md`) change **nothing** here. No community activity earns a Growth Point, no ledger event type exists for it, no rule version beyond `growth-points-v3` exists, and no community figure feeds Gate A. Redemption stays disabled, `GROWTH_POINTS_REDEEMABLE_FROM` stays empty, and no epoch is recorded. Even if community rewards are approved later, points earned under any new rule version are redeemable only if their `event_at` is on or after the cutoff management approves in writing. The status above is unchanged: **READY FOR PHASE 3 = NO**.

## Update 2026-10-12: chosen points, in-flight re-check, Emergency Stop & Reset Redemption

Status: implemented and tested locally (SQLite and PostgreSQL 17). **Not deployed to any staging environment; redemption stays disabled; Gate A is unchanged and still blocks real redemption.**

* **The member chooses how many points to use.** `GET /api/v1/renewal/quote?points=N` and `POST /api/v1/renewal/confirm {points: N}`. The server clamps N to `MIN(N, eligible old-cycle points, 15% cap)`; it can only lower the discount. 10 points = ₹1, so 500 points = ₹50. The quote also returns `max_points_usable`. The confirm still requires the figures the member saw (`expected_points`, `expected_discount_minor`) and refuses with `calculation_changed` if anything differs. Renewal panel: a number field (1 to the maximum), "Use the most", and "Remove discount" before confirming.
* **In-flight protection (defect fixed).** `confirm()` checked the gates only before taking the member lock. It now re-checks every gate (flag, approvals, kill switch, Gate A, rollout, cutoff) under the member lock immediately before a redemption row is written. A stop committed after a request passed the first check refuses it, and the whole renewal (subscription, invoice, payment, redemption) is rolled back. A redemption that committed before the stop is left as it is, by design.
* **Emergency Stop & Reset Redemption** (admin dashboard → Growth Points → Finance (real)).
  * `POST /api/admin/growth-points/redemption/kill {reason ≥ 10 chars, confirm: "STOP REDEMPTION"}`. Any signed-in admin (session + admin CSRF), because stopping is the safe direction. The phrase is checked on the server.
  * It appends one `growth_point_controls` row (append-only, database triggers) and an audit entry. It is read from the database on every redemption, so it applies to every instance at once and survives restarts.
  * Pressing it again while stopped is idempotent: no second control row, but the attempt is audited.
  * After committing, the endpoint reads the state back and returns 500 instead of success if it cannot confirm the stop.
  * It deletes and reverses nothing: points, ledgers, redemptions, invoices, payments, subscriptions, the cutoff and the audit log are unchanged (tested by counts before and after).
  * `POST …/redemption/resume {reason, confirm: "RESUME REDEMPTION"}` is a separate action, programme owners only. It opens nothing by itself; every other gate still applies.
  * `GET …/redemption/state` now returns `last_stop` (when, who, why) and the stop/resume `history`.
