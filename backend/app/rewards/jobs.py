"""Scheduled / on-demand reward maintenance: expiry, voiding, backfill. All idempotent, all shadow.

    python -m app.rewards.jobs            # one sweep (cron it, e.g. hourly), then exits
    POST /api/admin/growth-points/sweep    # the same, from the admin dashboard

A sweep never deletes or edits anything: expiry, voids and reversals are NEW ledger rows.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BusinessReferral, DealClosure, GrowthPointRenewal, PersonalProfile, Subscription, TGLMembership, utcnow
from . import engine, events, firewall, fraud, ledger, reconcile, renewal

log = logging.getLogger("tgl.rewards")


async def expire_due(db: AsyncSession, now: datetime | None = None) -> int:
    """Write an EXPIRY row for every lot whose renewal window plus grace has ended with points left."""
    now = now or utcnow()
    n = 0
    for lot in await ledger.lots(db, expiring_before=now, now=now):
        if lot.state == "EXPIRED" and await engine.adjust(db, lot, "EXPIRY", "Not used by the end of the grace period after the cycle they were earned in"):
            n += 1
    return n


async def resync_pending(db: AsyncSession, now: datetime | None = None) -> int:
    """Re-check the references behind pending points, so a referral that was closed or a deal that was disputed voids them."""
    now = now or utcnow()
    refs = {(l.row.reference_type, l.row.reference_id) for l in await ledger.lots(db, now=now) if l.state in ("PENDING", "AVAILABLE")}
    n = 0
    for kind, rid in sorted(refs):
        if kind == "referral":
            n += (await events.sync_referral(db, rid, now))["voided"]
        elif kind == "deal_closure":
            n += (await events.sync_closure(db, rid, now))["reversed"]
    return n


async def backfill(db: AsyncSession, now: datetime | None = None, limit: int = 500) -> dict:
    """Issue any reward the hooks missed (a crash between the business commit and the reward). Idempotent."""
    now = now or utcnow()
    out = {"referrals": 0, "closures": 0, "profiles": 0}
    ids = (await db.execute(select(BusinessReferral.id).where(BusinessReferral.accepted_at.is_not(None))
                            .order_by(BusinessReferral.updated_at.desc()).limit(limit))).scalars().all()
    for rid in ids:
        out["referrals"] += (await events.sync_referral(db, rid, now))["awarded"]
    cids = (await db.execute(select(DealClosure.id).where(DealClosure.status == "VERIFIED").order_by(DealClosure.updated_at.desc()).limit(limit))).scalars().all()
    for cid in cids:
        out["closures"] += (await events.sync_closure(db, cid, now))["awarded"]
    uids = (await db.execute(select(PersonalProfile.user_id).order_by(PersonalProfile.updated_at.desc()).limit(limit))).scalars().all()
    for uid in uids:
        out["profiles"] += (await events.sync_profile(db, uid, now))["awarded"]
    return out


async def renewals(db: AsyncSession, now: datetime | None = None, limit: int = 200) -> dict:
    """Record the hypothetical use of old-cycle points for every paid renewal not yet recorded (idempotent), and flag any recorded renewal
    whose subscription was later refunded (the points are NOT restored in Phase 1; an admin looks at it). Reads subscriptions; writes only
    shadow rows. Runs BEFORE expiry in a sweep so points that were eligible at the renewal are not swept away first."""
    if firewall.redemption_enabled():
        return {"recorded": 0, "redeemed_hypothetically": 0, "refund_flags": 0, "skipped": "real redemption is enabled: the shadow simulation no longer runs"}
    other_sub = Subscription.__table__.alias("other_sub")
    candidates = (await db.execute(
        select(Subscription.id).outerjoin(GrowthPointRenewal, GrowthPointRenewal.new_subscription_id == Subscription.id)
        .where(Subscription.status == "ACTIVE", GrowthPointRenewal.id.is_(None),
               or_(exists().where(other_sub.c.user_id == Subscription.user_id, other_sub.c.id != Subscription.id),
                   exists().where(TGLMembership.user_id == Subscription.user_id)))
        .order_by(Subscription.activated_at, Subscription.id).limit(limit))).scalars().all()
    out = {"recorded": 0, "redeemed_hypothetically": 0, "refund_flags": 0}
    for sid in candidates:
        header, created = await renewal.record(db, sid, now)
        if created:
            out["recorded"] += 1
            out["redeemed_hypothetically"] += header.redeemed_points
    refunded = (await db.execute(
        select(GrowthPointRenewal).join(Subscription, Subscription.id == GrowthPointRenewal.new_subscription_id)
        .where(GrowthPointRenewal.outcome == "REDEEMED", Subscription.status == "CANCELLED"))).scalars().all()
    for r in refunded:
        out["refund_flags"] += int(await fraud.raise_flag(
            db, "RENEWAL_REFUNDED", "HIGH", member_id=r.member_id, reference_type="renewal", reference_id=r.id, dedupe=r.id,
            details={"redeemed_points": r.redeemed_points, "why": "a renewal that used old-cycle points (hypothetically) was refunded; restoring points is a future redemption-policy decision"}))
    return out


async def reconcile_alert(db: AsyncSession) -> dict:
    """Run reconciliation and raise an admin alert (a HIGH review flag, once per distinct finding) for anything that does not add up.
    It never repairs anything: a correction is a separate, audited, explained act (admin 'Reconcile' rebuilds the derived balance cache only)."""
    import hashlib
    import json
    result = await reconcile.reconcile(db)
    new = 0
    for kind, items in (("drift", result["drift"]), ("violation", result["violations"])):
        for item in items:
            digest = hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()[:24]
            new += int(await fraud.raise_flag(db, "RECONCILIATION_MISMATCH", "HIGH", member_id=item.get("member_id"), dedupe=f"{kind}:{digest}",
                                              details={"kind": kind, **{k: v for k, v in item.items() if k != "member_id"}}))
    return {"ok": result["ok"], "members_checked": result["members_checked"], "findings": len(result["drift"]) + len(result["violations"]), "new_alerts": new}


async def sweep(db: AsyncSession, now: datetime | None = None, backfill_limit: int = 500) -> dict:
    now = now or utcnow()
    with firewall.guard():
        result = {"backfilled": await backfill(db, now, backfill_limit)}
        result["voided_or_reversed"] = await resync_pending(db, now)
        from ..redemption import service as redemption_service          # imported late: the redemption package imports this one
        result["redemption_reversals"] = await redemption_service.reverse_dead_renewals(db, now)
        result["renewals"] = await renewals(db, now)
        result["expired"] = await expire_due(db, now)
        result["reconciliation"] = await reconcile_alert(db)
    return result


async def _main() -> None:
    from ..database import SessionLocal
    if not firewall.shadow_enabled():
        print("GROWTH_POINTS_SHADOW_MODE is off: nothing to do.")
        return
    async with SessionLocal() as db:
        res = await sweep(db)
        await db.commit()
    print("sweep:", res)
    if not res["reconciliation"]["ok"]:
        raise SystemExit(1)                                  # a failing exit code lets cron or a monitor alert on it


if __name__ == "__main__":
    asyncio.run(_main())
