# Staging handoff: migrations 0010, 0011, 0012, 0013 (Growth Points + Phase A community recording)

For an **authorized operator**. Nothing in this document has been run against staging or production. Every value in `<angle brackets>` must be supplied by the operator; no credential, approval or cutoff is invented here.

**Scope.** Four additive migrations: `0010` shadow ledger tables, `0011` redemption infrastructure (built, disabled), `0012` the eligibility-epoch table (empty), `0013` Phase A community recording (`community_events` append-only, `need_help_offers`, additive columns on `business_needs` and `connections`; see `PHASE_A_COMMUNITY_ACTIVITY_RECORDING.md`). They add tables, columns, indexes and constraints. They change no existing row (0013 seeds one-time `BACKFILL` history events from connections that already exist) and record no cutoff. Redemption stays off. **Community recording awards no points.**

**Legend.** Commands that change data are marked `# WRITES`; commands that destroy data are marked `# DESTRUCTIVE — scratch database only`. Everything else is read-only.

### The operator checklist at a glance (each step is detailed in the sections below)

| # | Step | Section | Evidence to keep |
|---:|---|---|---|
| 1 | Confirm the target environment (database name, host, a second person) | stop conditions, 1 | written confirmation |
| 2 | Record the current revision | 1b | `alembic current` output |
| 3 | Take and verify a backup | 1a | readable `pg_restore --list` |
| 4 | Restore a copy and rehearse | 2 | `N/N checks passed` |
| 5 | Run the migration tests and scripts on scratch databases | 2 | both test outputs |
| 6 | Apply the migration, only after confirmation | 4 | `0013 (head)` |
| 7 | Verify schema and data | 5 | the query outputs |
| 8 | Verify the community routes and the admin report | 5b | HTTP statuses, report text |
| 9 | Verify invoices, payments and subscriptions are unchanged | 6 | `financial baseline unchanged` |
| 10 | Verify redemption is disabled and no cutoff or epoch exists | 6 | zero rows, empty variable |
| 11 | Verify synthetic and backfilled data are excluded | 5b, 6 | report counts |
| 12 | Record the first genuine observation | 7 | date and time of the first genuine event |
| 13 | Name ownership and a review cadence | 7 | named owner, cadence |
| 14 | Collect the evidence and approvals needed for the next stage | 10 | the checklist in section 10 |
| 15 | Know the failure response | 8 | rollback decision tree |

**Stop conditions (do not continue if any is true).** The target is not the intended staging database (check `current_database()` and the host out loud with a second person). You do not hold written authority to change that environment. The rehearsal on a copy has not ended with `N/N checks passed`. You are about to set any of `GROWTH_POINTS_REDEMPTION_ENABLED`, `GROWTH_POINTS_APPROVALS`, `GROWTH_POINTS_REDEEMABLE_FROM`, or to record an epoch: **that is out of scope here.**

---

## 1. Before anything: backups and a baseline

```bash
# 1a. Full logical backup (custom format) and a copy of where it is stored
pg_dump "<STAGING_DATABASE_URL>" -Fc -f staging_pre_0010_$(date +%Y%m%d_%H%M).dump
pg_restore --list staging_pre_0010_*.dump | head          # proves the file is readable

# 1b. The revision the database is at now (write it down; expected at most `0012` when upgrading from the last reviewed state, older if staging lags)
cd backend && DATABASE_URL="<STAGING_DATABASE_URL>" python -m alembic current

# 1c. Financial and community baseline: save this output; it is compared again in section 6
psql "<STAGING_DATABASE_URL>" -At -c "select 'connections', count(*) from connections union all select 'business_needs', count(*) from business_needs;" | tee baseline_community.txt
psql "<STAGING_DATABASE_URL>" -At -c "
select 'invoices', count(*), coalesce(sum(amount_due_minor),0), coalesce(sum(discount_minor),0) from invoices
union all select 'payments', count(*), coalesce(sum(amount_minor),0), 0 from payments
union all select 'subscriptions', count(*), 0, 0 from subscriptions
union all select 'plans', count(*), coalesce(sum(price_minor),0), 0 from plans;" | tee baseline_financial.txt
```

Also note the Supabase Storage bucket names (payment proofs, profile photos). The migrations do not touch storage; the backup of the database does not include it.

## 2. Rehearse on a **copy** (never on staging itself)

Restore the dump from 1a into a scratch database, then:

```bash
cd backend
DATABASE_URL="<SCRATCH_COPY_URL>" python scripts/verify_phase0_migration.py --rehearse-downgrade
```

