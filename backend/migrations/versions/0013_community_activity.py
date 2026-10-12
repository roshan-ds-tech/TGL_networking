"""Phase A: record connections, business needs and help offers (facts only; no Growth Points).

Adds, and changes nothing that exists:
  * connections: a NULLABLE pair_key column and a partial unique index over rows that carry one (existing rows keep NULL and are untouched);
  * business_needs: twelve NULLABLE columns for the need lifecycle (published / resolved / cancelled / removed, who removed it and why, the credited
    offer, duplicate-detection hashes, the publication month, and a TRACKED quality field). Every existing need stays valid and OPEN; only the new
    published_at column is filled (from created_at);
  * need_help_offers: one durable record per (need, helper) with a status machine and a unique constraint;
  * community_events: the append-only history of connection, need and help activity (UPDATE / DELETE / TRUNCATE refused by trigger), with ids and
    reason codes only, no free text. Existing connections are seeded into it once, marked BACKFILL, so "was this pair connected before" works for
    pairs connected before this release. Backfilled history is never reported as observation.

It touches no ledger, invoice, payment, subscription or price, creates no Growth Points event, and records no cutoff.

Revision ID: 0013
Revises: 0012
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

from migrations.helpers import lock_down

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

NEED_COLUMNS = (
    ("published_at", sa.DateTime(timezone=True)), ("resolved_at", sa.DateTime(timezone=True)), ("cancelled_at", sa.DateTime(timezone=True)),
    ("removed_at", sa.DateTime(timezone=True)), ("removed_by_admin_id", sa.String(36)), ("removed_reason", sa.String(240)), ("resolved_offer_id", sa.String(36)),
    ("title_hash", sa.String(32)), ("description_hash", sa.String(32)), ("publish_month_key", sa.String(7)), ("qualifies_for_future_reward", sa.Boolean()),
    ("quality_note", sa.String(24)),
)
OFFER_STATUSES = "'OFFERED','ACCEPTED','DECLINED','WITHDRAWN','CONFIRMED_HELPFUL','NOT_HELPFUL'"


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # connections: the hashed pair, set on every NEW row, plus a partial unique index over only those rows, so two requests that cross can not leave two
    # live rows for one pair. Existing rows keep NULL and are untouched (a legacy mutual pair can therefore never make the index fail).
    if "pair_key" not in {c["name"] for c in insp.get_columns("connections")}:
        op.add_column("connections", sa.Column("pair_key", sa.String(32), nullable=True))
    if "uq_connection_pair_live" not in {i["name"] for i in sa.inspect(bind).get_indexes("connections")}:
        where = sa.text("pair_key IS NOT NULL AND status IN ('PENDING','ACCEPTED')")
        op.create_index("uq_connection_pair_live", "connections", ["pair_key"], unique=True, sqlite_where=where, postgresql_where=where)

    have = {c["name"] for c in insp.get_columns("business_needs")}
    for name, type_ in NEED_COLUMNS:
        if name not in have:
            op.add_column("business_needs", sa.Column(name, type_, nullable=True))
    bind.exec_driver_sql("UPDATE business_needs SET published_at = created_at WHERE published_at IS NULL")
    if "uq_need_live_title" not in {i["name"] for i in sa.inspect(bind).get_indexes("business_needs")}:
        where = sa.text("title_hash IS NOT NULL AND status IN ('OPEN','RESOLVED')")      # only rows that carry a hash, so no existing need can make it fail
        op.create_index("uq_need_live_title", "business_needs", ["user_id", "title_hash"], unique=True, sqlite_where=where, postgresql_where=where)

    if "need_help_offers" not in tables:
        op.create_table(
            "need_help_offers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("need_id", sa.String(36), sa.ForeignKey("business_needs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("helper_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="OFFERED"),
            sa.Column("message", sa.Text(), nullable=True),
            _ts("created_at"), _ts("updated_at"), _ts("responded_at", True), _ts("withdrawn_at", True), _ts("outcome_at", True),
            sa.UniqueConstraint("need_id", "helper_user_id", name="uq_need_offer_helper"),
            sa.CheckConstraint(f"status IN ({OFFER_STATUSES})", name="ck_need_offer_status"),
        )
        op.create_index("ix_need_help_offers_need_id", "need_help_offers", ["need_id"])
        op.create_index("ix_need_help_offers_helper_user_id", "need_help_offers", ["helper_user_id"])
        op.create_index("ix_need_help_offers_status", "need_help_offers", ["status"])

    if "community_events" not in tables:
        op.create_table(
            "community_events",
            sa.Column("id", sa.String(36), primary_key=True),
            _ts("created_at"),
            sa.Column("domain", sa.String(12), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("actor_user_id", sa.String(36)), sa.Column("actor_admin_id", sa.String(36)), sa.Column("subject_user_id", sa.String(36)),
            sa.Column("pair_hash", sa.String(32)), sa.Column("connection_id", sa.String(36)), sa.Column("need_id", sa.String(36)), sa.Column("offer_id", sa.String(36)),
            sa.Column("reason_code", sa.String(40)),
            sa.Column("reconnection", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("details", sa.Text()),
            sa.CheckConstraint("domain IN ('CONNECTION','NEED','HELP','SIGNAL')", name="ck_community_event_domain"),
        )
        op.create_index("ix_community_domain_kind_created", "community_events", ["domain", "kind", "created_at"])
        op.create_index("ix_community_actor_created", "community_events", ["actor_user_id", "created_at"])
        op.create_index("ix_community_pair_created", "community_events", ["pair_hash", "created_at"])
        op.create_index("ix_community_need", "community_events", ["need_id"])
        _backfill_connections(bind)

    if bind.dialect.name == "sqlite":
        for name, op_ in (("community_events_no_update", "UPDATE"), ("community_events_no_delete", "DELETE")):
            op.execute(f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {op_} ON community_events BEGIN SELECT RAISE(ABORT, 'community_events is append-only'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE OR REPLACE FUNCTION tgl_community_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'community activity history is append-only'; END; $$ LANGUAGE plpgsql")
        op.execute("DROP TRIGGER IF EXISTS community_events_no_change ON community_events")
        op.execute("CREATE TRIGGER community_events_no_change BEFORE UPDATE OR DELETE ON community_events FOR EACH ROW EXECUTE FUNCTION tgl_community_immutable()")
        op.execute("DROP TRIGGER IF EXISTS community_events_no_truncate ON community_events")
        op.execute("CREATE TRIGGER community_events_no_truncate BEFORE TRUNCATE ON community_events FOR EACH STATEMENT EXECUTE FUNCTION tgl_community_immutable()")
    lock_down(["need_help_offers", "community_events"])


def _pair(a: str, b: str) -> str:
    return hashlib.sha256("|".join(sorted((a, b))).encode()).hexdigest()[:32]


def _backfill_connections(bind) -> None:
    """One REQUESTED event per existing connection row, one ACCEPTED (or DECLINED) event for how it stands, once per pair. All marked BACKFILL."""
    rows = bind.exec_driver_sql("SELECT id, requester_user_id, target_user_id, status, created_at, responded_at FROM connections ORDER BY created_at").fetchall()
    if not rows:
        return
    events = sa.table(
        "community_events", sa.column("id"), sa.column("created_at"), sa.column("domain"), sa.column("kind"), sa.column("actor_user_id"), sa.column("subject_user_id"),
        sa.column("pair_hash"), sa.column("connection_id"), sa.column("reason_code"), sa.column("reconnection"), sa.column("details"))
    details = json.dumps({"backfilled": True})
    out, accepted_pairs = [], set()

    def when(v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace(" ", "T"))
            except ValueError:
                return datetime.now(timezone.utc)
        return v or datetime.now(timezone.utc)

    for cid, req, tgt, st, created, responded in rows:
        ph = _pair(req, tgt)
        base = dict(domain="CONNECTION", actor_user_id=req, subject_user_id=tgt, pair_hash=ph, connection_id=cid, reason_code="BACKFILL", reconnection=False, details=details)
        out.append(dict(base, id=str(uuid.uuid4()), created_at=when(created), kind="REQUESTED"))
        if st == "ACCEPTED" and ph not in accepted_pairs:
            accepted_pairs.add(ph)
            out.append(dict(base, id=str(uuid.uuid4()), created_at=when(responded or created), kind="ACCEPTED", actor_user_id=tgt, subject_user_id=req))
        elif st == "DECLINED":
            out.append(dict(base, id=str(uuid.uuid4()), created_at=when(responded or created), kind="DECLINED", actor_user_id=tgt, subject_user_id=req))
    op.bulk_insert(events, out)


def downgrade() -> None:
    """Refused once real activity has been recorded: the history is the observation record. Backfilled rows alone do not count."""
    import os

    bind = op.get_bind()
    insp = sa.inspect(bind)
    held = 0
    if insp.has_table("community_events"):
        held += bind.exec_driver_sql("SELECT COUNT(*) FROM community_events WHERE reason_code IS NULL OR reason_code <> 'BACKFILL'").scalar()
    if insp.has_table("need_help_offers"):
        held += bind.exec_driver_sql("SELECT COUNT(*) FROM need_help_offers").scalar()
    if held and os.environ.get("TGL_ALLOW_DESTRUCTIVE_DOWNGRADE") != "1":
        raise RuntimeError(f"Refusing to downgrade 0013: it would permanently delete {held} recorded community events and help offers. Export them first, "
                           "then set TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1 only if that is really intended.")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS community_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS community_events_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS community_events_no_change ON community_events")
        op.execute("DROP TRIGGER IF EXISTS community_events_no_truncate ON community_events")
        op.execute("DROP FUNCTION IF EXISTS tgl_community_immutable()")
    for table in ("community_events", "need_help_offers"):
        if insp.has_table(table):
            op.drop_table(table)
    if "uq_connection_pair_live" in {i["name"] for i in insp.get_indexes("connections")}:
        op.drop_index("uq_connection_pair_live", table_name="connections")
    if "pair_key" in {c["name"] for c in insp.get_columns("connections")}:
        with op.batch_alter_table("connections") as batch:
            batch.drop_column("pair_key")
    if "uq_need_live_title" in {i["name"] for i in insp.get_indexes("business_needs")}:
        op.drop_index("uq_need_live_title", table_name="business_needs")
    have = {c["name"] for c in insp.get_columns("business_needs")}
    with op.batch_alter_table("business_needs") as batch:
        for name, _ in NEED_COLUMNS:
            if name in have:
                batch.drop_column(name)
