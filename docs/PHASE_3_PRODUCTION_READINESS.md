# Phase 3: production readiness

**STATUS: NOT STARTED (BLOCKED). Real redemption is NOT enabled; the Phase 2 engine is built and gated.** REAL FINANCIAL EFFECT = ₹0. Member preview OFF.

Phase 3 is the first phase with real money effect. Its prerequisites are evaluated by `python -m app.rewards.gates` (also `GET /api/admin/growth-points/gates`): the Phase 2 engine must exist, Gate A must have genuinely passed, and the external approvals must be recorded (they are only ever shown as ATTESTED, never verified). `redemption_can_be_enabled` is False while `REDEMPTION_ENGINE_BUILT` is False, whatever else is recorded (tested).

| Required | State |
|---|---|
| shadow period reviewed with genuine data | **not met** (no real data) |
| economic model validated / management approved | **not met** (no approval recorded) |
| accounting, GST and legal review | **external blocker** (not claimed) |
| production migration verified, database backup verified | **external blocker** (no staging or production credentials in this environment) |
| redemption, invoice, financial-invariant tests | **built and passing** (`test_phase2.py`, 103 checks, including a 10,105-operation simulation); a real-environment rehearsal is still required |
| fraud controls, reconciliation | shadow versions built and tested; real-money versions not built |
| monitoring operational, kill switch tested, rollback tested | monitoring partly (logs, exit code, alerts); kill switch built and tested in the rehearsal, **not yet on a real environment**; rollback not rehearsed |
| support/admin runbook | shadow part written (`GROWTH_POINTS_PRODUCTION_RUNBOOK.md`); redemption part pending |
| member documentation, Terms/Policy | management/legal: not present |
| pilot rollout approved | not met |
