import { useEffect, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { formatInrMinor } from '../../lib/format';
import { Timeline, timelineFor } from '../networking/Locked';

const MEMBERSHIP_META = {
  ACTIVE: { bg: '#C08D2E', color: '#22103A', label: 'Active' },
  PENDING: { bg: 'rgba(224,181,88,0.16)', color: '#EFCB77', label: 'Pending' },
  EXPIRING: { bg: 'rgba(224,181,88,0.16)', color: '#EFCB77', label: 'Expiring' },
  EXPIRED: { bg: 'rgba(142,59,59,0.14)', color: '#8E3B3B', label: 'Expired' },
};

// SHADOW PREVIEW. Shown only when the server says management has switched it on. It is a simulation: no balance here can be spent,
// and nothing on this card changes any invoice or payment.
function GrowthPointsPreview() {
  const [pv, setPv] = useState(null);
  useEffect(() => {
    let alive = true;
    api.growthPointsPreview().then((r) => { if (alive) setPv(r); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  if (!pv?.enabled) return null;
  const stat = (label, value) => (
    <div style={{ padding: 14, background: '#FFFCF5' }}>
      <p style={{ margin: '0 0 4px', fontSize: 10, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>{label}</p>
      <p style={{ margin: 0, fontSize: 17, fontWeight: 800, color: '#2B1740' }}>{value}</p>
    </div>
  );
  return (
    <section aria-label="Growth Points preview" style={{ marginTop: 26, padding: 20, borderRadius: 18, border: '1px dashed rgba(107,62,150,0.45)', background: 'rgba(107,62,150,0.04)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
        {(pv.redemption_open ? ['Growth Points', 'Renewal discount only'] : pv.labels).map((l) => (
          <span key={l} style={{ padding: '4px 10px', borderRadius: 999, background: 'rgba(107,62,150,0.12)', color: '#35194E', fontSize: 10, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}>{l}</span>
        ))}
      </div>
      <h2 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 800, color: '#2B1740' }}>{pv.redemption_open ? 'Growth Points' : pv.title}</h2>
      <p style={{ margin: '0 0 14px', fontSize: 13, lineHeight: 1.6, color: 'rgba(43,23,64,0.75)' }}>{pv.redemption_open ? 'Growth Points are rewards earned for verified networking contribution. They may be used only as a discount against eligible TGL subscription renewals. They are not cash.' : pv.disclaimer}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 1, background: 'rgba(53,26,78,0.1)', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 14, overflow: 'hidden' }}>
        {stat('Simulated points', pv.shadow_balance_points.toLocaleString('en-IN'))}
        {stat('Of which still pending', pv.pending_points.toLocaleString('en-IN'))}
        {stat('Possible value, if it were active', formatInrMinor(pv.estimated_value_paise))}
        {stat('Expiring within 30 days', pv.expiring_points.toLocaleString('en-IN'))}
      </div>
      {pv.cycle && (
        <p style={{ margin: '12px 0 0', fontSize: 12.5, color: 'rgba(43,23,64,0.7)' }}>
          This {pv.cycle.term_months}-month cycle: {pv.this_cycle_points.toLocaleString('en-IN')} of up to {pv.cycle_ceiling_points.toLocaleString('en-IN')} points.
          {pv.redemption_open ? ' Points are used only when you renew.' : ` Today this changes what you pay by ${formatInrMinor(pv.invoice_change_paise)}.`}
        </p>
      )}
    </section>
  );
}

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
          <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>TGL Membership</p>
          <h1 style={{ margin: '0 0 14px', fontSize: 'clamp(30px, 3.4vw, 44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>Season 1 Networking</h1>
          <p style={{ margin: '0 0 30px', fontSize: 16, lineHeight: 1.65, color: 'rgba(43,23,64,0.68)' }}>
            {active
              ? `Your Season 1 Networking membership is active until ${new Date(m.expires_at).toLocaleDateString()}.`
              : 'Your TGL Networking membership will become active after the Grand Finale.'}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 1, background: 'rgba(53,26,78,0.1)', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, overflow: 'hidden', marginBottom: 26 }}>
            <div style={{ padding: 18, background: '#FFFCF5' }}>
              <p style={{ margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>Type</p>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{m?.pathway === 'SUBSCRIPTION' ? 'Subscription' : status.has_registration ? 'Season 1 registrant' : 'Subscription'} · {active && m.starts_at && m.expires_at ? `${Math.round((new Date(m.expires_at) - new Date(m.starts_at)) / (30.44 * 24 * 3600 * 1000))} months` : '3 months'}</p>
            </div>
            <div style={{ padding: 18, background: '#FFFCF5' }}>
              <p style={{ margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>Activation</p>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{active ? new Date(m.starts_at).toLocaleDateString() : 'After Grand Finale'}</p>
            </div>
            <div style={{ padding: 18, background: '#FFFCF5' }}>
              <p style={{ margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>Expiry</p>
              <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{active ? new Date(m.expires_at).toLocaleDateString() : '3 months after activation'}</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 14, padding: '18px 20px', borderRadius: 16, background: 'rgba(107,62,150,0.07)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" style={{ color: '#6B3E96', flexShrink: 0, marginTop: 1 }}><use href="#i-bulb" /></svg>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: '#35194E' }}>
              {active
                ? 'The Grand Finale is complete. Your Networking membership is active for the dates shown.'
                : 'Payment confirms your Season 1 registration. It doesn\u2019t activate Networking — that happens after the Grand Finale on 5 December 2026.'}
            </p>
          </div>
          <GrowthPointsPreview />
          <p style={{ margin: '18px 0 0' }}>
            <button type="button" onClick={() => go('/app/subscription')} style={{ padding: '12px 22px', border: 'none', borderRadius: 999, background: '#35194E', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>Manage subscription and renewal</button>
          </p>
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
