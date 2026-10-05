import { useState } from 'react';
import { go } from '../../lib/customerApi';
import { showToast } from '../../components/AppShell';

/* Shown in place of every Networking page for an account with no Networking
   access (see networking_access in ProductApp). Pricing and per-tier benefits
   are product copy, not backend rules — nothing server-side differs by tier
   yet, and no payment is taken here. */

const PLANS = [
  {
    id: 'connect',
    name: 'Connect',
    price: 3000,
    tagline: 'Join the community and start building relationships.',
    features: [
      'Full member directory access',
      'Give and receive referrals',
      'Business Need Board',
      'Member profile and Growth Points',
    ],
  },
  {
    id: 'growth',
    name: 'Growth',
    price: 5000,
    tagline: 'For founders who want introductions, not just a directory.',
    popular: true,
    features: [
      'Everything in Connect',
      'Priority placement in the directory',
      'Monthly curated introductions',
      'Fast-track TGL Verified review',
      'Priority replies on Vertex enquiries',
    ],
  },
  {
    id: 'elite',
    name: 'Elite',
    price: 10000,
    tagline: 'The full TGL experience, with a dedicated hand to guide it.',
    features: [
      'Everything in Growth',
      'Featured member spotlight',
      '1:1 mentor session each month',
      'VIP seating at the Grand Finale',
      'Dedicated relationship manager',
    ],
  },
];

const PERKS = [
  { icon: 'i-users', title: 'Verified founders', desc: 'Every member is a registered Season 1 business.' },
  { icon: 'i-link', title: 'Tracked referrals', desc: 'Introductions followed through to revenue.' },
  { icon: 'i-shield', title: 'Trust you can see', desc: 'Trust scores and TGL Verified badges.' },
  { icon: 'i-clock', title: '3-month membership', desc: 'Full access for the whole season.' },
];

const inr = (n) => `₹${n.toLocaleString('en-IN')}`;

function Check({ gold }) {
  return (
    <span
      aria-hidden="true"
      style={{ width: 20, height: 20, borderRadius: '50%', flexShrink: 0, marginTop: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: gold ? 'rgba(224,181,88,0.2)' : 'rgba(107,62,150,0.1)', color: gold ? '#EFCB77' : '#6B3E96' }}
    >
      <svg width="11" height="11" viewBox="0 0 24 24"><use href="#i-check" /></svg>
    </span>
  );
}

function PlanCard({ plan, selected, onSelect }) {
  const dark = !!plan.popular;
  const ink = dark ? '#FFFBF3' : '#2B1740';
  const muted = dark ? 'rgba(246,238,223,0.7)' : 'rgba(43,23,64,0.62)';

  return (
    <article
      className={`tglp-rise ${dark ? 'tgl-dark-card' : ''}`}
      aria-label={`${plan.name} plan`}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        padding: '34px 30px 30px',
        borderRadius: 24,
        border: selected ? '2px solid #C08D2E' : dark ? '1px solid rgba(224,181,88,0.45)' : '1px solid rgba(53,26,78,0.12)',
        background: dark ? undefined : '#FFFCF5',
        boxShadow: dark ? '0 34px 70px -24px rgba(34,16,58,0.55)' : '0 14px 34px -22px rgba(34,16,58,0.25)',
        transition: 'border-color .2s ease, transform .3s ease',
      }}
    >
      {dark && (
        <span style={{ position: 'absolute', top: -13, left: '50%', transform: 'translateX(-50%)', padding: '6px 16px', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 10, fontWeight: 800, letterSpacing: '.18em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
          Most popular
        </span>
      )}

      <p style={{ margin: '0 0 6px', fontSize: 11, fontWeight: 700, letterSpacing: '.24em', textTransform: 'uppercase', color: dark ? '#E0B558' : '#8F6420' }}>{plan.name}</p>
      <p style={{ margin: '0 0 22px', minHeight: 44, fontSize: 14, lineHeight: 1.55, color: muted }}>{plan.tagline}</p>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 48, fontWeight: 800, lineHeight: 1, letterSpacing: '-0.03em', color: ink, fontVariantNumeric: 'tabular-nums' }}>{inr(plan.price)}</span>
      </div>
      <p style={{ margin: '0 0 26px', fontSize: 12.5, color: muted }}>3-month Season 1 membership</p>

      <button
        type="button"
        className={dark ? 'tglp-gold' : 'tglp-ghost'}
        onClick={() => onSelect(plan.id)}
        aria-pressed={selected}
        style={
          dark
            ? { padding: '16px 24px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }
            : { padding: '15px 24px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: selected ? 'rgba(53,26,78,0.06)' : 'transparent', color: '#35194E', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer' }
        }
      >
        {selected ? 'Selected' : `Choose ${plan.name}`}
      </button>

      <div style={{ height: 1, margin: '28px 0 22px', background: dark ? 'rgba(224,181,88,0.25)' : 'rgba(53,26,78,0.1)' }} />

      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 13 }}>
        {plan.features.map((f, i) => (
          <li key={f} style={{ display: 'flex', gap: 12, fontSize: 14, lineHeight: 1.45, color: ink, fontWeight: dark && i === 0 ? 700 : 500 }}>
            <Check gold={dark} />
            {f}
          </li>
        ))}
      </ul>
    </article>
  );
}

