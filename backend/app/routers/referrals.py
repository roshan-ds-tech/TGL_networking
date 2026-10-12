"""Referrals: a member (referrer, from the session) refers an outside
prospect to another TGL member (recipient).

Authorization model
  * The referrer is always the authenticated user; the payload cannot name one.
  * The recipient must be an active Networking member other than the referrer.
  * A referral — and the prospect's contact details in it — is visible only to
    its two participants; anyone else gets a 404 (not 403, so ids can't be
    probed). Status changes are role-checked and server-side only.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit, outbox
from .. import verification as ver
from ..rewards import hooks as reward_hooks
from ..referral_verification import extras_for, load_for_referrals
from ..config import settings
from ..database import get_db
from ..email_service import referral_received_email
from ..models import BusinessReferral, DealClosure, NetworkingProfile, PersonalProfile, User, Business, utcnow
from ..ratelimit import enforce
from ..schemas import (
    NotificationActor,
    ReferralCreate,
    ReferralDetail,
    ReferralOut,
    ReferralSummary,
    ReferralTransition,
)
from ..security import active_member_clause, require_active_networking_member, require_customer_csrf
from ..services import notify
from .customer import _people, _who

router = APIRouter(prefix="/api/v1", tags=["referrals"])

LIVE = ("GIVEN", "ACCEPTED", "CONTACTED", "MEETING_DONE", "BUSINESS_CLOSED")
IN_PROGRESS = ("GIVEN", "ACCEPTED", "CONTACTED", "MEETING_DONE")
CONVERTED = ("BUSINESS_CLOSED", "REVENUE_GENERATED")
CLOSED = ("DECLINED", "CANCELLED", "CLOSED")
VIEW_STATUSES = {"in_progress": IN_PROGRESS, "converted": CONVERTED, "closed": CLOSED}

# Who may make each move: R = recipient, G = referrer (giver), B = either.
_R, _G, _B = "receiver", "giver", "both"
#
# MEETING_DONE and BUSINESS_CLOSED are deliberately NOT here. A meeting counts only
# once BOTH members confirm it (routers/closures.py), and a business outcome only
# through a verified deal closure. Neither can be set by one member's PATCH.
TRANSITIONS: dict[str, dict[str, str]] = {
    "GIVEN": {"ACCEPTED": _R, "DECLINED": _R, "CANCELLED": _G},
    "ACCEPTED": {"CONTACTED": _R, "CLOSED": _R, "CANCELLED": _G},
    "CONTACTED": {"CLOSED": _R, "CANCELLED": _G},
    "MEETING_DONE": {"CLOSED": _R, "CANCELLED": _G},
    "BUSINESS_CLOSED": {"REVENUE_GENERATED": _B},
    "REVENUE_GENERATED": {},
    "DECLINED": {},
    "CANCELLED": {},
    "CLOSED": {},
}
_STAMP = {
    "ACCEPTED": "accepted_at", "CONTACTED": "contacted_at", "MEETING_DONE": "meeting_done_at",
    "BUSINESS_CLOSED": "business_closed_at", "REVENUE_GENERATED": "revenue_generated_at",
    "CANCELLED": "cancelled_at", "DECLINED": "declined_at", "CLOSED": "closed_at",
}
URGENCY_LABEL = {"HOT": "Hot — within a week", "WARM": "Warm — within a month", "DEVELOPING": "Developing — longer term", "UNSURE": "Not sure"}
INTRO_LABEL = {
    "EMAIL": "Introduction by email", "CALL": "Call being arranged", "SHARE_DETAILS": "Contact details shared",
    "ALREADY_KNOWS": "Prospect already knows you", "OTHER": "Other",
}


def _role(ref: BusinessReferral, user_id: str) -> str | None:
    if ref.giver_user_id == user_id:
        return _G
    if ref.receiver_user_id == user_id:
        return _R
    return None


def _allowed(ref: BusinessReferral, role: str | None) -> list[str]:
    return [s for s, who in TRANSITIONS.get(ref.status, {}).items() if role and who in (role, _B)]


def _actions_for(ref: BusinessReferral, role: str | None, extras: dict | None) -> list[str]:
    """The moves to offer. With a reported closed business, closing or cancelling the referral
    is held back until it is resolved, and revenue can only be logged once it is verified."""
    allowed = _allowed(ref, role)
    closure = (extras or {}).get("closure")
    if closure:
        allowed = [a for a in allowed if a not in ("CLOSED", "CANCELLED")]
    if "REVENUE_GENERATED" in allowed and not (closure and closure.get("status") == "VERIFIED"):
        allowed = [a for a in allowed if a != "REVENUE_GENERATED"]
    return allowed


def derive_quality(p: ReferralCreate) -> str:
    """How much introduction work the referrer did, inferred from what they
    supplied — not asked as a technical 'level'."""
    if p.intro_method == "CALL" and p.intro_call_preference:
        return "MEETING_ARRANGED"
    if p.intro_method in ("EMAIL", "CALL"):
        return "DIRECT_INTRO"
    context = len(p.opportunity_description) >= 80 and bool(p.prospect_company or p.prospect_email or p.note)
    return "WARM_REFERRAL" if context else "CONTACT_ONLY"


def _headline(text: str, limit: int = 160) -> str:
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    return one[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _out(ref: BusinessReferral, people: dict[str, NotificationActor], me: str, detail: bool = False, extras: dict | None = None):
    giver, receiver = people.get(ref.giver_user_id), people.get(ref.receiver_user_id)
    role = _role(ref, me)
    data = ReferralOut.model_validate(ref).model_dump()
    data.update(
        my_role=role,
        giver_name=giver.name if giver else None,
        giver_business=giver.business_name if giver else None,
        giver_photo_url=giver.photo_url if giver else None,
        receiver_name=receiver.name if receiver else None,
        receiver_business=receiver.business_name if receiver else None,
        receiver_photo_url=receiver.photo_url if receiver else None,
        allowed_actions=_actions_for(ref, role, extras),
        **(extras or {}),
    )
    if not detail:
        return ReferralOut(**data)
    extra = ReferralDetail.model_validate(ref).model_dump(include=set(ReferralDetail.model_fields) - set(ReferralOut.model_fields))
    return ReferralDetail(**data, **extra)


async def _get_visible(db: AsyncSession, referral_id: str, user: User) -> BusinessReferral:
    ref = await db.get(BusinessReferral, referral_id)
    if ref is None or user.id not in (ref.giver_user_id, ref.receiver_user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Referral not found")
    return ref


async def _eligible_recipient(db: AsyncSession, user_id: str, referrer_id: str) -> bool:
    """Same rule as the member search, so what you can pick is what you can send to."""
    if user_id == referrer_id:
        return False
    row = await db.scalar(
        select(NetworkingProfile.id)
        .join(Business, Business.id == NetworkingProfile.business_id)
        .join(PersonalProfile, PersonalProfile.user_id == NetworkingProfile.user_id)
        .join(User, User.id == NetworkingProfile.user_id)
        .where(
            NetworkingProfile.user_id == user_id,
            User.is_active.is_(True),
            await active_member_clause(db, NetworkingProfile.user_id),
        )
        .limit(1)
    )
    return row is not None


def _conflict(code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, {"code": code, "message": message, **extra})


async def _check_duplicates(db: AsyncSession, user: User, p: ReferralCreate) -> None:
    """Hard duplicate: I already have a live referral of this prospect to this
    member. Soft duplicate: the same prospect is already live with another
    member of mine, or this company with this member — allowed after the
    referrer confirms. Only the referrer's own referrals are ever revealed."""
    mine_live = (BusinessReferral.giver_user_id == user.id, BusinessReferral.status.in_(LIVE))
    same_prospect = [BusinessReferral.prospect_phone == p.prospect_phone]
    if p.prospect_email:
        same_prospect.append(func.lower(BusinessReferral.prospect_email) == str(p.prospect_email).lower())

    hard = await db.scalar(
        select(BusinessReferral).where(*mine_live, BusinessReferral.receiver_user_id == p.receiver_user_id, or_(*same_prospect)).limit(1)
    )
    if hard is not None:
        raise _conflict(
            "duplicate_referral",
            "You have already referred this prospect to this member, and that referral is still open.",
            existing_referral_id=hard.id,
        )
    if p.confirm_duplicate:
        return
    soft_filters = [BusinessReferral.receiver_user_id != p.receiver_user_id, or_(*same_prospect)]
    clauses = [and_(*soft_filters)]
    if p.prospect_company:
        clauses.append(and_(*[
            BusinessReferral.receiver_user_id == p.receiver_user_id,
            func.lower(BusinessReferral.prospect_company) == p.prospect_company.lower(),
        ]))
    rows = (await db.execute(
        select(BusinessReferral).where(*mine_live, or_(*clauses)).order_by(BusinessReferral.created_at.desc()).limit(3)
    )).scalars().all()
    if rows:
        people = await _people(db, {r.receiver_user_id for r in rows})
        raise _conflict(
            "possible_duplicate",
            "This looks similar to an existing referral.",
            matches=[
                {
                    "id": r.id,
                    "receiver_name": getattr(people.get(r.receiver_user_id), "name", None),
                    "prospect_name": r.prospect_name,
                    "prospect_company": r.prospect_company,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        )


@router.post("/referrals", response_model=ReferralDetail, status_code=status.HTTP_201_CREATED)
async def create_referral(
    payload: ReferralCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> ReferralDetail:
    enforce(f"referral-create:{user.id}", 30, 3600, "You are sending referrals too quickly. Please try again later.")
    if payload.receiver_user_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot refer someone to yourself.")
    # One answer for "no such account" and "not an eligible member", so the
    # endpoint can't be used to find out which ids are accounts.
    if not await _eligible_recipient(db, payload.receiver_user_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That member can't receive referrals.")
    receiver = await db.get(User, payload.receiver_user_id)

    await _check_duplicates(db, user, payload)

    now = utcnow()
    ref = BusinessReferral(
        giver_user_id=user.id,
        receiver_user_id=receiver.id,
        business_need=_headline(payload.opportunity_description, 160),
        opportunity_description=payload.opportunity_description,
        note=payload.note,
        prospect_name=payload.prospect_name,
        prospect_phone=payload.prospect_phone,
        prospect_email=str(payload.prospect_email).lower() if payload.prospect_email else None,
        prospect_company=payload.prospect_company,
        prospect_role=payload.prospect_role,
        prospect_location=payload.prospect_location,
        preferred_contact_method=payload.preferred_contact_method,
        relationship=payload.relationship,
        relationship_other=payload.relationship_other if payload.relationship == "OTHER" else None,
        category=payload.category,
        urgency=payload.urgency,
        value_range=payload.value_range,
        intro_method=payload.intro_method,
        intro_call_preference=payload.intro_call_preference if payload.intro_method == "CALL" else None,
        contact_permission=payload.contact_permission,
        consent_confirmed_at=now,
        quality=derive_quality(payload),
        status="GIVEN",
        last_action_at=now,
    )
    db.add(ref)
    try:
        await db.flush()  # assigns ref.id; the partial unique index catches a concurrent twin here
    except IntegrityError:
        await db.rollback()
        raise _conflict("duplicate_referral", "You have already referred this prospect to this member, and that referral is still open.")

    audit.record(
        db, actor=user, actor_role="giver", action="referral.created", resource_type="referral", resource_id=ref.id,
        after={"status": "GIVEN", "receiver_user_id": receiver.id, "estimated_value_range": ref.value_range, "quality": ref.quality},
    )
    people = await _people(db, {user.id, receiver.id})
    me = people.get(user.id)
    prospect_label = ref.prospect_company or ref.prospect_name
    who = await _who(db, user.id)
    notify(
        db, receiver.id, "referral_received", f"{who} sent you a referral",
        f"{prospect_label} · {URGENCY_LABEL[ref.urgency].split(' —')[0]} · {_headline(ref.business_need, 110)}",
        "business_referral", ref.id, actor_user_id=user.id,
    )
    # Same transaction as the referral; the background worker sends it later
    # (retrying on failure), so a slow or down mail provider can't fail this.
    origin = settings.public_origins[0] if settings.public_origins else settings.public_origin.rstrip("/")
    outbox.enqueue(
        db, "referral_received", receiver.email,
        referral_received_email(
            referrer=me.name if me else "A TGL member",
            referrer_business=me.business_name if me else None,
            prospect=prospect_label,
            urgency=URGENCY_LABEL[ref.urgency],
            intro=INTRO_LABEL[ref.intro_method],
            summary=_headline(ref.business_need, 200),
            link=f"{origin}/app/networking/referrals",
        ),
    )
    await db.commit()
    outbox.kick()
    return _out(ref, people, user.id, detail=True, extras=extras_for(ref, user.id, {}, {}, {}))


@router.get("/referrals/summary", response_model=ReferralSummary)
async def referral_summary(
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> ReferralSummary:
    # Grouped by status only: Postgres rejects GROUP BY on a bound-parameter expression
    # (the two `giver == :id` placeholders are different parameters to it), so the
    # sent/received split is a conditional sum rather than a second grouping column.
    rows = (await db.execute(
        select(BusinessReferral.status, func.sum(case((BusinessReferral.giver_user_id == user.id, 1), else_=0)), func.count())
        .where(or_(BusinessReferral.giver_user_id == user.id, BusinessReferral.receiver_user_id == user.id))
        .group_by(BusinessReferral.status)
    )).all()
    by_status: dict[str, int] = {}
    sent = received = awaiting = 0
    for st, given, n in rows:
        given = int(given or 0)
        by_status[st] = n
        sent += given
        received += n - given
        if st == "GIVEN":
            awaiting += n - given
    count = lambda group: sum(by_status.get(s, 0) for s in group)  # noqa: E731
    return ReferralSummary(
        total=sent + received, awaiting_response=awaiting, sent=sent, received=received, by_status=by_status,
        in_progress=count(IN_PROGRESS), converted=count(CONVERTED), closed=count(CLOSED),
    )


@router.get("/referrals", response_model=list[ReferralOut])
async def list_referrals(
    view: Literal["all", "sent", "received", "in_progress", "converted", "closed"] = "all",
    stage: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=20, ge=1, le=51),
    offset: int = Query(default=0, ge=0, le=100_000),
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> list[ReferralOut]:
    mine = or_(BusinessReferral.giver_user_id == user.id, BusinessReferral.receiver_user_id == user.id)
    filters = [mine]
    if view == "sent":
        filters = [BusinessReferral.giver_user_id == user.id]
    elif view == "received":
        filters = [BusinessReferral.receiver_user_id == user.id]
    elif view in VIEW_STATUSES:
        filters.append(BusinessReferral.status.in_(VIEW_STATUSES[view]))
    if stage:
        filters.append(BusinessReferral.status == stage.upper())
    refs = (await db.execute(
        select(BusinessReferral).where(*filters)
        .order_by(BusinessReferral.updated_at.desc(), BusinessReferral.id)
        .limit(limit).offset(offset)
    )).scalars().all()
    people = await _people(db, {uid for r in refs for uid in (r.giver_user_id, r.receiver_user_id)})
    conf, closures, evidence = await load_for_referrals(db, list(refs))
    return [_out(r, people, user.id, extras=extras_for(r, user.id, conf, closures, evidence)) for r in refs]


@router.get("/referrals/{referral_id}", response_model=ReferralDetail)
async def get_referral(
    referral_id: str,
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> ReferralDetail:
    ref = await _get_visible(db, referral_id, user)
    people = await _people(db, {ref.giver_user_id, ref.receiver_user_id})
    conf, closures, evidence = await load_for_referrals(db, [ref], with_evidence=True)
    return _out(ref, people, user.id, detail=True, extras=extras_for(ref, user.id, conf, closures, evidence))


@router.patch("/referrals/{referral_id}", response_model=ReferralDetail)
async def transition_referral(
    referral_id: str,
    payload: ReferralTransition,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
) -> ReferralDetail:
    ref = await _get_visible(db, referral_id, user)
    next_status = payload.status.upper()
    rule = TRANSITIONS.get(ref.status, {}).get(next_status)
    if rule is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid referral transition.")
    role = _role(ref, user.id)
    if rule not in (role, _B):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the other member can make that change.")

    live_closure = await db.scalar(
        select(DealClosure).where(DealClosure.referral_id == ref.id, DealClosure.status.not_in(tuple(ver.CLOSURE_ENDED))).limit(1)
    )
    if next_status in ("CLOSED", "CANCELLED") and live_closure is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A business outcome has been reported for this referral. Resolve it first.")
    if next_status == "REVENUE_GENERATED" and (live_closure is None or live_closure.status != ver.VERIFIED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Revenue can be logged once the closed business has been verified.")

    now = utcnow()
    values = {"status": next_status, _STAMP[next_status]: now, "last_action_at": now, "updated_at": now}
    if next_status in ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED") and ref.contacted_at is None:
        values["contacted_at"] = now  # a meeting implies the prospect was contacted
    # Compare-and-set on the status we validated against: two simultaneous
    # updates can't both succeed from the same starting point.
    res = await db.execute(
        update(BusinessReferral).where(BusinessReferral.id == ref.id, BusinessReferral.status == ref.status).values(**values)
    )
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("stale_status", "This referral was just updated. Refresh and try again.")

    audit.record(
        db, actor=user, actor_role=role, action="referral.status_changed", resource_type="referral", resource_id=ref.id,
        before={"status": ref.status}, after={"status": next_status},
    )
    other = ref.giver_user_id if role == _R else ref.receiver_user_id
    who = await _who(db, user.id)
    subject = ref.prospect_company or ref.prospect_name or ref.business_need
    if next_status == "ACCEPTED":
        notify(db, ref.giver_user_id, "referral_accepted", f"{who} accepted your referral", f"{subject} — {_headline(ref.business_need, 110)}", "business_referral", ref.id, actor_user_id=user.id)
    else:
        notify(db, other, "referral_status_changed", f"{who} marked a referral as {next_status.replace('_', ' ').lower()}", f"{subject} — {_headline(ref.business_need, 110)}", "business_referral", ref.id, actor_user_id=user.id)
    await db.commit()
    await reward_hooks.referral_changed(ref.id)        # shadow Growth Points: the verified state changed (no-op unless shadow mode is on)
    await db.refresh(ref)
    people = await _people(db, {ref.giver_user_id, ref.receiver_user_id})
    conf, closures, evidence = await load_for_referrals(db, [ref], with_evidence=True)
    return _out(ref, people, user.id, detail=True, extras=extras_for(ref, user.id, conf, closures, evidence))
