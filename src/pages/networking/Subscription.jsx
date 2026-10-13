import { useEffect, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { showToast } from '../../components/AppShell';
import { formatInrMinor } from '../../lib/format';
import RenewalPanel from '../profile/RenewalPanel';

/* Shown in place of every Networking page for an account with no Networking
   access (see networking_access in ProductApp). The per-tier feature lists are
   product copy; the PRICES and the membership PERIOD come from the server (plans
   table) - nothing here assumes either - and the purchase
   is a real subscription + invoice. There is no payment gateway: the member
   pays outside the app and uploads proof, which a TGL admin verifies. */

const PLANS = [
  {
    id: 'connect',
    name: 'Connect',
    tagline: 'Join the community and start building relationships.',
    features: [
      'Full member directory access',
      'Give and receive referrals',
      'Business Need Board',
      'Member profile',
      'Growth Points: coming soon',
    ],
  },
  {
    id: 'growth',
    name: 'Growth',
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
  { icon: 'i-clock', title: 'Full-period access', desc: 'Access for the whole membership period shown on your plan.' },
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
      <p style={{ margin: '0 0 26px', fontSize: 12.5, color: muted }}>{plan.months}-month membership</p>

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

function Money({ minor }) {
  return <>{formatInrMinor(minor)}</>;
}

function PaymentInstructions({ info }) {
  // Never invent payment details: until management configures the official text, say so and show nothing else.
  if (info === undefined) return <li>Payment instructions are loading…</li>;
  if (!info?.configured) {
    return (
      <li>
        <strong>Payment instructions are pending.</strong> The TGL team has not published how to pay this invoice yet, so please do not transfer any money for now. We will notify you when they are ready.
      </li>
    );
  }
  return (
    <li>
      Pay using these instructions, and include your payment reference:
      <span style={{ display: 'block', margin: '6px 0 0', padding: '10px 14px', borderRadius: 10, background: 'rgba(53,26,78,0.05)', whiteSpace: 'pre-line', overflowWrap: 'anywhere' }}>{info.instructions}</span>
    </li>
  );
}

export function MyInvoice({ sub, onChange }) {
  const [file, setFile] = useState(null);
  const [instructions, setInstructions] = useState(undefined); // undefined = loading
  useEffect(() => {
    let live = true;
    api.paymentInstructions().then((i) => live && setInstructions(i)).catch(() => live && setInstructions({ configured: false }));
    return () => { live = false; };
  }, []);
  const [busy, setBusy] = useState(false);
  const inv = sub.invoice;
  const pay = sub.payment;
  const submitted = pay?.status === 'SUBMITTED';

  async function run(fn, ok) {
    setBusy(true);
    try {
      const next = await fn();
      if (ok) showToast(ok);
      onChange(next);
      setFile(null);
    } catch (err) {
      showToast(err.message || 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Your subscription" style={{ maxWidth: 760, margin: '0 auto', padding: 30, border: '1px solid rgba(192,141,46,0.4)', borderRadius: 22, background: '#FFFCF5', boxShadow: '0 30px 60px -34px rgba(34,16,58,0.35)' }}>
      <p style={{ margin: '0 0 6px', fontSize: 11, fontWeight: 700, letterSpacing: '.24em', textTransform: 'uppercase', color: '#8F6420' }}>Your subscription</p>
      <h2 style={{ margin: '0 0 6px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>{sub.plan.name} · <Money minor={inv.amount_due_minor} /></h2>
      <p style={{ margin: '0 0 22px', fontSize: 14, color: 'rgba(43,23,64,0.65)' }}>{inv.period_months}-month membership · Invoice {inv.number}</p>

      <dl style={{ margin: '0 0 22px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        {[['Amount due', <Money key="a" minor={inv.amount_due_minor} />], ['Payment reference', pay.reference], ['Status', submitted ? 'Payment proof under review' : pay.status === 'FAILED' ? 'Proof not accepted' : 'Awaiting your payment']].map(([k, v]) => (
          <div key={k} style={{ padding: '12px 14px', borderRadius: 12, background: 'rgba(53,26,78,0.05)' }}>
            <dt style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.68)' }}>{k}</dt>
            <dd style={{ margin: '4px 0 0', fontSize: 15, fontWeight: 700, color: '#2B1740', overflowWrap: 'anywhere' }}>{v}</dd>
          </div>
        ))}
      </dl>

      {pay.status === 'FAILED' && pay.rejection_reason && (
        <p role="alert" style={{ margin: '0 0 16px', padding: '10px 14px', borderRadius: 10, background: 'rgba(142,59,59,0.1)', fontSize: 13.5, color: '#8E3B3B' }}>{pay.rejection_reason}. Please upload a new proof.</p>
      )}

      <ol style={{ margin: '0 0 20px', paddingLeft: 20, fontSize: 14, lineHeight: 1.7, color: 'rgba(43,23,64,0.75)' }}>
        <li>Pay exactly <strong><Money minor={inv.amount_due_minor} /></strong> and include the reference <strong>{pay.reference}</strong>.</li>
        <PaymentInstructions info={instructions} />
        <li>Upload a screenshot or PDF of the payment below.</li>
        <li>TGL verifies it and opens Networking for the {inv.period_months} months of your plan. You will be notified.</li>
      </ol>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
        <input type="file" accept="image/png,image/jpeg,image/webp,image/gif,application/pdf" aria-label="Payment proof" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button type="button" className="tglp-gold" disabled={!file || busy} onClick={() => run(() => api.submitPaymentProof(sub.id, file), 'Payment proof submitted for review.')} style={{ padding: '12px 22px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: !file || busy ? 'default' : 'pointer', opacity: !file || busy ? 0.6 : 1 }}>
          {busy ? 'Uploading…' : submitted ? 'Replace proof' : 'Submit payment proof'}
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => api.cancelSubscription(sub.id), 'Subscription cancelled.')} style={{ border: 'none', background: 'none', color: 'rgba(43,23,64,0.68)', textDecoration: 'underline', cursor: 'pointer', font: 'inherit', fontSize: 13 }}>Cancel this subscription</button>
      </div>
    </section>
  );
}

function CurrentPlan({ sub }) {
  const inv = sub.invoice;
  return (
    <div style={{ padding: 24, border: '1px solid rgba(53,26,78,0.12)', borderRadius: 18, background: '#FFFCF5' }}>
      <p style={{ margin: 0, fontSize: 10, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>Your subscription</p>
      <p style={{ margin: '6px 0 2px', fontSize: 22, fontWeight: 800, color: '#2B1740' }}>{sub.plan.name} · {inv ? <Money minor={inv.list_price_minor ?? inv.amount_before_discount_minor} /> : null}</p>
      <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{inv?.period_months ?? sub.plan.period_months}-month term · active since {new Date(sub.starts_at).toLocaleDateString()} · ends {new Date(sub.expires_at).toLocaleDateString()}</p>
    </div>
  );
}

export default function Subscription() {
  const [selectedId, setSelectedId] = useState(null);
  const [serverPlans, setServerPlans] = useState(null); // code -> plan; the server's prices are the only ones used to buy
  const [sub, setSub] = useState(undefined); // undefined = loading, null = none
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api.plans().then((rows) => live && setServerPlans(Object.fromEntries(rows.map((p) => [p.code, p])))).catch(() => live && setServerPlans({}));
    api.currentSubscription().then((s) => live && setSub(s)).catch(() => live && setSub(null));
    return () => { live = false; };
  }, []);

  // Only plans the server returned are shown, with the server's price and period: no local fallback price.
  const plans = serverPlans ? PLANS.filter((p) => serverPlans[p.id]).map((p) => ({ ...p, price: serverPlans[p.id].price_minor / 100, months: serverPlans[p.id].period_months })) : [];
  const selected = plans.find((p) => p.id === selectedId);
  const pending = sub && sub.status === 'PENDING' ? sub : null;

  async function proceed() {
    setBusy(true);
    try {
      setSub(await api.createSubscription(selected.id));
      showToast(`${selected.name} selected. Your invoice is ready.`);
    } catch (err) {
      showToast(err.message || 'Could not start your subscription.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {sub && sub.status === 'ACTIVE' ? (
        <header style={{ maxWidth: 1180, margin: '0 auto', padding: '48px 28px 0' }}>
          <h1 style={{ margin: 0, fontSize: 'clamp(26px,3.4vw,40px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#2B1740' }}>Subscription and renewal</h1>
        </header>
      ) : (
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
      )}

      <main style={{ maxWidth: 1180, margin: sub && sub.status === 'ACTIVE' ? '24px auto 0' : '-96px auto 0', padding: '0 28px 96px', position: 'relative' }}>
        {sub && sub.status === 'ACTIVE' ? (
          <>
            <CurrentPlan sub={sub} />
            <RenewalPanel />
          </>
        ) : pending ? (
          <MyInvoice sub={pending} onChange={(next) => setSub(next)} />
        ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: 22, alignItems: 'stretch' }}>
          {plans.map((plan) => (
            <PlanCard key={plan.id} plan={plan} selected={plan.id === selectedId} onSelect={setSelectedId} />
          ))}
          {serverPlans !== null && plans.length === 0 && (
            <p role="alert" style={{ gridColumn: '1 / -1', margin: 0, padding: 24, textAlign: 'center', borderRadius: 18, background: '#FFFCF5', color: 'rgba(43,23,64,0.7)' }}>
              Plans and prices could not be loaded. Please refresh the page in a moment.
            </p>
          )}
        </div>
        )}

        {!pending && !(sub && sub.status === 'ACTIVE') && (
        <div
          aria-live="polite"
          style={{ marginTop: 28, padding: '20px 26px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: 18, background: '#FFFCF5', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18, flexWrap: 'wrap' }}
        >
          {selected ? (
            <>
              <p style={{ margin: 0, fontSize: 15, color: '#2B1740' }}>
                <strong>{selected.name}</strong> · {inr(selected.price)} · {selected.months}-month membership
              </p>
              <button
                type="button"
                className="tglp-gold"
                disabled={busy || serverPlans === null || sub === undefined}
                onClick={proceed}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 12, padding: '15px 28px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }}
              >
                {busy ? 'Creating invoice…' : 'Continue'}
                <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
              </button>
            </>
          ) : (
            <p style={{ margin: 0, fontSize: 14.5, color: 'rgba(43,23,64,0.65)' }}>{serverPlans === null ? 'Loading plans…' : 'Choose a plan above to continue.'}</p>
          )}
        </div>
        )}

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
