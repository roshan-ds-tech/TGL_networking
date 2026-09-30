/* Small display helpers shared by the product-app screens. */

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

/** "3 days ago" / "2 weeks ago" — the posted-at stamp used on need cards. */
export function timeAgo(value) {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, Date.now() - then);
  if (diff < HOUR) return 'Just now';
  if (diff < DAY) return plural(Math.floor(diff / HOUR), 'hour');
  if (diff < WEEK) return plural(Math.floor(diff / DAY), 'day');
  if (diff < 5 * WEEK) return plural(Math.floor(diff / WEEK), 'week');
  return new Date(then).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Compact stamp for notification and referral rows: "2h", "3d", "1w". */
export function shortAgo(value) {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, Date.now() - then);
  if (diff < HOUR) return `${Math.max(1, Math.floor(diff / MINUTE))}m`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`;
  if (diff < WEEK) return `${Math.floor(diff / DAY)}d`;
  return `${Math.floor(diff / WEEK)}w`;
}

/** "18 Sep 2026" */
export function shortDate(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function plural(n, unit) {
  return `${n} ${unit}${n === 1 ? '' : 's'} ago`;
}

/* Trust Score is shown as a named tier and a five-segment bar rather than a
   number — it reflects relationship history, and a bare integer reads like a
   rating. Thresholds mirror the backend's scoring bands. */
export function trustTier(score = 0) {
  if (score >= 100) return { label: 'Trusted Leader', filled: 5 };
  if (score >= 50) return { label: 'Established', filled: 4 };
  if (score >= 20) return { label: 'Active', filled: 3 };
  if (score >= 1) return { label: 'Getting Started', filled: 2 };
  return { label: 'New Member', filled: 1 };
}
