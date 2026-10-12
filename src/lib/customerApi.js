import { setAuthHint, setCurrentUserId } from './authHint';
import { API_BASE, WAKING_STATUSES, markAwake, markMaybeAsleep, wakeBackend } from './apiBase';

const REQUEST_TIMEOUT_MS = 20000;

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

function sleepingError() {
  return new ApiError('The TGL server is starting up. Please try again in a few seconds.', 503, null);
}

function networkError(err) {
  const timedOut = err?.name === 'TimeoutError' || err?.name === 'AbortError';
  return new ApiError(
    timedOut
      ? 'The server is taking too long to respond. Please try again.'
      : "Can't reach TGL right now. Check your connection and try again.",
    0,
    null,
  );
}

function csrfToken() {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith('tgl_customer_csrf='))
    ?.split('=')[1];
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  if (!['GET', 'HEAD'].includes(options.method || 'GET')) {
    const csrf = csrfToken();
    if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf);
  }
  const method = (options.method || 'GET').toUpperCase();
  const isRead = method === 'GET' || method === 'HEAD';
  const send = () =>
    fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...options,
      headers,
      // A hung request must not leave a button spinning forever.
      signal: options.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });

  // Writes only go out once the backend is known to be awake (see apiBase.js),
  // and are then sent exactly once — never retried, so a slow start can't
  // create a duplicate account or submission.
  if (!isRead && !(await wakeBackend())) throw sleepingError();

  let res;
  try {
    res = await send();
  } catch (err) {
    if (err?.name === 'AbortError' && options.signal?.aborted) throw err; // caller cancelled
    res = null;
    if (!isRead) throw networkError(err);
  }
  // A read that met a sleeping backend: wait for it, then try once more.
  if (isRead && (res === null || WAKING_STATUSES.has(res.status))) {
    markMaybeAsleep();
    if (!(await wakeBackend())) throw sleepingError();
    try {
      res = await send();
    } catch (err) {
      if (err?.name === 'AbortError' && options.signal?.aborted) throw err;
      throw networkError(err);
    }
  }
  if (WAKING_STATUSES.has(res.status)) {
    markMaybeAsleep();
    throw sleepingError();
  }
  markAwake();
  if (res.status === 204) return null;
  const text = await res.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    // Not JSON — e.g. a proxy error page while the server restarts.
    payload = null;
  }
  if (!res.ok) {
    const detail = payload?.detail;
    let message = res.status >= 500 ? 'Something went wrong on our side. Please try again in a moment.' : 'Request failed.';
    if (typeof detail === 'string') {
      message = detail;
    } else if (detail && !Array.isArray(detail) && typeof detail.message === 'string') {
      message = detail.message; // structured conflicts, e.g. { code: 'duplicate_referral', message, ... }
    } else if (Array.isArray(detail) && detail.length) {
      // FastAPI/Pydantic validation errors: [{field, message}, ...]
      message = detail.map((d) => d.message || d.msg).filter(Boolean).join(' ') || message;
    }
    throw new ApiError(message, res.status, payload);
  }
  return payload;
}

