# Frontend on Vercel, backend on Render

The site and member app are served by a **new, separate Vercel project**
(not the one behind `tgl.skykeen.in`, which is left untouched). The FastAPI
backend stays on Render (`render.yaml`, see `DEPLOY_RENDER.md`), with Supabase
for data and files.

```
Browser ──► https://<project>.vercel.app          (Vercel, free Hobby plan)
              ├── /, /login, /app/…   static site + member app (from dist/)
              ├── /api/…   ──proxy──► https://<service>.onrender.com/api/…
              └── /admin/… ──proxy──► https://<service>.onrender.com/admin/…
                                           └──► Supabase (Postgres + Storage)
```

**Why the proxy:** session cookies are `HttpOnly; Secure; SameSite=Strict`.
A `vercel.app` page calling an `onrender.com` API directly is *cross-site*, so
browsers would drop the cookies and nobody could stay signed in. Vercel
forwards `/api` and `/admin` to Render, so the browser only ever sees one
origin. No CORS, no change to cookie security.

The Render address is **not** in the code: the build reads it from the
`BACKEND_ORIGIN` environment variable and generates Vercel's routing
(`scripts/vercel-output.mjs`, Vercel Build Output API). If it is missing or
not `https://`, the build fails with a clear message instead of deploying a
broken site.

## Steps

1. **Render first.** Deploy the backend per `DEPLOY_RENDER.md` and note its
   URL, e.g. `https://tgl-xxxx.onrender.com`. Check
   `https://tgl-xxxx.onrender.com/api/health` returns `{"status":"ok"}`.
2. **New Vercel project** — <https://vercel.com/new> → *Import* the GitHub
   repo `roshan-ds-tech/TGL_networking` → branch `main`.
   Make sure you are creating a **new** project; do not add this repo to the
   existing project that serves `tgl.skykeen.in`.
3. **Settings** — leave *Framework Preset* as detected; `vercel.json` sets
   the install and build commands (`npm ci`, `npm run build:vercel`). Root
   directory: the repo root.
4. **Environment variable** (Production, and Preview if you use previews):

   | Name | Value |
   |---|---|
   | `BACKEND_ORIGIN` | your Render URL, e.g. `https://tgl-xxxx.onrender.com` (no trailing path) |

   Do **not** set `VITE_API_URL` — the site must call the API on its own
   origin. No Supabase or Resend keys go to Vercel; they stay on Render.
5. **Deploy.** Note the Vercel URL, e.g. `https://tgl-networking.vercel.app`.
6. **Point the backend at it** — Render → service → *Environment*:
   * `PUBLIC_ORIGIN` = the Vercel URL (password-reset links use it),
   * `TRUSTED_PROXY_HOPS` = `2` (already the `render.yaml` default: Vercel +
     Render's load balancer).
   Save; Render redeploys.
7. **Admin login** (if not created yet), from your machine:
   ```bash
   cd backend && DATABASE_URL='<Supabase session pooler URL>' .venv/bin/python create_admin.py
   ```
8. **Verify** — `sh scripts/smoke-live.sh https://<project>.vercel.app`, then
   sign in to `https://<project>.vercel.app/admin` and open
   `/api/admin/diagnostics/client-ip`: `client_ip` should be **your** public
   IP. If it shows a Vercel or Render address instead, adjust
   `TRUSTED_PROXY_HOPS` (the per-IP rate limits depend on it).

If the backend's Render URL ever changes, update `BACKEND_ORIGIN` in Vercel
and redeploy.

## Notes

* **Cold starts.** Render Free sleeps after 15 idle minutes; the first API
  call after that waits while it wakes (~1 minute). The site itself (from
  Vercel) loads instantly; signing in or submitting the form is what waits.
  If Vercel's proxy times out during a wake-up the request fails with a
  "something went wrong / try again" message, and the retry succeeds.
* **Direct Render access.** The backend also still serves the site at its
  own `onrender.com` URL. Treat the Vercel URL as the public address; the
  Render URL is just the backend.
* **Custom domain later.** Add it to *this* Vercel project, then set
  `PUBLIC_ORIGIN` on Render to that domain.
