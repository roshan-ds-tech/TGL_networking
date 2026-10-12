"""Phase A: reliable RECORDING of connections, business needs and help offers. Facts only.

Nothing in this module awards, requests, caps or reverses a Growth Point, creates a ledger row, or touches an invoice, a payment or a price.
It must not import the rewards package: the point of Phase A is to start collecting genuine behaviour BEFORE any reward policy is approved
(docs/GROWTH_POINTS_BUSINESS_POLICY_PROPOSAL.md is a draft and is not approved).

What it provides
  * an append-only event history (`community_events`) written in the SAME transaction as the state change it describes, so a failed request
    leaves neither a half-changed state nor an orphan event, and a repeated request writes no second event;
  * the need lifecycle (validation, duplicate detection, a tracked monthly-quality field, cancel / resolve / admin remove and restore);
  * the help-offer lifecycle (offer, accept, decline, withdraw, confirm helpful / not helpful, resolve with attribution);
  * abuse SIGNALS (recorded, never acted on automatically);
  * a read-only, aggregate observation report that excludes synthetic demo members.

Deliberately NOT here: phone, IP, device or relationship-cluster analysis (the data model and privacy policy do not support it).
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, case, event, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import demo
from .models import BusinessNeed, CommunityEvent, Connection, NeedHelpOffer, User, utcnow

# ---------------------------------------------------------------- observational parameters
# These are NOT reward rules and NOT approved policy. They are measurement thresholds and technical safety caps, and every one can change
# without a rule version because none of them awards anything.
NEED_MIN_DESCRIPTION = 80            # characters, after trimming, before a need is published (proposed in the draft, applied as validation)
NEED_NEAR_DUPLICATE = 0.85           # token-set overlap (Jaccard) with the member's own recent need that counts as "the same need again"
NEED_DUPLICATE_WINDOW_DAYS = 90
NEED_DAILY_PUBLISH_CAP = 10          # technical anti-spam cap per member per 24 hours, counting cancelled and removed posts too
TRACKED_MONTHLY_QUALIFYING_LIMIT = 2 # the PROPOSED limit of qualifying posts a month. TRACKED ONLY: a third post is still published
OFFER_DAILY_CAP = 40                 # technical cap on help offers per member per 24 hours
CONNECTION_BURST_SIGNAL = 20         # connection requests in 24 h that raise a (non-punitive) signal
HELP_BURST_SIGNAL = 15
MAX_OFFER_MESSAGE = 1000
_IST = timezone(timedelta(minutes=330))          # business time, like the rewards calendar, but defined here so this module does not import it

NEED_STATUSES = ("OPEN", "RESOLVED", "CANCELLED", "REMOVED")
OFFER_TRANSITIONS: dict[tuple[str, str], tuple[str, str]] = {
    # (current status, action) -> (new status, who may do it)
    ("OFFERED", "accept"): ("ACCEPTED", "poster"),
    ("OFFERED", "decline"): ("DECLINED", "poster"),
    ("OFFERED", "withdraw"): ("WITHDRAWN", "helper"),
    ("ACCEPTED", "confirm_helpful"): ("CONFIRMED_HELPFUL", "poster"),
    ("ACCEPTED", "not_helpful"): ("NOT_HELPFUL", "poster"),
    ("ACCEPTED", "withdraw"): ("WITHDRAWN", "helper"),
}


# ---------------------------------------------------------------- the append-only guard and writer
@event.listens_for(CommunityEvent, "before_update")
@event.listens_for(CommunityEvent, "before_delete")
def _refuse_change(mapper, connection, target):  # pragma: no cover - exercised by tests
    raise RuntimeError("community_events is append-only")


def month_key(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_IST).strftime("%Y-%m")


def aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def pair_hash(a: str, b: str) -> str:
    """Order-independent, one-way: a pair can be followed through history without listing the two members."""
    return hashlib.sha256("|".join(sorted((a, b))).encode()).hexdigest()[:32]


def record(db: AsyncSession, domain: str, kind: str, *, actor: str | None = None, admin: str | None = None, subject: str | None = None,
           pair: str | None = None, connection_id: str | None = None, need_id: str | None = None, offer_id: str | None = None,
           reason: str | None = None, reconnection: bool = False, details: dict | None = None, at: datetime | None = None) -> CommunityEvent:
    """Add one event to the CALLER'S session: it commits, or rolls back, with the change it describes."""
    row = CommunityEvent(
        domain=domain, kind=kind, actor_user_id=actor, actor_admin_id=admin, subject_user_id=subject, pair_hash=pair, connection_id=connection_id,
        need_id=need_id, offer_id=offer_id, reason_code=reason, reconnection=reconnection,
        details=json.dumps(details, sort_keys=True, default=str) if details else None,
    )
    if at is not None:
        row.created_at = at
    db.add(row)
    return row


