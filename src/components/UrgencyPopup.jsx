import { useEffect, useState } from 'react';

const DISMISS_KEY = 'tgl-urgency-dismissed';
const SHOW_DELAY_MS = 6000;

export default function UrgencyPopup() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (sessionStorage.getItem(DISMISS_KEY)) return;
    const timer = setTimeout(() => setVisible(true), SHOW_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  const dismiss = () => {
    setVisible(false);
    sessionStorage.setItem(DISMISS_KEY, '1');
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Registration urgency notice"
      style={{
        position: 'fixed',
        right: '16px',
        bottom: '16px',
        zIndex: 200,
        width: 'min(360px, calc(100vw - 32px))',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '14px',
        padding: '20px 20px 20px 18px',
        borderRadius: '18px',
        background: 'linear-gradient(155deg, #2B1740, #22103A)',
        border: '1px solid rgba(224,181,88,0.4)',
        boxShadow: '0 24px 54px rgba(0,0,0,0.4)',
        color: '#F6EEDF',
        animation: 'tglRise .5s cubic-bezier(.2,.7,.3,1) both',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          flexShrink: 0,
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(150deg, #E0B558, #A8762F)',
          color: '#22103A',
          animation: 'tglGlow 2.4s ease-in-out infinite',
        }}
      >
        <svg width="19" height="19" viewBox="0 0 24 24" aria-hidden="true">
          <use href="#i-clock"></use>
        </svg>
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            margin: '0 0 5px',
            fontSize: '10.5px',
            letterSpacing: '.16em',
            textTransform: 'uppercase',
            fontWeight: '700',
            color: '#EFCB77',
          }}
        >
          Slots are filling fast
        </p>
        <p style={{ margin: '0 0 14px', fontSize: '14.5px', lineHeight: '1.55', color: 'rgba(246,238,223,0.85)' }}>
          Early-bird pricing won&rsquo;t last — hurry up and register now before your category fills up.
        </p>
        <a
          href="#register"
          onClick={dismiss}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            background: 'linear-gradient(135deg, #E0B558, #C08D2E)',
            color: '#22103A',
            fontWeight: '700',
            fontSize: '12px',
            letterSpacing: '.06em',
            textTransform: 'uppercase',
            padding: '10px 18px',
            borderRadius: '999px',
            textDecoration: 'none',
            transition: 'transform .2s ease, box-shadow .2s ease',
          }}
          className="urgency-cta"
        >
          Register Now
        </a>
      </div>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        style={{
          flexShrink: 0,
          width: '26px',
          height: '26px',
          borderRadius: '50%',
          border: '1px solid rgba(224,181,88,0.35)',
          background: 'rgba(255,255,255,0.06)',
          color: 'rgba(246,238,223,0.75)',
          fontSize: '15px',
          lineHeight: '1',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        &times;
      </button>
    </div>
  );
}
