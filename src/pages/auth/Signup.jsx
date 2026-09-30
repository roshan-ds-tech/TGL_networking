import { useState } from 'react';
import { ApiError, api, go } from '../../lib/customerApi';
import { Field } from '../../components/AppShell';
import WizardShell from './WizardShell';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/* Name and phone are asked here, with the rest of the account, but the
   register endpoint only takes credentials — they belong to the personal
   profile, which is saved at step 02. Parking them in sessionStorage keeps
   the promise the journey rail makes: you are asked once. Personal.jsx reads
   this key (and falls back to asking) — see SIGNUP_DETAILS_KEY there. */
export const SIGNUP_DETAILS_KEY = 'tgl_signup_details';

export default function Signup() {
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', password: '' });
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(ev) {
    ev.preventDefault();
    const errs = {};
    if (form.full_name.trim().length < 2) errs.full_name = 'Enter your full name.';
    if (!EMAIL_RE.test(form.email.trim())) errs.email = 'Enter a valid email address.';
    if (!/^\d{10}$/.test(form.phone.replace(/\D/g, '').replace(/^91|^0/, ''))) errs.phone = 'Enter a valid 10-digit mobile number.';
    if (form.password.length < 8) errs.password = 'Password must be at least 8 characters.';
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    setError('');
    setSubmitting(true);
    try {
      const result = await api.signup(form.email.trim(), form.password);
      if (result?.dev_verification_token) sessionStorage.setItem('tgl_dev_otp', result.dev_verification_token);
      sessionStorage.setItem(SIGNUP_DETAILS_KEY, JSON.stringify({ full_name: form.full_name.trim(), phone: form.phone.trim() }));
      go('/verify-email');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('An account already exists with this email. Log in instead — or use a different email to create a new account.');
      } else if (err instanceof ApiError && err.status === 429) {
        setError('Too many attempts. Please wait a few minutes and try again.');
      } else {
        setError(err.message || 'Could not create your account.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <WizardShell step={1}>
      <h1 style={{ margin: '0 0 8px', fontSize: 30, fontWeight: 800, letterSpacing: '-0.025em', color: '#2B1740' }}>Create your TGL account</h1>
      <p style={{ margin: '0 0 30px', fontSize: 15, color: 'rgba(43,23,64,0.62)' }}>Your account is the first step of the TGL journey.</p>

      <form onSubmit={submit} noValidate>
        <Field label="Full name" error={fieldErrors.full_name}>
          <input className="tgl-input" placeholder="Your full name" value={form.full_name} onChange={(e) => set('full_name', e.target.value)} autoFocus autoComplete="name" />
        </Field>
        <div className="tgl-portal-grid-2" style={{ margin: '18px 0' }}>
          <Field label="Email" error={fieldErrors.email}>
            <input className="tgl-input" type="email" placeholder="you@business.com" value={form.email} onChange={(e) => set('email', e.target.value)} autoComplete="email" />
          </Field>
          <Field label="Phone" error={fieldErrors.phone}>
            <input className="tgl-input" type="tel" placeholder="+91" value={form.phone} onChange={(e) => set('phone', e.target.value)} autoComplete="tel" />
          </Field>
        </div>
        <Field label="Password" error={fieldErrors.password}>
          <input className="tgl-input" type="password" placeholder="At least 8 characters" value={form.password} onChange={(e) => set('password', e.target.value)} autoComplete="new-password" />
        </Field>
        <p style={{ margin: '10px 0 30px', fontSize: 12.5, color: 'rgba(43,23,64,0.5)' }}>
          Prefer a one-time code? You can switch to OTP sign-in anytime.
        </p>

        {error && <div className="tgl-alert-error" role="alert" style={{ marginBottom: 20 }}><span>{error}</span></div>}

        <button
          type="submit"
          className="tglp-gold"
          disabled={submitting}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 12, padding: '17px 32px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontWeight: 700, fontSize: 13, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }}
        >
          {submitting ? 'Please wait…' : 'Create Account'}
          {!submitting && <svg width="17" height="17" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
        </button>
      </form>

      <p style={{ margin: '22px 0 0', fontSize: 13.5, color: 'rgba(43,23,64,0.6)' }}>
        Already have an account?{' '}
        <a href="/login" onClick={(e) => { e.preventDefault(); go('/login'); }} style={{ fontWeight: 700 }}>Sign in</a>
      </p>
    </WizardShell>
  );
}
