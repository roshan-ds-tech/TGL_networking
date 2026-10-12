"""Phase 0 foundations: plans, subscriptions, invoices, payments, two-party
confirmations, verified deal closures + evidence, and an append-only audit log.

Nothing here awards or applies Growth Points. invoices.discount_minor is held at
zero by a CHECK constraint.

Revision ID: 0008
Revises: 0007
"""
import uuid
from datetime import datetime, timezone

import os

from alembic import op
import sqlalchemy as sa

from migrations.helpers import lock_down

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

NEW_TABLES = ["plans", "subscriptions", "invoices", "payments", "referral_confirmations", "deal_closures", "deal_evidence", "audit_log"]
NOT_ENDED = "status NOT IN ('REJECTED','CANCELLED','INVALIDATED')"
LIVE_SUB = "status IN ('PENDING','ACTIVE')"


def _ts(name: str, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _have(insp, table: str) -> bool:
    return insp.has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _have(insp, "plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("code", sa.String(24), nullable=False),
            sa.Column("name", sa.String(60), nullable=False),
            sa.Column("price_minor", sa.Integer, nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("billing_period", sa.String(16), nullable=False, server_default="SEASON"),
            sa.Column("period_months", sa.Integer, nullable=False, server_default="3"),
            sa.Column("season_slug", sa.String(60), nullable=True),
            sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
            _ts("effective_from"), _ts("effective_to", True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            _ts("created_at"), _ts("updated_at"),
            sa.CheckConstraint("price_minor > 0", name="ck_plan_price_positive"),
            sa.CheckConstraint("period_months > 0", name="ck_plan_period_positive"),
            sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_plan_status"),
            sa.CheckConstraint("billing_period IN ('SEASON')", name="ck_plan_billing_period"),
        )
        op.create_index("ix_plans_code", "plans", ["code"], unique=True)
        op.create_index("ix_plans_status", "plans", ["status"])
        now = datetime.now(timezone.utc)
        plans = sa.table(
            "plans", sa.column("id"), sa.column("code"), sa.column("name"), sa.column("price_minor"), sa.column("currency"),
            sa.column("billing_period"), sa.column("period_months"), sa.column("season_slug"), sa.column("status"),
            sa.column("effective_from"), sa.column("sort_order"), sa.column("created_at"), sa.column("updated_at"),
        )
        op.bulk_insert(plans, [
            {"id": str(uuid.uuid4()), "code": code, "name": name, "price_minor": price, "currency": "INR", "billing_period": "SEASON",
             "period_months": 3, "season_slug": "season-1", "status": "ACTIVE", "effective_from": now, "sort_order": order,
             "created_at": now, "updated_at": now}
            for code, name, price, order in (("connect", "Connect", 300000, 1), ("growth", "Growth", 500000, 2), ("elite", "Elite", 1000000, 3))
        ])

    if not _have(insp, "subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
            _ts("starts_at", True), _ts("expires_at", True), _ts("activated_at", True), _ts("cancelled_at", True),
            sa.Column("cancel_reason", sa.String(240), nullable=True),
            _ts("created_at"), _ts("updated_at"),
            sa.CheckConstraint("status IN ('PENDING','ACTIVE','EXPIRED','CANCELLED')", name="ck_subscription_status"),
            sa.CheckConstraint("status <> 'ACTIVE' OR (starts_at IS NOT NULL AND expires_at IS NOT NULL AND activated_at IS NOT NULL)", name="ck_subscription_active_dates"),
        )
        op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
        op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
        op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
        op.create_index("uq_subscription_live_user", "subscriptions", ["user_id"], unique=True, sqlite_where=sa.text(LIVE_SUB), postgresql_where=sa.text(LIVE_SUB))

    if not _have(insp, "invoices"):
        op.create_table(
            "invoices",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("number", sa.String(32), nullable=False),
            sa.Column("subscription_id", sa.String(36), sa.ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("season_slug", sa.String(60), nullable=True),
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("plan_name", sa.String(60), nullable=False),
            sa.Column("period_months", sa.Integer, nullable=False),
            sa.Column("list_price_minor", sa.Integer, nullable=False),
            sa.Column("amount_before_discount_minor", sa.Integer, nullable=False),
            sa.Column("discount_minor", sa.Integer, nullable=False, server_default="0"),
            sa.Column("discount_reason", sa.String(120), nullable=True),
            sa.Column("amount_due_minor", sa.Integer, nullable=False),
            sa.Column("amount_paid_minor", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(12), nullable=False, server_default="ISSUED"),
            _ts("issued_at", True), _ts("paid_at", True), _ts("refunded_at", True),
            sa.Column("metadata_json", sa.Text, nullable=True),
            _ts("created_at"), _ts("updated_at"),
            sa.CheckConstraint("discount_minor = 0", name="ck_invoice_no_discount_phase0"),
            sa.CheckConstraint("amount_due_minor = amount_before_discount_minor - discount_minor", name="ck_invoice_amount_due"),
            sa.CheckConstraint("amount_paid_minor >= 0 AND amount_due_minor >= 0 AND list_price_minor > 0", name="ck_invoice_amounts"),
            sa.CheckConstraint("status IN ('DRAFT','ISSUED','PENDING','PAID','FAILED','CANCELLED','REFUNDED')", name="ck_invoice_status"),
            sa.CheckConstraint("status <> 'PAID' OR amount_paid_minor = amount_due_minor", name="ck_invoice_paid_matches"),
            sa.CheckConstraint("amount_paid_minor <= amount_due_minor", name="ck_invoice_paid_not_over"),
        )
        op.create_index("ix_invoices_number", "invoices", ["number"], unique=True)
        op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
        op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
        op.create_index("ix_invoices_status", "invoices", ["status"])

    if not _have(insp, "payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("method", sa.String(24), nullable=False, server_default="MANUAL_PROOF"),
            sa.Column("amount_minor", sa.Integer, nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
            sa.Column("reference", sa.String(32), nullable=False),
            sa.Column("proof_filename", sa.String(80), nullable=True),
            sa.Column("proof_mime", sa.String(64), nullable=True),
            sa.Column("proof_bytes", sa.Integer, nullable=True),
            _ts("submitted_at", True), _ts("verified_at", True),
            sa.Column("verified_by_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True),
            sa.Column("rejection_reason", sa.String(240), nullable=True),
            _ts("refunded_at", True),
            sa.Column("refund_reason", sa.String(240), nullable=True),
            _ts("created_at"), _ts("updated_at"),
            sa.CheckConstraint("amount_minor > 0", name="ck_payment_amount_positive"),
            sa.CheckConstraint("status IN ('PENDING','SUBMITTED','VERIFIED','FAILED','REFUNDED')", name="ck_payment_status"),
            sa.CheckConstraint("status NOT IN ('VERIFIED','REFUNDED') OR verified_at IS NOT NULL", name="ck_payment_verified_stamp"),
        )
        op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])
        op.create_index("ix_payments_user_id", "payments", ["user_id"])
        op.create_index("ix_payments_status", "payments", ["status"])
        op.create_index("ix_payments_reference", "payments", ["reference"], unique=True)

    if not _have(insp, "referral_confirmations"):
        op.create_table(
            "referral_confirmations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("referral_id", sa.String(36), sa.ForeignKey("business_referrals.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(8), nullable=False),
            _ts("confirmed_at"),
            sa.UniqueConstraint("referral_id", "kind", "user_id", name="uq_referral_confirmation"),
            sa.CheckConstraint("kind IN ('MEETING')", name="ck_confirmation_kind"),
            sa.CheckConstraint("role IN ('giver','receiver')", name="ck_confirmation_role"),
        )
        op.create_index("ix_referral_confirmations_referral_id", "referral_confirmations", ["referral_id"])

    if not _have(insp, "deal_closures"):
        op.create_table(
            "deal_closures",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("referral_id", sa.String(36), sa.ForeignKey("business_referrals.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("reported_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actual_value_minor", sa.BigInteger, nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
            sa.Column("value_band", sa.String(12), nullable=False),
            sa.Column("evidence_required", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("admin_approval_required", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="AWAITING_CONFIRMATION"),
            sa.Column("verification_level", sa.Integer, nullable=False, server_default="0"),
            _ts("confirmed_by_receiver_at", True), _ts("confirmed_by_referrer_at", True),
            sa.Column("confirmed_by_referrer_user_id", sa.String(36), nullable=True),
            _ts("submitted_at"), _ts("verified_at", True),
            sa.Column("verified_by_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True),
            sa.Column("rejection_reason", sa.String(240), nullable=True),
            sa.Column("dispute_reason", sa.String(500), nullable=True),
            sa.Column("disputed_by_user_id", sa.String(36), nullable=True),
            _ts("disputed_at", True),
            sa.Column("status_before_dispute", sa.String(24), nullable=True),
            _ts("invalidated_at", True),
            sa.Column("invalidated_reason", sa.String(240), nullable=True),
            _ts("created_at"), _ts("updated_at"),
            sa.CheckConstraint("actual_value_minor > 0", name="ck_closure_value_positive"),
            sa.CheckConstraint("verification_level BETWEEN 0 AND 4", name="ck_closure_level_range"),
            sa.CheckConstraint("status IN ('AWAITING_CONFIRMATION','AWAITING_EVIDENCE','UNDER_REVIEW','VERIFIED','REJECTED','DISPUTED','CANCELLED','INVALIDATED')", name="ck_closure_status"),
            sa.CheckConstraint("value_band IN ('UNDER_25K','25K_1L','1L_5L','5L_10L','10L_PLUS')", name="ck_closure_band"),
            sa.CheckConstraint("status <> 'VERIFIED' OR verification_level >= 2", name="ck_closure_verified_level"),
        )
        op.create_index("ix_deal_closures_referral_id", "deal_closures", ["referral_id"])
        op.create_index("ix_deal_closures_status", "deal_closures", ["status"])
        op.create_index("ix_deal_closures_value_band", "deal_closures", ["value_band"])
        op.create_index("uq_closure_live_referral", "deal_closures", ["referral_id"], unique=True, sqlite_where=sa.text(NOT_ENDED), postgresql_where=sa.text(NOT_ENDED))

    if not _have(insp, "deal_evidence"):
        op.create_table(
            "deal_evidence",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("closure_id", sa.String(36), sa.ForeignKey("deal_closures.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("evidence_type", sa.String(16), nullable=False),
            sa.Column("storage_name", sa.String(80), nullable=False),
            sa.Column("mime", sa.String(64), nullable=False),
            sa.Column("size_bytes", sa.Integer, nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("note", sa.String(240), nullable=True),
            sa.Column("uploaded_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            _ts("uploaded_at"),
            sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
            sa.Column("verified_by_admin_id", sa.String(36), sa.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True),
            _ts("verified_at", True),
            sa.Column("rejection_reason", sa.String(240), nullable=True),
            sa.CheckConstraint("status IN ('PENDING','VERIFIED','REJECTED')", name="ck_evidence_status"),
            sa.CheckConstraint("evidence_type IN ('INVOICE','PAYMENT_PROOF','OTHER')", name="ck_evidence_type"),
        )
        op.create_index("ix_deal_evidence_closure_id", "deal_evidence", ["closure_id"])
        op.create_index("ix_deal_evidence_sha256", "deal_evidence", ["sha256"])
        op.create_index("ix_deal_evidence_status", "deal_evidence", ["status"])

    if not _have(insp, "audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("actor_type", sa.String(8), nullable=False),
            sa.Column("actor_id", sa.String(36), nullable=True),
            sa.Column("actor_role", sa.String(16), nullable=True),
            sa.Column("action", sa.String(60), nullable=False),
            sa.Column("resource_type", sa.String(40), nullable=False),
            sa.Column("resource_id", sa.String(36), nullable=True),
            sa.Column("before_json", sa.Text, nullable=True),
            sa.Column("after_json", sa.Text, nullable=True),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("request_id", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.Text, nullable=True),
            sa.CheckConstraint("actor_type IN ('USER','ADMIN','SYSTEM')", name="ck_audit_actor_type"),
        )
        op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
        op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
        op.create_index("ix_audit_log_action", "audit_log", ["action"])
        op.create_index("ix_audit_resource", "audit_log", ["resource_type", "resource_id", "created_at"])

    # business_referrals: admin review marker
    have = {c["name"] for c in insp.get_columns("business_referrals")}
    with op.batch_alter_table("business_referrals") as batch:
        if "flagged" not in have:
            batch.add_column(sa.Column("flagged", sa.Boolean, nullable=False, server_default=sa.false()))
        if "flag_reason" not in have:
            batch.add_column(sa.Column("flag_reason", sa.String(240), nullable=True))
        if "flagged_at" not in have:
            batch.add_column(sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True))
        if "flagged_by" not in have:
            batch.add_column(sa.Column("flagged_by", sa.String(36), nullable=True))
    idx = {i["name"] for i in sa.inspect(bind).get_indexes("business_referrals")}
    if "ix_business_referrals_flagged" not in idx:
        op.create_index("ix_business_referrals_flagged", "business_referrals", ["flagged"])

    _audit_triggers(bind)
    lock_down(NEW_TABLES)  # Supabase Data API: RLS on, no policies, anon/authenticated lose grants


def _audit_triggers(bind) -> None:
    """audit_log is append-only: refuse UPDATE and DELETE (and TRUNCATE on Postgres) at the database."""
    if bind.dialect.name == "sqlite":
        for name, op_ in (("audit_log_no_update", "UPDATE"), ("audit_log_no_delete", "DELETE")):
            op.execute(f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op_} ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE OR REPLACE FUNCTION tgl_audit_log_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log")
        op.execute("CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION tgl_audit_log_immutable()")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
        op.execute("CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log FOR EACH STATEMENT EXECUTE FUNCTION tgl_audit_log_immutable()")


def downgrade() -> None:
    bind = op.get_bind()
    # This drops the financial and audit records. Refuse if there is anything in them, unless the operator
    # has said (TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1) that losing it is intended (for example a rehearsal on a copy).
    held = {t: bind.exec_driver_sql(f"SELECT COUNT(*) FROM {t}").scalar() for t in ("subscriptions", "invoices", "payments", "deal_closures", "deal_evidence", "referral_confirmations", "audit_log")}
    if any(held.values()) and os.environ.get("TGL_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(
            "Refusing to downgrade 0008: it would permanently delete " + ", ".join(f"{n} rows from {t}" for t, n in held.items() if n)
            + ". Take a backup, then set TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1 if that is really intended."
        )
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS tgl_audit_log_immutable()")
    op.drop_index("ix_business_referrals_flagged", table_name="business_referrals")
    with op.batch_alter_table("business_referrals") as batch:
        for col in ("flagged_by", "flagged_at", "flag_reason", "flagged"):
            batch.drop_column(col)
    for table in ("audit_log", "deal_evidence", "deal_closures", "referral_confirmations", "payments", "invoices", "subscriptions", "plans"):
        op.drop_table(table)
