import { useCallback, useEffect, useRef, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { shortDate, shortAgo } from '../../lib/format';
import { showToast } from '../../components/AppShell';
import NetTabs from './NetTabs';
import ImageSlot from '../../components/ImageSlot';
import GiveReferral from './GiveReferral';
import VerificationStrip from './ReferralVerification';
import {
  ACTION_LABEL, CONTACT_METHOD_LABEL, INTRO_LABEL, PERMISSION_LABEL, PRIMARY_ACTIONS, QUALITY_LABEL, RELATIONSHIP_LABEL,
  STAGES, STAGE_HELP, STATUS_LABEL, URGENCY_LABEL, VALUE_LABEL, VIEWS, formatPhone,
} from '../../lib/referralMeta';
import { CATEGORIES } from '../../data/categories';

const PAGE = 20;
const DEAD = new Set(['DECLINED', 'CANCELLED', 'CLOSED']);
const CATEGORY_NAME = Object.fromEntries(CATEGORIES.map((c) => [c.code, c.name]));

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function Stepper({ status }) {
  if (DEAD.has(status)) {
    return <span className={`rf-state rf-state--${status === 'DECLINED' ? 'danger' : 'muted'}`}>{STATUS_LABEL[status]}</span>;
  }
  const idx = Math.max(0, STAGES.indexOf(status));
  return (
    <div className="rf-steps" role="img" aria-label={`Stage ${idx + 1} of ${STAGES.length}: ${STATUS_LABEL[status]}`}>
      <ol>{STAGES.map((s, i) => <li key={s} className={i < idx ? 'done' : i === idx ? 'now' : ''} />)}</ol>
      <span>{STATUS_LABEL[status]}</span>
    </div>
  );
}

function Detail({ d }) {
  const rows = [
    ['Contact', d.prospect_name],
    ['Phone', d.prospect_phone && <a key="tel" href={`tel:${d.prospect_phone}`}>{formatPhone(d.prospect_phone)}</a>],
    ['Email', d.prospect_email && <a key="mail" href={`mailto:${d.prospect_email}`}>{d.prospect_email}</a>],
    ['Business', d.prospect_company],
    ['Role', d.prospect_role],
    ['Location', d.prospect_location],
    ['Prefers', CONTACT_METHOD_LABEL[d.preferred_contact_method]],
    ['Known as', d.relationship === 'OTHER' && d.relationship_other ? `Other — ${d.relationship_other}` : RELATIONSHIP_LABEL[d.relationship]],
    ['May be contacted', PERMISSION_LABEL[d.contact_permission]],
  ].filter(([, v]) => v);
  const meta = [
    ['Type', CATEGORY_NAME[d.category]],
    ['Timing', URGENCY_LABEL[d.urgency]],
    ['Value', d.value_range && d.value_range !== 'UNKNOWN' ? VALUE_LABEL[d.value_range] : null],
    ['Introduction', [INTRO_LABEL[d.intro_method], d.intro_call_preference].filter(Boolean).join(' — ')],
    ['Referral quality', QUALITY_LABEL[d.quality]],
    ['Submitted', shortDate(d.created_at)],
    ['Last update', d.last_action_at ? shortDate(d.last_action_at) : null],
  ].filter(([, v]) => v);
  return (
    <div className="rf-detail">
      <div>
        <h4>Prospective customer</h4>
        <dl>{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      </div>
      <div>
        <h4>Opportunity</h4>
        <p className="rf-detail-text">{d.opportunity_description || d.business_need}</p>
        {d.note && <p className="rf-detail-note"><strong>Note:</strong> {d.note}</p>}
        <dl>{meta.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      </div>
    </div>
  );
}

function ReferralCard({ r, expanded, onToggle, busy, onAct, onRefresh }) {
  const iAmRecipient = r.my_role === 'receiver';
  const name = (iAmRecipient ? r.giver_name : r.receiver_name) || 'TGL member';
  const business = iAmRecipient ? r.giver_business : r.receiver_business;
  const photo = iAmRecipient ? r.giver_photo_url : r.receiver_photo_url;
  const allowed = r.allowed_actions || [];
  const primary = PRIMARY_ACTIONS.find((a) => allowed.includes(a));
  const secondary = allowed.filter((a) => a !== primary);
  const [detail, setDetail] = useState(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!expanded) return undefined;
    let live = true;
    setLoadError(false);
    api.referral(r.id).then((d) => live && setDetail(d)).catch(() => live && setLoadError(true));
    return () => { live = false; };
  }, [expanded, r.id, r.updated_at]);

  const prospect = [r.prospect_name, r.prospect_company].filter(Boolean).join(' · ');
  return (
    <li className={`rf-card ${primary && !DEAD.has(r.status) ? 'has-action' : ''}`} id={`referral-${r.id}`}>
      <div className="rf-card-head">
        <ImageSlot shape="circle" initial={name} src={photo} style={{ width: 44, height: 44 }} fontSize={16} />
        <div className="rf-who">
          <p className="rf-dir">{iAmRecipient ? 'Referred to you by' : 'Referred to'}</p>
          <h3>{name}</h3>
          <p className="rf-biz">{business}</p>
        </div>
        <span className="rf-when" title={shortDate(r.created_at)}>{shortAgo(r.updated_at)} ago</span>
      </div>
      {prospect && <p className="rf-prospect"><span>Prospect</span> {prospect}</p>}
      <p className="rf-need">{r.business_need}</p>
      <div className="rf-chips">
        {r.urgency && <span className="rf-chip">{URGENCY_LABEL[r.urgency]}</span>}
        {r.intro_method && <span className="rf-chip">{INTRO_LABEL[r.intro_method]}</span>}
        {r.quality && <span className="rf-chip rf-chip--q">{QUALITY_LABEL[r.quality]}</span>}
        {r.category && CATEGORY_NAME[r.category] && <span className="rf-chip">{CATEGORY_NAME[r.category]}</span>}
      </div>
      <VerificationStrip r={r} onChanged={() => onRefresh(r.id)} />
      <div className="rf-card-foot">
        <Stepper status={r.status} />
        <div className="rf-card-actions">
          {secondary.map((a) => (
            <button key={a} type="button" className="rf-link-btn" disabled={busy} onClick={() => onAct(r, a)}>{ACTION_LABEL[a]}</button>
          ))}
          {primary && <button type="button" className="rf-btn rf-btn--dark" disabled={busy} onClick={() => onAct(r, primary)}>{busy ? 'Updating…' : ACTION_LABEL[primary]}</button>}
          {!primary && r.status === 'GIVEN' && !iAmRecipient && <span className="rf-wait">Waiting for {name.split(' ')[0]} to respond</span>}
          <button type="button" className="rf-link-btn rf-toggle" aria-expanded={expanded} onClick={onToggle}>{expanded ? 'Hide details' : 'View details'}</button>
        </div>
      </div>
      {expanded && (loadError ? <p className="rf-error">Couldn’t load the details. Try again.</p> : detail ? <Detail d={detail} /> : <p className="rf-wait">Loading details…</p>)}
    </li>
  );
}

export default function Referrals({ openGiveOnMount }) {
  const [view, setView] = useState('all');
  const [stage, setStage] = useState('');
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState(false);
  const [summary, setSummary] = useState(null);
  const [expandedId, setExpandedId] = useState('');
  const [giveOpen, setGiveOpen] = useState(!!openGiveOnMount);
  const [stashedTarget, setStashedTarget] = useState(null);
  const [busyId, setBusyId] = useState('');
  const seq = useRef(0);

  useEffect(() => {
    const stashed = sessionStorage.getItem('tgl_referral_target');
    if (stashed) {
      try {
        setStashedTarget(JSON.parse(stashed));
        setGiveOpen(true);
      } catch {
        // ignore malformed stash
      }
      sessionStorage.removeItem('tgl_referral_target');
    }
  }, []);

  const loadSummary = useCallback(() => api.referralSummary().then(setSummary).catch(() => {}), []);

  // One page at a time: PAGE + 1 rows are requested so "is there more?" needs no count query.
  const loadPage = useCallback((offset) => {
    const mine = ++seq.current;
    if (offset === 0) setLoading(true); else setLoadingMore(true);
    setFailed(false);
    return api.referrals({ view, stage, limit: PAGE + 1, offset })
      .then((rows) => {
        if (mine !== seq.current) return;
        setHasMore(rows.length > PAGE);
        setItems((prev) => (offset === 0 ? rows.slice(0, PAGE) : [...prev, ...rows.slice(0, PAGE)]));
      })
      .catch(() => { if (mine === seq.current) { setFailed(true); if (offset === 0) setItems([]); } })
      .finally(() => { if (mine === seq.current) { setLoading(false); setLoadingMore(false); } });
  }, [view, stage]);

  useEffect(() => { loadPage(0); }, [loadPage]);
  useEffect(() => { loadSummary(); }, [loadSummary]);

  async function act(r, nextStatus) {
    setBusyId(r.id);
    try {
      const updated = await api.updateReferral(r.id, nextStatus);
      setItems((prev) => prev.map((x) => (x.id === r.id ? { ...x, ...updated } : x)));
      showToast(`Referral ${STATUS_LABEL[updated.status].toLowerCase()}.`);
      loadSummary();
    } catch (err) {
      showToast(err.message || 'Could not update this referral.');
      loadPage(0);
    } finally {
      setBusyId('');
    }
  }

  // After a meeting or closure action: take the server's fresh copy of that one referral.
  const refreshOne = useCallback(async (id) => {
    const fresh = await api.referral(id);
    setItems((prev) => prev.map((x) => (x.id === id ? { ...x, ...fresh } : x)));
    loadSummary();
  }, [loadSummary]);

  const counts = summary ? { all: summary.total, sent: summary.sent, received: summary.received, in_progress: summary.in_progress, converted: summary.converted, closed: summary.closed } : {};
  const byStatus = summary?.by_status || {};
  const awaiting = summary?.awaiting_response || 0;
  const filtered = view !== 'all' || stage;

  function backToList() {
    setGiveOpen(false);
    if (window.location.pathname !== '/app/networking/referrals') go('/app/networking/referrals', { replace: true });
  }

  function viewReferral(ref) {
    backToList();
    setView('all');
    setStage('');
    setExpandedId(ref.id);
    // The referral may sit beyond the first page (e.g. an older duplicate): make sure it is on screen.
    loadPage(0)
      .then(() => api.referral(ref.id))
      .then((d) => setItems((prev) => (prev.some((x) => x.id === d.id) ? prev : [d, ...prev])))
      .catch(() => {});
    loadSummary();
    requestAnimationFrame(() => setTimeout(() => document.getElementById(`referral-${ref.id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 400));
  }

  return (
    <>
      <NetTabs active="Referrals" />
      <main className="rf">
        <div className="rf-top">
          <div>
            <h1>Referrals</h1>
            <p>Business you refer to fellow members, and business they refer to you — tracked from the first hello to revenue.</p>
          </div>
          <button type="button" className="rf-btn rf-btn--primary" onClick={() => setGiveOpen(true)}>
            <Icon id="i-plus" size={15} /> Give referral
          </button>
        </div>

        <nav className="rf-pipeline" aria-label="Filter by stage">
          {STAGES.map((s) => (
            <button key={s} type="button" className={`${stage === s ? 'is-on' : ''} ${!byStatus[s] ? 'is-zero' : ''}`} aria-pressed={stage === s} onClick={() => setStage(stage === s ? '' : s)}>
              <span className="rf-node">{byStatus[s] || 0}</span>
              <span className="rf-stage">{STATUS_LABEL[s]}</span>
            </button>
          ))}
        </nav>

        <div className="rf-layout">
          <section className="rf-main">
            <div className="rf-tabs" role="tablist" aria-label="Referral lists">
              {VIEWS.map(([key, label]) => (
                <button key={key} type="button" role="tab" aria-selected={view === key} className={view === key ? 'is-on' : ''} onClick={() => setView(key)}>
                  {label}{summary && <span>{counts[key]}</span>}
                </button>
              ))}
              {stage && (
                <button type="button" className="rf-filter-chip" onClick={() => setStage('')}>
                  {STATUS_LABEL[stage]} <Icon id="i-x" size={12} />
                </button>
              )}
            </div>

            {awaiting > 0 && (
              <p className="rf-nudge"><Icon id="i-bell" size={15} /> <strong>{awaiting}</strong> {awaiting === 1 ? 'referral is' : 'referrals are'} waiting for your response.</p>
            )}

            {loading ? (
              <div className="rf-list">{[0, 1].map((i) => <div key={i} className="rf-card rf-card--sk" aria-hidden="true"><span className="rf-sk rf-sk--a" /><span className="rf-sk-l"><span className="rf-sk" /><span className="rf-sk rf-sk--s" /></span></div>)}</div>
            ) : failed && items.length === 0 ? (
              <div className="rf-empty rf-empty--sm" role="alert">
                <h2>Couldn’t load referrals</h2>
                <p>Check your connection and try again.</p>
                <button type="button" className="rf-btn" onClick={() => loadPage(0)}>Try again</button>
              </div>
            ) : items.length === 0 ? (
              !filtered && summary?.total === 0 ? (
                <div className="rf-empty">
                  <span className="rf-empty-icon"><Icon id="i-send" size={24} /></span>
                  <h2>Your first referral starts here</h2>
                  <p>Introduce a business opportunity to a fellow member. When it turns into business, you both build Trust. Growth Points are coming soon.</p>
                  <button type="button" className="rf-btn rf-btn--primary" onClick={() => setGiveOpen(true)}><Icon id="i-plus" size={15} /> Give a referral</button>
                </div>
              ) : (
                <div className="rf-empty rf-empty--sm">
                  <h2>Nothing here</h2>
                  <p>{stage ? 'No referrals at this stage. Try another, or clear the filter.' : 'No referrals match this list yet.'}</p>
                  {filtered && <button type="button" className="rf-btn" onClick={() => { setView('all'); setStage(''); }}>Show all referrals</button>}
                </div>
              )
            ) : (
              <>
                <ul className="rf-list">
                  {items.map((r) => (
                    <ReferralCard key={r.id} r={r} expanded={expandedId === r.id} onToggle={() => setExpandedId(expandedId === r.id ? '' : r.id)} busy={busyId === r.id} onAct={act} onRefresh={refreshOne} />
                  ))}
                </ul>
                {hasMore && (
                  <div className="rf-more-wrap">
                    <button type="button" className="rf-btn" disabled={loadingMore} onClick={() => loadPage(items.length)}>{loadingMore ? 'Loading…' : 'Load more'}</button>
                  </div>
                )}
                {failed && <p className="rf-error" role="alert">Couldn’t load more. Try again.</p>}
              </>
            )}
          </section>

          <aside className="rf-side">
            <section className="rf-panel">
              <h2>Who’s who in a referral</h2>
              <ul className="rf-roles">
                <li><b>You</b><span>give the referral</span></li>
                <li><b>TGL member</b><span>receives the referral</span></li>
                <li><b>Prospect</b><span>is the business opportunity — a customer who needs the product or service</span></li>
              </ul>
            </section>
            <section className="rf-panel">
              <h2>How referrals progress</h2>
              <ol className="rf-how">
                {STAGES.map((s, i) => (
                  <li key={s}>
                    <span className="rf-how-n">{i + 1}</span>
                    <span><strong>{STATUS_LABEL[s]}</strong><small>{STAGE_HELP[s]}</small></span>
                  </li>
                ))}
              </ol>
            </section>
            <section className="rf-tip tgl-dark-card">
              <Icon id="i-bulb" size={18} />
              <p>The best referrals name a specific need. &ldquo;Needs a GST-ready CA for exports&rdquo; closes faster than &ldquo;knows a finance person&rdquo;.</p>
            </section>
          </aside>
        </div>
      </main>

      {giveOpen && (
        <GiveReferral
          initialTarget={stashedTarget}
          onClose={backToList}
          onSent={() => { loadPage(0); loadSummary(); }}
          onViewReferral={viewReferral}
        />
      )}
    </>
  );
}
