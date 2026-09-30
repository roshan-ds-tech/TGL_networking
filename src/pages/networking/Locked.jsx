import { go } from '../../lib/customerApi';

const FINALE = new Date('2026-12-05T00:00:00+05:30').getTime();

const OPENS_AFTER = [
  { icon: 'i-users', title: 'Member directory', desc: 'Find founders and businesses from across Season 1.' },
  { icon: 'i-link', title: 'Referrals', desc: 'Give and receive introductions, tracked to outcome.' },
  { icon: 'i-target', title: 'Business Need Board', desc: 'Post what you need. Offer help where you can.' },
  { icon: 'i-medal', title: 'Recognition', desc: 'Growth Points and achievements for real contribution.' },
];

const DONE = { bg: '#C08D2E', color: '#22103A' };
const WAITING = { bg: 'rgba(246,238,223,0.1)', color: 'rgba(246,238,223,0.6)' };
const SOLID_LINE = '#C08D2E';
const FAINT_LINE = 'rgba(224,181,88,0.3)';

export function timelineFor(status) {
  const registered = !!status.event_registration;
  const confirmed = status.event_registration?.status === 'CONFIRMED';
  const m = status.membership;
  const active = m?.status === 'ACTIVE';

  return [
    {
      t: 'Registration',
      d: registered ? 'Complete' : 'Not submitted yet',
      icon: registered ? 'i-check' : 'i-doc',
      ...(registered ? DONE : WAITING),
      line: registered ? SOLID_LINE : FAINT_LINE,
    },
    {
      t: 'Payment',
      d: confirmed ? 'Confirmed — registration secured' : 'Awaiting confirmation',
      icon: confirmed ? 'i-check' : 'i-clock',
      ...(confirmed ? DONE : WAITING),
      line: confirmed ? SOLID_LINE : FAINT_LINE,
    },
    {
      t: 'Grand Finale',
      d: '5 December 2026 · Bengaluru',
      icon: active ? 'i-check' : 'i-calendar',
      bg: active ? '#C08D2E' : '#35194E',
      color: active ? '#22103A' : '#EFCB77',
      line: active ? SOLID_LINE : FAINT_LINE,
    },
    {
      t: 'Networking',
      d: active && m?.starts_at && m?.expires_at
        ? `Active · ${new Date(m.starts_at).toLocaleDateString()} – ${new Date(m.expires_at).toLocaleDateString()}`
        : 'Locked until activation',
      icon: active ? 'i-check' : 'i-lock',
      ...(active ? DONE : WAITING),
      line: 'transparent',
    },
  ];
}

export function Timeline({ items }) {
  return items.map((t, i) => (
    <div key={t.t} style={{ display: 'flex', gap: 18 }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <span style={{ width: 34, height: 34, borderRadius: '50%', background: t.bg, color: t.color, border: '1px solid rgba(224,181,88,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 14 }}>
          <svg width="15" height="15" viewBox="0 0 24 24"><use href={`#${t.icon}`} /></svg>
        </span>
        {i < items.length - 1 && <span style={{ flex: 1, width: 1, background: t.line }} />}
      </div>
      <div style={{ padding: '18px 0 8px' }}>
        <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#FFFBF3' }}>{t.t}</p>
        <p style={{ margin: '3px 0 0', fontSize: 13, color: 'rgba(246,238,223,0.6)' }}>{t.d}</p>
      </div>
    </div>
  ));
}

export default function NetworkingLocked({ status }) {
  const daysToFinale = Math.max(0, Math.ceil((FINALE - Date.now()) / 86400000));

  return (
    <>
      <section className="tgl-dark-card" style={{ position: 'relative', overflow: 'hidden' }}>
        <div
          aria-hidden="true"
          className="tglp-glow"
          style={{ position: 'absolute', top: -160, right: -160, width: 620, height: 620, borderRadius: '50%', background: 'radial-gradient(circle, rgba(224,181,88,0.2), rgba(224,181,88,0) 65%)', pointerEvents: 'none' }}
        />
        <div data-grid-2="" style={{ position: 'relative', maxWidth: 1240, margin: '0 auto', padding: '88px 28px 96px', display: 'grid', gridTemplateColumns: 'minmax(0,1.1fr) minmax(0,0.9fr)', gap: 64, alignItems: 'center' }}>
          <div className="tglp-rise">
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '9px 16px', border: '1px solid rgba(224,181,88,0.4)', borderRadius: 999, background: 'rgba(224,181,88,0.08)', fontSize: 10.5, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: '#E0B558', marginBottom: 30, whiteSpace: 'nowrap' }}>
              <span className="tglp-tick" style={{ width: 7, height: 7, borderRadius: '50%', background: '#E0B558' }} />
              Networking · Members-only
            </span>
            <h1 style={{ margin: '0 0 22px' }}>
              <span style={{ display: 'block', fontSize: 'clamp(32px,4vw,54px)', lineHeight: 1.02, letterSpacing: '-0.035em', fontWeight: 800, textTransform: 'uppercase', color: '#FFFBF3' }}>
                Your membership is
              </span>
              <span className="tgl-script-word" style={{ display: 'block', marginTop: 4, fontSize: 'clamp(54px,7vw,98px)', lineHeight: 1 }}>coming soon.</span>
            </h1>
            <p style={{ margin: '0 0 36px', maxWidth: 520, fontSize: 17, lineHeight: 1.65, color: 'rgba(246,238,223,0.75)' }}>
              Your Season 1 registration is confirmed. Networking access will activate after the TGL Grand Finale on 5 December 2026, and runs for 3 months.
            </p>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="tglp-gold"
                onClick={() => go('/app/events')}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 12, padding: '17px 30px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }}
              >
                Explore TGL Events
                <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
              </button>
              <button
                type="button"
                className="tglp-ghost-dark"
                onClick={() => go('/app/profile/membership')}
                style={{ padding: '17px 26px', border: '1px solid rgba(246,238,223,0.3)', borderRadius: 999, background: 'transparent', color: '#F6EEDF', fontSize: 12.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
              >
                Membership details
              </button>
            </div>
          </div>

          <div className="tglp-rise-2">
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, padding: '26px 28px', border: '1px solid rgba(224,181,88,0.3)', borderRadius: '20px 20px 0 0', background: 'rgba(255,251,243,0.05)' }}>
              <span style={{ fontSize: 64, fontWeight: 800, lineHeight: 1, color: '#EFCB77', fontVariantNumeric: 'tabular-nums' }}>{daysToFinale}</span>
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.2em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.7)' }}>Days to the Grand Finale</span>
            </div>
            <div style={{ padding: '10px 28px 26px', border: '1px solid rgba(224,181,88,0.3)', borderTop: 'none', borderRadius: '0 0 20px 20px', background: 'rgba(255,251,243,0.03)' }}>
              <Timeline items={timelineFor(status)} />
            </div>
          </div>
        </div>
      </section>

      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '64px 28px 96px' }}>
        <p style={{ margin: '0 0 10px', fontSize: 11, letterSpacing: '.28em', textTransform: 'uppercase', fontWeight: 700, color: '#C08D2E' }}>What opens after the Finale</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, marginTop: 22 }}>
          {OPENS_AFTER.map((item) => (
            <div key={item.title} style={{ padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" style={{ color: '#6B3E96' }}><use href={`#${item.icon}`} /></svg>
              <p style={{ margin: '18px 0 6px', fontSize: 16, fontWeight: 800, color: '#2B1740' }}>{item.title}</p>
              <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'rgba(43,23,64,0.62)' }}>{item.desc}</p>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