export default function Subscription() {
  const [selectedId, setSelectedId] = useState(null);
  const selected = PLANS.find((p) => p.id === selectedId);

  function proceed() {
    // No payment gateway is wired up yet — be upfront rather than pretend.
    showToast(`${selected.name} plan noted. Online payment opens soon — the TGL team will be in touch.`);
  }

  return (
    <>
      <section className="tgl-dark-card" style={{ position: 'relative', overflow: 'hidden' }}>
        <div
          aria-hidden="true"
          className="tglp-glow"
          style={{ position: 'absolute', top: -180, left: '50%', marginLeft: -310, width: 620, height: 620, borderRadius: '50%', background: 'radial-gradient(circle, rgba(224,181,88,0.2), rgba(224,181,88,0) 65%)', pointerEvents: 'none' }}
        />
        <div style={{ position: 'relative', maxWidth: 860, margin: '0 auto', padding: '84px 28px 150px', textAlign: 'center' }} className="tglp-rise">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '9px 16px', border: '1px solid rgba(224,181,88,0.4)', borderRadius: 999, background: 'rgba(224,181,88,0.08)', fontSize: 10.5, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: '#E0B558', marginBottom: 28, whiteSpace: 'nowrap' }}>
            <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-lock" /></svg>
            Networking · Members-only
          </span>
          <h1 style={{ margin: '0 0 20px' }}>
            <span style={{ display: 'block', fontSize: 'clamp(30px,4vw,52px)', lineHeight: 1.04, letterSpacing: '-0.035em', fontWeight: 800, textTransform: 'uppercase', color: '#FFFBF3' }}>
              Unlock the TGL
            </span>
            <span className="tgl-script-word" style={{ display: 'block', marginTop: 4, fontSize: 'clamp(50px,7vw,92px)', lineHeight: 1 }}>Networking community.</span>
          </h1>
          <p style={{ margin: '0 auto', maxWidth: 560, fontSize: 17, lineHeight: 1.65, color: 'rgba(246,238,223,0.75)' }}>
            Meet verified founders, trade tracked referrals and find the help your business needs. Pick the plan that fits where you are.
          </p>
        </div>
      </section>

      <main style={{ maxWidth: 1180, margin: '-96px auto 0', padding: '0 28px 96px', position: 'relative' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: 22, alignItems: 'stretch' }}>
          {PLANS.map((plan) => (
            <PlanCard key={plan.id} plan={plan} selected={plan.id === selectedId} onSelect={setSelectedId} />
          ))}
        </div>

        <div
          aria-live="polite"
          style={{ marginTop: 28, padding: '20px 26px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: 18, background: '#FFFCF5', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18, flexWrap: 'wrap' }}
        >
          {selected ? (
            <>
              <p style={{ margin: 0, fontSize: 15, color: '#2B1740' }}>
                <strong>{selected.name}</strong> · {inr(selected.price)} · 3-month membership
              </p>
              <button
                type="button"
                className="tglp-gold"
                onClick={proceed}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 12, padding: '15px 28px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }}
              >
                Continue
                <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
              </button>
            </>
          ) : (
            <p style={{ margin: 0, fontSize: 14.5, color: 'rgba(43,23,64,0.65)' }}>Choose a plan above to continue.</p>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginTop: 64 }}>
          {PERKS.map((p) => (
            <div key={p.title} style={{ padding: 24, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" style={{ color: '#6B3E96' }}><use href={`#${p.icon}`} /></svg>
              <p style={{ margin: '16px 0 6px', fontSize: 15.5, fontWeight: 800, color: '#2B1740' }}>{p.title}</p>
              <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.55, color: 'rgba(43,23,64,0.65)' }}>{p.desc}</p>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', marginTop: 28, padding: '18px 22px', borderRadius: 16, background: 'rgba(107,62,150,0.07)' }}>
          <svg width="20" height="20" viewBox="0 0 24 24" style={{ color: '#6B3E96', flexShrink: 0, marginTop: 1 }}><use href="#i-bulb" /></svg>
          <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: '#35194E' }}>
            Registered for a TGL event already? Networking opens for the email you registered with once the Grand Finale is complete. Log in with that same email, or{' '}
            <a href="/app/events" onClick={(e) => { e.preventDefault(); go('/app/events'); }} style={{ fontWeight: 700 }}>see TGL events</a>.
          </p>
        </div>
      </main>
    </>
  );
}