Required: exit status 0 and `N/N checks passed`. It proves every pre-existing row is byte-identical after `python -m app.migrate`, that the new constraints and triggers exist, that every invoice still has a zero discount, and that the 0011 and 0010 downgrades are refused/allowed as designed.
Then the community migration test, which **builds its own schema and writes test rows**, on a *separate, empty* scratch database (never the restored copy, never staging):

```bash
cd backend
TEST_DATABASE_URL="postgresql+asyncpg://<scratch-user>@<scratch-host>/<EMPTY_SCRATCH_DB>" python test_community_migration.py   # WRITES + DESTRUCTIVE — scratch database only
```

Required: every check passes (22/22 on PostgreSQL). It proves migration 0013 preserves every existing row and column, backfills history once, is idempotent, downgrades cleanly, and **refuses** to downgrade once genuine activity exists. A restored copy of the staging database is the right place for `verify_phase0_migration.py`; it is the *wrong* place for this test.

**Known gap:** the script has no dedicated step for the `0012` downgrade. On the copy only, once, by hand: `python -m alembic downgrade 0011` (must succeed while `growth_point_redemption_epoch` is empty) then `python -m app.migrate` (back to `0012`).

## 3. Environment variables for the migration window

Set on the staging service **before** the new code starts. Everything Growth Points stays at its safe default.

| Variable | Value for this handoff | Why |
|---|---|---|
| `DATABASE_URL` | `<STAGING_DATABASE_URL>` (the pooled string the service already uses) | confirm it is staging, not production |
| `ENVIRONMENT` | unchanged | |
| `GROWTH_POINTS_REDEMPTION_ENABLED` | `false` | the app refuses to boot with `true` unless every approval is recorded |
| `GROWTH_POINTS_APPROVALS` | empty | approvals are written attestations from management; none are recorded here |
| `GROWTH_POINTS_REDEEMABLE_FROM` | **empty** | only a precise, written, management-approved cutoff may ever be set; empty = nothing is redeemable |
| `GROWTH_POINTS_DEMO_CUTOFF` | empty | refused in production; demo-only |
| `GROWTH_POINTS_MEMBER_PREVIEW` | `false` | members must not see points until management decides |
| `GROWTH_POINTS_SHADOW_MODE` | `false` for the migration; `true` only as a separate step (growth-points shadow recording) | recording of Growth Points is a separate decision from the schema. **Community recording (0013) needs no variable and awards nothing** |
| `GROWTH_POINTS_ROLLOUT_STAGE` | `internal` | |
| `PROGRAMME_OWNER_EMAILS` | `<named owner email(s)>` | only these admins can approve pair exceptions, the emergency stop and resume |
| `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE` | **unset** | it is the override for refused downgrades; never set it during a normal migration |
| `SUBSCRIPTION_PRICING_CONFIRMED` | unchanged | the pricing gate is a separate decision |

Never seed the demo members on staging. `scripts/seed_demo_members.py` refuses Supabase storage and non-local databases by design.

## 4. Migration order

1. Announce a short maintenance window. Pause any cron that runs `python -m app.rewards.jobs` (it has nothing to do until shadow mode is on).
2. Deploy the new code **without** starting traffic on it if the platform allows; otherwise deploy and run step 3 before the first request (the deploy step normally runs the migration first, then starts uvicorn).
3. Run once: `cd backend && python -m app.migrate`. It applies `0010`, then `0011`, then `0012`, then `0013`, in that order and no other. If the database is already at `0013` it does one query and exits.
4. Confirm: `python -m alembic current` prints `0013 (head)`. Rebuild both frontends (member `npm run build`, admin `cd admin-dashboard && npm run build`).
5. Start the application. The app does not touch the schema at runtime in production.

If any step fails: **stop**. Do not retry blindly and do not set `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE`. Capture the error, check `alembic current`, and go to section 8.

## 5. Verification commands (read-only)

```bash
curl -fsS https://<staging-host>/api/health                      # {"status":"ok"}
psql "<STAGING_DATABASE_URL>" -At <<'SQL'
select version_num from alembic_version;                                                       -- 0013
select count(*) from information_schema.tables where table_name in
 ('growth_point_rule_versions','growth_point_cycles','growth_point_ledger','growth_point_balances','growth_point_flags','growth_point_renewals',
  'growth_point_redemptions','growth_point_redemption_lots','growth_point_controls','growth_point_redemption_epoch');                         -- 10
select relname, relrowsecurity from pg_class where relname like 'growth_point_%' and relkind='r';                            -- every row: t
select tgrelid::regclass, tgname from pg_trigger where not tgisinternal and tgrelid::regclass::text in
 ('growth_point_ledger','growth_point_renewals','growth_point_redemptions','growth_point_redemption_lots','growth_point_controls','growth_point_redemption_epoch'); -- append-only triggers present
select conname, convalidated from pg_constraint where conrelid='invoices'::regclass and contype='c';                         -- all validated
SQL
```

