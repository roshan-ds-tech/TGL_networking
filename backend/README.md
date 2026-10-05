# TGL Season 1 — Backend & Admin Dashboard

FastAPI + SQLAlchemy (async) API that receives public registrations and powers a
password-protected admin dashboard for verifying payment screenshots.

## Layout

```
backend/
  app/
    main.py        FastAPI app, security headers, admin SPA hosting
    config.py      env-driven settings (refuses unsafe prod boot)
    database.py    async engine (SQLite WAL / Postgres) + sync_schema()
    models.py      Admin, Registration
    schemas.py     request/response validation
    security.py    Argon2id, session JWT, CSRF, auth dependencies
    storage.py     magic-byte upload validation + safe file reads
    ratelimit.py   sliding-window limiter
    routers/       auth.py, public.py, admin.py
  create_admin.py  CLI to create / reset an admin
  test_security.py 38-check security + behaviour suite
admin-dashboard/   React SPA, builds into backend/static/admin
```

## First-time setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
```

Build the dashboard (outputs into `backend/static/admin`):

```bash
cd ../admin-dashboard && npm install && npm run build
```

Create the client's login:

```bash
cd ../backend
.venv/Scripts/python.exe create_admin.py
```

Run:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dashboard: `http://localhost:8000/admin`

## Tests

```bash
.venv/Scripts/python.exe test_security.py
```

Covers auth, CSRF, SQL injection, path traversal, upload spoofing, user
enumeration, session invalidation and rate limiting. Uses a throwaway DB.

```bash
.venv/bin/python test_p0.py          # accounts, onboarding, networking, finale, notifications
(cd .. && npm run build) && .venv/bin/python test_production.py
                                     # production shape: same-origin site serving, 404s,
                                     # headers, XFF spoofing, Supabase Storage (local fake),
                                     # duplicate/concurrent submissions, 130-request load run
```

Every suite also runs against Postgres — the engine production (Supabase)
uses, and the one that exposes concurrency bugs SQLite hides. Point
`TEST_DATABASE_URL` at a **throwaway** database (its tables are dropped):

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/tgl_test .venv/bin/python test_production.py
```

Deployment: see `../DEPLOY_RENDER.md` (Render + Supabase).

```bash
.venv/Scripts/python.exe -m pip install werkzeug
.venv/Scripts/python.exe test_wsgi_bridge.py
```

Only needed if you're deploying to a WSGI-only host (see
`DEPLOY_PYTHONANYWHERE.md`) — proves the app works correctly when driven
through the `a2wsgi` adapter instead of served natively as ASGI.

## Environment variables

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `production` enables HSTS, secure cookies, disables `/docs` |
| `SECRET_KEY` | **Required in production**, ≥32 chars. Rotating it logs everyone out |
| `DATABASE_URL` | `sqlite+aiosqlite:///./var/tgl.db` or `postgresql+asyncpg://…` |
| `UPLOAD_DIR` | Screenshot storage. Keep outside any static/web root |
| `PUBLIC_ORIGIN` | Public site origin(s), for CORS on the register + availability endpoints. Comma-separate to allow more than one, e.g. `https://tgl.skykeen.in,https://tglwebsite.vercel.app`. Explicit allowlist only — `*` is ignored. **Every domain the site is served from must be listed** (see below) |

### Adding a domain to the site

`PUBLIC_ORIGIN` is an exact-match allowlist, so pointing a new domain at the
frontend is only half the job — it has to be added here as well.

The failure is easy to misread: the API still answers `200`, but without an
`Access-Control-Allow-Origin` header the browser refuses to let the page read
the response. The site looks completely normal and just shows the static
"40 slots" fallback instead of live counts, with a CORS error in the console.

To check a domain quickly:

```bash
curl -sD - -o /dev/null -H "Origin: https://your-domain" \
  https://roshands.pythonanywhere.com/api/categories/availability | grep -i access-control
```

No `access-control-allow-origin` line back means that origin is not allowlisted.
Add it to `PUBLIC_ORIGIN` in the WSGI file and hit **Reload**.
| `SESSION_HOURS` | Admin session lifetime (default 12) |
| `SLOTS_PER_CATEGORY` | Capacity per category shown by the public slot counters (default 40) |

## Public endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/registrations` | Registration intake (multipart, includes payment proof) |
| `GET /api/categories/availability` | Aggregate "x of 40 filled" counters for the marketing site |

`GET /api/categories/availability` is unauthenticated on purpose — the public
site renders a live slot counter per category. It returns **counts only**, never
registrant data, and is cached in-process for 30s so page traffic does not turn
into database load. The count is *all* registrations, matching the admin
dashboard's slot-fill logic (a submitted registration holds the slot while its
payment is being verified).

## Adding a column (there is no Alembic here)

`Base.metadata.create_all` only creates missing **tables** — it will never
alter one that already exists. Adding a field to a model is therefore not
enough: against a database that already holds rows, every query would start
failing with "no such column".

`database.sync_schema()` covers that gap. It runs on every boot (both the ASGI
lifespan and the WSGI `init_db_sync` path), inspects what the database actually
has, and issues `ALTER TABLE ... ADD COLUMN` for anything listed in
`_ADDED_COLUMNS` that is missing. It is idempotent, so repeated reloads are a
no-op.

To add a column: add it to the model, then add an entry to `_ADDED_COLUMNS`.
The column **must be nullable** — rows written before it existed cannot have a
value. Make it required for new submissions in the Pydantic schema instead,
which is how `utr` works.

## Production notes

1. **Terminate TLS in front of the app.** Session cookies are `Secure` when
   `ENVIRONMENT=production`, so plain HTTP will not authenticate.
2. **Set `SECRET_KEY`.** The app refuses to start in production without one.
3. **Back up two things:** the database *and* `UPLOAD_DIR`. Screenshots are the
   payment evidence and are not stored in the DB.
4. **Postgres for multi-instance.** The rate limiter is in-process, so with more
   than one worker the login limit applies per worker. Either run a single
   worker (plenty for this workload) or move the limiter to Redis.
5. `/docs` and `/openapi.json` are disabled in production.

## Security summary

| Concern | Mitigation |
|---|---|
| Password storage | Argon2id (memory-hard), never logged or returned |
| Session theft via XSS | `HttpOnly` cookie — unreadable from JS |
| CSRF | `SameSite=Strict` + double-submit token header on every mutation |
| Brute force | Per-IP rate limit + per-account lockout after 5 failures |
| User enumeration | One generic 401; unknown users still pay hash-verify cost |
| SQL injection | SQLAlchemy bound parameters throughout, no string SQL |
| Malicious uploads | Magic-byte sniffing (declared type ignored), 8 MB cap, UUID names |
| Path traversal | Server-generated filenames; reads re-checked inside upload root |
| IDOR on screenshots | UUID ids + auth required on the proof endpoint |
| Reused payment evidence | UTR normalised (case/separators) and rejected if already on another registration |
| Stored XSS via upload | `nosniff` + `sandbox` CSP on proof responses |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Info leak on errors | Unhandled exceptions log server-side, return generic 500 |
