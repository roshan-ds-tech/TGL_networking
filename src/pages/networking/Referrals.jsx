import { useEffect, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { shortDate } from '../../lib/format';
import { showToast } from '../../components/AppShell';
import NetTabs from './NetTabs';

const STAGES = ['GIVEN', 'ACCEPTED', 'MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED'];
const STAGE_LABELS = ['Given', 'Accepted', 'Meeting Done', 'Business Closed', 'Revenue Generated'];

// Step 03 of the give-a-referral form. There is no dedicated field for it on
// a referral, so the choice is carried at the top of the note — which is the
// first thing the receiver reads.
const INTRO_OPTIONS = [
  "I'll make an email introduction",
  "I'll set up a call",
  'Share contact details only',
];

const LABEL = { display: 'block', fontSize: 10.5, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)', marginBottom: 8 };

function stageIndex(status) {
  const i = STAGES.indexOf(status);
  return i === -1 ? 0 : i;
}

function nextAction(r, myId) {
  const iAmReceiver = r.receiver_user_id === myId;
  if (r.status === 'GIVEN') return iAmReceiver ? { label: 'Accept Referral', status: 'ACCEPTED' } : null;
  if (r.status === 'ACCEPTED') return { label: 'Mark Meeting Done', status: 'MEETING_DONE' };
  if (r.status === 'MEETING_DONE') return { label: 'Mark Business Closed', status: 'BUSINESS_CLOSED' };
  if (r.status === 'BUSINESS_CLOSED') return { label: 'Log Revenue', status: 'REVENUE_GENERATED' };
  return null;
}

function GiveReferralPanel({ pipeline, initialTarget, onClose, onSent }) {
  const [target, setTarget] = useState(initialTarget || null);
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [businessNeed, setBusinessNeed] = useState('');
  const [intro, setIntro] = useState(INTRO_OPTIONS[0]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (target || !q.trim()) {
      setResults([]);
      return;
    }
    const id = setTimeout(() => {
      api.members({ q }).then(setResults).catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(id);
  }, [q, target]);

  async function submit(ev) {
    ev.preventDefault();
    if (!target) {
      setError('Search and select who you are referring.');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await api.createReferral({ receiver_user_id: target.user_id, business_need: businessNeed, note: `Expected introduction: ${intro}` });
      onSent();
    } catch (err) {
      setError(err.message || 'Could not send the referral.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div data-grid-2="" className="tglp-rise-fast" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1fr)', borderRadius: 22, overflow: 'hidden', border: '1px solid rgba(192,141,46,0.4)', marginBottom: 40, boxShadow: '0 30px 60px -30px rgba(34,16,58,0.3)' }}>
      <div style={{ padding: 34, background: '#FFFCF5' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Give a referral</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ width: 36, height: 36, borderRadius: '50%', border: '1px solid rgba(53,26,78,0.14)', background: 'transparent', color: '#2B1740', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-x" /></svg>
          </button>
        </div>

        <label style={LABEL}>01 · Who are you referring?</label>
        {target ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 12, background: 'rgba(192,141,46,0.08)', border: '1px solid rgba(192,141,46,0.3)', marginBottom: 18 }}>
            <span style={{ fontWeight: 700, color: '#2B1740' }}>{target.business_name}{target.founder_name ? ` · ${target.founder_name}` : ''}</span>
            <button type="button" onClick={() => setTarget(null)} style={{ background: 'none', border: 'none', color: '#B8863B', fontWeight: 700, cursor: 'pointer' }}>Change</button>
          </div>
        ) : (
          <>
            <input className="tgl-input" placeholder="Search a member or business" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: results.length ? 8 : 18 }} />
            {results.length > 0 && (
              <div style={{ display: 'grid', gap: 8, marginBottom: 18 }}>
                {results.map((m) => (
                  <button
                    key={m.member_id}
                    type="button"
                    onClick={() => { setTarget({ user_id: m.user_id, business_name: m.business_name, founder_name: m.founder_name }); setResults([]); setQ(''); }}
                    style={{ textAlign: 'left', padding: '10px 14px', borderRadius: 10, border: '1px solid rgba(192,141,46,0.22)', background: '#fff', cursor: 'pointer' }}
                  >
                    <strong style={{ color: '#2B1740' }}>{m.business_name}</strong>
                    <span style={{ marginLeft: 8, color: 'var(--tgl-text-muted)', fontSize: 13 }}>{m.founder_name}</span>
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        <label style={LABEL}>02 · What is the opportunity?</label>
        <textarea className="tgl-input" rows={3} style={{ resize: 'vertical', marginBottom: 18 }} placeholder="Who needs what, and why this member is a fit." value={businessNeed} onChange={(e) => setBusinessNeed(e.target.value)} />

        <label style={LABEL}>03 · Expected introduction</label>
        <select className="tgl-input" style={{ marginBottom: 26 }} value={intro} onChange={(e) => setIntro(e.target.value)}>
          {INTRO_OPTIONS.map((o) => <option key={o}>{o}</option>)}
        </select>

        {error && (
          <div className="tgl-alert-error" role="alert" style={{ marginBottom: 18 }}>
            <span>{error}</span>
          </div>
        )}

        <button
          type="button"
          className="tglp-gold"
          onClick={submit}
          disabled={submitting || !businessNeed.trim()}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '16px 28px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: submitting ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          {submitting ? 'Sending…' : 'Submit Referral'}
          <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
        </button>
      </div>
      <div className="tgl-dark-card" style={{ padding: 34 }}>
        <p style={{ margin: '0 0 18px', fontSize: 10.5, letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: 700 }}>What happens next</p>
        {pipeline.map((pl) => (
          <div key={pl.label} style={{ display: 'flex', gap: 14, padding: '11px 0', borderBottom: '1px dashed rgba(224,181,88,0.28)' }}>
            <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: '#EFCB77' }}>{pl.n}</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#FFFBF3' }}>{pl.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Referrals({ status, openGiveOnMount }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('received');
  const [giveOpen, setGiveOpen] = useState(!!openGiveOnMount);
  const [stashedTarget, setStashedTarget] = useState(null);

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

  function load() {
    setLoading(true);
    api.referrals().then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }

  useEffect(load, []);

  const myId = status?.user?.id;
  const pipeline = STAGES.map((s, i) => ({ label: STAGE_LABELS[i], n: '0' + (i + 1), count: items.filter((r) => r.status === s).length }));

  const received = items.filter((r) => r.receiver_user_id === myId);
  const given = items.filter((r) => r.giver_user_id === myId);
  const closed = items.filter((r) => r.status === 'BUSINESS_CLOSED' || r.status === 'REVENUE_GENERATED');
  const tabs = [
    ['received', 'Received', received],
    ['given', 'Given', given],
    ['closed', 'Closed', closed],
  ];
  const activeList = tabs.find(([k]) => k === tab)?.[2] || [];

  async function act(r, nextStatus) {
    try {
      await api.updateReferral(r.id, nextStatus);
      showToast('Referral updated.');
      load();
    } catch (err) {
      showToast(err.message || 'Could not update this referral.');
    }
  }

  return (
    <>
      <NetTabs active="Referrals" />
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '48px 28px 96px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap', marginBottom: 34 }}>
          <div>
            <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Referrals</p>
            <h1 style={{ margin: 0, fontSize: 'clamp(30px, 3.4vw, 44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>Introductions that close business</h1>
          </div>
          {!giveOpen && (
            <button
              type="button"
              className="tglp-gold"
              onClick={() => setGiveOpen(true)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '15px 24px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-plus" /></svg>
              Give Referral
            </button>
          )}
        </div>

        {giveOpen && (
          <GiveReferralPanel
            pipeline={pipeline}
            initialTarget={stashedTarget}
            onClose={() => { setGiveOpen(false); go('/app/networking/referrals'); }}
            onSent={() => {
              setGiveOpen(false);
              go('/app/networking/referrals');
              showToast("Referral submitted. We'll notify you when it's accepted.");
              load();
            }}
          />
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', overflow: 'hidden', marginBottom: 34 }}>
          {pipeline.map((pl, i) => (
            <div key={pl.label} style={{ padding: '20px 18px', borderRight: i < pipeline.length - 1 ? '1px solid rgba(53,26,78,0.08)' : 'none' }}>
              <p style={{ margin: '0 0 10px', fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: 'rgba(43,23,64,0.65)' }}>{pl.n}</p>
              <p style={{ margin: '0 0 4px', fontSize: 28, fontWeight: 800, color: '#2B1740', fontVariantNumeric: 'tabular-nums' }}>{pl.count}</p>
              <p style={{ margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>{pl.label}</p>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 4, padding: 4, border: '1px solid rgba(53,26,78,0.12)', borderRadius: 999, background: '#FFFCF5', width: 'fit-content', marginBottom: 22 }}>
          {tabs.map(([key, label, list]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '11px 20px', border: 'none', borderRadius: 999, background: tab === key ? '#2B1740' : 'transparent', color: tab === key ? '#F6EEDF' : 'rgba(43,23,64,0.62)', fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer' }}
            >
              {label}
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", opacity: 0.7 }}>{list.length}</span>
            </button>
          ))}
        </div>

        {loading ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)' }}>Loading referrals…</p>
        ) : activeList.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '36px 20px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5' }}>
            <p style={{ fontSize: 14, color: 'var(--tgl-text-muted)', margin: 0 }}>Nothing here yet.</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {activeList.map((r) => {
              const iAmReceiver = r.receiver_user_id === myId;
              const otherName = iAmReceiver ? r.giver_name : r.receiver_name;
              const otherBusiness = iAmReceiver ? r.giver_business : r.receiver_business;
              const action = nextAction(r, myId);
              const idx = stageIndex(r.status);
              return (
                <div key={r.id} data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr) auto', gap: 28, alignItems: 'center', padding: '24px 26px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5' }}>
                  <div style={{ minWidth: 0 }}>
                    <p style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 800, color: '#2B1740' }}>{otherName || 'TGL Member'}</p>
                    <p style={{ margin: '0 0 8px', fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>{otherBusiness || ''} · {shortDate(r.created_at)}</p>
                    <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: 'rgba(43,23,64,0.75)' }}>{r.business_need}</p>
                  </div>
                  <div>
                    <p style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: '#6B3E96' }}>{STAGE_LABELS[idx]}</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 4 }}>
                      {STAGES.map((s, i) => (
                        <span key={s} style={{ height: 4, borderRadius: 2, background: i <= idx && r.status !== 'DECLINED' && r.status !== 'CANCELLED' ? (i === idx ? '#C08D2E' : '#6B3E96') : 'rgba(53,26,78,0.1)' }} />
                      ))}
                    </div>
                  </div>
                  {action ? (
                    <button
                      type="button"
                      className="tglp-invert"
                      onClick={() => act(r, action.status)}
                      style={{ padding: '12px 18px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                    >
                      {action.label}
                    </button>
                  ) : (
                    <span style={{ fontSize: 11, color: 'rgba(43,23,64,0.65)', whiteSpace: 'nowrap' }}>
                      {r.status === 'GIVEN' ? 'Awaiting response' : r.status.replace(/_/g, ' ').toLowerCase()}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}
