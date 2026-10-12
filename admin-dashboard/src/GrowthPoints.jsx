import { useCallback, useEffect, useState } from 'react';
import { api, ApiError, inr } from './api';
import EmergencyStop from './EmergencyStop';
import ReasonModal from './ReasonModal';

// Growth Points, SHADOW MODE. Everything here is a simulation: points are recorded and analysed, never applied to an invoice or a payment.
// Three different things are always kept apart: shadow EARNING, HYPOTHETICAL redemption, and the REAL financial cost (which must read ₹0).

const PAGE_SIZE = 25;
const SECTIONS = [
  ['overview', 'Overview', 'What members have earned so far, from which activities, and what has been held back by limits.'],
  ['observation', 'Review pack', 'The numbers management needs to decide whether the economy behaves as planned: members, activity, risk, modelled vs actual.'],
  ['gates', 'Launch gates', 'Which conditions for real redemption are met and which are not. Nothing is assumed: this is read from live data.'],
  ['finance', 'Finance (real)', 'Money actually given as discounts. Stays at ₹0 until redemption is approved and switched on.'],
  ['economics', 'Economics', 'The approved model next to what actually happened, per plan and per term length.'],
  ['members', 'Members', 'Every member’s points, their plan and what they could use at renewal.'],
  ['ledger', 'Ledger', 'Every single point movement. Rows are never edited or deleted.'],
  ['flags', 'Review flags', 'Unusual patterns for a person to look at. Nothing is ever punished automatically.'],
];
const EVENT_NAMES = { REFERRAL_ACCEPTED: 'Referral accepted', PROSPECT_CONTACTED: 'Prospect contacted', MEETING_COMPLETED: 'Meeting completed', BUSINESS_CLOSED: 'Business closed', REPEAT_BUSINESS: 'Repeat business', PROFILE_COMPLETED: 'Profile completed' };
const RULE_NAMES = { DAILY_CEILING: 'Daily limit (500)', MONTHLY_CEILING: 'Monthly limit (3,000)', CYCLE_CEILING: 'Subscription-term limit', CATEGORY_SUBCEILING: 'Limit for the kind of reward', PAIR_LOW_ASSURANCE: 'Same two members: quarterly limit', PAIR_CONCENTRATION: 'Repeated deals between the same two', PAIR_RECIPROCAL: 'Reciprocal deals', PAIR_RECIPROCAL_NEEDS_L4: 'Reciprocal deal awaiting approval', FREQUENCY_LIMIT: 'Monthly count limit', REPEAT_LIMIT: 'Repeat-business limit', OUTSIDE_WINDOW: 'Outside the 72-hour window', NO_ACTIVE_CYCLE: 'No active subscription term' };
const LABELS = { inr_minor: 'Money given (₹)', invoices_reduced: 'Invoices reduced', recorded_redemption_discount_minor: 'Discounts on record (₹)', ok: 'Books balance' };
const WORDS = { inr: 'Amount', ok: 'All good', p90: '90th percentile', p95: '95th percentile', id: 'ID', tgl: 'TGL', ll: 'LL' };
function nice(k) {
  if (LABELS[k]) return LABELS[k];
  let t = String(k).replace(/_(paise|minor)$/, ' (₹)').replace(/_percent$/, ' (%)').replace(/_percent_of_/, ' (%) of ').replace(/_paise_/g, ' ₹ ').replace(/_/g, ' ').trim();
  t = WORDS[t.toLowerCase()] || t;
  return t.charAt(0).toUpperCase() + t.slice(1);
}
const when = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');
const isCode = (v) => typeof v === 'string' && /^[A-Z][A-Z0-9_]{2,}$/.test(v);
const isMoney = (key) => /_paise|_minor|_inr$/.test(key);

function fmt(key, v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') {
    if (isMoney(key)) return inr(v);
    if (/_percent$/.test(key)) return `${v.toLocaleString('en-IN')}%`;
    return Number.isInteger(v) ? v.toLocaleString('en-IN') : v.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'string' && /_at$/.test(key)) return when(v);
  if (isCode(v)) return nice(v.toLowerCase());
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function Pill({ value }) {
  const t = String(value).toUpperCase();
  const tone = /^(MET|PASS|PASSED|YES|OK|AVAILABLE|OPEN_OK|REVIEWED)$/.test(t) ? 'ok' : /^(NOT MET|NOT_MET|FAIL|FAILED|NO|REVERSED|VOIDED|EXPIRED|HIGH|CRITICAL)$/.test(t) ? 'bad' : /^(PENDING|OPEN|MEDIUM|WARN|CAPPED|PARTIAL)$/.test(t) ? 'warn' : 'plain';
  return <span className={`gpx-tag gpx-tag--${tone}`}>{fmt('', isCode(value) ? value : String(value))}</span>;
}

