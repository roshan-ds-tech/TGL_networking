import { useEffect, useState } from 'react';
import { api } from '../../lib/customerApi';
import { showToast } from '../../components/AppShell';
import { formatInrMinor, rupeeInputText } from '../../lib/format';

/* Two-party meeting confirmation and the verified closed-business record.
   The server decides every state; this only shows it and sends the member's intent. */

// The thresholds are configuration on the server (awaiting management confirmation), never hard-coded here.
let rulesPromise = null;
const loadRules = () => (rulesPromise ||= api.dealRules().catch(() => { rulesPromise = null; return null; }));
const bandNote = (r) => (r
  ? `Evidence (an invoice or payment proof) is needed for deals of ${formatInrMinor(r.evidence_from_minor)} and above, and TGL reviews deals of ${formatInrMinor(r.admin_approval_from_minor)} and above.`
  : 'Evidence (an invoice or payment proof) may be needed for larger deals.');

const inr = formatInrMinor;

function useRules() {
  const [rules, setRules] = useState(null);
  useEffect(() => {
    let live = true;
    loadRules().then((r) => live && setRules(r));
    return () => { live = false; };
  }, []);
  return rules;
}

function Icon({ id, size = 14 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function ReasonDialog({ title, label, cta, onSubmit, onClose }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try { await onSubmit(reason.trim()); onClose(); } catch (err) { showToast(err.message || 'Something went wrong.'); setBusy(false); }
  }
  return (
    <div className="rf-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <form className="rf-modal rv-small" role="dialog" aria-modal="true" aria-labelledby="rv-reason-title" onSubmit={submit}>
        <header className="rf-modal-head"><h2 id="rv-reason-title">{title}</h2><button type="button" className="rf-x" onClick={onClose} aria-label="Close"><Icon id="i-x" size={16} /></button></header>
        <div className="rf-field">
          <label htmlFor="rv-reason">{label}</label>
          <textarea id="rv-reason" rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </div>
        <footer className="rf-modal-foot rv-foot">
          <button type="button" className="rf-btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="rf-btn rf-btn--dark" disabled={busy || reason.trim().length < 5}>{busy ? 'Sending…' : cta}</button>
        </footer>
      </form>
    </div>
  );
}

function ClosureDialog({ initial, onSubmit, onClose }) {
  const [value, setValue] = useState(initial ? rupeeInputText(initial.actual_value_minor) : '');
  const [note, setNote] = useState(initial?.note || '');
  const [busy, setBusy] = useState(false);
  const rules = useRules();
  const text = value.trim();
  const rupees = Number(text);
  // Whole rupees or up to two decimals; the server parses the text exactly (never a float).
  const valid = /^\d{1,10}(\.\d{1,2})?$/.test(text) && rupees >= 1 && rupees <= 1_000_000_000;
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try { await onSubmit({ actual_value: text, note: note.trim() || undefined }); onClose(); } catch (err) { showToast(err.message || 'Could not save.'); setBusy(false); }
  }
  return (
    <div className="rf-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <form className="rf-modal rv-small" role="dialog" aria-modal="true" aria-labelledby="rv-closure-title" onSubmit={submit}>
        <header className="rf-modal-head">
          <div><h2 id="rv-closure-title">{initial ? 'Correct the closed business' : 'Report closed business'}</h2><p>Enter what the business was actually worth. The other member must confirm it.</p></div>
          <button type="button" className="rf-x" onClick={onClose} aria-label="Close"><Icon id="i-x" size={16} /></button>
        </header>
        <div className="rf-field">
          <label htmlFor="rv-value">Actual value (₹)</label>
          <div className="rf-input"><span aria-hidden="true">₹</span><input id="rv-value" type="number" inputMode="decimal" min="1" step="0.01" value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. 375000" autoFocus /></div>
          {valid && <small className="rf-hint">{inr(Math.round(rupees * 100))}. {rules ? (Math.round(rupees * 100) >= rules.evidence_from_minor ? bandNote(rules) : `No evidence is needed for a deal below ${formatInrMinor(rules.evidence_from_minor)}.`) : ''}</small>}
          {!valid && value !== '' && <small className="rf-err">Enter the actual value in rupees.</small>}
        </div>
        <div className="rf-field">
          <label htmlFor="rv-note">Note <em>Optional</em></label>
          <textarea id="rv-note" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What was agreed?" />
        </div>
        <p className="rf-hint">The estimate on the original referral stays as it is; this is recorded separately as the actual outcome.</p>
        <footer className="rf-modal-foot rv-foot">
          <button type="button" className="rf-btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className="rf-btn rf-btn--primary" disabled={busy || !valid}>{busy ? 'Saving…' : initial ? 'Save value' : 'Report closed business'}</button>
        </footer>
      </form>
    </div>
  );
}

