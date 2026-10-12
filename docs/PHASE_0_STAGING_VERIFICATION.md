# Phase 0 — Staging Verification Procedure

How to prove migrations `0008` and `0009` (plan terms) and the Phase 0 code are safe **on staging**, before production.

PostgreSQL 17 was run locally for this hardening pass and everything below passed there (see
`PHASE_0_IMPLEMENTATION_REPORT.md` §3). Staging is still a required gate because a local PostgreSQL is
not Supabase: the items marked **Supabase-only** cannot be proven anywhere else.

Never run the rehearsal steps against production. Use a **copy**.

---

## 0. Before you start

* Staging (or a restored copy of production) with the real Supabase `DATABASE_URL`, the app deployed at the previous commit.
* A backup: `pg_dump` of the database, and a note of the Supabase bucket name for payment proofs.
* `backend/.env` for the run has `ENVIRONMENT=production` (as deployed) or any value; the script only needs `DATABASE_URL`.

## 1. Rehearse the migration on a copy (10 minutes)

```bash
cd backend
DATABASE_URL='postgresql://…/staging_copy' python scripts/verify_phase0_migration.py --rehearse-downgrade
```

It must end with `N/N checks passed` and exit status 0. It:

1. hashes every row of every existing table;
2. runs the real deploy step, `python -m app.migrate`;
3. proves every existing row is unchanged (members, referrals, memberships, registrations and **payment-proof records**);
4. checks tables, CHECK/UNIQUE/partial-unique constraints (all validated), foreign-key targets and RESTRICT rules, indexes, RLS on every table, the three plans, and that the database itself refuses `UPDATE`, `DELETE` and `TRUNCATE` on `audit_log`;
5. with `--rehearse-downgrade` (copy only): shows the downgrade is **refused** while Phase 0 data exists, then performs it with the explicit override, confirms the old tables are byte-identical to step 1, and upgrades again.

Without `--rehearse-downgrade` it never downgrades and never drops anything.

## 2. Supabase-only checks (cannot be proven locally)

| Check | How | Expected |
|---|---|---|
| The Data API cannot read the new tables | With the project's **anon** key: `curl "$SUPABASE_URL/rest/v1/audit_log?select=*" -H "apikey: $ANON_KEY"` (and `invoices`, `payments`, `subscriptions`, `deal_closures`, `deal_evidence`) | `401`/`403`/empty, never rows |
| The pooler works with row locks | Run the app against the pooled connection string; confirm a meeting from two accounts at once (below) | both succeed, referral becomes `MEETING_DONE` once |
| The app's database role | `select current_user;` and `\dt+` ownership | the table owner (the migration role). If you later move to a non-owner role, see "Hardening the audit log" below |
| Storage bucket stays private | Request a stored evidence key directly from the bucket without credentials | refused |

## 3. Smoke the flows on staging

With two test accounts (A refers B) and an admin:

1. **Subscription** — a third test account opens Networking, picks a plan, sees the invoice and the "payment instructions pending" notice (until management sets them), uploads a proof. Admin → Subscriptions → *Verify* (reason required). The account gains Networking; the expiry is the plan's term later: **3 months for Connect, 6 for Growth, 12 for Elite** (repeat with one account per plan).
2. **Meeting** — A gives B a referral; B accepts; A and B each press *Confirm we met*. The referral becomes *Meeting held* only after the second.
3. **Deal** — B reports ₹1,50,000.50; A confirms; B uploads an invoice; admin verifies the evidence (reason required). Admin detail shows both confirmations, the value, level 3 and the full timeline.
4. **Race** — press *Confirm we met* from both accounts at the same moment (two browsers, count to three). Repeat 5 times on new referrals. Every one must reach *Meeting held*.
5. **Audit** — in the SQL console as the app role: `UPDATE audit_log SET reason='x'`, `DELETE FROM audit_log`, `TRUNCATE audit_log` must each fail with `audit_log is append-only`.

## 4. Run the suites against staging's engine (optional, on a throwaway database)

```bash
cd backend
TEST_DATABASE_URL='postgresql+asyncpg://…/scratch_db' python test_phase0.py
TEST_DATABASE_URL='postgresql+asyncpg://…/scratch_db' python test_phase0_hardening.py
```

These **drop and recreate the `public` schema of the database you point them at**. Use an empty scratch database, never staging data.

## 5. Go / no-go

Go only if: step 1 passes; every §2 check holds; the §3 flows work, including the 5-run race; no `500` appears in the logs during §3.

## Hardening the audit log (recommended, not yet done)

The triggers stop `UPDATE`/`DELETE`/`TRUNCATE` for everyone, but a database **owner or superuser** can still `ALTER TABLE audit_log DISABLE TRIGGER`. The application connects as the owner on Supabase. If management wants the log protected from an application bug or a leaked app credential, run the app as a separate role that owns nothing and holds `INSERT, SELECT` on `audit_log` (the hardening suite proves a role with only those grants is refused `UPDATE`). That is an operations change, deliberately not made in Phase 0.

## Rollback

* Code: redeploy the previous commit. The new tables are unused by old code; nothing needs to be dropped.
* Schema: `alembic downgrade 0007` is **refused** while Phase 0 tables hold rows. After a backup, and only if losing that data is intended: `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1`.
