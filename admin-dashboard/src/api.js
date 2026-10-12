/* Thin API client.
 *
 * The session cookie is HttpOnly, so JS never touches it — the browser attaches
 * it automatically on same-origin requests. What we DO read is the readable
 * CSRF cookie, which must be echoed back in a header on every mutation. */

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)tgl_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = {};
  const isMutation = method !== 'GET' && method !== 'HEAD';
  if (isMutation) {
    headers['Content-Type'] = 'application/json';
    headers['X-CSRF-Token'] = csrfToken();
  }

  const res = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (res.status === 204) return null;

  let payload = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }

  if (!res.ok) {
    const detail = payload?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.message || d.msg).join(', ')
      : detail || `Request failed (${res.status})`;
    throw new ApiError(message, res.status);
  }
  return payload;
}

function qs(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) q.set(k, v);
  });
  return q.toString();
}

const post = (path, body) => request(path, { method: 'POST', body: body || {} });
const enc = encodeURIComponent;

export const api = {
  login: (email, password) =>
    request('/api/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),
  stats: () => request('/api/admin/stats'),
  season1: () => request('/api/admin/events/season-1'),
  undoSeason1: () => request('/api/admin/events/season-1/undo-complete', { method: 'POST' }),
  completeSeason1: () => request('/api/admin/events/season-1/complete', { method: 'POST' }),
  registrations: (params, signal) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) qs.set(k, v);
    });
    return request(`/api/admin/registrations?${qs}`, { signal });
  },
  customers: (params, signal) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) qs.set(k, v);
    });
    return request(`/api/admin/customers?${qs}`, { signal });
  },
  setVerified: (id, verified) =>
    request(`/api/admin/registrations/${encodeURIComponent(id)}/verify`, {
      method: 'PATCH',
      body: { verified },
    }),
  remove: (id) =>
    request(`/api/admin/registrations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  removeCustomer: (id) =>
    request(`/api/admin/customers/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  proofUrl: (id) => `/api/admin/registrations/${encodeURIComponent(id)}/proof`,

  // Referral review (Phase 0). Every mutating action carries a reason; the server refuses without one.
  referrals: (params, signal) => request(`/api/admin/referrals?${qs(params)}`, { signal }),
  referral: (id) => request(`/api/admin/referrals/${enc(id)}`),
  referralEvidenceUrl: (id, evidenceId) => `/api/admin/referrals/${enc(id)}/closure/evidence/${enc(evidenceId)}/file`,
  verifyEvidence: (id, evidenceId, reason) => post(`/api/admin/referrals/${enc(id)}/closure/evidence/${enc(evidenceId)}/verify`, { reason }),
  rejectEvidence: (id, evidenceId, reason) => post(`/api/admin/referrals/${enc(id)}/closure/evidence/${enc(evidenceId)}/reject`, { reason }),
  verifyClosure: (id, reason) => post(`/api/admin/referrals/${enc(id)}/closure/verify`, { reason }),
  rejectClosure: (id, reason) => post(`/api/admin/referrals/${enc(id)}/closure/reject`, { reason }),
  invalidateClosure: (id, reason) => post(`/api/admin/referrals/${enc(id)}/closure/invalidate`, { reason }),
  resolveDispute: (id, outcome, reason) => post(`/api/admin/referrals/${enc(id)}/closure/resolve-dispute`, { outcome, reason }),
  flagReferral: (id, flagged, reason) => post(`/api/admin/referrals/${enc(id)}/flag`, { flagged, reason }),
  correctReferralStatus: (id, status, reason) => post(`/api/admin/referrals/${enc(id)}/status`, { status, reason }),
  addReferralNote: (id, reason) => post(`/api/admin/referrals/${enc(id)}/notes`, { reason }),

  // Subscriptions: payment review.
  subscriptions: (params, signal) => request(`/api/admin/subscriptions?${qs(params)}`, { signal }),
  subscriptionProofUrl: (id) => `/api/admin/subscriptions/${enc(id)}/proof`,
  verifyPayment: (id, reason) => post(`/api/admin/subscriptions/${enc(id)}/payment/verify`, { reason }),
  rejectPayment: (id, reason) => post(`/api/admin/subscriptions/${enc(id)}/payment/reject`, { reason }),
  refundSubscription: (id, reason) => post(`/api/admin/subscriptions/${enc(id)}/refund`, { reason }),

  // Growth Points, SHADOW MODE (Phase 1): analytics are read-only; the actions only add review rows or shadow ledger rows. None touches money.
  gpStatus: () => request('/api/admin/growth-points/status'),
  gpDemoMembers: () => request('/api/admin/growth-points/demo-members'),
  gpSummary: () => request('/api/admin/growth-points/summary'),
  gpFinance: () => request('/api/admin/growth-points/finance'),
  gpRedemptionState: () => request('/api/admin/growth-points/redemption/state'),
  gpKill: (reason) => post('/api/admin/growth-points/redemption/kill', { reason }),
  gpResume: (reason) => post('/api/admin/growth-points/redemption/resume', { reason }),
  gpGates: () => request('/api/admin/growth-points/gates'),
  gpReview: () => request('/api/admin/growth-points/review'),
  gpReviewUrl: () => '/api/admin/growth-points/review?format=markdown',
  gpObservation: () => request('/api/admin/growth-points/observation'),
  gpExceptions: () => request('/api/admin/growth-points/exceptions'),
  gpEconomics: () => request('/api/admin/growth-points/economics'),
  gpMembers: (params, signal) => request(`/api/admin/growth-points/members?${qs(params)}`, { signal }),
  gpMember: (id) => request(`/api/admin/growth-points/members/${enc(id)}`),
  gpLedger: (params, signal) => request(`/api/admin/growth-points/ledger?${qs(params)}`, { signal }),
  gpFlags: (params, signal) => request(`/api/admin/growth-points/flags?${qs(params)}`, { signal }),
  gpReconcileReport: () => request('/api/admin/growth-points/reconcile'),
  gpExportUrl: (format) => `/api/admin/growth-points/export?format=${format}`,
  gpReviewFlag: (id, outcome, reason) => post(`/api/admin/growth-points/flags/${enc(id)}/review?outcome=${outcome}`, { reason }),
  gpApplyReversal: (id, reason) => post(`/api/admin/growth-points/flags/${enc(id)}/apply-reversal`, { reason }),
  // Phase A: community activity (connections, needs, help offers). Records facts only; awards nothing.
  communityReport: (days) => request(`/api/admin/community/report${days ? `?days=${days}` : ''}`),
  communityNeeds: (params) => request(`/api/admin/community/needs?${qs(params)}`),
  communityRemoveNeed: (id, reason) => post(`/api/admin/community/needs/${id}/remove`, { reason }),
  communityRestoreNeed: (id, reason) => post(`/api/admin/community/needs/${id}/restore`, { reason }),
  gpScan: (reason) => post('/api/admin/growth-points/scan', { reason }),
  gpSweep: (reason) => post('/api/admin/growth-points/sweep', { reason }),
  gpReconcile: (reason) => post('/api/admin/growth-points/reconcile', { reason }),
};

export const inr = (minor) => {
  if (minor == null) return '—';
  // Integer arithmetic only: paise are whole numbers, so no floating-point rounding can creep into a shown amount.
  const whole = Math.trunc(minor / 100);
  const paise = Math.abs(minor % 100);
  return `₹${whole.toLocaleString('en-IN')}${paise ? `.${String(paise).padStart(2, '0')}` : ''}`;
};

export const CATEGORIES = {
  '01': 'Fashion, Apparel & Textile',
  '02': 'Food, Bakery & Beverage',
  '03': 'Handmade, Craft & Artisan',
  '04': 'Jewellery & Accessories',
  '05': 'Home Decor, Lifestyle & Interior',
  '06': 'Kids Products, Toys & Parenting',
  '07': 'Beauty, Personal Care & Wellness',
  '08': 'Fitness, Sports & Health',
  '09': 'Business, Professional & Digital Services',
  '10': 'Emerging, Innovative & Unique',
};

export const EMPLOYEES = { '1-3': '1–3', '4-6': '4–6', '7-10': '7–10' };
export const AGES = {
  lt6: 'Under 6 months',
  '6-12': '6–12 months',
  '1-3y': '1–3 years',
  '3y+': 'Over 3 years',
};
