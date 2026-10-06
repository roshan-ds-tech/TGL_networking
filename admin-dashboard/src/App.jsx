import { useCallback, useEffect, useRef, useState } from 'react';
import { AGES, api, ApiError, CATEGORIES, EMPLOYEES } from './api';
import Accounts from './Accounts';
import DeleteModal from './DeleteModal';
import Login from './Login';
import ProofModal from './ProofModal';

const PAGE_SIZE = 25;
// Fallback only, for the brief window before `stats` loads. Once loaded, the
// real capacity always comes from stats.capacity_per_category (backend's
// SLOTS_PER_CATEGORY setting) so this can never drift from what the server
// actually enforces at registration time.
const DEFAULT_SLOTS_PER_CATEGORY = 40;
const EARLY_BIRD_SLOTS = 20;

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatCard({ label, value, tone }) {
  return (
    <div className={`stat stat--${tone || 'default'}`}>
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  );
}

export default function App() {
  const [admin, setAdmin] = useState(null);
  const [booting, setBooting] = useState(true);
  const [view, setView] = useState('registrations');

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [stats, setStats] = useState(null);

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [category, setCategory] = useState('');
  const [verifiedFilter, setVerifiedFilter] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pendingId, setPendingId] = useState(null);
  const [proof, setProof] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [finaleResult, setFinaleResult] = useState(null);
  const [finaleBusy, setFinaleBusy] = useState(false);
  const [finaleDone, setFinaleDone] = useState(false);
  const [legacyAdminUrl, setLegacyAdminUrl] = useState(null);
  const [finaleCounts, setFinaleCounts] = useState(null);

  const abortRef = useRef(null);

  // Whether the Finale is currently recorded as completed — drives whether the
  // panel offers "Complete" or "Undo".
  useEffect(() => {
    if (!admin) return;
    api
      .season1()
      .then((f) => {
        setFinaleDone(!!f.event.completed_at);
        setFinaleCounts({ registrations: f.registrations, members: f.members_with_access });
      })
      .catch(() => {});
  }, [admin]);

  useEffect(() => {
    api.me().then(setAdmin).catch(() => setAdmin(null)).finally(() => setBooting(false));
  }, []);

  // Debounce search so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    if (!admin || view !== 'registrations') return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError('');
    try {
      const [list, s] = await Promise.all([
        api.registrations(
          {
            page,
            page_size: PAGE_SIZE,
            search: debouncedSearch,
            category,
            verified: verifiedFilter,
          },
          controller.signal,
        ),
        api.stats(),
      ]);
      setRows(list.items);
      setTotal(list.total);
      setPages(list.pages);
      setLegacyAdminUrl(list.legacy_admin_url || null);
      setStats(s);
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (err instanceof ApiError && err.status === 401) {
        setAdmin(null);
        return;
      }
      setError(err.message || 'Could not load registrations.');
    } finally {
      setLoading(false);
    }
  }, [admin, view, page, debouncedSearch, category, verifiedFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleVerified(row) {
    setPendingId(row.id);
    setError('');
    try {
      const updated = await api.setVerified(row.id, !row.verified);
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      api.stats().then(setStats).catch(() => {});
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAdmin(null);
        return;
      }
      setError(err.message || 'Could not update verification status.');
    } finally {
      setPendingId(null);
    }
  }

  async function handleDelete(row) {
    await api.remove(row.id);
    setToDelete(null);
    // Reload rather than splicing the row out: the current page is now short by
    // one, so the counts, page total and any row pulled up from the next page
    // all need to come from the server.
    await load();
  }

  async function runFinale(kind) {
    const undo = kind === 'undo';
    const message = undo
      ? 'Undo the Grand Finale? Networking will close again for registered members, and memberships it activated will return to pending.'
      : 'Record the Season 1 Grand Finale as completed? Networking will open for every account whose email matches a registration, for 3 months.';
    if (!window.confirm(message)) return;
    setFinaleBusy(true);
    setError('');
    try {
      const result = undo ? await api.undoSeason1() : await api.completeSeason1();
      setFinaleResult(undo ? { undone: true, ...result } : result);
      setFinaleDone(!undo);
      if (!undo) setFinaleCounts({ registrations: result.registrations, members: result.members_with_access });
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAdmin(null);
        return;
      }
      setError(err.message || `Could not ${undo ? 'undo' : 'complete'} the Grand Finale.`);
    } finally {
      setFinaleBusy(false);
    }
  }

  async function handleLogout() {
    try {
      await api.logout();
    } finally {
      setAdmin(null);
    }
  }

  if (booting) {
    return <div className="boot">Loading…</div>;
  }

  if (!admin) {
    return <Login onSuccess={setAdmin} />;
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="topbar__eyebrow">The Growth League</p>
          <h1 className="topbar__title">Season 1 · Registrations</h1>
        </div>
        <div className="topbar__right">
          <span className="topbar__user">{admin.email}</span>
          <button type="button" className="btn btn--ghost" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>

      <main className="main">
        <div className="tabs" role="tablist" aria-label="Admin views">
          <button
            type="button"
            role="tab"
            aria-selected={view === 'registrations'}
            className={`tab${view === 'registrations' ? ' tab--active' : ''}`}
            onClick={() => setView('registrations')}
          >
            Registrations
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === 'accounts'}
            className={`tab${view === 'accounts' ? ' tab--active' : ''}`}
            onClick={() => setView('accounts')}
          >
            Accounts
          </button>
        </div>

        {view === 'accounts' ? (
          <Accounts onUnauthorized={() => setAdmin(null)} />
        ) : (
          <>
        {stats && (
          <section className="stats" aria-label="Summary">
            <StatCard label="Total registrations" value={stats.total} />
            <StatCard label="Payment verified" value={stats.verified} tone="ok" />
            <StatCard label="Awaiting verification" value={stats.pending} tone="warn" />
          </section>
        )}

        <section className="finale-admin" aria-label="Grand Finale membership activation">
          <div>
            <h2 className="finale-admin__title">
              Grand Finale · {finaleDone ? 'Completed' : 'Not completed'}
            </h2>
            <p className="finale-admin__copy">
              {finaleDone
                ? 'Networking is open, for 3 calendar months, to every account whose email matches a registration. Use Undo to close it again (for testing).'
                : 'Completing the Finale opens the Networking community, for 3 calendar months, to every account whose email matches a registration.'}
            </p>
            {finaleDone && finaleCounts && (
              <p className="finale-admin__result">
                Networking is open to {finaleCounts.members} account{finaleCounts.members === 1 ? '' : 's'} ({finaleCounts.registrations} registration
                {finaleCounts.registrations === 1 ? '' : 's'} on file).
              </p>
            )}
            {finaleResult?.undone && !finaleDone && (
              <p className="finale-admin__result">
                Undone — Networking is closed again
                {finaleResult.reverted > 0 &&
                  `; ${finaleResult.reverted} membership${finaleResult.reverted === 1 ? '' : 's'} returned to pending`}
                .
              </p>
            )}
          </div>
          <div className="finale-admin__actions">
            <button type="button" className="btn btn--verify" onClick={() => runFinale('complete')} disabled={finaleBusy || finaleDone}>
              {finaleBusy && !finaleDone ? 'Completing…' : 'Complete Grand Finale'}
            </button>
            <button type="button" className="btn btn--danger" onClick={() => runFinale('undo')} disabled={finaleBusy || !finaleDone}>
              {finaleBusy && finaleDone ? 'Undoing…' : 'Undo Grand Finale'}
            </button>
          </div>
        </section>

        {stats && stats.by_category.length > 0 && (
          <section className="slots" aria-label="Slots by category">
            <h2 className="slots__title">
              Slots filled by category
              <span className="slots__hint">
                Early-bird price applies for the first {EARLY_BIRD_SLOTS} of{' '}
                {stats.capacity_per_category ?? DEFAULT_SLOTS_PER_CATEGORY}
              </span>
            </h2>
            <div className="slots__grid">
              {stats.by_category.map((c) => {
                const capacity = stats.capacity_per_category ?? DEFAULT_SLOTS_PER_CATEGORY;
                const pct = Math.min(100, (c.total / capacity) * 100);
                const earlyBirdGone = c.total >= EARLY_BIRD_SLOTS;
                // The backend refuses new registrations once a category hits
                // this same capacity (see backend/app/routers/public.py) —
                // this mirrors that threshold so the dashboard shows it as
                // closed, not just "early-bird over".
                const categoryClosed = c.total >= capacity;
                return (
                  <div key={c.category} className="slot">
                    <div className="slot__head">
                      <span className="slot__name">
                        {c.category} · {CATEGORIES[c.category] || 'Unknown'}
                      </span>
                      <span className="slot__count">
                        {c.total}/{capacity}
                      </span>
                    </div>
                    <div className="slot__bar">
                      <div
                        className={`slot__fill${earlyBirdGone ? ' slot__fill--full' : ''}${categoryClosed ? ' slot__fill--closed' : ''}`}
                        style={{ width: `${pct}%` }}
                      />
                      <span className="slot__marker" style={{ left: '50%' }} />
                    </div>
                    {categoryClosed ? (
                      <span className="slot__flag slot__flag--closed">Full · registration closed</span>
                    ) : (
                      earlyBirdGone && (
                        <span className="slot__flag">Early-bird closed · standard price</span>
                      )
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        )}

        <section className="toolbar">
          <input
            type="search"
            className="input"
            placeholder="Search name, business, email or phone…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search registrations"
          />
          <select
            className="input"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(1);
            }}
            aria-label="Filter by category"
          >
            <option value="">All categories</option>
            {Object.entries(CATEGORIES).map(([k, v]) => (
              <option key={k} value={k}>
                {k} · {v}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={verifiedFilter}
            onChange={(e) => {
              setVerifiedFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Filter by verification status"
          >
            <option value="">All statuses</option>
            <option value="false">Pending only</option>
            <option value="true">Verified only</option>
          </select>
        </section>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        <div className="tablewrap">
          <table className="table">
            <thead>
              <tr>
                <th>Business</th>
                <th>Contact</th>
                <th>Category</th>
                <th>Team</th>
                <th>Operating</th>
                <th>City</th>
                <th>Submitted</th>
                <th>Payment proof</th>
                <th>Status</th>
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && !loading && (
                <tr>
                  <td colSpan={10} className="empty">
                    No registrations match these filters.
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className={r.verified ? 'row--verified' : undefined}>
                  <td>
                    <span className="cell__primary">{r.business_name}</span>
                    <span className="cell__sub">{r.full_name}</span>
                    {r.source !== 'local' && (
                      <span className="cell__sub" title="Registered on tgl.skykeen.in — mirrored here from the PythonAnywhere admin">
                        via tgl.skykeen.in
                      </span>
                    )}
                  </td>
                  <td>
                    <a className="cell__link" href={`mailto:${r.email}`}>
                      {r.email}
                    </a>
                    <span className="cell__sub">{r.phone}</span>
                  </td>
                  <td>
                    <span className="cell__primary">{r.category}</span>
                    <span className="cell__sub">{CATEGORIES[r.category] || '—'}</span>
                  </td>
                  <td>{EMPLOYEES[r.employees] || r.employees}</td>
                  <td>{AGES[r.business_age] || r.business_age}</td>
                  <td>{r.city || '—'}</td>
                  <td className="cell__mono">{formatDate(r.created_at)}</td>
                  <td>
                    {r.source === 'local' ? (
                      <button
                        type="button"
                        className="btn btn--link"
                        onClick={() => setProof(r)}
                      >
                        View proof
                      </button>
                    ) : (
                      <a className="btn btn--link" href={legacyAdminUrl || '#'} target="_blank" rel="noopener noreferrer" title="The payment proof is stored in the PythonAnywhere admin">
                        View in PythonAnywhere ↗
                      </a>
                    )}
                  </td>
                  <td>
                    {r.source !== 'local' ? (
                      <span className={r.verified ? 'btn btn--verified' : 'cell__sub'} style={{ cursor: 'default' }} title="Verify this payment in the PythonAnywhere admin; it syncs here within minutes">
                        {r.verified ? '✓ Verified' : 'Pending (verify in PythonAnywhere)'}
                      </span>
                    ) : (
                    <button
                      type="button"
                      className={`btn ${r.verified ? 'btn--verified' : 'btn--verify'}`}
                      onClick={() => toggleVerified(r)}
                      disabled={pendingId === r.id}
                      title={
                        r.verified
                          ? `Verified${r.verified_by_email ? ` by ${r.verified_by_email}` : ''} — click to undo`
                          : 'Mark payment as verified'
                      }
                    >
                      {pendingId === r.id ? '…' : r.verified ? '✓ Verified' : 'Verify'}
                    </button>
                    )}
                  </td>
                  <td>
                    {r.source === 'local' && (
                    <button
                      type="button"
                      className="btn btn--icon"
                      onClick={() => setToDelete(r)}
                      title={`Delete ${r.business_name}`}
                      aria-label={`Delete registration for ${r.business_name}`}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
                        <path
                          d="M4 7h16M10 4h4M9 7v12m6-12v12M6 7l1 13h10l1-13"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <div className="tablewrap__loading">Loading…</div>}
        </div>

        <nav className="pager" aria-label="Pagination">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
          >
            Previous
          </button>
          <span className="pager__info">
            Page {page} of {pages} · {total} registration{total === 1 ? '' : 's'}
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page >= pages || loading}
          >
            Next
          </button>
        </nav>
          </>
        )}
      </main>

      {proof && <ProofModal registration={proof} onClose={() => setProof(null)} />}
      {toDelete && (
        <DeleteModal
          registration={toDelete}
          onConfirm={() => handleDelete(toDelete)}
          onClose={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