export const api = {
  signup: (details) => request('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(details) }),
  login: (email, password) => request('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }).then((r) => { setAuthHint(true); return r; }),
  logout: () => request('/api/v1/auth/logout', { method: 'POST' }).finally(() => { setAuthHint(false); setCurrentUserId(null); }),
  me: () => request('/api/v1/auth/me'),
  // 200 either way: { authenticated, user? }. For pages that work signed out.
  session: () => request('/api/v1/auth/session').then((r) => { setAuthHint(!!r?.authenticated, r?.user ? r.user.photo_url : undefined); setCurrentUserId(r?.user?.id); return r; }),
  // Full status when signed in, null when not — without a 401 round trip.
  optionalStatus: async () => ((await api.session())?.authenticated ? api.status() : null),
  verifyEmail: (token) => {
    const fd = new FormData();
    fd.set('token', token);
    return request('/api/v1/auth/verify-email', { method: 'POST', body: fd });
  },
  resendVerification: () => request('/api/v1/auth/resend-verification', { method: 'POST' }),
  otpRequest: (email) => request('/api/v1/auth/otp/request', { method: 'POST', body: JSON.stringify({ email }) }),
  otpVerify: (email, code) => request('/api/v1/auth/otp/verify', { method: 'POST', body: JSON.stringify({ email, code }) }),
  forgotPassword: (email) => request('/api/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) }),
  resetPassword: (token, newPassword) => request('/api/v1/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, new_password: newPassword }) }),
  status: () => request('/api/v1/status').then(
    (r) => { setAuthHint(true, r?.user ? r.user.photo_url : undefined); setCurrentUserId(r?.user?.id); return r; },
    (err) => { if (err?.status === 401) setAuthHint(false); throw err; },
  ),
  uploadPhoto: (blob) => {
    const fd = new FormData();
    fd.set('photo', blob, 'photo.jpg');
    return request('/api/v1/profile/photo', { method: 'POST', body: fd });
  },
  removePhoto: () => request('/api/v1/profile/photo', { method: 'DELETE' }),
  savePersonal: (payload) => request('/api/v1/profile/personal', { method: 'PUT', body: JSON.stringify(payload) }),
  saveBusiness: (payload) => request('/api/v1/business', { method: 'PUT', body: JSON.stringify(payload) }),
  members: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
    return request(`/api/v1/networking/members${qs.size ? `?${qs}` : ''}`);
  },
  member: (id) => request(`/api/v1/networking/members/${id}`),
  // Typeahead for the referral recipient: server-side filtered, paged, no contact data.
  searchMembers: ({ q = '', limit = 8, offset = 0 } = {}, signal) => {
    const qs = new URLSearchParams({ q, limit, offset });
    return request(`/api/v1/networking/members/search?${qs}`, { signal });
  },
  referrals: ({ view = 'all', stage = '', limit = 20, offset = 0 } = {}) => {
    const qs = new URLSearchParams({ view, limit, offset });
    if (stage) qs.set('stage', stage);
    return request(`/api/v1/referrals?${qs}`);
  },
  referralSummary: () => request('/api/v1/referrals/summary'),
  referral: (id) => request(`/api/v1/referrals/${id}`),
  createReferral: (payload) => request('/api/v1/referrals', { method: 'POST', body: JSON.stringify(payload) }),
  // Two-party meeting confirmation and verified deal closure (Phase 0).
  confirmMeeting: (id) => request(`/api/v1/referrals/${id}/meeting/confirm`, { method: 'POST' }),
  withdrawMeeting: (id) => request(`/api/v1/referrals/${id}/meeting/withdraw`, { method: 'POST' }),
  disputeMeeting: (id, reason) => request(`/api/v1/referrals/${id}/meeting/dispute`, { method: 'POST', body: JSON.stringify({ reason }) }),
  reportClosure: (id, payload) => request(`/api/v1/referrals/${id}/closure`, { method: 'POST', body: JSON.stringify(payload) }),
  editClosure: (id, payload) => request(`/api/v1/referrals/${id}/closure`, { method: 'PATCH', body: JSON.stringify(payload) }),
  confirmClosure: (id, expectedValueMinor) => request(`/api/v1/referrals/${id}/closure/confirm`, { method: 'POST', body: JSON.stringify({ expected_value_minor: expectedValueMinor }) }),
  disputeClosure: (id, reason) => request(`/api/v1/referrals/${id}/closure/dispute`, { method: 'POST', body: JSON.stringify({ reason }) }),
  cancelClosure: (id) => request(`/api/v1/referrals/${id}/closure/cancel`, { method: 'POST' }),
  addEvidence: (id, { evidenceType, note, file }) => {
    const fd = new FormData();
    fd.set('evidence_type', evidenceType);
    if (note) fd.set('note', note);
    fd.set('file', file);
    return request(`/api/v1/referrals/${id}/closure/evidence`, { method: 'POST', body: fd });
  },
  evidenceUrl: (id, evidenceId) => `${API_BASE}/api/v1/referrals/${id}/closure/evidence/${evidenceId}/file`,
  // Subscriptions: plan -> subscription -> invoice -> payment (manual proof an admin verifies).
  plans: () => request('/api/v1/plans'),
  currentSubscription: () => request('/api/v1/subscriptions/current'),
  dealRules: () => request('/api/v1/deal-rules'),
  paymentInstructions: () => request('/api/v1/subscriptions/payment-instructions'),
  createSubscription: (planCode) => request('/api/v1/subscriptions', { method: 'POST', body: JSON.stringify({ plan_code: planCode }) }),
  submitPaymentProof: (subscriptionId, file) => {
    const fd = new FormData();
    fd.set('proof', file);
    return request(`/api/v1/subscriptions/${subscriptionId}/payment-proof`, { method: 'POST', body: fd });
  },
  // Renewal: the exact calculation, and the confirmation. The server recomputes everything; these numbers are only what the member saw.
  renewalQuote: (planCode, points) => request(`/api/v1/renewal/quote?plan_code=${encodeURIComponent(planCode)}${points ? `&points=${Number(points)}` : ''}`),
  renewalSimulate: (body) => request('/api/v1/renewal/simulate', { method: 'POST', body: JSON.stringify(body) }),
  renewalConfirm: (body) => request('/api/v1/renewal/confirm', { method: 'POST', body: JSON.stringify(body) }),
  growthPointsOverview: () => request('/api/v1/growth-points/overview'),
  growthPointsHistory: () => request('/api/v1/growth-points/history'),
  // Growth Points, SHADOW MODE: a labelled preview of the member's own simulated points. Read-only; nothing here changes what anyone pays.
  growthPointsPreview: () => request('/api/v1/growth-points/preview'),
  cancelSubscription: (subscriptionId) => request(`/api/v1/subscriptions/${subscriptionId}/cancel`, { method: 'POST' }),
  updateReferral: (id, status) => request(`/api/v1/referrals/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  needs: () => request('/api/v1/networking/needs'),
  // Phase A: my own needs in every status, the offers on a need, and the lifecycle actions. These record facts only; nothing here earns anything.
  needsMine: () => request('/api/v1/networking/needs?mine=true'),
  needOffers: (id) => request(`/api/v1/networking/needs/${id}/offers`),
  actOnOffer: (offerId, action) => request(`/api/v1/networking/needs/offers/${offerId}`, { method: 'PATCH', body: JSON.stringify({ action }) }),
  cancelNeed: (id) => request(`/api/v1/networking/needs/${id}/cancel`, { method: 'POST' }),
  resolveNeed: (id, offerId) => request(`/api/v1/networking/needs/${id}/resolve`, { method: 'POST', body: JSON.stringify({ offer_id: offerId || null }) }),
  createNeed: (payload) => request('/api/v1/networking/needs', { method: 'POST', body: JSON.stringify(payload) }),
  helpNeed: (id, message) => request(`/api/v1/networking/needs/${id}/help`, { method: 'POST', body: message ? JSON.stringify({ message }) : undefined }),
  listConnections: () => request('/api/v1/networking/connections'),
  createConnection: (payload) => request('/api/v1/networking/connections', { method: 'POST', body: JSON.stringify(payload) }),
  // action: 'accept' | 'decline' (decline is silent: the sender is not told).
  respondConnection: (id, action) => request(`/api/v1/networking/connections/${id}`, { method: 'PATCH', body: JSON.stringify({ action }) }),
  // Withdraw a request you sent, or remove a connection.
  removeConnection: (id) => request(`/api/v1/networking/connections/${id}`, { method: 'DELETE' }),
  createReferralRequest: (payload) => request('/api/v1/networking/referral-requests', { method: 'POST', body: JSON.stringify(payload) }),
  startVerification: () => request('/api/v1/business/verification/start', { method: 'POST' }),
  notifications: () => request('/api/v1/notifications'),
  readNotification: (id) => request(`/api/v1/notifications/${id}/read`, { method: 'POST' }),
  readAllNotifications: () => request('/api/v1/notifications/read-all', { method: 'POST' }),
};

// `replace` is for redirects (auth guards, onboarding gates) so the Back
// button doesn't land on a page that immediately bounces the user again.
export function go(path, { replace = false } = {}) {
  const from = window.location.pathname;
  window.history[replace ? 'replaceState' : 'pushState']({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
  if (window.location.pathname !== from && !window.location.hash) window.scrollTo(0, 0);
}

// Only same-origin absolute paths are honoured as a post-login destination —
// "//evil.com" or "https://…" in ?next= would otherwise be an open redirect.
export function safeNext(raw) {
  return typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? raw : null;
}

export function nextParam() {
  return safeNext(new URLSearchParams(window.location.search).get('next'));
}

export function loginUrl(next) {
  const target = safeNext(next);
  return target ? `/login?next=${encodeURIComponent(target)}` : '/login';
}