```bash
psql "<STAGING_DATABASE_URL>" -At <<'SQL'
select count(*) from information_schema.tables where table_name in ('community_events','need_help_offers');                       -- 2
select count(*) from community_events where reason_code = 'BACKFILL';                                                              -- equals the history rows expected from the existing connections (one-time)
select count(*) from community_events where reason_code is distinct from 'BACKFILL';                                               -- 0 until real members act
select tgrelid::regclass, tgname from pg_trigger where not tgisinternal and tgrelid::regclass::text = 'community_events';       -- append-only triggers present
SQL
```

### 5b. Community routes and the admin report (steps 8 and 11)

With an admin session: `GET /api/admin/community/report` returns 200 and, before any real use, says `genuine_events_recorded: 0` and that **no observation has started**; the admin **Community activity** tab shows the same. With a test account the operator owns: send and accept a connection, publish a need (description of at least 80 characters), offer help; each creates exactly one event; `growth_point_ledger` is still unchanged. **Caution:** the report cannot tell an operator's test account from a real member, so these test events **will appear as genuine**. The table is append-only and they cannot be removed. Write down the exact time of the last test event and its count; the observation starts with the first event *after* that time made by a real member, and the report's figures before then must be described as "operator verification activity", not observation. (Never use a `@demo.example.com` account on staging to avoid this: the demo domain is for development and copies only.)

With an admin session (section 9):

* `GET /api/admin/growth-points/status` shows `redemption_enabled: false`, `real_financial_effect_inr: 0`.
* `GET /api/admin/growth-points/gates` shows `redemption_can_be_enabled: false` and Gate A **NOT MET** (expected: Gate A needs real observation data; it must not be weakened).
* `cd backend && python -m app.rewards.gates` prints the same gate list.

## 6. Post-migration financial-safety checks (all must hold)

```bash
psql "<STAGING_DATABASE_URL>" -At -c "
select 'invoices', count(*), coalesce(sum(amount_due_minor),0), coalesce(sum(discount_minor),0) from invoices
union all select 'payments', count(*), coalesce(sum(amount_minor),0), 0 from payments
union all select 'subscriptions', count(*), 0, 0 from subscriptions
union all select 'plans', count(*), coalesce(sum(price_minor),0), 0 from plans;" | diff - baseline_financial.txt && echo "financial baseline unchanged"
psql "<STAGING_DATABASE_URL>" -At -c "select 'connections', count(*) from connections union all select 'business_needs', count(*) from business_needs;" | diff - baseline_community.txt \
  && echo "existing connections and needs unchanged (new needs and connections made after the migration will differ: compare the baseline taken immediately before it)"
psql "<STAGING_DATABASE_URL>" -At <<'SQL'
select 'invoices with any discount or points', count(*) from invoices where discount_minor<>0 or points_discount_minor<>0 or points_redeemed<>0;   -- 0
select 'real redemptions', count(*) from growth_point_redemptions;                                                                              -- 0
select 'redemption lots', count(*) from growth_point_redemption_lots;                                                                           -- 0
select 'epoch recorded', count(*) from growth_point_redemption_epoch;                                                                           -- 0 (no cutoff)
select 'kill-switch rows', count(*) from growth_point_controls;                                                                                 -- 0
select 'ledger rows', count(*) from growth_point_ledger;                                                                                        -- 0 until shadow mode is on
select 'demo members', count(*) from users where email like '%@demo.example.com';                                                               -- 0
select 'ledger rows from community', count(*) from growth_point_ledger where event_type in ('CONNECTION_ACCEPTED','NEED_PUBLISHED','NEED_HELP_CONFIRMED'); -- 0 (these types do not exist)
select code, price_minor, period_months from plans order by price_minor;                                                                        -- connect 300000/3, growth 500000/6, elite 1000000/12
SQL
```

Also confirm in the admin: **Growth Points → Finance (real)** shows "Money actually given ₹0", redemption switch Off, redeemable-from "Not set". A normal member renewal and a normal payment verification each still complete at full price (use a test account the operator owns).

## 7. Observation: when it starts, who owns it, how it is reviewed (steps 12 and 13)

