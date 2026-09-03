import { useState } from 'react';
import { api } from './api';

export default function Login({ onSuccess }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const admin = await api.login(email.trim(), password);
      setPassword('');
      onSuccess(admin);
    } catch (err) {
      // The server intentionally returns one generic message; show it as-is.
      setError(err.message || 'Sign in failed.');
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login__card" onSubmit={handleSubmit}>
        <p className="login__eyebrow">The Growth League</p>
        <h1 className="login__title">Admin sign in</h1>
        <p className="login__sub">Season 1 registration &amp; payment verification</p>

        <label className="field">
          <span className="field__label">Email</span>
          <input
            className="input"
            type="email"
            name="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>

        <label className="field">
          <span className="field__label">Password</span>
          <input
            className="input"
            type="password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
