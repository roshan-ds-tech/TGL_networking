"""Shadow-period eligibility (points earned before the approved cutoff NEVER become redeemable), demo members, and the simulation.

Targeted: it does not repeat the Phase 1/2 suites (caps, FIFO, duplicates and concurrency are proven in test_phase2.py).
Run:  .venv/bin/python test_demo_eligibility.py      TEST_DATABASE_URL=postgresql+asyncpg://... .venv/bin/python test_demo_eligibility.py
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
from datetime import timedelta, timezone
from pathlib import Path

os.environ["GROWTH_POINTS_SHADOW_MODE"] = "true"
os.environ["GROWTH_POINTS_MEMBER_PREVIEW"] = "true"
import test_phase0 as t0  # noqa: E402
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, app_settings, check, db, member_client, me, new_client, results, rows, scalar  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app import demo, ratelimit  # noqa: E402
from app.config import REQUIRED_APPROVALS, Settings, parse_cutoff  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin, User, utcnow  # noqa: E402
from app.redemption import service  # noqa: E402
from app.rewards import engine as reng, firewall, gates, reconcile, rules  # noqa: E402
from app.rewards.engine import AwardRequest  # noqa: E402
from app.security import hash_password  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import seed_demo_members as seeder  # noqa: E402


def go(fn):
    async def f():
        async with SessionLocal() as s:
            r = await fn(s)
            await s.commit()
            return r
    return asyncio.run(f())


def sql_fails(sql: str, **params) -> bool:
    async def f(s):
        try:
            await s.execute(text(sql), params)
            await s.commit()
            return False
        except (IntegrityError, DBAPIError):
            await s.rollback()
            return True
    return db(f)


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app) as boot:
        return body()


def body() -> int:
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    app_settings.programme_owner_emails = ADMIN_EMAIL
    counter = iter(range(1, 10000))
    clear = ratelimit._buckets.clear

    def buy(c, code):
        clear()
        sid = c.post("/api/v1/subscriptions", json={"plan_code": code}, headers=H(c)).json()["id"]
        clear()
        c.post(f"/api/v1/subscriptions/{sid}/payment-proof", files={"proof": ("p.png", io.BytesIO(PNG), "image/png")}, headers=H(c))
        admin.post(f"/api/admin/subscriptions/{sid}/payment/verify", json={"reason": "Bank credit seen"}, headers=AH)
        return sid

    def real_member(code="growth", ends_in=10):
        clear()
        k = next(counter)
        c = member_client(f"elig-{k}@example.com", f"Elig {k}")
        sid = buy(c, code)
        c.get("/api/v1/status")
        months = {"connect": 3, "growth": 6, "elite": 12}[code]
        ends = utcnow() + timedelta(days=ends_in)
        starts = ends - timedelta(days=round(months * 30.4375))
        async def f(s):
            await s.execute(text("update subscriptions set starts_at = :s, expires_at = :e, activated_at = :s where id = :i"), {"s": starts, "e": ends, "i": sid})
            await s.commit()
        db(f)
        return dict(c=c, mid=me(c), sid=sid, starts=starts, ends=ends, email=f"elig-{k}@example.com")

    def award(mid, ref, pts, at, kind="BUSINESS_CLOSED", level=4):
        async def f(s):
            with firewall.guard():
                res = await reng.award(s, AwardRequest(member_id=mid, event_type=kind, reference_type="deal_closure" if kind == "BUSINESS_CLOSED" else "referral", reference_id=ref, requested=pts,
                                                       level=level, event_at=at, role="referrer" if kind == "BUSINESS_CLOSED" else "member"))
            return res.row.points_delta
        return go(f)

    def close_all():
        app_settings.growth_points_redemption_enabled = False
        app_settings.growth_points_approvals = ""
        app_settings.growth_points_redeemable_from = ""
        app_settings.growth_points_demo_cutoff = ""
        app_settings.growth_points_rollout_stage = "internal"

    close_all()

    # ======================================================================================== 1. THE CUTOFF FORMAT
    good = parse_cutoff("2027-01-01T00:00:00+05:30")
    check("FORMAT: an ISO-8601 datetime WITH an explicit offset is read and normalised to UTC (2027-01-01T00:00+05:30 = 2026-12-31T18:30Z)", good.isoformat() == "2026-12-31T18:30:00+00:00" and parse_cutoff("2027-01-01T00:00:00Z") == parse_cutoff("2027-01-01T00:00:00+00:00"))
    bad = []
    for raw in ("2027-01-01", "2027-01-01T00:00:00", "next year", "", "2027-13-01T00:00:00+00:00", "01/01/2027"):
        try:
            parse_cutoff(raw)
        except ValueError:
            bad.append(raw)
    check("FORMAT: a bare date, a time without an offset, text, an empty value and an impossible date are all refused (no guessing of a timezone)", len(bad) == 6, str(bad))
    refused = []
    for raw in ("2027-01-01", "2027-01-01T00:00:00", "garbage"):
        try:
            Settings(growth_points_redeemable_from=raw)
        except Exception:
            refused.append(raw)
    ok_cfg = Settings(growth_points_redeemable_from="2027-01-01T00:00:00+05:30")
    check("STARTUP: GROWTH_POINTS_REDEEMABLE_FROM that is ambiguous or unreadable stops the application starting; a valid one starts; empty is the default (nothing redeemable)",
          len(refused) == 3 and ok_cfg.growth_points_redeemable_from and Settings().growth_points_redeemable_from == "")
    try:
        Settings(environment="production", growth_points_demo_cutoff="2027-01-01T00:00:00+00:00")
        prod_demo = False
    except Exception:
        prod_demo = True
    check("STARTUP: the demo (simulation) cutoff is refused in production", prod_demo)

    # ======================================================================================== 2. FAIL-SAFE: every other situation means NOTHING is redeemable
    async def status():
        async with SessionLocal() as s:
            return await service.cutoff_status(s)
    why = {}
    why["unset"] = asyncio.run(status())[1]
    app_settings.growth_points_redeemable_from = "2030-01-01T00:00:00+00:00"
    why["no_epoch_row"] = asyncio.run(status())[1]
    app_settings.growth_points_redeemable_from = "not a date"
    why["unreadable"] = asyncio.run(status())[1]
    check("FAIL-SAFE: unset, set-but-never-recorded, and unreadable-at-runtime all give 'nothing redeemable' with a reason (and never an exception)", why == {"unset": "cutoff_not_configured", "no_epoch_row": "cutoff_not_recorded", "unreadable": "cutoff_unreadable"}, str(why))

    # ======================================================================================== 3. RECORDING THE OFFICIAL CUTOFF (once, by the programme owner, after an approval, never in the past)
    cutoff = (utcnow() + timedelta(days=1)).replace(microsecond=0)
    body_ = {"cutoff_at": cutoff.isoformat(), "reason": "Approved by management for the Phase 3 launch (test)"}
    app_settings.growth_points_approvals = ""
    r_noapproval = admin.post("/api/admin/growth-points/redemption/epoch", json=body_, headers=AH)
    app_settings.growth_points_approvals = "MANAGEMENT_MODEL"
    ops = new_client()
    async def mk(s_):
        s_.add(Admin(email="ops-elig@tglseason.com", password_hash=hash_password(PASSWORD)))
        await s_.commit()
    db(mk)
    ops.post("/api/auth/login", json={"email": "ops-elig@tglseason.com", "password": PASSWORD})
    OH = {"X-CSRF-Token": ops.cookies.get("tgl_csrf") or ""}
    r_ops = ops.post("/api/admin/growth-points/redemption/epoch", json=body_, headers=OH)
    r_naive = admin.post("/api/admin/growth-points/redemption/epoch", json={"cutoff_at": "2031-01-01T00:00:00", "reason": "No offset given"}, headers=AH)
    r_past = admin.post("/api/admin/growth-points/redemption/epoch", json={"cutoff_at": (utcnow() - timedelta(days=1)).isoformat() + "+00:00", "reason": "Back-dated, must be refused"}, headers=AH)
    r_ok = admin.post("/api/admin/growth-points/redemption/epoch", json=body_, headers=AH)
    r_again = admin.post("/api/admin/growth-points/redemption/epoch", json={**body_, "cutoff_at": (cutoff + timedelta(days=30)).isoformat()}, headers=AH)
    check("EPOCH: needs a recorded approval (409), the programme owner (403), an explicit offset (422) and a cutoff that is not in the past (422); then it is recorded once; a second one is refused (409)",
          (r_noapproval.status_code, r_ops.status_code, r_naive.status_code, r_past.status_code, r_ok.status_code, r_again.status_code) == (409, 403, 422, 422, 200, 409),
          str([r.status_code for r in (r_noapproval, r_ops, r_naive, r_past, r_ok, r_again)]))
    check("EPOCH: it is immutable and can not be back-dated, even with SQL; it is audited", sql_fails("update growth_point_redemption_epoch set cutoff_at = '2000-01-01 00:00:00'") and sql_fails("delete from growth_point_redemption_epoch")
          and sql_fails("insert into growth_point_redemption_epoch (id, singleton, cutoff_at, recorded_at, recorded_by, reason) values ('x2', 'TWO', '2031-01-01 00:00:00', '2030-01-01 00:00:00', 'x', 'x')")
          and scalar("select count(*) from audit_log where action = 'growth_points.epoch_recorded'") == 1)
    app_settings.growth_points_approvals = ""
    app_settings.growth_points_redeemable_from = (cutoff + timedelta(seconds=1)).isoformat()
    w_mismatch = asyncio.run(status())[1]
    app_settings.growth_points_redeemable_from = "2000-01-01T00:00:00+00:00"
    w_earlier = asyncio.run(status())[1]
    app_settings.growth_points_redeemable_from = cutoff.isoformat()
    w_ok = asyncio.run(status())
    check("PERMANENCE: the environment value only counts if it equals the recorded cutoff: a later value and an EARLIER value (an attempt to grandfather shadow points in) both mean nothing is redeemable; the exact value works",
          w_mismatch == "cutoff_mismatch" and w_earlier == "cutoff_mismatch" and w_ok[1] == "ok" and w_ok[0] == cutoff)

    # ======================================================================================== 4. THE BOUNDARY AND THE LOTS
    m = real_member("growth")
    pts_before = award(m["mid"], "el-before-far", 1000, cutoff - timedelta(days=20))
    pts_just = award(m["mid"], "el-just-before", 450, cutoff - timedelta(seconds=1), kind="PROFILE_COMPLETED", level=3)
    pts_at = award(m["mid"], "el-at", 500, cutoff, kind="MEETING_COMPLETED", level=3)
    pts_after = award(m["mid"], "el-after", 800, cutoff + timedelta(hours=1))
    later = cutoff + timedelta(days=3)                               # by then every lot is usable (levels 3/4 need no waiting)

    async def quote_at(code, at):
        async with SessionLocal() as s:
            user = await s.get(User, m["mid"])
            return await service.quote(s, user, code, now=at)
    q = asyncio.run(quote_at("elite", later))
    check("BOUNDARY: the cutoff is INCLUSIVE: a point earned exactly at the cutoff is eligible; one second before is not; shadow-period points are excluded and counted",
          (pts_before, pts_just, pts_at, pts_after) == (1000, 450, 500, 800) and q["eligible_old_cycle_points"] == 500 + 800 and q["points_excluded_before_cutoff"] == 1000 + 450 and q["eligibility_basis"] == "ok", str(q)[:400])
    check("ELIGIBLE: post-cutoff points qualify for the NEW plan's cap (Elite 15,000): all 1,300 used, discount 130 rupees, payable 9,870 rupees", q["points_to_be_redeemed"] == 1300 and q["hypothetical_discount_paise"] == 13000 and q["hypothetical_amount_payable_paise"] == 1000000 - 13000)
    app_settings.growth_points_redeemable_from = "2000-01-01T00:00:00+00:00"          # an attempt to move the line earlier through configuration alone
    q_moved = asyncio.run(quote_at("elite", later))
    app_settings.growth_points_redeemable_from = cutoff.isoformat()
    check("PERMANENT: moving the environment value earlier does not make shadow-period points redeemable (nothing is redeemable until it matches the recorded cutoff again)", q_moved["eligible_old_cycle_points"] == 0 and q_moved["eligibility_basis"] == "cutoff_mismatch")

    # real redemption through the service: only eligible lots are consumed, FIFO, shadow lots untouched
    app_settings.growth_points_redemption_enabled = True
    app_settings.growth_points_approvals = ",".join(sorted(REQUIRED_APPROVALS))
    app_settings.growth_points_rollout_stage = "all"
    async def yes(_db):
        return True
    saved_gate = service._gate_a_passed
    service._gate_a_passed = yes
    async def do_confirm(code, at, mid, redeem=True, pts=None, disc=None, patch=None):
        async with SessionLocal() as s:
            user = await s.get(User, mid)
            q_ = await service.quote(s, user, code, now=at)
            try:
                res = await service.confirm(s, user, code, redeem=redeem, expected_points=q_["points_to_be_redeemed"] if pts is None else pts, expected_discount_minor=q_["hypothetical_discount_paise"] if disc is None else disc, now=at)
                await s.commit()
                return res
            except Exception as exc:                                    # noqa: BLE001
                await s.rollback()
                return exc
    lots_before = rows("select id, points_delta, event_at from growth_point_ledger where member_id = :m and entry_type = 'EARN' order by event_at", m=m["mid"])
    res = asyncio.run(do_confirm("elite", later, m["mid"]))
    used = rows("select l.reference_id, -x.delta from growth_point_redemption_lots x join growth_point_ledger l on l.id = x.lot_id where x.member_id = :m order by l.event_at", m=m["mid"])
    check("REAL PATH: only the post-cutoff lots were consumed (500 then 800, oldest first); the two shadow-period lots were never touched; the invoice carries exactly that discount",
          isinstance(res, dict) and used == [("el-at", 500), ("el-after", 800)] and res["growth_points_discount_minor"] == 13000 and res["amount_due_minor"] == 987000
          and scalar("select total_points from growth_point_balances where member_id = :m", m=m["mid"]) == 1450 and rows("select id, points_delta, event_at from growth_point_ledger where member_id = :m and entry_type = 'EARN' order by event_at", m=m["mid"]) == lots_before, str(res)[:200])
    rec = go(lambda s: reconcile.reconcile(s))
    check("RECONCILIATION: the shadow-period balance (1,450 points) stays in the ledger for audit and the books still balance", rec["ok"], str(rec)[:300])

    # nothing eligible: a member whose points are all shadow-period
    n = real_member("connect")
    award(n["mid"], "sh-only", 2000, cutoff - timedelta(days=10))
    async def quote_for(mid, code, at):
        async with SessionLocal() as s:
            return await service.quote(s, await s.get(User, mid), code, now=at)
    qn = asyncio.run(quote_for(n["mid"], "growth", later))
    rn_forged = asyncio.run(do_confirm("growth", later, n["mid"], redeem=True, pts=100, disc=1000))
    rn = asyncio.run(do_confirm("growth", later, n["mid"], redeem=True))
    rn_plain = rn                                                  # the same live renewal is returned (replay): asking again changes nothing
    check("NO ELIGIBLE POINTS: a member with only shadow-period points sees 0 eligible and an explanation; asking to redeem nothing creates no redemption; a forged 100-point request is refused as a changed calculation",
          qn["eligible_old_cycle_points"] == 0 and qn["points_excluded_before_cutoff"] == 2000 and "before Growth Points redemption began" in qn["reason"] and isinstance(rn, dict) and rn["points_redeemed"] == 0
          and getattr(rn_forged, "status_code", None) == 409 and isinstance(rn_plain, dict) and rn_plain["points_redeemed"] == 0 and rn_plain["amount_due_minor"] == 500000)
    check("NO ELIGIBLE POINTS (data): no redemption record exists for that member and their points are unchanged", scalar("select count(*) from growth_point_redemptions where member_id = :m", m=n["mid"]) == 0
          and scalar("select total_points from growth_point_balances where member_id = :m", m=n["mid"]) == 2000)

    # ======================================================================================== 5. A FAILED TRANSACTION LEAVES NOTHING BEHIND
    f = real_member("growth")
    award(f["mid"], "fail-1", 900, cutoff + timedelta(hours=2))
    import app.redemption.service as svc
    original = svc.audit.record
    def boom(db_, **kw):
        if kw.get("action") == "growth_points.redeemed":
            raise RuntimeError("simulated failure while recording the redemption audit")
        return original(db_, **kw)
    svc.audit.record = boom
    bal_before = scalar("select total_points from growth_point_balances where member_id = :m", m=f["mid"])
    failed = asyncio.run(do_confirm("connect", later + timedelta(days=1), f["mid"]))
    svc.audit.record = original
    check("TRANSACTION: if anything fails after the invoice and redemption were prepared, NOTHING is saved: no renewal subscription, no invoice, no redemption, no lot line, balance unchanged",
          isinstance(failed, RuntimeError) and scalar("select count(*) from subscriptions where user_id = :u and renews_subscription_id is not null", u=f["mid"]) == 0
          and scalar("select count(*) from growth_point_redemptions where member_id = :m", m=f["mid"]) == 0 and scalar("select count(*) from growth_point_redemption_lots where member_id = :m", m=f["mid"]) == 0
          and scalar("select count(*) from invoices where user_id = :u and points_redeemed > 0", u=f["mid"]) == 0 and scalar("select total_points from growth_point_balances where member_id = :m", m=f["mid"]) == bal_before)
    service._gate_a_passed = saved_gate
    close_all()

    # ======================================================================================== 6. DEMO MEMBERS: the seed
    for kw, expect in (({"environment": "production", "uses_supabase": False, "database_url": "sqlite+aiosqlite:///./x.db"}, True), ({"environment": "development", "uses_supabase": True, "database_url": "sqlite+aiosqlite:///./x.db"}, True),
                       ({"environment": "development", "uses_supabase": False, "database_url": "postgresql+asyncpg://u:p@db.example.org/prod"}, True), ({"environment": "development", "uses_supabase": False, "database_url": "sqlite+aiosqlite:///./x.db"}, False),
                       ({"environment": "test", "uses_supabase": False, "database_url": "postgresql+asyncpg://tgl@localhost:5432/tgl"}, False)):
        try:
            seeder.assert_safe(kw["database_url"], kw["environment"], kw["uses_supabase"])
            blocked = False
        except seeder.UnsafeTarget:
            blocked = True
        check(f"SEED SAFETY: {kw['environment']} / {'supabase photos' if kw['uses_supabase'] else 'local photos'} / {kw['database_url'].split('@')[-1][:28]} is {'REFUSED' if expect else 'allowed'}", blocked == expect)
    before_real = go(lambda s: demo.real_stats(s))
    cutoff_demo = utcnow() - timedelta(days=60)
    manifest = Path(TMP) / "manifest.json"
    first = asyncio.run(seeder.seed(SessionLocal, count=30, assets_dir=Path(TMP) / "avatars", fetch_images=False, demo_cutoff=cutoff_demo, manifest_path=manifest))
    second = asyncio.run(seeder.seed(SessionLocal, count=30, assets_dir=Path(TMP) / "avatars", fetch_images=False, demo_cutoff=cutoff_demo, manifest_path=manifest))
    check("SEED: creates 30 synthetic members with photos, then a second run creates none (idempotent, no duplicates)", first["created_now"] == 30 and first["photos_stored_now"] == 30 and second["created_now"] == 0 and second["already_existed"] == 30 and second["photos_stored_now"] == 0
          and scalar("select count(*) from users where email like '%@demo.example.com'") == 30 and scalar("select count(distinct email) from users where email like '%@demo.example.com'") == 30)
    check("SEED: every account is identifiable as synthetic (reserved demo.example.com domain, a manifest, DEMO- invoice numbers) and has the profile, business, networking profile and photo the member interface needs",
          scalar("select count(*) from users u join personal_profiles p on p.user_id = u.id join businesses b on b.user_id = u.id join networking_profiles n on n.user_id = u.id where u.email like '%@demo.example.com' and u.photo_key is not null") == 30
          and json.loads(manifest.read_text())["synthetic"] is True and len(json.loads(manifest.read_text())["members"]) == 30 and scalar("select count(*) from invoices where number like 'DEMO-%'") >= 30
          and scalar("select count(distinct category) from businesses b join users u on u.id = b.user_id where u.email like '%@demo.example.com'") == 10)
    check("SEED: no payment, no invoice discount, no redemption and no approval was created for any demo member", scalar("select count(*) from payments p join users u on u.id = p.user_id where u.email like '%@demo.example.com'") == 0
          and scalar("select count(*) from invoices i join users u on u.id = i.user_id where u.email like '%@demo.example.com' and (i.discount_minor <> 0 or i.points_discount_minor <> 0)") == 0
          and scalar("select count(*) from growth_point_redemptions r join users u on u.id = r.member_id where u.email like '%@demo.example.com'") == 0)
    async def photo_ok(s):
        from app.storage import read_profile_photo
        keys = (await s.execute(select(User.photo_key).where(demo.synthetic_clause()))).scalars().all()
        sizes = [len(await read_profile_photo(k)) for k in keys]
        return len(keys) == 30 and all(n_ > 500 for n_ in sizes)
    check("PHOTOS: all 30 stored images are readable through the app's own photo store (PNG/JPEG re-encoded by the existing pipeline)", go(photo_ok))
    png, src = seeder._avatar_bytes("fallback-test", "Test Person", Path(TMP) / "fb", False)
    check("PHOTOS: if the download is unavailable a generated initials avatar is used instead (a valid PNG), and its source is reported honestly", png[:8] == bytes.fromhex("89504e470d0a1a0a") and "generated" in src)
    check("PHOTOS: the source and licence are recorded: DiceBear 'lorelei', CC0 1.0 (illustrations, not photographs of people)", "CC0" in seeder.AVATAR_SOURCE and "lorelei" in seeder.AVATAR_SOURCE and "CC0" in json.loads(manifest.read_text())["image_source"])

    # ======================================================================================== 7. THE OBSERVATION GATE NEVER COUNTS SYNTHETIC DATA
    after_real = go(lambda s: demo.real_stats(s))
    check("GATE: seeding 30 synthetic members and their test ledger rows changed NOTHING in the genuine-member numbers (active members, observed days, rewards); the synthetic ones are reported separately",
          (after_real["real_active_members"], after_real["real_observed_days"], after_real["real_rewards_recorded"]) == (before_real["real_active_members"], before_real["real_observed_days"], before_real["real_rewards_recorded"])
          and after_real["synthetic_members_excluded"] == 30 and after_real["synthetic_ledger_rows_excluded"] > 0, f"{before_real} {after_real}")
    gt = admin.get("/api/admin/growth-points/gates").json()
    item = [i for i in gt["gate_a"]["items"] if "GENUINE members" in i["gate"]][0]
    review_ = admin.get("/api/admin/growth-points/review").json()
    check("GATE: with 30 synthetic members present Gate A is still NOT MET, the item says how many synthetic members were excluded, and the review's sufficiency counts genuine members only",
          gt["gate_a"]["passed"] is False and item["status"] == "NOT MET" and "30 synthetic members" in item["detail"] and review_["observation"]["sufficiency"]["synthetic_members_excluded"] == 30
          and review_["observation"]["sufficiency"]["active_members"] == after_real["real_active_members"] and gt["redemption_can_be_enabled"] is False)

    # ======================================================================================== 8. THE SIX SCENARIOS AND THE ROLLED-BACK SIMULATION
    app_settings.growth_points_demo_cutoff = cutoff_demo.isoformat()
    async def scenario_quotes(s):
        out_ = {}
        for i, name in seeder.SCENARIOS.items():
            user = await s.scalar(select(User).where(User.email == f"demo-{i:02d}@demo.example.com"))
            out_[name] = await service.quote(s, user, "connect", simulate=True)
        return out_
    sq = go(scenario_quotes)
    check("SCENARIOS: no points -> 0; post-cutoff points -> 2,400 eligible; shadow-period points -> 0 eligible with 2,400 excluded; expired -> 0; dispute-reversed -> 0; cap-hit (6,000 earned) -> 4,500 used on a Connect renewal with 1,500 left",
          (sq["NO_POINTS"]["eligible_old_cycle_points"], sq["ELIGIBLE_POST_CUTOFF"]["points_to_be_redeemed"], sq["SHADOW_PERIOD_ONLY"]["eligible_old_cycle_points"], sq["SHADOW_PERIOD_ONLY"]["points_excluded_before_cutoff"],
           sq["EXPIRED"]["eligible_old_cycle_points"], sq["DISPUTE_REVERSED"]["eligible_old_cycle_points"], sq["CAP_HIT"]["eligible_old_cycle_points"], sq["CAP_HIT"]["points_to_be_redeemed"], sq["CAP_HIT"]["remaining_old_cycle_points"])
          == (0, 2400, 0, 2400, 0, 0, 6000, 4500, 1500), str({k: (v["eligible_old_cycle_points"], v["points_to_be_redeemed"]) for k, v in sq.items()}))
    def login(i):
        c = new_client()
        r = c.post("/api/v1/auth/login", json={"email": f"demo-{i:02d}@demo.example.com", "password": demo.DEMO_PASSWORD})
        assert r.status_code == 200, r.text
        return c
    d6, d2, d3 = login(6), login(2), login(3)
    snap = lambda: (scalar("select count(*) from subscriptions"), scalar("select count(*) from invoices"), scalar("select count(*) from growth_point_redemptions"), scalar("select count(*) from growth_point_redemption_lots"),
                    scalar("select coalesce(sum(total_points), 0) from growth_point_balances"), scalar("select coalesce(sum(amount_due_minor), 0) from invoices"), scalar("select count(*) from audit_log"))
    before = snap()
    qd = d6.get("/api/v1/renewal/quote", params={"plan_code": "connect"}).json()
    clear()
    sim = d6.post("/api/v1/renewal/simulate", json={"plan_code": "connect", "redeem": True, "expected_points": qd["points_to_be_redeemed"], "expected_discount_minor": qd["hypothetical_discount_paise"]}, headers=H(d6))
    for _ in range(3):
        clear()
        d6.post("/api/v1/renewal/simulate", json={"plan_code": "connect", "redeem": True, "expected_points": qd["points_to_be_redeemed"], "expected_discount_minor": qd["hypothetical_discount_paise"]}, headers=H(d6))
    check("SIMULATION: a demo member sees mode SIMULATION with the real backend maths (4,500 points, Rs 450 off, Rs 2,550 payable) clearly labelled; running it 4 times saves NOTHING (no subscription, invoice, redemption, lot line, point, audit row)",
          qd["mode"] == "SIMULATION" and "SIMULATION" in qd["label"] and sim.status_code == 200 and sim.json()["simulated"] is True and sim.json()["applied"] is False and sim.json()["points_would_be_used"] == 4500 and sim.json()["discount_minor"] == 45000
          and sim.json()["amount_payable_minor"] == 255000 and "SIMULATION ONLY" in sim.json()["message"] and snap() == before, f"{sim.text[:200]} {before} {snap()}")
    clear()
    real_try = d6.post("/api/v1/renewal/confirm", json={"plan_code": "connect", "redeem": True, "expected_points": 4500, "expected_discount_minor": 45000}, headers=H(d6))
    check("REAL REDEMPTION STAYS CLOSED: the same demo member's real confirm is refused (redemption_disabled) and nothing changed", real_try.status_code == 409 and real_try.json()["detail"]["reason"] == "redemption_disabled" and snap() == before)
    clear()
    d3q = d3.get("/api/v1/renewal/quote", params={"plan_code": "connect"}).json()
    check("SHADOW-PERIOD MEMBER: the demo member whose points pre-date the cutoff sees no redeem button (can_simulate false) and the explanation", d3q["can_simulate"] is False and d3q["points_excluded_before_cutoff"] == 2400 and "before Growth Points redemption began" in d3q["reason"])
    real = real_member("growth")
    clear()
    r_real_sim = real["c"].post("/api/v1/renewal/simulate", json={"plan_code": "connect", "redeem": False}, headers=H(real["c"]))
    q_real = real["c"].get("/api/v1/renewal/quote", params={"plan_code": "connect"}).json()
    check("SIMULATION IS DEMO-ONLY: a genuine member gets 404 from the simulation and a PREVIEW (never SIMULATION) quote", r_real_sim.status_code == 404 and q_real["mode"] == "PREVIEW" and q_real["can_redeem"] is False)
    saved_env = app_settings.environment
    app_settings.environment = "production"
    clear()
    r_prod = d6.post("/api/v1/renewal/simulate", json={"plan_code": "connect", "redeem": False}, headers=H(d6))
    q_prod = d6.get("/api/v1/renewal/quote", params={"plan_code": "connect"}).json()
    app_settings.environment = saved_env
    app_settings.growth_points_demo_cutoff = ""
    clear()
    r_nocut = d6.post("/api/v1/renewal/simulate", json={"plan_code": "connect", "redeem": False}, headers=H(d6))
    check("SIMULATION IS DEV-ONLY: in a production environment, or without the demo cutoff, even a demo member gets 404 / PREVIEW", r_prod.status_code == 404 and q_prod["mode"] == "PREVIEW" and r_nocut.status_code == 404)
    close_all()

    passed = sum(1 for ok, _ in results if ok)
    print()
    for ok, name in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        code_ = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code_)
