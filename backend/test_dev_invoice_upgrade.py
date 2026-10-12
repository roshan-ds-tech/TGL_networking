"""scripts/upgrade_dev_invoice_checks.py: a local development SQLite database made before Phase 2 gets the Phase 2 invoice rules, losing nothing.

Targeted. Run:  .venv/bin/python test_dev_invoice_upgrade.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
TMP = Path(tempfile.mkdtemp(prefix="tgl-devupgrade-"))
results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail and not ok else ""))


def run(db: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "ENVIRONMENT": "development", **(env_extra or {})}
    return subprocess.run([sys.executable, "scripts/upgrade_dev_invoice_checks.py", "--database-url", f"sqlite+aiosqlite:///{db}", *args], capture_output=True, text=True, cwd=str(HERE), env=env)


def make_old_db(path: Path) -> None:
    """A database as create_all made it before Phase 2: current tables, but invoices carries `CHECK (discount_minor = 0)` instead of the points rules."""
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}", "ENVIRONMENT": "development"}
    subprocess.run([sys.executable, "-c", "import asyncio, app.models; from app.database import Base, engine\n"
                    "async def m():\n    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)\n    await engine.dispose()\nasyncio.run(m())"],
                   check=True, cwd=str(HERE), env=env, capture_output=True)
    con = sqlite3.connect(path, isolation_level=None)
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name = 'invoices'").fetchone()[0]
    new = re.compile(r"CONSTRAINT ck_invoice_discount_is_points.*?CONSTRAINT ck_invoice_payment_floor CHECK \([^)]*\),\s*", re.S)
    old_sql = new.sub("CONSTRAINT ck_invoice_no_discount_phase0 CHECK (discount_minor = 0), ", sql, count=1)
    assert old_sql != sql, "test setup: could not build the old shape"
    old_sql = re.sub(r'CREATE TABLE\s+"?invoices"?\s*\(', "CREATE TABLE invoices_old (", old_sql, count=1)
    extras = [r[0] for r in con.execute("SELECT sql FROM sqlite_master WHERE tbl_name = 'invoices' AND type = 'index' AND sql IS NOT NULL")]
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute(old_sql)
    con.execute("DROP TABLE invoices")
    con.execute("ALTER TABLE invoices_old RENAME TO invoices")
    for e in extras:
        con.execute(e)
    con.close()


def insert_invoice(con: sqlite3.Connection, n: int, **over) -> None:
    row = dict(id=f"inv{n}", number=f"INV-{n}", subscription_id=f"sub{n}", user_id="u1", plan_id="p1", currency="INR", plan_name="Connect", period_months=3, list_price_minor=300000,
               amount_before_discount_minor=300000, discount_minor=0, amount_due_minor=300000, amount_paid_minor=0, status="ISSUED", points_redeemed=0, points_discount_minor=0)
    row.update(over)
    cols = [r[1] for r in con.execute("PRAGMA table_info(invoices)")]
    full = {c: row.get(c) for c in cols}
    for c in cols:
        if full[c] is None and c in ("created_at", "issued_at", "updated_at"):
            full[c] = "2026-01-01 00:00:00"
    con.execute(f"INSERT INTO invoices ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [full[c] for c in cols])


def main() -> int:
    db = TMP / "old.db"
    make_old_db(db)
    con = sqlite3.connect(db, isolation_level=None)
    con.execute("PRAGMA foreign_keys = OFF")
    for n in range(3):
        insert_invoice(con, n)
    before = con.execute("SELECT * FROM invoices ORDER BY id").fetchall()
    try:
        insert_invoice(con, 90, discount_minor=1000, points_redeemed=100, points_discount_minor=1000, amount_due_minor=299000, amount_before_discount_minor=300000)
        old_blocks = False
    except sqlite3.IntegrityError:
        old_blocks = True
    check("setup: the old-shape database refuses ANY discount (this is why the simulation failed with an integrity conflict)", old_blocks)
    fk0 = len(con.execute("PRAGMA foreign_key_check").fetchall())
    con.close()

    dry = run(db, "--dry-run")
    check("DRY RUN: reports the old rule and the row count, changes nothing and writes no backup", dry.returncode == 0 and "old rule found" in dry.stdout and "3 invoice rows" in dry.stdout and not (TMP / "backups").exists())
    ran = run(db)
    check("UPGRADE: succeeds, writes a backup first, and reports every row identical", ran.returncode == 0 and "3 invoice rows identical" in ran.stdout and len(list((TMP / "backups").glob("*.db"))) == 1, ran.stdout + ran.stderr)
    con = sqlite3.connect(db, isolation_level=None)
    con.execute("PRAGMA foreign_keys = OFF")
    check("UPGRADE: the invoices rows are byte-for-byte what they were", con.execute("SELECT * FROM invoices ORDER BY id").fetchall() == before)
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name = 'invoices'").fetchone()[0]
    check("UPGRADE: the old rule is gone and the four Phase 2 rules (plus the amount rules) are present", "ck_invoice_no_discount_phase0" not in sql and all(c in sql for c in ("ck_invoice_discount_is_points", "ck_invoice_points_value", "ck_invoice_points_cap", "ck_invoice_payment_floor", "ck_invoice_amount_due")))
    check("UPGRADE: the indexes on invoices survived", {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'invoices' AND sql IS NOT NULL")} >= {"ix_invoices_number", "ix_invoices_user_id", "ix_invoices_status"})
    insert_invoice(con, 91, discount_minor=1000, points_redeemed=100, points_discount_minor=1000, amount_due_minor=299000)
    con.execute("DELETE FROM invoices WHERE id = 'inv91'")
    bad = {}
    for name, over in (("a discount that is not points", dict(discount_minor=500, points_discount_minor=0, amount_due_minor=299500)),
                       ("points worth the wrong amount", dict(discount_minor=1000, points_redeemed=50, points_discount_minor=1000, amount_due_minor=299000)),
                       ("more than 15 % of the price", dict(discount_minor=50000, points_redeemed=5000, points_discount_minor=50000, amount_due_minor=250000)),
                       ("an amount due that does not add up", dict(discount_minor=1000, points_redeemed=100, points_discount_minor=1000, amount_due_minor=300000))):
        try:
            insert_invoice(con, 100 + len(bad), **over)
            bad[name] = False
        except sqlite3.IntegrityError:
            bad[name] = True
    check("RULES AFTER: the legitimate points discount is accepted; a non-points discount, mis-priced points, a discount over 15 % and inconsistent amounts are all still refused by the database", all(bad.values()), str(bad))
    check("INTEGRITY: integrity_check ok (the fixture's invoices point at no real subscription; the rebuild added no violation of its own)", con.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and len(con.execute("PRAGMA foreign_key_check").fetchall()) == fk0)
    con.close()
    again = run(db)
    check("IDEMPOTENT: a second run does nothing and writes no second backup", again.returncode == 0 and "Nothing to do" in again.stdout and len(list((TMP / "backups").glob("*.db"))) == 1)

    prod = run(db, env_extra={"ENVIRONMENT": "production"})
    check("SAFETY: refuses when ENVIRONMENT is production", prod.returncode == 2 and "production" in prod.stderr)
    pg = subprocess.run([sys.executable, "scripts/upgrade_dev_invoice_checks.py", "--database-url", "postgresql+asyncpg://tgl@localhost:5432/tgl"], capture_output=True, text=True, cwd=str(HERE))
    check("SAFETY: refuses anything that is not a local SQLite file", pg.returncode != 0 and "REFUSED" in (pg.stderr + pg.stdout))

    db2 = TMP / "old_with_discount.db"
    make_old_db(db2)
    con = sqlite3.connect(db2, isolation_level=None)
    con.execute("PRAGMA foreign_keys = OFF")
    insert_invoice(con, 1)
    con.execute("PRAGMA ignore_check_constraints = ON")
    con.execute("UPDATE invoices SET discount_minor = 50, points_discount_minor = 50, points_redeemed = 5, amount_due_minor = 299950 WHERE id = 'inv1'")
    con.close()
    refused = run(db2)
    con = sqlite3.connect(db2)
    still_old = "ck_invoice_no_discount_phase0" in con.execute("SELECT sql FROM sqlite_master WHERE name = 'invoices'").fetchone()[0]
    con.close()
    check("SAFETY: if any invoice already carries a discount, it refuses and changes nothing", refused.returncode == 2 and "discount exists" in refused.stderr and still_old)

    failed = [n for ok, n in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    import shutil
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