async def lock_users(db: AsyncSession, ids) -> None:
    """Serialise lifecycle changes for these members: one row lock each, always in the same order, so two requests on the same pair or the same
    member can not interleave (a no-op on SQLite, whose writers are already serialised). Held until the caller commits."""
    wanted = sorted({i for i in ids if i})
    if wanted:
        await db.execute(select(User.id).where(User.id.in_(wanted)).order_by(User.id).with_for_update())


async def _signal(db: AsyncSession, kind: str, *, actor: str | None, subject: str | None = None, pair: str | None = None, need_id: str | None = None,
                  details: dict | None = None, within_hours: int = 24) -> None:
    """Record a review signal once per actor / pair / need per window. A signal NEVER blocks, reduces or punishes anything."""
    q = select(func.count(CommunityEvent.id)).where(CommunityEvent.domain == "SIGNAL", CommunityEvent.kind == kind,
                                                      CommunityEvent.created_at >= utcnow() - timedelta(hours=within_hours))
    for col, val in ((CommunityEvent.actor_user_id, actor), (CommunityEvent.pair_hash, pair), (CommunityEvent.need_id, need_id)):
        q = q.where(col == val) if val is not None else q
    if not await db.scalar(q):
        record(db, "SIGNAL", kind, actor=actor, subject=subject, pair=pair, need_id=need_id, details=details)


# ================================================================================================ connections
async def move_connection(db: AsyncSession, connection_id: str, allowed_from: tuple[str, ...], to_status: str) -> bool:
    """Compare-and-set the status of a connection row: True only if THIS request made the change. Two requests that answer the same connection at
    once can not both succeed (and so can not both write the same history event), on any database, with or without row locks."""
    res = await db.execute(update(Connection).where(Connection.id == connection_id, Connection.status.in_(allowed_from)).values(status=to_status, responded_at=utcnow()))
    return res.rowcount == 1


async def connection_event(db: AsyncSession, kind: str, a: str, b: str, *, actor: str, connection_id: str | None = None, extra: dict | None = None) -> CommunityEvent:
    """REQUESTED / ACCEPTED / DECLINED / WITHDRAWN / REMOVED for the pair (a, b), done by `actor`. `reconnection` is true when the pair was connected before.
    One query reads both what the history says about this pair and (for a request) how many this member made in the last day."""
    pair = pair_hash(a, b)
    E = CommunityEvent
    since = utcnow() - timedelta(hours=24)
    before, recent = (await db.execute(select(
        func.coalesce(func.sum(case((and_(E.kind == "ACCEPTED", E.pair_hash == pair), 1), else_=0)), 0),
        func.coalesce(func.sum(case((and_(E.kind == "REQUESTED", E.actor_user_id == actor, E.created_at >= since), 1), else_=0)), 0),
    ).where(E.domain == "CONNECTION", or_(E.pair_hash == pair, E.actor_user_id == actor)))).one()
    before, recent = int(before), int(recent) + 1
    other = b if actor == a else a
    row = record(db, "CONNECTION", kind, actor=actor, subject=other, pair=pair, connection_id=connection_id, reconnection=before > 0,
                 details={"connected_before": before, **(extra or {})})
    if kind == "REQUESTED":
        if recent >= CONNECTION_BURST_SIGNAL:
            await _signal(db, "CONNECTION_BURST", actor=actor, details={"requests_24h": recent})
        if before >= 2:
            await _signal(db, "RECONNECT_CYCLING", actor=actor, pair=pair, details={"connected_before": before}, within_hours=24 * 30)
    return row


