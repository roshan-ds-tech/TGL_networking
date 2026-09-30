import { useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { Button, Field } from '../../components/AppShell';

export default function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function submit(ev) {
    ev.preventDefault();
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err.message || 'This reset link is invalid or has expired.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main style={{ maxWidth: 520, margin: '0 auto', padding: '80px 28px 96px' }}>
      <div style={{ background: '#FFFCF5', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 22, padding: '40px 38px', boxShadow: '0 30px 60px -24px rgba(34,16,58,0.22)' }}>
        {!token ? (
          <>
            <h1 style={{ margin: '0 0 10px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Invalid link</h1>
            <p style={{ margin: '0 0 26px', fontSize: 15, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
              This reset link is missing its token. Request a new one from the sign-in page.
            </p>
            <Button variant="ghost" onClick={() => go('/forgot-password')}>Request a new link</Button>
          </>
        ) : done ? (
          <>
            <span style={{ width: 52, height: 52, borderRadius: '50%', background: 'rgba(192,141,46,0.14)', color: '#A8762F', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
              <svg width="24" height="24" viewBox="0 0 24 24"><use href="#i-check" /></svg>
            </span>
            <h1 style={{ margin: '0 0 10px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Password updated</h1>
            <p style={{ margin: '0 0 26px', fontSize: 15, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
              You can now sign in with your new password.
            </p>
            <Button onClick={() => go('/login')}>Go to sign in</Button>
          </>
        ) : (
          <>
            <p style={{ margin: '0 0 6px', fontSize: 10.5, letterSpacing: '.26em', textTransform: 'uppercase', fontWeight: 700, color: '#C08D2E' }}>Account recovery</p>
            <h1 style={{ margin: '0 0 10px', fontSize: 26, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Choose a new password</h1>
            <form onSubmit={submit} noValidate style={{ display: 'grid', gap: 18, marginTop: 12 }}>
              <Field label="New Password">
                <input className="tgl-input" type="password" placeholder="At least 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus autoComplete="new-password" />
              </Field>
              <Field label="Confirm Password">
                <input className="tgl-input" type="password" placeholder="Re-enter your password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
              </Field>
              {error && (
                <div className="tgl-alert-error" role="alert">
                  <span>{error}</span>
                </div>
              )}
              <Button type="submit" disabled={submitting} style={{ width: '100%' }}>
                {submitting ? 'Saving…' : 'Reset password'}
              </Button>
            </form>
          </>
        )}
      </div>
    </main>
  );
}
