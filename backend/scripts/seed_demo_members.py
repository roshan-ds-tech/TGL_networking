"""Seed ~30 SYNTHETIC TGL members (and 6 clearly-marked Growth Points test scenarios) into a DEVELOPMENT or TEST database, for interface testing.

    python scripts/seed_demo_members.py --database-url sqlite+aiosqlite:///./var/tgl_demo.db      # create / refresh (idempotent)
    python scripts/seed_demo_members.py --database-url ... --cleanup                                # deactivate them and remove THEIR photos (demo directory only)
    python scripts/seed_demo_members.py --database-url ... --migrate-photos [--dry-run]            # move older demo photos out of the shared photos directory

SAFETY (enforced in code, tested):
  * Refuses to write unless the target is a local SQLite file or a localhost PostgreSQL, ENVIRONMENT is not production, and photos would go to
    LOCAL storage (never Supabase). A staging seed needs a deliberate, separate decision; it is not enabled here.
  * Demo members are recognised by the reserved `demo.example.com` email domain (app/demo.py). Gate A, the objective gates and the review count
    GENUINE members only, so none of this can ever count as real observation.
  * No payments, no invoice discounts, no redemptions, no approvals, no gates are created or changed. The six scenario members have an
    active subscription and an invoice at full price numbered DEMO-xxxx, and a few shadow ledger rows made by the normal reward engine.
  * Idempotent: rerunning creates no duplicates (members are keyed by email, ledger rows by their idempotency key).
  * Demo photos are stored in their OWN directory (<UPLOAD_DIR>/demo_photos) under `demo-<hex>.jpg` names (app/storage.py). They can not collide
    with, overwrite or be deleted through the genuine photo path, and cleanup removes only a `demo-` file that a synthetic member of the target
    database references (and whose recorded checksum still matches the manifest).
  * Profile pictures: DiceBear "lorelei" illustrated avatars by Lisa Wischofsky, CC0 1.0 (public domain: no attribution required), downloaded once
    and stored locally through the app's own photo pipeline. They are illustrations, not people: they do not depict real individuals. If the
    download fails, a generated initials avatar is used instead, and the app's own fallback handles a missing image.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# NOTE: nothing from `app` may be imported at module level: --database-url must be applied to the environment BEFORE app.config is first loaded.
COUNT = 30
AVATAR_URL = "https://api.dicebear.com/9.x/lorelei/png?seed={seed}&size=256&backgroundColor=e8dff5,f6eedf,dfeaf5"
AVATAR_SOURCE = "DiceBear 'lorelei' by Lisa Wischofsky, CC0 1.0 (https://www.dicebear.com/styles/lorelei/)"

# (name, city, role, business, category, description, tags, interests, stage)
PEOPLE = [
    ("Aarav Mehta", "Bengaluru", "Founder", "ThreadLoom Apparel", "01", "Small-batch organic cotton menswear sold to boutiques and direct.", "apparel,sustainable,d2c", "wholesale partners, packaging, export", "Growing"),
    ("Diya Raman", "Chennai", "Co-founder", "Kanchi Weave Studio", "01", "Contemporary sarees and stoles woven with master artisans in Tamil Nadu.", "textiles,handloom,fashion", "retail partnerships, photography", "Early"),
    ("Kabir Sheikh", "Mumbai", "Founder", "UrbanHem Tailors", "01", "Made-to-measure workwear for startups and corporate teams.", "tailoring,uniforms,b2b", "corporate gifting, bulk orders", "Growing"),
    ("Meera Nair", "Kochi", "Founder", "Malabar Morning Bakes", "02", "Millet-based breads and cookies delivered across Kochi.", "bakery,millets,food", "cafes, subscriptions, packaging", "Growing"),
    ("Rohan Kulkarni", "Pune", "Founder", "Sip & Steep Co.", "02", "Single-estate teas and cold-brew concentrates for offices and cafes.", "beverage,tea,coffee", "horeca, gifting, events", "Early"),
    ("Anika Bose", "Kolkata", "Owner", "Bengal Larder", "02", "Regional pickles, sauces and sweets shipped nationwide.", "gourmet,condiments,regional", "marketplaces, export, labelling", "Scaling"),
    ("Ishaan Patel", "Ahmedabad", "Founder", "Rann Craft Collective", "03", "Block-printed home textiles made with Kutch artisan groups.", "craft,block print,artisan", "design collaborations, trade fairs", "Growing"),
    ("Tanvi Joshi", "Jaipur", "Founder", "Pichwai Pottery", "03", "Hand-painted blue pottery and tableware for homes and hotels.", "pottery,ceramics,handmade", "hospitality buyers, photography", "Early"),
    ("Vikram Iyer", "Bengaluru", "Founder", "Bamboo Bay Living", "03", "Furniture and baskets crafted from certified bamboo.", "bamboo,furniture,eco", "architects, retail, logistics", "Growing"),
    ("Neha Kapoor", "Delhi", "Founder", "Silver Thread Jewels", "04", "Oxidised silver jewellery designed for everyday wear.", "jewellery,silver,fashion", "influencer marketing, trade shows", "Growing"),
    ("Arjun Reddy", "Hyderabad", "Co-founder", "Nizam Pearl House", "04", "Heritage pearl jewellery with certified sourcing.", "pearls,luxury,gifting", "wedding planners, export", "Scaling"),
    ("Sana Qureshi", "Mumbai", "Founder", "Bagheera Leatherworks", "04", "Vegetable-tanned leather bags, belts and accessories.", "leather,accessories,craft", "b2b orders, d2c, packaging", "Early"),
    ("Rahul Menon", "Kochi", "Founder", "Casa Verde Interiors", "05", "Interior styling and modular furniture for small apartments.", "interiors,furniture,design", "builders, home stagers, vendors", "Growing"),
    ("Priya Desai", "Pune", "Founder", "Lumen & Lime", "05", "Handcrafted candles, diffusers and home fragrance.", "decor,candles,lifestyle", "gifting, marketplaces, wholesale", "Early"),
    ("Karthik Subramanian", "Chennai", "Founder", "Kolam Living", "05", "Smart-lighting and decor kits for rental homes.", "decor,smart home,rental", "proptech partners, retail", "Growing"),
    ("Aditi Sharma", "Delhi", "Founder", "Tiny Sprouts Toys", "06", "Wooden Montessori toys and learning kits for ages 1 to 6.", "toys,kids,education", "schools, parenting communities", "Growing"),
    ("Yash Agarwal", "Jaipur", "Founder", "Kidoodle Books", "06", "Illustrated regional-language storybooks and activity packs.", "books,children,publishing", "libraries, schools, distributors", "Early"),
    ("Pooja Hegde", "Bengaluru", "Co-founder", "Little Nest Baby Care", "06", "Organic baby apparel and skincare bundles for new parents.", "baby care,organic,d2c", "hospitals, parenting creators", "Scaling"),
    ("Nikhil Bhatt", "Ahmedabad", "Founder", "Ayu Botanica", "07", "Ayurvedic skincare and haircare made in small batches.", "wellness,skincare,ayurveda", "pharmacies, dermatologists", "Growing"),
    ("Zoya Khan", "Mumbai", "Founder", "Glow Ritual Salon Labs", "07", "Salon-grade treatments and a training academy for stylists.", "beauty,salon,training", "franchise partners, product distributors", "Scaling"),
    ("Siddharth Rao", "Hyderabad", "Founder", "PureRoots Wellness", "07", "Herbal supplements and wellness coaching programmes.", "wellness,supplements,coaching", "clinics, corporate wellness", "Early"),
    ("Ritika Singh", "Delhi", "Founder", "Stride Strong Fitness", "08", "Boutique strength studio with online coaching for founders.", "fitness,coaching,studio", "corporate memberships, nutrition partners", "Growing"),
    ("Aman Verma", "Pune", "Founder", "TrailBlaze Outdoors", "08", "Weekend treks, cycling tours and sports gear rentals.", "sports,outdoors,travel", "gear suppliers, college clubs", "Early"),
    ("Lakshmi Pillai", "Kochi", "Founder", "Flow State Yoga", "08", "Yoga teacher trainings and corporate wellness retreats.", "yoga,wellness,retreats", "resorts, HR teams", "Growing"),
    ("Manish Gupta", "Mumbai", "Founder", "LedgerLight Advisory", "09", "Bookkeeping and GST compliance for early-stage startups.", "accounting,gst,compliance", "founders, incubators, banks", "Growing"),
    ("Shreya Banerjee", "Kolkata", "Founder", "BrandBloom Studio", "09", "Brand identity and websites for first-generation entrepreneurs.", "branding,design,web", "small businesses, print vendors", "Early"),
    ("Devansh Malhotra", "Bengaluru", "Founder", "Pipeline Pilot", "09", "Outsourced sales development for B2B service companies.", "sales,b2b,outsourcing", "agencies, SaaS founders", "Scaling"),
    ("Isha Chaudhary", "Hyderabad", "Founder", "AgriLoop Labs", "10", "Soil-sensor kits and advice for small organic farms.", "agritech,iot,sustainability", "farmer groups, grants, pilots", "Early"),
    ("Pranav Naidu", "Chennai", "Founder", "SolarSathi", "10", "Rooftop solar installs and financing for small shops.", "solar,energy,climate", "banks, MSME clusters", "Growing"),
    ("Mira Fernandes", "Pune", "Founder", "ReWear Circular", "10", "A resale and repair marketplace for premium clothing.", "circular,resale,marketplace", "brands, logistics, creators", "Early"),
]
# the six Growth Points test scenarios, attached to the first six members
SCENARIOS = {1: "NO_POINTS", 2: "ELIGIBLE_POST_CUTOFF", 3: "SHADOW_PERIOD_ONLY", 4: "EXPIRED", 5: "DISPUTE_REVERSED", 6: "CAP_HIT"}
SCENARIO_PLAN = {1: "connect", 2: "growth", 3: "connect", 4: "growth", 5: "elite", 6: "growth"}


class UnsafeTarget(RuntimeError):
    pass


def assert_safe(database_url: str, environment: str, uses_supabase: bool) -> None:
    """Refuse anything that could be a shared or production system. Pure function: tested directly."""
    url = database_url.lower()
    if environment.strip().lower() == "production":
        raise UnsafeTarget("ENVIRONMENT is production: demo data is never written to production.")
    if uses_supabase:
        raise UnsafeTarget("Photos would go to Supabase storage. The demo seed writes to LOCAL storage only; seeding a staging project needs a separate, explicit decision.")
    if url.startswith("sqlite"):
        return
    if url.startswith(("postgresql", "postgres")) and any(h in url for h in ("@localhost", "@127.0.0.1", "@[::1]")):
        return
    raise UnsafeTarget("The target database is not a local SQLite file or a localhost PostgreSQL: refusing to write demo data.")


def _avatar_bytes(seed: str, name: str, assets: Path, fetch: bool) -> tuple[bytes, str]:
    """Return (png bytes, source). Cached on disk; falls back to a generated initials avatar if the download fails or is disabled."""
    cache = assets / f"{seed}.png"
    if cache.is_file():
        return cache.read_bytes(), AVATAR_SOURCE if not cache.name.endswith(".initials.png") else "generated initials avatar"
    if fetch:
        try:
            import urllib.request
            req = urllib.request.Request(AVATAR_URL.format(seed=seed), headers={"User-Agent": "tgl-demo-seed/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:        # noqa: S310 - fixed https URL
                data = resp.read()
            if data[:8] == bytes.fromhex("89504e470d0a1a0a") and 1_000 < len(data) < 400_000:
                assets.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
                return data, AVATAR_SOURCE
        except Exception:                                               # noqa: BLE001 - any failure means "use the generated fallback"
            pass
    from PIL import Image, ImageDraw
    initials = "".join(p[0] for p in name.split()[:2]).upper()
    img = Image.new("RGB", (256, 256), (107, 62, 150))
    ImageDraw.Draw(img).text((100, 110), initials, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), "generated initials avatar (download unavailable)"


async def seed(session_factory, *, count: int = COUNT, assets_dir: Path | None = None, fetch_images: bool = True, now=None, demo_cutoff=None, manifest_path: Path | None = None) -> dict:
    """Create or refresh the synthetic members. Idempotent. Returns a summary."""
    from starlette.datastructures import UploadFile
    from sqlalchemy import select

    from app.models import Business, Invoice, PersonalProfile, Plan, Subscription, User, utcnow
    from app.rewards import engine as reng, firewall, rules
    from app.rewards.engine import AwardRequest
    from app.security import hash_password
    from app.services import ensure_networking_profile
    from app.storage import demo_photo_root, is_demo_photo, save_profile_photo
    from app.subscriptions import build_purchase
    from app import demo

    now = now or utcnow()
    if demo_cutoff is None and manifest_path and manifest_path.is_file():      # a rerun keeps the cutoff the scenarios were built around
        from datetime import datetime
        demo_cutoff = datetime.fromisoformat(json.loads(manifest_path.read_text())["demo_cutoff"])
    demo_cutoff = demo_cutoff or (now - timedelta(days=60))
    assets_dir = assets_dir or (ROOT / "var" / "demo_assets" / "avatars")
    created, existing, photos, sources = 0, 0, 0, set()
    manifest: list[dict] = []
    people = PEOPLE[:count]
    from app.demo import DEMO_PASSWORD           # development / test only; the seed refuses production, so this can never exist there
    pw = hash_password(DEMO_PASSWORD)
    from app.subscriptions import ensure_default_plans
    async with session_factory() as db:
        await ensure_default_plans(db)
        await db.commit()
        plans = {p.code: p for p in (await db.execute(select(Plan))).scalars().all()}
        for i, (name, city, role, biz, cat, desc, tags, interests, stage) in enumerate(people, start=1):
            email = f"demo-{i:02d}@{demo.SYNTHETIC_DOMAIN}"
            user = await db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, password_hash=pw, full_name=name, phone=f"90000{i:05d}", is_active=True, email_verified_at=now)
                db.add(user)
                await db.flush()
                created += 1
            else:
                existing += 1
            if await db.get(PersonalProfile, user.id) is None:
                db.add(PersonalProfile(user_id=user.id, full_name=name, phone=user.phone, city=city, role=role, short_bio=f"{role} of {biz}. {desc}", completed_at=now))
            business = await db.scalar(select(Business).where(Business.user_id == user.id).limit(1))
            if business is None:
                business = Business(user_id=user.id, business_name=biz, category=cat, description=desc, city=city, employee_band=("1-3", "4-6", "7-10")[i % 3], business_age=("lt6", "6-12", "1-3y", "3y+")[i % 4],
                                    website=f"https://demo-{i:02d}.{demo.SYNTHETIC_DOMAIN}", founder_story=f"{name} started {biz} to serve a gap {city} businesses kept running into. (Synthetic demo profile.)", business_stage=stage)
                db.add(business)
                await db.flush()
            profile = await ensure_networking_profile(db, user.id)
            if profile is not None and not profile.industry_tags.startswith(tags.split(",")[0]):
                profile.industry_tags, profile.interests = tags, interests
                profile.headline = f"{role} · {biz}"
                profile.open_to_mentoring = i % 3 == 0
            if not user.is_active:                                  # a refresh after --cleanup brings the synthetic member back
                user.is_active = True
            if user.photo_key and is_demo_photo(user.photo_key) and not (demo_photo_root() / user.photo_key).is_file():
                user.photo_key = None                               # the demo file was removed: store it again
            if not user.photo_key:
                data, source = _avatar_bytes(f"demo-{i:02d}", name, assets_dir, fetch_images)
                user.photo_key = await save_profile_photo(UploadFile(file=io.BytesIO(data), filename=f"demo-{i:02d}.png"), demo=True)
                photos += 1
                sources.add(source)
            scenario = SCENARIOS.get(i)
            has_term = await db.scalar(select(Subscription.id).where(Subscription.user_id == user.id).limit(1))
            if not has_term:
                # every demo member has an active subscription (so the member interface treats them as members) with an invoice at FULL PRICE numbered
                # DEMO-xxxx and NO payment row: nothing here is a payment. Scenario members' terms end in 10 days (inside the renewal window).
                code = SCENARIO_PLAN.get(i) or ("connect", "growth", "elite")[i % 3]
                months = {"connect": 3, "growth": 6, "elite": 12}[code]
                ends = now + (timedelta(days=10) if scenario else timedelta(days=60 + 7 * (i % 8)))
                starts = ends - timedelta(days=round(months * 30.4375))
                sub, inv, _pay = build_purchase(user.id, plans[code])
                sub.status, sub.starts_at, sub.expires_at, sub.activated_at = "ACTIVE", starts, ends, starts
                db.add(sub)
                await db.flush()
                inv.subscription_id, inv.number, inv.status, inv.amount_paid_minor, inv.paid_at = sub.id, f"DEMO-{i:04d}", "PAID", inv.amount_due_minor, starts
                db.add(inv)
            entry = {"email": email, "user_id": user.id, "scenario": scenario, "synthetic": True}
            if user.photo_key and is_demo_photo(user.photo_key) and (demo_photo_root() / user.photo_key).is_file():
                entry["photo"] = user.photo_key
                entry["photo_sha256"] = hashlib.sha256((demo_photo_root() / user.photo_key).read_bytes()).hexdigest()
            manifest.append(entry)
        await db.commit()

        # --- Growth Points test scenarios, through the normal reward engine (shadow rows, append-only, idempotent keys)
        scenario_rows = {}
        for i, scenario in SCENARIOS.items():
            if i > count:
                continue
            user = await db.scalar(select(User).where(User.email == f"demo-{i:02d}@{demo.SYNTHETIC_DOMAIN}"))
            sub = await db.scalar(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at).limit(1))
            if sub is None:
                continue
            starts = rules.aware(sub.starts_at)

            async def award(kind, ref, pts, lvl, at, rtype, role):
                with firewall.guard():
                    return await reng.award(db, AwardRequest(member_id=user.id, event_type=kind, reference_type=rtype, reference_id=f"demo-sc{i}-{ref}", requested=pts, level=lvl, event_at=at, role=role))
            if scenario == "ELIGIBLE_POST_CUTOFF":
                for k, (kind, pts, lvl, rt) in enumerate([("BUSINESS_CLOSED", 1500, 4, "deal_closure"), ("MEETING_COMPLETED", 450, 3, "referral"), ("PROFILE_COMPLETED", 450, 3, "member")]):
                    await award(kind, k, pts, lvl, demo_cutoff + timedelta(days=5 + k, hours=1), rt, "referrer" if rt == "deal_closure" else "member")
            elif scenario == "SHADOW_PERIOD_ONLY":
                for k, (kind, pts, lvl, rt) in enumerate([("BUSINESS_CLOSED", 1500, 4, "deal_closure"), ("MEETING_COMPLETED", 450, 3, "referral"), ("PROFILE_COMPLETED", 450, 3, "member")]):
                    await award(kind, k, pts, lvl, demo_cutoff - timedelta(days=12 + k, hours=1), rt, "referrer" if rt == "deal_closure" else "member")
            elif scenario == "EXPIRED":
                old_start = starts - timedelta(days=330)
                old_sub = await db.scalar(select(Subscription).where(Subscription.user_id == user.id, Subscription.id != sub.id).limit(1))
                if old_sub is None:
                    old_sub = Subscription(user_id=user.id, plan_id=sub.plan_id, status="EXPIRED", starts_at=old_start, expires_at=old_start + timedelta(days=183), activated_at=old_start)
                    db.add(old_sub)
                    await db.flush()
                    oinv = Invoice(number="DEMO-0004-OLD", subscription_id=old_sub.id, user_id=user.id, plan_id=sub.plan_id, currency="INR", plan_name=plans["growth"].name, period_months=6,
                                   list_price_minor=plans["growth"].price_minor, amount_before_discount_minor=plans["growth"].price_minor, discount_minor=0, amount_due_minor=plans["growth"].price_minor,
                                   amount_paid_minor=plans["growth"].price_minor, status="PAID", issued_at=old_start, paid_at=old_start)
                    db.add(oinv)
                    await db.flush()
                await award("BUSINESS_CLOSED", 0, 1500, 4, old_start + timedelta(days=20), "deal_closure", "referrer")
                await award("MEETING_COMPLETED", 1, 450, 3, old_start + timedelta(days=30), "referral", "member")
            elif scenario == "DISPUTE_REVERSED":
                res = await award("BUSINESS_CLOSED", 0, 1500, 4, demo_cutoff + timedelta(days=8), "deal_closure", "referrer")
                lots = [l for l in await __import__("app.rewards.ledger", fromlist=["x"]).lots(db, member_id=user.id) if l.row.reference_id == f"demo-sc{i}-0" and l.remaining > 0]
                for lot in lots:
                    with firewall.guard():
                        await reng.adjust(db, lot, "REVERSAL", "Synthetic scenario: the deal was disputed and reversed", "demo-seed")
            elif scenario == "CAP_HIT":
                for k, (kind, pts, lvl, rt, off) in enumerate([("BUSINESS_CLOSED", 1800, 4, "deal_closure", 6), ("MEETING_COMPLETED", 750, 3, "referral", 7), ("PROFILE_COMPLETED", 450, 3, "member", 8),
                                                               ("BUSINESS_CLOSED", 1800, 4, "deal_closure", 45), ("MEETING_COMPLETED", 750, 3, "referral", 46), ("PROFILE_COMPLETED", 450, 3, "member", 47)]):
                    await award(kind, k, pts, lvl, demo_cutoff + timedelta(days=off, hours=1), rt, "referrer" if rt == "deal_closure" else "member")
            scenario_rows[scenario] = user.email
        await db.commit()
    result = {"members_total": len(people), "created_now": created, "already_existed": existing, "photos_stored_now": photos, "image_sources": sorted(sources), "scenarios": scenario_rows,
              "demo_cutoff": demo_cutoff.isoformat(), "login_password_dev_only": DEMO_PASSWORD}
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({"synthetic": True, "domain": demo.SYNTHETIC_DOMAIN, "image_source": AVATAR_SOURCE, "demo_cutoff": demo_cutoff.isoformat(), "members": manifest}, indent=2))
    return result


def manifest_path_for(database_url: str) -> Path:
    """One manifest per database: the user ids and photo files it lists belong to THAT database only."""
    from sqlalchemy.engine import make_url
    url = make_url(database_url)
    stem = Path(url.database).stem if url.get_backend_name() == "sqlite" and url.database else (url.database or "db")
    return Path(os.environ.get("TGL_DEMO_MANIFEST_DIR") or ROOT / "var") / f"demo_seed_manifest.{stem}.json"


async def cleanup(session_factory, manifest_path: Path | None = None) -> dict:
    """Deactivate every synthetic member and remove THEIR demo photos. Subscription, invoice and ledger rows are append-only / RESTRICT by design and
    stay (they are excluded from every real-member calculation); to wipe a development database completely, delete the file.

    A photo is removed only when ALL of these hold: the member is synthetic (reserved email domain), the stored name is in the demo namespace
    (`demo-<hex>.jpg`, which only the demo directory can serve or delete), and, if the manifest recorded a checksum for it, the file still matches.
    A synthetic member whose photo is an older plain name in the shared photos directory is NOT touched: run --migrate-photos first."""
    from sqlalchemy import select

    from app import demo
    from app.models import User
    from app.storage import delete_profile_photo, demo_photo_root, is_demo_photo
    recorded = {}
    if manifest_path and manifest_path.is_file():
        recorded = {m["user_id"]: m for m in json.loads(manifest_path.read_text()).get("members", [])}
    removed, skipped = 0, []
    async with session_factory() as db:
        users = (await db.execute(select(User).where(demo.synthetic_clause()))).scalars().all()
        for u in users:
            key = u.photo_key
            if key:
                if not is_demo_photo(key):
                    skipped.append({"email": u.email, "reason": "photo is in the shared photos directory: run --migrate-photos first"})
                else:
                    f = demo_photo_root() / key
                    want = (recorded.get(u.id) or {}).get("photo_sha256")
                    if f.is_file() and want and hashlib.sha256(f.read_bytes()).hexdigest() != want:
                        skipped.append({"email": u.email, "reason": "file changed since it was seeded (checksum differs): left in place"})
                    else:
                        removed += 1 if await delete_profile_photo(key) else 0
                        u.photo_key = None
            u.is_active = False
        await db.commit()
    return {"deactivated": len(users), "demo_photos_removed": removed, "photos_left_in_place": skipped}


def _local_sqlite_files() -> list[Path]:
    return sorted((ROOT / "var").glob("*.db"))


def _referenced_by_genuine_users(key: str, dbs: list[Path]) -> list[str]:
    """Databases (local SQLite files) where a NON-synthetic user stores this photo name."""
    import sqlite3
    hits = []
    for db in dbs:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            n = con.execute("select count(*) from users where photo_key = ? and email not like ?", (key, f"%@{__import__('app.demo', fromlist=['x']).SYNTHETIC_DOMAIN}")).fetchone()[0]
        except sqlite3.DatabaseError:
            n = 0
        finally:
            con.close()
        if n:
            hits.append(db.name)
    return hits


def _referenced_anywhere(key: str, dbs: list[Path]) -> bool:
    import sqlite3
    for db in dbs:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            if con.execute("select count(*) from users where photo_key = ?", (key,)).fetchone()[0]:
                return True
        except sqlite3.DatabaseError:
            pass
        finally:
            con.close()
    return False


async def migrate_legacy_photos(session_factory, *, dry_run: bool = False, reference_dbs: list[Path] | None = None) -> dict:
    """Move synthetic members' OLD photos (plain names in the shared photos directory) into the demo directory.

    Ownership is proven before anything is moved: the member is synthetic, and the same file name is not stored by any genuine user in ANY local
    database. The file is copied, verified byte for byte, the member row is repointed, and only then is the old file removed, and only if no row in
    any local database still references it. Files nobody references are never touched."""
    from sqlalchemy import func, select

    from app import demo
    from app.models import User
    from app.storage import _PHOTO_NAME_RE, DEMO_PHOTO_PREFIX, demo_photo_root, photo_root
    dbs = reference_dbs if reference_dbs is not None else _local_sqlite_files()
    moved, plan, refused = 0, [], []
    async with session_factory() as db:
        for u in (await db.execute(select(User).where(demo.synthetic_clause()))).scalars().all():
            key = u.photo_key
            if not key or key.startswith(DEMO_PHOTO_PREFIX):
                continue
            src = photo_root() / key
            owners = _referenced_by_genuine_users(key, dbs)
            if await db.scalar(select(func.count(User.id)).where(User.photo_key == key, ~demo.synthetic_clause())):      # the target database itself (also covers PostgreSQL)
                owners = [*owners, "the target database"]
            if not _PHOTO_NAME_RE.fullmatch(key) or not src.is_file() or owners:
                refused.append({"email": u.email, "key": key, "reason": f"used by a genuine user in {owners}" if owners else "file missing or not a stored photo name"})
                continue
            new = f"{DEMO_PHOTO_PREFIX}{key}"
            plan.append({"email": u.email, "from": f"photos/{key}", "to": f"demo_photos/{new}"})
            if dry_run:
                continue
            data = src.read_bytes()
            dst = demo_photo_root() / new
            if not dst.exists():
                dst.write_bytes(data)
            if dst.read_bytes() != data:
                refused.append({"email": u.email, "key": key, "reason": "copy did not verify: left untouched"})
                continue
            u.photo_key = new
            await db.commit()
            moved += 1
            # remove the old file only when nothing in any local database still points at it (the repointed row was committed above)
            if not _referenced_anywhere(key, dbs) and not await db.scalar(select(func.count(User.id)).where(User.photo_key == key)):
                src.unlink(missing_ok=True)
    return {"dry_run": dry_run, "moved": moved, "planned": plan if dry_run else len(plan), "refused": refused}


async def main_async(args) -> int:
    os.environ.setdefault("ENVIRONMENT", "development")
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    from app.config import settings
    from app import storage
    assert_safe(os.environ.get("DATABASE_URL") or settings.database_url, settings.environment, storage._use_supabase())
    import app.models  # noqa: F401  (registers every table on Base.metadata)
    from app.database import Base, SessionLocal, engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)               # a fresh local demo database; existing tables are left untouched
    manifest = manifest_path_for(os.environ.get("DATABASE_URL") or settings.database_url)
    if args.migrate_photos:
        print(json.dumps(await migrate_legacy_photos(SessionLocal, dry_run=args.dry_run), indent=2))
    elif args.cleanup:
        print(json.dumps(await cleanup(SessionLocal, manifest), indent=2))
    else:
        print(json.dumps(await seed(SessionLocal, count=args.count, fetch_images=not args.no_download, manifest_path=manifest), indent=2, default=str))
    await engine.dispose()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--database-url", help="a LOCAL sqlite file or localhost postgres (default: the app's DATABASE_URL)")
    ap.add_argument("--count", type=int, default=COUNT)
    ap.add_argument("--cleanup", action="store_true")
    ap.add_argument("--migrate-photos", action="store_true", help="move older demo photos out of the shared photos directory (ownership verified first)")
    ap.add_argument("--dry-run", action="store_true", help="with --migrate-photos: show what would move, change nothing")
    ap.add_argument("--no-download", action="store_true", help="use generated initials avatars instead of downloading")
    try:
        sys.exit(asyncio.run(main_async(ap.parse_args())))
    except UnsafeTarget as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(2)