function Facts({ title, hint, data, nested }) {
  if (!data) return null;
  const entries = Object.entries(data);
  const flat = entries.filter(([, v]) => v === null || typeof v !== 'object');
  const short = flat.filter(([, v]) => !(typeof v === 'string' && v.length > 46));
  const long = flat.filter(([, v]) => typeof v === 'string' && v.length > 46);
  const subs = entries.filter(([, v]) => v !== null && typeof v === 'object' && !Array.isArray(v));
  const lists = entries.filter(([, v]) => Array.isArray(v));
  const body = (
    <>
      {short.length > 0 && (
        <dl className="gp-facts">
          {short.map(([k, v]) => <div key={k}><dt>{nice(k)}</dt><dd className={typeof v === 'boolean' ? (v ? 'gp-yes' : 'gp-no') : undefined}>{fmt(k, v)}</dd></div>)}
        </dl>
      )}
      {long.map(([k, v]) => <p key={k} className="gp-note"><strong>{nice(k)}.</strong> {fmt(k, v)}</p>)}
      {subs.map(([k, v]) => <Facts key={k} title={nice(k)} data={v} nested />)}
      {lists.map(([k, v]) => <Table key={k} title={nice(k)} rows={v} />)}
    </>
  );
  if (nested) return <div className="gp-sub">{title && <h4 className="gp-sub__title">{title}</h4>}{body}</div>;
  return <section className="gpx-card">{title && <h3>{title}</h3>}{hint && <p className="cell__sub gp-hint">{hint}</p>}{body}</section>;
}

function Cell({ k, v }) {
  if (/_id$|^id$/.test(k)) return v ? <span className="cell__mono" title={String(v)}>{String(v).slice(0, 8)}</span> : '—';
  if (/^(status|state|severity)$|^passed$|^met$/.test(k) && v !== null && v !== undefined && typeof v !== 'object') return <Pill value={v} />;
  if (isCode(v) && /_.*_/.test(v)) return <code className="gpx-code">{v}</code>;
  if (isCode(v)) return <span className="gpx-tag gpx-tag--plain">{fmt(k, v)}</span>;
  return fmt(k, v);
}

