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
/* Swallowing the error keeps the page working, but it also means a broken
   counter looks identical to a genuinely empty one. Leave a breadcrumb so the
   cause is visible in DevTools — by far the most likely one is the site being
   served from a domain that is missing from the backend's PUBLIC_ORIGIN
   allowlist, which the browser reports as a CORS failure. */
function warnUnavailable(err) {
  if (err?.name === 'AbortError') return; // expected when the component unmounts
  console.warn(
    '[TGL] Slot availability could not be loaded; showing static copy instead. ' +
      "If this domain is new, check it is listed in the backend's PUBLIC_ORIGIN.",
    err,
  );
}

export default function useAvailability() {
  const [data, setData] = useState(null);

  const refresh = useCallback(() => {
    fetchAvailability().then(setData).catch(warnUnavailable);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchAvailability(controller.signal)
      .then(setData)
      .catch(warnUnavailable);
    return () => controller.abort();
  }, []);

  return [data, refresh];
}
