import { useCallback, useEffect, useState } from 'react';
import { api } from './customerApi';
import { getCurrentUserId } from './authHint';

/* Who is connected to whom.

   The API returns every connection row the signed-in member is part of. A row
   is (requester -> target, status): ACCEPTED means the two are connected;
   PENDING/DECLINED is a request the target has not accepted. `DECLINED` is the
   target setting it aside; the requester is not told, so for them it still
   reads as "requested". */

const EVENT = 'tgl:connections-changed';

/** Call after anything that changes a connection so every list refreshes. */
export const connectionsChanged = () => window.dispatchEvent(new Event(EVENT));

/** The relationship between me and one other member, from the rows. */
export function relationWith(rows, myId, otherId) {
  let sent = null;
  let received = null;
  for (const c of rows) {
    const mineOut = c.requester_user_id === myId && c.target_user_id === otherId;
    const mineIn = c.requester_user_id === otherId && c.target_user_id === myId;
    if (!mineOut && !mineIn) continue;
    if (c.status === 'ACCEPTED') return { kind: 'connected', id: c.id };
    if (mineOut) sent = c;
    else if (c.status === 'PENDING') received = c;
  }
  if (sent) return { kind: 'sent', id: sent.id };
  if (received) return { kind: 'received', id: received.id, note: received.note, createdAt: received.created_at };
  return { kind: 'none' };
}

export function useConnections() {
  const [rows, setRows] = useState(null);
  const load = useCallback(() => (
    api.listConnections().then(setRows).catch(() => setRows((prev) => prev ?? []))
  ), []);

  useEffect(() => {
    load();
    window.addEventListener(EVENT, load);
    return () => window.removeEventListener(EVENT, load);
  }, [load]);

  const myId = getCurrentUserId();
  const all = rows || [];
  const seen = new Set();
  const connected = all.filter((c) => {
    if (c.status !== 'ACCEPTED') return false;
    const other = c.requester_user_id === myId ? c.target_user_id : c.requester_user_id;
    if (seen.has(other)) return false; // an old crossed request can leave a row each way
    seen.add(other);
    return true;
  });
  return {
    loaded: rows !== null,
    reload: load,
    // Until the rows arrive nothing is known: say so, never claim "not connected".
    relation: (otherId) => (rows === null ? { kind: 'loading' } : relationWith(all, myId, otherId)),
    connected,
    invitations: all.filter((c) => c.target_user_id === myId && c.status === 'PENDING'),
    sent: all.filter((c) => c.requester_user_id === myId && c.status !== 'ACCEPTED'),
    otherOf: (c) => (c.requester_user_id === myId ? c.target_user_id : c.requester_user_id),
  };
}
