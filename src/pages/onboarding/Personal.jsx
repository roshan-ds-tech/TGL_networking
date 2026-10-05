import { useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { Field } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import WizardShell from '../auth/WizardShell';
import { SIGNUP_DETAILS_KEY } from '../auth/Signup';

function stashedDetails() {
  try {
    const raw = sessionStorage.getItem(SIGNUP_DETAILS_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed?.full_name && parsed?.phone) return parsed;
  } catch {
    // malformed stash — fall through and ask for the details
  }
  return null;
}

export default function Personal({ initial, reload }) {
  // Name and phone were captured at sign-up (Signup.jsx) and are not asked
  // again. They are only rendered as fields when this page is reached without
  // that stash — an account created before this flow existed, or a reload of
  // a different tab — because the profile endpoint requires both.
  const [carried] = useState(stashedDetails);
  const [form, setForm] = useState({
    full_name: initial?.full_name || carried?.full_name || '',
    phone: initial?.phone || carried?.phone || '',
    city: initial?.city || '',
    role: initial?.role || '',
    short_bio: initial?.short_bio || '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(ev) {
    ev.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await api.savePersonal(form);
      sessionStorage.removeItem(SIGNUP_DETAILS_KEY);
      // Refresh the shared status first — the onboarding gate reads it, and a
      // stale copy would bounce the user straight back to this step.
      await reload?.();
      // Editing from the profile page goes back there; onboarding moves on.
      go(initial ? '/app/profile' : '/onboarding/business');
    } catch (err) {
      setError(err.message || 'Could not save your profile.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <WizardShell step={2}>
      <h1 style={{ margin: '0 0 8px', fontSize: 30, fontWeight: 800, letterSpacing: '-0.025em', color: '#2B1740' }}>About you</h1>
      <p style={{ margin: '0 0 30px', fontSize: 15, color: 'rgba(43,23,64,0.65)' }}>A light profile so members know who they&apos;re talking to.</p>

      <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 26 }}>
        <ImageSlot shape="circle" label="Photo" initial={form.full_name} style={{ width: 84, height: 84 }} fontSize={30} />
        <div>
          <p style={{ margin: '0 0 4px', fontSize: 14, fontWeight: 700, color: '#2B1740' }}>Profile photo</p>
          <p style={{ margin: 0, fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>Shown from your initial for now — photo uploads are coming soon.</p>
        </div>
      </div>

      <form onSubmit={submit}>
        {!carried && (
          <div className="tgl-portal-grid-2" style={{ marginBottom: 18 }}>
            <Field label="Full name">
              <input className="tgl-input" placeholder="Your full name" value={form.full_name} onChange={(e) => set('full_name', e.target.value)} required autoComplete="name" />
            </Field>
            <Field label="Phone">
              <input className="tgl-input" type="tel" placeholder="+91" value={form.phone} onChange={(e) => set('phone', e.target.value)} required autoComplete="tel" />
            </Field>
          </div>
        )}

        <div className="tgl-portal-grid-2" style={{ marginBottom: 18 }}>
          <Field label="Location">
            <input className="tgl-input" placeholder="City" value={form.city} onChange={(e) => set('city', e.target.value)} required />
          </Field>
          <Field label="Role">
            <input className="tgl-input" placeholder="Founder, Director…" value={form.role} onChange={(e) => set('role', e.target.value)} required />
          </Field>
        </div>

        <Field label="Short bio">
          <textarea className="tgl-input" rows={3} style={{ resize: 'vertical' }} placeholder="Two lines about you and what you're building." value={form.short_bio} onChange={(e) => set('short_bio', e.target.value)} required />
        </Field>

        {error && <div className="tgl-alert-error" role="alert" style={{ marginTop: 18 }}><span>{error}</span></div>}

        {/* The design source puts a "Back" button here, to step 01. That step
            is the sign-up form, and by the time this page renders the account
            already exists — going back would only offer to create a second
            one — so this step starts at Continue. */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 30 }}>
          <button
            type="submit"
            className="tglp-gold"
            disabled={submitting}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 12, padding: '16px 30px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontWeight: 700, fontSize: 13, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            {submitting ? 'Saving…' : initial ? 'Save changes' : 'Continue'}
            {!submitting && <svg width="17" height="17" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
          </button>
        </div>
      </form>
    </WizardShell>
  );
}
