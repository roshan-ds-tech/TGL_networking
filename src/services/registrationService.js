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

  // Field-level errors arrive as [{field, message}] — both 422 validation
  // failures and 409 conflicts (a full category, an already-used UTR), so each
  // one can be shown against the input it belongs to.
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
    // With a single problem, lead with its actual message rather than a vague
    // "correct the highlighted fields" that makes the user hunt for it.
    const summary =
      detail.length === 1 && detail[0].message
        ? detail[0].message
        : 'Please correct the highlighted fields.';
    throw new SubmissionError(summary, fieldErrors);
  }

  if (res.status === 429) {
    throw new SubmissionError(
      typeof detail === 'string' ? detail : 'Too many attempts. Please try again later.',
    );
  }

  // Fallback for a conflict that didn't carry the field-level shape above.
  if (res.status === 409) {
    throw new SubmissionError(
      typeof detail === 'string'
        ? detail
        : 'That submission conflicts with an existing registration. Please review your details.',
    );
  }

  throw new SubmissionError(
    typeof detail === 'string' ? detail : 'Something went wrong. Please try again.',
  );
}
