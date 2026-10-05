/* Where the API lives.
 *
 * Production serves the site and the API from one origin (the FastAPI app
 * serves the built site), so requests are same-origin — that is what lets the
 * HttpOnly session cookie stay SameSite=Strict. In dev, Vite runs on its own
 * port and the API on :8000. VITE_API_URL overrides either. */
const raw = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

export const API_BASE = raw.replace(/\/$/, '');
