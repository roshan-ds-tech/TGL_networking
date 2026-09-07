/* Registration submission.
 *
 * The whole FormData object is posted (not a plain object) so the payment
 * screenshot travels with the rest of the fields as multipart/form-data. */

const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export class SubmissionError extends Error {
  constructor(message, fieldErrors = {}) {
    super(message);
    this.fieldErrors = fieldErrors;
  }
}

export async function submitRegistration(formData) {
  let res;
  try {
    res = await fetch(`${API_BASE}/api/registrations`, {
      method: 'POST',
      body: formData,
    });
  } catch {
    throw new SubmissionError(
      'We could not reach the registration server. Check your connection and try again.',
    );
  }

  if (res.ok) return res.json();

  let payload = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }
  const detail = payload?.detail;

  // Field-level validation errors come back as [{field, message}].
  if (Array.isArray(detail)) {
    const fieldErrors = {};
    const apiToForm = {
      full_name: 'name',
      business_name: 'business',
      business_age: 'age',
      agreed_terms: 'agree',
      media_consent: 'mediaConsent',
    };
    detail.forEach((d) => {
      const key = apiToForm[d.field] || d.field;
      if (key) fieldErrors[key] = d.message;
    });
    throw new SubmissionError('Please correct the highlighted fields.', fieldErrors);
  }

  if (res.status === 429) {
    throw new SubmissionError(
      typeof detail === 'string' ? detail : 'Too many attempts. Please try again later.',
    );
  }

  // The category filled up between the page loading and this submission —
  // highlight the category field specifically rather than a generic banner.
  if (res.status === 409) {
    const message =
      typeof detail === 'string'
        ? detail
        : 'This category just filled up. Please choose another category.';
    throw new SubmissionError(message, { category: message });
  }

  throw new SubmissionError(
    typeof detail === 'string' ? detail : 'Something went wrong. Please try again.',
  );
}
