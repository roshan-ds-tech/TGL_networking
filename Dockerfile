# Builds the admin dashboard, then packages it with the FastAPI backend into
# a single deployable image. Build context is the repo root (skykeen/).
#
#   docker build -t tgl-admin .
#   docker run -p 8000:8000 --env-file backend/.env -v tgl-data:/app/var tgl-admin

# ---- stage 1: build the admin SPA ----
FROM node:20-alpine AS admin-build
WORKDIR /src
COPY admin-dashboard/package.json admin-dashboard/package-lock.json* ./admin-dashboard/
RUN cd admin-dashboard && npm ci
COPY admin-dashboard ./admin-dashboard
# vite.config.js writes to ../backend/static/admin relative to admin-dashboard/,
# so an (empty) backend/ directory must exist alongside it in the build context.
RUN mkdir -p backend/static && cd admin-dashboard && npm run build

# ---- stage 2: python runtime ----
FROM python:3.12-slim
WORKDIR /app

# No compilers needed at runtime; argon2-cffi and asyncpg ship manylinux wheels.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/create_admin.py .
COPY --from=admin-build /src/backend/static ./static

ENV ADMIN_DIST_DIR=/app/static/admin \
    UPLOAD_DIR=/app/var/uploads \
    DATABASE_URL=sqlite+aiosqlite:////app/var/tgl.db \
    ENVIRONMENT=production

# /app/var must be a mounted volume in production so the database and payment
# screenshots survive redeploys.
RUN mkdir -p /app/var

EXPOSE 8000
# $PORT is provided by most PaaS platforms (Render, Railway, ...); 8000 is the local fallback.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
