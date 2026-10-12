"""business_referrals: prospect snapshot, opportunity context, lifecycle stamps.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

LIVE = "status IN ('GIVEN','ACCEPTED','CONTACTED','MEETING_DONE','BUSINESS_CLOSED') AND prospect_phone IS NOT NULL"

COLUMNS = [
    ("contacted_at", sa.DateTime(timezone=True)),
    ("closed_at", sa.DateTime(timezone=True)),
    ("prospect_name", sa.String(120)),
    ("prospect_phone", sa.String(20)),
    ("prospect_email", sa.String(255)),
    ("prospect_company", sa.String(160)),
    ("prospect_role", sa.String(120)),
    ("prospect_location", sa.String(120)),
    ("preferred_contact_method", sa.String(12)),
    ("relationship", sa.String(24)),
    ("relationship_other", sa.String(120)),
    ("opportunity_description", sa.Text()),
    ("category", sa.String(8)),
    ("urgency", sa.String(12)),
    ("value_range", sa.String(16)),
    ("intro_method", sa.String(16)),
    ("intro_call_preference", sa.String(120)),
    ("contact_permission", sa.String(16)),
    ("consent_confirmed_at", sa.DateTime(timezone=True)),
    ("quality", sa.String(16)),
    ("last_action_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    have = {c["name"] for c in insp.get_columns("business_referrals")}
    with op.batch_alter_table("business_referrals") as batch:
        for name, type_ in COLUMNS:
            if name not in have:
                batch.add_column(sa.Column(name, type_, nullable=True))
    # Existing referrals: their last action is when they were last touched.
    op.execute("UPDATE business_referrals SET last_action_at = updated_at WHERE last_action_at IS NULL")

    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("business_referrals")}
    if "ix_business_referrals_category" not in indexes:
        op.create_index("ix_business_referrals_category", "business_referrals", ["category"])
    if "ix_ref_receiver_created" not in indexes:
        op.create_index("ix_ref_receiver_created", "business_referrals", ["receiver_user_id", "created_at"])
    if "ix_ref_giver_created" not in indexes:
        op.create_index("ix_ref_giver_created", "business_referrals", ["giver_user_id", "created_at"])
    if "ix_ref_receiver_phone" not in indexes:
        op.create_index("ix_ref_receiver_phone", "business_referrals", ["receiver_user_id", "prospect_phone"])
    if "uq_ref_live_giver_receiver_phone" not in indexes:
        op.create_index(
            "uq_ref_live_giver_receiver_phone", "business_referrals",
            ["giver_user_id", "receiver_user_id", "prospect_phone"], unique=True,
            sqlite_where=sa.text(LIVE), postgresql_where=sa.text(LIVE),
        )


def downgrade() -> None:
    for name in ("uq_ref_live_giver_receiver_phone", "ix_ref_receiver_phone", "ix_ref_giver_created",
                 "ix_ref_receiver_created", "ix_business_referrals_category"):
        op.drop_index(name, table_name="business_referrals")
    with op.batch_alter_table("business_referrals") as batch:
        for name, _ in reversed(COLUMNS):
            batch.drop_column(name)
