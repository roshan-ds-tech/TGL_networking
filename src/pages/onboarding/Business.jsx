import { useEffect, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { Field, showToast } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import WizardShell from '../auth/WizardShell';

const GOLD_BTN = { display: 'inline-flex', alignItems: 'center', gap: 12, padding: '16px 30px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontWeight: 700, fontSize: 13, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' };
const GHOST_BTN = { padding: '16px 24px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 12, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' };

export default function Business({ initial, reload }) {
  const [form, setForm] = useState(() => {
    const empty = {
      business_name: '', category: '', description: '', city: '', employee_band: '', business_age: '', business_stage: '',
      founder_story: '', website: '', linkedin: '', instagram: '',
    };
    return Object.fromEntries(Object.keys(empty).map((k) => [k, initial?.[k] ?? '']));
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // Editing an existing business (from the profile page) returns there;
  // first-time onboarding continues into the product.
  const editing = !!initial;

  // Profile checklist links land on a specific section (#founder-story,
  // #links) — bring it into view and focus its first field.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    const el = id && document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.querySelector('input, textarea')?.focus({ preventScroll: true });
  }, []);

  function set(key, value) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(ev) {
    ev.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await api.saveBusiness(Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v || null])));
      await reload?.();
      if (editing) {
        go('/app/profile');
        showToast('Business details saved.');
      } else {
        go('/app/vertex');
        showToast('Profile saved. Register for Season 1 from Events.');
      }
    } catch (err) {
      setError(err.message || 'Could not save your business details.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <WizardShell step={3}>
      <h1 style={{ margin: '0 0 8px', fontSize: 30, fontWeight: 800, letterSpacing: '-0.025em', color: '#2B1740' }}>Your business</h1>
      <p style={{ margin: '0 0 30px', fontSize: 15, color: 'rgba(43,23,64,0.65)' }}>
        Used across Vertex, Networking and your Season 1 registration — you won&apos;t be asked twice.
      </p>

      <form onSubmit={submit}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 26 }}>
          <ImageSlot shape="rounded" radius={16} label="Logo" initial={form.business_name} style={{ width: 84, height: 84 }} fontSize={30} />
          <div style={{ flex: 1 }}>
            <Field label="Business name">
              <input className="tgl-input" placeholder="Registered or trading name" value={form.business_name} onChange={(e) => set('business_name', e.target.value)} required />
            </Field>
          </div>
        </div>

        <div className="tgl-portal-grid-2" style={{ marginBottom: 18 }}>
          <Field label="Category">
            <select className="tgl-input" value={form.category} onChange={(e) => set('category', e.target.value)} required>
              <option value="">Select a category</option>
              {CATEGORIES.map((c) => (
                <option key={c.code} value={c.code}>{c.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Location">
            <input className="tgl-input" placeholder="City" value={form.city} onChange={(e) => set('city', e.target.value)} required />
          </Field>
          <Field label="Business age">
            <select className="tgl-input" value={form.business_age} onChange={(e) => set('business_age', e.target.value)} required>
              <option value="">Select age</option>
              <option value="lt6">Less than 6 months</option>
              <option value="6-12">6–12 months</option>
              <option value="1-3y">1–3 years</option>
              <option value="3y+">More than 3 years</option>
            </select>
          </Field>
          <Field label="Team size">
            <select className="tgl-input" value={form.employee_band} onChange={(e) => set('employee_band', e.target.value)} required>
              <option value="">Select team size</option>
              <option value="1-3">1–3</option>
              <option value="4-6">4–6</option>
              <option value="7-10">7–10</option>
            </select>
          </Field>
          {/* Not in the design source, but the business record requires it —
              and asking here is cheaper than a follow-up form later. */}
          <Field label="Current stage">
            <input className="tgl-input" placeholder="Bootstrapped, Early revenue, Scaling…" value={form.business_stage} onChange={(e) => set('business_stage', e.target.value)} required />
          </Field>
        </div>

        <Field label="What the business does">
          <textarea className="tgl-input" rows={3} style={{ resize: 'vertical' }} placeholder="Describe your products or services." value={form.description} onChange={(e) => set('description', e.target.value)} required />
        </Field>

        <div id="founder-story" style={{ marginTop: 18 }}>
          <Field label="Founder story" optional>
            <textarea className="tgl-input" rows={4} maxLength={2000} style={{ resize: 'vertical' }} placeholder="Why you started, what you've learned, where you're headed." value={form.founder_story} onChange={(e) => set('founder_story', e.target.value)} />
          </Field>
        </div>

        <div id="links" style={{ marginTop: 18 }}>
          <p style={{ margin: '0 0 10px', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>Website &amp; socials · optional</p>
          <div className="tgl-portal-grid-2">
            <Field label="Website">
              <input className="tgl-input" inputMode="url" autoComplete="url" placeholder="yourbusiness.com" value={form.website} onChange={(e) => set('website', e.target.value)} maxLength={300} />
            </Field>
            <Field label="LinkedIn">
              <input className="tgl-input" inputMode="url" placeholder="linkedin.com/company/…" value={form.linkedin} onChange={(e) => set('linkedin', e.target.value)} maxLength={300} />
            </Field>
            <Field label="Instagram">
              <input className="tgl-input" inputMode="url" placeholder="instagram.com/…" value={form.instagram} onChange={(e) => set('instagram', e.target.value)} maxLength={300} />
            </Field>
          </div>
        </div>

        {error && <div className="tgl-alert-error" role="alert" style={{ marginTop: 18 }}><span>{error}</span></div>}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 30 }}>
          <button type="button" className="tglp-ghost" onClick={() => go(editing ? '/app/profile' : '/onboarding/personal')} style={GHOST_BTN}>{editing ? 'Cancel' : 'Back'}</button>
          <button type="submit" className="tglp-gold" disabled={submitting} style={GOLD_BTN}>
            {submitting ? 'Saving…' : editing ? 'Save changes' : 'Save & Continue'}
            {!submitting && <svg width="17" height="17" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
          </button>
        </div>
      </form>
    </WizardShell>
  );
}
