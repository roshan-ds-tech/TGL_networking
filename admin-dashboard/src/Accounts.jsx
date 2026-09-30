import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';

const PAGE_SIZE = 25;

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

// Accounts — who has a TGL product-app account. Deliberately separate from
// the Registrations view: an account here has not necessarily registered or
// paid for Season 1 (see App.jsx's registrations table for that).
export default function Accounts({ onUnauthorized }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const abortRef = useRef(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError('');
    try {
      const list = await api.customers(
        { page, page_size: PAGE_SIZE, search: debouncedSearch },
        controller.signal,
      );
      setRows(list.items);
      setTotal(list.total);
      setPages(list.pages);
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(err.message || 'Could not load accounts.');
    } finally {
      setLoading(false);
    }
  }, [page, debouncedSearch, onUnauthorized]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <section className="stats" aria-label="Summary">
        <div className="stat">
          <span className="stat__value">{total}</span>
          <span className="stat__label">TGL accounts</span>
        </div>
      </section>

      <section className="toolbar">
        <input
          type="search"
          className="input"
          placeholder="Search by email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search accounts"
        />
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
              <th>Email</th>
              <th>Name</th>
              <th>Business</th>
              <th>Email verified</th>
              <th>Personal profile</th>
              <th>Business profile</th>
              <th>Joined</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={7} className="empty">
                  No accounts match this search.
                </td>
              </tr>
            )}
            {rows.map((u) => (
              <tr key={u.id}>
                <td>
                  <a className="cell__link" href={`mailto:${u.email}`}>
                    {u.email}
                  </a>
                </td>
                <td>{u.full_name || <span className="cell__sub">—</span>}</td>
                <td>{u.business_name || <span className="cell__sub">—</span>}</td>
                <td>
                  {u.email_verified_at ? (
                    <span className="btn btn--verified" style={{ cursor: 'default' }}>
                      ✓ Verified
                    </span>
                  ) : (
                    <span className="cell__sub">Pending</span>
                  )}
                </td>
                <td>{u.personal_profile_complete ? '✓ Complete' : <span className="cell__sub">Incomplete</span>}</td>
                <td>{u.business_profile_complete ? '✓ Complete' : <span className="cell__sub">Incomplete</span>}</td>
                <td className="cell__mono">{formatDate(u.created_at)}</td>
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
          Page {page} of {pages} · {total} account{total === 1 ? '' : 's'}
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
  );
}