function Evidence({ r, closure, onChanged }) {
  const [file, setFile] = useState(null);
  const [type, setType] = useState('INVOICE');
  const [busy, setBusy] = useState(false);
  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      await api.addEvidence(r.id, { evidenceType: type, file });
      setFile(null);
      showToast('Evidence uploaded for review.');
      await onChanged();
    } catch (err) {
      showToast(err.message || 'Could not upload the file.');
    } finally { setBusy(false); }
  }
  return (
    <div className="rv-evidence">
      {closure.evidence.length > 0 && (
        <ul className="rv-evlist">
          {closure.evidence.map((e) => (
            <li key={e.id}>
              <span className={`rv-pill rv-pill--${e.status.toLowerCase()}`}>{e.status === 'PENDING' ? 'In review' : e.status === 'VERIFIED' ? 'Verified' : 'Not accepted'}</span>
              <a href={api.evidenceUrl(r.id, e.id)} target="_blank" rel="noopener noreferrer">{e.evidence_type.replace('_', ' ').toLowerCase()}</a>
              {e.rejection_reason && <small>{e.rejection_reason}</small>}
            </li>
          ))}
        </ul>
      )}
      {closure.can_add_evidence && (
        <form className="rv-upload" onSubmit={upload}>
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Evidence type">
            <option value="INVOICE">Invoice</option>
            <option value="PAYMENT_PROOF">Payment proof</option>
            <option value="OTHER">Other document</option>
          </select>
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif,application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} aria-label="Evidence file" />
          <button type="submit" className="rf-btn" disabled={!file || busy}>{busy ? 'Uploading…' : 'Upload'}</button>
        </form>
      )}
    </div>
  );
}

