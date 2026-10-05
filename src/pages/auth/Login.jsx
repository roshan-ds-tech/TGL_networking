import { useEffect, useRef, useState } from 'react';
import { ApiError, api, go, nextParam } from '../../lib/customerApi';
import { Eyebrow } from '../../components/AppShell';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const FEATURES = [
  { icon: 'i-compass', color: '#A8762F', bg: 'rgba(192,141,46,0.12)', title: 'Vertex', desc: 'Open B2B discovery — find the right service and provider.' },
  { icon: 'i-network', color: '#6B3E96', bg: 'rgba(107,62,150,0.1)', title: 'Networking', desc: 'The members-only TGL business community.' },
  { icon: 'i-calendar', color: '#35194E', bg: 'rgba(53,26,78,0.07)', title: 'Events', desc: 'Season 1 registration, evaluation and the Grand Finale.' },
];

// Segmented control in the sign-in card. Selected reads as a raised ivory
// chip on the ivory track rather than a gold fill — it is a mode switch, not
// the call to action.
function pill(on) {
  return {
    background: on ? '#FFFCF5' : 'transparent',
    color: on ? '#2B1740' : 'rgba(43,23,64,0.7)',
    boxShadow: on ? '0 4px 12px -6px rgba(53,26,78,0.35)' : 'none',
  };
}

const LABEL = { display: 'block', fontSize: 10.5, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)', marginBottom: 8 };

function OtpBoxes({ value, onChange }) {
  const refs = useRef([]);

  function setDigit(i, digit) {
    const next = value.padEnd(6, ' ').split('');
    next[i] = digit || ' ';
    onChange(next.join('').replace(/\s+$/, ''));
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 8, marginBottom: 10 }}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el; }}
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={1}
          aria-label={`Digit ${i + 1}`}
          value={value[i]?.trim() || ''}
          onChange={(e) => {
            const digit = e.target.value.replace(/\D/g, '').slice(-1);
            setDigit(i, digit);
            if (digit && i < 5) refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && !value[i]?.trim() && i > 0) refs.current[i - 1]?.focus();
          }}
          onPaste={(e) => {
            const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
            if (!pasted) return;
            e.preventDefault();
            onChange(pasted);
            refs.current[Math.min(pasted.length, 5)]?.focus();
          }}
          style={{ width: '100%', height: 52, textAlign: 'center', border: '1px solid rgba(53,26,78,0.16)', borderRadius: 12, fontSize: 20, fontWeight: 700, background: '#FFFBF3', color: '#2B1740', outline: 'none' }}
        />
      ))}
    </div>
  );
}

