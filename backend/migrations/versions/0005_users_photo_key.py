"""users.photo_key: stored name of the member's profile photo.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "photo_key" in cols:
        return  # already added by a development auto-create
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("photo_key", sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("photo_key")
