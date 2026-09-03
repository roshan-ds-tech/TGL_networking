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

export const api = {
  login: (email, password) =>
    request('/api/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),
  stats: () => request('/api/admin/stats'),
  registrations: (params, signal) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) qs.set(k, v);
    });
    return request(`/api/admin/registrations?${qs}`, { signal });
  },
  setVerified: (id, verified) =>
    request(`/api/admin/registrations/${encodeURIComponent(id)}/verify`, {
      method: 'PATCH',
      body: { verified },
    }),
  proofUrl: (id) => `/api/admin/registrations/${encodeURIComponent(id)}/proof`,
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
