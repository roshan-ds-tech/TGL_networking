import { useState } from 'react';
import { api } from '../lib/customerApi';
import { connectionsChanged } from '../lib/connections';
import { openConnectModal, showToast } from './AppShell';

function Icon({ id, size = 13 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

/* The one connect control, in every state a pair can be in:
     none      -> Connect (opens the request dialog)
     sent      -> Requested (waiting on them)
     received  -> Accept / Ignore (they asked you)
     connected -> Connected
   `prefix` picks the page's button styles (nh / nd / rf-style classes). */
export default function ConnectionButton({ relation, userId, name, businessName, prefix = 'nd', extra = '' }) {
  const [busy, setBusy] = useState(false);
  const base = `${prefix}-btn ${extra}`.trim();

  async function respond(action) {
    setBusy(true);
    try {
      await api.respondConnection(relation.id, action);
      showToast(action === 'accept' ? `You're now connected with ${name}.` : 'Request ignored.');
    } catch (err) {
      showToast(err.message || 'Could not update this request.');
    } finally {
      setBusy(false);
      connectionsChanged(); // refresh either way: the request may have changed under us
    }
  }

  if (relation.kind === 'connected') {
    return <span className={`${base} is-done`} aria-label={`Connected with ${name}`}><Icon id="i-check" /> Connected</span>;
  }
  if (relation.kind === 'sent') {
    return <button type="button" className={`${base} is-done`} disabled><Icon id="i-check" /> Requested</button>;
  }
  if (relation.kind === 'received') {
    return (
      <span className="cx-pair">
        <button type="button" className={`${base} ${prefix}-btn--dark`} disabled={busy} onClick={() => respond('accept')}>{busy ? '…' : 'Accept'}</button>
        <button type="button" className={base} disabled={busy} onClick={() => respond('decline')}>Ignore</button>
      </span>
    );
  }
  return (
    <button type="button" className={`${base} ${prefix}-btn--dark`} onClick={() => openConnectModal(businessName || name, userId)}>Connect</button>
  );
}