# ================================================================================================ needs
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalise(text: str | None) -> str:
    return _SPACE.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


def text_hash(text: str | None) -> str:
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:32]


def _tokens(text: str | None) -> set[str]:
    return {w for w in normalise(text).split() if len(w) >= 3}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class NeedRejected(Exception):
    def __init__(self, code: str, message: str, http_status: int):
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status


async def publish_need(db: AsyncSession, user: User, business_id: str, title: str, category: str, description: str | None, now: datetime | None = None) -> BusinessNeed:
    """Validate and publish a need, recording the facts. Raises NeedRejected (the caller records the rejection and commits it).
    Concurrent publications by one member are serialised by the member row lock, so the daily cap and the monthly count can not be bypassed."""
    now = now or utcnow()
    await lock_users(db, [user.id])
    desc = (description or "").strip()
    if len(desc) < NEED_MIN_DESCRIPTION:
        raise NeedRejected("TOO_SHORT_DESCRIPTION", f"Describe what you need in at least {NEED_MIN_DESCRIPTION} characters (scope, timeline, budget or location). You have written {len(desc)}.",
                           status.HTTP_422_UNPROCESSABLE_ENTITY)
    mine_all = (await db.execute(select(BusinessNeed).where(BusinessNeed.user_id == user.id, func.coalesce(BusinessNeed.published_at, BusinessNeed.created_at) >= now - timedelta(days=NEED_DUPLICATE_WINDOW_DAYS))
                                 .order_by(BusinessNeed.created_at.desc()).limit(500))).scalars().all()
    published_24h = sum(1 for n in mine_all if aware(n.published_at or n.created_at) >= now - timedelta(hours=24))     # cancelled and removed posts still count
    if published_24h >= NEED_DAILY_PUBLISH_CAP:
        raise NeedRejected("DAILY_CAP", "You have published a lot of needs today. Please try again tomorrow.", status.HTTP_429_TOO_MANY_REQUESTS)
    t_hash, d_hash = text_hash(title), text_hash(desc)
    mine_tokens = _tokens(f"{title} {desc}")
    for n in mine_all:      # includes cancelled and removed posts: deleting and re-posting does not make a need new
        if (n.title_hash or text_hash(n.title)) == t_hash or (n.description_hash or text_hash(n.description)) == d_hash:
            raise NeedRejected("DUPLICATE_RECENT", "You already posted this need recently. Update the existing one, or wait before posting it again.", status.HTTP_409_CONFLICT)
        if jaccard(mine_tokens, _tokens(f"{n.title} {n.description}")) >= NEED_NEAR_DUPLICATE:
            raise NeedRejected("NEAR_DUPLICATE_RECENT", "This is almost the same as a need you posted recently.", status.HTTP_409_CONFLICT)
    other = await db.scalar(select(func.count(BusinessNeed.id)).where(
        BusinessNeed.user_id != user.id, or_(BusinessNeed.title_hash == t_hash, BusinessNeed.description_hash == d_hash),
        func.coalesce(BusinessNeed.published_at, BusinessNeed.created_at) >= now - timedelta(days=NEED_DUPLICATE_WINDOW_DAYS)))
    month = month_key(now)
    qualifying = sum(1 for n in mine_all if n.publish_month_key == month and n.qualifies_for_future_reward)
    qualifies = qualifying < TRACKED_MONTHLY_QUALIFYING_LIMIT
    need = BusinessNeed(user_id=user.id, business_id=business_id, title=title, category=category, description=desc, status="OPEN", published_at=now,
                        title_hash=t_hash, description_hash=d_hash, publish_month_key=month, qualifies_for_future_reward=qualifies,
                        quality_note=None if qualifies else "MONTHLY_LIMIT")
    db.add(need)
    try:
        await db.flush()
    except IntegrityError:        # an identical live need from this member was stored by a concurrent request
        await db.rollback()
        raise NeedRejected("DUPLICATE_RECENT", "You already posted this need recently. Update the existing one, or wait before posting it again.", status.HTTP_409_CONFLICT)
    record(db, "NEED", "PUBLISHED", actor=user.id, need_id=need.id, reason=None if qualifies else "MONTHLY_LIMIT",
           details={"qualifies": qualifies, "qualifying_this_month_before": qualifying, "description_chars": len(desc), "month": month})
    if other:
        await _signal(db, "NEED_CROSS_MEMBER_DUPLICATE", actor=user.id, need_id=need.id, details={"other_members": int(other)}, within_hours=24 * 30)
    return need


