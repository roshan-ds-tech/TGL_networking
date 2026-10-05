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
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

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

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError('');
    try {
      await api.removeCustomer(toDelete.id);
      setToDelete(null);
      // Last row of a later page: step back so the page isn't left empty.
      if (rows.length === 1 && page > 1) setPage(page - 1);
      else await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setDeleteError(err.message || 'Could not delete this account.');
    } finally {
      setDeleting(false);
    }
  }

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
          placeholder="Search by name, email or phone…"
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
              <th>Phone</th>
              <th>Business</th>
              <th>Email verified</th>
              <th>Personal profile</th>
              <th>Business profile</th>
              <th>Joined</th>
              <th>
                <span className="sr-only">Delete</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={9} className="empty">
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
                <td className="cell__mono">{u.phone || <span className="cell__sub">—</span>}</td>
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
                <td>
                  <button
                    type="button"
                    className="btn btn--icon"
                    onClick={() => {
                      setDeleteError('');
                      setToDelete(u);
                    }}
                    title={`Delete ${u.email}`}
                    aria-label={`Delete account ${u.email}`}
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
    
      {toDelete && (
        <div className="modal" role="dialog" aria-modal="true" aria-label="Confirm deletion" onClick={deleting ? undefined : () => setToDelete(null)}>
          <div className="modal__card modal__card--sm" onClick={(e) => e.stopPropagation()}>
            <header className="modal__head">
              <div>
                <h2 className="modal__title">Delete this account?</h2>
                <p className="modal__sub">This cannot be undone.</p>
              </div>
            </header>
            <div className="modal__body modal__body--pad">
              <dl className="confirm">
                <div className="confirm__row">
                  <dt>Email</dt>
                  <dd>{toDelete.email}</dd>
                </div>
                <div className="confirm__row">
                  <dt>Name</dt>
                  <dd>{toDelete.full_name || '—'}</dd>
                </div>
                <div className="confirm__row">
                  <dt>Business</dt>
                  <dd>{toDelete.business_name || '—'}</dd>
                </div>
              </dl>
              <p className="confirm__warn">
                The account, its profile, business, referrals, connections and notifications will be permanently deleted.
                Event registrations are kept and can be managed under Registrations.
              </p>
              {deleteError && (
                <p className="alert" role="alert">
                  {deleteError}
                </p>
              )}
            </div>
            <footer className="modal__foot">
              <button type="button" className="btn btn--ghost" onClick={() => setToDelete(null)} disabled={deleting} autoFocus>
                Cancel
              </button>
              <button type="button" className="btn btn--danger" onClick={confirmDelete} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Delete permanently'}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}
