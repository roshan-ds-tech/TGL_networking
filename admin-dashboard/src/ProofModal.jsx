import { useEffect } from 'react';
import { api, CATEGORIES } from './api';

/* The proof endpoint requires the session cookie. Because the dashboard is
 * served same-origin by the API, a plain <img src> / <iframe src> carries the
 * cookie automatically — no blob juggling and no token in the URL. */
function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProofModal({ registration, onClose }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  const url = api.proofUrl(registration.id);
  const isPdf = registration.proof_mime === 'application/pdf';

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-label="Payment proof"
      onClick={onClose}
    >
      <div className="modal__card" onClick={(e) => e.stopPropagation()}>
        <header className="modal__head">
          <div>
            <h2 className="modal__title">{registration.business_name}</h2>
            <p className="modal__sub">
              {registration.full_name} · {registration.category} ·{' '}
              {CATEGORIES[registration.category] || ''}
            </p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal__body">
          {isPdf ? (
            <iframe className="modal__pdf" src={url} title="Payment proof (PDF)" />
          ) : (
            <img className="modal__img" src={url} alt="Payment proof" />
          )}
        </div>

        <footer className="modal__foot">
          <span className="cell__sub">
            {registration.proof_mime} · {formatBytes(registration.proof_bytes)}
          </span>
          <a className="btn btn--link" href={url} target="_blank" rel="noreferrer noopener">
            Open full size
          </a>
        </footer>
      </div>
    </div>
  );
}
