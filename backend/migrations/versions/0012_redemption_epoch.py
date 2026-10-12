"""Growth Points: the eligibility epoch (shadow-period points never carry over).

One immutable row, written once by the programme owner after management approves the cutoff, holds the instant before which every point is a
shadow-period (historical) point and permanently ineligible for redemption. It can not be edited, deleted or backdated (CHECK: cutoff_at >=
recorded_at; append-only triggers; singleton). Nothing here changes any existing row, and no cutoff is recorded by this migration.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

from migrations.helpers import lock_down

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TABLE = "growth_point_redemption_epoch"


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("singleton", sa.String(8), nullable=False, server_default="ONLY"),
            sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("recorded_by", sa.String(36), nullable=False),
            sa.Column("reason", sa.String(240), nullable=False),
            sa.UniqueConstraint("singleton", name="uq_gp_epoch_singleton"),
            sa.CheckConstraint("singleton = 'ONLY'", name="ck_gp_epoch_singleton"),
            sa.CheckConstraint("cutoff_at >= recorded_at", name="ck_gp_epoch_not_backdated"),
        )
    if bind.dialect.name == "sqlite":
        for name, op_ in ((f"{TABLE}_no_update", "UPDATE"), (f"{TABLE}_no_delete", "DELETE")):
            op.execute(f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op_} ON {TABLE} BEGIN SELECT RAISE(ABORT, '{TABLE} is append-only'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE OR REPLACE FUNCTION tgl_gp_ledger_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'growth point history is append-only'; END; $$ LANGUAGE plpgsql")
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_change ON {TABLE}")
        op.execute(f"CREATE TRIGGER {TABLE}_no_change BEFORE UPDATE OR DELETE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION tgl_gp_ledger_immutable()")
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_truncate ON {TABLE}")
        op.execute(f"CREATE TRIGGER {TABLE}_no_truncate BEFORE TRUNCATE ON {TABLE} FOR EACH STATEMENT EXECUTE FUNCTION tgl_gp_ledger_immutable()")
    lock_down([TABLE])


def downgrade() -> None:
    """Refused once a cutoff has been recorded: it is the permanent line between shadow-period and eligible points."""
    import os

    bind = op.get_bind()
    insp = sa.inspect(bind)
    held = bind.exec_driver_sql(f"SELECT COUNT(*) FROM {TABLE}").scalar() if insp.has_table(TABLE) else 0
    if held and os.environ.get("TGL_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError("Refusing to downgrade 0012: an eligibility cutoff has been recorded. It is the permanent line between shadow-period and eligible points. "
                           "Set TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1 only if that is really intended.")
    if bind.dialect.name == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_change ON {TABLE}")
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_truncate ON {TABLE}")
    if insp.has_table(TABLE):
        op.drop_table(TABLE)
