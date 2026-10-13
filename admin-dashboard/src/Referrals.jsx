import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, inr } from './api';
import ReasonModal from './ReasonModal';

const PAGE_SIZE = 25;
const STATUSES = ['GIVEN', 'ACCEPTED', 'CONTACTED', 'MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED', 'DECLINED', 'CANCELLED', 'CLOSED'];
const CLOSURE_STATUSES = ['NONE', 'AWAITING_CONFIRMATION', 'AWAITING_EVIDENCE', 'UNDER_REVIEW', 'VERIFIED', 'DISPUTED'];
const BANDS = { UNDER_25K: 'Under ₹25k', '25K_1L': '₹25k–1L', '1L_5L': '₹1L–5L', '5L_10L': '₹5L–10L', '10L_PLUS': '₹10L+' };
const LEVELS = ['L0 self-reported', 'L1 one party', 'L2 both parties', 'L3 evidence', 'L4 admin'];
const label = (s) => (s || '').replace(/_/g, ' ').toLowerCase();
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');

function Person({ p }) {
  return <>{p.name || p.email}<span className="cell__sub"> {p.name ? p.email : ''}</span></>;
}

function Detail({ id, onClose, onUnauthorized, onChanged }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState('');
  const [ask, setAsk] = useState(null); // { title, cta, danger, run(reason) }

  const load = useCallback(async () => {
    try { setD(await api.referral(id)); } catch (err) { if (err instanceof ApiError && err.status === 401) onUnauthorized(); else setError(err.message); }
  }, [id, onUnauthorized]);
  useEffect(() => { load(); }, [load]);

  const act = (title, fn, opts = {}) => setAsk({ title, ...opts, run: async (reason) => { setD(await fn(reason)); onChanged(); } });
  const c = d?.closure;

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Referral details" onClick={onClose}>
      <div className="modal__card" onClick={(e) => e.stopPropagation()}>
        <header className="modal__head">
          <div><h2 className="modal__title">Referral {id.slice(0, 8)}</h2><p className="modal__sub">{d ? `${label(d.status)} · created ${when(d.created_at)}` : 'Loading…'}</p></div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>Close</button>
        </header>
        <div className="modal__body modal__body--pad rdetail">
          {error && <p className="alert" role="alert">{error}</p>}
          {d && (<>
            {d.flagged && <p className="alert" role="status">Flagged: {d.flag_reason}</p>}
            {d.legacy_unverified && <p className="alert" role="status">Legacy record: this referral was moved on by the old one-member flow, so the meeting was never confirmed by both members. It does not count as a verified meeting or deal. Correcting the status to an earlier stage asks both members to confirm properly.</p>}
            <section className="rd-grid">
              <div><h3>Referrer</h3><p><Person p={d.referrer} /></p></div>
              <div><h3>Recipient</h3><p><Person p={d.recipient} /></p></div>
              <div><h3>Prospect</h3><p>{d.prospect_company || d.prospect_name || '—'}</p><p className="cell__sub">Estimate at creation: {BANDS[d.estimated_value_range] || label(d.estimated_value_range) || 'not given'}</p></div>
              <div><h3>Opportunity</h3><p>{d.opportunity}</p></div>
            </section>

            <section>
              <h3>Meeting confirmations ({d.meeting_confirmations.length}/2)</h3>
              {d.meeting_confirmations.length === 0 ? <p className="cell__sub">Nobody has confirmed a meeting.</p> : (
                <ul className="rd-list">{d.meeting_confirmations.map((m) => <li key={m.user.id}>{m.role === 'giver' ? 'Referrer' : 'Recipient'}: {m.user.name || m.user.email} · {when(m.confirmed_at)}</li>)}</ul>
              )}
            </section>

            <section>
              <h3>Closed business</h3>
              {!c ? <p className="cell__sub">None reported.{d.past_closures.length ? ` ${d.past_closures.length} earlier report(s) ended.` : ''}</p> : (<>
                <p><strong>{inr(c.actual_value_minor)}</strong> · {c.value_band_label} · <span className="rd-pill">{c.status_label}</span> · {c.verification_label} (level {c.verification_level})</p>
                <p className="cell__sub">Reported by {c.reported_by} {when(c.submitted_at)} · recipient confirmed {when(c.confirmed_by_receiver_at)} · referrer confirmed {when(c.confirmed_by_referrer_at)}{c.verified_by ? ` · verified by ${c.verified_by} ${when(c.verified_at)}` : ''}</p>
                {c.note && <p>“{c.note}”</p>}
                {c.dispute_reason && <p className="alert">Disputed by {c.disputed_by}: {c.dispute_reason}</p>}
                <p className="cell__sub">{c.evidence_required ? 'Evidence required.' : 'No evidence required.'} {c.admin_approval_required ? 'Admin approval required (₹5L+).' : ''}</p>
                {c.evidence.length > 0 && (
                  <table className="table rd-table"><thead><tr><th>Evidence</th><th>By</th><th>Status</th><th /></tr></thead><tbody>
                    {c.evidence.map((e) => (
                      <tr key={e.id}>
                        <td><a className="cell__link" href={api.referralEvidenceUrl(d.id, e.id)} target="_blank" rel="noopener noreferrer">{label(e.evidence_type)}</a> <span className="cell__sub">{(e.size_bytes / 1024).toFixed(0)} KB {e.note || ''}</span>{e.reused_in_other_closures > 0 && <span className="rd-warn"> Same file on {e.reused_in_other_closures} other deal(s)</span>}</td>
                        <td>{e.uploaded_by}<span className="cell__sub"> {when(e.uploaded_at)}</span></td>
                        <td>{label(e.status)}{e.rejection_reason ? <span className="cell__sub"> {e.rejection_reason}</span> : ''}</td>
                        <td>{e.status === 'PENDING' && c.status === 'UNDER_REVIEW' && (<>
                          <button type="button" className="btn btn--verify" onClick={() => act('Verify this evidence', (r) => api.verifyEvidence(d.id, e.id, r), { cta: 'Verify evidence' })}>Verify</button>{' '}
                          <button type="button" className="btn btn--ghost" onClick={() => act('Reject this evidence', (r) => api.rejectEvidence(d.id, e.id, r), { cta: 'Reject evidence', danger: true })}>Reject</button>
                        </>)}</td>
                      </tr>
                    ))}
                  </tbody></table>
                )}
                <div className="rd-actions">
                  {(c.status === 'UNDER_REVIEW' || (c.status === 'VERIFIED' && c.verification_level < 4)) && <button type="button" className="btn btn--primary" onClick={() => act('Verify this closed business', (r) => api.verifyClosure(d.id, r), { cta: 'Verify (level 4)' })}>Verify closed business</button>}
                  {c.status === 'DISPUTED' && (<>
                    <button type="button" className="btn btn--verify" onClick={() => act('Restore: the report was right', (r) => api.resolveDispute(d.id, 'RESTORE', r), { cta: 'Restore' })}>Restore</button>
                    <button type="button" className="btn btn--ghost" onClick={() => act('Reject the report', (r) => api.resolveDispute(d.id, 'REJECT', r), { cta: 'Reject report', danger: true })}>Reject</button>
                    <button type="button" className="btn btn--danger" onClick={() => act('Invalidate the report', (r) => api.resolveDispute(d.id, 'INVALIDATE', r), { cta: 'Invalidate', danger: true })}>Invalidate</button>
                  </>)}
                  {['AWAITING_CONFIRMATION', 'AWAITING_EVIDENCE', 'UNDER_REVIEW'].includes(c.status) && <button type="button" className="btn btn--ghost" onClick={() => act('Reject this closed business', (r) => api.rejectClosure(d.id, r), { cta: 'Reject', danger: true })}>Reject</button>}
                  {['VERIFIED', 'AWAITING_EVIDENCE', 'UNDER_REVIEW'].includes(c.status) && <button type="button" className="btn btn--danger" onClick={() => act('Invalidate this closed business', (r) => api.invalidateClosure(d.id, r), { cta: 'Invalidate', danger: true })}>Invalidate</button>}
                </div>
              </>)}
              {d.past_closures.map((p) => <p key={p.id} className="cell__sub">Earlier: {inr(p.actual_value_minor)} · {p.status_label}{p.rejection_reason ? ` · ${p.rejection_reason}` : ''}{p.invalidated_reason ? ` · ${p.invalidated_reason}` : ''}</p>)}
            </section>

            <section className="rd-actions">
              <button type="button" className="btn btn--ghost" onClick={() => act(d.flagged ? 'Clear the flag' : 'Flag for review', (r) => api.flagReferral(d.id, !d.flagged, r), { cta: d.flagged ? 'Clear flag' : 'Flag' })}>{d.flagged ? 'Clear flag' : 'Flag'}</button>
              <button type="button" className="btn btn--ghost" onClick={() => act('Add an admin note', (r) => api.addReferralNote(d.id, r), { cta: 'Add note' })}>Add note</button>
              {!c && (
                <select className="input rd-status" value="" onChange={(e) => { const st = e.target.value; if (st) act(`Correct the status to ${label(st)}`, (r) => api.correctReferralStatus(d.id, st, r), { cta: 'Correct status' }); }} aria-label="Correct the status">
                  <option value="">Correct status…</option>
                  {STATUSES.filter((s) => !['MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED', d.status].includes(s)).map((s) => <option key={s} value={s}>{label(s)}</option>)}
                </select>
              )}
            </section>

            <section>
              <h3>History</h3>
              <ol className="rd-timeline">{d.timeline.map((t, i) => (
                <li key={i}><span className="cell__mono">{when(t.at)}</span> <strong>{t.action}</strong> · {t.actor_type === 'SYSTEM' ? 'system' : (t.actor || t.actor_role)}{t.reason ? ` — ${t.reason}` : ''}</li>
              ))}</ol>
            </section>
          </>)}
        </div>
      </div>
      {ask && <ReasonModal title={ask.title} cta={ask.cta} danger={ask.danger} onClose={() => setAsk(null)} onSubmit={ask.run} />}
    </div>
  );
}

