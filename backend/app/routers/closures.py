"""Two-party meeting confirmation, verified deal closure and deal evidence.

Why this exists: until Phase 0 a single member could move a referral to
MEETING_DONE or BUSINESS_CLOSED alone, and no actual deal value was recorded.
Here:

  * a meeting counts only when BOTH the referrer and the recipient confirm it;
  * a business outcome is a separate record (DealClosure) holding the ACTUAL value
    reported at closure, which the other member confirms, with evidence for larger
    deals and an admin's review above that;
  * every state change is authorised on the server from the session (never from a
    client-supplied id or status), applied with compare-and-set, and audited.

Nothing in this module awards, calculates or applies Growth Points.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit
from .. import verification as v
from ..rewards import hooks as reward_hooks
from ..database import get_db
from ..models import BusinessReferral, DealClosure, DealEvidence, ReferralConfirmation, User, utcnow
from ..ratelimit import enforce
from ..referral_verification import closure_out, meeting_state
from ..schemas_p0 import ClosureConfirm, ClosureCreate, ClosureDispute, ClosureOut, DealRulesOut, MeetingState
from ..security import require_active_networking_member, require_customer_csrf
from ..services import notify
from ..storage import delete_proof, read_proof, save_document
from .customer import _who

router = APIRouter(prefix="/api/v1", tags=["referral-verification"])

_GIVER, _RECEIVER = "giver", "receiver"


# ---------------------------------- helpers ----------------------------------

async def _party(db: AsyncSession, referral_id: str, user: User, lock: bool = False) -> tuple[BusinessReferral, str]:
    """The referral and the caller's role in it. Anyone else gets a 404, the same
    answer as for an id that does not exist, so ids cannot be probed.

    lock=True takes a row lock on the referral (SELECT ... FOR UPDATE; a no-op on SQLite,
    whose writers are already serialised). Every state change goes through it so the two
    members' requests run one after the other: on Postgres, without it, two confirmations
    arriving together each insert their own row, neither sees the other's uncommitted row,
    and the referral never advances."""
    ref = await db.get(BusinessReferral, referral_id, with_for_update=lock, populate_existing=lock)
    if ref is None or user.id not in (ref.giver_user_id, ref.receiver_user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Referral not found")
    return ref, (_GIVER if ref.giver_user_id == user.id else _RECEIVER)


async def meeting_is_verified(db: AsyncSession, referral_id: str) -> bool:
    """True only when BOTH members have a confirmation row. A status alone proves nothing:
    referrals moved to MEETING_DONE by the old one-member flow have no rows."""
    roles = set((await db.execute(select(ReferralConfirmation.role).where(
        ReferralConfirmation.referral_id == referral_id, ReferralConfirmation.kind == v.MEETING))).scalars().all())
    return roles >= {_GIVER, _RECEIVER}


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


async def _live_closure(db: AsyncSession, referral_id: str) -> DealClosure | None:
    return await db.scalar(
        select(DealClosure).where(DealClosure.referral_id == referral_id, DealClosure.status.not_in(tuple(v.CLOSURE_ENDED)))
        .order_by(DealClosure.created_at.desc()).limit(1)
    )


async def _evidence(db: AsyncSession, closure_id: str) -> list[DealEvidence]:
    return list((await db.execute(select(DealEvidence).where(DealEvidence.closure_id == closure_id).order_by(DealEvidence.uploaded_at))).scalars().all())


async def _closure_view(db: AsyncSession, ref: BusinessReferral, closure: DealClosure, me: str) -> ClosureOut:
    return closure_out(ref, closure, await _evidence(db, closure.id), me)


async def _meeting_view(db: AsyncSession, ref: BusinessReferral, me: str) -> MeetingState:
    rows = (await db.execute(select(ReferralConfirmation).where(ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING))).scalars().all()
    return meeting_state(ref, list(rows), me)


async def flag_referral(db: AsyncSession, ref: BusinessReferral, reason: str, actor_id: str | None = None) -> None:
    """Queue a referral for admin review. Further signals are added to the reason (so an admin
    sees them all); it has no other effect."""
    if ref.flagged:
        if ref.flag_reason and reason not in ref.flag_reason:
            ref.flag_reason = f"{ref.flag_reason}; {reason}"[:240]
    else:
        ref.flagged, ref.flag_reason, ref.flagged_at, ref.flagged_by = True, reason[:240], utcnow(), actor_id
    audit.record(db, actor=None, action="referral.flagged", resource_type="referral", resource_id=ref.id, after={"flagged": True}, reason=reason)


async def revert_referral_after_closure_ended(db: AsyncSession, ref: BusinessReferral) -> None:
    """A closure that is rejected, cancelled or invalidated no longer supports BUSINESS_CLOSED."""
    if ref.status in ("BUSINESS_CLOSED", "REVENUE_GENERATED"):
        before = ref.status
        ref.status, ref.business_closed_at, ref.revenue_generated_at, ref.last_action_at = "MEETING_DONE", None, None, utcnow()
        audit.record(db, actor=None, action="referral.status_changed", resource_type="referral", resource_id=ref.id,
                     before={"status": before}, after={"status": "MEETING_DONE"}, reason="The reported business outcome is no longer valid")


@router.get("/deal-rules", response_model=DealRulesOut)
async def deal_rules(_: User = Depends(require_active_networking_member)) -> DealRulesOut:
    """The evidence / review thresholds currently in force, so the screens never hard-code them. They are
    configuration awaiting management confirmation (settings.deal_thresholds_confirmed), not fixed rules."""
    return DealRulesOut(evidence_from_minor=v.evidence_from_minor(), admin_approval_from_minor=v.admin_approval_from_minor())


# ------------------------------ meeting confirmation ------------------------------

@router.post("/referrals/{referral_id}/meeting/confirm", response_model=MeetingState)
async def confirm_meeting(
    referral_id: str,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    enforce(f"meeting-confirm:{user.id}", 60, 3600, "You are confirming too quickly. Please try again later.")
    me_id = user.id  # read now: a rollback below expires the ORM objects
    ref, role = await _party(db, referral_id, user, lock=True)
    mine = await db.scalar(select(ReferralConfirmation.id).where(
        ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING, ReferralConfirmation.user_id == user.id))
    if mine is not None:
        # Idempotent: repeating a confirmation (a double click, a retry, a replayed request) changes nothing -
        # no second row, no second audit entry, no second notification - and answers with the current state.
        return await _meeting_view(db, ref, user.id)
    if ref.status not in v.MEETING_CONFIRMABLE_STATUSES:
        if ref.status in ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED"):
            raise _conflict("This record predates two-member confirmation. TGL will ask you both to confirm the meeting again.")
        raise _conflict("A meeting can be confirmed once the referral has been accepted.")

    now = utcnow()
    prior_status = ref.status  # the bulk UPDATE below refreshes `ref`; the audit entry needs the status as it was
    db.add(ReferralConfirmation(referral_id=ref.id, kind=v.MEETING, user_id=user.id, role=role, confirmed_at=now))
    try:
        await db.flush()  # the unique key still backs the lock: a concurrent repeat from the same member cannot add a second row
    except IntegrityError:
        await db.rollback()
        ref = await db.get(BusinessReferral, referral_id, populate_existing=True)
        return await _meeting_view(db, ref, me_id)
    audit.record(db, actor=user, actor_role=role, action="referral.meeting_confirmed", resource_type="referral", resource_id=ref.id,
                 after={"confirmed_by": role}, metadata={"referral_id": ref.id})

    roles = set((await db.execute(select(ReferralConfirmation.role).where(
        ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING))).scalars().all())
    who = await _who(db, user.id)
    other = ref.receiver_user_id if role == _GIVER else ref.giver_user_id
    subject = ref.prospect_company or ref.prospect_name or ref.business_need
    if roles >= {_GIVER, _RECEIVER}:
        # Compare-and-set: if both members confirm at the same instant, exactly one transaction advances the status.
        res = await db.execute(
            update(BusinessReferral)
            .where(BusinessReferral.id == ref.id, BusinessReferral.status.in_(tuple(v.MEETING_CONFIRMABLE_STATUSES)))
            .values(status="MEETING_DONE", meeting_done_at=now, last_action_at=now, updated_at=now,
                    contacted_at=func.coalesce(BusinessReferral.contacted_at, now))
        )
        if res.rowcount:
            audit.record(db, actor=None, action="referral.status_changed", resource_type="referral", resource_id=ref.id,
                         before={"status": prior_status}, after={"status": "MEETING_DONE"}, reason="Meeting confirmed by both members",
                         metadata={"verification_level": v.L2_BOTH_CONFIRMED})
            for uid in (ref.giver_user_id, ref.receiver_user_id):
                notify(db, uid, "referral_status_changed", "Meeting confirmed by both of you", f"{subject}", "business_referral", ref.id, actor_user_id=user.id)
    else:
        notify(db, other, "referral_status_changed", f"{who} confirmed the meeting", f"{subject}. Please confirm it too if it took place.", "business_referral", ref.id, actor_user_id=user.id)
    await db.commit()
    if roles >= {_GIVER, _RECEIVER}:
        await reward_hooks.referral_changed(ref.id)   # shadow Growth Points (no-op unless shadow mode is on)
    await db.refresh(ref)
    return await _meeting_view(db, ref, user.id)


@router.post("/referrals/{referral_id}/meeting/withdraw", response_model=MeetingState)
async def withdraw_meeting_confirmation(
    referral_id: str,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    """Take back your own confirmation, while the other member has not yet confirmed too."""
    ref, role = await _party(db, referral_id, user, lock=True)
    if ref.status not in v.MEETING_CONFIRMABLE_STATUSES:
        raise _conflict("This meeting has already been confirmed by both members. Use 'Report a problem' instead.")
    mine = await db.scalar(select(ReferralConfirmation).where(
        ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING, ReferralConfirmation.user_id == user.id))
    if mine is None:
        raise _conflict("You have not confirmed this meeting.")
    await db.delete(mine)
    audit.record(db, actor=user, actor_role=role, action="referral.meeting_withdrawn", resource_type="referral", resource_id=ref.id,
                 before={"confirmed_by": role}, metadata={"referral_id": ref.id})
    await db.commit()
    rows = (await db.execute(select(ReferralConfirmation).where(ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING))).scalars().all()
    return meeting_state(ref, list(rows), user.id)


@router.post("/referrals/{referral_id}/meeting/dispute", status_code=status.HTTP_204_NO_CONTENT)
async def dispute_meeting(
    referral_id: str,
    payload: ClosureDispute,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    """After both have confirmed, either can say it was wrong. It queues the referral for an admin."""
    ref, role = await _party(db, referral_id, user, lock=True)
    if ref.status not in ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED"):
        raise _conflict("There is no confirmed meeting to dispute.")
    await flag_referral(db, ref, f"Meeting disputed by the {role}: {payload.reason}", user.id)
    audit.record(db, actor=user, actor_role=role, action="referral.meeting_disputed", resource_type="referral", resource_id=ref.id,
                 reason=payload.reason, metadata={"referral_id": ref.id})
    await db.commit()
    await reward_hooks.referral_changed(ref.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------- deal closure ---------------------------------

@router.get("/referrals/{referral_id}/closure", response_model=ClosureOut | None)
async def get_closure(referral_id: str, user: User = Depends(require_active_networking_member), db: AsyncSession = Depends(get_db)):
    ref, _ = await _party(db, referral_id, user)
    closure = await _live_closure(db, ref.id)
    return await _closure_view(db, ref, closure, user.id) if closure else None


@router.post("/referrals/{referral_id}/closure", response_model=ClosureOut, status_code=status.HTTP_201_CREATED)
async def report_closure(
    referral_id: str,
    payload: ClosureCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    """The RECIPIENT reports that business was closed, with the actual value. The server
    converts to paise, derives the band, and decides what verification is needed."""
    enforce(f"closure-report:{user.id}", 20, 3600, "You are reporting too quickly. Please try again later.")
    ref, role = await _party(db, referral_id, user, lock=True)
    if role != _RECEIVER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the member who received the referral can report the closed business.")
    if ref.status != "MEETING_DONE" or not await meeting_is_verified(db, ref.id):
        raise _conflict("Business can be reported closed after the meeting has been confirmed by both members.")
    if await _live_closure(db, ref.id) is not None:
        raise _conflict("A closed business has already been reported for this referral.")

    minor = payload.actual_value_minor
    now = utcnow()
    closure = DealClosure(
        referral_id=ref.id, reported_by_user_id=user.id, actual_value_minor=minor, currency="INR",
        value_band=v.value_band(minor), evidence_required=v.evidence_required(minor),
        admin_approval_required=v.admin_approval_required(minor), note=payload.note,
        status=v.AWAITING_CONFIRMATION, verification_level=v.L0_SELF_REPORTED,
        confirmed_by_receiver_at=now, submitted_at=now,
    )
    db.add(closure)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _conflict("A closed business has already been reported for this referral.")
    audit.record(db, actor=user, actor_role=role, action="closure.reported", resource_type="deal_closure", resource_id=closure.id,
                 after={"actual_value_minor": minor, "value_band": closure.value_band, "estimated_value_range": ref.value_range,
                        "evidence_required": closure.evidence_required, "admin_approval_required": closure.admin_approval_required,
                        "status": closure.status}, metadata={"referral_id": ref.id})
    # Reported very soon after acceptance is unusual: queue it for a human look (no other effect).
    if ref.accepted_at is not None:
        accepted = ref.accepted_at if ref.accepted_at.tzinfo else ref.accepted_at.replace(tzinfo=now.tzinfo)
        if (now - accepted).total_seconds() < v.quick_close_hours() * 3600:
            await flag_referral(db, ref, f"Closed business reported within {v.quick_close_hours()} hours of the referral being accepted")
    who = await _who(db, user.id)
    notify(db, ref.giver_user_id, "referral_status_changed", f"{who} reported a closed business",
           f"{ref.prospect_company or ref.prospect_name or ref.business_need}. Please review and confirm it.", "business_referral", ref.id, actor_user_id=user.id)
    await db.commit()
    return await _closure_view(db, ref, closure, user.id)


@router.patch("/referrals/{referral_id}/closure", response_model=ClosureOut)
async def edit_closure(
    referral_id: str,
    payload: ClosureCreate,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    """Correct the reported value, only before the referrer has confirmed it. After that it is locked."""
    ref, role = await _party(db, referral_id, user, lock=True)
    closure = await _live_closure(db, ref.id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No closed business has been reported.")
    if closure.reported_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the member who reported it can change it.")
    minor = payload.actual_value_minor
    before = {"actual_value_minor": closure.actual_value_minor, "value_band": closure.value_band, "note": closure.note}
    res = await db.execute(
        update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == v.AWAITING_CONFIRMATION)
        .values(actual_value_minor=minor, value_band=v.value_band(minor), evidence_required=v.evidence_required(minor),
                admin_approval_required=v.admin_approval_required(minor), note=payload.note, updated_at=utcnow())
    )
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This can no longer be changed. The value is locked once the other member has responded.")
    await db.refresh(closure)
    audit.record(db, actor=user, actor_role=role, action="closure.value_changed", resource_type="deal_closure", resource_id=closure.id,
                 before=before, after={"actual_value_minor": minor, "value_band": closure.value_band, "note": closure.note}, metadata={"referral_id": ref.id})
    await db.commit()
    return await _closure_view(db, ref, closure, user.id)


@router.post("/referrals/{referral_id}/closure/confirm", response_model=ClosureOut)
async def confirm_closure(
    referral_id: str,
    payload: ClosureConfirm,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    """The REFERRER confirms the reported outcome. `payload.expected_value_minor` is the value they were
    shown: if it has changed since, the confirmation is refused rather than applied to a number they did not see."""
    ref, role = await _party(db, referral_id, user, lock=True)
    if role != _GIVER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the member who made the referral can confirm the closed business.")
    closure = await _live_closure(db, ref.id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No closed business has been reported.")
    if closure.status != v.AWAITING_CONFIRMATION:
        raise _conflict("This has already been answered.")
    expected_value_minor = payload.expected_value_minor
    if closure.actual_value_minor != expected_value_minor:
        raise _conflict("The reported value has changed. Please review it again before confirming.")

    now = utcnow()
    new_status = v.AWAITING_EVIDENCE if closure.evidence_required else v.VERIFIED
    values = dict(status=new_status, verification_level=v.L2_BOTH_CONFIRMED, confirmed_by_referrer_at=now,
                  confirmed_by_referrer_user_id=user.id, updated_at=now)
    if new_status == v.VERIFIED:
        values["verified_at"] = now  # verified by both members (level 2); no admin step is needed below the evidence threshold
    res = await db.execute(update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == v.AWAITING_CONFIRMATION,
                                                     DealClosure.actual_value_minor == expected_value_minor).values(**values))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This was just changed. Please review it again.")
    await db.refresh(closure)
    audit.record(db, actor=user, actor_role=role, action="closure.confirmed", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": v.AWAITING_CONFIRMATION, "verification_level": v.L0_SELF_REPORTED},
                 after={"status": new_status, "verification_level": v.L2_BOTH_CONFIRMED, "actual_value_minor": closure.actual_value_minor},
                 metadata={"referral_id": ref.id})
    moved = await db.execute(update(BusinessReferral).where(BusinessReferral.id == ref.id, BusinessReferral.status == "MEETING_DONE")
                             .values(status="BUSINESS_CLOSED", business_closed_at=now, last_action_at=now, updated_at=now))
    if moved.rowcount:
        audit.record(db, actor=None, action="referral.status_changed", resource_type="referral", resource_id=ref.id,
                     before={"status": "MEETING_DONE"}, after={"status": "BUSINESS_CLOSED"}, reason="Closed business confirmed by both members")
    who = await _who(db, user.id)
    notify(db, closure.reported_by_user_id, "referral_status_changed", f"{who} confirmed the closed business",
           "Thank you." if new_status == v.VERIFIED else "Please add the supporting evidence so TGL can verify it.", "business_referral", ref.id, actor_user_id=user.id)
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    await db.refresh(ref)
    return await _closure_view(db, ref, closure, user.id)


@router.post("/referrals/{referral_id}/closure/dispute", response_model=ClosureOut)
async def dispute_closure(
    referral_id: str,
    payload: ClosureDispute,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    ref, role = await _party(db, referral_id, user, lock=True)
    closure = await _live_closure(db, ref.id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No closed business has been reported.")
    if closure.status == v.DISPUTED or v.DISPUTED not in v.CLOSURE_TRANSITIONS.get(closure.status, set()):
        raise _conflict("This cannot be disputed in its current state.")
    prior, now = closure.status, utcnow()
    res = await db.execute(update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == prior).values(
        status=v.DISPUTED, status_before_dispute=prior, dispute_reason=payload.reason, disputed_by_user_id=user.id, disputed_at=now, updated_at=now))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This was just changed. Please review it again.")
    await db.refresh(closure)
    audit.record(db, actor=user, actor_role=role, action="closure.disputed", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": prior}, after={"status": v.DISPUTED}, reason=payload.reason, metadata={"referral_id": ref.id})
    await flag_referral(db, ref, f"Closed business disputed by the {role}: {payload.reason}", user.id)
    other = ref.receiver_user_id if role == _GIVER else ref.giver_user_id
    who = await _who(db, user.id)
    notify(db, other, "referral_status_changed", f"{who} disputed the closed business", "TGL will review it.", "business_referral", ref.id, actor_user_id=user.id)
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await _closure_view(db, ref, closure, user.id)


@router.post("/referrals/{referral_id}/closure/cancel", response_model=ClosureOut)
async def cancel_closure(
    referral_id: str,
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    """The reporter withdraws a report nobody has confirmed yet, so it can be reported again correctly."""
    ref, role = await _party(db, referral_id, user, lock=True)
    closure = await _live_closure(db, ref.id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No closed business has been reported.")
    if closure.reported_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the member who reported it can cancel it.")
    res = await db.execute(update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == v.AWAITING_CONFIRMATION)
                           .values(status=v.CANCELLED, updated_at=utcnow()))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This can no longer be cancelled.")
    await db.refresh(closure)
    audit.record(db, actor=user, actor_role=role, action="closure.cancelled", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": v.AWAITING_CONFIRMATION}, after={"status": v.CANCELLED}, metadata={"referral_id": ref.id})
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await _closure_view(db, ref, closure, user.id)


# ----------------------------------- evidence -----------------------------------

@router.post("/referrals/{referral_id}/closure/evidence", response_model=ClosureOut, status_code=status.HTTP_201_CREATED)
async def add_evidence(
    referral_id: str,
    evidence_type: str = Form(...),
    note: str | None = Form(default=None, max_length=240),
    file: UploadFile = File(...),
    user: User = Depends(require_active_networking_member),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    enforce(f"evidence-upload:{user.id}", 30, 3600, "You are uploading too quickly. Please try again later.")
    ref, role = await _party(db, referral_id, user, lock=True)
    kind = (evidence_type or "").upper()
    if kind not in v.EVIDENCE_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Evidence type must be INVOICE, PAYMENT_PROOF or OTHER.")
    closure = await _live_closure(db, ref.id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No closed business has been reported.")
    if closure.status not in (v.AWAITING_EVIDENCE, v.UNDER_REVIEW):
        raise _conflict("Evidence can be added while the closed business is awaiting evidence or under review. It cannot be changed once verified.")
    existing = await _evidence(db, closure.id)
    if len([e for e in existing if e.status != v.EVIDENCE_REJECTED]) >= v.MAX_EVIDENCE_PER_CLOSURE:
        raise _conflict(f"A closed business can have at most {v.MAX_EVIDENCE_PER_CLOSURE} evidence files.")

    name, mime, size, digest = await save_document(file, "Evidence")
    try:
        row = DealEvidence(closure_id=closure.id, evidence_type=kind, storage_name=name, mime=mime, size_bytes=size, sha256=digest,
                           note=(note or "").strip() or None, uploaded_by_user_id=user.id, status=v.EVIDENCE_PENDING)
        db.add(row)
        await db.flush()
        reused = await db.scalar(select(func.count(DealEvidence.id)).where(DealEvidence.sha256 == digest, DealEvidence.closure_id != closure.id))
        audit.record(db, actor=user, actor_role=role, action="evidence.uploaded", resource_type="deal_evidence", resource_id=row.id,
                     after={"evidence_type": kind, "mime": mime, "size_bytes": size, "status": "PENDING"},
                     metadata={"referral_id": ref.id, "closure_id": closure.id, "same_file_in_other_closures": int(reused or 0)})
        if reused:
            await flag_referral(db, ref, "The same evidence file is attached to another closed business")
        if closure.status == v.AWAITING_EVIDENCE:
            res = await db.execute(update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == v.AWAITING_EVIDENCE)
                                   .values(status=v.UNDER_REVIEW, updated_at=utcnow()))
            if res.rowcount:
                audit.record(db, actor=None, action="closure.status_changed", resource_type="deal_closure", resource_id=closure.id,
                             before={"status": v.AWAITING_EVIDENCE}, after={"status": v.UNDER_REVIEW}, reason="Evidence submitted", metadata={"referral_id": ref.id})
        await db.commit()
    except Exception:
        # The file is stored before the row is committed: if anything fails in between, do not leave an unreachable file behind.
        await db.rollback()
        await delete_proof(name)
        raise
    await db.refresh(closure)
    return await _closure_view(db, ref, closure, user.id)


@router.get("/referrals/{referral_id}/closure/evidence/{evidence_id}/file")
async def evidence_file(
    referral_id: str,
    evidence_id: str,
    user: User = Depends(require_active_networking_member),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream a file to one of the two members. Never a public URL: the storage name is not exposed."""
    ref, _ = await _party(db, referral_id, user)
    row = await db.get(DealEvidence, evidence_id)
    closure = await db.get(DealClosure, row.closure_id) if row else None
    if row is None or closure is None or closure.referral_id != ref.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    data = await read_proof(row.storage_name)
    return Response(content=data, media_type=row.mime, headers={
        "Content-Disposition": f'inline; filename="evidence-{row.id[:8]}"', "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; object-src 'none'; sandbox", "Cache-Control": "private, no-store",
    })
