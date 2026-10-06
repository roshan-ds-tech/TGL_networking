"""index registrations by lower(email)

Every /status and networking request checks "is this account's email on a
registration?" with lower(email). EXPLAIN ANALYZE on realistic volume (400
registrations, 3,000 accounts): the directory's account<->registration join
went from 8.3 ms to 0.7 ms, and an unregistered-email lookup became an index
scan. Built on a small table, so a plain (transactional) CREATE INDEX is fine.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("registrations")}
    if "ix_registrations_lower_email" in existing:
        return  # already built by a development auto-create
    op.create_index("ix_registrations_lower_email", "registrations", [sa.text("lower(email)")], unique=False)


def downgrade() -> None:
    op.drop_index("ix_registrations_lower_email", table_name="registrations")
