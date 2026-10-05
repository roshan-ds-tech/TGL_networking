import { useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { Button, showToast } from '../../components/AppShell';

const VERIF_MAP = {
  NOT_STARTED: ['Not started', 'You can verify anytime. Networking works fully without it.', 'rgba(53,26,78,0.06)', '#35194E'],
  PENDING: ['Pending review', 'Our team is reviewing your documents. This usually takes a few working days.', 'rgba(107,62,150,0.1)', '#6B3E96'],
  NEEDS_INFO: ['Needs information', 'We need one more document to complete your review.', 'rgba(192,141,46,0.14)', '#8A5A18'],
  VERIFIED: ['Verified', 'The TGL Verified badge now appears on your profile across Vertex and Networking.', '#22103A', '#EFCB77'],
  REJECTED: ['Not approved', 'Your submission could not be verified. You can resubmit with updated documents.', 'rgba(142,59,59,0.1)', '#8E3B3B'],
};

const WHY_ITEMS = [
  { icon: 'i-shield', title: 'Badge across the platform', desc: 'Shown on your Networking profile and Vertex listing.' },
  { icon: 'i-search', title: 'Verified filter', desc: 'Members and Vertex users can filter for verified businesses.' },
  { icon: 'i-doc', title: "What you'll need", desc: 'A registration document or GST certificate and one ID.' },
];

export default function Verification({ status, reload }) {
  const [submitting, setSubmitting] = useState(false);
  const verifStatus = status.business?.verification_status || 'NOT_STARTED';
  const [label, baseNote, bg, color] = VERIF_MAP[verifStatus] || VERIF_MAP.NOT_STARTED;
  const viaRegistration = !!status.business?.verified_via_registration;
  const note = viaRegistration
    ? 'Granted automatically because your TGL Season 1 registration and payment have been verified by our team. The badge appears on your profile across Vertex and Networking.'
    : baseNote;

  async function start() {
    setSubmitting(true);
    try {
      await api.startVerification();
      showToast('Verification submitted for review.');
      reload();
    } catch (err) {
      showToast(err.message || 'Could not start verification.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ maxWidth: 1240, margin: '0 auto', padding: '40px 28px 96px' }}>
      <button
        type="button"
        onClick={() => go('/app/profile')}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 0, border: 'none', background: 'none', color: '#6B3E96', fontSize: 11, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', marginBottom: 28 }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-back" /></svg>
        Profile
      </button>

      <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr)', gap: 48, alignItems: 'start' }}>
        <div>
          <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Optional</p>
          <h1 style={{ margin: '0 0 14px', fontSize: 'clamp(30px, 3.4vw, 44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>Verify your business</h1>
          <p style={{ margin: '0 0 32px', fontSize: 16, lineHeight: 1.65, color: 'rgba(43,23,64,0.68)' }}>
            TGL Verified is a trust badge, separate from your membership. You can use Networking fully without it.
          </p>
          <div style={{ borderTop: '1px solid rgba(53,26,78,0.12)', marginBottom: 32 }}>
            {WHY_ITEMS.map((item) => (
              <div key={item.title} style={{ display: 'flex', gap: 16, padding: '18px 0', borderBottom: '1px solid rgba(53,26,78,0.1)' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" style={{ color: '#A8762F', flexShrink: 0 }}><use href={`#${item.icon}`} /></svg>
                <div>
                  <p style={{ margin: '0 0 3px', fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{item.title}</p>
                  <p style={{ margin: 0, fontSize: 13.5, color: 'rgba(43,23,64,0.65)' }}>{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
          {(verifStatus === 'NOT_STARTED' || verifStatus === 'REJECTED') && (
            <Button onClick={start} disabled={submitting} style={{ padding: '17px 30px', fontSize: 12.5 }}>
              {submitting ? 'Submitting…' : 'Start Verification'}
              {!submitting && <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
            </Button>
          )}
        </div>

        <div>
          <div style={{ padding: 30, borderRadius: 22, background: bg, marginBottom: 18 }}>
            <p style={{ margin: '0 0 12px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.24em', textTransform: 'uppercase', color, opacity: 0.8 }}>Verification status</p>
            <p style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color }}>
              <svg width="24" height="24" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
              {label}
            </p>
            <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color, opacity: 0.85 }}>{note}</p>
          </div>
        </div>
      </div>
    </main>
  );
}
