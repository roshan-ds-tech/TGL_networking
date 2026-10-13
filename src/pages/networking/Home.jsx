import { useEffect, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { shortAgo, shortDate, trustTier } from '../../lib/format';
import { showToast } from '../../components/AppShell';
import ConnectionButton from '../../components/ConnectionButton';
import { useConnections } from '../../lib/connections';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));
const STAGES = [
  ['GIVEN', 'Given'],
  ['ACCEPTED', 'Accepted'],
  ['MEETING_DONE', 'Meeting done'],
  ['BUSINESS_CLOSED', 'Business closed'],
  ['REVENUE_GENERATED', 'Revenue generated'],
];
const STAGE_LABEL = Object.fromEntries(STAGES);
const DAY = 24 * 60 * 60 * 1000;

function greeting(now) {
  const h = new Date(now).getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function nav(to) {
  return (e) => { e.preventDefault(); go(to); };
}

function Panel({ title, sub, link, children }) {
  return (
    <article className="nh-panel">
      <header className="nh-panel-head">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {link && (
          <a className="nh-more" href={link.to} onClick={nav(link.to)}>
            {link.label} <Icon id="i-arrow" size={13} />
          </a>
        )}
      </header>
      {children}
    </article>
  );
}

function Empty({ icon, title, body, action }) {
  return (
    <div className="nh-empty">
      <span className="nh-empty-icon"><Icon id={icon} size={20} /></span>
      <p className="nh-empty-title">{title}</p>
      <p className="nh-empty-body">{body}</p>
      {action}
    </div>
  );
}

function SkeletonRows({ n = 3 }) {
  return Array.from({ length: n }, (_, i) => (
    <div key={i} className="nh-row nh-row--skeleton" aria-hidden="true">
      <span className="nh-sk nh-sk--avatar" />
      <span className="nh-sk-lines"><span className="nh-sk" /><span className="nh-sk nh-sk--short" /></span>
    </div>
  ));
}

export default function NetworkingHome({ status }) {
  // null = still loading, [] = loaded and empty: the two read very differently.
  const [members, setMembers] = useState(null);
  const [needs, setNeeds] = useState(null);
  const [referrals, setReferrals] = useState(null);
  const [gp, setGp] = useState(null);
  const net = useConnections();
  const [helped, setHelped] = useState(new Set());
  const [now] = useState(Date.now); // one clock per visit keeps render pure

  const me = status.user?.id;

  useEffect(() => {
    // Never suggest the signed-in member to themselves.
    api.members({}).then((rows) => setMembers(rows.filter((m) => m.user_id !== me))).catch(() => setMembers([]));
    api.needs().then((rows) => setNeeds(rows.slice(0, 4))).catch(() => setNeeds([]));
    api.referrals().then(setReferrals).catch(() => setReferrals([]));
    api.growthPointsOverview().then(setGp).catch(() => setGp(null));
  }, [me]);

  const byUser = new Map((members || []).map((m) => [m.user_id, m]));
  const toMeet = (members || []).filter((m) => net.relation(m.user_id).kind !== 'connected').slice(0, 4);
  const invites = net.invitations.filter((c) => byUser.has(c.requester_user_id));
  const firstName = (status.personal_profile?.full_name || '').split(/\s+/)[0];
  const profile = status.networking_profile;
  const tier = trustTier(profile?.trust_score || 0);
  const refs = referrals || [];
  const given = refs.filter((r) => r.giver_user_id === me).length;
  const received = refs.filter((r) => r.receiver_user_id === me).length;
  const pipeline = STAGES.map(([key, label]) => ({ key, label, count: refs.filter((r) => r.status === key).length }));
  const maxStage = Math.max(1, ...pipeline.map((p) => p.count));
  const recent = [...refs].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)).slice(0, 3);

  const m = status.membership;
  let membershipLeft = null;
  if (m?.starts_at && m?.expires_at) {
    const start = new Date(m.starts_at).getTime();
    const end = new Date(m.expires_at).getTime();
    const days = Math.max(0, Math.ceil((end - now) / DAY));
    const pct = Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100));
    membershipLeft = { days, pct };
  }

  async function offerHelp(need) {
    try {
      await api.helpNeed(need.id);
      setHelped((prev) => new Set(prev).add(need.id));
      showToast('Response sent. The member will be notified.');
    } catch (err) {
      showToast(err.message || 'Could not send your response.');
    }
  }

  return (
    <>
      <NetTabs active="Overview" />
      <main className="nh">
        <div className="nh-top">
          <div>
            <p className="nh-kicker">{greeting(now)}{firstName ? `, ${firstName}` : ''}</p>
            <h1>Your network at a glance</h1>
            <p className="nh-lede">Meet founders worth knowing, answer what members need, and track every referral from introduction to revenue.</p>
          </div>
          <div className="nh-actions">
            <button type="button" className="nh-btn nh-btn--primary" onClick={() => go('/app/referrals/new')}>
              <Icon id="i-plus" size={15} /> Give referral
            </button>
            <button type="button" className="nh-btn" onClick={() => go('/app/networking/needs')}>
              <Icon id="i-megaphone" size={15} /> Post a need
            </button>
            <button type="button" className="nh-btn" onClick={() => go('/app/networking/members')}>
              <Icon id="i-search" size={15} /> Find members
            </button>
          </div>
        </div>

        <div className="nh-stats">
          <button type="button" className="nh-stat nh-stat--link" onClick={() => go('/app/growth-points')}>
            <span className="nh-stat-label"><Icon id="i-chart" size={14} /> Growth Points</span>
            {/* The number comes from the server's overview (the points ledger), only when Growth Points are visible to this member. */}
            <span className="nh-stat-value nh-stat-value--gold">{gp?.visible ? gp.balance.total.toLocaleString('en-IN') : '0'}</span>
            <span className="nh-stat-note">{gp?.visible ? (gp.preview_only ? 'Preview: not redeemable yet' : 'Available to use at renewal') : 'Coming soon. Not being awarded yet'}</span>
            <span className="nh-stat-go">View how you earn and where they came from →</span>
          </button>
          <div className="nh-stat">
            <span className="nh-stat-label"><Icon id="i-shield" size={14} /> Trust</span>
            <span className="nh-stat-value nh-stat-value--text">{tier.label}</span>
            <span className="nh-meter" role="img" aria-label={`Trust level ${tier.filled} of 5`}>
              {[1, 2, 3, 4, 5].map((n) => <span key={n} className={n <= tier.filled ? 'on' : ''} />)}
            </span>
          </div>
          <div className="nh-stat">
            <span className="nh-stat-label"><Icon id="i-send" size={14} /> Referrals</span>
            <span className="nh-stat-value">{referrals ? given : '–'}<small> given</small></span>
            <span className="nh-stat-note">{referrals ? `${received} received` : 'Loading…'}</span>
          </div>
          <div className="nh-stat">
            <span className="nh-stat-label"><Icon id="i-users" size={14} /> Connections</span>
            <span className="nh-stat-value">{net.loaded ? net.connected.length : '–'}</span>
            <span className="nh-stat-note">{net.invitations.length > 0 ? `${net.invitations.length} waiting on you` : 'People you\'re connected with'}</span>
          </div>
        </div>

        <div className="nh-grid">
          <div className="nh-col">
            {invites.length > 0 && (
              <Panel title="Connection requests" sub={`${invites.length} ${invites.length === 1 ? 'member wants' : 'members want'} to connect with you`} link={{ to: '/app/networking/connections', label: invites.length > 3 ? 'See all' : 'My network' }}>
                <ul className="nh-list">
                  {invites.slice(0, 3).map((c) => {
                    const mb = byUser.get(c.requester_user_id);
                    return (
                      <li key={c.id} className="nh-row">
                        <a className="nh-person" href={`/app/networking/members/${mb.member_id}`} onClick={nav(`/app/networking/members/${mb.member_id}`)}>
                          <ImageSlot shape="circle" initial={mb.founder_name} src={mb.photo_url} style={{ width: 48, height: 48 }} fontSize={18} />
                          <span className="nh-person-text">
                            <span className="nh-name">{mb.founder_name}</span>
                            <span className="nh-meta">{mb.business_name}{c.note ? ` · “${c.note}”` : ''}</span>
                          </span>
                        </a>
                        <ConnectionButton prefix="nh" extra="nh-btn--sm" relation={net.relation(mb.user_id)} userId={mb.user_id} name={mb.founder_name} businessName={mb.business_name} />
                      </li>
                    );
                  })}
                </ul>
              </Panel>
            )}
            <Panel title="People to meet" sub="Founders in the Season 1 network" link={{ to: '/app/networking/members', label: 'All members' }}>
              {members === null || !net.loaded ? <SkeletonRows /> : toMeet.length === 0 ? (
                <Empty icon="i-users" title={members.length === 0 ? 'No other members yet' : "You've met everyone for now"} body={members.length === 0 ? 'Check back as more Season 1 founders activate their membership.' : 'New members will show up here as they join.'} />
              ) : (
                <ul className="nh-list">
                  {toMeet.map((mb) => {
                    const meta = [mb.business_name, CATEGORY_MAP.get(mb.category) || mb.category, mb.city].filter(Boolean).join(' · ');
                    return (
                      <li key={mb.member_id} className="nh-row">
                        <a className="nh-person" href={`/app/networking/members/${mb.member_id}`} onClick={nav(`/app/networking/members/${mb.member_id}`)}>
                          <ImageSlot shape="circle" initial={mb.founder_name} src={mb.photo_url} style={{ width: 48, height: 48 }} fontSize={18} />
                          <span className="nh-person-text">
                            <span className="nh-name">
                              {mb.founder_name}
                              {mb.tgl_verified && <span className="nh-verified" title="TGL Verified"><Icon id="i-shield" size={13} /></span>}
                              {mb.open_to_mentoring && <span className="nh-tag">Mentor</span>}
                            </span>
                            <span className="nh-meta">{meta}</span>
                            {mb.headline && <span className="nh-headline">{mb.headline}</span>}
                          </span>
                        </a>
                        <ConnectionButton prefix="nh" extra="nh-btn--sm" relation={net.relation(mb.user_id)} userId={mb.user_id} name={mb.founder_name} businessName={mb.business_name} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            <Panel title="Open business needs" sub="Members asking for an introduction or a supplier" link={{ to: '/app/networking/needs', label: 'Need board' }}>
              {needs === null ? <SkeletonRows /> : needs.length === 0 ? (
                <Empty
                  icon="i-megaphone"
                  title="No open needs right now"
                  body="Looking for a supplier, partner or client? Ask the network."
                  action={<button type="button" className="nh-btn nh-btn--sm" onClick={() => go('/app/networking/needs')}>Post a need</button>}
                />
              ) : (
                <ul className="nh-list">
                  {needs.map((n) => {
                    const isOwn = n.poster_user_id === me;
                    const done = helped.has(n.id);
                    return (
                      <li key={n.id} className="nh-row">
                        <div className="nh-person">
                          <ImageSlot shape="circle" initial={n.poster_name} src={n.poster_photo_url} style={{ width: 48, height: 48 }} fontSize={18} />
                          <span className="nh-person-text">
                            <span className="nh-name nh-name--need">{n.title}</span>
                            <span className="nh-meta">
                              {n.poster_name} · {CATEGORY_MAP.get(n.category) || n.category} · {shortAgo(n.created_at)} ago
                            </span>
                          </span>
                        </div>
                        <button type="button" className={`nh-btn nh-btn--sm ${isOwn || done ? 'is-done' : 'nh-btn--gold-line'}`} disabled={isOwn || done} onClick={() => offerHelp(n)}>
                          {isOwn ? 'Your need' : done ? <><Icon id="i-check" size={13} /> Offer sent</> : 'I can help'}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>
          </div>

          <aside className="nh-col">
            <Panel title="Referral pipeline" link={{ to: '/app/networking/referrals', label: 'Open' }}>
              <p className="nh-total">
                <strong>{referrals ? refs.length : '–'}</strong> {refs.length === 1 ? 'referral' : 'referrals'} in motion
              </p>
              <ol className="nh-funnel">
                {pipeline.map((p) => (
                  <li key={p.key}>
                    <span className="nh-funnel-label">{p.label}</span>
                    <span className="nh-funnel-track"><span style={{ width: `${(p.count / maxStage) * 100}%` }} /></span>
                    <span className="nh-funnel-n">{p.count}</span>
                  </li>
                ))}
              </ol>
            </Panel>

            <Panel title="Recent activity">
              {referrals === null ? <SkeletonRows n={2} /> : recent.length === 0 ? (
                <Empty
                  icon="i-send"
                  title="No referrals yet"
                  body="Your first referral starts your Trust history. Growth Points are coming soon."
                  action={<button type="button" className="nh-btn nh-btn--sm nh-btn--primary" onClick={() => go('/app/referrals/new')}>Give a referral</button>}
                />
              ) : (
                <ul className="nh-feed">
                  {recent.map((r) => {
                    const outgoing = r.giver_user_id === me;
                    const other = outgoing ? r.receiver_name : r.giver_name;
                    return (
                      <li key={r.id}>
                        <span className={`nh-dot ${outgoing ? 'out' : 'in'}`} />
                        <span className="nh-feed-text">
                          <strong>{outgoing ? `To ${other || 'a member'}` : `From ${other || 'a member'}`}</strong>
                          <span>{r.business_need}</span>
                          <span className="nh-feed-meta">{STAGE_LABEL[r.status] || r.status.replace(/_/g, ' ').toLowerCase()} · {shortAgo(r.updated_at)} ago</span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            <article className="nh-member tgl-dark-card">
              <div className="nh-member-head">
                <span>Season 1 membership</span>
                <span className="nh-member-pill">Active</span>
              </div>
              {membershipLeft ? (
                <>
                  <p className="nh-member-big">{membershipLeft.days} <small>days left</small></p>
                  <span className="nh-member-track"><span style={{ width: `${membershipLeft.pct}%` }} /></span>
                  <p className="nh-member-note">Ends on {shortDate(m.expires_at)}</p>
                </>
              ) : (
                <p className="nh-member-note">Complimentary for Season 1 registrants · 3 months</p>
              )}
              <a href="/app/profile/membership" onClick={nav('/app/profile/membership')}>Membership details <Icon id="i-arrow" size={13} /></a>
            </article>
          </aside>
        </div>
      </main>
    </>
  );
}
