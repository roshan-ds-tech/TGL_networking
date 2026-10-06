"""baseline schema — the 15 tables production had before migrations were
introduced (previously created at app startup by create_all + sync_schema).

An existing database is STAMPED at this revision instead of running it
(app/migrate.py); a new database runs it.

Revision ID: 0001
Revises: 
Create Date: 2026-10-06 12:14:20.253086
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


from migrations.helpers import lock_down  # noqa: E402

BASELINE_TABLES = ['admins', 'events', 'users', 'business_referrals', 'businesses', 'connections', 'notifications', 'personal_profiles', 'referral_requests', 'user_verification_tokens', 'business_needs', 'event_registrations', 'networking_profiles', 'registrations', 'tgl_memberships']


def upgrade() -> None:
    op.create_table('admins',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admins_email'), 'admins', ['email'], unique=True)
    op.create_table('events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('grand_finale_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('registration_open', sa.Boolean(), nullable=False),
    sa.Column('registration_closes_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('membership_duration_months', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_events_slug'), 'events', ['slug'], unique=True)
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('business_referrals',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('giver_user_id', sa.String(length=36), nullable=False),
    sa.Column('receiver_user_id', sa.String(length=36), nullable=False),
    sa.Column('business_need', sa.String(length=240), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('meeting_done_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('business_closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revenue_generated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['giver_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['receiver_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_business_referrals_giver_user_id'), 'business_referrals', ['giver_user_id'], unique=False)
    op.create_index(op.f('ix_business_referrals_receiver_user_id'), 'business_referrals', ['receiver_user_id'], unique=False)
    op.create_index(op.f('ix_business_referrals_status'), 'business_referrals', ['status'], unique=False)
    op.create_table('businesses',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('business_name', sa.String(length=160), nullable=False),
    sa.Column('category', sa.String(length=8), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('city', sa.String(length=120), nullable=False),
    sa.Column('employee_band', sa.String(length=16), nullable=False),
    sa.Column('business_age', sa.String(length=16), nullable=False),
    sa.Column('website', sa.String(length=300), nullable=True),
    sa.Column('instagram', sa.String(length=300), nullable=True),
    sa.Column('linkedin', sa.String(length=300), nullable=True),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('founder_story', sa.Text(), nullable=True),
    sa.Column('business_stage', sa.String(length=80), nullable=False),
    sa.Column('tgl_verified', sa.Boolean(), nullable=False),
    sa.Column('tgl_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification_status', sa.String(length=16), nullable=False),
    sa.Column('verification_submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_business_user_created', 'businesses', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_businesses_category'), 'businesses', ['category'], unique=False)
    op.create_index(op.f('ix_businesses_user_id'), 'businesses', ['user_id'], unique=False)
    op.create_table('connections',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('requester_user_id', sa.String(length=36), nullable=False),
    sa.Column('target_user_id', sa.String(length=36), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['requester_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('requester_user_id', 'target_user_id', name='uq_connection_pair')
    )
    op.create_index(op.f('ix_connections_requester_user_id'), 'connections', ['requester_user_id'], unique=False)
    op.create_index(op.f('ix_connections_target_user_id'), 'connections', ['target_user_id'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('recipient_user_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('related_entity_type', sa.String(length=64), nullable=True),
    sa.Column('related_entity_id', sa.String(length=36), nullable=True),
    sa.Column('actor_user_id', sa.String(length=36), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notification_recipient_read', 'notifications', ['recipient_user_id', 'read_at'], unique=False)
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_recipient_user_id'), 'notifications', ['recipient_user_id'], unique=False)
    op.create_index(op.f('ix_notifications_type'), 'notifications', ['type'], unique=False)
    op.create_table('personal_profiles',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('city', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=120), nullable=False),
    sa.Column('short_bio', sa.Text(), nullable=False),
    sa.Column('profile_photo_url', sa.String(length=500), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('referral_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('requester_user_id', sa.String(length=36), nullable=False),
    sa.Column('target_user_id', sa.String(length=36), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['requester_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_referral_requests_requester_user_id'), 'referral_requests', ['requester_user_id'], unique=False)
    op.create_index(op.f('ix_referral_requests_target_user_id'), 'referral_requests', ['target_user_id'], unique=False)
    op.create_table('user_verification_tokens',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('purpose', sa.String(length=24), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_verification_tokens_token_hash'), 'user_verification_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_user_verification_tokens_user_id'), 'user_verification_tokens', ['user_id'], unique=False)
    op.create_table('business_needs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('business_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_business_needs_business_id'), 'business_needs', ['business_id'], unique=False)
    op.create_index(op.f('ix_business_needs_category'), 'business_needs', ['category'], unique=False)
    op.create_index(op.f('ix_business_needs_created_at'), 'business_needs', ['created_at'], unique=False)
    op.create_index(op.f('ix_business_needs_status'), 'business_needs', ['status'], unique=False)
    op.create_index(op.f('ix_business_needs_user_id'), 'business_needs', ['user_id'], unique=False)
    op.create_table('event_registrations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('business_id', sa.String(length=36), nullable=False),
    sa.Column('legacy_registration_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('payment_status', sa.String(length=32), nullable=False),
    sa.Column('payment_reference', sa.String(length=32), nullable=True),
    sa.Column('admin_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('admin_verified_by_id', sa.String(length=36), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['admin_verified_by_id'], ['admins.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'user_id', 'business_id', name='uq_event_registration_user_business')
    )
    op.create_index(op.f('ix_event_registrations_business_id'), 'event_registrations', ['business_id'], unique=False)
    op.create_index(op.f('ix_event_registrations_event_id'), 'event_registrations', ['event_id'], unique=False)
    op.create_index(op.f('ix_event_registrations_payment_reference'), 'event_registrations', ['payment_reference'], unique=False)
    op.create_index(op.f('ix_event_registrations_payment_status'), 'event_registrations', ['payment_status'], unique=False)
    op.create_index(op.f('ix_event_registrations_status'), 'event_registrations', ['status'], unique=False)
    op.create_index(op.f('ix_event_registrations_user_id'), 'event_registrations', ['user_id'], unique=False)
    op.create_table('networking_profiles',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('business_id', sa.String(length=36), nullable=False),
    sa.Column('headline', sa.String(length=180), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('founder_story', sa.Text(), nullable=True),
    sa.Column('industry_tags', sa.Text(), nullable=True),
    sa.Column('business_stage', sa.String(length=80), nullable=True),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('interests', sa.Text(), nullable=True),
    sa.Column('open_to_mentoring', sa.Boolean(), nullable=False),
    sa.Column('seeking_mentor', sa.Boolean(), nullable=False),
    sa.Column('show_email', sa.Boolean(), nullable=False),
    sa.Column('show_phone', sa.Boolean(), nullable=False),
    sa.Column('trust_score', sa.Integer(), nullable=False),
    sa.Column('growth_points', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_networking_profiles_business_id'), 'networking_profiles', ['business_id'], unique=False)
    op.create_index(op.f('ix_networking_profiles_user_id'), 'networking_profiles', ['user_id'], unique=True)


    op.create_table('registrations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('business_name', sa.String(length=160), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('category', sa.String(length=8), nullable=False),
    sa.Column('employees', sa.String(length=16), nullable=False),
    sa.Column('business_age', sa.String(length=16), nullable=False),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('proof_filename', sa.String(length=80), nullable=False),
    sa.Column('proof_mime', sa.String(length=64), nullable=False),
    sa.Column('proof_bytes', sa.Integer(), nullable=False),
    sa.Column('agreed_terms', sa.Boolean(), nullable=False),
    sa.Column('media_consent', sa.Boolean(), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by_id', sa.String(length=36), nullable=True),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('business_id', sa.String(length=36), nullable=True),
    sa.Column('event_registration_id', sa.String(length=36), nullable=True),
    sa.Column('submitter_ip_hash', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['verified_by_id'], ['admins.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reg_category_created', 'registrations', ['category', 'created_at'], unique=False)
    op.create_index('ix_reg_verified_created', 'registrations', ['verified', 'created_at'], unique=False)
    op.create_index(op.f('ix_registrations_category'), 'registrations', ['category'], unique=False)
    op.create_index(op.f('ix_registrations_created_at'), 'registrations', ['created_at'], unique=False)
    op.create_index(op.f('ix_registrations_email'), 'registrations', ['email'], unique=False)
    op.create_index(op.f('ix_registrations_phone'), 'registrations', ['phone'], unique=False)
    op.create_index(op.f('ix_registrations_verified'), 'registrations', ['verified'], unique=False)
    op.create_table('tgl_memberships',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('membership_type', sa.String(length=32), nullable=False),
    sa.Column('pathway', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('source_event_registration_id', sa.String(length=36), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_event_registration_id'], ['event_registrations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_event_registration_id')
    )
    op.create_index('ix_membership_user_status', 'tgl_memberships', ['user_id', 'status'], unique=False)
    op.create_index(op.f('ix_tgl_memberships_status'), 'tgl_memberships', ['status'], unique=False)
    op.create_index(op.f('ix_tgl_memberships_user_id'), 'tgl_memberships', ['user_id'], unique=False)
    # registrations <-> event_registrations reference each other: add those
    # two keys once both tables exist.
    with op.batch_alter_table('registrations') as batch:
        batch.create_foreign_key('registrations_event_registration_id_fkey', 'event_registrations', ['event_registration_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('event_registrations') as batch:
        batch.create_foreign_key('event_registrations_legacy_registration_id_fkey', 'registrations', ['legacy_registration_id'], ['id'], ondelete='SET NULL')
    lock_down(BASELINE_TABLES)


def downgrade() -> None:
    with op.batch_alter_table('registrations') as batch:
        batch.drop_constraint('registrations_event_registration_id_fkey', type_='foreignkey')
    with op.batch_alter_table('event_registrations') as batch:
        batch.drop_constraint('event_registrations_legacy_registration_id_fkey', type_='foreignkey')
    op.drop_table('tgl_memberships')
    op.drop_table('registrations')
    op.drop_table('networking_profiles')
    op.drop_table('event_registrations')
    op.drop_table('business_needs')
    op.drop_table('user_verification_tokens')
    op.drop_table('referral_requests')
    op.drop_table('personal_profiles')
    op.drop_table('notifications')
    op.drop_table('connections')
    op.drop_table('businesses')
    op.drop_table('business_referrals')
    op.drop_table('users')
    op.drop_table('events')
    op.drop_table('admins')
