"""Admin referral management: investigate referrals, review evidence, verify or reject deal closures.

Every mutating action requires a reason, is authorised by the admin session
(+ CSRF), is a compare-and-set on the current status, and writes an audit entry.
Nothing here creates, adjusts or reverses Growth Points: they do not exist yet.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .. import audit
from .. import verification as v
from ..rewards import hooks as reward_hooks
from ..database import get_db
from ..models import (
    Admin, AuditLog, BusinessReferral, DealClosure, DealEvidence, PersonalProfile, ReferralConfirmation, User, utcnow,
)
from ..schemas_p0 import (
    AdminClosureOut, AdminDisputeResolution, AdminEvidenceOut, AdminFlagIn, AdminMeetingConfirmation, AdminNoteIn, AdminPerson,
    AdminReferralDetail, AdminReferralItem, AdminReferralPage, AdminStatusCorrection, AdminTimelineEntry, ReasonIn,
)
from ..security import get_current_admin, require_csrf
from ..services import notify
from ..storage import read_proof
from .closures import revert_referral_after_closure_ended

router = APIRouter(prefix="/api/admin", tags=["admin-referrals"])

REFERRAL_STATUSES = ("GIVEN", "ACCEPTED", "CONTACTED", "MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED", "DECLINED", "CANCELLED", "CLOSED")
# An admin may correct a status, but never INTO an outcome that only the two-party workflow can
# produce: MEETING_DONE needs both members' confirmations and BUSINESS_CLOSED / REVENUE_GENERATED
# need a verified closure. An admin can move a referral OUT of those stages (an error correction),
# which is also the "legacy" path: a referral advanced by the old one-member flow carries no
# confirmations, so the only fix is back to CONTACTED, from where both members confirm properly.
CORRECTABLE = frozenset({"GIVEN", "ACCEPTED", "CONTACTED", "DECLINED", "CANCELLED", "CLOSED"})
_BACKWARD = frozenset({"GIVEN", "ACCEPTED", "CONTACTED"})  # earlier stages: the meeting is no longer confirmed
_ADVANCED = ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED")
_STAMP = {"ACCEPTED": "accepted_at", "CONTACTED": "contacted_at", "DECLINED": "declined_at", "CANCELLED": "cancelled_at", "CLOSED": "closed_at"}


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)


def _person(user: User | None, name: str | None) -> AdminPerson:
    return AdminPerson(id=user.id if user else "", email=user.email if user else "", name=name or (user.full_name if user else None))


def _day(value: date, end: bool) -> datetime:
    return datetime.combine(value, time.max if end else time.min, tzinfo=timezone.utc)


async def _referral(db: AsyncSession, referral_id: str, lock: bool = False) -> BusinessReferral:
    """lock=True: SELECT ... FOR UPDATE, so an admin action and the members' own requests on the
    same referral run one after the other (a no-op on SQLite)."""
    ref = await db.get(BusinessReferral, referral_id, with_for_update=lock, populate_existing=lock)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Referral not found")
    return ref


async def _live_closure(db: AsyncSession, referral_id: str) -> DealClosure:
    c = await db.scalar(select(DealClosure).where(DealClosure.referral_id == referral_id, DealClosure.status.not_in(tuple(v.CLOSURE_ENDED))).limit(1))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This referral has no open closed-business record.")
    return c


async def _move(db: AsyncSession, closure: DealClosure, allowed_from: set[str], new_status: str, **values) -> str:
    """Compare-and-set a closure status, honouring the transition table. Returns the previous status."""
    prior = closure.status
    if prior not in allowed_from or new_status not in v.CLOSURE_TRANSITIONS.get(prior, set()):
        raise _conflict(f"A {v.CLOSURE_LABEL.get(prior, prior).lower()} closed business cannot be moved to {new_status.lower().replace('_', ' ')}.")
    res = await db.execute(update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == prior).values(status=new_status, updated_at=utcnow(), **values))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This was just updated by someone else. Refresh and try again.")
    await db.refresh(closure)
    return prior


def _evidence_admin(e: DealEvidence, names: dict[str, str], reused: int) -> AdminEvidenceOut:
    return AdminEvidenceOut(
        id=e.id, evidence_type=e.evidence_type, mime=e.mime, size_bytes=e.size_bytes, note=e.note, uploaded_by=names.get(e.uploaded_by_user_id, e.uploaded_by_user_id),
        uploaded_at=e.uploaded_at, status=e.status, verified_at=e.verified_at, verified_by=names.get(e.verified_by_admin_id or "", e.verified_by_admin_id),
        rejection_reason=e.rejection_reason, reused_in_other_closures=reused,
    )


def _closure_admin(c: DealClosure, evidence: list[DealEvidence], names: dict[str, str], reuse: dict[str, int]) -> AdminClosureOut:
    return AdminClosureOut(
        id=c.id, status=c.status, status_label=v.CLOSURE_LABEL.get(c.status, c.status), verification_level=c.verification_level,
        verification_label=v.LEVEL_LABEL[c.verification_level], actual_value_minor=c.actual_value_minor, currency=c.currency, value_band=c.value_band,
        value_band_label=v.BAND_LABEL[c.value_band], evidence_required=c.evidence_required, admin_approval_required=c.admin_approval_required, note=c.note,
        reported_by=names.get(c.reported_by_user_id, c.reported_by_user_id), confirmed_by_receiver_at=c.confirmed_by_receiver_at,
        confirmed_by_referrer_at=c.confirmed_by_referrer_at, submitted_at=c.submitted_at, verified_at=c.verified_at,
        verified_by=names.get(c.verified_by_admin_id or "", c.verified_by_admin_id), rejection_reason=c.rejection_reason, dispute_reason=c.dispute_reason,
        disputed_by=names.get(c.disputed_by_user_id or "", c.disputed_by_user_id), disputed_at=c.disputed_at, invalidated_reason=c.invalidated_reason,
        evidence=[_evidence_admin(e, names, reuse.get(e.sha256, 0)) for e in evidence],
    )


# ------------------------------------ list ------------------------------------

@router.get("/referrals", response_model=AdminReferralPage)
async def list_referrals(
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    date_from: date | None = None,
    date_to: date | None = None,
    referrer: str | None = Query(default=None, max_length=120),
    recipient: str | None = Query(default=None, max_length=120),
    closure_status: str | None = Query(default=None, max_length=24),
    verification_level: int | None = Query(default=None, ge=0, le=4),
    deal_band: str | None = Query(default=None, max_length=12),
    flagged: bool | None = None,
    legacy_unverified: bool | None = Query(default=None, description="Advanced past 'accepted' by the old one-member flow, with no two-party confirmation"),
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=25, ge=1, le=100),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    G, R = aliased(User), aliased(User)
    GP, RP = aliased(PersonalProfile), aliased(PersonalProfile)
    live = and_(DealClosure.referral_id == BusinessReferral.id, DealClosure.status.not_in(tuple(v.CLOSURE_ENDED)))
    conf = (select(func.count(ReferralConfirmation.id)).where(ReferralConfirmation.referral_id == BusinessReferral.id, ReferralConfirmation.kind == v.MEETING)
            .correlate(BusinessReferral).scalar_subquery())
    base = (
        select(BusinessReferral, G, R, GP.full_name, RP.full_name, DealClosure, conf)
        .join(G, G.id == BusinessReferral.giver_user_id).join(R, R.id == BusinessReferral.receiver_user_id)
        .outerjoin(GP, GP.user_id == G.id).outerjoin(RP, RP.user_id == R.id)
        .outerjoin(DealClosure, live)
    )
    if status_filter:
        base = base.where(BusinessReferral.status == status_filter.upper())
    if date_from:
        base = base.where(BusinessReferral.created_at >= _day(date_from, False))
    if date_to:
        base = base.where(BusinessReferral.created_at <= _day(date_to, True))
    for term, user_alias, prof in ((referrer, G, GP), (recipient, R, RP)):
        if term:
            like = f"%{term.strip().lower()}%"
            base = base.where(or_(func.lower(user_alias.email).like(like), func.lower(func.coalesce(prof.full_name, user_alias.full_name, "")).like(like)))
    if closure_status:
        base = base.where(DealClosure.id.is_(None)) if closure_status.upper() == "NONE" else base.where(DealClosure.status == closure_status.upper())
    if verification_level is not None:
        base = base.where(DealClosure.verification_level == verification_level)
    if deal_band:
        base = base.where(DealClosure.value_band == deal_band.upper())
    if flagged is not None:
        base = base.where(BusinessReferral.flagged.is_(flagged))
    if legacy_unverified is not None:
        legacy = and_(BusinessReferral.status.in_(_ADVANCED), conf < 2)
        base = base.where(legacy if legacy_unverified else ~legacy)
    total = await db.scalar(select(func.count()).select_from(base.with_only_columns(BusinessReferral.id).subquery())) or 0
    rows = (await db.execute(base.order_by(BusinessReferral.created_at.desc(), BusinessReferral.id).limit(page_size).offset((page - 1) * page_size))).all()
    items = [
        AdminReferralItem(
            id=r.id, status=r.status, created_at=r.created_at, updated_at=r.updated_at, referrer=_person(g, gn), recipient=_person(rc, rn),
            prospect_company=r.prospect_company, prospect_name=r.prospect_name, estimated_value_range=r.value_range, meeting_confirmations=int(n or 0),
            closure_status=c.status if c else None, closure_level=c.verification_level if c else None, closure_band=c.value_band if c else None,
            actual_value_minor=c.actual_value_minor if c else None, flagged=bool(r.flagged), flag_reason=r.flag_reason,
            legacy_unverified=r.status in _ADVANCED and int(n or 0) < 2,
        )
        for r, g, rc, gn, rn, c, n in rows
    ]
    return AdminReferralPage(items=items, total=total, page=page, page_size=page_size, pages=max(1, math.ceil(total / page_size)))


# ------------------------------------ detail ------------------------------------

@router.get("/referrals/{referral_id}", response_model=AdminReferralDetail)
async def referral_detail(referral_id: str, _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    closures = list((await db.execute(select(DealClosure).where(DealClosure.referral_id == ref.id).order_by(DealClosure.created_at.desc()))).scalars().all())
    evidence = list((await db.execute(select(DealEvidence).where(DealEvidence.closure_id.in_([c.id for c in closures])).order_by(DealEvidence.uploaded_at))).scalars().all()) if closures else []
    confirmations = list((await db.execute(select(ReferralConfirmation).where(ReferralConfirmation.referral_id == ref.id).order_by(ReferralConfirmation.confirmed_at))).scalars().all())
    resource_ids = [ref.id] + [c.id for c in closures] + [e.id for e in evidence]
    audit_rows = list((await db.execute(select(AuditLog).where(AuditLog.resource_id.in_(resource_ids)).order_by(AuditLog.created_at, AuditLog.id).limit(300))).scalars().all())

    user_ids = {ref.giver_user_id, ref.receiver_user_id} | {c.user_id for c in confirmations} | {e.uploaded_by_user_id for e in evidence} | {c.reported_by_user_id for c in closures}
    user_ids |= {c.disputed_by_user_id for c in closures if c.disputed_by_user_id} | {a.actor_id for a in audit_rows if a.actor_type == "USER" and a.actor_id}
    admin_ids = {c.verified_by_admin_id for c in closures if c.verified_by_admin_id} | {e.verified_by_admin_id for e in evidence if e.verified_by_admin_id} | {a.actor_id for a in audit_rows if a.actor_type == "ADMIN" and a.actor_id}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()}
    profiles = dict((await db.execute(select(PersonalProfile.user_id, PersonalProfile.full_name).where(PersonalProfile.user_id.in_(user_ids)))).all())
    admins = {a.id: a.email for a in (await db.execute(select(Admin).where(Admin.id.in_(admin_ids)))).scalars().all()} if admin_ids else {}
    names = {uid: (profiles.get(uid) or u.full_name or u.email) for uid, u in users.items()} | admins

    hashes = {e.sha256 for e in evidence}
    reuse: dict[str, int] = {}
    if hashes:
        for sha, n in (await db.execute(select(DealEvidence.sha256, func.count(DealEvidence.id)).where(DealEvidence.sha256.in_(hashes), DealEvidence.closure_id.not_in([c.id for c in closures])).group_by(DealEvidence.sha256))).all():
            reuse[sha] = n
    by_closure: dict[str, list[DealEvidence]] = {}
    for e in evidence:
        by_closure.setdefault(e.closure_id, []).append(e)
    import json
    timeline = [
        AdminTimelineEntry(
            at=a.created_at, actor_type=a.actor_type, actor=names.get(a.actor_id or "", a.actor_id), actor_role=a.actor_role, action=a.action,
            resource_type=a.resource_type, reason=a.reason, before=json.loads(a.before_json) if a.before_json else None, after=json.loads(a.after_json) if a.after_json else None,
        )
        for a in audit_rows
    ]
    live = next((c for c in closures if c.status not in v.CLOSURE_ENDED), None)
    g, r = users.get(ref.giver_user_id), users.get(ref.receiver_user_id)
    return AdminReferralDetail(
        id=ref.id, status=ref.status, created_at=ref.created_at, updated_at=ref.updated_at, accepted_at=ref.accepted_at, contacted_at=ref.contacted_at,
        meeting_done_at=ref.meeting_done_at, business_closed_at=ref.business_closed_at, referrer=_person(g, names.get(ref.giver_user_id)),
        recipient=_person(r, names.get(ref.receiver_user_id)), prospect_name=ref.prospect_name, prospect_company=ref.prospect_company,
        opportunity=ref.opportunity_description or ref.business_need, estimated_value_range=ref.value_range, quality=ref.quality,
        flagged=bool(ref.flagged), flag_reason=ref.flag_reason,
        meeting_verified=len({c.role for c in confirmations} & {"giver", "receiver"}) == 2,
        legacy_unverified=ref.status in _ADVANCED and len({c.role for c in confirmations} & {"giver", "receiver"}) < 2,
        meeting_confirmations=[AdminMeetingConfirmation(user=_person(users.get(c.user_id), names.get(c.user_id)), role=c.role, confirmed_at=c.confirmed_at) for c in confirmations],
        closure=_closure_admin(live, by_closure.get(live.id, []), names, reuse) if live else None,
        past_closures=[_closure_admin(c, by_closure.get(c.id, []), names, reuse) for c in closures if c is not live],
        timeline=timeline,
    )


@router.get("/referrals/{referral_id}/closure/evidence/{evidence_id}/file")
async def admin_evidence_file(referral_id: str, evidence_id: str, _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    row = await db.get(DealEvidence, evidence_id)
    closure = await db.get(DealClosure, row.closure_id) if row else None
    if row is None or closure is None or closure.referral_id != referral_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    data = await read_proof(row.storage_name)
    return Response(content=data, media_type=row.mime, headers={
        "Content-Disposition": f'inline; filename="evidence-{row.id[:8]}"', "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; object-src 'none'; sandbox", "Cache-Control": "private, no-store",
    })


# ----------------------------------- evidence -----------------------------------

async def _evidence_of(db: AsyncSession, referral_id: str, evidence_id: str) -> tuple[DealEvidence, DealClosure]:
    row = await db.get(DealEvidence, evidence_id)
    closure = await db.get(DealClosure, row.closure_id) if row else None
    if row is None or closure is None or closure.referral_id != referral_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    return row, closure


@router.post("/referrals/{referral_id}/closure/evidence/{evidence_id}/verify", response_model=AdminReferralDetail)
async def verify_evidence(referral_id: str, evidence_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    row, closure = await _evidence_of(db, referral_id, evidence_id)
    if closure.status != v.UNDER_REVIEW:
        raise _conflict("Evidence can be verified while the closed business is under review.")
    now = utcnow()
    res = await db.execute(update(DealEvidence).where(DealEvidence.id == row.id, DealEvidence.status == v.EVIDENCE_PENDING)
                           .values(status=v.EVIDENCE_VERIFIED, verified_by_admin_id=admin.id, verified_at=now, rejection_reason=None))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This evidence has already been reviewed.")
    audit.record(db, actor=admin, action="evidence.verified", resource_type="deal_evidence", resource_id=row.id,
                 before={"status": "PENDING"}, after={"status": "VERIFIED"}, reason=payload.reason, metadata={"referral_id": ref.id, "closure_id": closure.id})
    # Below the admin-approval threshold, verified evidence completes the verification (level 3).
    if not closure.admin_approval_required:
        prior = await _move(db, closure, {v.UNDER_REVIEW}, v.VERIFIED, verification_level=v.L3_EVIDENCE, verified_at=now, verified_by_admin_id=admin.id)
        audit.record(db, actor=admin, action="closure.verified", resource_type="deal_closure", resource_id=closure.id,
                     before={"status": prior, "verification_level": v.L2_BOTH_CONFIRMED}, after={"status": v.VERIFIED, "verification_level": v.L3_EVIDENCE},
                     reason=payload.reason, metadata={"referral_id": ref.id})
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await referral_detail(referral_id, admin, db)


@router.post("/referrals/{referral_id}/closure/evidence/{evidence_id}/reject", response_model=AdminReferralDetail)
async def reject_evidence(referral_id: str, evidence_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    row, closure = await _evidence_of(db, referral_id, evidence_id)
    if closure.status != v.UNDER_REVIEW:
        raise _conflict("Evidence can be rejected while the closed business is under review.")
    now = utcnow()
    res = await db.execute(update(DealEvidence).where(DealEvidence.id == row.id, DealEvidence.status == v.EVIDENCE_PENDING)
                           .values(status=v.EVIDENCE_REJECTED, verified_by_admin_id=admin.id, verified_at=now, rejection_reason=payload.reason))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This evidence has already been reviewed.")
    audit.record(db, actor=admin, action="evidence.rejected", resource_type="deal_evidence", resource_id=row.id,
                 before={"status": "PENDING"}, after={"status": "REJECTED"}, reason=payload.reason, metadata={"referral_id": ref.id, "closure_id": closure.id})
    remaining = await db.scalar(select(func.count(DealEvidence.id)).where(DealEvidence.closure_id == closure.id, DealEvidence.status.in_((v.EVIDENCE_PENDING, v.EVIDENCE_VERIFIED))))
    if not remaining:
        prior = await _move(db, closure, {v.UNDER_REVIEW}, v.AWAITING_EVIDENCE)
        audit.record(db, actor=admin, action="closure.status_changed", resource_type="deal_closure", resource_id=closure.id,
                     before={"status": prior}, after={"status": v.AWAITING_EVIDENCE}, reason="All evidence was rejected", metadata={"referral_id": ref.id})
    notify(db, row.uploaded_by_user_id, "referral_status_changed", "Your evidence was not accepted", f"{payload.reason}. Please upload a corrected document.", "business_referral", ref.id)
    await db.commit()
    return await referral_detail(referral_id, admin, db)


# ----------------------------------- closure -----------------------------------

def _notify_both(db: AsyncSession, ref: BusinessReferral, title: str, body: str) -> None:
    for uid in (ref.giver_user_id, ref.receiver_user_id):
        notify(db, uid, "referral_status_changed", title, body, "business_referral", ref.id)


@router.post("/referrals/{referral_id}/closure/verify", response_model=AdminReferralDetail)
async def verify_closure(referral_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    closure = await _live_closure(db, referral_id)
    now = utcnow()
    if closure.status == v.UNDER_REVIEW:
        verified = await db.scalar(select(func.count(DealEvidence.id)).where(DealEvidence.closure_id == closure.id, DealEvidence.status == v.EVIDENCE_VERIFIED))
        if closure.evidence_required and not verified:
            raise _conflict("Verify at least one piece of evidence first.")
        prior = await _move(db, closure, {v.UNDER_REVIEW}, v.VERIFIED, verification_level=v.L4_ADMIN, verified_at=now, verified_by_admin_id=admin.id)
        before_level = v.L2_BOTH_CONFIRMED
    elif closure.status == v.VERIFIED and closure.verification_level < v.L4_ADMIN:
        res = await db.execute(update(DealClosure).where(DealClosure.id == closure.id, DealClosure.status == v.VERIFIED, DealClosure.verification_level < v.L4_ADMIN)
                               .values(verification_level=v.L4_ADMIN, verified_at=now, verified_by_admin_id=admin.id, updated_at=now))
        if res.rowcount == 0:
            await db.rollback()
            raise _conflict("This was just updated by someone else. Refresh and try again.")
        prior, before_level = v.VERIFIED, closure.verification_level
    else:
        raise _conflict("This closed business is not ready for admin verification.")
    audit.record(db, actor=admin, action="closure.verified", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": prior, "verification_level": before_level}, after={"status": v.VERIFIED, "verification_level": v.L4_ADMIN},
                 reason=payload.reason, metadata={"referral_id": ref.id})
    _notify_both(db, ref, "The closed business was verified by TGL", ref.prospect_company or ref.prospect_name or ref.business_need)
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await referral_detail(referral_id, admin, db)


@router.post("/referrals/{referral_id}/closure/reject", response_model=AdminReferralDetail)
async def reject_closure(referral_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    closure = await _live_closure(db, referral_id)
    prior = await _move(db, closure, {v.UNDER_REVIEW, v.DISPUTED, v.AWAITING_EVIDENCE, v.AWAITING_CONFIRMATION}, v.REJECTED, rejection_reason=payload.reason)
    audit.record(db, actor=admin, action="closure.rejected", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": prior}, after={"status": v.REJECTED}, reason=payload.reason, metadata={"referral_id": ref.id})
    await revert_referral_after_closure_ended(db, ref)
    _notify_both(db, ref, "The reported closed business was not accepted", payload.reason)
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await referral_detail(referral_id, admin, db)


@router.post("/referrals/{referral_id}/closure/invalidate", response_model=AdminReferralDetail)
async def invalidate_closure(referral_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    closure = await _live_closure(db, referral_id)
    prior = await _move(db, closure, {v.VERIFIED, v.UNDER_REVIEW, v.AWAITING_EVIDENCE, v.DISPUTED}, v.INVALIDATED, invalidated_at=utcnow(), invalidated_reason=payload.reason)
    audit.record(db, actor=admin, action="closure.invalidated", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": prior, "verification_level": closure.verification_level}, after={"status": v.INVALIDATED}, reason=payload.reason, metadata={"referral_id": ref.id})
    await revert_referral_after_closure_ended(db, ref)
    _notify_both(db, ref, "The closed business was invalidated", payload.reason)
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await referral_detail(referral_id, admin, db)


@router.post("/referrals/{referral_id}/closure/resolve-dispute", response_model=AdminReferralDetail)
async def resolve_dispute(referral_id: str, payload: AdminDisputeResolution, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    closure = await _live_closure(db, referral_id)
    if closure.status != v.DISPUTED:
        raise _conflict("This closed business is not under dispute.")
    if payload.outcome == "RESTORE":
        target = closure.status_before_dispute or v.AWAITING_CONFIRMATION
        prior = await _move(db, closure, {v.DISPUTED}, target, dispute_reason=None, disputed_by_user_id=None, disputed_at=None, status_before_dispute=None)
    elif payload.outcome == "REJECT":
        prior = await _move(db, closure, {v.DISPUTED}, v.REJECTED, rejection_reason=payload.reason)
        await revert_referral_after_closure_ended(db, ref)
    else:
        prior = await _move(db, closure, {v.DISPUTED}, v.INVALIDATED, invalidated_at=utcnow(), invalidated_reason=payload.reason)
        await revert_referral_after_closure_ended(db, ref)
    audit.record(db, actor=admin, action="closure.dispute_resolved", resource_type="deal_closure", resource_id=closure.id,
                 before={"status": prior}, after={"status": closure.status, "outcome": payload.outcome}, reason=payload.reason, metadata={"referral_id": ref.id})
    _notify_both(db, ref, "TGL reviewed the disputed closed business", payload.reason)
    await db.commit()
    await reward_hooks.closure_changed(closure.id)
    return await referral_detail(referral_id, admin, db)


# ------------------------------ flags, status, notes ------------------------------

@router.post("/referrals/{referral_id}/flag", response_model=AdminReferralDetail)
async def set_flag(referral_id: str, payload: AdminFlagIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    before = {"flagged": bool(ref.flagged), "flag_reason": ref.flag_reason}
    ref.flagged = payload.flagged
    ref.flag_reason = payload.reason if payload.flagged else None
    ref.flagged_at = utcnow() if payload.flagged else None
    ref.flagged_by = admin.id if payload.flagged else None
    audit.record(db, actor=admin, action="referral.flagged" if payload.flagged else "referral.unflagged", resource_type="referral", resource_id=ref.id,
                 before=before, after={"flagged": payload.flagged}, reason=payload.reason)
    await db.commit()
    return await referral_detail(referral_id, admin, db)


@router.post("/referrals/{referral_id}/status", response_model=AdminReferralDetail)
async def correct_status(referral_id: str, payload: AdminStatusCorrection, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    """Fix an erroneous status. An admin can never SET MEETING_DONE, BUSINESS_CLOSED or REVENUE_GENERATED:
    those exist only as the result of the two-party workflow, so no admin action can fabricate a verified
    meeting or deal. Moving a referral back to an earlier stage discards the (now untrue) meeting
    confirmations; what was discarded is preserved in the audit entry."""
    ref = await _referral(db, referral_id, lock=True)
    target = payload.status.upper()
    if target not in REFERRAL_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status.")
    if target not in CORRECTABLE:
        raise _conflict("Meeting and closed-business statuses can only be reached through the members' confirmations and a verified closure.")
    has_live = await db.scalar(select(DealClosure.id).where(DealClosure.referral_id == ref.id, DealClosure.status.not_in(tuple(v.CLOSURE_ENDED))).limit(1))
    if has_live:
        raise _conflict("Resolve the closed-business record first (reject or invalidate it).")
    if ref.status == target:
        raise _conflict("The referral already has that status.")
    confirmations = list((await db.execute(select(ReferralConfirmation).where(ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING))).scalars().all())
    verified_meeting = {c.role for c in confirmations} >= {"giver", "receiver"}
    prior_status = ref.status  # the bulk UPDATE below refreshes `ref`, so capture it now for the audit entry
    was_advanced = prior_status in _ADVANCED
    legacy = was_advanced and not verified_meeting
    now = utcnow()
    values = {"status": target, "last_action_at": now, "updated_at": now}
    if target in _STAMP and getattr(ref, _STAMP[target]) is None:
        values[_STAMP[target]] = now
    removed: list[dict] = []
    if was_advanced:
        values.update(business_closed_at=None, revenue_generated_at=None)
        if target in _BACKWARD:
            values["meeting_done_at"] = None
            removed = [{"role": c.role, "user_id": c.user_id, "confirmed_at": c.confirmed_at.isoformat() if c.confirmed_at else None} for c in confirmations]
    res = await db.execute(update(BusinessReferral).where(BusinessReferral.id == ref.id, BusinessReferral.status == ref.status).values(**values))
    if res.rowcount == 0:
        await db.rollback()
        raise _conflict("This was just updated. Refresh and try again.")
    if removed:
        await db.execute(delete(ReferralConfirmation).where(ReferralConfirmation.referral_id == ref.id, ReferralConfirmation.kind == v.MEETING))
    audit.record(db, actor=admin, action="referral.status_corrected", resource_type="referral", resource_id=ref.id,
                 before={"status": prior_status}, after={"status": target}, reason=payload.reason,
                 metadata={"legacy_unverified": legacy, "meeting_verified": verified_meeting, "removed_meeting_confirmations": removed})
    await db.commit()
    await reward_hooks.referral_changed(ref.id)
    return await referral_detail(referral_id, admin, db)


@router.post("/referrals/{referral_id}/notes", response_model=AdminReferralDetail)
async def add_note(referral_id: str, payload: AdminNoteIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    ref = await _referral(db, referral_id)
    audit.record(db, actor=admin, action="admin.note", resource_type="referral", resource_id=ref.id, reason=payload.reason)
    await db.commit()
    return await referral_detail(referral_id, admin, db)
