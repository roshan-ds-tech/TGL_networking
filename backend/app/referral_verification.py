"""Shared read/query helpers for meeting confirmation and deal closure.

The state changes themselves live in routers/closures.py (member side) and
routers/admin_referrals.py (admin side); this module builds the views both use.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BusinessReferral, DealClosure, DealEvidence, ReferralConfirmation
from .schemas_p0 import ClosureOut, EvidenceOut, MeetingState
from . import verification as v


def meeting_state(ref: BusinessReferral, confirmations: list[ReferralConfirmation], me: str) -> MeetingState:
    mine = next((c for c in confirmations if c.user_id == me), None)
    theirs = next((c for c in confirmations if c.user_id != me), None)
    if ref.status in v.MEETING_CONFIRMABLE_STATUSES:
        state = "WAITING_FOR_OTHER" if mine else "WAITING_FOR_YOU"
    elif ref.status in ("MEETING_DONE", "BUSINESS_CLOSED", "REVENUE_GENERATED"):
        # Only two confirmation rows (one per member) make a meeting verified. A referral moved on by the
        # old one-member flow has none: it is shown as "not verified", never as confirmed.
        state = "CONFIRMED_BY_BOTH" if {c.role for c in confirmations} >= {"giver", "receiver"} else "NOT_VERIFIED"
    else:
        state = "NOT_AVAILABLE"
    return MeetingState(
        state=state, you_confirmed=mine is not None, other_confirmed=theirs is not None,
        you_confirmed_at=mine.confirmed_at if mine else None, other_confirmed_at=theirs.confirmed_at if theirs else None,
    )


def evidence_out(e: DealEvidence, me: str) -> EvidenceOut:
    return EvidenceOut(
        id=e.id, evidence_type=e.evidence_type, mime=e.mime, size_bytes=e.size_bytes, note=e.note, uploaded_at=e.uploaded_at,
        uploaded_by_you=e.uploaded_by_user_id == me, status=e.status, rejection_reason=e.rejection_reason, verified_at=e.verified_at,
    )


def closure_out(ref: BusinessReferral, c: DealClosure, evidence: list[DealEvidence], me: str) -> ClosureOut:
    is_referrer = ref.giver_user_id == me
    is_reporter = c.reported_by_user_id == me
    live_evidence = [e for e in evidence if e.status != v.EVIDENCE_REJECTED]
    return ClosureOut(
        id=c.id, referral_id=c.referral_id, status=c.status, status_label=v.CLOSURE_LABEL.get(c.status, c.status),
        verification_level=c.verification_level, verification_label=v.LEVEL_LABEL[c.verification_level],
        actual_value_minor=c.actual_value_minor, currency=c.currency, value_band=c.value_band,
        value_band_label=v.BAND_LABEL[c.value_band], evidence_required=c.evidence_required,
        admin_approval_required=c.admin_approval_required, note=c.note, reported_by_you=is_reporter,
        confirmed_by_receiver_at=c.confirmed_by_receiver_at, confirmed_by_referrer_at=c.confirmed_by_referrer_at,
        submitted_at=c.submitted_at, verified_at=c.verified_at, rejection_reason=c.rejection_reason, dispute_reason=c.dispute_reason,
        can_confirm=is_referrer and c.status == v.AWAITING_CONFIRMATION,
        can_dispute=c.status in (v.AWAITING_CONFIRMATION, v.AWAITING_EVIDENCE, v.UNDER_REVIEW, v.VERIFIED),
        can_edit=is_reporter and c.status == v.AWAITING_CONFIRMATION,
        can_cancel=is_reporter and c.status == v.AWAITING_CONFIRMATION,
        can_add_evidence=c.status in (v.AWAITING_EVIDENCE, v.UNDER_REVIEW) and len(live_evidence) < v.MAX_EVIDENCE_PER_CLOSURE,
        evidence=[evidence_out(e, me) for e in evidence],
    )


async def load_for_referrals(db: AsyncSession, refs: list[BusinessReferral], with_evidence: bool = False):
    """Confirmations and the live closure for a page of referrals, in two queries (three with evidence)."""
    ids = [r.id for r in refs]
    confirmations: dict[str, list[ReferralConfirmation]] = defaultdict(list)
    closures: dict[str, DealClosure] = {}
    evidence: dict[str, list[DealEvidence]] = defaultdict(list)
    if not ids:
        return confirmations, closures, evidence
    rows = (await db.execute(select(ReferralConfirmation).where(ReferralConfirmation.referral_id.in_(ids), ReferralConfirmation.kind == v.MEETING))).scalars().all()
    for c in rows:
        confirmations[c.referral_id].append(c)
    crows = (await db.execute(
        select(DealClosure).where(DealClosure.referral_id.in_(ids), DealClosure.status.not_in(tuple(v.CLOSURE_ENDED)))
        .order_by(DealClosure.created_at.desc())
    )).scalars().all()
    for c in crows:
        closures.setdefault(c.referral_id, c)
    if with_evidence and closures:
        erows = (await db.execute(select(DealEvidence).where(DealEvidence.closure_id.in_([c.id for c in closures.values()])).order_by(DealEvidence.uploaded_at))).scalars().all()
        for e in erows:
            evidence[e.closure_id].append(e)
    return confirmations, closures, evidence


def extras_for(ref: BusinessReferral, me: str, confirmations, closures, evidence) -> dict:
    """The `meeting` and `closure` fields a referral response carries."""
    closure = closures.get(ref.id)
    return {
        "meeting": meeting_state(ref, confirmations.get(ref.id, []), me).model_dump(),
        "closure": closure_out(ref, closure, evidence.get(closure.id, []), me).model_dump() if closure else None,
    }
