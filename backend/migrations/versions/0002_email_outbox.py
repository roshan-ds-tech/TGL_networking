"""email outbox: transactional emails queued in the request's transaction and
sent by the background worker (app/outbox.py).

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

from migrations.helpers import lock_down

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A development database built by the app's auto-create may already have
    # it; a stamped pre-migration database won't. Don't fail either way.
    if sa.inspect(op.get_bind()).has_table("email_outbox"):
        lock_down(["email_outbox"])
        return
    op.create_table('email_outbox',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('to_email', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('html', sa.Text(), nullable=True),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_email_outbox_due', 'email_outbox', ['status', 'next_attempt_at'], unique=False)
    lock_down(["email_outbox"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_due", table_name="email_outbox")
    op.drop_table("email_outbox")
