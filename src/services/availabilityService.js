/* Public slot-availability counters.
 *
 * Feeds the "x of 40 filled" indicator on the Categories section and the
 * scarcity line in the urgency popup. Read-only and unauthenticated. */

import { API_BASE } from '../lib/apiBase';

export async function fetchAvailability(signal) {
  const res = await fetch(`${API_BASE}/api/categories/availability`, { signal });
  if (!res.ok) throw new Error(`Availability request failed (${res.status})`);
  return res.json();
}
