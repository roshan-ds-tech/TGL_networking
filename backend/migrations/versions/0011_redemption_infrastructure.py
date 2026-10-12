"""Growth Points, Phase 2: real redemption infrastructure (built, disabled, approval-gated).

Adds, without activating anything:
  * subscriptions.renews_subscription_id and the indexes that let ONE renewal be raised while the running term is still live;
  * invoices.points_redeemed / points_discount_minor and a stricter replacement for the Phase 0 "discount must be 0" CHECK:
    the only discount that can exist is points at 10 paise each, at most 15 % of the list price, with the amount due never below
    80 % of it. Every existing invoice has discount 0 and stays valid;
  * growth_point_redemptions / growth_point_redemption_lots (append-only: the real redemption record) and growth_point_controls
    (append-only switches: the kill switch).

Nothing here changes a row. The redemption service stays OFF behind GROWTH_POINTS_REDEMPTION_ENABLED, the approval gates and the kill switch.
The downgrade is refused if any real redemption, or any invoice with a points discount, exists.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

from migrations.helpers import lock_down

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TABLES = ["growth_point_redemptions", "growth_point_redemption_lots", "growth_point_controls"]
LIVE_ORDINARY = "status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NULL"
LIVE_RENEWAL = "status IN ('PENDING','ACTIVE') AND renews_subscription_id IS NOT NULL"


def _ts(name: str, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _checks(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_check_constraints(table) if c.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- subscriptions: renewals
    cols = {c["name"] for c in insp.get_columns("subscriptions")}
    if "renews_subscription_id" not in cols:
        with op.batch_alter_table("subscriptions") as batch:
            batch.add_column(sa.Column("renews_subscription_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_subscription_renews", "subscriptions", ["renews_subscription_id"], ["id"], ondelete="RESTRICT")
    idx = {i["name"] for i in sa.inspect(bind).get_indexes("subscriptions")}
    if "uq_subscription_live_user" in idx:
        op.drop_index("uq_subscription_live_user", table_name="subscriptions")
    op.create_index("uq_subscription_live_user", "subscriptions", ["user_id"], unique=True, sqlite_where=sa.text(LIVE_ORDINARY), postgresql_where=sa.text(LIVE_ORDINARY))
    if "uq_subscription_live_renewal" not in idx:
        op.create_index("uq_subscription_live_renewal", "subscriptions", ["renews_subscription_id"], unique=True, sqlite_where=sa.text(LIVE_RENEWAL), postgresql_where=sa.text(LIVE_RENEWAL))

    # --- invoices: the points discount, replacing "discount = 0"
    icols = {c["name"] for c in insp.get_columns("invoices")}
    checks = _checks(insp, "invoices")
    with op.batch_alter_table("invoices") as batch:
        if "points_redeemed" not in icols:
            batch.add_column(sa.Column("points_redeemed", sa.Integer, nullable=False, server_default="0"))
        if "points_discount_minor" not in icols:
            batch.add_column(sa.Column("points_discount_minor", sa.Integer, nullable=False, server_default="0"))
        if "ck_invoice_no_discount_phase0" in checks:
            batch.drop_constraint("ck_invoice_no_discount_phase0", type_="check")
        for name, expr in (("ck_invoice_discount_is_points", "discount_minor = points_discount_minor"), ("ck_invoice_points_value", "points_discount_minor = points_redeemed * 10"),
                           ("ck_invoice_points_cap", "points_discount_minor * 100 <= list_price_minor * 15"), ("ck_invoice_payment_floor", "amount_due_minor * 100 >= list_price_minor * 80")):
            if name not in checks:
                batch.create_check_constraint(name, expr)

    have = set(sa.inspect(bind).get_table_names())
    if "growth_point_redemptions" not in have:
        op.create_table(
            "growth_point_redemptions",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("member_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("entry_type", sa.String(8), nullable=False),
            sa.Column("reverses_id", sa.String(36), sa.ForeignKey("growth_point_redemptions.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("old_cycle_id", sa.String(36), sa.ForeignKey("growth_point_cycles.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("subscription_id", sa.String(36), sa.ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("points", sa.Integer, nullable=False),
            sa.Column("point_value_paise", sa.Integer, nullable=False),
            sa.Column("discount_paise", sa.Integer, nullable=False),
            sa.Column("list_price_minor", sa.Integer, nullable=False),
            sa.Column("amount_due_minor", sa.Integer, nullable=False),
            sa.Column("cap_points", sa.Integer, nullable=False),
            sa.Column("eligible_points", sa.Integer, nullable=False),
            sa.Column("restored_points", sa.Integer, nullable=False, server_default="0"),
            sa.Column("rule_version", sa.String(40), nullable=False),
            sa.Column("created_by", sa.String(40), nullable=False),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("details", sa.Text, nullable=True),
            sa.Column("idempotency_key", sa.String(160), nullable=False),
            sa.UniqueConstraint("idempotency_key", name="uq_gp_redemption_idempotency"),
            sa.CheckConstraint("entry_type IN ('REDEEM', 'REVERSE')", name="ck_gp_redemption_type"),
            sa.CheckConstraint("points > 0 AND point_value_paise > 0 AND discount_paise = points * point_value_paise", name="ck_gp_redemption_value"),
            sa.CheckConstraint("discount_paise * 100 <= list_price_minor * 15", name="ck_gp_redemption_cap"),
            sa.CheckConstraint("points <= cap_points AND points <= eligible_points", name="ck_gp_redemption_within_limits"),
            sa.CheckConstraint("amount_due_minor = list_price_minor - discount_paise AND amount_due_minor * 100 >= list_price_minor * 80", name="ck_gp_redemption_amounts"),
            sa.CheckConstraint("(entry_type = 'REDEEM' AND reverses_id IS NULL AND restored_points = 0) OR (entry_type = 'REVERSE' AND reverses_id IS NOT NULL AND restored_points >= 0 AND restored_points <= points)",
                               name="ck_gp_redemption_reverse_link"),
        )
        for col in ("created_at", "member_id", "old_cycle_id", "subscription_id", "invoice_id"):
            op.create_index(f"ix_growth_point_redemptions_{col}", "growth_point_redemptions", [col])
        op.create_index("uq_gp_redemption_invoice", "growth_point_redemptions", ["invoice_id"], unique=True, sqlite_where=sa.text("entry_type = 'REDEEM'"), postgresql_where=sa.text("entry_type = 'REDEEM'"))
        op.create_index("uq_gp_redemption_reverse", "growth_point_redemptions", ["reverses_id"], unique=True, sqlite_where=sa.text("entry_type = 'REVERSE'"), postgresql_where=sa.text("entry_type = 'REVERSE'"))
    if "growth_point_redemption_lots" not in have:
        op.create_table(
            "growth_point_redemption_lots",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("redemption_id", sa.String(36), sa.ForeignKey("growth_point_redemptions.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("member_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("lot_id", sa.String(36), sa.ForeignKey("growth_point_ledger.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("delta", sa.Integer, nullable=False),
            sa.UniqueConstraint("redemption_id", "lot_id", name="uq_gp_redemption_lot"),
            sa.CheckConstraint("delta <> 0", name="ck_gp_redemption_lot_delta"),
        )
        for col in ("redemption_id", "member_id", "lot_id"):
            op.create_index(f"ix_growth_point_redemption_lots_{col}", "growth_point_redemption_lots", [col])
    if "growth_point_controls" not in have:
        op.create_table(
            "growth_point_controls",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("key", sa.String(40), nullable=False),
            sa.Column("value", sa.String(12), nullable=False),
            sa.Column("actor_id", sa.String(36), nullable=True),
            sa.Column("reason", sa.String(240), nullable=False),
        )
        op.create_index("ix_growth_point_controls_created_at", "growth_point_controls", ["created_at"])
        op.create_index("ix_growth_point_controls_key", "growth_point_controls", ["key"])
    _triggers(bind)
    lock_down(TABLES)


def _triggers(bind) -> None:
    tables = ("growth_point_redemptions", "growth_point_redemption_lots", "growth_point_controls")
    if bind.dialect.name == "sqlite":
        for t in tables:
            for name, op_ in ((f"{t}_no_update", "UPDATE"), (f"{t}_no_delete", "DELETE")):
                op.execute(f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op_} ON {t} BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE OR REPLACE FUNCTION tgl_gp_ledger_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'growth point history is append-only'; END; $$ LANGUAGE plpgsql")
        for t in tables:
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_change ON {t}")
            op.execute(f"CREATE TRIGGER {t}_no_change BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION tgl_gp_ledger_immutable()")
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
            op.execute(f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} FOR EACH STATEMENT EXECUTE FUNCTION tgl_gp_ledger_immutable()")


def downgrade() -> None:
    """Refused while a real redemption or a points discount exists: they are financial records."""
    import os

    bind = op.get_bind()
    insp = sa.inspect(bind)
    held = bind.exec_driver_sql("SELECT COUNT(*) FROM growth_point_redemptions").scalar() if insp.has_table("growth_point_redemptions") else 0
    discounted = bind.exec_driver_sql("SELECT COUNT(*) FROM invoices WHERE points_discount_minor <> 0").scalar() if "points_discount_minor" in {c["name"] for c in insp.get_columns("invoices")} else 0
    if (held or discounted) and os.environ.get("TGL_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(f"Refusing to downgrade 0011: {held} real redemptions and {discounted} invoices with a points discount exist. They are financial records; export them first, "
                           "then set TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1 only if that is really intended.")
    tables = ("growth_point_controls", "growth_point_redemption_lots", "growth_point_redemptions")
    if bind.dialect.name == "sqlite":
        for t in tables:
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_update")
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_delete")
    elif bind.dialect.name == "postgresql":
        for t in tables:
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_change ON {t}")
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
    for t in tables:
        if insp.has_table(t):
            op.drop_table(t)
    checks = {c["name"] for c in insp.get_check_constraints("invoices") if c.get("name")}
    with op.batch_alter_table("invoices") as batch:
        for name in ("ck_invoice_discount_is_points", "ck_invoice_points_value", "ck_invoice_points_cap", "ck_invoice_payment_floor"):
            if name in checks:
                batch.drop_constraint(name, type_="check")
        batch.create_check_constraint("ck_invoice_no_discount_phase0", "discount_minor = 0")
        batch.drop_column("points_discount_minor")
        batch.drop_column("points_redeemed")
    op.drop_index("uq_subscription_live_renewal", table_name="subscriptions")
    op.drop_index("uq_subscription_live_user", table_name="subscriptions")
    op.create_index("uq_subscription_live_user", "subscriptions", ["user_id"], unique=True, sqlite_where=sa.text("status IN ('PENDING','ACTIVE')"), postgresql_where=sa.text("status IN ('PENDING','ACTIVE')"))
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_constraint("fk_subscription_renews", type_="foreignkey")
        batch.drop_column("renews_subscription_id")
