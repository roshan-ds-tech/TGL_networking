import { useEffect, useState } from 'react';

// Every privileged admin action asks for a reason; it is stored in the audit log.
export default function ReasonModal({ title, sub, cta = 'Confirm', danger = false, optionalNote = false, onSubmit, onClose }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !busy) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onSubmit(reason.trim());
      onClose();
    } catch (err) {
      setError(err.message || 'That did not work.');
      setBusy(false);
    }
  }
  const ok = optionalNote || reason.trim().length >= 3;
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={busy ? undefined : onClose}>
      <form className="modal__card modal__card--sm" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <header className="modal__head"><div><h2 className="modal__title">{title}</h2>{sub && <p className="modal__sub">{sub}</p>}</div></header>
        <div className="modal__body modal__body--pad">
          <label className="field">
            <span className="field__label">Reason (kept in the audit log)</span>
            <textarea className="input" rows={3} maxLength={240} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
          </label>
          {error && <p className="alert" role="alert">{error}</p>}
        </div>
        <footer className="modal__foot">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`} disabled={!ok || busy}>{busy ? 'Saving…' : cta}</button>
        </footer>
      </form>
    </div>
  );
}
