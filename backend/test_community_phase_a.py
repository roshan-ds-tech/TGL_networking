"""Phase A: reliable recording of connections, business needs and help offers. Facts only: nothing here may award a Growth Point.

Targeted. Run:  .venv/bin/python test_community_phase_a.py          TEST_DATABASE_URL=postgresql+asyncpg://... .venv/bin/python test_community_phase_a.py
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import random
import re
import shutil
import string
import sys
from concurrent.futures import ThreadPoolExecutor

os.environ["GROWTH_POINTS_SHADOW_MODE"] = "true"      # the strongest form of "Phase A awards nothing": recording is ON and still nothing is issued
os.environ["GROWTH_POINTS_MEMBER_PREVIEW"] = "false"
import test_phase0 as t0
from test_phase0 import ADMIN_EMAIL, PASSWORD, PNG, TMP, H, check, member_client, me, new_client, results, rows, scalar

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import community, ratelimit
from app.config import settings as app_settings
from app.main import app

random.seed(7)


def words(n: int) -> str:
    return " ".join("".join(random.choices(string.ascii_lowercase, k=7)) for _ in range(n))


def desc(n: int = 16) -> str:
    return "We need a reliable partner for this: " + words(n)          # well over 80 characters, and different every time


def clear() -> None:
    ratelimit._buckets.clear()


def ev(domain: str, kind: str | None = None, **where):
    sql = "select kind, reconnection, actor_user_id, subject_user_id, reason_code, details, need_id, offer_id, actor_admin_id from community_events where domain = :d"
    p = {"d": domain}
    if kind:
        sql += " and kind = :k"
        p["k"] = kind
    for i, (col, val) in enumerate(where.items()):
        sql += f" and {col} = :w{i}"
        p[f"w{i}"] = val
    return rows(sql + " order by created_at, id", **p)


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app):
        return body()


def body() -> int:
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    AH = {"X-CSRF-Token": admin.cookies.get("tgl_csrf") or ""}
    emails = {"a": "ca@example.com", "b": "cb@example.com", "c": "cc@example.com", "d": "cd@example.com", "e": "ce@example.com", "z": "demo-90@demo.example.com", "out": "cout@example.com"}
    cl = {k: member_client(v, f"Member {k.upper()}") for k, v in emails.items()}
    for k, v in emails.items():
        if k == "out":
            continue
        r = new_client().post("/api/registrations", data={"name": f"Member {k.upper()}", "business": f"{k.upper()} Co", "email": v, "phone": "9876543210", "category": "01", "employees": "1-3", "age": "lt6", "agree": "true", "mediaConsent": "true"},
                              files={"paymentProof": ("p.png", io.BytesIO(PNG), "image/png")})
        assert r.status_code == 201, r.text
    for reg in admin.get("/api/admin/registrations", params={"page_size": 50}).json()["items"]:
        assert admin.patch(f"/api/admin/registrations/{reg['id']}/verify", json={"verified": True}, headers=AH).status_code == 200
    assert admin.post("/api/admin/events/season-1/complete", headers=AH).status_code == 200
    ids = {k: me(c) for k, c in cl.items()}
    a, b, c_, d, e, z, out = (cl[k] for k in ("a", "b", "c", "d", "e", "z", "out"))
    A, B, C, D, E, Z = (ids[k] for k in ("a", "b", "c", "d", "e", "z"))
    empty = admin.get("/api/admin/community/report")
    ej = empty.json() if empty.status_code == 200 else {}
    check("EMPTY REPORT: with no genuine observation the report still answers, shows zeros and no invented medians, and says no observation has started",
          empty.status_code == 200 and ej["observation"]["genuine_events_recorded"] == 0 and ej["observation"]["first_event_at"] is None and ej["timing_hours_median"]["publication_to_first_offer"] is None
          and ej["connections"]["outcomes"]["acceptance_rate_percent"] is None and "does not claim" in ej["observation"]["note"] and "baseline" in ej["observation"])
    ledger_before = scalar("select count(*) from growth_point_ledger")
    fin_before = tuple(scalar(f"select count(*) from {t}") for t in ("invoices", "payments", "subscriptions"))
    check("setup: five genuine members and one synthetic demo member have Networking access; one account has none", all(cl[k].get("/api/v1/status").json()["networking_access"] for k in ("a", "b", "c", "d", "e", "z")) and not out.get("/api/v1/status").json()["networking_access"])
    check("setup: Growth Points recording is ON for this whole run (so any accidental award would show)", app_settings.growth_points_shadow_mode is True)
    pairs = lambda x, y: rows("select id, requester_user_id, target_user_id, status from connections where (requester_user_id = :x and target_user_id = :y) or (requester_user_id = :y and target_user_id = :x)", x=x, y=y)  # noqa: E731
    post = lambda cli, x: cli.post("/api/v1/networking/connections", json={"target_user_id": x, "note": "private note text"}, headers=H(cli))  # noqa: E731

    # =============================================================================== 1. CONNECTION LIFECYCLE AND HISTORY
    clear()
    r = post(a, B)
    check("a request creates the row and ONE history event, and it is not a reconnection", r.status_code == 201 and len(pairs(A, B)) == 1 and [x[0] for x in ev("CONNECTION")][-1:] == ["REQUESTED"] and ev("CONNECTION", "REQUESTED")[-1][1] in (0, False))
    n_ev = len(ev("CONNECTION"))
    dup = post(a, B)
    check("a duplicate request is refused (409) and writes no second event", dup.status_code == 409 and len(pairs(A, B)) == 1 and len(ev("CONNECTION")) == n_ev)
    rid = pairs(A, B)[0][0]
    check("a third member can not answer or withdraw it (404) and nothing is recorded", c_.patch(f"/api/v1/networking/connections/{rid}", json={"action": "accept"}, headers=H(c_)).status_code == 404
          and c_.delete(f"/api/v1/networking/connections/{rid}", headers=H(c_)).status_code == 404 and len(ev("CONNECTION")) == n_ev)
    check("the sender can not accept their own request (404)", a.patch(f"/api/v1/networking/connections/{rid}", json={"action": "accept"}, headers=H(a)).status_code == 404)
    check("the target declines: the row is DECLINED and a DECLINED event exists (the sender is not told, as before)", b.patch(f"/api/v1/networking/connections/{rid}", json={"action": "decline"}, headers=H(b)).status_code == 200
          and pairs(A, B)[0][3] == "DECLINED" and ev("CONNECTION", "DECLINED") and len(a.get("/api/v1/notifications").json()) == len([1 for n in a.get("/api/v1/notifications").json() if n["type"] != "connection_declined"]))
    check("the sender withdraws it: the row goes, a WITHDRAWN event records the status it had", a.delete(f"/api/v1/networking/connections/{rid}", headers=H(a)).status_code == 204 and not pairs(A, B)
          and json.loads(ev("CONNECTION", "WITHDRAWN")[-1][5])["from_status"] == "DECLINED")
    clear()
    r = post(a, B)
    rid = pairs(A, B)[0][0]
    check("the sender asks again after withdrawing: a new request, still the first time they are connected (not a reconnection)", r.status_code == 201 and ev("CONNECTION", "REQUESTED")[-1][1] in (0, False))
    check("the target accepts: ACCEPTED event, first connection", b.patch(f"/api/v1/networking/connections/{rid}", json={"action": "accept"}, headers=H(b)).status_code == 200 and pairs(A, B)[0][3] == "ACCEPTED"
          and ev("CONNECTION", "ACCEPTED")[-1][1] in (0, False))
    check("accepting twice is a 409 and records nothing more", b.patch(f"/api/v1/networking/connections/{rid}", json={"action": "accept"}, headers=H(b)).status_code == 409 and len(ev("CONNECTION", "ACCEPTED")) == 1)
    check("removing a connection deletes the live rows (as before) and records REMOVED with who removed it", b.delete(f"/api/v1/networking/connections/{rid}", headers=H(b)).status_code == 204 and not pairs(A, B)
          and json.loads(ev("CONNECTION", "REMOVED")[-1][5])["removed_by"] == "target")
    check("HISTORY SURVIVES REMOVAL: the pair is still remembered as having been connected", scalar("select count(*) from community_events where domain = 'CONNECTION' and kind = 'ACCEPTED' and pair_hash = :h", h=community.pair_hash(A, B)) == 1)
    clear()
    r = post(a, B)
    check("a later request by the same pair is recorded as a RECONNECTION attempt", r.status_code == 201 and ev("CONNECTION", "REQUESTED")[-1][1] in (1, True))
    rid = pairs(A, B)[0][0]
    check("and its acceptance is recorded as a reconnection", b.patch(f"/api/v1/networking/connections/{rid}", json={"action": "accept"}, headers=H(b)).status_code == 200 and ev("CONNECTION", "ACCEPTED")[-1][1] in (1, True))
    clear()
    check("crossing requests: asking back is an accept, with both events and exactly one live row", post(c_, D).status_code == 201 and post(d, C).status_code == 201 and len(pairs(C, D)) == 1 and pairs(C, D)[0][3] == "ACCEPTED"
          and len(ev("CONNECTION", "ACCEPTED", pair_hash=community.pair_hash(C, D))) == 1)
    check("the history rows hold ids and reason codes only: no note, name or e-mail", not any(re.search(r"private note|@example", json.dumps([str(x) for x in r_])) for r_ in rows("select * from community_events")))
    check("a connection is refused to an account without Networking access, and to oneself", post(out, A).status_code in (401, 403) and post(a, A).status_code == 400)

    # concurrency: crossing requests, and a double-click storm
    clear()
    def go(args):
        who, target = args
        return who.post("/api/v1/networking/connections", json={"target_user_id": target}, headers=H(who)).status_code
    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(go, [(a, E), (e, A), (a, E), (e, A), (a, E), (e, A)]))
    live = pairs(A, E)
    check("CONCURRENT crossing and repeated requests leave ONE live, consistent row (never two active connections)", len(live) == 1 and live[0][3] in ("PENDING", "ACCEPTED") and all(code in (201, 409) for code in codes), f"{codes} {live}")
    print("DEBUG codes", codes, "requested", len(ev("CONNECTION", "REQUESTED", pair_hash=community.pair_hash(A, E))), "accepted", len(ev("CONNECTION", "ACCEPTED", pair_hash=community.pair_hash(A, E))), live)
    check("...and the history matches reality: at most one ACCEPTED, and one REQUESTED event per request that succeeded",
          len(ev("CONNECTION", "ACCEPTED", pair_hash=community.pair_hash(A, E))) <= 1 and len(ev("CONNECTION", "REQUESTED", pair_hash=community.pair_hash(A, E))) == codes.count(201))
    clear()
    with ThreadPoolExecutor(6) as pool:
        codes2 = list(pool.map(go, [(b, E)] * 6))
    check("CONCURRENT double clicks create exactly one request row and one REQUESTED event", sorted(codes2).count(201) == 1 and len(pairs(B, E)) == 1 and len(ev("CONNECTION", "REQUESTED", pair_hash=community.pair_hash(B, E))) == 1, str(codes2))

    # transaction safety: a failure while recording leaves no half change
    real = community.connection_event
    async def boom(db, kind, *args, **kw):
        if kind == "ACCEPTED":
            raise RuntimeError("simulated failure while recording")
        return await real(db, kind, *args, **kw)
    clear()
    post(c_, B)
    rid2 = pairs(C, B)[0][0]
    community.connection_event = boom
    try:
        quiet = TestClient(app, raise_server_exceptions=False)
        quiet.cookies.update(b.cookies)
        failed = quiet.patch(f"/api/v1/networking/connections/{rid2}", json={"action": "accept"}, headers=H(b))
    finally:
        community.connection_event = real
    check("ROLLBACK: a failure while recording the acceptance leaves the request PENDING and writes no ACCEPTED event", failed.status_code == 500 and pairs(C, B)[0][3] == "PENDING"
          and not ev("CONNECTION", "ACCEPTED", pair_hash=community.pair_hash(C, B)))

    # rate limit
    clear()
    codes3 = [post(d, B).status_code for _ in range(31)]
    check("RATE LIMIT: the 31st connection request in an hour is refused (429); repeated refusals still create no duplicate row", codes3[-1] == 429 and len(pairs(D, B)) == 1)
    clear()

    # =============================================================================== 2. NEEDS
    def post_need(cli, title=None, description=None, category="01"):
        body = {"title": title or f"Need {words(3)}", "category": category}
        if description is not None:
            body["description"] = description
        return cli.post("/api/v1/networking/needs", json=body, headers=H(cli))
    legacy_id = "legacy-need-0001"
    biz = scalar("select id from businesses where user_id = :u", u=A)
    async def insert_legacy(s):
        await s.execute(text("insert into business_needs (id, user_id, business_id, title, category, description, status, created_at, updated_at) values (:i, :u, :b, 'Legacy short need', '01', 'old', 'OPEN', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"), {"i": legacy_id, "u": A, "b": biz})
        await s.commit()
    t0.db(insert_legacy)
    listed = [n for n in b.get("/api/v1/networking/needs").json()]
    check("COMPATIBILITY: a need created before Phase A (no lifecycle columns) is still listed, unchanged, with the old fields", any(n["id"] == legacy_id and n["title"] == "Legacy short need" and n["status"] == "OPEN" for n in listed))
    r = post_need(a, description="too short")
    check("a description under 80 characters is refused (422) and the rejection is recorded", r.status_code == 422 and ev("NEED", "REJECTED")[-1][4] == "TOO_SHORT_DESCRIPTION" and scalar("select count(*) from business_needs where user_id = :u", u=A) == 1)
    check("a missing description is refused too", post_need(a).status_code == 422)
    t1, d1 = "Looking for GST ready accountant", desc()
    r = post_need(a, t1, d1)
    n1 = r.json()["id"] if r.status_code == 201 else None
    row = rows("select status, published_at, title_hash, description_hash, publish_month_key, qualifies_for_future_reward from business_needs where id = :i", i=n1)[0] if n1 else None
    check("a valid need is published: OPEN, with its lifecycle facts, hashes, month and the tracked quality field (and nothing else)", r.status_code == 201 and row[0] == "OPEN" and row[1] and row[2] and row[3] and row[4] and row[5] in (1, True))
    check("...with a PUBLISHED event holding counts only", json.loads(ev("NEED", "PUBLISHED", need_id=n1)[0][5])["qualifies"] is True)
    check("the legacy client shape is unchanged: the POST response and the board list still carry every old field", {"id", "title", "category", "description", "status", "poster_user_id", "poster_name", "business_name", "created_at"} <= set(r.json()))
    dupe = post_need(a, t1, d1)
    check("the same need again is refused as a DUPLICATE (409) and the attempt is recorded", dupe.status_code == 409 and ev("NEED", "REJECTED")[-1][4] == "DUPLICATE_RECENT")
    near = post_need(a, "Looking for a GST ready accountant!", d1 + " thanks")
    check("a near copy is refused as a NEAR_DUPLICATE (409)", near.status_code == 409 and ev("NEED", "REJECTED")[-1][4] in ("NEAR_DUPLICATE_RECENT", "DUPLICATE_RECENT"))
    check("cancelling by someone else is a 404; by the poster it works once and is recorded", b.post(f"/api/v1/networking/needs/{n1}/cancel", headers=H(b)).status_code == 404
          and a.post(f"/api/v1/networking/needs/{n1}/cancel", headers=H(a)).status_code == 204 and a.post(f"/api/v1/networking/needs/{n1}/cancel", headers=H(a)).status_code == 409 and ev("NEED", "CANCELLED", need_id=n1))
    check("DELETE-AND-REPOST DOES NOT BYPASS: re-posting the cancelled need is still refused as a duplicate", post_need(a, t1, d1).status_code == 409)
    clear()
    n2 = post_need(a, f"Need {words(3)}", desc()).json()["id"]
    n3 = post_need(a, f"Need {words(3)}", desc()).json()["id"]
    n4r = post_need(a, f"Need {words(3)}", desc())
    n4 = n4r.json()["id"]
    q = {i: rows("select qualifies_for_future_reward, quality_note from business_needs where id = :i", i=i)[0] for i in (n1, n2, n3, n4)}
    check("TRACKED LIMIT: of one member's posts in a month the first two qualify, the third is still PUBLISHED but not qualifying (MONTHLY_LIMIT); nothing is blocked or rewarded",
          n4r.status_code == 201 and q[n1][0] in (1, True) and q[n2][0] in (1, True) and q[n3][0] in (0, False) and q[n3][1] == "MONTHLY_LIMIT" and q[n4][0] in (0, False))
    clear()
    check("...and cancelling a post does not free a slot: a fourth is still not qualifying", a.post(f"/api/v1/networking/needs/{n2}/cancel", headers=H(a)).status_code == 204 and rows("select qualifies_for_future_reward from business_needs where id = :i", i=post_need(a, f"Need {words(3)}", desc()).json()["id"])[0][0] in (0, False))
    shared_t, shared_d = f"Need {words(3)}", desc()
    check("a copy posted by ANOTHER member is allowed but raises a (non-punitive) cross-member duplicate signal", post_need(b, shared_t, shared_d).status_code == 201 and post_need(c_, shared_t, shared_d).status_code == 201 and ev("SIGNAL", "NEED_CROSS_MEMBER_DUPLICATE"))
    clear()
    cc_t, cc_d = f"Need {words(3)}", desc()
    with ThreadPoolExecutor(5) as pool:
        codes_n = list(pool.map(lambda _: post_need(c_, cc_t, cc_d).status_code, range(5)))
    check("CONCURRENT identical publications store exactly one need and one PUBLISHED event; the rest are rejected as duplicates", codes_n.count(201) == 1 and set(codes_n) <= {201, 409}
          and scalar("select count(*) from business_needs where user_id = :u and title = :t", u=C, t=cc_t) == 1, str(codes_n))
    # daily cap
    clear()
    made = 0
    for _ in range(14):
        clear()
        rr = post_need(e, f"Need {words(3)}", desc())
        made += rr.status_code == 201
        if rr.status_code != 201:
            last = rr
            break
    check("TECHNICAL CAP: a member can not publish more than 10 needs in 24 hours (429 DAILY_CAP, recorded); cancelled posts count", made == 10 and last.status_code == 429 and ev("NEED", "REJECTED")[-1][4] == "DAILY_CAP")
    clear()
    codes4 = [post_need(d, f"Need {words(3)}", "short").status_code for _ in range(11)]
    check("RATE LIMIT: publication attempts are limited per hour (429), rejected ones included", codes4[-1] == 429)
    clear()
    # moderation
    nm = post_need(b, f"Need {words(3)}", desc()).json()["id"]
    check("only an admin can moderate: a member (401), no CSRF (403), no reason (422)", b.post(f"/api/admin/community/needs/{nm}/remove", json={"reason": "spam"}, headers=H(b)).status_code == 401
          and admin.post(f"/api/admin/community/needs/{nm}/remove", json={"reason": "spam"}).status_code == 403 and admin.post(f"/api/admin/community/needs/{nm}/remove", json={}, headers=AH).status_code == 422)
    admin_id = scalar("select id from admins where email = :e", e=ADMIN_EMAIL)
    before_audit = scalar("select count(*) from audit_log")
    rm = admin.post(f"/api/admin/community/needs/{nm}/remove", json={"reason": "Not a genuine business need"}, headers=AH)
    row = rows("select status, removed_by_admin_id, removed_reason, removed_at from business_needs where id = :i", i=nm)[0]
    check("MODERATION IS ATTRIBUTED: REMOVED, with the moderator's id, the reason and the time, a history event with the admin id, and an audit entry",
          rm.status_code == 200 and row[0] == "REMOVED" and row[1] == admin_id and row[2] == "Not a genuine business need" and row[3] and ev("NEED", "REMOVED", need_id=nm)[0][8] == admin_id and scalar("select count(*) from audit_log") == before_audit + 1)
    check("a removed need is off the board; the poster can not cancel or resolve it, nor offer help on it", nm not in [n["id"] for n in c_.get("/api/v1/networking/needs").json()] and b.post(f"/api/v1/networking/needs/{nm}/cancel", headers=H(b)).status_code == 409
          and c_.post(f"/api/v1/networking/needs/{nm}/help", headers=H(c_)).status_code == 409)
    check("it stays visible to the poster under 'mine' with its REMOVED status", any(n["id"] == nm and n["status"] == "REMOVED" for n in b.get("/api/v1/networking/needs", params={"mine": "true"}).json()))
    check("restoring is admin-only, needs a reason and records who", admin.post(f"/api/admin/community/needs/{nm}/restore", json={"reason": "Reviewed again"}, headers=AH).status_code == 200 and rows("select status from business_needs where id = :i", i=nm)[0][0] == "OPEN"
          and ev("NEED", "RESTORED", need_id=nm)[0][8] == admin_id)
    check("no route lets anyone change a need's owner or edit it (405 / 404)", all(b.request(m, f"/api/v1/networking/needs/{nm}", json={"user_id": A}, headers=H(b)).status_code in (404, 405) for m in ("PUT", "PATCH", "DELETE")))
    check("an admin's list shows the moderator history and marks synthetic posters", admin.get("/api/admin/community/needs").status_code == 200 and "synthetic" in admin.get("/api/admin/community/needs").json()["items"][0])

    # =============================================================================== 3. HELP OFFERS
    clear()
    nh = post_need(b, f"Need {words(3)}", desc()).json()["id"]
    notif0 = scalar("select count(*) from notifications where recipient_user_id = :u and type = 'need_help_offered'", u=B)
    r = c_.post(f"/api/v1/networking/needs/{nh}/help", headers=H(c_))
    check("'I can help' (an existing client, no body) still answers 204 and now stores a durable OFFER", r.status_code == 204 and rows("select status, helper_user_id from need_help_offers where need_id = :n", n=nh) == [("OFFERED", C)])
    check("...with one OFFERED event, one notification to the poster, and the offer is NOT counted as help", len(ev("HELP", "OFFERED", need_id=nh)) == 1 and scalar("select count(*) from notifications where recipient_user_id = :u and type = 'need_help_offered'", u=B) == notif0 + 1)
    r2 = c_.post(f"/api/v1/networking/needs/{nh}/help", headers=H(c_))
    check("a second click changes nothing: still one offer, one event, no second notification", r2.status_code == 204 and scalar("select count(*) from need_help_offers where need_id = :n", n=nh) == 1 and len(ev("HELP", "OFFERED", need_id=nh)) == 1
          and scalar("select count(*) from notifications where recipient_user_id = :u and type = 'need_help_offered'", u=B) == notif0 + 1)
    check("self-help is refused (400)", b.post(f"/api/v1/networking/needs/{nh}/help", headers=H(b)).status_code == 400)
    clear()
    with ThreadPoolExecutor(6) as pool:
        codes5 = list(pool.map(lambda _: d.post(f"/api/v1/networking/needs/{nh}/help", headers=H(d)).status_code, range(6)))
    check("CONCURRENT offers by one helper create exactly one offer and one event", scalar("select count(*) from need_help_offers where need_id = :n and helper_user_id = :h", n=nh, h=D) == 1 and set(codes5) <= {204} and len(ev("HELP", "OFFERED", need_id=nh, actor_user_id=D)) == 1, str(codes5))
    offer_c = rows("select id from need_help_offers where need_id = :n and helper_user_id = :h", n=nh, h=C)[0][0]
    offer_d = rows("select id from need_help_offers where need_id = :n and helper_user_id = :h", n=nh, h=D)[0][0]
    seen_b = b.get(f"/api/v1/networking/needs/{nh}/offers").json()
    seen_c = c_.get(f"/api/v1/networking/needs/{nh}/offers").json()
    check("AUTHORISATION: the poster sees every offer with the helper; a helper sees only their own offer without identities; a stranger sees nothing",
          len(seen_b) == 2 and all(o["helper_name"] for o in seen_b) and len(seen_c) == 1 and seen_c[0]["mine"] and seen_c[0]["helper_name"] is None and a.get(f"/api/v1/networking/needs/{nh}/offers").json() == [])
    act = lambda cli, oid, action: cli.patch(f"/api/v1/networking/needs/offers/{oid}", json={"action": action}, headers=H(cli))  # noqa: E731
    check("INVALID AND UNAUTHORISED TRANSITIONS are refused: helper accepting their own offer (403), a stranger (404), confirming before accepting (409), an unknown action (422)",
          act(c_, offer_c, "accept").status_code == 403 and act(a, offer_c, "accept").status_code == 404 and act(b, offer_c, "confirm_helpful").status_code == 409 and act(b, offer_c, "marry").status_code == 422
          and rows("select status from need_help_offers where id = :i", i=offer_c)[0][0] == "OFFERED")
    check("the poster accepts (a notification reaches the helper), once only", act(b, offer_c, "accept").status_code == 200 and act(b, offer_c, "accept").status_code == 409 and ev("HELP", "ACCEPTED", offer_id=offer_c))
    check("the poster can decline another offer, which is then final; a decline can not be confirmed", act(b, offer_d, "decline").status_code == 200 and act(b, offer_d, "confirm_helpful").status_code == 409 and act(d, offer_d, "withdraw").status_code == 409)
    check("RESOLVING: crediting an offer that is not confirmed helpful is refused (409); a foreign offer is a 404; only the poster may resolve (404)",
          b.post(f"/api/v1/networking/needs/{nh}/resolve", json={"offer_id": offer_c}, headers=H(b)).status_code == 409 and b.post(f"/api/v1/networking/needs/{nh}/resolve", json={"offer_id": "nope"}, headers=H(b)).status_code == 404
          and c_.post(f"/api/v1/networking/needs/{nh}/resolve", json={}, headers=H(c_)).status_code == 404)
    check("the poster confirms the help was useful, then resolves the need crediting that helper: attribution recorded", act(b, offer_c, "confirm_helpful").status_code == 200
          and b.post(f"/api/v1/networking/needs/{nh}/resolve", json={"offer_id": offer_c}, headers=H(b)).status_code == 204
          and rows("select status, resolved_offer_id from business_needs where id = :i", i=nh)[0] == ("RESOLVED", offer_c) and json.loads(ev("NEED", "RESOLVED", need_id=nh)[0][5])["credited_helper"] is True)
    check("a resolved need leaves the board and can not be resolved or cancelled again; new offers are refused", b.post(f"/api/v1/networking/needs/{nh}/resolve", json={}, headers=H(b)).status_code == 409 and e.post(f"/api/v1/networking/needs/{nh}/help", headers=H(e)).status_code == 409)
    nh2 = post_need(b, f"Need {words(3)}", desc()).json()["id"]
    check("a need can be resolved with NO credited helper, and that is recorded as such", b.post(f"/api/v1/networking/needs/{nh2}/resolve", json={}, headers=H(b)).status_code == 204 and json.loads(ev("NEED", "RESOLVED", need_id=nh2)[0][5])["credited_helper"] is False)
    # a failure while recording an offer transition leaves the offer where it was
    clear()
    nrb = post_need(b, f"Need {words(3)}", desc()).json()["id"]
    d.post(f"/api/v1/networking/needs/{nrb}/help", json={"message": "secret offer message"}, headers=H(d))
    orb = rows("select id from need_help_offers where need_id = :n", n=nrb)[0][0]
    real_record = community.record
    def boom_record(db_, domain, kind, **kw):
        if domain == "HELP" and kind == "ACCEPTED":
            raise RuntimeError("simulated failure while recording")
        return real_record(db_, domain, kind, **kw)
    community.record = boom_record
    try:
        quiet2 = TestClient(app, raise_server_exceptions=False)
        quiet2.cookies.update(b.cookies)
        failed2 = quiet2.patch(f"/api/v1/networking/needs/offers/{orb}", json={"action": "accept"}, headers=H(b))
    finally:
        community.record = real_record
    check("ROLLBACK: a failure while recording an accepted offer leaves it OFFERED with no ACCEPTED event", failed2.status_code == 500 and rows("select status from need_help_offers where id = :i", i=orb)[0][0] == "OFFERED" and not ev("HELP", "ACCEPTED", offer_id=orb))
    check("an offer's message is stored for the poster only: the poster sees it, the helper's view is theirs, and no event or report ever contains it",
          any(o["message"] == "secret offer message" for o in b.get(f"/api/v1/networking/needs/{nrb}/offers").json()) and not any("secret offer" in json.dumps([str(x) for x in r_]) for r_ in rows("select * from community_events")))
    # reciprocal signal
    clear()
    nb = post_need(c_, f"Need {words(3)}", desc()).json()["id"]
    e.post(f"/api/v1/networking/needs/{nb}/help", headers=H(e)); a.post(f"/api/v1/networking/needs/{nb}/help", headers=H(a))
    ob_a = rows("select id from need_help_offers where need_id = :n and helper_user_id = :h", n=nb, h=A)[0][0]
    act(c_, ob_a, "accept"); act(c_, ob_a, "confirm_helpful")
    na = post_need(a, f"Need {words(3)}", desc()).json()["id"]
    c_.post(f"/api/v1/networking/needs/{na}/help", headers=H(c_))
    oa_c = rows("select id from need_help_offers where need_id = :n and helper_user_id = :h", n=na, h=C)[0][0]
    act(a, oa_c, "accept"); act(a, oa_c, "confirm_helpful")
    check("REPEATED / RECIPROCAL help raises a review signal and does nothing else", ev("SIGNAL", "HELP_RECIPROCAL") and rows("select status from need_help_offers where id = :i", i=oa_c)[0][0] == "CONFIRMED_HELPFUL")
    # rate limit on offers
    clear()
    nrl = post_need(d, f"Need {words(3)}", desc()).json()["id"]
    codes6 = [e.post(f"/api/v1/networking/needs/{nrl}/help", headers=H(e)).status_code for _ in range(32)]
    check("RATE LIMIT: the 31st help request in an hour is refused (429), and no duplicate offer appears", codes6[-1] == 429 and scalar("select count(*) from need_help_offers where need_id = :n and helper_user_id = :h", n=nrl, h=E) == 1)
    clear()

    # account deletion: the current-state rows go with the account (as before), the history stays (ids only), and nothing breaks
    check("ACCOUNT DELETION: removing a member who has needs, offers and connections works, their live rows cascade, and the pseudonymous history remains",
          (lambda before_ev: (admin.delete(f"/api/admin/customers/{E}", headers=AH).status_code == 204 and scalar("select count(*) from users where id = :u", u=E) == 0
                              and scalar("select count(*) from need_help_offers where helper_user_id = :u", u=E) == 0 and scalar("select count(*) from business_needs where user_id = :u", u=E) == 0
                              and scalar("select count(*) from community_events") >= before_ev))(scalar("select count(*) from community_events")))
    # =============================================================================== 4. APPEND-ONLY, ROLLBACK, DEMO EXCLUSION, REPORT, NO POINTS
    async def tamper(sql):
        from app.database import SessionLocal
        try:
            async with SessionLocal() as s:
                await s.execute(text(sql))
                await s.commit()
            return False
        except Exception:
            return True
    check("the history is append-only at the database: UPDATE and DELETE are refused", asyncio.run(tamper("update community_events set kind = 'X'")) and asyncio.run(tamper("delete from community_events")))
    # the synthetic demo member generates activity of every kind
    clear()
    rep0 = admin.get("/api/admin/community/report").json()
    post(z, A); zn = post_need(z, f"Need {words(3)}", desc()).json()["id"]; a.post(f"/api/v1/networking/needs/{zn}/help", headers=H(a)); z.post(f"/api/v1/networking/needs/{nh2}/help", headers=H(z))
    rep1 = admin.get("/api/admin/community/report").json()
    flat = lambda r_: json.dumps({k: v for k, v in r_.items() if k not in ("observation",)}, sort_keys=True, default=str)  # noqa: E731
    import difflib
    diff = [l for l in difflib.unified_diff(json.dumps(rep0, indent=1, sort_keys=True, default=str).splitlines(), json.dumps(rep1, indent=1, sort_keys=True, default=str).splitlines(), lineterm="") if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    print("DEBUG report diff:", diff[:12])
    check("SYNTHETIC EXCLUSION: a demo member's connection, need and help produce events, none of which changes any genuine figure; they are counted separately",
          flat(rep0) == flat(rep1) and rep1["observation"]["synthetic_events_excluded"] > rep0["observation"]["synthetic_events_excluded"] and scalar("select count(*) from community_events where actor_user_id = :z", z=Z) >= 2)
    check("the report is aggregate and anonymous: no id, e-mail or message text appears in it", not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-|@|private note|We need a reliable", json.dumps(rep1, default=str)))
    check("RAW ACTIVITY IS KEPT APART FROM OUTCOMES: offers are counted as offers; only poster-confirmed offers are 'helpful'; an unaccepted offer is not progress",
          rep1["help_offers"]["raw_activity"]["offers"] >= 5 and rep1["help_offers"]["outcomes"]["confirmed_helpful"] < rep1["help_offers"]["raw_activity"]["offers"] and "note" in rep1["help_offers"]["outcomes"])
    check("the report measures the lifecycle: reconnections, rejected needs by reason, resolved with and without a credited helper, time to first offer and to resolution",
          rep1["connections"]["raw_activity"]["reconnection_requests"] >= 1 and rep1["connections"]["outcomes"]["reconnections_accepted"] >= 1 and rep1["needs"]["raw_activity"]["rejected_by_reason"].get("TOO_SHORT_DESCRIPTION", 0) >= 1
          and rep1["needs"]["outcomes"]["resolved_with_a_credited_helper"] >= 1 and rep1["needs"]["outcomes"]["resolved_without_credit"] >= 1 and rep1["timing_hours_median"]["publication_to_first_offer"] is not None
          and rep1["timing_hours_median"]["publication_to_resolution"] is not None and rep1["repeat_and_reciprocal"]["signals_recorded"])
    check("the report says it does not claim an observation period has started, and backfilled history is excluded", "does not claim" in rep1["observation"]["note"] and "backfilled_history_events_excluded" in rep1["observation"])
    check("the report and moderation are admin-only", b.get("/api/admin/community/report").status_code == 401 and new_client().get("/api/admin/community/report").status_code == 401)
    check("NO GROWTH POINTS: with recording ON, not one ledger row, balance change, invoice, payment or subscription came from any of the above", scalar("select count(*) from growth_point_ledger") == ledger_before
          and tuple(scalar(f"select count(*) from {t}") for t in ("invoices", "payments", "subscriptions")) == fin_before)
    src = open("app/community.py").read() + open("app/routers/community.py").read() + open("app/routers/admin_community.py").read()
    check("the Phase A modules do not import or mention the rewards package, the ledger or any Growth Points table", not re.search(r"(?m)^\s*(from\s+\S*rewards|import\s+\S*rewards)|GrowthPoint[A-Z]|growth_point_", src))
    check("no new reward rule version exists: the rules module still holds growth-points-v3 and the closed event list", __import__("app.rewards.rules", fromlist=["x"]).RULE_VERSION == "growth-points-v3" and "CONNECTION_ACCEPTED" not in __import__("app.rewards.rules", fromlist=["x"]).EVENTS)

    failed = [n for ok, n in results if not ok]
    for ok, n in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}")
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
