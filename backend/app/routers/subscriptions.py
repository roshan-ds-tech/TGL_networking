"""Subscriptions, invoices and payments (Phase 0 foundation).

Member endpoints live under /api/v1; the admin review endpoints under /api/admin.
The backend decides every price, status and amount: the client only names a plan
and uploads a proof.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import audit
from ..database import get_db
from ..models import Admin, Invoice, PersonalProfile, Payment, Plan, Subscription, User, utcnow
from ..ratelimit import enforce
from ..schemas_p0 import (
    AdminPerson, AdminSubscriptionItem, AdminSubscriptionPage, InvoiceOut, PaymentInstructionsOut, PaymentOut, PlanOut, ReasonIn,
    SubscriptionCreate, SubscriptionOut,
)
from ..security import (
    get_current_admin, has_networking_access, require_csrf, require_customer_csrf, require_verified_user,
)
from ..services import add_calendar_months, notify
from ..storage import delete_proof, read_proof, save_document
from ..subscriptions import build_purchase, expire_stale, payment_instructions, plan_is_purchasable

router = APIRouter(prefix="/api/v1", tags=["subscriptions"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin-subscriptions"])


def _payment_out(p: Payment | None) -> PaymentOut | None:
    if p is None:
        return None
    return PaymentOut(
        id=p.id, method=p.method, status=p.status, amount_minor=p.amount_minor, reference=p.reference,
        has_proof=bool(p.proof_filename), submitted_at=p.submitted_at, verified_at=p.verified_at,
        rejection_reason=p.rejection_reason, refunded_at=p.refunded_at,
    )


async def _bundle(db: AsyncSession, sub: Subscription) -> SubscriptionOut:
    plan = await db.get(Plan, sub.plan_id)
    invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.created_at.desc()).limit(1))
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.created_at.desc()).limit(1)) if invoice else None
    return SubscriptionOut(
        id=sub.id, status=sub.status, plan=PlanOut.model_validate(plan), starts_at=sub.starts_at, expires_at=sub.expires_at,
        activated_at=sub.activated_at, created_at=sub.created_at, is_renewal=bool(sub.renews_subscription_id),
        invoice=InvoiceOut.model_validate(invoice) if invoice else None, payment=_payment_out(payment),
    )


def _effective(sub: Subscription) -> str:
    exp = sub.expires_at
    if sub.status == "ACTIVE" and exp is not None:
        exp = exp if exp.tzinfo else exp.replace(tzinfo=utcnow().tzinfo)
        if exp <= utcnow():
            return "EXPIRED"
    return sub.status


async def _own(db: AsyncSession, subscription_id: str, user: User, lock: bool = False) -> Subscription:
    """The member's own subscription (404 for anyone else's). lock=True takes a row lock so the member's
    cancel / proof upload and an admin's verify / reject / refund run one after the other, not interleaved
    (SELECT ... FOR UPDATE on Postgres; SQLite already serialises writers)."""
    sub = await db.get(Subscription, subscription_id, with_for_update=lock, populate_existing=lock)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")  # same answer for "not yours"
    return sub


# ------------------------------------ member ------------------------------------

@router.get("/plans", response_model=list[PlanOut])
async def list_plans(_: User = Depends(require_verified_user), db: AsyncSession = Depends(get_db)) -> list[Plan]:
    rows = (await db.execute(select(Plan).where(Plan.status == "ACTIVE").order_by(Plan.sort_order, Plan.price_minor))).scalars().all()
    return [p for p in rows if plan_is_purchasable(p)]


@router.get("/subscriptions/current", response_model=SubscriptionOut | None)
async def current_subscription(user: User = Depends(require_verified_user), db: AsyncSession = Depends(get_db)):
    if await expire_stale(db, user.id):
        await db.commit()
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc()).limit(1))
    if sub is None:
        return None
    return await _bundle(db, sub)


@router.get("/subscriptions/payment-instructions", response_model=PaymentInstructionsOut)
async def subscription_payment_instructions(_: User = Depends(require_verified_user)) -> PaymentInstructionsOut:
    """How to pay a subscription invoice. `configured` is false until management supplies the official text;
    the app never makes payment details up."""
    text = payment_instructions()
    return PaymentInstructionsOut(configured=text is not None, instructions=text)


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    payload: SubscriptionCreate,
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    enforce(f"subscribe:{user.id}", 10, 3600, "Too many attempts. Please try again later.")
    plan = await db.scalar(select(Plan).where(Plan.code == payload.plan_code))
    if plan is None or not plan_is_purchasable(plan):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That plan is not available.")
    if await expire_stale(db, user.id):
        await db.flush()  # a lapsed ACTIVE row must not block buying again
    if await has_networking_access(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have Networking access.")
    live = await db.scalar(select(Subscription.id).where(Subscription.user_id == user.id, Subscription.status.in_(("PENDING", "ACTIVE"))).limit(1))
    if live is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a subscription in progress.")

    sub, invoice, payment = build_purchase(user.id, plan)
    db.add(sub)
    try:
        await db.flush()  # the partial unique index stops a concurrent twin here
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a subscription in progress.")
    invoice.subscription_id = sub.id
    db.add(invoice)
    await db.flush()
    payment.invoice_id = invoice.id
    db.add(payment)
    audit.record(db, actor=user, action="subscription.created", resource_type="subscription", resource_id=sub.id,
                 after={"plan": plan.code, "price_minor": plan.price_minor, "period_months": plan.period_months, "status": "PENDING"})
    audit.record(db, actor=user, action="invoice.issued", resource_type="invoice", resource_id=invoice.id,
                 after={"number": invoice.number, "amount_due_minor": invoice.amount_due_minor, "discount_minor": 0, "status": "ISSUED"})
    await db.commit()
    return await _bundle(db, sub)


@router.post("/subscriptions/{subscription_id}/payment-proof", response_model=SubscriptionOut)
async def submit_payment_proof(
    subscription_id: str,
    proof: UploadFile = File(...),
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    enforce(f"payment-proof:{user.id}", 10, 3600, "Too many uploads. Please try again later.")
    sub = await _own(db, subscription_id, user, lock=True)
    if sub.status != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, "This subscription is not awaiting payment.")
    invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.created_at.desc()).limit(1))
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.created_at.desc()).limit(1))
    if payment is None or payment.status not in ("PENDING", "FAILED", "SUBMITTED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "A payment can no longer be submitted for this subscription.")
    name, mime, size, digest = await save_document(proof, "Payment proof")
    try:
        old = payment.proof_filename
        before = {"payment_status": payment.status, "invoice_status": invoice.status}
        payment.proof_filename, payment.proof_mime, payment.proof_bytes = name, mime, size
        payment.status, payment.submitted_at, payment.rejection_reason = "SUBMITTED", utcnow(), None
        invoice.status = "PENDING"
        audit.record(db, actor=user, action="payment.proof_submitted", resource_type="payment", resource_id=payment.id,
                     before=before, after={"payment_status": "SUBMITTED", "invoice_status": "PENDING", "bytes": size, "mime": mime, "sha256": digest},
                     metadata={"subscription_id": sub.id, "replaced_previous_proof": bool(old)})
        await db.commit()
    except Exception:
        # The file is stored before the row is committed: do not leave an unreachable file behind if the commit fails.
        await db.rollback()
        await delete_proof(name)
        raise
    if old:
        await delete_proof(old)  # only after the new one is committed
    return await _bundle(db, sub)


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionOut)
async def cancel_subscription(
    subscription_id: str,
    user: User = Depends(require_verified_user),
    __: None = Depends(require_customer_csrf),
    db: AsyncSession = Depends(get_db),
):
    sub = await _own(db, subscription_id, user, lock=True)
    if sub.status != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an unpaid subscription can be cancelled here.")
    invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.created_at.desc()).limit(1))
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.created_at.desc()).limit(1))
    if payment is not None and payment.status == "VERIFIED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This payment has already been verified.")
    sub.status, sub.cancelled_at, sub.cancel_reason = "CANCELLED", utcnow(), "Cancelled by the member"
    invoice.status = "CANCELLED"
    if payment is not None and payment.status in ("PENDING", "SUBMITTED"):
        payment.status = "FAILED"
        payment.rejection_reason = "Cancelled by the member"
    audit.record(db, actor=user, action="subscription.cancelled", resource_type="subscription", resource_id=sub.id,
                 before={"status": "PENDING"}, after={"status": "CANCELLED"}, reason="Cancelled by the member")
    await db.commit()
    return await _bundle(db, sub)


# ------------------------------------- admin -------------------------------------

async def _claim(db: AsyncSession, model, row_id: str, expected: str, **values) -> None:
    """Compare-and-set a status: two admins acting at once cannot both succeed."""
    res = await db.execute(update(model).where(model.id == row_id, model.status == expected).values(**values))
    if res.rowcount == 0:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This was just updated by someone else. Refresh and try again.")


async def _pair(db: AsyncSession, subscription_id: str, lock: bool = False) -> tuple[Subscription, Invoice, Payment]:
    sub = await db.get(Subscription, subscription_id, with_for_update=lock, populate_existing=lock)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription not found")
    invoice = await db.scalar(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.created_at.desc()).limit(1))
    payment = await db.scalar(select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.created_at.desc()).limit(1))
    if invoice is None or payment is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This subscription has no invoice or payment.")
    return sub, invoice, payment


@admin_router.get("/subscriptions", response_model=AdminSubscriptionPage)
async def admin_list_subscriptions(
    status_filter: str | None = Query(default=None, alias="status", max_length=12),
    payment_status: str | None = Query(default=None, max_length=12),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=25, ge=1, le=100),
    _: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(Subscription, Plan, Invoice, Payment, User, PersonalProfile.full_name)
        .join(Plan, Plan.id == Subscription.plan_id)
        .join(Invoice, Invoice.subscription_id == Subscription.id)
        .join(Payment, Payment.invoice_id == Invoice.id)
        .join(User, User.id == Subscription.user_id)
        .outerjoin(PersonalProfile, PersonalProfile.user_id == User.id)
    )
    if status_filter:
        base = base.where(Subscription.status == status_filter.upper())
    if payment_status:
        base = base.where(Payment.status == payment_status.upper())
    if search:
        like = f"%{search.strip().lower()}%"
        base = base.where(or_(func.lower(User.email).like(like), func.lower(Invoice.number).like(like), func.lower(Payment.reference).like(like)))
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await db.execute(base.order_by(Subscription.created_at.desc()).limit(page_size).offset((page - 1) * page_size))).all()
    items = [
        AdminSubscriptionItem(
            id=s.id, status=s.status, effective_status=_effective(s), user=AdminPerson(id=u.id, email=u.email, name=name or u.full_name),
            plan_code=pl.code, plan_name=pl.name, invoice_number=inv.number, invoice_status=inv.status,
            amount_due_minor=inv.amount_due_minor, amount_paid_minor=inv.amount_paid_minor, payment_status=pay.status,
            payment_reference=pay.reference, has_proof=bool(pay.proof_filename), submitted_at=pay.submitted_at,
            created_at=s.created_at, expires_at=s.expires_at,
        )
        for s, pl, inv, pay, u, name in rows
    ]
    return AdminSubscriptionPage(items=items, total=total, page=page, page_size=page_size, pages=max(1, math.ceil(total / page_size)))


@admin_router.get("/subscriptions/{subscription_id}/proof")
async def admin_subscription_proof(subscription_id: str, _: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    _sub, _inv, payment = await _pair(db, subscription_id)
    if not payment.proof_filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payment proof has been submitted.")
    data = await read_proof(payment.proof_filename)
    return Response(
        content=data, media_type=payment.proof_mime or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="payment-{payment.reference}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; object-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@admin_router.post("/subscriptions/{subscription_id}/payment/verify", response_model=SubscriptionOut)
async def admin_verify_payment(
    subscription_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db),
):
    sub, invoice, payment = await _pair(db, subscription_id, lock=True)
    if sub.status != "PENDING" or payment.status != "SUBMITTED" or invoice.status != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a submitted payment on a pending subscription can be verified.")
    plan = await db.get(Plan, sub.plan_id)
    if invoice.period_months != plan.period_months:
        # The member was invoiced for a different term than the plan now carries (plan data was corrected after the invoice
        # was issued). Never grant a term the invoice did not state, and never silently grant a different one.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This invoice is for {invoice.period_months} months but the {plan.name} plan is now {plan.period_months} months. "
            "Cancel this invoice and ask the member to purchase again.",
        )
    now = utcnow()
    await _claim(db, Payment, payment.id, "SUBMITTED", status="VERIFIED", verified_at=now, verified_by_admin_id=admin.id)
    payment.status, payment.verified_at, payment.verified_by_admin_id = "VERIFIED", now, admin.id
    invoice.status, invoice.paid_at, invoice.amount_paid_minor = "PAID", now, invoice.amount_due_minor
    start = now
    if sub.renews_subscription_id:
        # An early renewal (raised in the last 30 days of the running term) starts when that term ends, so the member never pays for overlapping time.
        running = await db.get(Subscription, sub.renews_subscription_id)
        if running is not None and running.status == "ACTIVE" and running.expires_at is not None and running.expires_at > now:
            start = running.expires_at
    sub.status, sub.activated_at, sub.starts_at = "ACTIVE", now, start
    sub.expires_at = add_calendar_months(start, plan.period_months)
    audit.record(db, actor=admin, action="payment.verified", resource_type="payment", resource_id=payment.id,
                 before={"payment_status": "SUBMITTED", "invoice_status": "PENDING", "subscription_status": "PENDING"},
                 after={"payment_status": "VERIFIED", "invoice_status": "PAID", "subscription_status": "ACTIVE",
                        "amount_paid_minor": invoice.amount_paid_minor, "expires_at": sub.expires_at},
                 reason=payload.reason, metadata={"subscription_id": sub.id, "invoice": invoice.number})
    notify(db, sub.user_id, "membership_activated", "Your subscription is active",
           f"Your {plan.name} plan is confirmed. Networking is open until {sub.expires_at:%d %b %Y}.", "subscription", sub.id)
    await db.commit()
    return await _bundle(db, sub)


@admin_router.post("/subscriptions/{subscription_id}/payment/reject", response_model=SubscriptionOut)
async def admin_reject_payment(
    subscription_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db),
):
    sub, invoice, payment = await _pair(db, subscription_id, lock=True)
    if sub.status != "PENDING" or payment.status != "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a submitted payment can be rejected.")
    await _claim(db, Payment, payment.id, "SUBMITTED", status="FAILED", rejection_reason=payload.reason)
    payment.status, payment.rejection_reason = "FAILED", payload.reason
    invoice.status = "FAILED"
    audit.record(db, actor=admin, action="payment.rejected", resource_type="payment", resource_id=payment.id,
                 before={"payment_status": "SUBMITTED"}, after={"payment_status": "FAILED", "invoice_status": "FAILED"}, reason=payload.reason,
                 metadata={"subscription_id": sub.id})
    notify(db, sub.user_id, "registration_submitted", "Your payment could not be verified",
           f"{payload.reason}. You can submit a new proof from the Subscription page.", "subscription", sub.id)
    await db.commit()
    return await _bundle(db, sub)


@admin_router.post("/subscriptions/{subscription_id}/refund", response_model=SubscriptionOut)
async def admin_refund(
    subscription_id: str, payload: ReasonIn, admin: Admin = Depends(get_current_admin), __: None = Depends(require_csrf), db: AsyncSession = Depends(get_db),
):
    """Record a refund TGL has made outside the system. Access ends; no money moves here."""
    sub, invoice, payment = await _pair(db, subscription_id, lock=True)
    if payment.status != "VERIFIED" or invoice.status != "PAID":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a verified, paid subscription can be refunded.")
    now = utcnow()
    before = {"payment_status": payment.status, "invoice_status": invoice.status, "subscription_status": sub.status}
    await _claim(db, Payment, payment.id, "VERIFIED", status="REFUNDED", refunded_at=now, refund_reason=payload.reason)
    payment.status, payment.refunded_at, payment.refund_reason = "REFUNDED", now, payload.reason
    invoice.status, invoice.refunded_at = "REFUNDED", now
    sub.status, sub.cancelled_at, sub.cancel_reason = "CANCELLED", now, payload.reason
    audit.record(db, actor=admin, action="payment.refunded", resource_type="payment", resource_id=payment.id, before=before,
                 after={"payment_status": "REFUNDED", "invoice_status": "REFUNDED", "subscription_status": "CANCELLED"},
                 reason=payload.reason, metadata={"subscription_id": sub.id, "amount_minor": invoice.amount_paid_minor})
    await db.commit()
    return await _bundle(db, sub)
