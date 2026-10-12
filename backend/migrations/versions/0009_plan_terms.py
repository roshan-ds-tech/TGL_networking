"""Plan terms: Connect 3 months, Growth 6 months, Elite 12 months.

Migration 0008 seeded all three plans as 3-month "SEASON" plans and its CHECK only allowed that one label. The real
terms are 3 / 6 / 12 months. This migration:

  * sets the term of the three canonical plans (by code) to 3 / 6 / 12 months. A plan row is configuration, not history;
  * removes `plans.billing_period` and its CHECK. The label had one legal value and no logic behind it: the term is
    `period_months`, nothing else;
  * adds CHECK `ck_plan_period_allowed` (period_months IN (3, 6, 12)).

It never touches `invoices`, `payments` or `subscriptions`. Each invoice keeps the term it was issued with (its own
`period_months`), and every subscription keeps its stored `starts_at` / `expires_at`, so history stays exactly as it was
for audit. Subscriptions that are still PENDING on an invoice issued under the old data are only REPORTED in the log:
verification refuses to grant a term the invoice did not state, and an admin decides (cancel and re-issue).

Not destructive: no rows are deleted. The downgrade restores the column and its CHECK and leaves the corrected terms in
place (reverting a financial term silently would be the wrong default).

Revision ID: 0009
Revises: 0008
"""
import logging
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# A point-in-time copy of the canonical terms in app/subscriptions.py::DEFAULT_PLANS. A migration must not change
# behaviour when the application's constants change, so it does not import them; test_plan_terms.py asserts the two agree.
CANONICAL_TERMS = {"connect": 3, "growth": 6, "elite": 12}

_plans = sa.table("plans", sa.column("code", sa.String), sa.column("period_months", sa.Integer), sa.column("updated_at", sa.DateTime(timezone=True)))


def _check_names(insp) -> set[str]:
    return {c["name"] for c in insp.get_check_constraints("plans") if c.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    now = datetime.now(timezone.utc)

    # 1. the terms of the canonical plans (a no-op where they are already right)
    for code, months in CANONICAL_TERMS.items():
        res = bind.execute(sa.update(_plans).where(_plans.c.code == code, _plans.c.period_months != months).values(period_months=months, updated_at=now))
        if res.rowcount:
            log.info("plan %s: term set to %s months", code, months)

    bad = bind.execute(sa.text("SELECT code, period_months FROM plans WHERE period_months NOT IN (3, 6, 12)")).all()
    if bad:
        raise RuntimeError(
            f"Refusing to continue: plans with a term other than 3, 6 or 12 months exist: {[tuple(r) for r in bad]}. "
            "Decide what each should be (and add the term to ck_plan_period_allowed deliberately) before migrating."
        )

    # 2. the label column and its CHECK go; the term CHECK is added
    columns = {c["name"] for c in insp.get_columns("plans")}
    checks = _check_names(insp)
    with op.batch_alter_table("plans") as batch:
        if "ck_plan_billing_period" in checks:
            batch.drop_constraint("ck_plan_billing_period", type_="check")
        if "billing_period" in columns:
            batch.drop_column("billing_period")
        if "ck_plan_period_allowed" not in checks:
            batch.create_check_constraint("ck_plan_period_allowed", "period_months IN (3, 6, 12)")

    # 3. report (never change) what history says
    open_old = bind.execute(sa.text(
        "SELECT s.id, p.code, i.period_months, p.period_months FROM subscriptions s "
        "JOIN invoices i ON i.subscription_id = s.id JOIN plans p ON p.id = s.plan_id "
        "WHERE s.status = 'PENDING' AND i.period_months <> p.period_months"
    )).all()
    if open_old:
        log.warning(
            "%d PENDING subscription(s) hold an invoice issued under the old 3-month data and will be refused at verification "
            "until cancelled and re-issued: %s", len(open_old), [f"{r[0]} ({r[1]}: invoiced {r[2]} months, plan {r[3]})" for r in open_old],
        )
    history = bind.execute(sa.text(
        "SELECT COUNT(*) FROM subscriptions s JOIN invoices i ON i.subscription_id = s.id JOIN plans p ON p.id = s.plan_id "
        "WHERE s.status <> 'PENDING' AND i.period_months <> p.period_months"
    )).scalar()
    if history:
        log.info("%d settled subscription(s) keep the term they were invoiced with (left unchanged, as audit history)", history)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = {c["name"] for c in insp.get_columns("plans")}
    checks = _check_names(insp)
    with op.batch_alter_table("plans") as batch:
        if "ck_plan_period_allowed" in checks:
            batch.drop_constraint("ck_plan_period_allowed", type_="check")
        if "billing_period" not in columns:
            batch.add_column(sa.Column("billing_period", sa.String(16), nullable=False, server_default="SEASON"))
        if "ck_plan_billing_period" not in checks:
            batch.create_check_constraint("ck_plan_billing_period", "billing_period IN ('SEASON')")
