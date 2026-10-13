import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from './api';
import ReasonModal from './ReasonModal';

// Phase A: what members actually do with connections, needs and help offers. It RECORDS facts. It awards nothing and changes no reward rule.
// Everything in the report is genuine members only; synthetic demo members are excluded and counted separately.

const NEED_STATUS = ['', 'OPEN', 'RESOLVED', 'CANCELLED', 'REMOVED'];
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');
const num = (v) => (v === null || v === undefined ? '—' : typeof v === 'number' ? v.toLocaleString('en-IN') : String(v));

function Tile({ label, value, note }) {
  return <div className="gpx-kpi"><span className="gpx-kpi__label">{label}</span><span className="gpx-kpi__value">{num(value)}</span>{note && <span className="gpx-kpi__note">{note}</span>}</div>;
}

function Group({ title, hint, children }) {
  return <section className="gpx-card"><h3>{title}</h3>{hint && <p className="cell__sub gp-hint">{hint}</p>}<div className="gpx-kpis">{children}</div></section>;
}

export default function Community({ onUnauthorized }) {
  const [days, setDays] = useState('');
  const [rep, setRep] = useState(null);
  const [needs, setNeeds] = useState(null);
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [ask, setAsk] = useState(null);

  const guard = useCallback((err) => {
    if (err instanceof ApiError && err.status === 401) { onUnauthorized(); return; }
    setError(err.message || 'Could not load.');
  }, [onUnauthorized]);

  useEffect(() => { setRep(null); api.communityReport(days).then(setRep).catch(guard); }, [days, guard]);
  const loadNeeds = useCallback(() => api.communityNeeds({ status, page, page_size: 15 }).then(setNeeds).catch(guard), [status, page, guard]);
  useEffect(() => { loadNeeds(); }, [loadNeeds]);

  const c = rep?.connections, n = rep?.needs, h = rep?.help_offers, t = rep?.timing_hours_median, r = rep?.repeat_and_reciprocal;
  return (
    <>
      <header className="gpx-hero">
        <div>
          <p className="gpx-eyebrow">Observation (Phase A)</p>
          <h2 className="gpx-title">Community activity</h2>
          <p className="gpx-lead">
            How members really use <strong>connections, business needs and help offers</strong>. This page only <strong>records and counts</strong>: nothing here earns Growth Points,
            and no reward rule has changed. Figures are <strong>genuine members only</strong>; synthetic demo members are excluded and counted separately.
            An offer is not help: only a poster&apos;s &quot;it helped&quot; confirmation counts as a useful contribution.
          </p>
        </div>
        <div className="gpx-pills">
          <span className="gpx-pill gpx-pill--safe">Points awarded: none</span>
          <span className="gpx-pill gpx-pill--safe">Rule version: unchanged</span>
        </div>
      </header>
      {error && <p className="alert" role="alert">{error}</p>}
      <div className="gpx-actions">
        <label className="cell__sub">Period <select className="input" value={days} onChange={(e) => setDays(e.target.value)}><option value="">Everything recorded</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label>
      </div>
      {!rep ? <p className="cell__sub">Loading…</p> : (
        <>
          <p className="gp-note"><strong>{num(rep.observation.genuine_events_recorded)} genuine events recorded from {num(rep.observation.genuine_members_with_activity)} members.</strong> First: {when(rep.observation.first_event_at)} · Last: {when(rep.observation.last_event_at)} ·
            Excluded: {num(rep.observation.synthetic_events_excluded)} synthetic, {num(rep.observation.backfilled_history_events_excluded)} backfilled history. {rep.observation.note} {rep.observation.baseline}</p>
          <Group title="Connections" hint="Raw requests are activity. Acceptance is the outcome.">
            <Tile label="Requests" value={c.raw_activity.requested} />
            <Tile label="Accepted" value={c.outcomes.accepted} note={`Acceptance rate ${num(c.outcomes.acceptance_rate_percent)}%`} />
            <Tile label="Declined" value={c.raw_activity.declined} /><Tile label="Withdrawn" value={c.raw_activity.withdrawn} /><Tile label="Removed" value={c.raw_activity.removed} />
            <Tile label="Reconnection requests" value={c.raw_activity.reconnection_requests} note={`${num(c.outcomes.reconnections_accepted)} accepted`} />
            <Tile label="Pairs connected now" value={c.outcomes.pairs_connected_now} />
          </Group>
          <Group title="Business needs" hint={n.quality_tracking.note}>
            <Tile label="Published" value={n.raw_activity.published} /><Tile label="Rejected" value={n.raw_activity.rejected} note={Object.entries(n.raw_activity.rejected_by_reason).map(([k, v]) => `${k.toLowerCase().replace(/_/g, ' ')}: ${v}`).join(' · ') || undefined} />
            <Tile label="Cancelled" value={n.raw_activity.cancelled} /><Tile label="Removed by moderators" value={n.raw_activity.removed_by_moderators} />
            <Tile label="Within the proposed monthly limit" value={n.quality_tracking.published_within_proposed_monthly_limit} note={`${num(n.quality_tracking.published_over_proposed_monthly_limit)} over it · ${num(n.quality_tracking.within_limit_and_not_removed_now)} not removed`} />
            <Tile label="Received an offer" value={n.outcomes.needs_that_received_an_offer} />
            <Tile label="Resolved" value={n.outcomes.resolved} note={`${num(n.outcomes.resolved_with_a_credited_helper)} with a credited helper · ${num(n.outcomes.resolved_without_credit)} without`} />
          </Group>
          <Group title="Help offers" hint={h.outcomes.note}>
            <Tile label="Offers made (raw)" value={h.raw_activity.offers} /><Tile label="Accepted by the poster" value={h.progress.accepted} />
            <Tile label="Declined" value={h.raw_activity.declined} /><Tile label="Withdrawn" value={h.raw_activity.withdrawn} />
            <Tile label="Confirmed helpful (outcome)" value={h.outcomes.confirmed_helpful} /><Tile label="Not helpful" value={h.outcomes.not_helpful} />
          </Group>
          <Group title="Speed (median hours)" hint="Only needs that reached each step are counted; the sample size is shown.">
            <Tile label="Publication to first offer" value={t.publication_to_first_offer} note={`n = ${num(t.sample_sizes.first_offer)}`} />
            <Tile label="To first “helpful” confirmation" value={t.publication_to_first_helpful_confirmation} note={`n = ${num(t.sample_sizes.first_helpful)}`} />
            <Tile label="Publication to resolution" value={t.publication_to_resolution} note={`n = ${num(t.sample_sizes.resolution)}`} />
          </Group>
          <Group title="Repeated and reciprocal activity" hint="Counts only. Signals are for a person to look at; nothing is punished automatically.">
            <Tile label="Pairs with 2+ helpful confirmations" value={r.pairs_with_two_or_more_helpful_confirmations} />
            <Tile label="Pairs helping each other" value={r.pairs_helping_each_other} />
            {Object.entries(r.signals_recorded).map(([k, v]) => <Tile key={k} label={k.toLowerCase().replace(/_/g, ' ')} value={v} />)}
          </Group>
        </>
      )}

      <section className="gpx-card">
        <h3>Moderate needs</h3>
        <p className="cell__sub gp-hint">Remove a need that is not genuine, or restore one. Your name, the reason and the time are recorded in the need, the activity history and the audit log.</p>
        <div className="gpx-actions"><label className="cell__sub">Status <select className="input" value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }}>{NEED_STATUS.map((s) => <option key={s} value={s}>{s || 'Any'}</option>)}</select></label></div>
        {!needs ? <p className="cell__sub">Loading…</p> : (
          <div className="tablewrap gpx-tablewrap" tabIndex={0} role="region" aria-label="Table (scrolls sideways on small screens)">
            <table className="table gpx-table">
              <thead><tr><th>Posted</th><th>Poster</th><th>Need</th><th>Status</th><th className="gpx-num">Offers</th><th>Tracked</th><th /></tr></thead>
              <tbody>
                {needs.items.length === 0 && <tr><td colSpan={7} className="empty">No needs.</td></tr>}
                {needs.items.map((x) => (
                  <tr key={x.id}>
                    <td>{when(x.published_at || x.created_at)}</td>
                    <td className="gpx-wide">{x.poster_name || x.poster_email}{x.synthetic && <span className="gpx-tag gpx-tag--plain"> demo</span>}</td>
                    <td className="gpx-wide"><strong>{x.title}</strong><div className="cell__sub">{(x.description || '').slice(0, 140)}{(x.description || '').length > 140 ? '…' : ''}</div>{x.removed_reason && <div className="cell__sub">Removed: {x.removed_reason}</div>}</td>
                    <td><span className="gpx-tag gpx-tag--plain">{x.status}</span></td>
                    <td className="gpx-num">{x.offers}</td>
                    <td>{x.qualifies_for_future_reward === null || x.qualifies_for_future_reward === undefined ? 'legacy' : x.qualifies_for_future_reward ? 'within limit' : (x.quality_note || 'over limit').toLowerCase().replace(/_/g, ' ')}</td>
                    <td>
                      {['OPEN', 'RESOLVED'].includes(x.status) && <button type="button" className="btn btn--danger" onClick={() => setAsk({ title: 'Remove this need', sub: 'It leaves the board. The need, offers and history are kept.', cta: 'Remove', danger: true, onSubmit: async (reason) => { await api.communityRemoveNeed(x.id, reason); loadNeeds(); } })}>Remove</button>}
                      {x.status === 'REMOVED' && <button type="button" className="btn btn--ghost" onClick={() => setAsk({ title: 'Restore this need', sub: 'It returns to the board (or to resolved).', cta: 'Restore', onSubmit: async (reason) => { await api.communityRestoreNeed(x.id, reason); loadNeeds(); } })}>Restore</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {needs && needs.pages > 1 && <div className="pager"><span className="pager__info">{needs.total} total · page {needs.page} of {needs.pages}</span><span><button type="button" className="btn btn--ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>{' '}<button type="button" className="btn btn--ghost" disabled={page >= needs.pages} onClick={() => setPage(page + 1)}>Next</button></span></div>}
      </section>
      {ask && <ReasonModal {...ask} onClose={() => setAsk(null)} />}
    </>
  );
}
