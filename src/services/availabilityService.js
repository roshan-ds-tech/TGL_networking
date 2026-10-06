/* Public slot-availability counters.
 *
 * Feeds the "x of 40 filled" indicator on the Categories section and the
 * scarcity line in the urgency popup. Read-only and unauthenticated. */

import { API_BASE, WAKING_STATUSES, markAwake, markMaybeAsleep, wakeBackend } from '../lib/apiBase';

export async function fetchAvailability(signal) {
  const get = () => fetch(`${API_BASE}/api/categories/availability`, { signal });
  let res;
  try {
    res = await get();
  } catch (err) {
    if (signal?.aborted) throw err;
    res = null;
  }
  // Backend asleep: wait for it to start, then read again (reads are safe to repeat).
  if (res === null || WAKING_STATUSES.has(res.status)) {
    markMaybeAsleep();
    if (!(await wakeBackend())) throw new Error('Availability unavailable: backend not reachable');
    res = await get();
  }
  if (!res.ok) throw new Error(`Availability request failed (${res.status})`);
  markAwake();
  return res.json();
}
