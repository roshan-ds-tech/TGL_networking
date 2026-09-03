# Deploying the backend to PythonAnywhere (free, no card)

No credit card required to sign up. Keeps the current design completely
unchanged — SQLite and payment screenshots stay on local disk, exactly as
already built and tested. The tradeoff is deployment mechanics: no Docker, no
`git push`-to-deploy — you configure the app once through their dashboard,
then click a "Reload" button after future code changes.

**Caveat I want to be upfront about:** I have not run this exact app on
PythonAnywhere's actual infrastructure — I don't have an account there and
can't get one in this environment. What I *have* verified locally is the
part most likely to break: driving the FastAPI app through the same
ASGI→WSGI adapter (`a2wsgi`) that this setup requires, covering login,
cookies, CSRF, file upload, binary file download, and a cold start against
an empty database — `backend/test_wsgi_bridge.py`, 13/13 passing. What I
can't verify from here is PythonAnywhere-specific behaviour (their exact
Python versions, disk quota enforcement, proxy quirks). If something doesn't
match this runbook once you're actually on their dashboard, tell me what you
see and I'll adjust.

> Why the WSGI file calls `init_db_sync()`: `a2wsgi` does not run ASGI
> lifespan events, so the app's normal startup hook — the thing that creates
> the database tables — never fires on this host. Without that call, every
> request returns a 500 with `no such table: admins`. This was a real bug
> caught while testing; the call is idempotent and safe on every reload.

> Why the WSGI file sets `SQLITE_WAL=false`: SQLite's WAL journal mode needs
> shared-memory file locking that PythonAnywhere's NFS-backed home directory
> doesn't support reliably — it hangs rather than erroring, with nothing in
> the error log, until PythonAnywhere's 5-minute watchdog kills the worker.
> This was found live on a real deployment (first request worked, every one
> after it hung), not caught by local testing since it's specific to
> network-filesystem storage. `SQLITE_WAL=false` uses SQLite's plain rollback
> journal instead, which doesn't have this dependency.

## 0. Prerequisite: push your latest commits

This repo (`github.com/roshan-ds-tech/TGL`) already exists and is where
PythonAnywhere will `git clone` from — just make sure everything's pushed:

```bash
cd C:\Users\rosha\Downloads\skykeen\tgl-react
git push
```

If the repo is private, PythonAnywhere will prompt for your GitHub
credentials on clone — use a [personal access token](https://github.com/settings/tokens)
as the password, not your account password.

## 1. Create the account

Sign up at [pythonanywhere.com](https://www.pythonanywhere.com/registration/register/beginner/)
— the free "Beginner" account needs only an email address, no card.

Your app will initially be reachable at `https://<username>.pythonanywhere.com`
with HTTPS already included — no domain or DNS setup needed for this path.

## 2. Get the code onto their filesystem

Open a **Bash console** (Dashboard → New console → Bash) and run:

```bash
git clone https://github.com/roshan-ds-tech/TGL.git ~/TGL
cd ~/TGL/backend
python3.10 -m venv venv    # check the Web tab for which Python versions are offered; pick the newest 3.10+
source venv/bin/activate
pip install -r requirements.txt
mkdir -p var/uploads
```

## 3. Build and upload the admin dashboard

PythonAnywhere's free console doesn't include Node.js, so build the React
dashboard **on your own machine** first (same as always):

```bash
cd admin-dashboard
npm install && npm run build     # outputs into ../backend/static/admin
cd ../backend
zip -r static-admin.zip static    # Windows PowerShell: Compress-Archive -Path 'static' -DestinationPath 'static-admin.zip' -Force
```

The zip must contain `static/admin/...` at its root (not `admin/...`), so that
unzipping it from `backend/` lands the files in `backend/static/admin/`.

> Already done for you: `backend/static-admin.zip` is built and ready to
> upload. Rebuild it with the commands above whenever the dashboard changes.

Then in PythonAnywhere's **Files** tab, navigate to `TGL/backend/`,
upload `static-admin.zip`, and back in the Bash console:

```bash
cd ~/TGL/backend
unzip static-admin.zip && rm static-admin.zip
```

Re-do this step (rebuild + re-upload the zip) whenever the admin dashboard's
source changes.

## 4. Create the web app

**Web tab → Add a new web app → Manual configuration** (not the Flask/Django
wizard) → pick the same Python version as your venv.

Then configure three things on that page:

1. **Virtualenv:** `/home/<username>/TGL/backend/venv`
2. **WSGI configuration file:** click the link to open it, delete
   everything, and paste in the contents of
   [`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py) from
   this repo. Edit the two `CHANGE-ME` values:
   - `PROJECT_DIR` → your real username
   - `SECRET_KEY` → generate one:
     ```bash
     python3 -c "import secrets; print(secrets.token_urlsafe(48))"
     ```
   - Also update `PUBLIC_ORIGIN` once your public site is deployed.
3. Click the big green **Reload** button at the top of the Web tab.

## 5. Create the admin login

Back in a Bash console:

```bash
cd ~/TGL/backend
source venv/bin/activate
python create_admin.py
```

## 6. Verify

Visit `https://<username>.pythonanywhere.com/admin` — you should see the
login screen. If not, check **Web tab → Log files → Error log**, which
shows Python tracebacks from the WSGI file.

## Updating after code changes

```bash
cd ~/TGL && git pull
cd backend && source venv/bin/activate && pip install -r requirements.txt
```

Then **Web tab → Reload**. (If only the admin dashboard changed, redo step 3
instead.)

## Backups

`~/TGL/backend/var/` holds `tgl.db` and `uploads/` — this is regular
disk in your PythonAnywhere account, so it persists indefinitely, but isn't
automatically backed up. Periodically download it via the Files tab, or from
your own machine:

```bash
scp -r <username>@ssh.pythonanywhere.com:TGL/backend/var ./tgl-backup-$(date +%F)
```
(SSH access requires a paid plan; free-tier accounts should instead
zip the folder in a Bash console and download it through the Files tab.)

## Known limitations of this path vs. the Docker-based options

- **Free tier disk quota is small** (roughly 512 MB last I'm aware — check
  your account's actual limit on the Dashboard). Should comfortably fit a
  Season 1 event's database and screenshot volume, but won't scale to many
  seasons' worth without occasional cleanup or an upgrade.
- **No automated deploys.** Every update is `git pull` + manual Reload.
- **Outbound internet is restricted to a whitelist** on the free tier. This
  backend makes no outbound HTTP calls today, so it doesn't matter now — but
  if you ever add one (an email service, a payment webhook, etc.), it would
  need to be on PythonAnywhere's allowed-hosts list or the free tier
  upgraded.
