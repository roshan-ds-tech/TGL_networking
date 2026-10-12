import { useEffect, useState } from 'react';
import { showToast } from '../../components/AppShell';
import { api } from '../../lib/customerApi';
import { formatInrMinor } from '../../lib/format';
import { MyInvoice } from '../networking/Subscription';

// Renew, and redeem Growth Points on the renewal, from the subscription page. The server computes and re-validates EVERYTHING; this component only
// shows what the server returned and sends back the figures the member saw so the server can refuse if they changed.
//   REAL        redemption is open for this member: "Redeem Growth Points" -> calculation -> confirm -> a real discount on the renewal invoice
//   SIMULATION  a synthetic demo account in development: the same screens, ending in a rolled-back simulation (nothing is saved)
//   PREVIEW     Growth Points are not active: the numbers are labelled hypothetical and there is no redeem button
const PLANS = [['connect', 'Connect'], ['growth', 'Growth'], ['elite', 'Elite']];
const box = { padding: 22, borderRadius: 18, border: '1px solid rgba(53,26,78,0.12)', background: '#FFFCF5', marginTop: 24 };
const label = { margin: 0, fontSize: 10, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' };
const when = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '—');
const pts = (n) => Number(n).toLocaleString('en-IN');

function Row({ name, value, strong, note }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '7px 0', borderBottom: '1px solid rgba(53,26,78,0.07)' }}>
      <span style={{ fontSize: 13.5, color: 'rgba(43,23,64,0.75)' }}>{name}{note && <span style={{ display: 'block', fontSize: 11.5, color: 'rgba(43,23,64,0.55)' }}>{note}</span>}</span>
      <span style={{ fontSize: strong ? 17 : 14, fontWeight: strong ? 800 : 600, color: '#2B1740', textAlign: 'right' }}>{value}</span>
    </div>
  );
}

const goldBtn = (enabled) => ({ padding: '12px 22px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', cursor: enabled ? 'pointer' : 'default', opacity: enabled ? 1 : 0.55 });
const darkBtn = { padding: '11px 22px', border: 'none', borderRadius: 999, background: '#35194E', color: '#fff', fontWeight: 700, cursor: 'pointer' };

