import { useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { Button, Field } from '../../components/AppShell';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(ev) {
    ev.preventDefault();
    if (!EMAIL_RE.test(email.trim())) {
      setError('Enter a valid email address.');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await api.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(err.message || 'Could not send a reset link. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ maxWidth: 520, margin: '0 auto', padding: '80px 28px 96px' }}>
      <button
        type="button"
        onClick={() => go('/login')}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 0, border: 'none', background: 'none', color: '#6B3E96', fontSize: 11, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', marginBottom: 28 }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-back" /></svg>
        Back to sign in
      </button>
      <div style={{ background: '#FFFCF5', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 22, padding: '40px 38px', boxShadow: '0 30px 60px -24px rgba(34,16,58,0.22)' }}>
        {sent ? (
          <>
            <span style={{ width: 52, height: 52, borderRadius: '50%', background: 'rgba(192,141,46,0.14)', color: '#A8762F', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
              <svg width="24" height="24" viewBox="0 0 24 24"><use href="#i-mail" /></svg>
            </span>
            <h1 style={{ margin: '0 0 10px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Check your inbox</h1>
            <p style={{ margin: '0 0 26px', fontSize: 15, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
              If an account exists for that email, a reset link is on its way. It expires in 30 minutes.
            </p>
            <Button variant="ghost" onClick={() => go('/login')} style={{ padding: '15px 26px', fontSize: 12, letterSpacing: '.12em' }}>Return to sign in</Button>
          </>
        ) : (
          <>
            <p style={{ margin: '0 0 6px', fontSize: 10.5, letterSpacing: '.26em', textTransform: 'uppercase', fontWeight: 700, color: '#C08D2E' }}>Account recovery</p>
            <h1 style={{ margin: '0 0 10px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Reset your password</h1>
            <p style={{ margin: '0 0 26px', fontSize: 15, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
              Enter the email you registered with and we&apos;ll send a reset link.
            </p>
            <form onSubmit={submit} noValidate style={{ display: 'grid', gap: 18 }}>
              <Field label="Email" error={error}>
                <input className="tgl-input" type="email" placeholder="you@business.com" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus autoComplete="email" />
              </Field>
              <Button type="submit" disabled={submitting} style={{ width: '100%', padding: 17, fontSize: 13, letterSpacing: '.12em' }}>
                {submitting ? 'Sending…' : 'Send reset link'}
              </Button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}
