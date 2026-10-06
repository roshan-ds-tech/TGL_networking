# One image serves the whole product from one origin: the public site + member
# app (repo root), the admin dashboard, and the FastAPI API. Same origin is
# what keeps session cookies SameSite=Strict with no CORS in the way.
# Build context is the repo root.
#
#   docker build -t tgl .
#   docker run -p 8000:8000 --env-file backend/.env tgl

# ---- stage 1: public site + member app ----
FROM node:22-alpine AS site-build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY public ./public
COPY scripts ./scripts
COPY src ./src
# VITE_API_URL is deliberately unset: the built site calls the API on its own
# origin (src/lib/apiBase.js).
RUN npm run build

# ---- stage 2: admin SPA ----
FROM node:22-alpine AS admin-build
WORKDIR /src
COPY admin-dashboard/package.json admin-dashboard/package-lock.json* ./admin-dashboard/
RUN cd admin-dashboard && npm ci
COPY admin-dashboard ./admin-dashboard
# vite.config.js writes to ../backend/static/admin relative to admin-dashboard/,
# so an (empty) backend/ directory must exist alongside it in the build context.
RUN mkdir -p backend/static && cd admin-dashboard && npm run build

# ---- stage 3: python runtime ----
FROM python:3.12-slim
WORKDIR /app

# No compilers needed at runtime; argon2-cffi and asyncpg ship manylinux wheels.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini backend/create_admin.py ./
COPY --from=admin-build /src/backend/static ./static
COPY --from=site-build /src/dist ./static/site

# Production defaults; DATABASE_URL, SECRET_KEY etc. come from the platform.
# The SQLite/local-disk fallbacks only matter for a host with a mounted
# volume at /app/var (see docker-compose.yml) — Render uses Supabase instead.
ENV ADMIN_DIST_DIR=/app/static/admin \
    SITE_DIST_DIR=/app/static/site \
    UPLOAD_DIR=/app/var/uploads \
    DATABASE_URL=sqlite+aiosqlite:////app/var/tgl.db \
    ENVIRONMENT=production \
    PYTHONUNBUFFERED=1

# Run as an unprivileged user; it only needs to write to /app/var.
RUN useradd --system --uid 10001 --home /app tgl && mkdir -p /app/var && chown -R tgl /app/var
USER tgl

EXPOSE 8000
# $PORT is provided by most PaaS platforms (Render, Railway, ...); 8000 is the local fallback.
# Deploy order: migrate the database, then start serving. When the schema is
# already current (every restart / Render wake-up) the migrate step is one
# query. One worker on purpose: the rate limiter is in-process (ratelimit.py).
CMD ["sh", "-c", "python -m app.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
