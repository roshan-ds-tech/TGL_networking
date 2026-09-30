# TGL P0 Implementation

## Architecture

P0 keeps the current React + Vite frontend and FastAPI + SQLAlchemy backend. The public marketing site remains available at `/`. Authenticated product routes are mounted inside the same Vite app under `/login`, `/signup`, `/verify-email`, `/onboarding/*`, and `/app/*`.

The backend preserves the legacy public `/api/registrations` payment-proof flow and adds a customer API under `/api/v1/*`. Customer identity is separate from admin identity.

## Auth And Onboarding

Customer sessions use HttpOnly cookies (`tgl_customer_session`) plus a readable CSRF cookie echoed through `X-CSRF-Token`. Passwords use Argon2id. Signup returns a development-only email verification token when not in production; production does not expose that token.

Onboarding order:

1. Create account.
2. Verify email (6-digit code, emailed via Resend).
3. Complete personal profile.
4. Complete business profile.
5. Register for Season 1 — via the public homepage form (see below), not an in-app step.

Account creation is deliberately decoupled from Season 1 registration: having
a TGL account does not mean you registered/paid for the event, and vice versa
(a walk-in registrant may never create an account at all). The admin
dashboard reflects this with two separate views — Accounts
(`GET /api/admin/customers`) and Registrations (`GET /api/admin/registrations`).

## Season 1 And Membership

Season 1 is represented in the `events` table with slug `season-1-2026` and `membership_duration_months = 3`.

Registration happens through the public, payment-proof form (`POST
/api/registrations` — the same form anonymous registrants use). If the
submitter is logged in (`get_optional_user` in `security.py`), the endpoint:

- derives full_name/business/category/etc. from the account's saved
  `PersonalProfile`/`Business` server-side — never from the submitted form
  fields, which the SPA only pre-fills for display
- links the legacy `registrations` row to the account (`user_id`, `business_id`)
- creates an `event_registrations` row with `PAYMENT_REVIEW`
- creates a `tgl_memberships` row with `PENDING`
- creates a notification for the registration submission

(see `link_registration_to_account` in `services.py`). An anonymous submitter
gets exactly the pre-P0 behavior: a legacy `registrations` row with no
account linkage.

Admin payment verification confirms the event registration and keeps membership `PENDING`. Payment confirmation never activates Networking.

Grand Finale completion is recorded through `POST /api/admin/events/season-1/complete`. It activates all eligible confirmed registrations idempotently:

- `starts_at = completed_at`
- `expires_at = starts_at + 3 calendar months`
- `status = ACTIVE`
- networking profile created if missing
- activation notification created

## Networking Authorization

Member-only APIs require server-side active Networking membership. Account existence, payment confirmation, business verification, and TGL Verified status do not grant access.

Active members can access:

- `/api/v1/networking/members`
- `/api/v1/networking/members/{member_id}`
- `/api/v1/referrals`

## Key Routes

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/verify-email`
- `GET /api/v1/status`
- `POST /api/v1/auth/resend-verification`
- `PUT /api/v1/profile/personal`
- `PUT /api/v1/business`
- `POST /api/registrations` — Season 1 registration/payment proof; optionally
  authenticated (see above), also used anonymously by the public form
- `GET /api/v1/networking/members`
- `GET /api/v1/networking/members/{member_id}`
- `GET/POST /api/v1/referrals`
- `PATCH /api/v1/referrals/{id}`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/read-all`
- `POST /api/admin/events/season-1/complete`
- `GET /api/admin/customers` — TGL accounts, separate from event registrations

## Local Development

Frontend:

```bash
npm run dev
```

Backend:

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

The frontend product app expects the API at `VITE_API_URL` (defaults to `http://localhost:8000`).

Admin dashboard remains the existing app in `admin-dashboard`.

## Checks

```bash
# Frontend (public marketing + product app)
npm run lint
npm run build

# Admin dashboard (builds into backend/static/admin)
cd admin-dashboard && npm run build

# Backend
cd backend
.venv/Scripts/python.exe -m compileall -q app
.venv/Scripts/python.exe test_security.py   # legacy public/admin surface (83 checks)
.venv/Scripts/python.exe test_p0.py         # P0 customer/membership rules (111 checks)
.venv/Scripts/python.exe test_wsgi_bridge.py
```

Verified on 2026-09-22: lint clean (pre-existing warnings only, 0 errors), both frontend
builds pass, `test_p0.py` 111/111, `test_security.py` 83/83, `test_wsgi_bridge.py`
18/18.

Since the initial 2026-09-21 verification, this pass: switched email
verification from a long token to a 6-digit OTP sent via Resend (see
`email_service.py`); removed the UTR/UPI field from registration entirely
(payment screenshot is sufficient); and removed the dedicated in-app "Season
1 Registration" step in favor of routing everyone — logged in or not —
through the one public payment-proof form, auto-linked to the account when
logged in. `test_p0.py`'s count reflects the removed endpoint's dedicated
checks (its behavior is now covered by the public-form tests).

## Known P1/P2 Follow-Ups

- Alembic migration workflow instead of the current additive `create_all` + schema sync.
- Razorpay automation and paid Networking renewals.
- Business/KYB verification workflow.
- TGL Verified workflow.
- Trust Score and Growth Points engines.
- Vertex AI/search, AI Business Match, chat, awards, and analytics.