function Table({ title, hint, rows, onRow, bare }) {
  if (!rows || rows.length === 0) return title ? <div className="gpx-card gpx-card--quiet"><h3>{title}</h3><p className="cell__sub">None yet.</p></div> : null;
  const cols = Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== 'object' || rows[0][k] === null);
  const num = (c) => rows.every((r) => r[c] === null || r[c] === undefined || typeof r[c] === 'number') && !/_id$|^id$/.test(c);
  const wrap = (
    <div className="tablewrap gpx-tablewrap">
      <table className="table gpx-table">
        <thead><tr>{cols.map((c) => <th key={c} className={num(c) ? 'gpx-num' : undefined}>{nice(c)}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || i} onClick={onRow ? () => onRow(r) : undefined} className={onRow ? 'gpx-row--click' : undefined}>
              {cols.map((c) => <td key={c} className={num(c) ? 'gpx-num' : (typeof r[c] === 'string' && r[c].length > 60 ? 'gpx-wide' : undefined)}><Cell k={c} v={r[c]} /></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  if (bare) return wrap;
  return <section className="gpx-card">{title && <h3>{title}</h3>}{hint && <p className="cell__sub gp-hint">{hint}</p>}{wrap}</section>;
}

export default function GrowthPoints({ onUnauthorized }) {
  const [section, setSection] = useState('overview');
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [ask, setAsk] = useState(null);
  const [notice, setNotice] = useState('');

  const guard = useCallback((err, fallback) => {
    if (err instanceof ApiError && err.status === 401) { onUnauthorized(); return; }
    if (err.name !== 'AbortError') setError(err.message || fallback);
  }, [onUnauthorized]);

  useEffect(() => { api.gpStatus().then(setStatus).catch((e) => guard(e, 'Could not load the shadow-mode status.')); }, [guard]);

  const run = (title, sub, fn, cta) => setAsk({
    title, sub, cta,
    onSubmit: async (reason) => { const res = await fn(reason); setNotice(`${title}: ${JSON.stringify(res)}`); },
  });

  return (
    <>
      <header className="gpx-hero">
        <div>
          <p className="gpx-eyebrow">Rewards programme</p>
          <h2 className="gpx-title">Growth Points</h2>
          <p className="gpx-lead">
            Growth Points reward members for <strong>verified business outcomes</strong> from networking: an accepted referral, a confirmed meeting, a closed deal. They are never given for clicks.
            Members will be able to use them as a <strong>discount on a subscription renewal</strong> (at most 15% of the renewal price). Until that is approved, points are only <strong>recorded and analysed</strong> here:
            they change no invoice, payment or subscription.
          </p>
          <details className="gpx-how">
            <summary>How points are earned</summary>
            <table className="gpx-mini">
              <tbody>
                <tr><td>Referral accepted</td><td>30 for the referrer (45 with a direct introduction), 15 for the recipient</td></tr>
                <tr><td>Prospect contacted</td><td>15 for the recipient (within 72 hours)</td></tr>
                <tr><td>Meeting completed</td><td>45 for the referrer, 60 for the recipient (both must confirm)</td></tr>
                <tr><td>Business closed</td><td>210 to 1,890 for the referrer (by deal size), 30% of the pool to the recipient</td></tr>
                <tr><td>Repeat business</td><td>Half of the closed-business reward, once per prospect per quarter</td></tr>
                <tr><td>Profile completed</td><td>75, once</td></tr>
                <tr><td colSpan={2}>Limits: 500 a day, 3,000 a month, and 12% of the plan price per subscription term. Creating a referral earns nothing by itself.</td></tr>
              </tbody>
            </table>
          </details>
        </div>
        <div className="gpx-pills" aria-label="Current status">
          <span className={`gpx-pill ${status?.shadow_mode ? 'gpx-pill--on' : 'gpx-pill--off'}`}>Recording points: {status ? (status.shadow_mode ? 'ON' : 'OFF') : '…'}</span>
          <span className={`gpx-pill ${status?.member_preview ? 'gpx-pill--on' : 'gpx-pill--off'}`}>Members can see points: {status ? (status.member_preview ? 'YES (preview)' : 'NO') : '…'}</span>
          <span className="gpx-pill gpx-pill--safe">Redemption: {status ? (status.redemption_enabled ? 'ON' : 'OFF') : '…'}</span>
          <span className="gpx-pill gpx-pill--safe">Real money effect: ₹{status ? status.real_financial_effect_inr : '…'}</span>
        </div>
      </header>
      {status && !status.shadow_mode && (
        <p className="gpx-warn" role="alert"><strong>Points are not being recorded.</strong> No member earns anything while recording is off. Set <code>GROWTH_POINTS_SHADOW_MODE=true</code> in the backend settings and restart, then run <em>Catch up</em> to record what already happened.</p>
      )}
      <nav className="gpx-nav" aria-label="Growth Points sections">
        {SECTIONS.map(([id, name]) => <button key={id} type="button" aria-current={section === id ? 'page' : undefined} className={`gpx-navbtn${section === id ? ' gpx-navbtn--on' : ''}`} onClick={() => setSection(id)}>{name}</button>)}
      </nav>
      <p className="gpx-desc">{SECTIONS.find(([id]) => id === section)?.[2]}</p>
      <div className="gpx-actions">
        <a className="btn btn--ghost" href={api.gpExportUrl('csv')}>Download ledger (CSV)</a>
        <a className="btn btn--ghost" href={api.gpExportUrl('json')}>Download ledger (JSON)</a>
        <button type="button" className="btn btn--ghost" title="Records points that were missed, expires old ones and reconciles" onClick={() => run('Catch up', 'Records any points the live hooks missed (for example while recording was off), expires what is due and checks the books. Safe to repeat; shadow rows only.', api.gpSweep, 'Catch up')}>Catch up</button>
        <button type="button" className="btn btn--ghost" title="Look for unusual patterns" onClick={() => run('Scan for unusual patterns', 'Raises review items only. It never changes a member’s points.', api.gpScan, 'Run scan')}>Scan for unusual patterns</button>
        <button type="button" className="btn btn--ghost" title="Check that every balance matches the ledger" onClick={() => run('Check the books', 'Checks that every member’s balance equals the sum of their ledger rows and rebuilds the cached balance. The ledger itself is never touched.', api.gpReconcile, 'Check')}>Check the books</button>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      {notice && <p className="cell__sub" role="status">{notice}</p>}
      {section === 'overview' && <Overview guard={guard} status={status} />}
      {section === 'observation' && <Observation guard={guard} />}
      {section === 'gates' && <Gates guard={guard} />}
      {section === 'finance' && <Finance guard={guard} />}
      {section === 'economics' && <Economics guard={guard} />}
      {section === 'members' && <Members guard={guard} />}
      {section === 'ledger' && <Ledger guard={guard} />}
      {section === 'flags' && <Flags guard={guard} run={run} />}
      {ask && <ReasonModal {...ask} onClose={() => setAsk(null)} />}
    </>
  );
}

function useLoad(fn, guard, deps) {
  const [data, setData] = useState(null);
  useEffect(() => {
    const ctl = new AbortController();
    setData(null);
    fn(ctl.signal).then(setData).catch((e) => guard(e, 'Could not load this view.'));
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return data;
}

function Kpi({ label, value, note, tone }) {
  return <div className={`gpx-kpi${tone ? ` gpx-kpi--${tone}` : ''}`}><span className="gpx-kpi__label">{label}</span><span className="gpx-kpi__value">{value}</span>{note && <span className="gpx-kpi__note">{note}</span>}</div>;
}

function Overview({ guard, status }) {
  const s = useLoad(() => api.gpSummary(), guard, []);
  if (!s) return <p className="cell__sub">Loading…</p>;
  const e = s.shadow_earning || {};
  const h = s.hypothetical_redemption || {};
  const r = s.real_financial_cost || {};
  const rows = (e.by_event_type || []).map((x) => ({ Activity: EVENT_NAMES[x.event_type] || x.event_type, Rewards: x.rewards_recorded, 'Points earned': x.points_issued, 'Held back by limits': x.points_capped, Reversed: x.points_voided_or_reversed, Expired: x.points_expired }));
  const caps = (e.capped?.by_rule || []).map((x) => ({ Limit: RULE_NAMES[x.capped_by] || x.capped_by || '—', Rewards: x.rewards, 'Points held back': x.points_capped }));
  const empty = !e.points_issued;
  return (
    <>
      <section className="gpx-kpis" aria-label="Key numbers">
        <Kpi label="Points recorded" value={(e.points_issued || 0).toLocaleString('en-IN')} note="All members (demo members included), all time. Shadow: not redeemable." />
        <Kpi label="Members who earned" value={e.members_with_points || 0} note={`Average ${e.average_points_per_member || 0} · median ${e.median_points_per_member || 0} · best ${(e.max_points_one_member || 0).toLocaleString('en-IN')}`} />
        <Kpi label="Could be used at renewal" value={inr(h.hypothetical_redemption_liability_paise)} note="Hypothetical: what members could take off a renewal today." tone="warn" />
        <Kpi label="Money actually given" value={inr(r.inr_minor)} note={r.ok ? 'Books balance' : 'Check the books'} tone="ok" />
      </section>
      {empty && (
        <div className="gpx-empty" role="status">
          <h3>No points recorded yet</h3>
          <p>{status && !status.shadow_mode ? 'Recording is off, so nothing is being earned. Turn on GROWTH_POINTS_SHADOW_MODE, restart, then press “Catch up” to record activity that already happened.' :
            'Points appear after something verified happens: a referral is accepted, a meeting is confirmed by both members, or a closed deal is verified. Members also need an active subscription or Season 1 access. Creating a referral earns nothing by itself.'}</p>
        </div>
      )}
      <Card title="Points by activity" sub="What members were rewarded for.">
        <Table rows={rows} bare />
      </Card>
      {caps.length > 0 && <Card title="What held rewards back" sub="Limits that reduced a reward. The original amount is always kept on the ledger row."><Table rows={caps} bare /></Card>}
      <Card title="Waiting versus usable" sub="Quick rewards wait 7 days; verified deals are usable at once.">
        <dl className="gpx-pairs">
          <div><dt>Waiting (pending)</dt><dd>{(h.pending_points || 0).toLocaleString('en-IN')} points</dd></div>
          <div><dt>Usable now</dt><dd>{(h.available_points || 0).toLocaleString('en-IN')} points</dd></div>
          <div><dt>Worth at most (hypothetical)</dt><dd>{inr(h.maximum_potential_liability_paise)}</dd></div>
        </dl>
        <p className="cell__sub">{h.label}</p>
      </Card>
    </>
  );
}

function Card({ title, sub, children }) {
  return <section className="gpx-card"><h3>{title}</h3>{sub && <p className="cell__sub">{sub}</p>}{children}</section>;
}

function Observation({ guard }) {
  const rv = useLoad(() => api.gpReview(), guard, []);
  if (!rv) return <p className="cell__sub">Loading…</p>;
  const ob = rv.observation;
  return (
    <>
      <p className="cell__sub"><strong>Gate A suggestion: {rv.gate_a.suggested_status}.</strong> {rv.gate_a.note} <a href={api.gpReviewUrl()}>Download the review (Markdown)</a></p>
      <Facts title="Members" hint="Who is taking part. Demo (synthetic) members are excluded from these counts." data={rv.dashboard.member_metrics} />
      <Facts title="Activity" hint="What members did that can earn points." data={rv.dashboard.activity_metrics} />
      <Facts title="Rewards" hint="How many rewards were recorded and how many were held back, reversed or expired." data={rv.dashboard.reward_metrics} />
      <Facts title="Risk signals" hint="Patterns for a person to look at. Nothing is ever punished automatically." data={rv.dashboard.risk_metrics} />
      <Facts title="Economics (hypothetical)" data={rv.dashboard.economic_metrics} />
      <Table title="Exit criteria (management answers)" rows={rv.exit_criteria} />
      <p className="cell__sub">{rv.proposed_model_changes_note}</p>
      <Table title="Proposed model changes (never applied automatically)" rows={rv.proposed_model_changes} />
      <p className="cell__sub">The observation period has no automatic end date: management decides when there is enough data to compare MODELLED with ACTUAL. Aggregates only; nothing here is visible to members.</p>
      <Facts title="Data collected so far" data={ob.sufficiency} />
      <Facts title="Observed" data={ob.observed} />
      <Facts title="Modelled vs actual (compare per member-month, never raw totals)" data={ob.modelled_vs_actual} />
      <Facts title="Success metrics" data={ob.success_metrics} />
      <Facts title="Real financial cost (measured)" data={ob.real_financial_cost} />
    </>
  );
}

function Finance({ guard }) {
  const f = useLoad(() => api.gpFinance(), guard, []);
  const st = useLoad(() => api.gpRedemptionState(), guard, []);
  if (!f || !st) return <p className="cell__sub">Loading…</p>;
  return (
    <>
      <section className="gpx-card">
        <h3>Where redemption stands</h3>
        <p className="cell__sub gp-hint">This is the real economy: money actually given as discounts. It is never added to the hypothetical or modelled numbers.</p>
        <dl className="gp-facts">
          <div><dt>Redemption switch</dt><dd className={st.flag_enabled ? 'gp-yes' : 'gp-no'}>{st.flag_enabled ? 'On' : 'Off'}</dd></div>
          <div><dt>Emergency stop</dt><dd className={st.kill_switch_on ? 'gp-no' : 'gp-yes'}>{st.kill_switch_on ? 'Stopped' : 'Not pressed'}</dd></div>
          <div><dt>Rollout stage</dt><dd>{nice(st.rollout_stage)}</dd></div>
          <div><dt>Redeemable from</dt><dd>{st.redeemable_from || 'Not set'}</dd></div>
        </dl>
        {!st.redeemable_from && <p className="gp-note">Nothing is redeemable until management records an approved date. Points earned before that date never become redeemable.</p>}
      </section>
      <EmergencyStop guard={guard} />
      <Facts title="Realized (real discounts given)" hint="Money actually taken off invoices. Zero while redemption is off." data={f.realized} />
      <Facts title="Points" hint="Points that were redeemed, restored or expired through real redemption." data={f.points} />
      <Facts title="Outstanding potential liability (not incurred)" data={f.outstanding_potential_liability} />
    </>
  );
}

function Gates({ guard }) {
  const g = useLoad(() => api.gpGates(), guard, []);
  if (!g) return <p className="cell__sub">Loading…</p>;
  return (
    <>
      <section className="gpx-card">
        <h3>Can real redemption start?</h3>
        <p className="cell__sub gp-hint">{g.note}</p>
        <dl className="gp-facts">
          <div><dt>Build of the redemption feature may start</dt><dd className={g.may_start_phase_2_build ? 'gp-yes' : 'gp-no'}>{g.may_start_phase_2_build ? 'Yes' : 'Not yet'}</dd></div>
          <div><dt>Redemption can be switched on</dt><dd className={g.redemption_can_be_enabled ? 'gp-yes' : 'gp-no'}>{g.redemption_can_be_enabled ? 'Yes' : 'No'}</dd></div>
          <div><dt>Real money effect</dt><dd>₹{g.real_financial_effect_inr}</dd></div>
        </dl>
      </section>
      <Table title="Gate A: is there enough real data?" hint="Counts real members only. Demo members never count." rows={g.gate_a.items} />
      <Table title="Environment" hint="Settings that must be correct before launch." rows={g.environment.items} />
      <Table title="Before real launch" hint="Approvals and checks that management must complete." rows={g.phase_3_prerequisites.items} />
    </>
  );
}

function Economics({ guard }) {
  const eco = useLoad(() => api.gpEconomics(), guard, []);
  if (!eco) return <p className="cell__sub">Loading…</p>;
  return (
    <>
      <p className="gp-note">The modelled 400-member economy is a projection. “Actual” is what the programme has recorded. They are shown side by side and never mixed.</p>
      <Facts title="Modelled (400 members, approved assumptions)" data={eco.modelled} />
      <Facts title="Actual (recorded so far)" data={eco.actual_shadow} />
      <Facts title="Hypothetical redemption" data={eco.hypothetical_redemption} />
      <Facts title="Real financial cost" data={eco.real_financial_cost} />
      <Facts title="Unit economics" data={eco.unit_economics} />
      <Table title="Plan comparison (cycle-normalised)" rows={eco.plan_comparison} />
    </>
  );
}

function Pager({ page, pages, total, setPage }) {
  return (
    <div className="pager">
      <span className="pager__info">{total} total · page {page} of {pages}</span>
      <span>
        <button type="button" className="btn btn--ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>{' '}
        <button type="button" className="btn btn--ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
      </span>
    </div>
  );
}

function Members({ guard }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [deb, setDeb] = useState('');
  const [open, setOpen] = useState(null);
  useEffect(() => { const t = setTimeout(() => { setDeb(search); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  const res = useLoad((signal) => api.gpMembers({ page, page_size: PAGE_SIZE, search: deb }, signal), guard, [page, deb]);
  const detail = useLoad(() => (open ? api.gpMember(open) : Promise.resolve(null)), guard, [open]);
  if (open) {
    return (
      <>
        <button type="button" className="btn btn--ghost" onClick={() => setOpen(null)}>← All members</button>
        {!detail ? <p className="cell__sub">Loading…</p> : (
          <>
            <h3 className="gp-block__title">{detail.member.email}</h3>
            <Facts title="Shadow snapshot" data={detail.snapshot} />
            <Table title="Lots (points with their remaining value and state)" rows={detail.lots} />
            <Table title="Ledger" rows={detail.ledger} />
            <Table title="Review flags" rows={detail.flags} />
          </>
        )}
      </>
    );
  }
  return (
    <>
      <div className="toolbar" role="search"><input className="input" placeholder="Search by name or email" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search members" /></div>
      {!res ? <p className="cell__sub">Loading…</p> : (
        <>
          <Table rows={res.items.map(({ member_id, ...rest }) => ({ id: member_id, ...rest }))} onRow={(r) => setOpen(r.id)} />
          <Pager page={res.page} pages={res.pages} total={res.total} setPage={setPage} />
          <p className="cell__sub">{res.disclaimer}</p>
        </>
      )}
    </>
  );
}

function Ledger({ guard }) {
  const [page, setPage] = useState(1);
  const [f, setF] = useState({ event_type: '', status: '', capped_by: '', entry_type: '' });
  const res = useLoad((signal) => api.gpLedger({ ...f, page, page_size: 50 }, signal), guard, [page, f]);
  const set = (k) => (e) => { setPage(1); setF((x) => ({ ...x, [k]: e.target.value })); };
  const opt = (name, k, values) => <select className="input" value={f[k]} onChange={set(k)} aria-label={name}><option value="">{name}</option>{values.map((v) => <option key={v} value={v}>{v}</option>)}</select>;
  return (
    <>
      <div className="toolbar">
        {opt('Any event', 'event_type', ['REFERRAL_ACCEPTED', 'PROSPECT_CONTACTED', 'MEETING_COMPLETED', 'BUSINESS_CLOSED', 'REPEAT_BUSINESS', 'PROFILE_COMPLETED'])}
        {opt('Any entry type', 'entry_type', ['EARN', 'VOID', 'REVERSAL', 'EXPIRY'])}
        {opt('Any status', 'status', ['PENDING', 'AVAILABLE', 'CAPPED', 'VOIDED', 'REVERSED', 'EXPIRED'])}
        {opt('Any cap rule', 'capped_by', ['PAIR_LOW_ASSURANCE', 'PAIR_CONCENTRATION', 'PAIR_RECIPROCAL', 'PAIR_RECIPROCAL_NEEDS_L4', 'FREQUENCY_LIMIT', 'REPEAT_LIMIT', 'CATEGORY_SUBCEILING', 'DAILY_CEILING', 'MONTHLY_CEILING', 'CYCLE_CEILING', 'NO_ACTIVE_CYCLE', 'OUTSIDE_WINDOW'])}
      </div>
      {!res ? <p className="cell__sub">Loading…</p> : (
        <>
          <Table rows={res.items.map(({ id, created_at, member_id, entry_type, event_type, points_delta, requested_points, capped_points, capped_by, status, verification_level, assurance, rule_version }) => (
            { id, created_at, member_id, entry_type, event_type, points_delta, requested_points, capped_points, capped_by, status, verification_level, assurance, rule_version }))} />
          <Pager page={res.page} pages={res.pages} total={res.total} setPage={setPage} />
        </>
      )}
    </>
  );
}

function Flags({ guard, run }) {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('OPEN');
  const [tick, setTick] = useState(0);
  const res = useLoad((signal) => api.gpFlags({ page, page_size: 50, status }, signal), guard, [page, status, tick]);
  return (
    <>
      <p className="cell__sub">Flags are signals for a human to look at. Raising one never changes a member’s points or account.</p>
      <div className="toolbar"><select className="input" value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} aria-label="Status"><option value="OPEN">Open</option><option value="REVIEWED">Reviewed</option><option value="DISMISSED">Dismissed</option><option value="">Any</option></select></div>
      {!res ? <p className="cell__sub">Loading…</p> : (
        <>
          <div className="tablewrap">
            <table className="table">
              <thead><tr><th>Raised</th><th>Kind</th><th>Severity</th><th>Member</th><th>Detail</th><th>Status</th><th /></tr></thead>
              <tbody>
                {res.items.length === 0 && <tr><td colSpan={7} className="empty">Nothing to review.</td></tr>}
                {res.items.map((f) => (
                  <tr key={f.id}>
                    <td>{when(f.created_at)}</td><td>{nice(f.kind)}</td><td>{f.severity || '—'}</td>
                    <td className="cell__mono">{(f.member_id || '').slice(0, 8) || '—'}</td>
                    <td className="cell__sub">{f.summary || (f.details ? JSON.stringify(f.details) : '')}</td>
                    <td>{f.status}</td>
                    <td>{f.status === 'OPEN' && (
                      <>
                        <button type="button" className="btn btn--ghost" onClick={() => run('Mark reviewed', 'Record that you looked at this signal.', async (reason) => { await api.gpReviewFlag(f.id, 'REVIEWED', reason); setTick((t) => t + 1); return { id: f.id, status: 'REVIEWED' }; }, 'Mark reviewed')}>Reviewed</button>{' '}
                        {f.kind === 'REVERSAL_NEEDS_REVIEW' && (
                          <><button type="button" className="btn btn--danger" onClick={() => run('Reverse these points', 'Adds a NEW negative ledger row; the original is never edited. Use only when the deal or referral is still invalid.', async (reason) => { const r = await api.gpApplyReversal(f.id, reason); setTick((t) => t + 1); return r; }, 'Reverse')}>Reverse points</button>{' '}</>
                        )}
                        <button type="button" className="btn btn--ghost" onClick={() => run('Dismiss', 'Record that this signal is a false alarm.', async (reason) => { await api.gpReviewFlag(f.id, 'DISMISSED', reason); setTick((t) => t + 1); return { id: f.id, status: 'DISMISSED' }; }, 'Dismiss')}>Dismiss</button>
                      </>
                    )}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={res.page} pages={res.pages} total={res.total} setPage={setPage} />
        </>
      )}
    </>
  );
}
