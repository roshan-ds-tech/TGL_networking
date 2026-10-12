"""connections: request lifecycle (status, responded_at).

Requests made before this existed stay PENDING, except pairs where both members
asked each other: those are connected, so both rows become ACCEPTED.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("connections")}
    with op.batch_alter_table("connections") as batch:
        if "status" not in cols:
            batch.add_column(sa.Column("status", sa.String(length=12), nullable=False, server_default="PENDING"))
        if "responded_at" not in cols:
            batch.add_column(sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("connections")}
    if "ix_connections_status" not in indexes:
        op.create_index("ix_connections_status", "connections", ["status"])
    op.execute(
        "UPDATE connections SET status = 'ACCEPTED', responded_at = CURRENT_TIMESTAMP "
        "WHERE status = 'PENDING' AND EXISTS ("
        "SELECT 1 FROM connections r WHERE r.requester_user_id = connections.target_user_id "
        "AND r.target_user_id = connections.requester_user_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_connections_status", table_name="connections")
    with op.batch_alter_table("connections") as batch:
        batch.drop_column("responded_at")
        batch.drop_column("status")
