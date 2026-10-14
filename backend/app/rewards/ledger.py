"""Reading the shadow ledger, and the guards that keep it append-only.

A "lot" is one EARN row. Its remaining points are its own plus its children (VOID / REVERSAL / EXPIRY rows, all negative,
all pointing at it through `parent_id`). Nothing is ever edited: remaining, and whether a lot is pending, available or
expired, are derived.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..models import GrowthPointBalance, GrowthPointLedger, GrowthPointRedemptionLot, utcnow
from . import rules


@event.listens_for(GrowthPointLedger, "before_update")
@event.listens_for(GrowthPointLedger, "before_delete")
def _refuse_change(mapper, connection, target):  # noqa: ARG001 - SQLAlchemy hook signature
    raise RuntimeError("growth_point_ledger is append-only")


def pair_key(a: str, b: str) -> str:
    """Order-independent: (A, B) and (B, A) share one budget."""
    return "|".join(sorted((a, b)))


@dataclass
class Lot:
    row: GrowthPointLedger
    remaining: int
    state: str          # PENDING / AVAILABLE / EXPIRED (past its end of grace, not yet swept) / EMPTY

    @property
    def id(self) -> str:
        return self.row.id


def classify(row: GrowthPointLedger, remaining: int, now: datetime) -> str:
    if remaining <= 0:
        return "EMPTY"
    if row.expires_at is not None and rules.aware(row.expires_at) <= now:
        return "EXPIRED"
    if row.available_at is not None and rules.aware(row.available_at) > now:
        return "PENDING"
    return "AVAILABLE"


async def lots(db: AsyncSession, *, member_id: str | None = None, reference_type: str | None = None, reference_id: str | None = None,
               event_type: str | None = None, expiring_before: datetime | None = None, now: datetime | None = None) -> list[Lot]:
    """EARN lots (points > 0) with their remaining points, in one query."""
    now = now or utcnow()
    child = aliased(GrowthPointLedger)
    # REAL redemptions (app/redemption) consume lots through growth_point_redemption_lots, never by editing the earning row
    real = select(GrowthPointRedemptionLot.lot_id.label("lot_id"), func.sum(GrowthPointRedemptionLot.delta).label("delta")).group_by(GrowthPointRedemptionLot.lot_id).subquery()
    q = (
        select(GrowthPointLedger, func.coalesce(func.sum(child.points_delta), 0), func.coalesce(func.max(real.c.delta), 0))
        .outerjoin(child, child.parent_id == GrowthPointLedger.id)
        .outerjoin(real, real.c.lot_id == GrowthPointLedger.id)
        .where(GrowthPointLedger.entry_type == "EARN", GrowthPointLedger.points_delta > 0)
        .group_by(GrowthPointLedger.id)
        .order_by(GrowthPointLedger.expires_at, GrowthPointLedger.created_at, GrowthPointLedger.id)      # first in, first out by expiry
    )
    if member_id:
        q = q.where(GrowthPointLedger.member_id == member_id)
    if reference_type:
        q = q.where(GrowthPointLedger.reference_type == reference_type)
    if reference_id:
        q = q.where(GrowthPointLedger.reference_id == reference_id)
    if event_type:
        q = q.where(GrowthPointLedger.event_type == event_type)
    if expiring_before is not None:
        q = q.where(GrowthPointLedger.expires_at <= expiring_before)
    out = []
    for row, adj, red in (await db.execute(q)).all():
        remaining = row.points_delta + int(adj) + int(red)
        out.append(Lot(row=row, remaining=remaining, state=classify(row, remaining, now)))
    return out


async def member_balance(db: AsyncSession, member_id: str, now: datetime | None = None) -> dict[str, int]:
    """A member's points that still count: pending + available lots (expired, voided, reversed and redeemed points excluded). The single
    definition used by the member's own Growth Points page and by their profile."""
    found = await lots(db, member_id=member_id, now=now)
    pending = sum(l.remaining for l in found if l.state == "PENDING")
    available = sum(l.remaining for l in found if l.state == "AVAILABLE")
    return {"total": pending + available, "pending": pending, "available": available}


async def balance_row(db: AsyncSession, member_id: str) -> GrowthPointBalance:
    row = await db.get(GrowthPointBalance, member_id)
    if row is None:
        row = GrowthPointBalance(member_id=member_id, total_points=0)
        db.add(row)
        await db.flush()
    return row


async def ledger_total(db: AsyncSession, member_id: str) -> int:
    """What the member's cached balance must equal: every ledger row, plus real redemptions (negative) and their restorations (positive)."""
    base = int(await db.scalar(select(func.coalesce(func.sum(GrowthPointLedger.points_delta), 0)).where(GrowthPointLedger.member_id == member_id)) or 0)
    real = int(await db.scalar(select(func.coalesce(func.sum(GrowthPointRedemptionLot.delta), 0)).where(GrowthPointRedemptionLot.member_id == member_id)) or 0)
    return base + real
