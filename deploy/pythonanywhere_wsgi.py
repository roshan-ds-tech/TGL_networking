"""Content to paste into PythonAnywhere's auto-generated WSGI file
(Web tab -> Code section -> WSGI configuration file link).

PythonAnywhere's free tier only serves WSGI apps, not ASGI, so this wraps the
FastAPI (ASGI) app with a2wsgi's adapter. Verified locally against the exact
same app (cookies, CSRF, file upload, binary file download, cold start on an
empty database) in backend/test_wsgi_bridge.py — 13/13 checks pass through
this bridge.

EDIT THE TWO PLACEHOLDERS BELOW (search for CHANGE-ME) before saving.
"""
import os
import sys

# ---- 1. Make the app importable ----
# CHANGE-ME: replace 'yourusername' with your actual PythonAnywhere username.
PROJECT_DIR = "/home/yourusername/TGL/backend"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ---- 2. Configuration ----
# Must be set BEFORE `from app.main import app` below — app/config.py reads
# these at import time. Do not commit real values here; this file lives
# outside git (it's pasted directly into PythonAnywhere's dashboard).
os.environ["ENVIRONMENT"] = "production"
# CHANGE-ME: generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
# Deliberately short (fails the >=32-char production check) so that if you
# forget to replace it, the app refuses to boot instead of silently running
# with a key that's published in this repo.
os.environ["SECRET_KEY"] = "CHANGE-ME"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{PROJECT_DIR}/var/tgl.db"
# PythonAnywhere's free-tier home directory is network-mounted (NFS); SQLite's
# WAL mode needs shared-memory locking that NFS doesn't support reliably, and
# hangs (not errors) as a result. Must stay off on this host.
os.environ["SQLITE_WAL"] = "false"
os.environ["UPLOAD_DIR"] = f"{PROJECT_DIR}/var/uploads"
os.environ["ADMIN_DIST_DIR"] = f"{PROJECT_DIR}/static/admin"
# Comma-separate to allow more than one origin. Add "http://localhost:5173" here
# if you want to run the site locally against this deployed backend — without it
# the browser blocks every API call from localhost as a CORS error.
os.environ["PUBLIC_ORIGIN"] = "https://tglwebsite.vercel.app"
os.environ["SESSION_HOURS"] = "12"

# ---- 3. Create tables / upload dir ----
# Required: a2wsgi does not run ASGI lifespan events, so the app's own startup
# handler never fires here. Without this the first request fails with
# "no such table: admins". Safe to run on every reload — it's idempotent.
from app.database import init_db_sync  # noqa: E402

init_db_sync()

# ---- 4. Wrap the ASGI app for PythonAnywhere's WSGI server ----
# ForkSafeASGIMiddleware, not a2wsgi's ASGIMiddleware directly: uWSGI loads
# this file in the master process and then forks its workers. a2wsgi starts
# its event loop in a background thread at construction time, and threads do
# not survive fork() -- the worker would inherit a loop nobody is running, and
# every request would hang silently forever. See app/wsgi.py.
from app.main import app as _fastapi_app  # noqa: E402
from app.wsgi import ForkSafeASGIMiddleware  # noqa: E402

application = ForkSafeASGIMiddleware(_fastapi_app)
