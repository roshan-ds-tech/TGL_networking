import { go } from '../../lib/customerApi';
import { Timeline, timelineFor } from '../networking/Locked';

const MEMBERSHIP_META = {
  ACTIVE: { bg: '#C08D2E', color: '#22103A', label: 'Active' },
  PENDING: { bg: 'rgba(224,181,88,0.16)', color: '#EFCB77', label: 'Pending' },
  EXPIRING: { bg: 'rgba(224,181,88,0.16)', color: '#EFCB77', label: 'Expiring' },
  EXPIRED: { bg: 'rgba(142,59,59,0.14)', color: '#8E3B3B', label: 'Expired' },
};

export default function Membership({ status }) {
  const m = status.membership;
  const active = m?.status === 'ACTIVE';
  const meta = MEMBERSHIP_META[m?.status] || MEMBERSHIP_META.PENDING;
  const timeline = timelineFor(status);

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

      <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 48, alignItems: 'start' }}>
        <div>
          <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>TGL Membership</p>
          <h1 style={{ margin: '0 0 14px', fontSize: 'clamp(30px, 3.4vw, 44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>Season 1 Networking</h1>
          <p style={{ margin: '0 0 30px', fontSize: 16, lineHeight: 1.65, color: 'rgba(43,23,64,0.68)' }}>
            {active
              ? `Your Season 1 Networking membership is active until ${new Date(m.expires_at).toLocaleDateString()}.`
              : 'Your TGL Networking membership will become active after the Grand Finale.'}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 1, background: 'rgba(53,26,78,0.1)', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, overflow: 'hidden', marginBottom: 26 }}>
            <div style={{ padding: 18, background: '#FFFCF5' }}>
              <p style={{ margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)' }}>Type</p>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#2B1740' }}>Complimentary · 3 months</p>
            </div>
            <div style={{ padding: 18, background: '#FFFCF5' }}>
              <p style={{ margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)' }}>Activation</p>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{active ? new Date(m.starts_at).toLocaleDateString() : 'After Grand Finale'}</p>
            </div>
            <div style={{ padding: 18, background: '#FFFCF5' }}>
              <p style={{ margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)' }}>Expiry</p>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{active ? new Date(m.expires_at).toLocaleDateString() : '3 months after activation'}</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 14, padding: '18px 20px', borderRadius: 16, background: 'rgba(107,62,150,0.07)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" style={{ color: '#6B3E96', flexShrink: 0, marginTop: 1 }}><use href="#i-bulb" /></svg>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: '#35194E' }}>
              Payment confirms your Season 1 registration. It doesn&apos;t activate Networking — that happens after the Grand Finale on 5 December 2026.
            </p>
          </div>
        </div>

        <div className="tglp-framed">
          <div className="tgl-dark-card" style={{ padding: '32px 32px 20px', borderRadius: 22, boxShadow: '0 30px 60px rgba(34,16,58,0.28)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <p style={{ margin: 0, fontSize: 10.5, letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: 700 }}>Status</p>
              <span style={{ padding: '7px 14px', borderRadius: 999, background: meta.bg, color: meta.color, fontSize: 10.5, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase' }}>{meta.label}</span>
            </div>
            <Timeline items={timeline} />
          </div>
        </div>
      </div>
    </main>
  );
}
