"""Demo photo isolation: synthetic demo photos live in their own directory and namespace, and seeding / cleanup / migration can never touch a genuine photo.

Targeted. Run:  .venv/bin/python test_demo_isolation.py      (SQLite, or TEST_DATABASE_URL=postgresql+asyncpg://... for PostgreSQL)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import test_phase0 as t0
from test_phase0 import ADMIN_EMAIL, PASSWORD, TMP, H, check, member_client, me, new_client, results, scalar

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text
from starlette.datastructures import UploadFile

from app import demo, storage
from app.database import SessionLocal
from app.main import app
from app.models import User

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import seed_demo_members as seeder  # noqa: E402


def go(fn):
    async def f():
        async with SessionLocal() as s:
            r = await fn(s)
            await s.commit()
            return r
    return asyncio.run(f())


def png(color=(10, 120, 200)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(b, "PNG")
    return b.getvalue()


def jpg(color) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(b, "JPEG")
    return b.getvalue()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def main() -> int:
    asyncio.run(t0.seed())
    with TestClient(app):
        return body()


def body() -> int:
    photos, demo_dir = storage.photo_root(), storage.demo_photo_root()
    ZERO_DEMO = "demo-" + "0" * 32 + ".jpg"
    check("the demo directory is a different directory from the genuine photos directory, and not inside it", demo_dir != photos and photos not in demo_dir.parents and demo_dir not in photos.parents)

    # --- genuine members with real uploads, and an unrelated stray file in each directory
    a, b = member_client("real-a@example.com", "Real Alpha"), member_client("real-b@example.com", "Real Beta")
    for c, colour in ((a, (200, 30, 30)), (b, (30, 200, 30))):
        r = c.post("/api/v1/profile/photo", files={"photo": ("p.png", io.BytesIO(png(colour)), "image/png")}, headers=H(c))
        assert r.status_code in (200, 201), r.text
    a_id, b_id = me(a), me(b)
    a_key = scalar("select photo_key from users where id = :i", i=a_id)
    (photos / ("0" * 32 + ".jpg")).write_bytes(b"stray genuine-directory file nobody references")
    (demo_dir / ZERO_DEMO).write_bytes(b"stray demo-directory file nobody references")
    (demo_dir / "notes.txt").write_text("unrelated")
    genuine_before = tree(photos)
    check("setup: two genuine members have their own photos in the genuine directory (plain names, no demo prefix)", len(genuine_before) == 3 and a_key and not a_key.startswith("demo-") and (photos / a_key).is_file())

    # --- seeding
    manifest = Path(TMP) / "manifest.json"
    kw = dict(count=30, assets_dir=Path(TMP) / "avatars", fetch_images=False, manifest_path=manifest)
    first = asyncio.run(seeder.seed(SessionLocal, **kw))
    keys = [k for (k,) in go(lambda s: s.execute(select(User.photo_key).where(demo.synthetic_clause())))]
    in_demo = sorted(p.name for p in demo_dir.glob("demo-*.jpg") if p.name != ZERO_DEMO)
    check("SEED: 30 synthetic members, each with a `demo-` photo stored in the demo directory", first["created_now"] == 30 and first["photos_stored_now"] == 30 and len(keys) == 30 and all(storage.is_demo_photo(k) for k in keys) and sorted(keys) == in_demo)
    check("ISOLATION: seeding wrote NOTHING to the genuine photos directory (every file there is byte-identical to before)", tree(photos) == genuine_before)
    m = json.loads(manifest.read_text())
    check("MANIFEST: it records each demo photo and its checksum (the ownership record for cleanup)", len(m["members"]) == 30 and all(x.get("photo") in keys and len(x.get("photo_sha256", "")) == 64 for x in m["members"]))

    second = asyncio.run(seeder.seed(SessionLocal, **kw))
    keys2 = [k for (k,) in go(lambda s: s.execute(select(User.photo_key).where(demo.synthetic_clause())))]
    check("IDEMPOTENT: a second run creates no member and no photo and keeps the same photo for every member", second["created_now"] == 0 and second["photos_stored_now"] == 0 and sorted(keys2) == sorted(keys) and scalar("select count(*) from users where email like '%@demo.example.com'") == 30)

    # --- collisions
    new_plain = asyncio.run(storage.save_profile_photo(UploadFile(file=io.BytesIO(png((1, 2, 3))), filename="x.png")))
    check("COLLISION: a genuine upload can never get a demo name or land in the demo directory, and its name is random (never equal to a demo name)", not new_plain.startswith("demo-") and (photos / new_plain).is_file() and not (demo_dir / new_plain).exists() and new_plain not in keys)
    asyncio.run(storage.delete_profile_photo(new_plain))
    forged = "demo-" + a_key
    check("COLLISION: a demo-style name built from a genuine photo's name resolves only inside the demo directory: it cannot delete the genuine file", asyncio.run(storage.delete_profile_photo(forged)) is False and (photos / a_key).is_file())
    try:
        asyncio.run(storage.read_profile_photo(forged))
        read_forged = True
    except Exception:
        read_forged = False
    check("COLLISION: reading that forged demo name is a 404, not the genuine photo", read_forged is False)

    # --- the app serves both kinds correctly
    check("SERVING: a genuine member's own photo is served from the genuine directory", a.get(f"/api/v1/members/{a_id}/photo").status_code == 200 and a.get(f"/api/v1/members/{a_id}/photo").content == (photos / a_key).read_bytes())
    demo_user = go(lambda s: s.scalar(select(User).where(User.email == "demo-01@demo.example.com")))
    own = new_client()
    r = own.post("/api/v1/auth/login", json={"email": "demo-01@demo.example.com", "password": demo.DEMO_PASSWORD})
    got = own.get(f"/api/v1/members/{demo_user.id}/photo") if r.status_code == 200 else None
    check("SERVING: a demo member's photo is served from the demo directory (the demo member signs in and sees their own picture)", got is not None and got.status_code == 200 and got.content == (demo_dir / demo_user.photo_key).read_bytes() and got.content[:3] == b"\xff\xd8\xff", f"{r.status_code}")

    # --- the admin Demo tab: a narrow, admin-only, read-only image route (the members-only photo route is unchanged)
    from app.config import settings as cfg
    admin = new_client()
    assert admin.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD}).status_code == 200
    original_env = cfg.environment
    demo_ids = {e: i for i, e in go(lambda s_: s_.execute(select(User.id, User.email).where(demo.synthetic_clause())))}
    d1 = demo_ids["demo-01@demo.example.com"]
    URL = "/api/admin/growth-points/demo-members/{}/photo"
    wanted = (demo_dir / demo_user.photo_key).read_bytes()
    r_admin = admin.get(URL.format(demo_user.id))
    check("ADMIN PHOTO: an administrator gets the demo member's picture (JPEG, same bytes as the demo file, nosniff, private cache)",
          r_admin.status_code == 200 and r_admin.content == wanted and r_admin.headers["content-type"] == "image/jpeg" and r_admin.headers.get("x-content-type-options") == "nosniff" and "private" in r_admin.headers.get("cache-control", ""))
    check("ADMIN PHOTO: an unauthenticated visitor is refused (401) and learns nothing", new_client().get(URL.format(demo_user.id)).status_code == 401)
    check("ADMIN PHOTO: an ordinary member, even one with a full session and Networking access, is refused (401); the genuine members' own sessions work only on the member route",
          a.get(URL.format(demo_user.id)).status_code == 401 and own.get(URL.format(demo_user.id)).status_code == 401)
    check("ADMIN PHOTO: a GENUINE member's photo is never served by it, even to an administrator (404, same as a made-up id)",
          admin.get(URL.format(a_id)).status_code == 404 and admin.get(URL.format(b_id)).status_code == 404 and admin.get(URL.format("00000000-0000-0000-0000-000000000000")).status_code == 404)
    check("ADMIN PHOTO: ids that look like paths or traversal are refused (404/422), and nothing outside the demo directory is read",
          all(admin.get("/api/admin/growth-points/demo-members/" + bad + "/photo").status_code in (404, 422) for bad in ("..%2f..%2fphotos%2f" + a_key, "%2e%2e", a_key, "../" + a_key)))
    go(lambda s_: s_.execute(text("update users set photo_key = null where id = :i"), {"i": d1}))
    check("ADMIN PHOTO: a demo member with no photo gives a clean 404 (the tab then shows initials)", admin.get(URL.format(d1)).status_code == 404)
    go(lambda s_: s_.execute(text("update users set photo_key = :k where id = :i"), {"k": "demo-" + "9" * 32 + ".jpg", "i": d1}))
    check("ADMIN PHOTO: a stored name whose file is missing gives a clean 404, not an error", admin.get(URL.format(d1)).status_code == 404)
    go(lambda s_: s_.execute(text("update users set photo_key = :k where id = :i"), {"k": a_key, "i": d1}))
    check("ADMIN PHOTO: even if a demo row were pointed at a genuine photo's plain name, the route refuses it (only demo-namespace files)", admin.get(URL.format(d1)).status_code == 404)
    go(lambda s_: s_.execute(text("update users set photo_key = :k where id = :i"), {"k": demo_user.photo_key, "i": d1}))
    listing = admin.get("/api/admin/growth-points/demo-members").json()["items"]
    check("ADMIN LIST: every demo member's photo_url is the admin route (never the members-only one) and loads for the administrator",
          len(listing) == 30 and all(i["photo_url"].startswith("/api/admin/growth-points/demo-members/") for i in listing if i["photo_url"]) and admin.get(listing[0]["photo_url"]).status_code == 200 and "/api/v1/members/" not in json.dumps(listing))
    object.__setattr__(cfg, "environment", "production")
    try:
        prod_photo = admin.get(URL.format(demo_user.id)).status_code
    finally:
        object.__setattr__(cfg, "environment", original_env)
    check("ADMIN PHOTO: in production the route does not exist in effect (404)", prod_photo == 404)
    check("MEMBER PHOTO ROUTE: unchanged: it still refuses an unauthenticated visitor, and a genuine member's photo is still served to the members allowed to see it",
          new_client().get(f"/api/v1/members/{a_id}/photo").status_code == 401 and a.get(f"/api/v1/members/{a_id}/photo").status_code == 200)

    # --- Supabase never holds or serves demo photos
    real_flag = storage._use_supabase
    storage._use_supabase = lambda: True
    try:
        try:
            asyncio.run(storage.save_profile_photo(UploadFile(file=io.BytesIO(png()), filename="x.png"), demo=True))
            sup_save = True
        except RuntimeError:
            sup_save = False
        try:
            asyncio.run(storage.read_profile_photo(keys[0]))
            sup_read = True
        except Exception:
            sup_read = False
        sup_del = asyncio.run(storage.delete_profile_photo(keys[0]))
    finally:
        storage._use_supabase = real_flag
    check("SUPABASE: with remote storage a demo photo can not be stored, read or deleted (demo assets are local-only)", not sup_save and not sup_read and sup_del is False and (demo_dir / keys[0]).is_file())

    # --- legacy photos: refused when a genuine user uses the file, moved when only demo members do
    legacy, shared = "1" * 32 + ".jpg", "2" * 32 + ".jpg"
    # the test repoints demo-03 and demo-04 at plain legacy names below, which leaves their original demo files unreferenced: cleanup must NOT remove those either
    orphans = {k for (k,) in go(lambda s: s.execute(select(User.photo_key).where(User.email.in_(["demo-03@demo.example.com", "demo-04@demo.example.com"]))))}
    (photos / legacy).write_bytes(jpg((9, 9, 9)))
    (photos / shared).write_bytes(jpg((8, 8, 8)))

    async def set_keys(s):
        await s.execute(text("update users set photo_key = :k where email = 'demo-03@demo.example.com'"), {"k": legacy})
        await s.execute(text("update users set photo_key = :k where email = 'demo-04@demo.example.com'"), {"k": shared})
        await s.execute(text("update users set photo_key = :k where id = :i"), {"k": shared, "i": b_id})
    go(set_keys)
    before_files = tree(photos)
    dry = asyncio.run(seeder.migrate_legacy_photos(SessionLocal, dry_run=True, reference_dbs=[]))
    check("MIGRATE (dry run): changes nothing", tree(photos) == before_files and dry["planned"] and not dry["moved"])
    clean = asyncio.run(seeder.cleanup(SessionLocal, manifest))
    check("CLEANUP: a synthetic member whose photo is an older plain name in the SHARED directory is left alone (file and row), with the reason reported",
          (photos / legacy).is_file() and (photos / shared).is_file() and any(x["email"] == "demo-03@demo.example.com" for x in clean["photos_left_in_place"]) and scalar("select photo_key from users where email = 'demo-03@demo.example.com'") == legacy)
    asyncio.run(seeder.seed(SessionLocal, **kw))          # cleanup removed the other demo photos; the reseed restores them (members 03 and 04 keep their legacy names)
    go(lambda s: s.execute(text("update users set is_active = :t where email in ('demo-03@demo.example.com', 'demo-04@demo.example.com')"), {"t": True}))
    mig = asyncio.run(seeder.migrate_legacy_photos(SessionLocal, reference_dbs=[]))
    moved_to = scalar("select photo_key from users where email = 'demo-03@demo.example.com'")
    check("MIGRATE: a demo-only legacy photo is copied to the demo directory, verified, the row repointed and the old file removed", mig["moved"] >= 1 and moved_to == "demo-" + legacy and (demo_dir / moved_to).read_bytes() == jpg((9, 9, 9)) and not (photos / legacy).exists())
    check("MIGRATE: a file that a GENUINE member also uses is refused: it stays where it is, byte for byte, and the genuine member's row is untouched",
          any(x["email"] == "demo-04@demo.example.com" for x in mig["refused"]) and (photos / shared).read_bytes() == jpg((8, 8, 8)) and scalar("select photo_key from users where id = :i", i=b_id) == shared)
    go(lambda s: s.execute(text("update users set photo_key = null where email = 'demo-04@demo.example.com'")))   # test housekeeping: restore b's photo state
    (photos / shared).unlink()
    go(lambda s: s.execute(text("update users set photo_key = null where id = :i"), {"i": b_id}))

    # --- cleanup removes only demo-owned files; reseed restores them
    asyncio.run(seeder.seed(SessionLocal, **kw))
    owned = {k for (k,) in go(lambda s: s.execute(select(User.photo_key).where(demo.synthetic_clause()))) if k}
    check("setup: every demo member references one demo file; the stray demo-named file and notes.txt are not referenced", len(owned) == 30 and (demo_dir / ZERO_DEMO).is_file() and ZERO_DEMO not in owned)
    genuine_now = tree(photos)
    clean2 = asyncio.run(seeder.cleanup(SessionLocal, manifest))
    left = {p.name for p in demo_dir.iterdir() if p.is_file()}
    check("CLEANUP: removes exactly the 30 files the demo members own; every unreferenced file (a stray demo-named file, two orphaned demo photos, notes.txt) stays", clean2["demo_photos_removed"] == 30 and left == {ZERO_DEMO, "notes.txt"} | orphans and not (owned & left), f"removed={clean2['demo_photos_removed']} left={sorted(left)[:4]} skipped={clean2['photos_left_in_place'][:2]}")
    check("CLEANUP: every genuine photo and the stray file in the genuine directory are byte-identical afterwards; the genuine member still has their picture", tree(photos) == genuine_now and (photos / a_key).is_file() and a.get(f"/api/v1/members/{a_id}/photo").status_code == 200)
    check("CLEANUP: the synthetic members are deactivated with no photo, and no genuine user was changed",
          scalar("select count(*) from users where email like '%@demo.example.com' and (is_active = :t or photo_key is not null)", t=True) == 0 and scalar("select count(*) from users where email not like '%@demo.example.com' and is_active = :t", t=False) == 0)

    # --- seed again after cleanup
    again = asyncio.run(seeder.seed(SessionLocal, **kw))
    keys3 = [k for (k,) in go(lambda s: s.execute(select(User.photo_key).where(demo.synthetic_clause())))]
    check("RESEED: after cleanup the same 30 members are active again with 30 NEW demo photos, nothing duplicated, genuine files untouched",
          again["created_now"] == 0 and again["photos_stored_now"] == 30 and len(set(keys3)) == 30 and all(storage.is_demo_photo(k) for k in keys3) and not (set(keys3) & owned)
          and scalar("select count(*) from users where email like '%@demo.example.com' and is_active = :t", t=True) == 30 and scalar("select count(*) from users where email like '%@demo.example.com'") == 30
          and tree(photos) == genuine_now)

    # --- a modified file is not removed
    (demo_dir / keys3[0]).write_bytes(b"someone replaced this file")
    clean3 = asyncio.run(seeder.cleanup(SessionLocal, manifest))
    check("CLEANUP: a demo-named file whose checksum no longer matches the manifest is left in place and reported", (demo_dir / keys3[0]).is_file() and any("checksum" in x["reason"] for x in clean3["photos_left_in_place"]) and clean3["demo_photos_removed"] == 29)

    # --- the command line really uses --database-url (it used to be ignored once `app` had been imported at module level)
    other_db, default_db = Path(TMP) / "other_demo.db", Path(TMP) / "default_should_stay_empty.db"
    env = {**os.environ, "UPLOAD_DIR": str(Path(TMP) / "cli_uploads"), "TGL_DEMO_MANIFEST_DIR": str(Path(TMP) / "manifests"), "ENVIRONMENT": "development", "DATABASE_URL": f"sqlite+aiosqlite:///{default_db}"}
    env.pop("TEST_DATABASE_URL", None)
    proc = subprocess.run([sys.executable, "scripts/seed_demo_members.py", "--database-url", f"sqlite+aiosqlite:///{other_db}", "--count", "3", "--no-download"], capture_output=True, text=True, env=env, cwd=str(Path(__file__).parent))
    n_other = sqlite3.connect(other_db).execute("select count(*) from users").fetchone()[0] if other_db.exists() else -1
    default_has_users = default_db.exists() and "users" in {r[0] for r in sqlite3.connect(default_db).execute("select name from sqlite_master")}
    check("CLI: --database-url is honoured (rows land in the named database, none in the default one) and photos go to the demo directory under the configured upload dir",
          proc.returncode == 0 and n_other == 3 and not default_has_users and len(list((Path(TMP) / "cli_uploads" / "demo_photos").glob("demo-*.jpg"))) == 3 and not list((Path(TMP) / "cli_uploads" / "photos").glob("*.jpg")), (proc.stderr or proc.stdout)[-300:])

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
