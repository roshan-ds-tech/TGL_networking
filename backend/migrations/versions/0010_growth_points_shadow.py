"""Growth Points, Phase 1: the SHADOW ledger and its supporting tables.

Adds five tables and nothing else:

  growth_point_rule_versions   the exact parameters of each rule version, written once
  growth_point_cycles          a member's subscription cycle (actual paid term) with its ceilings frozen
  growth_point_ledger          the append-only shadow ledger (UPDATE / DELETE / TRUNCATE refused by trigger)
  growth_point_balances        a derived cache of each member's shadow total (also the per-member row lock)
  growth_point_flags           fraud / gaming review items

None of them touches an invoice, a payment, a price or a subscription, and no existing table or row is changed. The ledger's
CHECK constraints make a non-shadow row or a REDEMPTION row impossible. Row-level security is on for every new table.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

from migrations.helpers import lock_down

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLES = ["growth_point_rule_versions", "growth_point_cycles", "growth_point_ledger", "growth_point_balances", "growth_point_flags", "growth_point_renewals"]
EVENT_TYPES = (
    "REFERRAL_ACCEPTED", "PROSPECT_CONTACTED", "MEETING_COMPLETED", "BUSINESS_CLOSED", "REPEAT_BUSINESS", "PROFILE_COMPLETED",
    "EVENT_ATTENDED", "SUCCESSFUL_INTRODUCTION", "NEED_RESOLVED", "MENTORING_SESSION", "MEMBER_INVITED",
)


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _ts(name: str, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    have = set(insp.get_table_names())

    if "growth_point_rule_versions" not in have:
        op.create_table(
            "growth_point_rule_versions",
            sa.Column("version", sa.String(40), primary_key=True),
            sa.Column("parameters_json", sa.Text, nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            _ts("created_at"),
        )

    if "growth_point_cycles" not in have:
        op.create_table(
            "growth_point_cycles",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("member_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("source_type", sa.String(12), nullable=False),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("plan_code", sa.String(24), nullable=False),
            sa.Column("price_minor", sa.Integer, nullable=False),
            sa.Column("term_months", sa.Integer, nullable=False),
            _ts("starts_at"), _ts("ends_at"), _ts("renewal_opens_at"), _ts("grace_ends_at"),
            sa.Column("ceiling_points", sa.Integer, nullable=False),
            sa.Column("process_ceiling", sa.Integer, nullable=False),
            sa.Column("closure_ceiling", sa.Integer, nullable=False),
            sa.Column("other_ceiling", sa.Integer, nullable=False),
            sa.Column("rule_version", sa.String(40), nullable=False),
            _ts("created_at"),
            sa.UniqueConstraint("source_type", "source_id", name="uq_gp_cycle_source"),
            sa.CheckConstraint(_in("source_type", ("SUBSCRIPTION", "MEMBERSHIP")), name="ck_gp_cycle_source_type"),
            sa.CheckConstraint("term_months > 0 AND price_minor > 0 AND ceiling_points >= 0", name="ck_gp_cycle_positive"),
        )
        op.create_index("ix_growth_point_cycles_member_id", "growth_point_cycles", ["member_id"])
        op.create_index("ix_gp_cycle_member_start", "growth_point_cycles", ["member_id", "starts_at"])

    if "growth_point_ledger" not in have:
        op.create_table(
            "growth_point_ledger",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"), _ts("event_at"),
            sa.Column("member_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("counterparty_id", sa.String(36), nullable=True),
            sa.Column("pair_key", sa.String(73), nullable=True),
            sa.Column("entry_type", sa.String(10), nullable=False),
            sa.Column("event_type", sa.String(30), nullable=False),
            sa.Column("category", sa.String(8), nullable=False),
            sa.Column("role", sa.String(10), nullable=True),
            sa.Column("reference_type", sa.String(20), nullable=False),
            sa.Column("reference_id", sa.String(36), nullable=False),
            sa.Column("parent_id", sa.String(36), nullable=True),
            sa.Column("cycle_id", sa.String(36), nullable=True),
            sa.Column("prospect_key", sa.String(16), nullable=True),
            sa.Column("points_delta", sa.Integer, nullable=False),
            sa.Column("requested_points", sa.Integer, nullable=False),
            sa.Column("capped_points", sa.Integer, nullable=False, server_default="0"),
            sa.Column("capped_by", sa.String(40), nullable=True),
            sa.Column("cap_trace", sa.Text, nullable=True),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("assurance", sa.String(10), nullable=True),
            sa.Column("verification_level", sa.Integer, nullable=False),
            _ts("available_at", True), _ts("expires_at", True),
            sa.Column("remaining", sa.Integer, nullable=False),
            sa.Column("balance_after", sa.Integer, nullable=False),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("details", sa.Text, nullable=True),
            sa.Column("created_by", sa.String(40), nullable=False, server_default="system"),
            sa.Column("rule_version", sa.String(40), nullable=False),
            sa.Column("idempotency_key", sa.String(160), nullable=False),
            sa.Column("shadow", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("day_key", sa.String(10), nullable=False),
            sa.Column("month_key", sa.String(7), nullable=False),
            sa.Column("quarter_key", sa.String(7), nullable=False),
            sa.UniqueConstraint("idempotency_key", name="uq_gp_ledger_idempotency"),
            sa.CheckConstraint("shadow = true", name="ck_gp_ledger_shadow_only"),
            sa.CheckConstraint(_in("entry_type", ("EARN", "VOID", "REVERSAL", "EXPIRY", "SIM_REDEEM")), name="ck_gp_ledger_entry_type"),
            sa.CheckConstraint(_in("event_type", EVENT_TYPES), name="ck_gp_ledger_event_type"),
            sa.CheckConstraint(_in("category", ("PROCESS", "CLOSURE", "OTHER")), name="ck_gp_ledger_category"),
            sa.CheckConstraint(_in("status", ("PENDING", "AVAILABLE", "CAPPED", "VOIDED", "REVERSED", "EXPIRED", "SIMULATED")), name="ck_gp_ledger_status"),
            sa.CheckConstraint("assurance IS NULL OR assurance IN ('LOW', 'VERIFIED')", name="ck_gp_ledger_assurance"),
            sa.CheckConstraint("(entry_type = 'EARN' AND points_delta >= 0) OR (entry_type <> 'EARN' AND points_delta <= 0)", name="ck_gp_ledger_sign"),
            sa.CheckConstraint("entry_type = 'EARN' OR parent_id IS NOT NULL", name="ck_gp_ledger_parent"),
            sa.CheckConstraint("verification_level BETWEEN 0 AND 4", name="ck_gp_ledger_level_range"),
            sa.CheckConstraint("entry_type <> 'EARN' OR points_delta = 0 OR verification_level >= 1", name="ck_gp_ledger_l0_never_pays"),
            sa.CheckConstraint("capped_points >= 0 AND requested_points >= 0 AND remaining >= 0", name="ck_gp_ledger_nonnegative"),
        )
        op.create_index("ix_gp_ledger_member_created", "growth_point_ledger", ["member_id", "created_at"])
        op.create_index("ix_gp_ledger_reference", "growth_point_ledger", ["reference_type", "reference_id"])
        op.create_index("ix_gp_ledger_pair_quarter", "growth_point_ledger", ["pair_key", "quarter_key"])
        op.create_index("ix_gp_ledger_cycle_category", "growth_point_ledger", ["cycle_id", "category"])
        op.create_index("ix_gp_ledger_expiry", "growth_point_ledger", ["entry_type", "expires_at"])
        op.create_index("ix_gp_ledger_member_month", "growth_point_ledger", ["member_id", "month_key"])
        op.create_index("ix_gp_ledger_member_day", "growth_point_ledger", ["member_id", "day_key"])
        op.create_index("ix_gp_ledger_parent", "growth_point_ledger", ["parent_id"])

    if "growth_point_balances" not in have:
        op.create_table(
            "growth_point_balances",
            sa.Column("member_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("total_points", sa.Integer, nullable=False, server_default="0"),
            _ts("updated_at"),
            sa.CheckConstraint("total_points >= 0", name="ck_gp_balance_nonnegative"),
        )

    if "growth_point_flags" not in have:
        op.create_table(
            "growth_point_flags",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("severity", sa.String(8), nullable=False, server_default="INFO"),
            sa.Column("member_id", sa.String(36), nullable=True),
            sa.Column("pair_key", sa.String(73), nullable=True),
            sa.Column("reference_type", sa.String(20), nullable=True),
            sa.Column("reference_id", sa.String(36), nullable=True),
            sa.Column("details", sa.Text, nullable=True),
            sa.Column("dedupe_key", sa.String(160), nullable=False),
            sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
            sa.Column("reviewed_by_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True),
            _ts("reviewed_at", True),
            sa.Column("review_note", sa.String(240), nullable=True),
            sa.UniqueConstraint("dedupe_key", name="uq_gp_flag_dedupe"),
            sa.CheckConstraint(_in("status", ("OPEN", "REVIEWED", "DISMISSED")), name="ck_gp_flag_status"),
            sa.CheckConstraint(_in("severity", ("INFO", "WARN", "HIGH")), name="ck_gp_flag_severity"),
        )
        op.create_index("ix_growth_point_flags_created_at", "growth_point_flags", ["created_at"])
        op.create_index("ix_growth_point_flags_kind", "growth_point_flags", ["kind"])
        op.create_index("ix_growth_point_flags_member_id", "growth_point_flags", ["member_id"])
        op.create_index("ix_growth_point_flags_status", "growth_point_flags", ["status"])

    if "growth_point_renewals" not in have:
        op.create_table(
            "growth_point_renewals",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("member_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("old_cycle_id", sa.String(36), sa.ForeignKey("growth_point_cycles.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("new_subscription_id", sa.String(36), nullable=False),      # no foreign key on purpose: a shadow table is never tied to a financial table
            sa.Column("new_invoice_id", sa.String(36), nullable=True),
            sa.Column("from_plan", sa.String(24), nullable=True),
            sa.Column("to_plan", sa.String(24), nullable=False),
            sa.Column("new_term_months", sa.Integer, nullable=False),
            sa.Column("new_price_minor", sa.Integer, nullable=False),
            sa.Column("outcome", sa.String(20), nullable=False),
            sa.Column("eligible_points", sa.Integer, nullable=False),
            sa.Column("redemption_cap_points", sa.Integer, nullable=False),
            sa.Column("redeemed_points", sa.Integer, nullable=False),
            sa.Column("remaining_points", sa.Integer, nullable=False),
            sa.Column("hypothetical_discount_paise", sa.Integer, nullable=False),
            sa.Column("hypothetical_payable_paise", sa.Integer, nullable=False),
            _ts("decided_at"), _ts("old_expires_at", True),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("rule_version", sa.String(40), nullable=False),
            sa.Column("idempotency_key", sa.String(160), nullable=False),
            sa.Column("shadow", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.UniqueConstraint("new_subscription_id", name="uq_gp_renewal_subscription"),
            sa.UniqueConstraint("idempotency_key", name="uq_gp_renewal_idempotency"),
            sa.CheckConstraint("shadow = true", name="ck_gp_renewal_shadow_only"),
            sa.CheckConstraint(_in("outcome", ("REDEEMED", "NOTHING_ELIGIBLE", "NOT_A_RENEWAL", "REFUNDED_CYCLE")), name="ck_gp_renewal_outcome"),
            sa.CheckConstraint("redeemed_points >= 0 AND eligible_points >= 0 AND remaining_points >= 0 AND redemption_cap_points >= 0", name="ck_gp_renewal_nonnegative"),
            sa.CheckConstraint("redeemed_points <= eligible_points AND redeemed_points <= redemption_cap_points", name="ck_gp_renewal_within_caps"),
            sa.CheckConstraint("hypothetical_discount_paise >= 0 AND hypothetical_payable_paise >= 0", name="ck_gp_renewal_amounts"),
        )
        op.create_index("ix_growth_point_renewals_created_at", "growth_point_renewals", ["created_at"])
        op.create_index("ix_growth_point_renewals_member_id", "growth_point_renewals", ["member_id"])
        op.create_index("ix_growth_point_renewals_old_cycle_id", "growth_point_renewals", ["old_cycle_id"])
        op.create_index("ix_growth_point_renewals_to_plan", "growth_point_renewals", ["to_plan"])

    _ledger_triggers(bind)
    lock_down(TABLES)


def _ledger_triggers(bind) -> None:
    """growth_point_ledger and growth_point_renewals are append-only: refuse UPDATE and DELETE (and TRUNCATE on PostgreSQL) at the database."""
    tables = ("growth_point_ledger", "growth_point_renewals")
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
    """Refused while the shadow ledger holds rows, exactly like 0008: it is the record the whole experiment is explained from."""
    import os

    bind = op.get_bind()
    insp = sa.inspect(bind)
    held = bind.exec_driver_sql("SELECT COUNT(*) FROM growth_point_ledger").scalar() if insp.has_table("growth_point_ledger") else 0
    if held and os.environ.get("TGL_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            f"Refusing to downgrade 0010: it would permanently delete {held} shadow ledger rows. Export them first "
            "(GET /api/admin/growth-points/export), then set TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1 if that is really intended."
        )
    if bind.dialect.name == "sqlite":
        for t in ("growth_point_ledger", "growth_point_renewals"):
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_update")
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_delete")
    elif bind.dialect.name == "postgresql":
        for t in ("growth_point_ledger", "growth_point_renewals"):
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_change ON {t}")
            op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
        op.execute("DROP FUNCTION IF EXISTS tgl_gp_ledger_immutable()")
    for table in ("growth_point_renewals", "growth_point_flags", "growth_point_balances", "growth_point_ledger", "growth_point_cycles", "growth_point_rule_versions"):
        if insp.has_table(table):
            op.drop_table(table)
