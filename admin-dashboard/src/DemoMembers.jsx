import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from './api';

// Synthetic demo members for trying the member app by hand. Development and test databases only: in production the
// server returns nothing and no password is ever shown. All of them share one documented local-only password.

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}

function Avatar({ name, url }) {
  const [broken, setBroken] = useState(false);
  const initials = (name || '?').split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  if (url && !broken) return <img className="demo-avatar" src={url} alt="" loading="lazy" onError={() => setBroken(true)} />;
  return <span className="demo-avatar demo-avatar--text" aria-hidden="true">{initials}</span>;
}

export default function DemoMembers({ onUnauthorized }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [reveal, setReveal] = useState(false);
  const [copied, setCopied] = useState('');
  const [q, setQ] = useState('');

  const load = useCallback(() => {
    setError('');
    api.gpDemoMembers().then(setData).catch((e) => {
      if (e instanceof ApiError && e.status === 401) { onUnauthorized(); return; }
      setError(e.message || 'Could not load the demo members.');
    });
  }, [onUnauthorized]);
  useEffect(load, [load]);

  const doCopy = async (key, text) => {
    if (await copy(text)) { setCopied(key); setTimeout(() => setCopied((c) => (c === key ? '' : c)), 1400); }
  };

  const items = (data?.items || []).filter((m) => !q.trim() || `${m.name} ${m.email} ${m.business || ''} ${m.city || ''}`.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <>
      <header className="gpx-hero">
        <div>
          <p className="gpx-eyebrow">For testing only</p>
          <h2 className="gpx-title">Demo members</h2>
          <p className="gpx-lead">
            These are <strong>made-up members</strong> so you can sign in to the member app and try Networking, referrals and Growth Points by hand.
            They are labelled synthetic, never count towards the launch checks, and are never created or shown in production.
          </p>
        </div>
      </header>

      {error && <p className="alert" role="alert">{error}</p>}
      {!data && !error && <p className="cell__sub">Loading…</p>}

      {data && data.enabled === false && (
        <div className="gpx-empty" role="status"><h3>Not available here</h3><p>{data.message}</p></div>
      )}

      {data && data.enabled && (
        <>
          <section className="gpx-card">
            <h3>Shared password</h3>
            <p className="cell__sub">{data.password_note}</p>
            <p>
              <span className="demo-pw">{reveal ? (data.items[0]?.password || '—') : '••••••••••••••••••'}</span>{' '}
              <button type="button" className="btn btn--ghost" onClick={() => setReveal((v) => !v)}>{reveal ? 'Hide' : 'Show'}</button>{' '}
              {data.items[0] && <button type="button" className="btn btn--ghost" onClick={() => doCopy('pw', data.items[0].password)}>{copied === 'pw' ? 'Copied' : 'Copy password'}</button>}
            </p>
            <p className="cell__sub">Sign in at the member app (usually <code>localhost:5173</code>) with any email below.</p>
          </section>

          {data.items.length === 0 ? (
            <div className="gpx-empty" role="status">
              <h3>No demo members yet</h3>
              <p>Create them once from the backend folder (it refuses to run against production and is safe to repeat):</p>
              <p><code>{data.how_to_create}</code></p>
            </div>
          ) : (
            <section className="gpx-card">
              <h3>{data.total} demo members</h3>
              <input className="input" type="search" placeholder="Search name, email, business or city" aria-label="Search demo members" value={q} onChange={(e) => setQ(e.target.value)} style={{ margin: '8px 0 12px', maxWidth: 360 }} />
              <div className="table-wrap" style={{ overflowX: 'auto' }}>
                <table className="table">
                  <thead><tr><th>Member</th><th>Email</th><th>Password</th><th>Plan</th><th>Business</th><th>City</th><th>Points</th><th>Scenario</th></tr></thead>
                  <tbody>
                    {items.map((m) => (
                      <tr key={m.id}>
                        <td><Avatar name={m.name} url={m.photo_url} />{m.name}</td>
                        <td style={{ whiteSpace: 'nowrap' }}><span className="demo-pw">{m.email}</span> <button type="button" className="btn btn--ghost" onClick={() => doCopy(m.id, m.email)}>{copied === m.id ? 'Copied' : 'Copy'}</button></td>
                        <td><span className="demo-pw">{reveal ? m.password : '••••••••'}</span></td>
                        <td>{m.plan || '—'}</td>
                        <td>{m.business || '—'}</td>
                        <td>{m.city || '—'}</td>
                        <td>{m.growth_points.toLocaleString('en-IN')}</td>
                        <td>{m.scenario || '—'}</td>
                      </tr>
                    ))}
                    {items.length === 0 && <tr><td colSpan={8} className="cell__sub">No match.</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}
