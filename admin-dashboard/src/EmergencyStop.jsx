import { useEffect, useState } from 'react';
import { api } from './api';

// Emergency Stop & Reset Redemption. Blocks NEW Growth Points redemptions on every instance at once. It deletes nothing and reverses nothing:
// points, ledgers, redemptions, invoices, payments, subscriptions and the cutoff stay exactly as they are. The server checks the admin session,
// the CSRF token, the typed phrase and the reason; this screen only collects them and shows what the server says.
// Lifting the stop is a separate action (programme owners only, its own phrase); it opens nothing by itself, every other gate still applies.

const when = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

function ConfirmDialog({ title, sub, phrase, cta, danger, onConfirm, onClose }) {
  const [reason, setReason] = useState('');
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);
  const ok = reason.trim().length >= 10 && typed.trim() === phrase;
  async function submit(e) {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      await onConfirm({ reason: reason.trim(), confirm: typed.trim() });
      onClose();
    } catch (err) {
      setError(err.message || 'That did not work. Nothing was changed.');
      setBusy(false);
    }
  }
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="es-title" onClick={busy ? undefined : onClose}>
      <form className="modal__card modal__card--sm" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <header className="modal__head"><div><h2 className="modal__title" id="es-title">{title}</h2><p className="modal__sub">{sub}</p></div></header>
        <div className="modal__body modal__body--pad">
          <label className="field">
            <span className="field__label">Reason (at least 10 characters, kept in the audit log)</span>
            <textarea className="input" rows={3} maxLength={240} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
          </label>
          <label className="field" style={{ marginTop: 12 }}>
            <span className="field__label">Type <strong>{phrase}</strong> to confirm</span>
            <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} aria-describedby="es-phrase-hint" />
          </label>
          <p id="es-phrase-hint" className="cell__sub" style={{ marginTop: 6 }}>The button stays disabled until the phrase matches exactly.</p>
          {error && <p className="alert" role="alert">{error}</p>}
        </div>
        <footer className="modal__foot">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`} disabled={!ok || busy}>{busy ? 'Working…' : cta}</button>
        </footer>
      </form>
    </div>
  );
}

export default function EmergencyStop({ guard }) {
  const [st, setSt] = useState(null);
  const [dialog, setDialog] = useState(null); // null | 'stop' | 'resume'
  const [result, setResult] = useState(null); // { ok, text }
  const load = () => api.gpRedemptionState().then(setSt).catch((e) => guard(e, 'Could not load the redemption state.'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);
  if (!st) return <p className="cell__sub">Loading…</p>;

  async function stop(body) {
    const res = await api.gpKill(body);
    await load(); // show what the server now holds, never a local assumption
    setResult({ ok: true, text: res.already_stopped ? 'Redemption was already stopped. It stays stopped; your attempt is in the audit log.' : 'Redemption is now STOPPED for every member. Nothing was deleted or reversed.' });
  }
  async function resume(body) {
    const res = await api.gpResume(body);
    await load();
    setResult({ ok: true, text: res.already_resumed ? 'The stop was not on.' : 'The emergency stop is lifted. Redemption opens only if every other gate is also open.' });
  }

  return (
    <section className="gpx-card" aria-labelledby="es-heading" style={{ borderColor: st.kill_switch_on ? 'var(--danger, #b3261e)' : undefined }}>
      <h3 id="es-heading">Emergency Stop &amp; Reset Redemption</h3>
      <p className="cell__sub gp-hint">
        Blocks every NEW Growth Points redemption immediately, on every server, with no restart. Members keep all their points. Invoices, payments,
        subscriptions, past redemptions and history are not changed, deleted or reversed. Any admin can stop; lifting the stop is a separate action for programme owners.
      </p>
      <dl className="gp-facts">
        <div><dt>Redemption right now</dt><dd className={st.kill_switch_on ? 'gp-no' : st.flag_enabled ? 'gp-yes' : 'gp-no'}>{st.kill_switch_on ? 'STOPPED (emergency stop)' : st.flag_enabled ? 'Switch on (other gates still apply)' : 'Off (switch not on)'}</dd></div>
        <div><dt>Last stopped</dt><dd>{st.last_stop ? `${when(st.last_stop.at)} by ${st.last_stop.by || 'unknown admin'}` : 'Never'}</dd></div>
        {st.last_stop && <div><dt>Reason</dt><dd>{st.last_stop.reason}</dd></div>}
      </dl>
      {result && <p role="status" className={result.ok ? 'gp-note' : 'alert'} style={{ marginTop: 10 }}>{result.text}</p>}
      <div className="gpx-actions" style={{ marginTop: 14, marginBottom: 0 }}>
        <button type="button" className="btn btn--danger" onClick={() => { setResult(null); setDialog('stop'); }}>Emergency Stop &amp; Reset Redemption</button>
        {st.kill_switch_on && <button type="button" className="btn btn--ghost" onClick={() => { setResult(null); setDialog('resume'); }}>Lift the stop…</button>}
      </div>
      <details style={{ marginTop: 14 }}>
        <summary>Stop and resume history ({st.history.length})</summary>
        {st.history.length === 0 ? <p className="cell__sub">Never used.</p> : (
          <table className="gpx-mini">
            <thead><tr><th>When</th><th>Action</th><th>By</th><th>Reason</th></tr></thead>
            <tbody>{st.history.map((h) => <tr key={`${h.at}-${h.action}`}><td>{when(h.at)}</td><td>{h.action}</td><td>{h.by || '—'}</td><td>{h.reason}</td></tr>)}</tbody>
          </table>
        )}
      </details>
      {dialog === 'stop' && (
        <ConfirmDialog title="Emergency Stop & Reset Redemption" phrase={st.stop_phrase} cta="Stop all redemptions" danger
          sub="New redemptions will be refused for every member until a programme owner lifts the stop. Members keep their points; nothing already invoiced or paid changes."
          onConfirm={stop} onClose={() => setDialog(null)} />
      )}
      {dialog === 'resume' && (
        <ConfirmDialog title="Lift the emergency stop" phrase={st.resume_phrase} cta="Lift the stop"
          sub="Programme owners only. This does not switch redemption on by itself: the switch, every approval, Gate A, the rollout stage and the cutoff are still checked."
          onConfirm={resume} onClose={() => setDialog(null)} />
      )}
    </section>
  );
}
