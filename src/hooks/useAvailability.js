import { useEffect, useState } from 'react';
import { fetchAvailability } from '../services/availabilityService';

/* Fetches the public slot counters once per page load.
 *
 * Called in App and passed down, so the Categories grid and the urgency popup
 * share a single request. Failure is non-fatal by design: `data` stays null and
 * both consumers fall back to their static copy rather than showing an error —
 * a marketing page should never break because a counter is unavailable. */
export default function useAvailability() {
  const [data, setData] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchAvailability(controller.signal)
      .then(setData)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  return data;
}
