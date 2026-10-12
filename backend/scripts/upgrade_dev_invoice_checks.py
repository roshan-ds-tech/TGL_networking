"""Bring a LOCAL DEVELOPMENT SQLite database's `invoices` CHECK constraints up to the Phase 2 shape.

    python scripts/upgrade_dev_invoice_checks.py --database-url sqlite+aiosqlite:///./var/tgl.db [--dry-run]

Why: a development database created before Phase 2 (by create_all, not by Alembic) still carries the Phase 0 rule `CHECK (discount_minor = 0)`.
SQLite can not alter a CHECK in place and `app.database.sync_schema` only adds columns, so the redemption SIMULATION (which builds an invoice with a
points discount inside a transaction it always rolls back) is refused by that old rule. Production and staging are unaffected: Alembic migration 0011
replaces the rule there.

What it does (the documented SQLite "12 step" table rebuild, in one transaction, with foreign keys switched off for the duration):
  1. refuses anything that is not a local SQLite file, or ENVIRONMENT=production;
  2. does nothing if the old rule is not present;
  3. copies the database to var/backups/ first (SQLite online backup);
  4. rebuilds ONLY the invoices table with the four Phase 2 rules instead of the old one (discount = points discount, points are worth 10 paise,
     at most 15 % of the list price, amount due never below 80 %), keeping every row, index and trigger;
  5. verifies row count and a hash of every row are identical before and after, that the rebuild added no foreign-key violation, and integrity_check, and rolls back on any difference.
No other table is touched. The new rules are STRICTER about a discount than before only in allowing the points discount the product defines; every existing
invoice has discount 0 and stays valid.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = re.compile(r"CONSTRAINT\s+ck_invoice_no_discount_phase0\s+CHECK\s*\(\s*discount_minor\s*=\s*0\s*\)\s*,?\s*", re.I)
NEW = ("CONSTRAINT ck_invoice_discount_is_points CHECK (discount_minor = points_discount_minor), "
       "CONSTRAINT ck_invoice_points_value CHECK (points_discount_minor = points_redeemed * 10), "
       "CONSTRAINT ck_invoice_points_cap CHECK (points_discount_minor * 100 <= list_price_minor * 15), "
       "CONSTRAINT ck_invoice_payment_floor CHECK (amount_due_minor * 100 >= list_price_minor * 80), ")


def sqlite_path(url: str) -> Path:
    if not url.lower().startswith("sqlite"):
        raise SystemExit("REFUSED: this tool only upgrades a local SQLite development file.")
    path = url.split(":///", 1)[1].split("?", 1)[0]
    return (ROOT / path).resolve() if not os.path.isabs(path) else Path(path)


def row_hashes(con: sqlite3.Connection, table: str) -> dict[str, str]:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    return {str(r[0]): hashlib.sha256(repr(r).encode()).hexdigest() for r in con.execute(f"SELECT id, {', '.join(cols)} FROM {table}")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./var/tgl.db"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production":
        print("REFUSED: ENVIRONMENT is production.", file=sys.stderr)
        return 2
    db = sqlite_path(args.database_url)
    if not db.is_file():
        print(f"REFUSED: {db} does not exist.", file=sys.stderr)
        return 2
    con = sqlite3.connect(db, isolation_level=None, timeout=30)
    row = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'invoices'").fetchone()
    if row is None or not OLD.search(row[0] or ""):
        print(f"{db.name}: invoices already has the Phase 2 rules (or no invoices table). Nothing to do.")
        return 0
    cols = {r[1] for r in con.execute("PRAGMA table_info(invoices)")}
    if not {"points_redeemed", "points_discount_minor"} <= cols:
        print("REFUSED: the points columns are missing; start the backend once (it adds them) and run this again.", file=sys.stderr)
        return 2
    n_rows = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    if con.execute("SELECT COUNT(*) FROM invoices WHERE discount_minor <> 0 OR points_discount_minor <> 0 OR points_redeemed <> 0").fetchone()[0]:
        print("REFUSED: an invoice with a discount exists; the new rules are not applied automatically to it.", file=sys.stderr)
        return 2
    print(f"{db.name}: old rule found; {n_rows} invoice rows, all with discount 0.")
    if args.dry_run:
        print("dry run: nothing changed.")
        return 0
    backups = db.parent / "backups"
    backups.mkdir(exist_ok=True)
    backup = backups / f"{db.stem}.pre-invoice-checks.{datetime.now():%Y%m%d-%H%M%S}.db"
    dst = sqlite3.connect(backup)
    con.backup(dst)
    dst.close()
    print(f"backup written: {backup}")

    before = row_hashes(con, "invoices")
    fk_before = len(con.execute("PRAGMA foreign_key_check").fetchall())          # a development database may already hold dangling references; the rebuild must not add any
    old_sql = row[0]
    new_sql = OLD.sub(NEW, old_sql, count=1)
    new_sql = re.sub(r'CREATE TABLE\s+"?invoices"?\s*\(', "CREATE TABLE invoices_new (", new_sql, count=1, flags=re.I)
    extras = [r[0] for r in con.execute("SELECT sql FROM sqlite_master WHERE tbl_name = 'invoices' AND type IN ('index', 'trigger') AND sql IS NOT NULL")]
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(new_sql)
        con.execute("INSERT INTO invoices_new SELECT * FROM invoices")
        con.execute("DROP TABLE invoices")
        con.execute("ALTER TABLE invoices_new RENAME TO invoices")
        for sql in extras:
            con.execute(sql)
        after = row_hashes(con, "invoices")
        problems = []
        if after != before:
            problems.append("row contents differ after the rebuild")
        if len(con.execute("PRAGMA foreign_key_check").fetchall()) > fk_before:
            problems.append("the rebuild introduced foreign-key violations")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            problems.append("integrity_check failed")
        if OLD.search(con.execute("SELECT sql FROM sqlite_master WHERE name = 'invoices'").fetchone()[0]):
            problems.append("old rule still present")
        if problems:
            con.execute("ROLLBACK")
            print("ROLLED BACK: " + "; ".join(problems), file=sys.stderr)
            return 1
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")
    print(f"done: {len(after)} invoice rows identical before and after; the four Phase 2 rules are in place; integrity ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
