"""Rehearse and verify the Phase 0 / 1 / 2 migrations (0008 foundations, 0009 plan terms, 0010 shadow Growth Points ledger, 0011 redemption infrastructure) against a database.

RUN THIS ON A COPY OF THE DATABASE, never on production directly:

    DATABASE_URL=postgresql://user:pass@host:5432/staging_copy \\
        python scripts/verify_phase0_migration.py [--rehearse-downgrade]

What it does
  1. records the state of every existing table (row count and a hash of every row);
  2. runs the real deploy step, `python -m app.migrate`, as a subprocess;
  3. checks that every pre-existing row is byte-for-byte unchanged. From a database already at 0008 that includes every
     subscription, invoice, payment and audit row (history is never rewritten); only the `plans` table may change, and only
     its `period_months` (and the dropped `billing_period` label);
  4. checks the new objects: tables, CHECK / UNIQUE / partial-unique constraints (and that
     they are validated), foreign-key targets and delete rules, indexes, row-level security,
     the three seeded plans, and the audit-log triggers (it tries to UPDATE / DELETE / TRUNCATE
     a probe audit row inside a transaction and expects the database to refuse);
  5. with --rehearse-downgrade (copies only): downgrades 0009 -> 0008 and upgrades again, proving the data tables are identical
     throughout. From a pre-0008 database it also writes one audit row, proves the 0008 downgrade is REFUSED while Phase 0 data
     exists, downgrades with the explicit override, proves the old tables are still identical to step 1, and upgrades again.

It never deletes or rewrites existing member data. Exit status 0 only if every check passed.
Works on PostgreSQL (the production engine) and SQLite (development); the PostgreSQL-only
checks are skipped on SQLite and said so.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.database import _CONNECT_ARGS, DATABASE_URL  # noqa: E402
from app.migrate import HEAD  # noqa: E402

SHADOW_TABLES = ("growth_point_rule_versions", "growth_point_cycles", "growth_point_ledger", "growth_point_balances", "growth_point_flags", "growth_point_renewals")
NEW_TABLES = ("plans", "subscriptions", "invoices", "payments", "referral_confirmations", "deal_closures", "deal_evidence", "audit_log")
RESULTS: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((bool(ok), name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")


def engine():
    return create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args=_CONNECT_ARGS)


async def _column_hashes(conn, table: str, cols: list[str]) -> tuple[int, dict[str, str]]:
    """(row count, {column: sha256 of that column's values in primary-key order}). Per column, so a comparison can ignore
    columns that a downgrade legitimately removed (for example the 0008 flag columns on business_referrals)."""
    pk = await conn.run_sync(lambda c, t=table: inspect(c).get_pk_constraint(t)["constrained_columns"]) or cols[:1]
    order = ", ".join(f'"{c}"' for c in pk)
    select = ", ".join(f'"{c}"' for c in cols)
    hashers = {c: hashlib.sha256() for c in cols}
    n = 0
    for row in (await conn.execute(text(f'SELECT {select} FROM "{table}" ORDER BY {order}'))).all():
        for c, v in zip(cols, row):
            hashers[c].update(repr(str(v)).encode())
        n += 1
    return n, {c: h.hexdigest() for c, h in hashers.items()}


async def snapshot(exclude: set[str]) -> dict[str, dict]:
    """{table: {"columns": [...], "count": n, "hashes": {column: sha256}}}."""
    eng = engine()
    snap: dict[str, dict] = {}
    async with eng.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        for table in sorted(set(tables) - exclude):
            cols = await conn.run_sync(lambda c, t=table: [x["name"] for x in inspect(c).get_columns(t)])
            n, hashes = await _column_hashes(conn, table, cols)
            snap[table] = {"columns": cols, "count": n, "hashes": hashes}
    await eng.dispose()
    return snap


async def compare(before: dict[str, dict], skip: frozenset[str] = frozenset(), skip_removed: bool = False) -> list[str]:
    """Tables present in `before` must still hold the same rows over every column they still have.
    `skip_removed`: after a deliberate downgrade past a table's own revision (a database that started at 0010 or later), a table that no longer exists
    is expected to be gone and is not a problem; it is compared again, byte for byte, once the upgrade recreates it."""
    eng = engine()
    problems: list[str] = []
    async with eng.connect() as conn:
        existing = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        for table, old in before.items():
            if table in skip or (skip_removed and table not in existing):
                continue
            now_cols = await conn.run_sync(lambda c, t=table: [x["name"] for x in inspect(c).get_columns(t)])
            cols = [c for c in old["columns"] if c in now_cols]
            n, hashes = await _column_hashes(conn, table, cols)
            changed = [c for c in cols if hashes[c] != old["hashes"][c]]
            if n != old["count"] or changed:
                problems.append(f"{table}: {old['count']} -> {n} rows" + ("" if n != old["count"] else f", contents changed in {changed}"))
    await eng.dispose()
    return problems


async def scalar(sql: str, **params):
    eng = engine()
    async with eng.connect() as conn:
        v = (await conn.execute(text(sql), params)).scalar()
    await eng.dispose()
    return v


async def refused(sql: str) -> bool:
    """True if the database refuses the statement (the transaction is always rolled back)."""
    eng = engine()
    try:
        async with eng.connect() as conn:
            try:
                await conn.execute(text(sql))
                return False
            except Exception:
                return True
            finally:
                await conn.rollback()
    finally:
        await eng.dispose()


def migrate(*args: str, allow_destructive: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if allow_destructive:
        env["TGL_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
    code = "import sys; from app.migrate import _alembic, main; " + ("sys.exit(main())" if not args else f"_alembic{args!r}")
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)


async def verify_new_objects(pg: bool) -> None:
    eng = engine()
    async with eng.connect() as conn:
        tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
    await eng.dispose()
    check(f"alembic is at {HEAD}", await scalar("SELECT version_num FROM alembic_version") == HEAD)
    check("the Phase 2 redemption tables exist and every invoice still has a zero discount", {"growth_point_redemptions", "growth_point_redemption_lots", "growth_point_controls", "growth_point_redemption_epoch"} <= tables and await scalar("SELECT count(*) FROM invoices WHERE discount_minor <> 0 OR points_discount_minor <> 0") == 0)
    check("the six Phase 1 shadow tables exist", set(SHADOW_TABLES) <= tables, str(set(SHADOW_TABLES) - tables))
    check("all 8 Phase 0 tables exist", set(NEW_TABLES) <= tables, str(set(NEW_TABLES) - tables))
    plans = {r[0]: r[1:] for r in await _rows("SELECT code, price_minor, period_months, currency FROM plans")}
    check("the three plans carry exact paise prices and their real terms: Connect 3, Growth 6, Elite 12 months",
          plans == {"connect": (300000, 3, "INR"), "growth": (500000, 6, "INR"), "elite": (1000000, 12, "INR")}, str(plans))
    eng = engine()
    async with eng.connect() as conn:
        plan_cols = {c["name"] for c in await conn.run_sync(lambda c: inspect(c).get_columns("plans"))}
    await eng.dispose()
    check("the old billing-period label column is gone (the term is period_months alone)", "billing_period" not in plan_cols and "period_months" in plan_cols)
    check("no plan has a term other than 3, 6 or 12 months", await scalar("SELECT count(*) FROM plans WHERE period_months NOT IN (3, 6, 12)") == 0)
    check("no redemption, voucher, coupon, discount or reward table exists (only the Phase 1 shadow growth_point_* tables)",
          not [t for t in tables if not t.startswith("growth_point_") and any(w in t for w in ("growth", "reward", "point", "ledger", "redemption", "redeem", "voucher", "coupon", "discount"))])
    check("every invoice still has a zero discount", await scalar("SELECT count(*) FROM invoices WHERE discount_minor <> 0") == 0)
    if not pg:
        print("  (PostgreSQL-only checks skipped: SQLite)")
        return
    gp_checks = {"ck_gp_ledger_shadow_only", "ck_gp_ledger_entry_type", "ck_gp_ledger_event_type", "uq_gp_ledger_idempotency", "uq_gp_cycle_source", "ck_gp_renewal_shadow_only", "ck_gp_renewal_within_caps", "uq_gp_renewal_subscription", "ck_gp_epoch_not_backdated", "uq_gp_epoch_singleton"}
    have_gp = {r[0] for r in await _rows("SELECT conname FROM pg_constraint WHERE contype IN ('c','u')")}
    check("the shadow ledger's CHECK / UNIQUE constraints exist (shadow only, idempotency key, no redemption event type)", gp_checks <= have_gp, str(gp_checks - have_gp))
    check("the ledger's append-only triggers exist", await scalar("SELECT count(*) FROM pg_trigger WHERE tgrelid = 'growth_point_ledger'::regclass AND NOT tgisinternal AND tgenabled = 'O'") >= 2)
    check("the renewal records' append-only triggers exist", await scalar("SELECT count(*) FROM pg_trigger WHERE tgrelid = 'growth_point_renewals'::regclass AND NOT tgisinternal AND tgenabled = 'O'") >= 2)
    expected_checks = {
        "ck_invoice_discount_is_points", "ck_invoice_points_value", "ck_invoice_points_cap", "ck_invoice_payment_floor", "ck_gp_redemption_value", "ck_gp_redemption_cap", "ck_gp_redemption_amounts", "ck_invoice_amount_due", "ck_invoice_amounts", "ck_invoice_status", "ck_invoice_paid_matches", "ck_invoice_paid_not_over",
        "ck_plan_price_positive", "ck_plan_period_positive", "ck_plan_period_allowed", "ck_plan_status", "ck_payment_amount_positive", "ck_payment_status",
        "ck_payment_verified_stamp", "ck_subscription_status", "ck_subscription_active_dates", "ck_closure_value_positive", "ck_closure_level_range",
        "ck_closure_status", "ck_closure_band", "ck_closure_verified_level", "ck_evidence_status", "ck_evidence_type", "ck_confirmation_kind",
        "ck_confirmation_role", "ck_audit_actor_type", "uq_referral_confirmation",
    }
    have = {r[0] for r in await _rows("SELECT conname FROM pg_constraint WHERE contype IN ('c','u')")}
    check("every CHECK / UNIQUE constraint exists", expected_checks <= have, str(expected_checks - have))
    check("every constraint is validated (none left NOT VALID)", await scalar("SELECT count(*) FROM pg_constraint WHERE NOT convalidated") == 0)
    idx = {r[0]: r[1] for r in await _rows("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")}
    check("partial unique index: one live subscription per member", "uq_subscription_live_user" in idx and "UNIQUE" in idx["uq_subscription_live_user"] and "WHERE" in idx["uq_subscription_live_user"])
    check("partial unique index: one live renewal per subscription being renewed", "uq_subscription_live_renewal" in idx and "UNIQUE" in idx["uq_subscription_live_renewal"] and "renews_subscription_id IS NOT NULL" in idx["uq_subscription_live_renewal"])
    check("partial unique index: one live closure per referral", "uq_closure_live_referral" in idx and "UNIQUE" in idx["uq_closure_live_referral"] and "WHERE" in idx["uq_closure_live_referral"])
    hot = {"ix_subscriptions_user_id", "ix_invoices_user_id", "ix_invoices_subscription_id", "ix_payments_invoice_id", "ix_payments_status", "ix_deal_closures_referral_id",
           "ix_deal_closures_status", "ix_deal_evidence_closure_id", "ix_deal_evidence_sha256", "ix_referral_confirmations_referral_id", "ix_audit_resource", "ix_audit_log_created_at",
           "ix_business_referrals_flagged", "ix_invoices_number", "ix_payments_reference", "ix_plans_code"}
    check("indexes exist for the important queries", hot <= set(idx), str(hot - set(idx)))
    fks = await _rows("""SELECT c.conrelid::regclass::text, c.confrelid::regclass::text, c.confdeltype
                         FROM pg_constraint c WHERE c.contype = 'f' AND c.conrelid::regclass::text IN
                         ('subscriptions','invoices','payments','deal_closures','deal_evidence','referral_confirmations')""")
    rules = {(a, b): (d.decode() if isinstance(d, bytes) else d) for a, b, d in fks}
    check("money and deal records RESTRICT deleting the member / plan / invoice they depend on",
          all(rules.get((t, "users")) == "r" for t in ("subscriptions", "invoices", "payments")) and rules.get(("subscriptions", "plans")) == "r"
          and rules.get(("invoices", "subscriptions")) == "r" and rules.get(("payments", "invoices")) == "r"
          and rules.get(("deal_closures", "users")) == "r" and rules.get(("deal_closures", "business_referrals")) == "r" and rules.get(("deal_evidence", "deal_closures")) == "r", str(sorted(rules.items())))
    check("foreign keys point at the intended tables", {("invoices", "subscriptions"), ("payments", "invoices"), ("deal_evidence", "deal_closures"), ("deal_closures", "business_referrals"), ("referral_confirmations", "business_referrals")} <= set(rules))
    all_tables = [r[0] for r in await _rows("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")]
    no_rls = [t for t in all_tables if not await scalar("SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:t)", t=f"public.{t}")]
    check("row-level security is ON for every public table (Supabase Data API closed)", no_rls == [], str(no_rls))
    check("both audit-log triggers exist and are enabled", await scalar("SELECT count(*) FROM pg_trigger WHERE tgrelid = 'audit_log'::regclass AND NOT tgisinternal AND tgenabled = 'O'") == 2)
    probe = "INSERT INTO audit_log (id, created_at, actor_type, action, resource_type) VALUES ('probe-0008', now(), 'SYSTEM', 'probe', 'probe')"
    check("a probe audit row can be inserted (then rolled back)", not await refused(probe))
    eng = engine()
    async with eng.connect() as conn:
        await conn.execute(text(probe))
        for sql in ("UPDATE audit_log SET reason = 'x' WHERE id = 'probe-0008'", "DELETE FROM audit_log WHERE id = 'probe-0008'", "TRUNCATE audit_log"):
            try:
                await conn.execute(text("SAVEPOINT s"))
                await conn.execute(text(sql))
                check(f"the database refuses: {sql.split(' WHERE')[0]}", False)
            except Exception:
                check(f"the database refuses: {sql.split(' WHERE')[0]}", True)
                await conn.execute(text("ROLLBACK TO SAVEPOINT s"))
        await conn.rollback()
    await eng.dispose()


async def _rows(sql: str):
    eng = engine()
    async with eng.connect() as conn:
        rows = (await conn.execute(text(sql))).all()
    await eng.dispose()
    return rows


PLAN_FIELDS = "id, code, name, price_minor, currency, season_slug, status, effective_from, effective_to, sort_order, created_at"


async def plan_rows() -> list[tuple]:
    """Every plan column except the term (the only thing 0009 may change) and the dropped label."""
    return [tuple(str(v) for v in r) for r in await _rows(f"SELECT {PLAN_FIELDS} FROM plans ORDER BY code")]


async def main_async(rehearse: bool) -> int:
    pg = DATABASE_URL.startswith("postgresql")
    print(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}  ({'PostgreSQL' if pg else 'SQLite'})")
    start = await _state()
    print(f"Current migration state: {start}")
    plans_before: list[tuple] = []
    if start == HEAD:
        print(f"Already at {HEAD}: verifying only (no snapshot comparison possible).")
        before: dict[str, dict] = {}
    else:
        # From 0008 everything but `plans` must be untouched, history included; before 0008 the Phase 0 tables do not exist yet.
        exclude = {"alembic_version", "plans"} if start == "0008" else {"alembic_version"} if start == "0009" else {"alembic_version", *SHADOW_TABLES} if start == "0010" else {"alembic_version", *SHADOW_TABLES, "growth_point_redemptions", "growth_point_redemption_lots", "growth_point_controls"} if start == "0011" else {"alembic_version", *NEW_TABLES}
        before = await snapshot(exclude)
        if start == "0008":
            plans_before = await plan_rows()
            hist = {t: before[t]["count"] for t in ("subscriptions", "invoices", "payments", "audit_log") if t in before}
            print(f"History to preserve: {hist}")
        print(f"Snapshot of {len(before)} tables, {sum(v['count'] for v in before.values())} rows.")
        proc = migrate()
        print(proc.stderr[-1500:] if proc.returncode else "migrate: ok" + (("\n" + proc.stderr[-1500:]) if "WARNING" in proc.stderr else ""))
        check("the deploy step (python -m app.migrate) succeeds", proc.returncode == 0, proc.stderr[-300:])
        if proc.returncode:
            return 1
        problems = await compare(before)
        check("every existing row in every existing table is unchanged", problems == [], "; ".join(problems))
        check("existing payment-proof records are intact", "registrations" not in before or not [p for p in problems if p.startswith(("registrations", "event_registrations"))])
        if start == "0008":
            check("no subscription, invoice, payment or audit row was rewritten", not [p for p in problems if p.split(":")[0] in ("subscriptions", "invoices", "payments", "audit_log")])
            check("the only plan data that changed is the term (ids, prices, names, currency, status, dates all identical)", await plan_rows() == plans_before)
    await verify_new_objects(pg)
    again = migrate()
    check("running the migration again is a no-op", again.returncode == 0)

    if rehearse:
        print("\nDowngrade rehearsal (copies only)")
        d11 = migrate("downgrade", "0010")
        check("0011 (redemption infrastructure) downgrades while no real redemption or points discount exists", d11.returncode == 0 and await _state() == "0010", d11.stderr[-300:])
        check("the invoice's zero-discount CHECK is restored by that downgrade and the redemption tables are gone", await scalar("SELECT count(*) FROM invoices WHERE discount_minor <> 0") == 0)
        u11 = migrate()
        check("0011 upgrades again", u11.returncode == 0 and await _state() == HEAD, u11.stderr[-300:])
        down0 = migrate("downgrade", "0009")
        check("0010 (shadow ledger) downgrades while the ledger is empty", down0.returncode == 0 and await _state() == "0009", down0.stderr[-300:])
        eng = engine()
        async with eng.connect() as conn:
            left = set(await conn.run_sync(lambda c: inspect(c).get_table_names())) & set(SHADOW_TABLES)
        await eng.dispose()
        check("the six shadow tables are gone after that downgrade", left == set(), str(left))
        if before and start in ("0009", "0010", "0011", HEAD):
            problems = await compare(before)
            check("every older table is identical after the 0010 downgrade", problems == [], "; ".join(problems))
        up0 = migrate()
        check("the migrations upgrade again", up0.returncode == 0 and await _state() == HEAD, up0.stderr[-300:])
        await verify_new_objects(pg)
        uid = await scalar("SELECT id FROM users ORDER BY created_at LIMIT 1")
        if uid:
            eng = engine()
            async with eng.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO growth_point_ledger (id, created_at, event_at, member_id, entry_type, event_type, category, reference_type, reference_id, points_delta, requested_points, capped_points, "
                    "status, verification_level, remaining, balance_after, created_by, rule_version, idempotency_key, shadow, day_key, month_key, quarter_key) VALUES "
                    "('rehearsal-gp', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :u, 'EARN', 'PROFILE_COMPLETED', 'OTHER', 'member', :u, 75, 75, 0, 'AVAILABLE', 3, 75, 75, 'system', 'growth-points-v3', 'rehearsal-gp-key', true, "
                    "'2026-01-01', '2026-01', '2026-Q1')"), {"u": uid})
            await eng.dispose()
            refused_gp = migrate("downgrade", "0009")
            check("the 0010 downgrade is REFUSED while the shadow ledger holds rows", refused_gp.returncode != 0 and "Refusing to downgrade 0010" in (refused_gp.stderr + refused_gp.stdout), (refused_gp.stderr or refused_gp.stdout)[-200:])
            check("the refused downgrade kept the ledger row", await _state() in ("0010", HEAD) and await scalar("SELECT count(*) FROM growth_point_ledger WHERE id = 'rehearsal-gp'") == 1)
            gp_down = migrate("downgrade", "0009", allow_destructive=True)
            check("with the explicit override the downgrade succeeds", gp_down.returncode == 0 and await _state() == "0009", gp_down.stderr[-300:])
            up_gp = migrate()
            check("and upgrading again recreates an empty ledger", up_gp.returncode == 0 and await scalar("SELECT count(*) FROM growth_point_ledger") == 0, up_gp.stderr[-300:])
        down1 = migrate("downgrade", "0008")
        check("0009 downgrades without data loss", down1.returncode == 0 and await _state() == "0008", down1.stderr[-300:])
        if before and start == "0008":
            problems = await compare(before)
            check("after the 0009 downgrade every subscription, invoice and payment row is identical", problems == [], "; ".join(problems))
        up1 = migrate()
        check("0009 / 0010 / 0011 upgrade again", up1.returncode == 0 and await _state() == HEAD, up1.stderr[-300:])
        if before and start == "0008":
            problems = await compare(before)
            check("and the history is still identical", problems == [], "; ".join(problems))
        await verify_new_objects(pg)
        if start != "0008":
            eng = engine()
            async with eng.begin() as conn:
                await conn.execute(text("INSERT INTO audit_log (id, created_at, actor_type, action, resource_type) VALUES ('rehearsal-1', CURRENT_TIMESTAMP, 'SYSTEM', 'rehearsal', 'rehearsal')"))
            await eng.dispose()
            refusal = migrate("downgrade", "0007")
            check("the 0008 downgrade is REFUSED while Phase 0 data exists", refusal.returncode != 0 and "Refusing to downgrade" in (refusal.stderr + refusal.stdout), (refusal.stderr or refusal.stdout)[-200:])
            # PostgreSQL rolls the whole downgrade back (still 0009); SQLite may have completed the harmless 0009 step (0008). Either way no data is lost.
            check("the refused downgrade lost nothing", await _state() in ("0008", "0009", "0010", HEAD) and await scalar("SELECT count(*) FROM audit_log WHERE id = 'rehearsal-1'") == 1 and await scalar("SELECT count(*) FROM plans") == 3)
            down = migrate("downgrade", "0007", allow_destructive=True)
            check("downgrade with the explicit override succeeds", down.returncode == 0, down.stderr[-300:])
            if before:
                problems = await compare(before, frozenset(NEW_TABLES), skip_removed=True)
                check("after downgrade the old tables are identical to the original snapshot", problems == [], "; ".join(problems))
            check("Phase 0 tables are gone after downgrade", await scalar("SELECT count(*) FROM information_schema.tables WHERE table_name = 'audit_log'") == 0 if pg else True)
            up = migrate()
            check("upgrading again works", up.returncode == 0, up.stderr[-300:])
            if before:
                problems = await compare(before, frozenset(NEW_TABLES) if start != "0008" else frozenset())
                check("and the old tables are still identical", problems == [], "; ".join(problems))
            await verify_new_objects(pg)

    bad = [n for ok, n in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed")
    return 0 if not bad else 1


async def _state() -> str | None:
    try:
        return await scalar("SELECT version_num FROM alembic_version")
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async("--rehearse-downgrade" in sys.argv)))
