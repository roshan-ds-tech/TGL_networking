"""The management review pack for the shadow observation period (Gate A).

Everything is computed from the shadow ledger and the Phase 0 records and is READ-ONLY. Nothing here changes the economic model:
where real data differs materially from the model it produces a PROPOSED MODEL CHANGE and waits for management. It never
decides pass/fail on its own: `gate_a.suggested_status` is a suggestion, only management approves moving on.

The thresholds below are ANALYSIS thresholds (where a human should look), not business rules.
CLI:  python -m app.rewards.review            prints the Markdown report
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BusinessReferral, GrowthPointFlag, GrowthPointLedger, utcnow
from .. import demo
from . import analytics, reconcile, rules

L = GrowthPointLedger

MIN_ACTIVE_MEMBERS = 30                   # fewer members than this and a percentile means little
MIN_OBSERVED_DAYS = 30
MATERIAL_COST_FACTOR = 1.5                # projected cost above 1.5x the modelled share of revenue is material
CEILING_BINDING_SHARE_PERCENT = 25        # more than a quarter of cycles in the top tier (>= 75 % of their ceiling)
CONCENTRATION_TOP1_PERCENT = 25           # the top 1 % of members holding more than a quarter of all points
LOW_MEDIAN_PERCENT_OF_CEILING = 5         # a typical member under 5 % of their ceiling is not earning anything meaningful
CAPPED_SHARE_PERCENT = 20                 # more than a fifth of recorded rewards reduced by a ceiling or pair rule


def _i(v) -> int:
    return int(v or 0)


async def _dashboard(db: AsyncSession, ob: dict, summary: dict, now: datetime) -> dict:
    started = ob["observed"]["observation_started"]
    since = started or now
    count = lambda *w: select(func.count(func.distinct(L.reference_id))).where(L.entry_type == "EARN", L.points_delta > 0, *w)       # noqa: E731
    activity = {
        "referrals_created": _i(await db.scalar(select(func.count(BusinessReferral.id)).where(BusinessReferral.created_at >= since))),
        "referrals_accepted": _i(await db.scalar(select(func.count(BusinessReferral.id)).where(BusinessReferral.accepted_at.is_not(None), BusinessReferral.accepted_at >= since))),
        "referrals_contacted": _i(await db.scalar(select(func.count(BusinessReferral.id)).where(BusinessReferral.contacted_at.is_not(None), BusinessReferral.contacted_at >= since))),
        "meetings_verified": _i(await db.scalar(count(L.event_type == "MEETING_COMPLETED"))),
        "businesses_closed": _i(await db.scalar(count(L.event_type == "BUSINESS_CLOSED"))),
        "repeat_business": _i(await db.scalar(count(L.event_type == "REPEAT_BUSINESS"))),
        "profiles_completed": _i(await db.scalar(select(func.count(L.id)).where(L.entry_type == "EARN", L.event_type == "PROFILE_COMPLETED", L.points_delta > 0))),
    }
    sums = (await db.execute(select(
        func.coalesce(func.sum(case((L.entry_type == "EARN", L.requested_points), else_=0)), 0),
        func.coalesce(func.sum(case((L.entry_type == "EARN", L.points_delta), else_=0)), 0),
        func.coalesce(func.sum(case((L.entry_type == "EARN", L.capped_points), else_=0)), 0)))).one()
    hyp = summary["hypothetical_redemption"]
    led = ob["success_metrics"]["ledger"]
    rewards = {
        "points_requested": _i(sums[0]), "points_awarded": _i(sums[1]), "points_capped": _i(sums[2]), "points_expired": led["points_expired"],
        "points_reversed": led["points_reversed"], "points_voided": led["points_voided"], "points_pending": hyp["pending_points"], "points_available": hyp["available_points"],
        "capped_by_rule": summary["shadow_earning"]["capped"]["by_rule"],
    }
    kinds = ob["success_metrics"]["fraud_flags"]["by_kind"]
    risk = {
        "pair_concentration_flags": kinds.get("PAIR_CONCENTRATION", 0), "reciprocal_referral_flags": kinds.get("RECIPROCAL_REFERRALS", 0), "rapid_closure_flags": kinds.get("RAPID_CLOSURE", 0),
        "repeated_prospect_flags": kinds.get("SAME_PROSPECT_ACROSS_PAIRS", 0), "high_value_closure_flags": kinds.get("HIGH_VALUE_CLOSURE", 0),
        "reversal_review_flags": kinds.get("REVERSAL_NEEDS_REVIEW", 0), "all_fraud_flags": ob["success_metrics"]["fraud_flags"]["total"], "open_flags": ob["success_metrics"]["fraud_flags"]["open"],
        "reciprocal_pairs": ob["success_metrics"]["repeat_and_circular_patterns"]["reciprocal_pairs"],
        "top_pair_share_of_closed_business_points_percent": ob["success_metrics"]["repeat_and_circular_patterns"]["top_pair_share_of_closed_business_points_percent"],
        "note": "Flags are signals for a human. Nothing is punished automatically.",
    }
    sm = ob["success_metrics"]
    economic = {
        "hypothetical_point_value_paise": rules.PAISE_PER_POINT, "hypothetical_redemption_now_paise": sm["hypothetical_redemption_cost_now_paise"],
        "hypothetical_annual_reward_cost_projected_paise": sm["hypothetical_annual_liability_projected_paise"], "hypothetical_annual_reward_cost_worst_case_paise": sm["hypothetical_annual_liability_worst_case_paise"],
        "hypothetical_reward_cost_percent_of_revenue": sm["hypothetical_reward_cost_percent_of_subscription_revenue"], "maximum_potential_liability_now_paise": sm["maximum_potential_redemption_cost_now_paise"],
        "actual_plan_mix": ob["observed"]["plan_mix"], "actual_plan_mix_percent": ob["observed"]["plan_mix_percent"], "real_financial_cost": ob["real_financial_cost"],
        "label": "HYPOTHETICAL / SHADOW: not a cost TGL has incurred.",
    }
    return {"member_metrics": sm["points_per_member"], "points_by_plan": sm["points_by_plan"], "points_by_cycle_length": sm["points_by_cycle_length"],
            "activity_metrics": activity, "reward_metrics": rewards, "risk_metrics": risk, "economic_metrics": economic}


def _proposals(ob: dict, summary: dict, dash: dict) -> tuple[list[dict], str]:
    """PROPOSED MODEL CHANGEs, only once there is enough data, and only where the real data differs materially from the model."""
    suff = ob["sufficiency"]
    if suff["active_members"] < MIN_ACTIVE_MEMBERS or suff["observed_days"] < MIN_OBSERVED_DAYS:
        return [], f"No proposals yet: need at least {MIN_ACTIVE_MEMBERS} active members and {MIN_OBSERVED_DAYS} days of data (have {suff['active_members']} and {suff['observed_days']})."
    out: list[dict] = []
    dist = ob["success_metrics"]["points_per_member"]
    cost = ob["success_metrics"]["hypothetical_reward_cost_percent_of_subscription_revenue"]["projected"]
    modelled = ob["modelled_vs_actual"]["expected_cost_percent_of_revenue"]["modelled"]

    def add(topic, current, observed, impact, recommend):
        out.append({"topic": topic, "current_rule": current, "observed_behavior": observed, "financial_impact": impact, "recommended_change": recommend,
                    "status": "PROPOSED: awaiting management approval. The model is NOT changed automatically."})

    if cost is not None and cost > modelled * MATERIAL_COST_FACTOR:
        add("Reward cost above the model", "12% earning ceiling, 15% redemption cap", f"projected hypothetical cost {cost}% of revenue vs {modelled}% modelled",
            f"about {round(cost - modelled, 2)} percentage points of revenue more than modelled", "review the earning ceiling and the reward values before any redemption is switched on")
    tiers = summary["shadow_earning"]["distribution_of_cycles_by_share_of_ceiling"]
    cycles = sum(tiers.values())
    if cycles and tiers.get("Top", 0) * 100 / cycles > CEILING_BINDING_SHARE_PERCENT:
        add("The 12% ceiling binds for many members", "12% of plan price per cycle", f"{tiers['Top']} of {cycles} cycles are at 75% or more of their ceiling",
            "points are already capped for those members; raising the ceiling raises the worst case towards 15% of revenue", "decide whether the ceiling is doing its job (cost control) or discouraging activity")
    if dist["top_1_percent_share_of_points_percent"] > CONCENTRATION_TOP1_PERCENT:
        add("Rewards concentrated in very few members", "no per-member share limit (ceilings per cycle only)", f"the top 1% of members hold {dist['top_1_percent_share_of_points_percent']}% of all points",
            "cost is driven by a handful of members, so it is sensitive to their behaviour and to gaming", "review the top members' activity for genuineness; consider whether a different sub-ceiling is needed")
    ceilings = [p["cycle_ceiling_points"] for p in ob["success_metrics"]["points_by_plan"]]
    if ceilings and dist["median"] * 100 < min(ceilings) * LOW_MEDIAN_PERCENT_OF_CEILING:
        add("A typical member earns very little", "reward values per event", f"median {dist['median']} points per member against ceilings of {min(ceilings)}+",
            "low cost, but the reward may not motivate", "review whether the event values are meaningful or whether the activity is simply low")
    rec = dash["reward_metrics"]
    if rec["points_requested"] and rec["points_capped"] * 100 / rec["points_requested"] > CAPPED_SHARE_PERCENT:
        add("Many rewards are reduced by a ceiling or pair rule", "pair rules, 500 daily, 3,000 monthly, cycle and sub-ceilings", f"{round(rec['points_capped'] * 100 / rec['points_requested'], 1)}% of requested points were capped",
            "members receive less than the reward table suggests", "check which rule caps most (see capped_by_rule) and whether it is intended")
    return out, ("Proposals are listed below; management decides." if out else "Real data does not differ materially from the model on the measured points.")


def _exit_criteria(ob: dict, summary: dict, dash: dict, quality: dict) -> list[dict]:
    """The ten questions of the observation exit. Each gets the evidence; a human answers."""
    dist = ob["success_metrics"]["points_per_member"]
    suff = ob["sufficiency"]
    enough = suff["active_members"] >= MIN_ACTIVE_MEMBERS and suff["observed_days"] >= MIN_OBSERVED_DAYS
    tiers = summary["shadow_earning"]["distribution_of_cycles_by_share_of_ceiling"]
    cycles = sum(tiers.values())
    cost = ob["success_metrics"]["hypothetical_reward_cost_percent_of_subscription_revenue"]
    ren = ob["success_metrics"]["renewals"]
    plans = ob["success_metrics"]["points_by_plan"]
    deals = dash["activity_metrics"]["businesses_closed"]
    closure_pts = sum(e["points_issued"] for e in summary["shadow_earning"]["by_event_type"] if e["event_type"] in ("BUSINESS_CLOSED", "REPEAT_BUSINESS"))
    total_pts = summary["shadow_earning"]["points_issued"]

    def q(n, question, evidence, ok):
        ind = "NEEDS MORE DATA" if not enough else ("SUPPORTS" if ok else "CONCERN")
        return {"n": n, "question": question, "evidence": evidence, "indication": ind, "answered_by": "management"}

    return [
        q(1, "Are normal members earning meaningful rewards?", f"median {dist['median']} points, average {dist['average']}, P90 {dist['p90']} (a point is worth Rs 0.10)", dist["median"] >= 100),
        q(2, "Are top members hitting ceilings?", f"{tiers.get('Top', 0)} of {cycles} cycles are at 75% or more of their ceiling", True),
        q(3, "Are rewards concentrated among a few members?", f"top 1% hold {dist['top_1_percent_share_of_points_percent']}% of points; max {dist['max']}", dist["top_1_percent_share_of_points_percent"] <= CONCENTRATION_TOP1_PERCENT),
        q(4, "Are members gaming referrals?", f"{dash['risk_metrics']['all_fraud_flags']} flags ({dash['risk_metrics']['open_flags']} open), {dash['risk_metrics']['reciprocal_pairs']} reciprocal pairs, top pair {dash['risk_metrics']['top_pair_share_of_closed_business_points_percent']}% of closed-business points",
          dash["risk_metrics"]["open_flags"] == 0 and dash["risk_metrics"]["top_pair_share_of_closed_business_points_percent"] <= 50),
        q(5, "Are business outcomes genuinely driving rewards?", f"{deals} verified closed deals; closed business is {round(closure_pts * 100 / total_pts, 1) if total_pts else 0}% of points", deals > 0 and (not total_pts or closure_pts * 100 / total_pts >= 20)),
        q(6, "Is hypothetical liability within acceptable limits?", f"projected {cost['projected']}% of revenue, worst case {cost['worst_case']}%, outstanding now {cost['outstanding_now']}%", cost["projected"] is not None and cost["projected"] <= 12),
        q(7, "Is the 12% earning model still economically appropriate?", f"modelled {ob['modelled_vs_actual']['expected_cost_percent_of_revenue']['modelled']}% vs projected {ob['modelled_vs_actual']['expected_cost_percent_of_revenue']['actual_projected']}% of revenue",
          ob["modelled_vs_actual"]["expected_cost_percent_of_revenue"]["actual_projected"] is not None and ob["modelled_vs_actual"]["expected_cost_percent_of_revenue"]["actual_projected"] <= 12),
        q(8, "Is the 15% redemption cap still appropriate?", f"{ren['renewals_that_used_points']} of {ren['renewals_recorded']} renewals used points; average {ren['average_old_cycle_points_redeemed_per_renewal']} points; hypothetical discount {ren['hypothetical_discount_total_paise']} paise in total",
          ren["renewals_recorded"] > 0),
        q(9, "Are expiry and renewal rules behaving correctly?", f"expired {ren['points_expired_before_redemption']} (stranded by non-renewal {ren['points_stranded_by_non_renewal']}); renewal outcomes {ren['outcomes']}; reconciliation {'clean' if quality['reconciliation_ok'] else 'NOT CLEAN'}",
          ren["renewals_recorded"] > 0 and quality["reconciliation_ok"]),
        q(10, "Are plan-level rewards fair across 3/6/12-month subscriptions?", "; ".join(f"{p['plan']}: " + (f"{p['points_per_member_per_year_normalised']} points per member-year" if p["points_per_member_per_year_normalised"] is not None else "not enough member-months yet") + f" ({p['worst_case_percent_of_price']}% of price worst case)" for p in plans) or "no data",
          bool(plans) and len({p["worst_case_percent_of_price"] for p in plans}) == 1),
    ]


async def _quality(db: AsyncSession) -> dict:
    """The quality checks a review must pass before the numbers can be trusted: no ledger drift, no ceiling or renewal violation, no
    duplicate reward (structurally impossible: unique idempotency key, still counted), no unresolved HIGH-severity flag, no real financial cost."""
    rec = await reconcile.reconcile(db)
    dup = _i(await db.scalar(select(func.count()).select_from(select(L.idempotency_key).group_by(L.idempotency_key).having(func.count(L.id) > 1).subquery())))
    high_open = _i(await db.scalar(select(func.count(GrowthPointFlag.id)).where(GrowthPointFlag.status == "OPEN", GrowthPointFlag.severity == "HIGH")))
    cost = await analytics.real_financial_cost(db)
    checks = {"reconciliation_ok": bool(rec["ok"]), "ledger_drift_findings": len(rec["drift"]), "rule_violations": len(rec["violations"]), "duplicate_rewards": dup,
              "unresolved_high_severity_flags": high_open, "real_financial_cost_is_zero": bool(cost["ok"])}
    checks["ok"] = rec["ok"] and dup == 0 and high_open == 0 and cost["ok"]
    return checks


async def report(db: AsyncSession, now: datetime | None = None) -> dict:
    now = now or utcnow()
    ob = await analytics.observation(db, now)
    real = await demo.real_stats(db)
    # the sufficiency that decides Gate A counts GENUINE members only; the tables below still show everything in this database, and say so
    ob["sufficiency"] = {**ob["sufficiency"], "active_members": real["real_active_members"], "observed_days": real["real_observed_days"],
                         "synthetic_members_excluded": real["synthetic_members_excluded"], "synthetic_ledger_rows_excluded": real["synthetic_ledger_rows_excluded"]}
    summary = await analytics.summary(db, now)
    dash = await _dashboard(db, ob, summary, now)
    proposals, proposals_note = _proposals(ob, summary, dash)
    quality = await _quality(db)
    criteria = _exit_criteria(ob, summary, dash, quality)
    enough = ob["sufficiency"]["active_members"] >= MIN_ACTIVE_MEMBERS and ob["sufficiency"]["observed_days"] >= MIN_OBSERVED_DAYS
    concerns = [c for c in criteria if c["indication"] == "CONCERN"]
    suggested = "INSUFFICIENT DATA" if not enough else ("RECALIBRATE" if concerns or proposals or not quality["ok"] else "PASS")
    return {
        "generated_at": now, "disclaimer": analytics.DISCLAIMER, "dashboard": dash, "observation": ob, "proposed_model_changes": proposals, "proposed_model_changes_note": proposals_note,
        "exit_criteria": criteria, "data_quality": quality,
        "gate_a": {"suggested_status": suggested, "only_management_can_approve_phase_2": True, "real_financial_effect_inr": 0,
                   "note": "A suggestion computed from the data. PASS or RECALIBRATE is decided by management. If RECALIBRATE, no financial redemption is built.",
                   "thresholds": {"min_active_members": MIN_ACTIVE_MEMBERS, "min_observed_days": MIN_OBSERVED_DAYS}},
    }


def to_markdown(r: dict) -> str:
    ob, d, g = r["observation"], r["dashboard"], r["gate_a"]
    inr = lambda p: "n/a" if p is None else f"Rs {p / 100:,.2f}"           # noqa: E731
    lines = [
        "# Phase 1 shadow review (Gate A)", "", f"Generated {r['generated_at']:%Y-%m-%d %H:%M} UTC. **REAL FINANCIAL EFFECT = Rs 0.** Member preview OFF.", "",
        f"**Suggested status: {g['suggested_status']}** (management decides; this is not an approval).", f"Data quality: {r['data_quality']}", "",
        "## Who and how much", f"- Real (active) members observed: **{ob['observed']['active_members']}**, over {ob['observed']['observed_days']} days ({ob['observed']['member_months']} member-months)",
        f"- Plan mix: {ob['observed']['plan_mix']} ({ob['observed']['plan_mix_percent']}%)",
        f"- Activity: {d['activity_metrics']}", "", "## Points",
        f"- Total shadow points awarded: **{d['reward_metrics']['points_awarded']}** (requested {d['reward_metrics']['points_requested']}, capped {d['reward_metrics']['points_capped']}, expired {d['reward_metrics']['points_expired']}, reversed {d['reward_metrics']['points_reversed']}, pending {d['reward_metrics']['points_pending']})",
        f"- Per member: average {d['member_metrics']['average']}, **median {d['member_metrics']['median']}**, P90 {d['member_metrics']['p90']}, P95 {d['member_metrics']['p95']}, top 1% hold {d['member_metrics']['top_1_percent_share_of_points_percent']}% (max {d['member_metrics']['max']})",
        f"- Risk: {d['risk_metrics']}", "", "## Hypothetical economics (not a cost TGL has incurred)",
        f"- Redemption now: {inr(d['economic_metrics']['hypothetical_redemption_now_paise'])}; maximum potential: {inr(d['economic_metrics']['maximum_potential_liability_now_paise'])}",
        f"- Annual reward cost: projected {inr(d['economic_metrics']['hypothetical_annual_reward_cost_projected_paise'])}, worst case {inr(d['economic_metrics']['hypothetical_annual_reward_cost_worst_case_paise'])}; as % of revenue {d['economic_metrics']['hypothetical_reward_cost_percent_of_revenue']}",
        f"- Renewals (hypothetical): {ob['success_metrics']['renewals']}", "", "## Modelled vs actual", "```", str(ob["modelled_vs_actual"]), "```", "", "## Proposed model changes", r["proposed_model_changes_note"], ""]
    for p in r["proposed_model_changes"]:
        lines += [f"### {p['topic']}", f"- Current rule: {p['current_rule']}", f"- Observed: {p['observed_behavior']}", f"- Financial impact: {p['financial_impact']}", f"- Recommended: {p['recommended_change']}", f"- {p['status']}", ""]
    lines += ["## Exit criteria (answered by management)", ""]
    for c in r["exit_criteria"]:
        lines.append(f"{c['n']}. **{c['question']}** [{c['indication']}] {c['evidence']}")
    lines += ["", "## Unresolved business questions", "- Whether and when members see the preview.", "- Redemption policy after a refunded renewal (restore, and to what expiry).",
              "- Early renewal before the term ends is not supported by the Phase 0 subscription flow; renewal happens from the term end (up to 30 days after).",
              "- The member-facing renewal calculation cannot be shown while the member preview is off.", ""]
    return "\n".join(lines)


async def _main() -> None:
    from ..database import SessionLocal
    async with SessionLocal() as db:
        print(to_markdown(await report(db)))


if __name__ == "__main__":
    asyncio.run(_main())
