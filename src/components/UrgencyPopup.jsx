import { useEffect, useState } from 'react';

const SHOW_DELAY_MS = 3500;

/* Shows on every page load by design — dismissing it only hides it for the
 * current view, it is not persisted. */
export default function UrgencyPopup({ availability, deadline }) {
  const [visible, setVisible] = useState(false);
  const [closing, setClosing] = useState(false);
  const [remaining, setRemaining] = useState(() => splitRemaining(deadline));

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), SHOW_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!visible) return undefined;
    const id = setInterval(() => setRemaining(splitRemaining(deadline)), 1000);
    return () => clearInterval(id);
  }, [visible, deadline]);

  // Let the exit animation finish before unmounting.
  const dismiss = () => {
    setClosing(true);
    setTimeout(() => setVisible(false), 260);
  };

  if (!visible) return null;

  const filled = availability?.total_filled ?? null;
  const capacity = availability?.total_capacity ?? null;
  const left = filled !== null ? Math.max(0, capacity - filled) : null;
  const pct = filled !== null && capacity ? Math.min(100, (filled / capacity) * 100) : 0;

  return (
    <aside
      role="complementary"
      aria-label="Registration availability"
      className="urgency"
      data-closing={closing ? '' : undefined}
    >
      <span aria-hidden="true" className="urgency__hairline" />

      <div className="urgency__head">
        <span className="urgency__eyebrow">
          <span aria-hidden="true" className="urgency__dot" />
          Season 1 · Registrations open
        </span>
        <button type="button" onClick={dismiss} aria-label="Dismiss" className="urgency__close">
          <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
            <path
              d="M1 1l10 10M11 1L1 11"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {left !== null ? (
        <>
          <p className="urgency__title">
            <strong>{left}</strong> {left === 1 ? 'slot' : 'slots'} still open
          </p>
          <p className="urgency__sub">
            Across all 10 categories. Early-bird pricing closes as each category fills.
          </p>
          <div className="urgency__meter" aria-hidden="true">
            <span className="urgency__meter-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="urgency__count">
            <span>{filled} claimed</span>
            <span>{capacity} total</span>
          </p>
        </>
      ) : (
        <>
          <p className="urgency__title">Slots are filling up</p>
          <p className="urgency__sub">
            40 slots per category, 10 categories. Secure yours before your category closes.
          </p>
        </>
      )}

      {remaining && (
        <div className="urgency__deadline">
          <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true">
            <use href="#i-clock" />
          </svg>
          <span>
            Closes in
            <strong>
              {' '}
              {remaining.days}d {pad(remaining.hours)}h {pad(remaining.minutes)}m
            </strong>
          </span>
        </div>
      )}

      <div className="urgency__actions">
        <a href="#register" onClick={dismiss} className="urgency__cta">
          Register now
          <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
            <use href="#i-arrow" />
          </svg>
        </a>
        <button type="button" onClick={dismiss} className="urgency__later">
          Not now
        </button>
      </div>
    </aside>
  );
}

function pad(n) {
  return n < 10 ? `0${n}` : String(n);
}

function splitRemaining(deadline) {
  if (!deadline) return null;
  const ms = deadline - new Date();
  if (ms <= 0) return null;
  const total = Math.floor(ms / 1000);
  return {
    days: Math.floor(total / 86400),
    hours: Math.floor(total / 3600) % 24,
    minutes: Math.floor(total / 60) % 60,
  };
}
