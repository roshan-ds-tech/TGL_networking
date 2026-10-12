"""Admin views and actions for the Growth Points SHADOW period.

Everything here is analysis. No endpoint changes an invoice, a payment or a subscription; the actions only write shadow
ledger / review rows, each with a written reason, an admin id and an audit entry.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit
from ..database import get_db
from ..config import settings
from ..storage import is_demo_photo, read_profile_photo
from ..models import Admin, AuditLog, DealClosure, GrowthPointFlag, GrowthPointLedger, GrowthPointRedemption, GrowthPointRedemptionEpoch, GrowthPointRenewal, User, utcnow
from ..redemption import finance as redemption_finance
from ..redemption import service as redemption_service
from ..rewards import analytics, engine, events, firewall, fraud, gates, jobs, ledger, reconcile, renewal, review, rules, simulation
from ..schemas_p0 import ReasonIn
from ..security import get_current_admin, require_csrf

router = APIRouter(prefix="/api/admin/growth-points", tags=["admin-growth-points-shadow"])


def _need_programme_owner(admin: Admin) -> None:
    """Pair exceptions are a high-trust decision: only the programme owner(s) named in PROGRAMME_OWNER_EMAILS may approve one.
    Empty list = nobody can (fail closed)."""
    if admin.email.strip().lower() not in settings.programme_owners():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a programme owner can approve a pair exception.")


def _need_shadow() -> None:
    if not firewall.shadow_enabled():
        raise HTTPException(status.HTTP_409_CONFLICT, "Growth Points shadow mode is off (GROWTH_POINTS_SHADOW_MODE). Turn it on to run this.")


@router.get("/status")
async def shadow_status(_: Admin = Depends(get_current_admin)) -> dict:
    return {"shadow_mode": firewall.shadow_enabled(), "redemption_enabled": firewall.redemption_enabled(), "member_preview": firewall.member_preview_enabled(),
            "rule_version": rules.RULE_VERSION, "real_financial_effect_inr": 0,
            "message": "Shadow mode only: points are recorded and simulated, never applied to an invoice or a payment."}


@router.get("/rules")
async def current_rules(_: Admin = Depends(get_current_admin)) -> dict:
    return {"rule_version": rules.RULE_VERSION, "parameters": json.loads(rules.parameters_json())}


@router.get("/summary")
async def summary(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.summary(db)


@router.get("/observation")
async def observation(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """The observation-period review pack: success metrics, and MODELLED vs ACTUAL. Admin only; aggregates only."""
    return await analytics.observation(db)


@router.get("/demo-members")
async def demo_members(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """The synthetic demo members (development / test databases only) with their sign-in details, so the interface can be tried by hand.
    They share ONE documented local-only password. In production this returns nothing and never shows a password."""
    from .. import demo
    from ..models import Business, PersonalProfile, Plan, Subscription
    if settings.environment.strip().lower() == "production":
        return {"enabled": False, "items": [], "message": "Demo members and their sign-in details are never shown in production."}
    scenario = {1: "Profile points only (no referral activity)", 2: "Eligible points (post-cutoff)", 3: "Shadow-period points only (never redeemable)", 4: "Points expired", 5: "Points reversed after a dispute", 6: "Cap hit (6,000 points)"}
    users = (await db.execute(select(User).where(demo.synthetic_clause()).order_by(User.email))).scalars().all()
    ids = [u.id for u in users]
    balances = {m: int(t or 0) for m, t in (await db.execute(select(GrowthPointLedger.member_id, func.sum(GrowthPointLedger.points_delta)).where(GrowthPointLedger.member_id.in_(ids)).group_by(GrowthPointLedger.member_id))).all()} if ids else {}
    plans = {m: p for m, p in (await db.execute(select(Subscription.user_id, Plan.name).join(Plan, Plan.id == Subscription.plan_id).where(Subscription.user_id.in_(ids), Subscription.status == "ACTIVE"))).all()} if ids else {}
    biz = {m: b for m, b in (await db.execute(select(Business.user_id, Business.business_name).where(Business.user_id.in_(ids)))).all()} if ids else {}
    cities = {m: c for m, c in (await db.execute(select(PersonalProfile.user_id, PersonalProfile.city).where(PersonalProfile.user_id.in_(ids)))).all()} if ids else {}
    items = []
    for u in users:
        n = int(u.email.split("@")[0].split("-")[-1]) if u.email.split("@")[0].split("-")[-1].isdigit() else 0
        items.append({"id": u.id, "email": u.email, "password": demo.DEMO_PASSWORD, "name": u.full_name, "business": biz.get(u.id), "city": cities.get(u.id), "plan": plans.get(u.id), "active": u.is_active,
                      "growth_points": balances.get(u.id, 0), "scenario": scenario.get(n), "photo_url": f"/api/admin/growth-points/demo-members/{u.id}/photo?v={u.photo_key.split('.')[0][-12:]}" if is_demo_photo(u.photo_key) else None})
    return {"enabled": True, "items": items, "total": len(items), "password_note": "All demo accounts share this local-only password. It exists only in development and test databases.",
            "how_to_create": "python scripts/seed_demo_members.py   (from the backend folder; refuses production; safe to run again)"}


@router.get("/demo-members/{user_id}/photo")
async def demo_member_photo(user_id: str, _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    """The picture of ONE synthetic demo member, for the admin Demo members tab only. Read-only and narrow on purpose:
      * an administrator session is required (the member photo route stays members-only and is not touched);
      * development / test databases only (the list above is empty in production);
      * the member must be synthetic (reserved demo email domain) and the stored name must be in the demo namespace, so a genuine member's photo
        can never be served here, whatever id is asked for;
      * the client sends only the member id: the file name comes from the database and is validated by the existing photo store, so there is no
        path to traverse."""
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    if settings.environment.strip().lower() == "production":
        raise not_found
    from .. import demo
    key = await db.scalar(select(User.photo_key).where(User.id == user_id, demo.synthetic_clause()))
    if not is_demo_photo(key):
        raise not_found
    data = await read_profile_photo(key)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": f"private, max-age={60 * 60}", "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@router.get("/finance")
async def finance(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """The REAL economy (realized cost, redemptions, outstanding potential liability), kept apart from the modelled and shadow numbers."""
    return await redemption_finance.summary(db)


@router.get("/redemptions")
async def redemptions_list(page: int = Query(default=1, ge=1, le=100_000), page_size: int = Query(default=25, ge=1, le=100), _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    R = GrowthPointRedemption
    total = int(await db.scalar(select(func.count(R.id))) or 0)
    rows = (await db.execute(select(R).order_by(R.created_at.desc(), R.id).limit(page_size).offset((page - 1) * page_size))).scalars().all()
    cols = ("id", "created_at", "member_id", "entry_type", "reverses_id", "old_cycle_id", "subscription_id", "invoice_id", "points", "discount_paise", "list_price_minor", "amount_due_minor",
            "cap_points", "eligible_points", "restored_points", "rule_version", "created_by", "reason")
    return {"items": [{c: getattr(r, c) for c in cols} for r in rows], "total": total, "page": page, "pages": max(1, -(-total // page_size))}


@router.get("/redemptions/export")
async def redemptions_export(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    """For the professional accounting / GST review: every redemption and reversal with its invoice fields. Ids and amounts only (no names, emails or phones)."""
    from ..models import Invoice
    R = GrowthPointRedemption
    q = select(R, Invoice).join(Invoice, Invoice.id == R.invoice_id).order_by(R.created_at, R.id).limit(200_000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["redemption_id", "entry_type", "reverses_id", "created_at", "member_id", "invoice_number", "invoice_status", "invoice_issued_at", "plan_name", "period_months", "currency",
                "list_price_minor", "points", "point_value_paise", "discount_minor", "amount_due_minor", "amount_paid_minor", "restored_points", "rule_version", "created_by", "reason"])
    for r, inv in (await db.execute(q)).all():
        w.writerow([r.id, r.entry_type, r.reverses_id or "", r.created_at, r.member_id, inv.number, inv.status, inv.issued_at, inv.plan_name, inv.period_months, inv.currency, r.list_price_minor, r.points,
                    r.point_value_paise, r.discount_paise, r.amount_due_minor, inv.amount_paid_minor, r.restored_points, r.rule_version, r.created_by, r.reason or ""])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="growth-points-redemptions.csv"'})


class EpochIn(BaseModel):
    cutoff_at: datetime
    reason: str = Field(min_length=3, max_length=240)


@router.post("/redemption/epoch")
async def record_epoch(payload: EpochIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Record the OFFICIALLY APPROVED eligibility cutoff, once and forever. Every point earned before it is a shadow-period point and is permanently
    ineligible for redemption. Programme owner only; needs MANAGEMENT_MODEL recorded in GROWTH_POINTS_APPROVALS; the cutoff must carry an explicit
    UTC offset and can not be in the past (so nothing already earned can be grandfathered in). It does NOT enable redemption. Do not call it
    without a written management approval of the exact instant."""
    _need_programme_owner(admin)
    if "MANAGEMENT_MODEL" not in settings.growth_points_approval_codes():
        raise HTTPException(status.HTTP_409_CONFLICT, "MANAGEMENT_MODEL is not recorded in GROWTH_POINTS_APPROVALS: a cutoff needs an approval first.")
    if payload.cutoff_at.tzinfo is None or payload.cutoff_at.utcoffset() is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The cutoff needs an explicit UTC offset, for example 2027-01-01T00:00:00+05:30.")
    cutoff = payload.cutoff_at.astimezone(timezone.utc)
    now = utcnow()
    if cutoff < now:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The cutoff can not be in the past: points already earned never become redeemable.")
    if await db.scalar(select(GrowthPointRedemptionEpoch.id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A cutoff has already been recorded. It is immutable.")
    db.add(GrowthPointRedemptionEpoch(cutoff_at=cutoff, recorded_at=now, recorded_by=admin.id, reason=payload.reason))
    audit.record(db, actor=admin, action="growth_points.epoch_recorded", resource_type="growth_points", resource_id=None, after={"cutoff_at": cutoff.isoformat()}, reason=payload.reason)
    await db.commit()
    return {"cutoff_at": cutoff.isoformat(), "note": "Recorded. Set GROWTH_POINTS_REDEEMABLE_FROM to this exact instant for it to take effect; redemption itself stays gated."}


@router.get("/redemption/state")
async def redemption_state(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    cutoff, why = await redemption_service.cutoff_status(db)
    return {"effective_cutoff": cutoff, "cutoff_status": why, "recorded_epoch": await db.scalar(select(GrowthPointRedemptionEpoch.cutoff_at).limit(1)),"flag_enabled": firewall.redemption_enabled(), "kill_switch_on": await redemption_service.killed(db), "rollout_stage": settings.growth_points_rollout_stage,
            "redeemable_from": settings.growth_points_redeemable_from or None, "approvals_recorded": sorted(settings.growth_points_approval_codes())}


@router.post("/redemption/kill")
async def kill_switch(payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """EMERGENCY: stop NEW redemptions now, no restart. Existing invoices, redemptions, points and history are untouched. Programme owner only."""
    _need_programme_owner(admin)
    await redemption_service.set_kill(db, True, admin.id, payload.reason)
    audit.record(db, actor=admin, action="growth_points.kill_switch_on", resource_type="growth_points", resource_id=None, reason=payload.reason)
    await db.commit()
    return {"kill_switch_on": True}


@router.post("/redemption/resume")
async def kill_switch_resume(payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Lift the kill switch (the other gates still apply). Programme owner only."""
    _need_programme_owner(admin)
    await redemption_service.set_kill(db, False, admin.id, payload.reason)
    audit.record(db, actor=admin, action="growth_points.kill_switch_off", resource_type="growth_points", resource_id=None, reason=payload.reason)
    await db.commit()
    return {"kill_switch_on": False}


@router.get("/gates")
async def objective_gates(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """Gate A, the environment checks and the Phase 3 prerequisites, evaluated from data and environment. Read-only."""
    return await gates.evaluate(db)


@router.get("/review")
async def gate_a_review(format_: str = Query(default="json", alias="format", pattern="^(json|markdown)$"), _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    """The Gate A management review: dashboard, modelled vs actual, proposed model changes (never applied), exit criteria. Admin only."""
    r = await review.report(db)
    if format_ == "markdown":
        return Response(review.to_markdown(r), media_type="text/markdown", headers={"Cache-Control": "no-store"})
    return Response(json.dumps(r, default=str), media_type="application/json", headers={"Cache-Control": "no-store"})


@router.get("/renewal-preview")
async def renewal_preview(member_id: str = Query(max_length=36), plan_code: str = Query(pattern="^(connect|growth|elite)$"), at: datetime | None = None,
                          _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """What renewing into a plan WOULD look like for a member: current and new plan, price and term, eligible old-cycle points, the point value,
    the NEW plan's redemption ceiling, the points that would be used (oldest first), the hypothetical discount and amount payable.
    HYPOTHETICAL / SHADOW ONLY, admin only, read-only. (Members do not see it while the member preview is off.)"""
    if await db.get(User, member_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return await renewal.preview(db, member_id, plan_code, at)


@router.get("/renewals")
async def renewals_list(page: int = Query(default=1, ge=1, le=100_000), page_size: int = Query(default=25, ge=1, le=100), outcome: str | None = Query(default=None, max_length=20),
                        _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """Every recorded hypothetical renewal redemption (ids, plans, points and amounts only)."""
    R = GrowthPointRenewal
    q = select(R)
    if outcome:
        q = q.where(R.outcome == outcome)
    total = int(await db.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = (await db.execute(q.order_by(R.created_at.desc(), R.id).limit(page_size).offset((page - 1) * page_size))).scalars().all()
    cols = ("id", "created_at", "member_id", "old_cycle_id", "from_plan", "to_plan", "new_term_months", "new_price_minor", "outcome", "eligible_points", "redemption_cap_points",
            "redeemed_points", "remaining_points", "hypothetical_discount_paise", "hypothetical_payable_paise", "decided_at", "old_expires_at", "reason", "rule_version", "shadow")
    return {"items": [{c: getattr(r, c) for c in cols} for r in rows], "total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size)),
            "label": renewal.LABEL}


@router.get("/exceptions")
async def pair_exceptions(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """Every approved pair exception, from the audit log: approver, reason, pair, event, time, original cap and approved amount."""
    rows = (await db.execute(select(AuditLog).where(AuditLog.action == "growth_points.pair_exception").order_by(AuditLog.created_at.desc()).limit(200))).scalars().all()
    return {"items": [{"id": r.id, "created_at": r.created_at, "approver_id": r.actor_id, "reason": r.reason, "closure_id": r.resource_id,
                       "before": json.loads(r.before_json) if r.before_json else None, "after": json.loads(r.after_json) if r.after_json else None} for r in rows]}


@router.get("/economics")
async def economics(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.economics(db)


@router.get("/members")
async def members(page: int = Query(default=1, ge=1, le=100_000), page_size: int = Query(default=25, ge=1, le=100), search: str | None = Query(default=None, max_length=120),
                  _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.members_page(db, page, page_size, search)


@router.get("/members/{member_id}")
async def member_detail(member_id: str, _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.get(User, member_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    snap = await simulation.member_snapshot(db, member_id)
    lots = await ledger.lots(db, member_id=member_id)
    recent = await analytics.ledger_page(db, 1, 100, member_id=member_id)
    flags = await analytics.flags_page(db, 1, 50, None, None, member_id=member_id)
    return {"member": {"id": user.id, "email": user.email}, "snapshot": snap,
            "lots": [{"id": l.id, "event_type": l.row.event_type, "points": l.row.points_delta, "remaining": l.remaining, "state": l.state,
                      "available_at": l.row.available_at, "expires_at": l.row.expires_at, "capped_by": l.row.capped_by} for l in lots],
            "ledger": recent["items"], "flags": flags["items"]}


@router.get("/ledger")
async def ledger_list(page: int = Query(default=1, ge=1, le=100_000), page_size: int = Query(default=50, ge=1, le=200), member_id: str | None = Query(default=None, max_length=36),
                      event_type: str | None = Query(default=None, max_length=30), status_: str | None = Query(default=None, alias="status", max_length=10),
                      capped_by: str | None = Query(default=None, max_length=40), entry_type: str | None = Query(default=None, max_length=10),
                      _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.ledger_page(db, page, page_size, member_id, event_type, status_, capped_by, entry_type)


@router.get("/flags")
async def flags(page: int = Query(default=1, ge=1, le=100_000), page_size: int = Query(default=50, ge=1, le=200), status_: str | None = Query(default=None, alias="status", max_length=10),
                kind: str | None = Query(default=None, max_length=40), _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await analytics.flags_page(db, page, page_size, status_, kind)


@router.get("/reconcile")
async def reconcile_report(_: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    return await reconcile.reconcile(db)


EXPORT_COLUMNS = ("id", "created_at", "event_at", "member_id", "counterparty_id", "entry_type", "event_type", "category", "role", "reference_type", "reference_id",
                  "parent_id", "cycle_id", "points_delta", "requested_points", "capped_points", "capped_by", "status", "assurance", "verification_level",
                  "available_at", "expires_at", "remaining", "balance_after", "rule_version", "day_key", "month_key", "quarter_key")


@router.get("/export")
async def export(format_: str = Query(default="csv", alias="format", pattern="^(csv|json)$"), since: datetime | None = None,
                 _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    """The shadow ledger for economic analysis. No emails, phones, evidence or exact deal values: ids, points, rules and bands only."""
    q = select(GrowthPointLedger).order_by(GrowthPointLedger.created_at, GrowthPointLedger.id).limit(200_000)
    if since:
        q = q.where(GrowthPointLedger.created_at >= since)
    rows = (await db.execute(q)).scalars().all()
    headers = {"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="growth-points-shadow-ledger.{format_}"'}
    if format_ == "json":
        return Response(json.dumps([{c: getattr(r, c) for c in EXPORT_COLUMNS} for r in rows], default=str), media_type="application/json", headers=headers)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_COLUMNS)
    for r in rows:
        w.writerow([getattr(r, c) if getattr(r, c) is not None else "" for c in EXPORT_COLUMNS])
    return Response(buf.getvalue(), media_type="text/csv", headers=headers)


# ------------------------------------------------------------------ actions (shadow ledger / review rows only)

@router.post("/flags/{flag_id}/review")
async def review_flag(flag_id: str, payload: ReasonIn, outcome: str = Query(default="REVIEWED", pattern="^(REVIEWED|DISMISSED)$"),
                      admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    flag = await db.get(GrowthPointFlag, flag_id)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")
    if flag.status != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, "This flag was already reviewed.")
    flag.status, flag.reviewed_by_admin_id, flag.reviewed_at, flag.review_note = outcome, admin.id, utcnow(), payload.reason
    audit.record(db, actor=admin, action="growth_points.flag_reviewed", resource_type="growth_point_flag", resource_id=flag.id,
                 before={"status": "OPEN"}, after={"status": outcome}, reason=payload.reason)
    await db.commit()
    return {"id": flag.id, "status": flag.status}


@router.post("/flags/{flag_id}/apply-reversal")
async def apply_late_reversal(flag_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf),
                              db: AsyncSession = Depends(get_db)) -> dict:
    """The ONLY way points that were already usable are taken back after the 60-day automatic window.

    The engine never claws back by itself outside the window: it queues a REVERSAL_NEEDS_REVIEW flag (OPEN = awaiting an admin).
    An admin who decides the points should go calls this, with a reason. It adds a NEW REVERSAL row pointing at the original lot
    (created_by = the admin); the original row is never touched. It refuses if the deal / referral has been restored since.
    To keep the points instead, dismiss the flag."""
    _need_shadow()
    flag = await db.get(GrowthPointFlag, flag_id)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")
    if flag.kind != "REVERSAL_NEEDS_REVIEW":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a late-reversal review item can be applied.")
    if flag.status != "OPEN":
        raise HTTPException(status.HTTP_409_CONFLICT, "This flag was already reviewed.")
    marker = "reversal-review:"
    lot_id = flag.dedupe_key.split(marker, 1)[1] if marker in flag.dedupe_key else None
    lots = await ledger.lots(db, reference_type=flag.reference_type, reference_id=flag.reference_id) if lot_id else []
    lot = next((l for l in lots if l.id == lot_id), None)
    if lot is None or lot.remaining <= 0 or lot.state == "EXPIRED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is left to reverse (the points were already reversed or have expired).")
    if not await events.still_invalid(db, lot):
        raise HTTPException(status.HTTP_409_CONFLICT, "The deal or referral behind these points is valid again. Dismiss the flag instead.")
    with firewall.guard():
        row = await engine.adjust(db, lot, "REVERSAL", f"Late reversal approved by an admin: {payload.reason}", created_by=admin.id)
    flag.status, flag.reviewed_by_admin_id, flag.reviewed_at, flag.review_note = "REVIEWED", admin.id, utcnow(), payload.reason
    audit.record(db, actor=admin, action="growth_points.late_reversal", resource_type="growth_point_flag", resource_id=flag.id,
                 before={"status": "OPEN", "points_remaining": lot.remaining}, after={"status": "REVIEWED", "reversal_row": row.id if row else None, "points": -lot.remaining},
                 reason=payload.reason)
    await db.commit()
    return {"id": flag.id, "status": flag.status, "reversal_row": row.id if row else None, "points_reversed": lot.remaining}


@router.post("/scan")
async def scan(payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Run the fraud / gaming analysis over everything recorded so far. Creates review items only."""
    created = await fraud.scan(db)
    audit.record(db, actor=admin, action="growth_points.scan", resource_type="growth_points", resource_id=None, after={"new_flags": created}, reason=payload.reason)
    await db.commit()
    return {"new_flags": created}


@router.post("/sweep")
async def sweep(payload: ReasonIn, backfill_limit: int = Query(default=500, ge=1, le=5000), admin: Admin = Depends(get_current_admin),
                __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Expire what is due, void or reverse what no longer stands, and issue anything the hooks missed. Idempotent."""
    _need_shadow()
    result = await jobs.sweep(db, backfill_limit=backfill_limit)
    audit.record(db, actor=admin, action="growth_points.sweep", resource_type="growth_points", resource_id=None, after=result, reason=payload.reason)
    await db.commit()
    return result


@router.post("/reconcile")
async def reconcile_and_repair(payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Re-run reconciliation and rebuild the cached balances (derived data) from the ledger. The ledger itself is never touched."""
    result = await reconcile.reconcile(db, repair_cache=True)
    audit.record(db, actor=admin, action="growth_points.reconcile", resource_type="growth_points", resource_id=None,
                 after={"drift": len(result["drift"]), "violations": len(result["violations"])}, reason=payload.reason)
    await db.commit()
    return result


@router.post("/closures/{closure_id}/reevaluate")
async def reevaluate_closure(closure_id: str, payload: ReasonIn, pair_exception: bool = Query(default=False), admin: Admin = Depends(get_current_admin),
                             __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db)) -> dict:
    """Re-run the reward for one verified closure: after an admin raised it to level 4 (a reciprocal closure needs that), or to record a
    reasoned exception to the pair concentration rule. Adds new shadow rows; never edits an old one."""
    _need_shadow()
    if pair_exception:
        _need_programme_owner(admin)
    closure = await db.get(DealClosure, closure_id)
    if closure is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Closure not found")
    L = GrowthPointLedger
    columns = (L.id, L.member_id, L.pair_key, L.event_type, L.requested_points, L.points_delta, L.capped_points, L.capped_by)
    earn = lambda: select(*columns).where(L.entry_type == "EARN", L.reference_type == "deal_closure", L.reference_id == closure_id).order_by(L.created_at, L.id)   # noqa: E731
    before = (await db.execute(earn())).all()
    with firewall.guard():
        result = await events.sync_closure(db, closure_id, pair_exception=pair_exception, reeval=True, created_by=admin.id, reason=payload.reason)
    audit.record(db, actor=admin, action="growth_points.closure_reevaluated", resource_type="deal_closure", resource_id=closure_id,
                 after={**result, "pair_exception": pair_exception}, reason=payload.reason)
    if pair_exception:
        seen = {r.id for r in before}
        approved = [r for r in (await db.execute(earn())).all() if r.id not in seen]
        # the full exception record: approver (the audit actor), reason, pair, event, time (the audit row), the cap it overrides and what was approved
        audit.record(
            db, actor=admin, action="growth_points.pair_exception", resource_type="deal_closure", resource_id=closure_id, reason=payload.reason,
            before={"pair": before[0].pair_key if before else None, "event": before[0].event_type if before else None,
                    "original_cap": [{"member_id": r.member_id, "requested_points": r.requested_points, "awarded_points": r.points_delta, "capped_points": r.capped_points, "capped_by": r.capped_by} for r in before]},
            after={"approved": [{"member_id": r.member_id, "event_type": r.event_type, "approved_points": r.points_delta, "requested_points": r.requested_points, "still_capped_by": r.capped_by} for r in approved]},
        )
    await db.commit()
    return result
