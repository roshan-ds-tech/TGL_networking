"""Subscription foundation: plans, purchase, invoice, payment.

Lifecycle (statuses are only ever set by the server):

    PLAN -> SUBSCRIPTION (PENDING) + INVOICE (ISSUED) + PAYMENT (PENDING)
         -> member uploads proof: PAYMENT SUBMITTED, INVOICE PENDING
         -> admin verifies:       PAYMENT VERIFIED, INVOICE PAID, SUBSCRIPTION ACTIVE  (= access)
            admin rejects:        PAYMENT FAILED,  INVOICE FAILED   (member may submit again)
         -> admin refunds:        PAYMENT REFUNDED, INVOICE REFUNDED, SUBSCRIPTION CANCELLED
         -> member cancels (unpaid): SUBSCRIPTION CANCELLED, INVOICE CANCELLED, PAYMENT FAILED
         -> the period ends:      SUBSCRIPTION EXPIRED (access also stops by date, whatever the stored status)

TGL takes payments by manual proof that an admin verifies; there is no payment
gateway and none is pretended here. No Growth Point discount exists: the invoice
carries a discount column that a database CHECK holds at zero.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import audit
from .config import settings
from .models import Invoice, Payment, Plan, Subscription, utcnow

SEASON_SLUG = "season-1"

# THE canonical plan definitions: the one place a plan's price and TERM are written down.
# (code, name, price in paise, term in months, sort order)
#
#     Connect  Rs 3,000   3 months
#     Growth   Rs 5,000   6 months
#     Elite    Rs 10,000 12 months
#
# Everything else reads the plan ROW, never a constant: invoices copy price and term from the row at purchase,
# verification adds `period_months` to the start date, and the member screens show what the API returns.
# Migration 0009 carries its own point-in-time copy (a migration must never change when code does);
# test_plan_terms.py fails if that copy and this table ever disagree.
DEFAULT_PLANS = (
    ("connect", "Connect", 3_000 * 100, 3, 1),
    ("growth", "Growth", 5_000 * 100, 6, 2),
    ("elite", "Elite", 10_000 * 100, 12, 3),
)


async def ensure_default_plans(db: AsyncSession) -> int:
    """Development and tests only (production gets plans from migrations 0008 and 0009).

    Creates a missing canonical plan. For an existing one it never touches the name, price or status (a price an
    admin changed, or a plan archived, is not reset by a restart) but it does correct a TERM that differs from the
    canonical one: databases created before the correction were seeded with 3 months for every plan, which is data
    that was simply wrong. Invoices keep the term they were issued with. Returns the number of rows created or corrected."""
    have = {p.code: p for p in (await db.execute(select(Plan))).scalars().all()}
    changed = 0
    for code, name, price, months, order in DEFAULT_PLANS:
        row = have.get(code)
        if row is None:
            db.add(Plan(
                code=code, name=name, price_minor=price, currency="INR", period_months=months,
                season_slug=SEASON_SLUG, status="ACTIVE", sort_order=order,
            ))
            changed += 1
        elif row.period_months != months:
            row.period_months = months
            changed += 1
    return changed


def new_invoice_number() -> str:
    return f"INV-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(4).upper()}"


def new_payment_reference() -> str:
    return f"TGLS-{secrets.token_hex(4).upper()}"


def plan_is_purchasable(plan: Plan, now: datetime | None = None) -> bool:
    now = now or utcnow()
    start = plan.effective_from if plan.effective_from.tzinfo else plan.effective_from.replace(tzinfo=timezone.utc)
    end = plan.effective_to
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return plan.status == "ACTIVE" and start <= now and (end is None or now < end)


def build_purchase(user_id: str, plan: Plan) -> tuple[Subscription, Invoice, Payment]:
    """The three records for one purchase. The price comes from the plan row, never from the client."""
    now = utcnow()
    sub = Subscription(user_id=user_id, plan_id=plan.id, status="PENDING")
    invoice = Invoice(
        number=new_invoice_number(), user_id=user_id, plan_id=plan.id, season_slug=plan.season_slug,
        currency=plan.currency, plan_name=plan.name, period_months=plan.period_months,
        list_price_minor=plan.price_minor, amount_before_discount_minor=plan.price_minor,
        discount_minor=0, amount_due_minor=plan.price_minor, amount_paid_minor=0,
        status="ISSUED", issued_at=now,
    )
    payment = Payment(
        user_id=user_id, method="MANUAL_PROOF", amount_minor=plan.price_minor, currency=plan.currency,
        status="PENDING", reference=new_payment_reference(),
    )
    return sub, invoice, payment


# Words that mean "someone forgot to fill this in". Payment details containing any of them are
# treated as NOT configured, so a template or sample can never reach a member as real instructions.
_PLACEHOLDER_MARKERS = ("todo", "tbd", "changeme", "change_me", "change-me", "replace", "placeholder", "xxxx", "your-", "<", "lorem", "example", "sample", "dummy")


def payment_instructions() -> str | None:
    """The official payment instructions for subscription invoices, or None when management has not
    supplied them. TGL's bank / UPI details are never invented or defaulted in code."""
    text = (settings.subscription_payment_instructions or "").strip()
    if not text or any(marker in text.lower() for marker in _PLACEHOLDER_MARKERS):
        return None
    return text


async def expire_stale(db: AsyncSession, user_id: str) -> int:
    """Flip this member's ACTIVE subscriptions whose period has ended to EXPIRED (audited).

    Access never depends on this having run: every access check also requires
    `expires_at > now`, so a stale ACTIVE row grants nothing. This only keeps the stored status
    truthful and lets the member buy again. Call it before reading or creating a subscription;
    the caller commits."""
    now = utcnow()
    ids = (await db.execute(select(Subscription.id).where(
        Subscription.user_id == user_id, Subscription.status == "ACTIVE", Subscription.expires_at.is_not(None), Subscription.expires_at <= now,
    ))).scalars().all()
    flipped = 0
    for sub_id in ids:
        res = await db.execute(update(Subscription).where(Subscription.id == sub_id, Subscription.status == "ACTIVE").values(status="EXPIRED", updated_at=now))
        if res.rowcount:
            flipped += 1
            audit.record(db, actor=None, action="subscription.expired", resource_type="subscription", resource_id=sub_id,
                         before={"status": "ACTIVE"}, after={"status": "EXPIRED"}, reason="Period ended")
    return flipped