export default function VerificationStrip({ r, onChanged }) {
  const rules = useRules();
  const [dialog, setDialog] = useState(null); // 'report' | 'edit' | 'dispute-meeting' | 'dispute-closure'
  const [busy, setBusy] = useState(false);
  const other = ((r.my_role === 'receiver' ? r.giver_name : r.receiver_name) || 'the other member').split(' ')[0];
  const meeting = r.meeting;
  const closure = r.closure;
  const showMeeting = meeting && meeting.state !== 'NOT_AVAILABLE';
  const canReport = r.status === 'MEETING_DONE' && meeting?.state === 'CONFIRMED_BY_BOTH' && r.my_role === 'receiver' && !closure;
  if (!showMeeting && !closure && !canReport) return null;

  async function run(fn, ok) {
    setBusy(true);
    try { await fn(); if (ok) showToast(ok); await onChanged(); } catch (err) { showToast(err.message || 'Something went wrong. Please try again.'); await onChanged().catch(() => {}); } finally { setBusy(false); }
  }

  return (
    <div className="rv">
      {showMeeting && (
        <div className="rv-row">
          <span className="rv-label"><Icon id="i-calendar" /> Meeting</span>
          {meeting.state === 'WAITING_FOR_YOU' && (<>
            <span className="rv-state rv-state--you">Waiting for your confirmation</span>
            <button type="button" className="rf-btn rf-btn--dark" disabled={busy} onClick={() => run(() => api.confirmMeeting(r.id), 'Meeting confirmed.')}>Confirm we met</button>
          </>)}
          {meeting.state === 'WAITING_FOR_OTHER' && (<>
            <span className="rv-state">You confirmed. Waiting for {other}</span>
            <button type="button" className="rf-link-btn" disabled={busy} onClick={() => run(() => api.withdrawMeeting(r.id), 'Confirmation withdrawn.')}>Withdraw</button>
          </>)}
          {meeting.state === 'NOT_VERIFIED' && (
            <span className="rv-state">Recorded before meetings needed both members. TGL will ask you both to confirm it again.</span>
          )}
          {meeting.state === 'CONFIRMED_BY_BOTH' && (<>
            <span className="rv-state rv-state--ok"><Icon id="i-check" /> Confirmed by both</span>
            <button type="button" className="rf-link-btn" onClick={() => setDialog('dispute-meeting')}>Report a problem</button>
          </>)}
        </div>
      )}

      {canReport && (
        <div className="rv-row">
          <span className="rv-label"><Icon id="i-briefcase" /> Business</span>
          <span className="rv-state">Did this turn into business?</span>
          <button type="button" className="rf-btn rf-btn--primary" onClick={() => setDialog('report')}>Report closed business</button>
        </div>
      )}

      {closure && (
        <div className="rv-closure">
          <div className="rv-row">
            <span className="rv-label"><Icon id="i-briefcase" /> Business</span>
            <strong className="rv-amount">{inr(closure.actual_value_minor)}</strong>
            <span className="rv-meta">{closure.value_band_label}</span>
            <span className={`rv-pill rv-pill--${closure.status.toLowerCase()}`}>{closure.status_label}</span>
          </div>
          <p className="rv-level">{closure.verification_label}{closure.note ? ` · ${closure.note}` : ''}</p>
          {closure.status === 'AWAITING_CONFIRMATION' && closure.can_confirm && (
            <div className="rv-row">
              <span className="rv-state rv-state--you">{other} reported this. Is it right?</span>
              <button type="button" className="rf-btn rf-btn--dark" disabled={busy} onClick={() => run(() => api.confirmClosure(r.id, closure.actual_value_minor), 'Confirmed. Thank you.')}>Confirm</button>
            </div>
          )}
          {closure.status === 'AWAITING_CONFIRMATION' && closure.reported_by_you && (
            <div className="rv-row">
              <span className="rv-state">Waiting for {other} to confirm</span>
              <button type="button" className="rf-link-btn" onClick={() => setDialog('edit')}>Correct value</button>
              <button type="button" className="rf-link-btn" disabled={busy} onClick={() => run(() => api.cancelClosure(r.id), 'Report cancelled.')}>Cancel report</button>
            </div>
          )}
          {(closure.status === 'AWAITING_EVIDENCE' || closure.status === 'UNDER_REVIEW') && (
            <>
              <p className="rv-help">{closure.status === 'AWAITING_EVIDENCE' ? `Both of you confirmed this. Please add supporting evidence so TGL can verify it. ${bandNote(rules)}` : 'TGL is reviewing the evidence. You will be notified.'}</p>
              <Evidence r={r} closure={closure} onChanged={onChanged} />
            </>
          )}
          {closure.status === 'DISPUTED' && <p className="rv-help">This was disputed and is with TGL for review.{closure.dispute_reason ? ` Reason: ${closure.dispute_reason}` : ''}</p>}
          {closure.can_dispute && closure.status !== 'DISPUTED' && (
            <button type="button" className="rf-link-btn rv-dispute" onClick={() => setDialog('dispute-closure')}>This is not right</button>
          )}
        </div>
      )}

      {dialog === 'report' && <ClosureDialog onClose={() => setDialog(null)} onSubmit={async (p) => { await api.reportClosure(r.id, p); showToast('Reported. We have asked the other member to confirm.'); await onChanged(); }} />}
      {dialog === 'edit' && <ClosureDialog initial={closure} onClose={() => setDialog(null)} onSubmit={async (p) => { await api.editClosure(r.id, p); showToast('Value updated.'); await onChanged(); }} />}
      {dialog === 'dispute-meeting' && <ReasonDialog title="Report a problem with the meeting" label="What was wrong?" cta="Send to TGL" onClose={() => setDialog(null)} onSubmit={async (reason) => { await api.disputeMeeting(r.id, reason); showToast('Thanks. TGL will look into it.'); await onChanged(); }} />}
      {dialog === 'dispute-closure' && <ReasonDialog title="Dispute the closed business" label="What is not right?" cta="Send to TGL" onClose={() => setDialog(null)} onSubmit={async (reason) => { await api.disputeClosure(r.id, reason); showToast('Disputed. TGL will review it.'); await onChanged(); }} />}
    </div>
  );
}
