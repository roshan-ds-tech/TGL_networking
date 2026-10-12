import { useEffect, useMemo, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { timeAgo } from '../../lib/format';
import { connectionsChanged, useConnections } from '../../lib/connections';
import { showToast } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function Empty({ icon, title, body, action }) {
  return (
    <div className="rf-empty rf-empty--sm">
      <span className="rf-empty-icon"><Icon id={icon} size={22} /></span>
      <h2>{title}</h2>
      <p>{body}</p>
      {action}
    </div>
  );
}

export default function Connections() {
  const net = useConnections();
  const [members, setMembers] = useState(null);
  const [tab, setTab] = useState(null); // null = pick a sensible default once data is in
  const [busyId, setBusyId] = useState('');

  useEffect(() => {
    api.members({}).then(setMembers).catch(() => setMembers([]));
  }, []);

  // Profile details for each person, keyed by account id. A connection whose
  // member is no longer active simply has no card and is left out.
  const byUser = useMemo(() => new Map((members || []).map((m) => [m.user_id, m])), [members]);
  const ready = net.loaded && members !== null;

  const lists = {
    invitations: net.invitations,
    connected: net.connected,
    sent: net.sent,
  };
  const shown = (key) => lists[key].filter((c) => byUser.has(net.otherOf(c)));
  const counts = { invitations: shown('invitations').length, connected: shown('connected').length, sent: shown('sent').length };
  const active = tab || (counts.invitations > 0 ? 'invitations' : 'connected');
  const rows = ready ? shown(active) : [];

  async function run(c, fn, okMsg) {
    setBusyId(c.id);
    try {
      await fn();
      if (okMsg) showToast(okMsg);
    } catch (err) {
      showToast(err.message || 'Something went wrong. Please try again.');
    } finally {
      setBusyId('');
      connectionsChanged();
    }
  }

  const TABS = [
    ['invitations', 'Invitations'],
    ['connected', 'Connected'],
    ['sent', 'Sent'],
  ];

  return (
    <>
      <NetTabs active="My Network" />
      <main className="cx">
        <div className="cx-top">
          <h1>My network</h1>
          <p>Accept invitations, see who you&apos;re connected with, and keep track of requests you&apos;ve sent.</p>
        </div>

        <div className="rf-tabs cx-tabs" role="tablist">
          {TABS.map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={active === key} className={active === key ? 'is-on' : ''} onClick={() => setTab(key)}>
              {label}{ready && <span>{counts[key]}</span>}
            </button>
          ))}
        </div>

        {!ready ? (
          <ul className="cx-list">{[0, 1].map((i) => <li key={i} className="cx-card cx-card--sk" aria-hidden="true"><span className="rf-sk rf-sk--a" /><span className="rf-sk-l"><span className="rf-sk" /><span className="rf-sk rf-sk--s" /></span></li>)}</ul>
        ) : rows.length === 0 ? (
          active === 'invitations' ? (
            <Empty icon="i-bell" title="No invitations right now" body="When a member asks to connect with you, it shows up here so you can accept or ignore it." action={<button type="button" className="rf-btn" onClick={() => go('/app/networking/members')}>Find members</button>} />
          ) : active === 'connected' ? (
            <Empty icon="i-users" title="You're not connected with anyone yet" body="Send a few connection requests. Once a member accepts, they appear here." action={<button type="button" className="rf-btn rf-btn--primary" onClick={() => go('/app/networking/members')}>Find members</button>} />
          ) : (
            <Empty icon="i-send" title="No pending requests" body="Requests you send wait here until the member responds." action={<button type="button" className="rf-btn" onClick={() => go('/app/networking/members')}>Find members</button>} />
          )
        ) : (
          <ul className="cx-list">
            {rows.map((c) => {
              const m = byUser.get(net.otherOf(c));
              const busy = busyId === c.id;
              const meta = [m.business_name, CATEGORY_MAP.get(m.category) || m.category, m.city].filter(Boolean).join(' · ');
              return (
                <li key={c.id} className="cx-card">
                  <a className="cx-person" href={`/app/networking/members/${m.member_id}`} onClick={(e) => { e.preventDefault(); go(`/app/networking/members/${m.member_id}`); }}>
                    <ImageSlot shape="circle" initial={m.founder_name} src={m.photo_url} style={{ width: 52, height: 52 }} fontSize={19} />
                    <span className="cx-text">
                      <span className="cx-name">
                        {m.founder_name}
                        {m.tgl_verified && <span className="cx-ver" title="TGL Verified"><Icon id="i-shield" size={14} /></span>}
                        {active === 'invitations' && <small>{timeAgo(c.created_at)}</small>}
                      </span>
                      <span className="cx-meta">{meta}</span>
                      {m.headline && <span className="cx-head">{m.headline}</span>}
                    </span>
                  </a>

                  {active === 'invitations' && c.note && <p className="cx-note">&ldquo;{c.note}&rdquo;</p>}

                  <div className="cx-actions">
                    {active === 'invitations' && (
                      <>
                        <button type="button" className="rf-btn rf-btn--dark" disabled={busy} onClick={() => run(c, () => api.respondConnection(c.id, 'accept'), `You're now connected with ${m.founder_name}.`)}>{busy ? 'Working…' : 'Accept'}</button>
                        <button type="button" className="rf-btn" disabled={busy} onClick={() => run(c, () => api.respondConnection(c.id, 'decline'), 'Request ignored.')}>Ignore</button>
                      </>
                    )}
                    {active === 'connected' && (
                      <>
                        <button type="button" className="rf-btn" onClick={() => { sessionStorage.setItem('tgl_referral_target', JSON.stringify({ user_id: m.user_id, business_name: m.business_name, founder_name: m.founder_name, photo_url: m.photo_url })); go('/app/referrals/new'); }}>Give referral</button>
                        <button type="button" className="rf-link-btn" disabled={busy} onClick={() => { if (window.confirm(`Remove ${m.founder_name} from your connections?`)) run(c, () => api.removeConnection(c.id), 'Connection removed.'); }}>Remove</button>
                      </>
                    )}
                    {active === 'sent' && (
                      <>
                        <span className="cx-pending"><Icon id="i-clock" size={13} /> Waiting for {m.founder_name.split(' ')[0]} · {timeAgo(c.created_at)}</span>
                        <button type="button" className="rf-link-btn" disabled={busy} onClick={() => run(c, () => api.removeConnection(c.id), 'Request withdrawn.')}>Withdraw</button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </>
  );
}
