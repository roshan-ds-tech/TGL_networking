"""HYPOTHETICAL, READ-ONLY, SHADOW-ONLY evaluation: replay the genuine Phase A community history through the PROPOSED (unapproved) Community rewards.

    python scripts/community_candidate_evaluation.py [--since 2027-01-01] [--default-plan connect] [--json]

What it is
  * a pure replay: it SELECTs from community_events (and plans/subscriptions to know each member's ceiling) and feeds the result to the reference model in
    docs/growth_points_model/community_candidate_model.py. It opens a session, never commits, never writes, creates no table, no ledger row, no
    Growth Point, no notification and no balance. Run it against a COPY or a replica; on production it is still read-only.
  * it counts ONLY genuine activity: synthetic demo members (the reserved demo e-mail domain, exactly as Gate A does) and backfilled history
    (reason_code BACKFILL, written when the feature was installed) are excluded. Observation starts only on a deployed environment with real use;
    until then this prints "no genuine activity" and stops. It never claims Gate A.
  * every figure is labelled HYPOTHETICAL: "if the proposed rules were in force, these events would have requested X points and been awarded Y".
    A result is not a Growth Point, not a balance and not redeemable, and it is not evidence that the proposal is approved.
  * the database session is put in read-only mode (PostgreSQL SET TRANSACTION READ ONLY, SQLite PRAGMA query_only) so a write could not succeed even by mistake;
    on a database without the Phase A tables it stops with exit code 2 and says why, instead of reporting zero.
  * output is aggregate only: counts, points and rule names. No member id, name, e-mail, message or pair is printed.

What it cannot see (Phase A does not record it, so the replay is a LOWER bound): successful introductions and their meetings, and the existing v3
Process / Closure points a member earns in the same month (those would consume the monthly 3,000 limit and the cycle ceiling).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "docs" / "growth_points_model"))

import community_candidate_model as cm  # noqa: E402

LABEL = "HYPOTHETICAL — proposed rules, NOT approved, NOT awarded, NOT a balance"
PLAN_PRICE_MINOR = {"connect": 300_000, "growth": 500_000, "elite": 1_000_000}      # fallback when a member has no subscription row (minor units)


def to_candidate_events(rows: list[dict]) -> list[cm.Event]:
    """Map Phase A history rows (dicts with id, domain, kind, at, actor, subject, reason) to candidate events. Pure; used by the test too.

    CONNECTION/ACCEPTED -> both members earn a CONNECTION_ACCEPTED (counterparty = the other)
    NEED/PUBLISHED      -> the poster earns NEED_PUBLISHED (the model's monthly limit of 2 decides which count; a tracked reason is ignored here)
    HELP/CONFIRMED_HELPFUL (actor = poster, subject = helper) -> the helper earns NEED_HELP_CONFIRMED
    NEED/RESOLVED       -> the credited helper earns NEED_RESOLVED and the poster earns NEED_CLOSED, only when a helper was credited
    Everything else (requests, offers, declines, signals, removals) earns nothing and is not mapped.
    """
    out: list[cm.Event] = []
    for r in sorted(rows, key=lambda x: (x["at"], x["id"])):
        at, d, k, a, s = r["at"], r["domain"], r["kind"], r.get("actor"), r.get("subject")
        if d == "CONNECTION" and k == "ACCEPTED" and a and s:
            out.append(cm.Event(f"{r['id']}:a", a, "CONNECTION_ACCEPTED", at, counterparty=s))
            out.append(cm.Event(f"{r['id']}:b", s, "CONNECTION_ACCEPTED", at, counterparty=a))
        elif d == "NEED" and k == "PUBLISHED" and a:
            out.append(cm.Event(f"{r['id']}:p", a, "NEED_PUBLISHED", at))
        elif d == "HELP" and k == "CONFIRMED_HELPFUL" and a and s:
            out.append(cm.Event(f"{r['id']}:h", s, "NEED_HELP_CONFIRMED", at, counterparty=a))
        elif d == "NEED" and k == "RESOLVED" and a and s:
            out.append(cm.Event(f"{r['id']}:r", s, "NEED_RESOLVED", at, counterparty=a))
            out.append(cm.Event(f"{r['id']}:c", a, "NEED_CLOSED", at, counterparty=s))
    return out


def summarise(events: list[cm.Event], decisions: list[cm.Decision], model: cm.Model) -> dict:
    by_kind: dict[str, dict] = {}
    cuts: Counter = Counter()
    for dec in decisions:
        row = by_kind.setdefault(dec.event.kind, {"events": 0, "requested": 0, "awarded": 0})
        row["events"] += 1
        row["requested"] += dec.requested
        row["awarded"] += dec.awarded
        if dec.capped_by and dec.awarded < dec.requested:
            cuts[dec.capped_by] += 1
    per_member = sorted(c.total for c in model.cycles.values())
    requested, awarded = sum(r["requested"] for r in by_kind.values()), sum(r["awarded"] for r in by_kind.values())
    return {
        "label": LABEL,
        "events_replayed": len(decisions),
        "members_with_hypothetical_points": sum(1 for v in per_member if v),
        "requested_points": requested,
        "hypothetical_awarded_points": awarded,
        "hypothetical_rupee_value": round(awarded * 0.10, 2),
        "by_kind": by_kind,
        "events_reduced_by_rule": dict(cuts),
        "per_member_points": {"min": per_member[0] if per_member else 0, "median": per_member[len(per_member) // 2] if per_member else 0, "max": per_member[-1] if per_member else 0},
        "not_visible": ["successful introductions and meetings (not recorded in Phase A)", "existing v3 Process/Closure points that share the monthly and cycle limits"],
    }


class SchemaNotReady(RuntimeError):
    """The database is not at a revision this tool understands (it needs the Phase A tables, migration 0013 or later)."""


MIN_OBSERVATION_DAYS = 91                                                          # one full quarter; two are preferred (proposal, observation requirements)


async def _load(since: datetime | None, default_plan: str) -> tuple[list[dict], dict[str, int], int, int, int]:
    from sqlalchemy import and_, func, inspect, or_, select, text

    from app import demo
    from app.database import SessionLocal
    from app.models import CommunityEvent as E, Plan, Subscription, User

    async with SessionLocal() as db:
        # Enforce read-only at the database, not just by promise: a write attempted by any future edit fails instead of landing.
        dialect = db.bind.dialect.name
        if dialect == "postgresql":
            await db.execute(text("SET TRANSACTION READ ONLY"))
        elif dialect == "sqlite":
            await db.execute(text("PRAGMA query_only = ON"))
        tables = set(await (await db.connection()).run_sync(lambda c: inspect(c).get_table_names()))
        missing = {"community_events", "users", "plans", "subscriptions"} - tables
        if missing:
            raise SchemaNotReady(f"missing table(s): {', '.join(sorted(missing))}. Migration 0013 (Phase A) has not been applied to this database.")
        synthetic = select(User.id).where(demo.synthetic_clause())
        genuine = and_(or_(E.actor_user_id.is_(None), E.actor_user_id.not_in(synthetic)), or_(E.subject_user_id.is_(None), E.subject_user_id.not_in(synthetic)),
                       or_(E.reason_code.is_(None), E.reason_code != "BACKFILL"))
        q = select(E.id, E.domain, E.kind, E.created_at, E.actor_user_id, E.subject_user_id).where(genuine, E.domain.in_(("CONNECTION", "NEED", "HELP")))
        if since is not None:
            q = q.where(E.created_at >= since)
        rows = [{"id": i, "domain": d, "kind": k, "at": (c if c.tzinfo else c.replace(tzinfo=timezone.utc)), "actor": a, "subject": s} for i, d, k, c, a, s in (await db.execute(q)).all()]
        excluded = int(await db.scalar(select(func.count(E.id)).where(~genuine)) or 0)
        # each member's plan price: the latest ACTIVE (else any) subscription; members without one use --default-plan
        prices: dict[str, int] = {}
        for uid, price in (await db.execute(select(Subscription.user_id, Plan.price_minor).join(Plan, Plan.id == Subscription.plan_id).order_by(Subscription.created_at))).all():
            prices[uid] = int(price)
        await db.rollback()                                                           # nothing was written; make that explicit
    fallback = PLAN_PRICE_MINOR[default_plan]
    ids = {x for r in rows for x in (r["actor"], r["subject"]) if x}
    return rows, {u: prices.get(u, fallback) for u in ids}, excluded, fallback, sum(1 for u in ids if u not in prices)


async def main_async(args) -> int:
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
    try:
        rows, prices, excluded, fallback, assumed = await _load(since, args.default_plan)
    except SchemaNotReady as exc:
        print(f"Cannot evaluate: {exc}", file=sys.stderr)
        return 2
    if not rows:
        msg = {"label": LABEL, "genuine_events": 0, "synthetic_or_backfilled_events_excluded": excluded,
               "result": "no genuine community activity yet: nothing to evaluate. Observation has not started (it starts only after deployment to an authorised environment with real use)."}
        print(json.dumps(msg, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in msg.items()))
        return 0
    events = to_candidate_events(rows)
    model = cm.Model({m: prices.get(m, fallback) for m in {e.member for e in events}})
    decisions = model.run(events)
    first, last = min(r["at"] for r in rows), max(r["at"] for r in rows)
    covered = (last - first).days
    window = {"first_genuine_event": first.isoformat(), "last_genuine_event": last.isoformat(), "days_between_first_and_last": covered,
              "full_quarter_observed": covered >= MIN_OBSERVATION_DAYS,
              "note": "descriptive only: observation is judged by management, from the first genuine event on an authorised environment; this is not Gate A"}
    result = summarise(events, decisions, model) | {"synthetic_or_backfilled_events_excluded": excluded, "observation_window": window,
                                                    "members_priced_by_assumed_plan": assumed, "assumed_plan_for_members_without_subscription": args.default_plan}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(LABEL)
        for k, v in result.items():
            if k != "label":
                print(f"  {k}: {v}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", help="ISO date; only events on or after it (UTC midnight)")
    ap.add_argument("--default-plan", choices=sorted(PLAN_PRICE_MINOR), default="connect", help="ceiling to assume for a member with no subscription row")
    ap.add_argument("--json", action="store_true")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
