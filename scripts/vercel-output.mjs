/* Package the built site for Vercel (Build Output API v3), fronting the
 * FastAPI backend on Render.
 *
 * Why a proxy and not a plain cross-origin API call: session cookies are
 * HttpOnly + SameSite=Strict. A *.vercel.app page calling a *.onrender.com API
 * is cross-site, so browsers would drop those cookies and nobody could stay
 * signed in. Vercel instead forwards /api/* and /admin/* to Render, so the
 * browser only ever talks to one origin — exactly as when the backend serves
 * the site itself.
 *
 * The backend address comes from the BACKEND_ORIGIN environment variable
 * (Vercel project settings), never from source:
 *   BACKEND_ORIGIN=https://tgl-xxxx.onrender.com npm run build:vercel
 */
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist = resolve(root, 'dist');
const out = resolve(root, '.vercel/output');

export function backendOrigin(raw) {
  if (!raw) {
    throw new Error(
      'BACKEND_ORIGIN is not set. In Vercel: Project Settings -> Environment Variables -> ' +
        'BACKEND_ORIGIN = your Render service URL (e.g. https://tgl-xxxx.onrender.com).',
    );
  }
  let url;
  try {
    url = new URL(raw.trim());
  } catch {
    throw new Error(`BACKEND_ORIGIN is not a valid URL: ${raw}`);
  }
  if (url.protocol !== 'https:' && url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
    throw new Error('BACKEND_ORIGIN must use https:// (cookies and payment proofs travel over it).');
  }
  if ((url.pathname !== '/' && url.pathname !== '') || url.search || url.hash) {
    throw new Error('BACKEND_ORIGIN must be an origin only, e.g. https://tgl-xxxx.onrender.com');
  }
  return url.origin;
}

// Same policy the backend sends for the site (backend/app/main.py).
const SECURITY_HEADERS = {
  'Content-Security-Policy':
    "default-src 'self'; script-src 'self'; " +
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob:; " +
    "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; " +
    "base-uri 'self'; form-action 'self'",
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
};

// Member-app routes (keep in step with src/main.jsx and backend/app/main.py).
const PRODUCT = '^/(?:login|signup|verify-email|forgot-password|reset-password|(?:app|onboarding)(?:/.*)?)$';

export function routes(backend) {
  return [
    // 1. API + admin dashboard -> Render (terminal: Render sends its own headers).
    { src: '^/api(/.*)?$', dest: `${backend}/api$1` },
    { src: '^/admin(/.*)?$', dest: `${backend}/admin$1` },
    // 2. Headers for everything Vercel serves itself.
    { src: '^/(.*)$', headers: SECURITY_HEADERS, continue: true },
    { src: PRODUCT, headers: { 'X-Robots-Tag': 'noindex, nofollow' }, continue: true },
    { src: '^/assets/(.*)$', headers: { 'Cache-Control': 'public, max-age=31536000, immutable' }, continue: true },
    { src: '^/(?:index\\.html)?$', headers: { 'Cache-Control': 'no-cache' }, continue: true },
    // 3. Real files (assets, logo, robots.txt, sitemap.xml…).
    { handle: 'filesystem' },
    // 4. The homepage (explicit — don't rely on implicit directory indexes).
    { src: '^/$', dest: '/index.html' },
    // 5. Member-app deep links -> the app shell.
    { src: PRODUCT, dest: '/index.html', headers: { 'Cache-Control': 'no-cache' } },
    // 6. Anything else: the shell with a real 404 status (it renders the TGL 404 page).
    { src: '^/.*$', dest: '/index.html', status: 404, headers: { 'Cache-Control': 'no-cache' } },
  ];
}

function main() {
  const backend = backendOrigin(process.env.BACKEND_ORIGIN);
  if (!existsSync(resolve(dist, 'index.html'))) throw new Error('dist/ not built — run `npm run build` first.');
  rmSync(out, { recursive: true, force: true });
  mkdirSync(resolve(out, 'static'), { recursive: true });
  cpSync(dist, resolve(out, 'static'), { recursive: true });
  writeFileSync(resolve(out, 'config.json'), JSON.stringify({ version: 3, routes: routes(backend) }, null, 2));
  console.log(`vercel-output: static site + routes written; /api and /admin proxy to ${backend}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