* **Observation starts only when** this release runs in an authorised environment that is receiving **genuine** member activity. Deployment alone does not start it, and nothing that exists today (the development databases, the 30 synthetic demo members, the one-time `BACKFILL` rows, the operator's own test activity) counts.
* **Record the real timestamp** of the first genuine event: `GET /api/admin/community/report` returns `observation.first_event_at`. Write it, with the date you read it, in the sign-off table. Do not estimate it and never back-date it.
* **Never** count synthetic or backfilled events as observation, and **never** state that Gate A is met from this report: the report says what happened, not that a gate passed.
* **Ownership and cadence:** name one person who reads the report (weekly during the first month, then fortnightly) and one who is accountable for the decision at the end. Suggested checks each time: members with activity; connection acceptance and reconnection; needs published, rejected, over the tracked limit; offers versus confirmed help; time to first offer; signals. No action is taken automatically on a signal.
* **Duration:** at least one full calendar quarter before the policy decision (two preferred), as in the proposal.
* Optional, read-only: `cd backend && python scripts/community_candidate_evaluation.py` prints a HYPOTHETICAL replay of that genuine history through the *proposed* rules. It writes nothing. It is analysis for the decision, not an award.

## 7b. Starting Growth Points shadow recording (separate, optional step; needs the go-ahead)

Only after sections 5 and 6 pass and management has said recording may begin: set `GROWTH_POINTS_SHADOW_MODE=true`, restart, run `cd backend && python -m app.rewards.jobs` once (idempotent catch-up), confirm reconciliation is clean, real cost ₹0, and schedule the job hourly. Keep `GROWTH_POINTS_MEMBER_PREVIEW=false` until management decides. Daily owner checks are in `GROWTH_POINTS_PRODUCTION_RUNBOOK.md`.

## 8. Rollback precautions

* **Application rollback is safe at any time**: the new tables and columns are additive and the old code ignores them. Redeploying the previous commit does not require a downgrade.
* **Database downgrade is the last resort** and is protected on purpose: `0012` refuses once an epoch exists; `0011` refuses while a real redemption or a points discount exists; `0010` refuses while the ledger holds rows. Order if it is ever needed: `0013` → `0012` → `0011` → `0010`, one revision at a time (`python -m alembic downgrade 0012`, and so on). `0013` **refuses** once genuine community activity has been recorded.
* **Failure response (step 15).** (1) Migration fails part-way: stop, capture the error, read `alembic current`; if the database is unchanged, fix the cause and rerun once; if not, restore the dump into a new database. (2) A check in sections 5–6 fails: do not enable anything; redeploy the previous commit (safe) and investigate on the copy. (3) Unexpected points, discounts or ledger rows: stop and escalate; do not edit or delete rows. (4) A member reports a duplicate request or a missing connection: the current-state tables work as before; compare with `community_events`, which is append-only.
* **Never** set `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1` without (a) an export (`GET /api/admin/growth-points/export?format=csv`, and `…/redemptions/export` if any exist), (b) a fresh `pg_dump`, and (c) written approval. Those rows are the financial and audit record.
* **Preferred recovery after a bad migration with no new data written**: restore the `staging_pre_0010_*.dump` from section 1 into a new database, point the service at it, redeploy the previous commit.
* **Emergency stop for real redemption** (if it were ever enabled): admin → Growth Points → Finance (real) → Emergency stop (programme owner, reason). It is not needed while redemption is off.

## 9. Admin access

Use an **existing** staging admin account supplied by the operator. If none exists: `cd backend && python create_admin.py --email <admin@…>` (prompts for the password; it is never passed as an argument or printed). Add the programme owner's email to `PROGRAMME_OWNER_EMAILS` and restart. Admin sign-in is at `https://<staging-host>/admin`. Do not share or record passwords in tickets or chat.

## 10. Evidence and approvals for the next stage (step 14), and what is still blocked

Before anyone is asked to approve community rewards: the observation quarter completed with the dates in section 7; the report and the evaluator output attached; the decision register in `GROWTH_POINTS_BUSINESS_POLICY_PROPOSAL.md` (section 16) answered in writing, including the privacy items and the moderation owner; `GROWTH_POINTS_COMMUNITY_REWARDS_IMPLEMENTATION_SPEC.md` reviewed. None of this exists yet.

Still blocked, and deliberately not done:

* No epoch is recorded and `GROWTH_POINTS_REDEEMABLE_FROM` stays empty until management approves a precise cutoff **in writing**; then the programme owner records it once (immutable) and only then is the variable set to the identical instant.
* Real redemption, approvals (`MANAGEMENT_MODEL`, `ACCOUNTING_GST`, `PRODUCTION_BACKUP`, `ROLLBACK_TESTED`, `MEMBER_TERMS`, `MONITORING_OWNER`) and the rollout stages are Phase 3 decisions, not part of this handoff.
* Gate A is unchanged: only genuine members count; the 30 synthetic demo members and their activity are excluded everywhere and are never present on staging.
* Supabase-only checks from `PHASE_0_STAGING_VERIFICATION.md` section 2 (anon key cannot read the new tables; bucket stays private) still need the real staging project.

### Sign-off

| Step | Done by | Date/time | Result |
|---|---|---|---|
| Target confirmed as staging (second person) | | | |
| Backup 1a verified readable | | | |
| Rehearsal on copy `N/N` (and 0012 manual step) | | | |
| `test_community_migration.py` on an empty scratch database: all pass | | | |
| `python -m app.migrate` → `0013 (head)` | | | |
| Community report loads; says no observation yet (before real use) | | | |
| First genuine event timestamp read from the report | | | |
| Report owner and cadence named | | | |
| Section 5 verification | | | |
| Section 6 financial checks (all as expected) | | | |

---

## 11. Local verification record (2026-10-12) — implemented and verified locally; NOT yet run on staging

Status legend: **Verified locally** = run on scratch SQLite and scratch PostgreSQL 17.11 on this date. **Waiting for staging** = nothing below was run against a staging or production system. **Waiting for management** = the candidate policy is DRAFT and unapproved. **Disabled** = redemption.

* **Suites (all exit 0, 0 failed).** SQLite / PostgreSQL checks: test_p0 357/357, test_phase0 245/245, test_phase0_hardening 242/245, test_phase1 372/373, test_phase1_simulation 10/10, test_phase2 104/104, test_plan_terms 51/51, test_production 91/95, test_security 83/83, test_legacy_sync 11/11, test_demo_eligibility 35/35, test_demo_isolation 34/34, test_dev_invoice_upgrade 12/12, test_growth_points_page 18/18, test_community_phase_a 75/75, test_community_migration 21/22, test_candidate_policy_invariants 19/19, test_candidate_evaluator 12/12 (after this session's two added checks), test_wsgi_bridge 18/18 (SQLite only; Werkzeug 3.1.9 installed in an isolated venv).
* **Why the counts differ.** The extra PostgreSQL checks are PostgreSQL-only by design: ledger TRUNCATE refusal (phase1), row-level security (production: 4, community migration: 1), and in phase0_hardening 3 audit-log protections (least-privilege role cannot UPDATE, audit triggers enabled, TRUNCATE refused). Diffed line by line against the logs. One wording difference in test_production (concurrent duplicate submissions) is the same check with a stricter assertion on PostgreSQL. No skips other than the RLS block on SQLite, which prints "skipped".
* **500 responses in the test_community_phase_a log are deliberate** (`simulated failure while recording`): they prove that a failing history write rolls the whole action back.
* **asyncpg `CancelledError` at shutdown** reported earlier did **not** reproduce in any of the 18 PostgreSQL logs this session; no cause is established and it is not suppressed. Treat as unexplained until seen again.
* **Migration.** 0013 applies from empty (the full 0001→0013 chain), from a populated 0012 (pending/accepted/declined/legacy mutual pair connections, legacy needs; every pre-existing row unchanged), is idempotent, downgrades with only BACKFILL history, and refuses once real activity exists. A `pg_dump -Fc` → `pg_restore` copy at 0012 migrated to 0013 and the source stayed at 0012.
* **Shadow evaluator hardened:** the session is now read-only at the database (PostgreSQL `SET TRANSACTION READ ONLY`, SQLite `query_only`); it exits 2 with an explanation on a database without the Phase A tables; it reports the first/last genuine event and whether a full quarter (91 days) is covered, and how many members were priced with the assumed plan. 400,002 events on scratch PostgreSQL: `community.report` ≈ 0.6 s (5 runs, 0.61–0.68), evaluator ≈ 3.8 s, row count unchanged afterwards. These are single-machine timings, not a performance claim.
* **Candidate model reproduced** from the proposal's Appendix A: ₹83,006 (1.87%) / ₹88,677 (2.00%), all-redeem 2.26% / 2.48%, worst case ₹532,800 (12.0%), closure headroom 1,980 / 3,300 / 6,600, ring 940 → 710. The monthly 3,000 limit trimming a 1,890 closure when more than 1,110 other points are held is existing v3 behaviour and is unchanged (decision for management).
* **Frontend.** Lint: 0 errors, 26 warnings (unchanged). Both builds succeed (customer site and admin dashboard). **Not run this session:** browser flows (the browser extension was unavailable), automated accessibility and end-to-end tests (none exist in the repository).
* **Still open:** a staging target (URL, database, branch, operator) has not been named; the 12 management decisions; observation has not started; redemption is off.
