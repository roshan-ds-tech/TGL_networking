"""The objective gates between Phase 1, Phase 2 and Phase 3, evaluated from the data and the environment, never from belief.

Each item is MET, NOT MET, or ATTESTED (an external approval that someone recorded in GROWTH_POINTS_APPROVALS: the code can not
verify a professional's approval, so it never calls it more than ATTESTED). Nothing is inferred as approved. Redemption itself is not
built yet, so `redemption_can_be_enabled` is False whatever the data says: a green Gate A only allows the Phase 2 build to start.

CLI:  python -m app.rewards.gates
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from .. import demo
from . import firewall, review

REDEMPTION_ENGINE_BUILT = True           # the Phase 2 engine, its rehearsal and its tests exist (docs/PHASE_2_REDEMPTION_READINESS.md); it stays gated by everything below
PHASE3_APPROVALS = ("MANAGEMENT_MODEL", "ACCOUNTING_GST", "PRODUCTION_BACKUP", "ROLLBACK_TESTED", "MEMBER_TERMS", "MONITORING_OWNER")


def _item(name: str, met: bool, detail: str, external: bool = False) -> dict:
    return {"gate": name, "status": ("ATTESTED" if external else "MET") if met else "NOT MET", "detail": detail}


async def evaluate(db: AsyncSession) -> dict:
    rep = await review.report(db)
    ob, q = rep["observation"], rep["data_quality"]
    suff = dict(ob["sufficiency"])
    real = await demo.real_stats(db)                       # GENUINE members only: synthetic demo members never count towards Gate A
    suff.update(active_members=real["real_active_members"], observed_days=real["real_observed_days"])
    try:
        from ..migrate import HEAD
        at = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    except Exception:                                               # noqa: BLE001 - a missing table is itself a NOT MET
        HEAD, at = None, None
    approvals = settings.growth_points_approval_codes()
    gate_a = [
        _item("at least 30 active GENUINE members (synthetic demo members never count)", suff["active_members"] >= review.MIN_ACTIVE_MEMBERS,
              f"{suff['active_members']} genuine observed; {real['synthetic_members_excluded']} synthetic members and {real['synthetic_ledger_rows_excluded']} synthetic ledger rows excluded"),
        _item("at least 30 days of genuine shadow observation", suff["observed_days"] >= review.MIN_OBSERVED_DAYS, f"{suff['observed_days']} days of genuine member activity"),
        _item("all three plans observed", suff["all_three_plans_observed"], str(ob["observed"]["plan_mix"])),
        _item("reconciliation clean, no duplicate rewards, no unresolved HIGH flag, real financial cost zero", q["ok"], str(q)),
        _item("the review's data-derived suggestion is PASS", rep["gate_a"]["suggested_status"] == "PASS", rep["gate_a"]["suggested_status"]),
        _item("management approved the model", "MANAGEMENT_MODEL" in approvals, "recorded in GROWTH_POINTS_APPROVALS" if "MANAGEMENT_MODEL" in approvals else "not recorded", external=True),
    ]
    environment = [
        _item("redemption flag is OFF", not firewall.redemption_enabled(), "GROWTH_POINTS_REDEMPTION_ENABLED"),
        _item("member preview is OFF", not firewall.member_preview_enabled(), "GROWTH_POINTS_MEMBER_PREVIEW"),
        _item("shadow processing is ON", firewall.shadow_enabled(), "GROWTH_POINTS_SHADOW_MODE"),
        _item("a programme owner is configured (pair exceptions, reconciliation)", bool(settings.programme_owners()), "PROGRAMME_OWNER_EMAILS"),
        _item("database is at the newest migration", bool(HEAD) and at == HEAD, f"{at} / {HEAD}"),
    ]
    phase3 = [
        _item("Phase 2 redemption engine built, rehearsed and tested", REDEMPTION_ENGINE_BUILT, "built in Phase 2 (tests/test_phase2.py); its use is gated by every other item"),
        *[_item(f"external approval recorded: {code}", code in approvals, "recorded in GROWTH_POINTS_APPROVALS" if code in approvals else "not recorded", external=True) for code in PHASE3_APPROVALS],
    ]
    gate_a_ok = all(i["status"] != "NOT MET" for i in gate_a)
    env_ok = all(i["status"] == "MET" for i in environment)
    phase3_ok = gate_a_ok and all(i["status"] != "NOT MET" for i in phase3)
    return {
        "gate_a": {"items": gate_a, "passed": gate_a_ok}, "environment": {"items": environment, "ok": env_ok}, "phase_3_prerequisites": {"items": phase3, "passed": phase3_ok},
        "may_start_phase_2_build": gate_a_ok and env_ok, "redemption_can_be_enabled": bool(phase3_ok and REDEMPTION_ENGINE_BUILT and env_ok),
        "real_financial_effect_inr": rep["observation"]["real_financial_cost"]["inr_minor"] / 100, "note": "Evaluated from data and environment. Approvals are attestations, never verified. Real redemption stays disabled until every item is met.",
    }


async def _main() -> None:
    import json

    from ..database import SessionLocal
    async with SessionLocal() as db:
        print(json.dumps(await evaluate(db), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
