/* Where the API lives, and how to reach it when it is asleep.
 *
 * Production serves the site and the API from one origin (Vercel proxies /api
 * to the backend, or the backend serves the site itself), so requests are
 * same-origin — that is what lets the HttpOnly session cookie stay
 * SameSite=Strict. In dev, Vite runs on its own port and the API on :8000.
 * VITE_API_URL overrides either. */
const raw = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

export const API_BASE = raw.replace(/\/$/, '');

/* The backend runs on a plan that sleeps after ~15 idle minutes and takes up
 * to about a minute to start again. While it starts, the proxy in front of it
 * answers 502/503/504 at once instead of waiting. So:
 *   - before any write, wakeBackend() polls /api/health until the backend
 *     answers, and only then is the write sent — exactly once, so a slow wake
 *     can never turn into a duplicate account or registration;
 *   - reads that hit a waking backend wait for it and retry once.
 * Listeners can show a message via the 'tgl:backend-waking' / 'tgl:backend-awake'
 * window events. */
export const WAKING_STATUSES = new Set([502, 503, 504]);

const AWAKE_FOR_MS = 10 * 60 * 1000; // re-check after 10 min; the backend sleeps after 15
const WAKE_BUDGET_MS = 90 * 1000;
let awakeUntil = 0;
let inFlight = null;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const emit = (name) => {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(name));
};

/** Any normal answer from the backend proves it is up. */
export function markAwake() {
  awakeUntil = Date.now() + AWAKE_FOR_MS;
}

export function markMaybeAsleep() {
  awakeUntil = 0;
}

/** Resolves true once the backend answers (immediately if it recently did),
 *  false if it is still unreachable after ~90 s. Concurrent callers share one
 *  wake-up. */
export function wakeBackend() {
  if (Date.now() < awakeUntil) return Promise.resolve(true);
  if (!inFlight) {
    inFlight = (async () => {
      const start = Date.now();
      let delay = 1000;
      let announced = false;
      try {
        while (Date.now() - start < WAKE_BUDGET_MS) {
          try {
            const res = await fetch(`${API_BASE}/api/health`, { cache: 'no-store', signal: AbortSignal.timeout(30000) });
            if (res.ok) {
              markAwake();
              return true;
            }
            if (!WAKING_STATUSES.has(res.status)) return false; // a real error, not a sleeping server
          } catch {
            // network error or a 30 s timeout while it boots — keep trying
          }
          if (!announced) {
            announced = true;
            emit('tgl:backend-waking');
          }
          await sleep(delay);
          delay = Math.min(delay * 1.6, 8000);
        }
        return false;
      } finally {
        if (announced) emit('tgl:backend-awake');
        inFlight = null;
      }
    })();
  }
  return inFlight;
}
