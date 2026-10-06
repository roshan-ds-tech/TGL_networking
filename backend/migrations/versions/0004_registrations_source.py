"""registrations.source: "local" or "pythonanywhere" (read-only copies of the
legacy system's registrations, see app/legacy_sync.py).

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("registrations")}
    if "source" in cols:
        return  # already added by a development auto-create
    with op.batch_alter_table("registrations") as batch:
        batch.add_column(sa.Column("source", sa.String(length=16), server_default="local", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("registrations") as batch:
        batch.drop_column("source")