export default function Login() {
  const [mode, setMode] = useState('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [otpRequested, setOtpRequested] = useState(false);
  const [otpCooldown, setOtpCooldown] = useState(0);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  // Where to go once signed in: the page that sent them here (?next=, set by
  // the ProductApp auth guard), else Vertex — the product's landing surface.
  const destination = () => nextParam() || '/app/vertex';

  // Already signed in (bookmark, Back button, typed URL) — skip the form.
  useEffect(() => {
    let cancelled = false;
    api.session()
      .then((s) => { if (!cancelled && s?.authenticated) go(destination(), { replace: true }); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  function switchMode(next) {
    setMode(next);
    setError('');
    setFieldErrors({});
  }

  async function submitPassword(ev) {
    ev.preventDefault();
    const errs = {};
    if (!EMAIL_RE.test(email.trim())) errs.email = 'Enter a valid email address.';
    if (password.length < 1) errs.password = 'Enter your password.';
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    setError('');
    setSubmitting(true);
    try {
      await api.login(email.trim(), password);
      go(destination(), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? 'Too many attempts. Please wait a few minutes and try again.' : err.message || 'Could not sign in.');
    } finally {
      setSubmitting(false);
    }
  }

  async function requestOtp() {
    if (!EMAIL_RE.test(email.trim())) {
      setFieldErrors({ email: 'Enter a valid email address.' });
      return;
    }
    setFieldErrors({});
    setError('');
    setSubmitting(true);
    try {
      await api.otpRequest(email.trim());
      setOtpRequested(true);
      setOtpCooldown(30);
      const id = setInterval(() => setOtpCooldown((s) => { if (s <= 1) { clearInterval(id); return 0; } return s - 1; }), 1000);
    } catch (err) {
      setError(err.message || 'Could not send a code. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOtp(ev) {
    ev.preventDefault();
    if (!otpRequested) {
      requestOtp();
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await api.otpVerify(email.trim(), otp.trim());
      go(destination(), { replace: true });
    } catch (err) {
      setError(err.message || 'Invalid or expired code.');
    } finally {
      setSubmitting(false);
    }
  }

  const isPassword = mode === 'password';

  return (
    <main className="tgl-auth-layout" data-grid-2="">
      <div className="tgl-auth-story tglp-rise">
        <Eyebrow>Member Sign In</Eyebrow>
        <h1 style={{ margin: '0 0 22px' }}>
          <span style={{ display: 'block', fontSize: 'clamp(34px,4.2vw,56px)', lineHeight: 1, letterSpacing: '-0.035em', fontWeight: 800, textTransform: 'uppercase', color: '#2B1740' }}>
            Welcome back to
          </span>
          <span className="tgl-script-word" style={{ display: 'block', marginTop: 6, fontSize: 'clamp(50px,6.6vw,92px)', lineHeight: 1 }}>
            the League.
          </span>
        </h1>
        <p style={{ margin: '0 0 36px', maxWidth: 480, fontSize: 17, lineHeight: 1.65, color: 'rgba(43,23,64,0.7)' }}>
          One account for everything TGL — discover solutions on Vertex, build relationships in Networking and follow your Season 1 journey.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', borderTop: '1px solid rgba(53,26,78,0.14)', maxWidth: 480 }}>
          {FEATURES.map((f) => (
            <div key={f.title} style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 0', borderBottom: '1px solid rgba(53,26,78,0.1)' }}>
              <span style={{ width: 40, height: 40, borderRadius: 12, background: f.bg, color: f.color, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <svg width="19" height="19" viewBox="0 0 24 24"><use href={`#${f.icon}`} /></svg>
              </span>
              <div>
                <p style={{ margin: 0, fontSize: 14.5, fontWeight: 700, color: '#2B1740' }}>{f.title}</p>
                <p style={{ margin: '2px 0 0', fontSize: 13, color: 'rgba(43,23,64,0.65)' }}>{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="tgl-auth-frame tglp-rise-2">
        <div style={{ position: 'relative', background: '#FFFCF5', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 22, padding: 'clamp(26px, 6vw, 40px) clamp(18px, 5vw, 38px)', boxShadow: '0 30px 60px -24px rgba(34,16,58,0.28)' }}>
          <p style={{ margin: '0 0 6px', fontSize: 10.5, letterSpacing: '.26em', textTransform: 'uppercase', fontWeight: 700, color: '#8F6420' }}>Sign in</p>
          <h2 style={{ margin: '0 0 18px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Continue to your account</h2>
          <p role="note" style={{ margin: '0 0 24px', padding: '12px 14px', border: '1px solid rgba(192,141,46,0.4)', borderRadius: 12, background: 'rgba(224,181,88,0.12)', fontSize: 13.5, lineHeight: 1.5, color: '#2B1740' }}>
            <strong>Important:</strong> use the same email and credentials you used for your event registration to get access to the Networking community.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', padding: 4, border: '1px solid rgba(53,26,78,0.12)', borderRadius: 999, background: '#F6EEDF', marginBottom: 24 }}>
            {[['password', 'Password'], ['otp', 'One-time code']].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => switchMode(key)}
                style={{ padding: '11px 8px', border: 'none', borderRadius: 999, fontSize: 'clamp(10px, 2.9vw, 11px)', lineHeight: 1.2, fontWeight: 700, letterSpacing: 'clamp(0.06em, 0.5vw, 0.14em)', textTransform: 'uppercase', cursor: 'pointer', minWidth: 0, ...pill(mode === key) }}
              >
                {label}
              </button>
            ))}
          </div>

          <form onSubmit={isPassword ? submitPassword : submitOtp} noValidate>
            <label htmlFor="login-email" style={LABEL}>Email</label>
            <input
              id="login-email"
              className="tgl-input"
              type="email"
              placeholder="you@business.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={otpRequested && !isPassword}
              autoComplete="email"
              style={{ marginBottom: fieldErrors.email ? 6 : 18 }}
            />
            {fieldErrors.email && <p role="alert" className="tgl-field-error" style={{ margin: '0 0 14px' }}>{fieldErrors.email}</p>}

            {isPassword ? (
              <>
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: '4px 12px', marginBottom: 8 }}>
                  <label htmlFor="login-password" style={{ ...LABEL, marginBottom: 0 }}>Password</label>
                  <a href="/forgot-password" onClick={(e) => { e.preventDefault(); go('/forgot-password'); }} style={{ fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap', flexShrink: 0 }}>
                    Forgot password?
                  </a>
                </div>
                <input
                  id="login-password"
                  className="tgl-input"
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  style={{ marginBottom: fieldErrors.password ? 6 : 26 }}
                />
                {fieldErrors.password && <p role="alert" className="tgl-field-error" style={{ margin: '0 0 22px' }}>{fieldErrors.password}</p>}
              </>
            ) : otpRequested ? (
              <>
                <span style={LABEL}>6-digit code</span>
                <OtpBoxes value={otp} onChange={setOtp} />
                <p style={{ margin: '0 0 24px', fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>
                  Code sent to your email.{' '}
                  <button
                    type="button"
                    onClick={requestOtp}
                    disabled={otpCooldown > 0 || submitting}
                    style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', fontWeight: 600, color: otpCooldown > 0 ? 'inherit' : '#6B3E96', cursor: otpCooldown > 0 ? 'default' : 'pointer' }}
                  >
                    {otpCooldown > 0 ? `Resend in ${otpCooldown}s` : 'Resend'}
                  </button>
                </p>
              </>
            ) : (
              <p style={{ margin: '0 0 26px', fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>
                We&apos;ll email you a six-digit code instead of asking for a password.
              </p>
            )}

            {error && <div className="tgl-alert-error" role="alert" style={{ marginBottom: 18 }}><span>{error}</span></div>}

            <button
              type="submit"
              className="tglp-gold"
              disabled={submitting || (!isPassword && otpRequested && otp.trim().length !== 6)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: 17, border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontWeight: 700, fontSize: 13, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }}
            >
              {submitting ? 'Please wait…' : isPassword || otpRequested ? 'Continue' : 'Send code'}
              {!submitting && <svg width="17" height="17" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
            </button>
          </form>

          <p style={{ margin: '24px 0 0', paddingTop: 22, borderTop: '1px solid rgba(53,26,78,0.1)', textAlign: 'center', fontSize: 13.5, color: 'rgba(43,23,64,0.65)' }}>
            New to TGL?{' '}
            <a href="/signup" onClick={(e) => { e.preventDefault(); go('/signup'); }} style={{ fontWeight: 700 }}>Create an account</a>
          </p>
        </div>
      </div>
    </main>
  );
}
