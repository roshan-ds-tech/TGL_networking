/* A remembered "this browser was signed in" flag (plus the avatar URL), used
   only to pick what the navbar draws while the real session check is still in
   flight.

   Without it every page load starts with no account info, so the header shows
   "Create Account" for the second the check takes (longer while the backend
   wakes) and then swaps it for the profile icon. The hint is never trusted for
   access — pages still wait for the server — and it is corrected as soon as
   any session response arrives. */

const KEY = 'tgl_signed_in';
const EVENT = 'tgl:auth-hint';

// Snapshot is the raw stored string ('' = no hint) so useSyncExternalStore
// sees a stable primitive between reads.
function read() {
  try {
    return window.localStorage.getItem(KEY) || '';
  } catch {
    return ''; // private mode / blocked storage: behave as "unknown"
  }
}

/** photoUrl: undefined keeps the stored one; null/'' clears it. */
export function setAuthHint(signedIn, photoUrl) {
  if (typeof window === 'undefined') return;
  let next = '';
  if (signedIn) {
    const keep = photoUrl === undefined ? parseAuthHint(read()).photo : photoUrl;
    next = JSON.stringify({ photo: keep || null });
  }
  if (next === read()) return;
  try {
    if (next) window.localStorage.setItem(KEY, next);
    else window.localStorage.removeItem(KEY);
  } catch {
    return;
  }
  window.dispatchEvent(new Event(EVENT));
}

export function parseAuthHint(raw) {
  if (!raw) return { signedIn: false, photo: null };
  try {
    const v = JSON.parse(raw);
    return { signedIn: true, photo: typeof v?.photo === 'string' ? v.photo : null };
  } catch {
    return { signedIn: true, photo: null }; // older/odd value: still a sign-in
  }
}

export function subscribeAuthHint(cb) {
  window.addEventListener(EVENT, cb);
  window.addEventListener('storage', cb); // another tab signed in or out
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener('storage', cb);
  };
}

export const getAuthHint = read;
// The prerendered page and the first hydration pass have no storage: they
// must agree with each other, so the server snapshot is always "unknown".
export const getServerAuthHint = () => '';
