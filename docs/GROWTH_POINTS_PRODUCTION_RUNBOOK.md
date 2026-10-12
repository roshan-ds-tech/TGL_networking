# Growth Points production runbook

Status: **shadow mode only. Real redemption is not built and is disabled.** Sections marked *(Phase 2/3, not built)* are the procedure the redemption phases must complete; they are listed so nobody mistakes them for working controls.
Keep these four things separate everywhere: **MODELLED** (the 400-member model), **ACTUAL SHADOW** (what the shadow ledger recorded), **HYPOTHETICAL** (what members would be able to use at renewal), **REAL FINANCIAL** (what TGL actually gave away: ₹0 until Phase 3).

## Owners (the programme owner role: `PROGRAMME_OWNER_EMAILS`)
Daily reconciliation · fraud-flag queue · late-reversal decisions · pair-exception approval · incident escalation. If the variable is empty nobody can approve a pair exception.

## 1. Normal operation (shadow mode)
* Flags: `GROWTH_POINTS_SHADOW_MODE=true`, `GROWTH_POINTS_REDEMPTION_ENABLED=false` (the app refuses to start with true), `GROWTH_POINTS_MEMBER_PREVIEW=false`.
* Schedule `python -m app.rewards.jobs` hourly (it records new renewals, expires lots, reconciles and raises alerts; it exits non-zero when reconciliation fails so cron or a monitor can alert).
* Daily, the programme owner: admin tab *Growth Points (shadow)*: **Overview** (real financial cost must read ₹0), **Reconcile**, **Review flags**, **Observation**.
* `python -m app.rewards.gates` (or `GET /api/admin/growth-points/gates`) shows which gates are met. It never infers approval.

## 2. Enable / disable shadow processing
Enable: `python -m app.migrate`, set `GROWTH_POINTS_SHADOW_MODE=true`, restart, run the jobs once (idempotent backfill), confirm cost ₹0 and reconciliation clean. Disable: set it `false` and restart: every hook becomes a no-op at once; rows stay; members and payments are unaffected.

## 3. Reconciliation
`GET/POST /api/admin/growth-points/reconcile`, and the jobs run. Checks: ledger sum = cached balance per member; no negative lot; no orphan child row; no cycle, category, daily, monthly or pair budget above its ceiling; every renewal record = its SIM_REDEEM rows and never above 15 % of the new plan. Any finding creates a HIGH `RECONCILIATION_MISMATCH` flag once. **Nothing is self-healed.** The admin POST rebuilds only the derived balance cache (audited with a reason); any other correction is a separate, written, audited act.

## 4. Fraud and review queue
Flags are signals; **nothing is punished or reduced automatically**. For each OPEN flag: inspect, then Reviewed or Dismissed with a reason (audited). Kinds: pair concentration/frequency/volume, reciprocal referrals, same prospect across pairs, rapid closure, high-value closure, concentration, repeatedly capped, late-reversal review, renewal refunded / after expiry, reconciliation mismatch.

## 5. Late false deal (after 60 days) and reversals
Within 60 days the engine reverses automatically (new rows). After 60 days it raises an OPEN `REVERSAL_NEEDS_REVIEW` flag. An admin either dismisses it or calls *Reverse points* (`POST …/flags/{id}/apply-reversal`, reason required): a **new** REVERSAL row, original untouched, audited. Refused if the deal is valid again.

## 6. Pair exceptions
Programme owner only; reason required; the audit entry `growth_points.pair_exception` records approver, reason, pair, event, time, original cap and approved amount (`GET /api/admin/growth-points/exceptions`).

## 7. Incident response
1. Anything that looks like real money moved, a failing reconciliation, a spike in points or repeated `tgl.rewards` errors: **disable shadow processing** (section 2). 2. Record what you saw (screenshots, `GET …/reconcile`, `GET …/export`). 3. Do not edit data. 4. Escalate to management. 5. Resume only after the cause is explained and written down.

## 8. Database failure, rollback
Hooks run after the member's request commits and never fail it; a failed hook is logged and re-driven by the next jobs run. Restore from backup, run `python -m app.migrate`, run the jobs (idempotent). Removing the feature entirely: export first; the 0010 downgrade is refused while the ledger holds rows unless `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1`.

## 9. Monitoring (what exists)
`tgl.rewards` log (errors), the jobs exit code, reconciliation alerts, the real-cost tile, `GET …/gates`. There is no paging system; someone must watch these daily. Not built: alerting on query latency or lock contention (see the performance numbers in the Phase 1 checklist for the baseline).

## 10. Redemption: enable, disable, kill switch, refunds, discrepancies *(built in Phase 2; DISABLED; Phase 3 enables it only through the gates)*
**Enable (Phase 3 only, never before every gate is met):** `python -m app.migrate` (0011); record every approval in `GROWTH_POINTS_APPROVALS`; record the officially approved eligibility cutoff once with `POST /api/admin/growth-points/redemption/epoch` (programme owner; written management approval of the exact instant first; it can never be changed) and set `GROWTH_POINTS_REDEEMABLE_FROM` to the same instant (ISO-8601 with offset). Shadow-period points never become redeemable; `GROWTH_POINTS_ROLLOUT_STAGE=internal`; set `GROWTH_POINTS_REDEMPTION_ENABLED=true` and restart (the app refuses to boot otherwise); `python -m app.rewards.gates` must show Gate A met. Test with a programme-owner account, then `cohort` (plus `GROWTH_POINTS_ROLLOUT_EMAILS`), then `all`, checking reconciliation and the Finance tab after each stage.
**Emergency stop (no restart):** admin tab Growth Points → Finance (real) → *Emergency stop* (`POST /api/admin/growth-points/redemption/kill`, programme owner, reason). NEW redemptions fail safely; existing invoices, redemptions, history and members' points stay as they are; a plain renewal still works at full price. *Resume* lifts it. Permanent disable: set the flag false and restart.
**Refund or cancelled renewal:** the sweep (`python -m app.rewards.jobs`, hourly) adds a REVERSE record per refunded or cancelled renewal; points come back only up to each lot's original expiry, never after it, never as cash. Reconciliation raises an alert if one is still unreversed after an hour. Do not edit rows by hand: every row is append-only.
**Invoice, payment or point discrepancy:** reconciliation (admin button or the hourly job) names it (redemption vs lot lines vs invoice discount vs balance). Do not repair silently: engage the kill switch if money is affected, record what you found, and correct only by an audited, explained, append-only act.
**Accounting review:** `GET /api/admin/growth-points/redemptions/export` (CSV with invoice fields) and the Finance tab are the technical outputs for the professional reviewer.