async def need_for_update(db: AsyncSession, need_id: str) -> BusinessNeed:
    need = (await db.execute(select(BusinessNeed).where(BusinessNeed.id == need_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if need is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Need not found")
    return need


async def move_need(db: AsyncSession, need_id: str, allowed_from: tuple[str, ...], **values) -> bool:
    """Compare-and-set the status of a need (values must include `status`): True only if THIS request made the change, so two requests that race
    (cancel and resolve, two removals) can not both succeed or both write a history event."""
    res = await db.execute(update(BusinessNeed).where(BusinessNeed.id == need_id, BusinessNeed.status.in_(allowed_from)).values(**values))
    return res.rowcount == 1


# ================================================================================================ help offers
async def create_offer(db: AsyncSession, need: BusinessNeed, helper: User, message: str | None) -> tuple[NeedHelpOffer, bool]:
    """(offer, created). A second click, a retry or a concurrent request finds the existing offer and creates nothing."""
    need_id, helper_id, poster_id = need.id, helper.id, need.user_id          # plain values: after a rollback the ORM objects are expired
    await lock_users(db, [helper_id])                  # one helper's clicks are serialised, so the checks below and the insert can not interleave
    existing = await db.scalar(select(NeedHelpOffer).where(NeedHelpOffer.need_id == need_id, NeedHelpOffer.helper_user_id == helper_id))
    if existing is not None:
        return existing, False
    since = utcnow() - timedelta(hours=24)
    made = int(await db.scalar(select(func.count(NeedHelpOffer.id)).where(NeedHelpOffer.helper_user_id == helper.id, NeedHelpOffer.created_at >= since)) or 0)
    if made >= OFFER_DAILY_CAP:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You have offered help a lot today. Please try again tomorrow.")
    offer = NeedHelpOffer(need_id=need.id, helper_user_id=helper.id, status="OFFERED", message=(message or "").strip()[:MAX_OFFER_MESSAGE] or None)
    db.add(offer)
    try:
        await db.flush()                               # the unique (need, helper) constraint is the last line of defence against a twin
    except IntegrityError:
        await db.rollback()
        return await db.scalar(select(NeedHelpOffer).where(NeedHelpOffer.need_id == need_id, NeedHelpOffer.helper_user_id == helper_id)), False
    pair = pair_hash(helper_id, poster_id)
    record(db, "HELP", "OFFERED", actor=helper_id, subject=poster_id, pair=pair, need_id=need_id, offer_id=offer.id, details={"message_chars": len(offer.message or "")})
    if made + 1 >= HELP_BURST_SIGNAL:
        await _signal(db, "HELP_BURST", actor=helper_id, details={"offers_24h": made + 1})
    repeats = int(await db.scalar(select(func.count(NeedHelpOffer.id)).join(BusinessNeed, BusinessNeed.id == NeedHelpOffer.need_id).where(
        NeedHelpOffer.helper_user_id == helper_id, BusinessNeed.user_id == poster_id, NeedHelpOffer.created_at >= utcnow() - timedelta(days=30))) or 0)
    if repeats >= 3:
        await _signal(db, "HELP_PAIR_REPEAT", actor=helper_id, subject=poster_id, pair=pair, details={"offers_30d": repeats}, within_hours=24 * 30)
    return offer, True


async def transition_offer(db: AsyncSession, offer_id: str, action: str, user: User) -> NeedHelpOffer:
    """Compare-and-set on the offer's current status, under a row lock. Only the named party may make each move."""
    offer = (await db.execute(select(NeedHelpOffer).where(NeedHelpOffer.id == offer_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    need = await db.get(BusinessNeed, offer.need_id) if offer else None
    if offer is None or need is None or user.id not in (offer.helper_user_id, need.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")                 # no hint that it exists
    rule = OFFER_TRANSITIONS.get((offer.status, action))
    if rule is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"An offer that is {offer.status.lower().replace('_', ' ')} can not be '{action}'.")
    new_status, who = rule
    is_poster = user.id == need.user_id
    if (who == "poster") != is_poster:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the member who posted the need can do that." if who == "poster" else "Only the member who offered can do that.")
    open_needed = action in ("accept", "decline", "withdraw")
    if (open_needed and need.status != "OPEN") or (not open_needed and need.status not in ("OPEN", "RESOLVED")):
        raise HTTPException(status.HTTP_409_CONFLICT, "This need is no longer open.")
    now = utcnow()
    stamp = {"accept": "responded_at", "decline": "responded_at", "withdraw": "withdrawn_at"}.get(action, "outcome_at")
    moved = await db.execute(update(NeedHelpOffer).where(NeedHelpOffer.id == offer.id, NeedHelpOffer.status == offer.status).values(**{"status": new_status, stamp: now, "updated_at": now}))
    if moved.rowcount != 1:                                  # a concurrent request moved it first (the row lock is a no-op on SQLite)
        raise HTTPException(status.HTTP_409_CONFLICT, "This offer was just updated. Refresh and try again.")
    await db.refresh(offer)
    pair = pair_hash(offer.helper_user_id, need.user_id)
    record(db, "HELP", {"accept": "ACCEPTED", "decline": "DECLINED", "withdraw": "WITHDRAWN", "confirm_helpful": "CONFIRMED_HELPFUL", "not_helpful": "NOT_HELPFUL"}[action],
           actor=user.id, subject=(need.user_id if not is_poster else offer.helper_user_id), pair=pair, need_id=need.id, offer_id=offer.id)
    if new_status == "CONFIRMED_HELPFUL":
        back = int(await db.scalar(select(func.count(NeedHelpOffer.id)).join(BusinessNeed, BusinessNeed.id == NeedHelpOffer.need_id).where(
            NeedHelpOffer.helper_user_id == need.user_id, BusinessNeed.user_id == offer.helper_user_id, NeedHelpOffer.status == "CONFIRMED_HELPFUL",
            NeedHelpOffer.outcome_at >= now - timedelta(days=60))) or 0)
        if back:
            await _signal(db, "HELP_RECIPROCAL", actor=user.id, subject=offer.helper_user_id, pair=pair, need_id=need.id, details={"reverse_confirmed_60d": back}, within_hours=24 * 30)
    return offer


# ================================================================================================ the read-only observation report
def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


async def report(db: AsyncSession, since: datetime | None = None) -> dict:
    """Aggregate, read-only and anonymous: counts and times, never an id, a name or a message. SYNTHETIC members and their events are excluded
    from every figure (the reserved demo e-mail domain, exactly as Gate A does) and counted separately. Backfilled history (events written when the
    feature was installed, from rows that already existed) is reported separately and is NOT observation. Raw activity is kept apart from outcomes:
    an offer is an offer, not help."""
    synthetic_ids = select(User.id).where(demo.synthetic_clause())
    E = CommunityEvent
    genuine = and_(or_(E.actor_user_id.is_(None), E.actor_user_id.not_in(synthetic_ids)), or_(E.subject_user_id.is_(None), E.subject_user_id.not_in(synthetic_ids)),
                   or_(E.reason_code.is_(None), E.reason_code != "BACKFILL"))
    window = [E.created_at >= since] if since is not None else []

    async def counts(domain: str, **extra) -> dict[str, int]:
        q = select(E.kind, func.count(E.id)).where(E.domain == domain, genuine, *window).group_by(E.kind)
        return {k: int(n) for k, n in (await db.execute(q)).all()}

    conn_c, need_c, help_c, sig_c = await counts("CONNECTION"), await counts("NEED"), await counts("HELP"), await counts("SIGNAL")
    reconnect_req = int(await db.scalar(select(func.count(E.id)).where(E.domain == "CONNECTION", E.kind == "REQUESTED", E.reconnection.is_(True), genuine, *window)) or 0)
    reconnect_acc = int(await db.scalar(select(func.count(E.id)).where(E.domain == "CONNECTION", E.kind == "ACCEPTED", E.reconnection.is_(True), genuine, *window)) or 0)
    rejected = {k: int(n) for k, n in (await db.execute(select(E.reason_code, func.count(E.id)).where(E.domain == "NEED", E.kind == "REJECTED", genuine, *window).group_by(E.reason_code))).all()}
    qualifying = int(await db.scalar(select(func.count(E.id)).where(E.domain == "NEED", E.kind == "PUBLISHED", E.reason_code.is_(None), genuine, *window)) or 0)
    over_limit = int(await db.scalar(select(func.count(E.id)).where(E.domain == "NEED", E.kind == "PUBLISHED", E.reason_code == "MONTHLY_LIMIT", genuine, *window)) or 0)

    # --- timings and outcomes from the state tables (genuine posters and helpers only)
    N, O = BusinessNeed, NeedHelpOffer
    needs = (await db.execute(select(N.id, N.status, N.published_at, N.created_at, N.resolved_at, N.resolved_offer_id).where(N.published_at.is_not(None), N.user_id.not_in(synthetic_ids))
                              .order_by(N.published_at.desc()).limit(5000))).all()
    offers = (await db.execute(select(O.need_id, O.status, O.created_at, O.outcome_at, O.helper_user_id).join(N, N.id == O.need_id).where(
        O.helper_user_id.not_in(synthetic_ids), N.user_id.not_in(synthetic_ids)))).all()
    by_need: dict[str, list] = {}
    for o in offers:
        by_need.setdefault(o.need_id, []).append(o)
    to_first_offer, to_first_helpful, to_resolution = [], [], []
    resolved_with_attribution = resolved_unattributed = needs_with_offers = 0
    for n in needs:
        pub = aware(n.published_at)
        offs = by_need.get(n.id, [])
        if offs:
            needs_with_offers += 1
            to_first_offer.append((min(aware(o.created_at) for o in offs) - pub).total_seconds() / 3600)
        helpful = [aware(o.outcome_at) for o in offs if o.status == "CONFIRMED_HELPFUL" and o.outcome_at]
        if helpful:
            to_first_helpful.append((min(helpful) - pub).total_seconds() / 3600)
        if n.status == "RESOLVED" and n.resolved_at:
            to_resolution.append((aware(n.resolved_at) - pub).total_seconds() / 3600)
            resolved_with_attribution += bool(n.resolved_offer_id)
            resolved_unattributed += not n.resolved_offer_id
    # --- repeated and reciprocal help between the same two members (counts of pairs, never who)
    helpful_pairs: dict[tuple, int] = {}
    rows = (await db.execute(select(O.helper_user_id, N.user_id).join(N, N.id == O.need_id).where(O.status == "CONFIRMED_HELPFUL", O.helper_user_id.not_in(synthetic_ids), N.user_id.not_in(synthetic_ids)))).all()
    for helper, poster in rows:
        helpful_pairs[(helper, poster)] = helpful_pairs.get((helper, poster), 0) + 1
    repeated = sum(1 for v in helpful_pairs.values() if v >= 2)
    reciprocal = sum(1 for (a, b) in helpful_pairs if (b, a) in helpful_pairs and a < b)
    pairs_connected = int(await db.scalar(select(func.count(Connection.id)).where(Connection.status == "ACCEPTED", Connection.requester_user_id.not_in(synthetic_ids),
                                                                                   Connection.target_user_id.not_in(synthetic_ids))) or 0)
    synthetic_events = int(await db.scalar(select(func.count(E.id)).where(or_(E.actor_user_id.in_(synthetic_ids), E.subject_user_id.in_(synthetic_ids)))) or 0)
    backfilled = int(await db.scalar(select(func.count(E.id)).where(E.reason_code == "BACKFILL")) or 0)
    span = (await db.execute(select(func.min(E.created_at), func.max(E.created_at), func.count(E.id)).where(genuine))).one()
    active_members = int(await db.scalar(select(func.count(func.distinct(E.actor_user_id))).where(genuine, E.actor_user_id.is_not(None))) or 0)
    still_qualifying = int(await db.scalar(select(func.count(N.id)).where(N.published_at.is_not(None), N.qualifies_for_future_reward.is_(True), N.status != "REMOVED", N.user_id.not_in(synthetic_ids))) or 0)

    def rate(n: int, d: int) -> float | None:
        return round(100 * n / d, 1) if d else None

    return {
        "scope": "GENUINE members only. Synthetic demo members and backfilled history are excluded. Aggregates only: no names, ids or messages. Records activity; awards nothing.",
        "window_since": since,
        "observation": {"genuine_events_recorded": int(span[2] or 0), "genuine_members_with_activity": active_members, "first_event_at": span[0], "last_event_at": span[1],
                        "synthetic_events_excluded": synthetic_events, "backfilled_history_events_excluded": backfilled,
                        "scope": "This block is all-time and ignores the period filter.",
                        "baseline": "Connections that existed when this feature was installed were backfilled once and are excluded. Pairs connected and removed before then are unknown, so a first connection recorded here may in fact be a reconnection.",
                        "note": "An observation period starts only when these features run in an authorised environment with real member activity. This report does not claim it has."},
        "connections": {
            "raw_activity": {"requested": conn_c.get("REQUESTED", 0), "declined": conn_c.get("DECLINED", 0), "withdrawn": conn_c.get("WITHDRAWN", 0), "removed": conn_c.get("REMOVED", 0),
                             "reconnection_requests": reconnect_req},
            "outcomes": {"accepted": conn_c.get("ACCEPTED", 0), "reconnections_accepted": reconnect_acc, "acceptance_rate_percent": rate(conn_c.get("ACCEPTED", 0), conn_c.get("REQUESTED", 0)),
                         "pairs_connected_now": pairs_connected},
        },
        "needs": {
            "raw_activity": {"published": need_c.get("PUBLISHED", 0), "rejected": sum(rejected.values()), "rejected_by_reason": rejected, "cancelled": need_c.get("CANCELLED", 0),
                             "removed_by_moderators": need_c.get("REMOVED", 0), "restored": need_c.get("RESTORED", 0)},
            "quality_tracking": {"published_within_proposed_monthly_limit": qualifying, "published_over_proposed_monthly_limit": over_limit, "within_limit_and_not_removed_now": still_qualifying,
                                 "note": "Tracked policy field only. No post is blocked or rewarded because of it."},
            "outcomes": {"resolved": need_c.get("RESOLVED", 0), "resolved_with_a_credited_helper": resolved_with_attribution, "resolved_without_credit": resolved_unattributed,
                         "needs_that_received_an_offer": needs_with_offers},
        },
        "help_offers": {
            "raw_activity": {"offers": help_c.get("OFFERED", 0), "withdrawn": help_c.get("WITHDRAWN", 0), "declined": help_c.get("DECLINED", 0)},
            "progress": {"accepted": help_c.get("ACCEPTED", 0)},
            "outcomes": {"confirmed_helpful": help_c.get("CONFIRMED_HELPFUL", 0), "not_helpful": help_c.get("NOT_HELPFUL", 0),
                         "note": "An offer is not help. Only a poster's 'helpful' confirmation counts as a useful contribution."},
        },
        "timing_hours_median": {"publication_to_first_offer": _median(to_first_offer), "publication_to_first_helpful_confirmation": _median(to_first_helpful),
                                "publication_to_resolution": _median(to_resolution), "sample_sizes": {"first_offer": len(to_first_offer), "first_helpful": len(to_first_helpful), "resolution": len(to_resolution)}},
        "repeat_and_reciprocal": {"pairs_with_two_or_more_helpful_confirmations": repeated, "pairs_helping_each_other": reciprocal, "signals_recorded": sig_c},
    }
