import { useEffect, useMemo, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { shortDate, shortAgo } from '../../lib/format';
import { showToast } from '../../components/AppShell';
import NetTabs from './NetTabs';
import ImageSlot from '../../components/ImageSlot';

const STAGES = ['GIVEN', 'ACCEPTED', 'MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED'];
const STAGE_LABELS = ['Given', 'Accepted', 'Meeting done', 'Business closed', 'Revenue generated'];
const STAGE_HELP = [
  'You send an introduction with the opportunity.',
  'The member accepts and takes it forward.',
  'You or they confirm the first meeting happened.',
  'The introduction turns into a deal.',
  'Revenue is logged and Growth Points are earned.',
];
const DEAD = new Set(['DECLINED', 'CANCELLED']);

// The choice is carried at the top of the note: a referral has no dedicated
// field for it and the receiver reads the note first.
const INTRO_OPTIONS = [
  "I'll make an email introduction",
  "I'll set up a call",
  'Share contact details only',
];

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function stageIndex(status) {
  const i = STAGES.indexOf(status);
  return i === -1 ? 0 : i;
}

function nextAction(r, myId) {
  const iAmReceiver = r.receiver_user_id === myId;
  if (r.status === 'GIVEN') return iAmReceiver ? { label: 'Accept', status: 'ACCEPTED' } : null;
  if (r.status === 'ACCEPTED') return { label: 'Mark meeting done', status: 'MEETING_DONE' };
  if (r.status === 'MEETING_DONE') return { label: 'Mark business closed', status: 'BUSINESS_CLOSED' };
  if (r.status === 'BUSINESS_CLOSED') return { label: 'Log revenue', status: 'REVENUE_GENERATED' };
  return null;
}

/* ------------------------------ Give a referral ------------------------------ */

function GiveReferralModal({ initialTarget, onClose, onSent }) {
  const [target, setTarget] = useState(initialTarget || null);
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [businessNeed, setBusinessNeed] = useState('');
  const [intro, setIntro] = useState(INTRO_OPTIONS[0]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (target || !q.trim()) {
      setResults([]);
      setSearching(false);
      return undefined;
    }
    setSearching(true);
    let live = true;
    const id = setTimeout(() => {
      api.members({ q }).then((r) => live && setResults(r.slice(0, 5))).catch(() => live && setResults([])).finally(() => live && setSearching(false));
    }, 300);
    return () => { live = false; clearTimeout(id); };
  }, [q, target]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !submitting) onClose(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose, submitting]);

  async function submit(ev) {
    ev.preventDefault();
    if (!target) {
      setError('Search for and select the member you are referring.');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await api.createReferral({ receiver_user_id: target.user_id, business_need: businessNeed.trim(), note: `Expected introduction: ${intro}` });
      onSent();
    } catch (err) {
      setError(err.message || 'Could not send the referral.');
    } finally {
      setSubmitting(false);
    }
  }

  const ready = !!target && businessNeed.trim().length > 0;

  return (
    <div className="rf-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !submitting) onClose(); }}>
      <form className="rf-modal" role="dialog" aria-modal="true" aria-labelledby="rf-title" onSubmit={submit}>
        <header className="rf-modal-head">
          <div>
            <h2 id="rf-title">Give a referral</h2>
            <p>Introduce a member to an opportunity. They are notified straight away.</p>
          </div>
          <button type="button" className="rf-x" onClick={onClose} aria-label="Close"><Icon id="i-x" size={16} /></button>
        </header>

        <div className="rf-field">
          <label htmlFor="rf-who"><span>1</span> Who are you referring?</label>
          {target ? (
            <div className="rf-picked">
              <ImageSlot shape="circle" initial={target.founder_name || target.business_name} src={target.photo_url} style={{ width: 40, height: 40 }} fontSize={15} />
              <span><strong>{target.founder_name || target.business_name}</strong><small>{target.business_name}</small></span>
              <button type="button" onClick={() => setTarget(null)}>Change</button>
            </div>
          ) : (
            <>
              <div className="rf-input"><Icon id="i-search" size={16} /><input id="rf-who" placeholder="Search a member or business" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" autoFocus /></div>
              {(results.length > 0 || (q.trim() && !searching)) && (
                <ul className="rf-results">
                  {results.map((m) => (
                    <li key={m.member_id}>
                      <button type="button" onClick={() => { setTarget({ user_id: m.user_id, business_name: m.business_name, founder_name: m.founder_name, photo_url: m.photo_url }); setQ(''); }}>
                        <ImageSlot shape="circle" initial={m.founder_name} src={m.photo_url} style={{ width: 34, height: 34 }} fontSize={13} />
                        <span><strong>{m.founder_name}</strong><small>{m.business_name}</small></span>
                      </button>
                    </li>
                  ))}
                  {results.length === 0 && <li className="rf-none">No members found for “{q.trim()}”.</li>}
                </ul>
              )}
            </>
          )}
        </div>

        <div className="rf-field">
          <label htmlFor="rf-need"><span>2</span> What is the opportunity?</label>
          <textarea id="rf-need" rows={3} maxLength={500} placeholder="Who needs what, and why this member is a good fit." value={businessNeed} onChange={(e) => setBusinessNeed(e.target.value)} />
          <small className="rf-count">{businessNeed.length}/500</small>
        </div>

        <fieldset className="rf-field rf-intro">
          <legend><span>3</span> How will you introduce them?</legend>
          <div className="rf-choices">
            {INTRO_OPTIONS.map((o) => (
              <label key={o} className={intro === o ? 'is-on' : ''}>
                <input type="radio" name="intro" checked={intro === o} onChange={() => setIntro(o)} />
                {o}
              </label>
            ))}
          </div>
        </fieldset>

        {error && <p className="rf-error" role="alert">{error}</p>}

        <footer className="rf-modal-foot">
          <button type="button" className="rf-btn" onClick={onClose} disabled={submitting}>Cancel</button>
          <button type="submit" className="rf-btn rf-btn--primary" disabled={submitting || !ready}>{submitting ? 'Sending…' : 'Send referral'}<Icon id="i-send" size={14} /></button>
        </footer>
      </form>
    </div>
  );
}

