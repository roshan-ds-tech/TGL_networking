import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, inr } from './api';
import ReasonModal from './ReasonModal';

const PAGE_SIZE = 25;
const label = (s) => (s || '').replace(/_/g, ' ').toLowerCase();
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');

// Payment review for plan subscriptions. TGL takes payment by manual proof; there is no gateway.
export default function Subscriptions({ onUnauthorized }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [f, setF] = useState({ status: '', payment_status: '', search: '' });
  const [deb, setDeb] = useState(f);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [ask, setAsk] = useState(null);
  const abort = useRef(null);

  useEffect(() => { const t = setTimeout(() => { setDeb(f); setPage(1); }, 300); return () => clearTimeout(t); }, [f]);

  const load = useCallback(async () => {
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    setLoading(true);
    setError('');
    try {
      const res = await api.subscriptions({ ...deb, page, page_size: PAGE_SIZE }, ctl.signal);
      setRows(res.items); setTotal(res.total); setPages(res.pages);
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (err instanceof ApiError && err.status === 401) { onUnauthorized(); return; }
      setError(err.message || 'Could not load subscriptions.');
    } finally { if (abort.current === ctl) setLoading(false); }
  }, [deb, page, onUnauthorized]);
  useEffect(() => { load(); }, [load]);

  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  return (
    <>
      <div className="toolbar" role="search">
        <input className="input" placeholder="Email, invoice number or payment reference" value={f.search} onChange={set('search')} aria-label="Search" />
        <select className="input" value={f.status} onChange={set('status')} aria-label="Subscription status"><option value="">Any subscription status</option>{['PENDING', 'ACTIVE', 'EXPIRED', 'CANCELLED'].map((s) => <option key={s} value={s}>{label(s)}</option>)}</select>
        <select className="input" value={f.payment_status} onChange={set('payment_status')} aria-label="Payment status"><option value="">Any payment status</option>{['PENDING', 'SUBMITTED', 'VERIFIED', 'FAILED', 'REFUNDED'].map((s) => <option key={s} value={s}>{label(s)}</option>)}</select>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      <div className="tablewrap" tabIndex={0} role="region" aria-label="Table (scrolls sideways on small screens)">
        <table className="table">
          <thead><tr><th>Member</th><th>Plan</th><th>Invoice</th><th>Amount</th><th>Payment</th><th>Subscription</th><th>Submitted</th><th /></tr></thead>
          <tbody>
            {rows.length === 0 && !loading && <tr><td colSpan={8} className="empty">No subscriptions match.</td></tr>}
            {rows.map((s) => (
              <tr key={s.id}>
                <td>{s.user.name || s.user.email}<span className="cell__sub"> {s.user.name ? s.user.email : ''}</span></td>
                <td>{s.plan_name}</td>
                <td className="cell__mono">{s.invoice_number}<span className="cell__sub"> {label(s.invoice_status)} · {s.payment_reference}</span></td>
                <td className="cell__mono">{inr(s.amount_due_minor)}<span className="cell__sub"> paid {inr(s.amount_paid_minor)}</span></td>
                <td>{label(s.payment_status)}</td>
                <td>{label(s.effective_status)}{s.expires_at ? <span className="cell__sub"> until {when(s.expires_at)}</span> : ''}</td>
                <td className="cell__mono">{when(s.submitted_at)}</td>
                <td>
                  {s.has_proof && <a className="btn btn--ghost" href={api.subscriptionProofUrl(s.id)} target="_blank" rel="noopener noreferrer">Proof</a>}{' '}
                  {s.payment_status === 'SUBMITTED' && (<>
                    <button type="button" className="btn btn--verify" onClick={() => setAsk({ title: 'Verify this payment', sub: 'Confirm the money has arrived (for example, the bank reference). This opens the member\'s access.', cta: 'Verify payment', run: async (r) => { await api.verifyPayment(s.id, r); await load(); } })}>Verify</button>{' '}
                    <button type="button" className="btn btn--ghost" onClick={() => setAsk({ title: 'Reject this payment', cta: 'Reject', danger: true, run: async (r) => { await api.rejectPayment(s.id, r); await load(); } })}>Reject</button>
                  </>)}
                  {s.payment_status === 'VERIFIED' && <button type="button" className="btn btn--ghost" onClick={() => setAsk({ title: 'Record a refund', sub: 'Ends access. Record only; no money moves here.', cta: 'Record refund', danger: true, run: async (r) => { await api.refundSubscription(s.id, r); await load(); } })}>Refund</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="tablewrap__loading">Loading…</div>}
      </div>
      <nav className="pager" aria-label="Pagination">
        <button type="button" className="btn btn--ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1 || loading}>Previous</button>
        <span className="pager__info">Page {page} of {pages} · {total} subscription{total === 1 ? '' : 's'}</span>
        <button type="button" className="btn btn--ghost" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages || loading}>Next</button>
      </nav>
      {ask && <ReasonModal title={ask.title} sub={ask.sub} cta={ask.cta} danger={ask.danger} onClose={() => setAsk(null)} onSubmit={ask.run} />}
    </>
  );
}
