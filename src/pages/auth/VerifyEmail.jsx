import { useEffect, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { Button, Card, Eyebrow, Field, HeroMeta } from '../../components/AppShell';

export default function VerifyEmail() {
  const [token, setToken] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const id = setInterval(() => setResendCooldown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [resendCooldown]);

  useEffect(() => {
    // A dev-only code stashed by Signup right before landing here. Consumed
    // once so a later real signup doesn't leak a stale code into this screen.
    const stashed = sessionStorage.getItem('tgl_dev_otp');
    if (stashed) {
      setToken(stashed);
      sessionStorage.removeItem('tgl_dev_otp');
    }
    api.me()
      .then((user) => {
        if (user.email_verified_at) go('/onboarding/personal');
        else setEmail(user.email);
      })
      .catch(() => go('/login')); // no session at all — this screen only makes sense mid-signup
  }, []);

  async function logout() {
    setLoggingOut(true);
    try {
      await api.logout();
    } catch {
      // best-effort — send them to login either way
    } finally {
      go('/login');
    }
  }

  async function submit(ev) {
    ev.preventDefault();
    setError('');
    setNotice('');
    setSubmitting(true);
    try {
      await api.verifyEmail(token.trim());
      go('/onboarding/personal');
    } catch (err) {
      setError(err.message || 'Invalid or expired verification code.');
    } finally {
      setSubmitting(false);
    }
  }

  async function resend() {
    setError('');
    setNotice('');
    setResending(true);
    try {
      const result = await api.resendVerification();
      setNotice('A new code has been sent to your email.');
      setResendCooldown(60);
      if (result?.dev_verification_token) setToken(result.dev_verification_token);
    } catch (err) {
      setError(err.message || 'Could not resend the code. Please try again shortly.');
    } finally {
      setResending(false);
    }
  }

  return (
    <main className="tgl-auth-layout">
      <div className="tgl-auth-story">
        <Eyebrow>Account Activation</Eyebrow>
        <h1 className="tgl-hero-headline">
          Verify Your
          <span className="tgl-script-word">Email.</span>
        </h1>
        <p style={{ margin: '22px 0 0', fontSize: 17, lineHeight: 1.65, color: 'rgba(43,23,64,0.7)' }}>
          One quick step keeps the League trustworthy — every member is a real, reachable founder.
        </p>
        <p style={{ margin: '12px 0 0', fontSize: 15, lineHeight: 1.7, color: 'rgba(43,23,64,0.62)' }}>
          Enter the 6-digit code emailed to you at signup to unlock your founder profile and Season 1 registration.
        </p>
        <HeroMeta />
      </div>

      <div className="tgl-auth-frame">
        <Card>
          <div style={{ textAlign: 'center', marginBottom: 22 }}>
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'rgba(192,141,46,0.12)', border: '1px solid rgba(192,141,46,0.35)', color: '#C08D2E', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginBottom: 14 }}>
              <svg width="24" height="24" viewBox="0 0 24 24"><use href="#i-mail" /></svg>
            </div>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: 'var(--tgl-text-muted)' }}>
              {email ? (<>We emailed a 6-digit code to <strong style={{ color: '#2B1740' }}>{email}</strong>.</>) : 'Enter the 6-digit code we emailed you at signup.'}
            </p>
          </div>

          <form onSubmit={submit} noValidate style={{ display: 'grid', gap: 16 }}>
            <Field label="Verification Code">
              <input
                className="tgl-input"
                placeholder="123456"
                value={token}
                onChange={(e) => setToken(e.target.value.replace(/\D/g, '').slice(0, 6))}
                autoFocus
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                required
                style={{ letterSpacing: '0.3em', fontSize: 20, textAlign: 'center' }}
              />
            </Field>

            {notice && !error && (
              <div className="tgl-alert-info" role="status"><span>{notice}</span></div>
            )}
            {error && (
              <div className="tgl-alert-error" role="alert"><span>{error}</span></div>
            )}

            <Button type="submit" disabled={submitting || token.trim().length !== 6} style={{ width: '100%' }}>
              {submitting ? 'Verifying…' : 'Verify and Continue'}
              {!submitting && <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
            </Button>

            <button
              type="button"
              onClick={resend}
              disabled={resending || resendCooldown > 0}
              style={{ background: 'none', border: 'none', padding: 0, fontSize: 13, fontWeight: 600, color: resendCooldown > 0 ? 'var(--tgl-text-muted)' : '#C08D2E', cursor: resending || resendCooldown > 0 ? 'default' : 'pointer', justifySelf: 'center' }}
            >
              {resending ? 'Sending…' : resendCooldown > 0 ? `Resend code in ${resendCooldown}s` : "Didn't get a code? Resend"}
            </button>

            {email && (
              <p style={{ margin: 0, textAlign: 'center', fontSize: 12.5, color: 'var(--tgl-text-muted)' }}>
                Not {email}?{' '}
                <button type="button" onClick={logout} disabled={loggingOut} style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', fontWeight: 600, color: '#2B1740', textDecoration: 'underline', cursor: loggingOut ? 'default' : 'pointer' }}>
                  {loggingOut ? 'Signing out…' : 'Sign out'}
                </button>
              </p>
            )}
          </form>
        </Card>
      </div>
    </main>
  );
}