/* ---------------------------------- Page ---------------------------------- */

function Stepper({ status }) {
  if (DEAD.has(status)) {
    return <span className={`rf-state rf-state--${status === 'DECLINED' ? 'danger' : 'muted'}`}>{status === 'DECLINED' ? 'Declined' : 'Withdrawn'}</span>;
  }
  const idx = stageIndex(status);
  return (
    <div className="rf-steps" role="img" aria-label={`Stage ${idx + 1} of 5: ${STAGE_LABELS[idx]}`}>
      <ol>
        {STAGES.map((s, i) => <li key={s} className={i < idx ? 'done' : i === idx ? 'now' : ''} />)}
      </ol>
      <span>{STAGE_LABELS[idx]}</span>
    </div>
  );
}

export default function Referrals({ status, openGiveOnMount }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('received');
  const [stageFilter, setStageFilter] = useState('');
  const [giveOpen, setGiveOpen] = useState(!!openGiveOnMount);
  const [stashedTarget, setStashedTarget] = useState(null);
  const [busyId, setBusyId] = useState('');

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

  function load(silent) {
    if (!silent) setLoading(true);
    api.referrals().then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }
  useEffect(() => { load(false); }, []);

  const myId = status?.user?.id;
  const counts = useMemo(() => STAGES.map((s) => items.filter((r) => r.status === s).length), [items]);

  const lists = useMemo(() => {
    const isMine = (r) => r.receiver_user_id === myId;
    const received = items.filter(isMine);
    const given = items.filter((r) => r.giver_user_id === myId);
    const closed = items.filter((r) => r.status === 'BUSINESS_CLOSED' || r.status === 'REVENUE_GENERATED');
    return { received, given, closed };
  }, [items, myId]);

  const actionable = (r) => !!nextAction(r, myId);
  const tabs = [['received', 'Received'], ['given', 'Given'], ['closed', 'Closed']];
  const rows = useMemo(() => lists[tab]
    .filter((r) => !stageFilter || r.status === stageFilter)
    .sort((a, b) => (actionable(b) - actionable(a)) || (new Date(b.updated_at) - new Date(a.updated_at))),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [lists, tab, stageFilter, myId]);
  const waitingOnMe = items.filter((r) => nextAction(r, myId) && !DEAD.has(r.status)).length;
  const total = items.length;

  async function act(r, nextStatus, okMsg = 'Referral updated.') {
    setBusyId(r.id);
    try {
      await api.updateReferral(r.id, nextStatus);
      showToast(okMsg);
      load(true);
    } catch (err) {
      showToast(err.message || 'Could not update this referral.');
    } finally {
      setBusyId('');
    }
  }

  return (
    <>
      <NetTabs active="Referrals" />
      <main className="rf">
        <div className="rf-top">
          <div>
            <h1>Referrals</h1>
            <p>Introductions you give and receive, tracked from the first hello to revenue.</p>
          </div>
          <button type="button" className="rf-btn rf-btn--primary" onClick={() => setGiveOpen(true)}>
            <Icon id="i-plus" size={15} /> Give referral
          </button>
        </div>

        {/* The pipeline doubles as the stage filter: one band instead of five dead tiles. */}
        <nav className="rf-pipeline" aria-label="Filter by stage">
          {STAGES.map((s, i) => (
            <button key={s} type="button" className={`${stageFilter === s ? 'is-on' : ''} ${counts[i] === 0 ? 'is-zero' : ''}`} aria-pressed={stageFilter === s} onClick={() => setStageFilter(stageFilter === s ? '' : s)}>
              <span className="rf-node">{counts[i]}</span>
              <span className="rf-stage">{STAGE_LABELS[i]}</span>
            </button>
          ))}
        </nav>

        <div className="rf-layout">
          <section className="rf-main">
            <div className="rf-tabs" role="tablist">
              {tabs.map(([key, label]) => (
                <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'is-on' : ''} onClick={() => setTab(key)}>
                  {label}<span>{lists[key].length}</span>
                </button>
              ))}
              {stageFilter && (
                <button type="button" className="rf-filter-chip" onClick={() => setStageFilter('')}>
                  {STAGE_LABELS[STAGES.indexOf(stageFilter)]} <Icon id="i-x" size={12} />
                </button>
              )}
            </div>

            {waitingOnMe > 0 && !loading && (
              <p className="rf-nudge"><Icon id="i-bell" size={15} /> <strong>{waitingOnMe}</strong> {waitingOnMe === 1 ? 'referral is' : 'referrals are'} waiting on you.</p>
            )}

            {loading ? (
              <div className="rf-list">{[0, 1].map((i) => <div key={i} className="rf-card rf-card--sk" aria-hidden="true"><span className="rf-sk rf-sk--a" /><span className="rf-sk-l"><span className="rf-sk" /><span className="rf-sk rf-sk--s" /></span></div>)}</div>
            ) : rows.length === 0 ? (
              total === 0 ? (
                <div className="rf-empty">
                  <span className="rf-empty-icon"><Icon id="i-send" size={24} /></span>
                  <h2>Your first referral starts here</h2>
                  <p>Introduce a member to a real opportunity. When it turns into business, you both build Trust and earn Growth Points.</p>
                  <button type="button" className="rf-btn rf-btn--primary" onClick={() => setGiveOpen(true)}><Icon id="i-plus" size={15} /> Give a referral</button>
                </div>
              ) : (
                <div className="rf-empty rf-empty--sm">
                  <h2>{stageFilter ? 'Nothing at this stage' : `No ${tab} referrals`}</h2>
                  <p>{stageFilter ? 'Try another stage, or clear the filter.' : tab === 'received' ? 'When a member refers business to you, it shows up here.' : tab === 'given' ? 'Referrals you send show up here with their progress.' : 'Referrals that turn into business are collected here.'}</p>
                  {stageFilter && <button type="button" className="rf-btn" onClick={() => setStageFilter('')}>Clear filter</button>}
                </div>
              )
            ) : (
              <ul className="rf-list">
                {rows.map((r) => {
                  const iAmReceiver = r.receiver_user_id === myId;
                  const name = (iAmReceiver ? r.giver_name : r.receiver_name) || 'TGL member';
                  const business = iAmReceiver ? r.giver_business : r.receiver_business;
                  const photo = iAmReceiver ? r.giver_photo_url : r.receiver_photo_url;
                  const action = DEAD.has(r.status) ? null : nextAction(r, myId);
                  const busy = busyId === r.id;
                  const awaiting = !action && r.status === 'GIVEN';
                  return (
                    <li key={r.id} className={`rf-card ${action ? 'has-action' : ''}`}>
                      <div className="rf-card-head">
                        <ImageSlot shape="circle" initial={name} src={photo} style={{ width: 44, height: 44 }} fontSize={16} />
                        <div className="rf-who">
                          <p className="rf-dir">{iAmReceiver ? 'From' : 'To'}</p>
                          <h3>{name}</h3>
                          <p className="rf-biz">{business}</p>
                        </div>
                        <span className="rf-when" title={shortDate(r.created_at)}>{shortAgo(r.updated_at)} ago</span>
                      </div>
                      <p className="rf-need">{r.business_need}</p>
                      <div className="rf-card-foot">
                        <Stepper status={r.status} />
                        <div className="rf-card-actions">
                          {action && <button type="button" className="rf-btn rf-btn--dark" disabled={busy} onClick={() => act(r, action.status)}>{busy ? 'Updating…' : action.label}</button>}
                          {r.status === 'GIVEN' && iAmReceiver && <button type="button" className="rf-link-btn" disabled={busy} onClick={() => act(r, 'DECLINED', 'Referral declined.')}>Decline</button>}
                          {r.status === 'GIVEN' && !iAmReceiver && <button type="button" className="rf-link-btn" disabled={busy} onClick={() => act(r, 'CANCELLED', 'Referral withdrawn.')}>Withdraw</button>}
                          {awaiting && !iAmReceiver && <span className="rf-wait">Waiting for {name.split(' ')[0]} to accept</span>}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <aside className="rf-side">
            <section className="rf-panel">
              <h2>How referrals work</h2>
              <ol className="rf-how">
                {STAGE_LABELS.map((l, i) => (
                  <li key={l}>
                    <span className="rf-how-n">{i + 1}</span>
                    <span><strong>{l}</strong><small>{STAGE_HELP[i]}</small></span>
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
        <GiveReferralModal
          initialTarget={stashedTarget}
          onClose={() => { setGiveOpen(false); if (window.location.pathname !== '/app/networking/referrals') go('/app/networking/referrals', { replace: true }); }}
          onSent={() => {
            setGiveOpen(false);
            if (window.location.pathname !== '/app/networking/referrals') go('/app/networking/referrals', { replace: true });
            showToast("Referral submitted. We'll notify you when it's accepted.");
            setTab('given');
            setStageFilter('');
            load(true);
          }}
        />
      )}
    </>
  );
}
