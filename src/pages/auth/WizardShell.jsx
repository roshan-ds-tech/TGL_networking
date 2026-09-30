const WIZARD_STEPS = ['Account', 'Personal Profile', 'Business Profile', 'Event Registration'];
const JOURNEY = [
  { n: '01', t: 'Account', d: 'Create your TGL login.' },
  { n: '02', t: 'Personal & business profile', d: "Tell members who you are." },
  { n: '03', t: 'Season 1 registration', d: 'Register and confirm payment.' },
  { n: '04', t: 'Grand Finale · 5 Dec 2026', d: 'The on-site award show in Bengaluru.' },
  { n: '05', t: 'Networking membership', d: 'Activates after the Finale, for 3 months.' },
];

// Shared card + progress bar + "your TGL journey" aside for Signup and the
// two onboarding steps. Step 4 (Event Registration) never becomes "current"
// here — that happens later, outside this wizard, via the public site's
// payment-proof form — it's shown only as a preview of what's next.
export default function WizardShell({ step, children }) {
  return (
    <main style={{ maxWidth: 1240, margin: '0 auto', padding: '56px 28px 96px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', borderTop: '1px solid rgba(53,26,78,0.14)', marginBottom: 48 }}>
        {WIZARD_STEPS.map((label, i) => {
          const n = i + 1;
          const done = n < step;
          const cur = n === step;
          return (
            <div key={label} style={{ position: 'relative', padding: '18px 16px 0 0' }}>
              <span style={{ position: 'absolute', top: -1, left: 0, right: 0, height: 2, background: done || cur ? 'linear-gradient(90deg,#C08D2E,#EFCB77)' : 'transparent' }} />
              <p style={{ margin: '0 0 6px', fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, fontWeight: 600, color: done || cur ? '#A8762F' : 'rgba(43,23,64,0.35)' }}>
                {'0' + n}
              </p>
              <p style={{ margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: cur ? '#2B1740' : done ? 'rgba(43,23,64,0.7)' : 'rgba(43,23,64,0.4)' }}>
                {label}
              </p>
            </div>
          );
        })}
      </div>
      <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1fr)', gap: 56, alignItems: 'start' }}>
        <div style={{ background: '#FFFCF5', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 22, padding: '40px', boxShadow: '0 30px 60px -30px rgba(34,16,58,0.22)' }}>
          {children}
        </div>
        <aside data-sticky-col="" style={{ position: 'sticky', top: 110 }}>
          <div className="tgl-dark-card" style={{ borderRadius: 20, padding: '34px 32px', boxShadow: '0 30px 60px rgba(34,16,58,0.28)' }}>
            <p style={{ margin: '0 0 20px', fontSize: 10.5, letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: 700 }}>Your TGL journey</p>
            {JOURNEY.map((j) => (
              <div key={j.n} style={{ display: 'flex', gap: 14, padding: '13px 0', borderBottom: '1px dashed rgba(224,181,88,0.28)' }}>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11.5, color: '#EFCB77', minWidth: 22 }}>{j.n}</span>
                <div>
                  <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: '#FFFBF3' }}>{j.t}</p>
                  <p style={{ margin: '3px 0 0', fontSize: 12.5, lineHeight: 1.5, color: 'rgba(246,238,223,0.6)' }}>{j.d}</p>
                </div>
              </div>
            ))}
            <p style={{ margin: '18px 0 0', fontSize: 12.5, lineHeight: 1.55, color: 'rgba(246,238,223,0.6)' }}>
              Business verification is optional and happens separately from your profile.
            </p>
          </div>
        </aside>
      </div>
    </main>
  );
}
