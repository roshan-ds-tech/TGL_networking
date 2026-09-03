# TGL Season 1 — Backend & Admin Dashboard

FastAPI + SQLAlchemy (async) API that receives public registrations and powers a
password-protected admin dashboard for verifying payment screenshots.

## Layout

```
backend/
  app/
    main.py        FastAPI app, security headers, admin SPA hosting
    config.py      env-driven settings (refuses unsafe prod boot)
    database.py    async engine (SQLite WAL / Postgres)
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
| `PUBLIC_ORIGIN` | Public site origin, for CORS on the register endpoint |
| `SESSION_HOURS` | Admin session lifetime (default 12) |

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
| Stored XSS via upload | `nosniff` + `sandbox` CSP on proof responses |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Info leak on errors | Unhandled exceptions log server-side, return generic 500 |