export default function Referrals({ onUnauthorized }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [f, setF] = useState({ status: '', closure_status: '', verification_level: '', deal_band: '', flagged: '', legacy_unverified: '', referrer: '', recipient: '', date_from: '', date_to: '' });
  const [deb, setDeb] = useState(f);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(null);
  const abort = useRef(null);

  useEffect(() => { const t = setTimeout(() => { setDeb(f); setPage(1); }, 300); return () => clearTimeout(t); }, [f]);

  const load = useCallback(async () => {
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    setLoading(true);
    setError('');
    try {
      const res = await api.referrals({ ...deb, page, page_size: PAGE_SIZE }, ctl.signal);
      setRows(res.items); setTotal(res.total); setPages(res.pages);
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (err instanceof ApiError && err.status === 401) { onUnauthorized(); return; }
      setError(err.message || 'Could not load referrals.');
    } finally { if (abort.current === ctl) setLoading(false); }
  }, [deb, page, onUnauthorized]);
  useEffect(() => { load(); }, [load]);

  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  return (
    <>
      <div className="toolbar" role="search">
        <input className="input" placeholder="Referrer name or email" value={f.referrer} onChange={set('referrer')} aria-label="Referrer" />
        <input className="input" placeholder="Recipient name or email" value={f.recipient} onChange={set('recipient')} aria-label="Recipient" />
        <select className="input" value={f.status} onChange={set('status')} aria-label="Status"><option value="">Any status</option>{STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select>
        <select className="input" value={f.closure_status} onChange={set('closure_status')} aria-label="Closed business"><option value="">Any closed-business state</option>{CLOSURE_STATUSES.map((s) => <option key={s} value={s}>{s === 'NONE' ? 'No closed business' : label(s)}</option>)}</select>
        <select className="input" value={f.verification_level} onChange={set('verification_level')} aria-label="Verification level"><option value="">Any verification</option>{LEVELS.map((l, i) => <option key={l} value={i}>{l}</option>)}</select>
        <select className="input" value={f.deal_band} onChange={set('deal_band')} aria-label="Deal value band"><option value="">Any deal value</option>{Object.entries(BANDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className="input" value={f.flagged} onChange={set('flagged')} aria-label="Flagged"><option value="">Flagged or not</option><option value="true">Flagged</option><option value="false">Not flagged</option></select>
        <select className="input" value={f.legacy_unverified} onChange={set('legacy_unverified')} aria-label="Legacy records"><option value="">Verified and legacy</option><option value="true">Legacy (never confirmed by both)</option><option value="false">Not legacy</option></select>
        <input className="input" type="date" value={f.date_from} onChange={set('date_from')} aria-label="Created from" />
        <input className="input" type="date" value={f.date_to} onChange={set('date_to')} aria-label="Created to" />
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      <div className="tablewrap" tabIndex={0} role="region" aria-label="Table (scrolls sideways on small screens)">
        <table className="table">
          <thead><tr><th>Created</th><th>Referrer</th><th>Recipient</th><th>Prospect</th><th>Status</th><th>Meeting</th><th>Closed business</th><th>Actual value</th><th /></tr></thead>
          <tbody>
            {rows.length === 0 && !loading && <tr><td colSpan={9} className="empty">No referrals match these filters.</td></tr>}
            {rows.map((r) => (
              <tr key={r.id} className={r.flagged ? 'row--flag' : ''}>
                <td className="cell__mono">{when(r.created_at)}</td>
                <td><Person p={r.referrer} /></td>
                <td><Person p={r.recipient} /></td>
                <td>{r.prospect_company || r.prospect_name || '—'}<span className="cell__sub"> est. {BANDS[r.estimated_value_range] || '—'}</span></td>
                <td>{label(r.status)}{r.legacy_unverified && <span className="cell__sub" title="Moved on by the old one-member flow; no two-party confirmation"> legacy</span>}</td>
                <td>{r.meeting_confirmations}/2</td>
                <td>{r.closure_status ? <>{label(r.closure_status)}<span className="cell__sub"> L{r.closure_level} · {BANDS[r.closure_band]}</span></> : <span className="cell__sub">—</span>}</td>
                <td className="cell__mono">{inr(r.actual_value_minor)}</td>
                <td>{r.flagged && <span className="rd-warn" title={r.flag_reason}>⚑ </span>}<button type="button" className="btn btn--ghost" onClick={() => setOpen(r.id)}>Review</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="tablewrap__loading">Loading…</div>}
      </div>
      <nav className="pager" aria-label="Pagination">
        <button type="button" className="btn btn--ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1 || loading}>Previous</button>
        <span className="pager__info">Page {page} of {pages} · {total} referral{total === 1 ? '' : 's'}</span>
        <button type="button" className="btn btn--ghost" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages || loading}>Next</button>
      </nav>
      {open && <Detail id={open} onClose={() => setOpen(null)} onUnauthorized={onUnauthorized} onChanged={load} />}
    </>
  );
}
