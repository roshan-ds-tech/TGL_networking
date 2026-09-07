import { useCallback, useEffect, useState } from 'react';
import { fetchAvailability } from '../services/availabilityService';

/* Fetches the public slot counters once per page load, with a manual refresh.
 *
 * Called in App and passed down, so the Categories grid, the registration
 * form and the urgency popup share a single request. Failure is non-fatal by
 * design: `data` stays null and consumers fall back to their static copy
 * rather than showing an error — a marketing page should never break because
 * a counter is unavailable. `refresh` is exposed so the form can pull fresh
 * counts right after the server rejects a submission for a category that
 * just filled up. */
export default function useAvailability() {
  const [data, setData] = useState(null);

  const refresh = useCallback(() => {
    fetchAvailability().then(setData).catch(() => {});
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchAvailability(controller.signal)
      .then(setData)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  return [data, refresh];
}
