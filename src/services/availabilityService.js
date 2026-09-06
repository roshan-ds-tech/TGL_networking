/* Public slot-availability counters.
 *
 * Feeds the "x of 40 filled" indicator on the Categories section and the
 * scarcity line in the urgency popup. Read-only and unauthenticated. */

const API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export async function fetchAvailability(signal) {
  const res = await fetch(`${API_BASE}/api/categories/availability`, { signal });
  if (!res.ok) throw new Error(`Availability request failed (${res.status})`);
  return res.json();
}