export default function RenewalPanel() {
  const [plan, setPlan] = useState('connect');
  const [q, setQ] = useState(null);
  const [sub, setSub] = useState(undefined);
  const [step, setStep] = useState('view'); // view | calc | done
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState(null);

  useEffect(() => {
    let live = true;
    api.currentSubscription().then((s) => live && setSub(s)).catch(() => live && setSub(null));
    return () => { live = false; };
  }, []);
  useEffect(() => {
    let live = true;
    api.renewalQuote(plan).then((r) => live && setQ(r)).catch(() => live && setQ(null));
    return () => { live = false; };
  }, [plan, sub]);

  if (sub && sub.status === 'PENDING' && sub.is_renewal && sub.invoice) {
    return (
      <div style={box}>
        {outcome?.kind === 'REAL' && <p role="status" style={{ margin: '0 0 12px', padding: 14, borderRadius: 12, background: 'rgba(60,140,90,0.12)', color: '#1F4D33', fontSize: 13.5, lineHeight: 1.55 }}>{outcome.message}</p>}
        <p style={label}>Your renewal</p>
        <MyInvoice sub={sub} onChange={setSub} />
      </div>
    );
  }
  if (!q || q.enabled === false || !q.renewal_window) return null;

  const now = Date.now();
  const inWindow = now >= new Date(q.renewal_window.opens).getTime() && now <= new Date(q.renewal_window.closes).getTime();
  const mode = q.mode;
  const points = q.points_to_be_redeemed;
  const eligible = q.eligible_old_cycle_points;
  const canRedeem = (mode === 'REAL' && q.can_redeem && inWindow) || (mode === 'SIMULATION' && q.can_simulate && inWindow);
  const price = q.new_plan_price_minor;
  const body = { plan_code: plan, redeem: points > 0, expected_points: points > 0 ? points : null, expected_discount_minor: points > 0 ? q.hypothetical_discount_paise : null };

  async function run(fn, onOk) {
    setBusy(true);
    try { await fn(); onOk?.(); } catch (err) {
      showToast(err.message || 'Something went wrong. Please try again.');
      setStep('view');
      api.renewalQuote(plan).then(setQ).catch(() => {});
    } finally { setBusy(false); }
  }
  const confirmReal = () => run(async () => {
    const res = await api.renewalConfirm(body);
    setOutcome({ kind: 'REAL', message: points > 0 ? `Growth Points were used as a subscription discount (${formatInrMinor(res.growth_points_discount_minor)} off). They were not converted into cash. Your invoice is ${formatInrMinor(res.amount_due_minor)}.` : 'Renewal started. Your invoice is below.' });
    setSub(await api.currentSubscription());
    setStep('view');
  });
  const renewFullPrice = () => run(async () => {
    await api.renewalConfirm({ plan_code: plan, redeem: false });
    setOutcome({ kind: 'REAL', message: 'Renewal started at the full price. No Growth Points were used.' });
    setSub(await api.currentSubscription());
  });
  const simulate = () => run(async () => {
    const res = await api.renewalSimulate(body);
    setOutcome({ kind: 'SIMULATION', res });
    setStep('done');
  });

  return (
    <section aria-label="Renew and redeem Growth Points" style={box}>
      <p style={label}>{mode === 'REAL' ? 'Renew your subscription' : mode === 'SIMULATION' ? 'Renewal (simulation)' : 'Renewal preview'}</p>
      {mode !== 'REAL' && <p role="note" style={{ margin: '8px 0 0', padding: 12, borderRadius: 12, background: 'rgba(107,62,150,0.1)', color: '#35194E', fontSize: 12.5, fontWeight: 700 }}>{q.label}</p>}
      <p style={{ margin: '10px 0 12px', fontSize: 13, color: 'rgba(43,23,64,0.7)' }}>
        Current plan: <strong>{q.current_plan}</strong>, ends {when(q.renewal_window.old_term_ends)}. Renewal opens {when(q.renewal_window.opens)} and closes {when(q.renewal_window.closes)}.
        {!inWindow && ' Renewal is not open right now.'}
      </p>
      <div role="group" aria-label="Choose your next plan" style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {PLANS.map(([code, name]) => (
          <button key={code} type="button" aria-pressed={plan === code} onClick={() => { setPlan(code); setStep('view'); setOutcome(null); }}
            style={{ padding: '9px 18px', borderRadius: 999, border: '1px solid rgba(53,26,78,0.25)', background: plan === code ? '#35194E' : 'transparent', color: plan === code ? '#fff' : '#35194E', fontWeight: 700, cursor: 'pointer' }}>{name}</button>
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', padding: '12px 0', borderTop: '1px solid rgba(53,26,78,0.1)', borderBottom: '1px solid rgba(53,26,78,0.1)' }}>
        <div>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 800, color: '#2B1740' }}>{q.new_plan} · {q.new_plan_term_months} months</p>
          <p style={{ margin: '2px 0 0', fontSize: 22, fontWeight: 800, color: '#2B1740' }}>{formatInrMinor(price)}</p>
        </div>
        {canRedeem && step === 'view' && (
          <button type="button" onClick={() => setStep('calc')} style={goldBtn(true)}>{mode === 'SIMULATION' ? 'Redeem Growth Points (simulation)' : 'Redeem Growth Points'}</button>
        )}
      </div>

      {!canRedeem && (
        <p role="status" style={{ margin: '12px 0 0', fontSize: 13, lineHeight: 1.55, color: 'rgba(43,23,64,0.75)' }}>
          {mode === 'PREVIEW' && 'Redeeming Growth Points is not available yet. '}
          {eligible === 0 ? (q.reason || 'You have no eligible Growth Points for this renewal. Points earned before redemption began can not be redeemed; points earned from then on, while your subscription is active, can.') : (!inWindow ? 'Renewal is not open right now.' : '')}
          {q.points_excluded_before_cutoff > 0 && ` (${pts(q.points_excluded_before_cutoff)} of your points were earned before redemption began and can never be redeemed.)`}
        </p>
      )}

      {step === 'calc' && canRedeem && (
        <div style={{ marginTop: 14 }}>
          <Row name="Eligible Growth Points available to redeem" value={`${pts(eligible)} points`} />
          <Row name="Most that can be applied to this invoice" value={`${pts(q.new_plan_redemption_ceiling_points)} points`} note={`15% of the ${q.new_plan} price · 10 points = ₹1`} />
          <Row name="Growth Points you will use" value={`${pts(points)} points`} />
          <Row name="Original subscription price" value={formatInrMinor(price)} />
          <Row name="Growth Points discount" value={`− ${formatInrMinor(q.hypothetical_discount_paise)}`} />
          <Row name="Points left after this renewal" value={pts(q.remaining_old_cycle_points)} note={q.remaining_old_cycle_points ? 'They expire when your renewal window closes.' : null} />
          <Row name="Final amount payable" value={formatInrMinor(q.hypothetical_amount_payable_paise)} strong />
          <p style={{ margin: '10px 0 0', fontSize: 12.5, lineHeight: 1.55, color: 'rgba(43,23,64,0.7)' }}>{q.explanation}</p>
          <div role="alertdialog" aria-label="Confirm" style={{ marginTop: 12, padding: 16, borderRadius: 14, background: 'rgba(107,62,150,0.08)' }}>
            <p style={{ margin: '0 0 10px', fontWeight: 800, color: '#2B1740' }}>
              {mode === 'SIMULATION' ? `SIMULATION: you would use ${pts(points)} Growth Points for a ${formatInrMinor(q.hypothetical_discount_paise)} subscription discount.` : `You are using ${pts(points)} Growth Points for a ${formatInrMinor(q.hypothetical_discount_paise)} subscription discount.`}
            </p>
            <button type="button" disabled={busy} onClick={mode === 'SIMULATION' ? simulate : confirmReal} style={darkBtn}>{busy ? 'Working…' : mode === 'SIMULATION' ? 'Run simulation' : 'Confirm redemption'}</button>{' '}
            <button type="button" disabled={busy} onClick={() => setStep('view')} style={{ border: 'none', background: 'none', textDecoration: 'underline', cursor: 'pointer', color: '#35194E' }}>Back</button>
          </div>
        </div>
      )}

      {step === 'done' && outcome?.kind === 'SIMULATION' && (
        <div role="status" style={{ marginTop: 14, padding: 16, borderRadius: 14, background: 'rgba(224,181,88,0.15)', border: '1px dashed #C08D2E' }}>
          <p style={{ margin: '0 0 6px', fontWeight: 800, color: '#2B1740' }}>SIMULATION COMPLETE: nothing was applied</p>
          <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: '#35194E' }}>
            The server ran the real calculation and rolled it back. It would have used {pts(outcome.res.points_would_be_used)} points for a {formatInrMinor(outcome.res.discount_minor)} discount, taking {formatInrMinor(outcome.res.plan_price_minor)} down to {formatInrMinor(outcome.res.amount_payable_minor)}.
            No points were used, no invoice was created and no payment changed. This is not a completed redemption.
          </p>
          <button type="button" onClick={() => setStep('view')} style={{ ...darkBtn, marginTop: 10 }}>Done</button>
        </div>
      )}

      {mode === 'REAL' && inWindow && step === 'view' && (
        <p style={{ margin: '14px 0 0', fontSize: 13 }}>
          <button type="button" disabled={busy} onClick={renewFullPrice} style={{ border: 'none', background: 'none', textDecoration: 'underline', cursor: 'pointer', color: '#35194E', fontSize: 13 }}>Renew at the full price without using Growth Points</button>
        </p>
      )}
      <p style={{ margin: '12px 0 0', fontSize: 12, lineHeight: 1.5, color: 'rgba(43,23,64,0.6)' }}>{q.terms}</p>
    </section>
  );
}
