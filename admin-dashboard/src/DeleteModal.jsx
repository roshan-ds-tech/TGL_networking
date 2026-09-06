import { useEffect, useRef, useState } from 'react';
import { CATEGORIES } from './api';

/* Confirmation gate for an irreversible delete.
 *
 * The row and its payment screenshot are erased for good, so this deliberately
 * costs a deliberate action: the confirm button is focused but the dialog shows
 * exactly which business is about to go, and Escape / clicking away cancels. */
export default function DeleteModal({ registration, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const cancelRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && !busy) onClose();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    // Focus the safe action, not the destructive one.
    cancelRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose, busy]);

  async function handleConfirm() {
    setBusy(true);
    setError('');
    try {
      await onConfirm();
    } catch (err) {
      setError(err.message || 'Could not delete this registration.');
      setBusy(false);
    }
  }

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm deletion"
      onClick={busy ? undefined : onClose}
    >
      <div className="modal__card modal__card--sm" onClick={(e) => e.stopPropagation()}>
        <header className="modal__head">
          <div>
            <h2 className="modal__title">Delete this registration?</h2>
            <p className="modal__sub">This cannot be undone.</p>
          </div>
        </header>

        <div className="modal__body modal__body--pad">
          <dl className="confirm">
            <div className="confirm__row">
              <dt>Business</dt>
              <dd>{registration.business_name}</dd>
            </div>
            <div className="confirm__row">
              <dt>Contact</dt>
              <dd>
                {registration.full_name} · {registration.email}
              </dd>
            </div>
            <div className="confirm__row">
              <dt>Category</dt>
              <dd>
                {registration.category} · {CATEGORIES[registration.category] || '—'}
              </dd>
            </div>
          </dl>

          <p className="confirm__warn">
            The registration row <strong>and its payment screenshot</strong> will be
            permanently deleted.
            {registration.verified && ' This payment has already been verified.'}
          </p>

          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
        </div>

        <footer className="modal__foot">
          <button
            type="button"
            ref={cancelRef}
            className="btn btn--ghost"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button type="button" className="btn btn--danger" onClick={handleConfirm} disabled={busy}>
            {busy ? 'Deleting…' : 'Delete permanently'}
          </button>
        </footer>
      </div>
    </div>
  );
}
