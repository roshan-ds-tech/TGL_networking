const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
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
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers,
  });
  if (res.status === 204) return null;
  const text = await res.text();
  const payload = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = payload?.detail;
    let message = 'Request failed.';
    if (typeof detail === 'string') {
      message = detail;
    } else if (Array.isArray(detail) && detail.length) {
      // FastAPI/Pydantic validation errors: [{field, message}, ...]
      message = detail.map((d) => d.message || d.msg).filter(Boolean).join(' ') || message;
    }
    throw new ApiError(message, res.status, payload);
  }
  return payload;
}

export const api = {
  signup: (email, password) => request('/api/v1/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) => request('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request('/api/v1/auth/logout', { method: 'POST' }),
  me: () => request('/api/v1/auth/me'),
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
  status: () => request('/api/v1/status'),
  savePersonal: (payload) => request('/api/v1/profile/personal', { method: 'PUT', body: JSON.stringify(payload) }),
  saveBusiness: (payload) => request('/api/v1/business', { method: 'PUT', body: JSON.stringify(payload) }),
  members: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null));
    return request(`/api/v1/networking/members${qs.size ? `?${qs}` : ''}`);
  },
  member: (id) => request(`/api/v1/networking/members/${id}`),
  referrals: () => request('/api/v1/referrals'),
  createReferral: (payload) => request('/api/v1/referrals', { method: 'POST', body: JSON.stringify(payload) }),
  updateReferral: (id, status) => request(`/api/v1/referrals/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  needs: () => request('/api/v1/networking/needs'),
  createNeed: (payload) => request('/api/v1/networking/needs', { method: 'POST', body: JSON.stringify(payload) }),
  helpNeed: (id) => request(`/api/v1/networking/needs/${id}/help`, { method: 'POST' }),
  listConnections: () => request('/api/v1/networking/connections'),
  createConnection: (payload) => request('/api/v1/networking/connections', { method: 'POST', body: JSON.stringify(payload) }),
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
