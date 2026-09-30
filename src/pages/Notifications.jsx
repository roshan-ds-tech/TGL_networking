import { useEffect, useState } from 'react';
import { api } from '../lib/customerApi';
import { shortAgo } from '../lib/format';

const CATEGORY_MAP = {
  referral_received: 'referrals',
  referral_status_changed: 'referrals',
  referral_accepted: 'referrals',
  referral_requested: 'referrals',
  need_help_offered: 'referrals',
  connection_request: 'networking',
  membership_activated: 'membership',
  registration_confirmed: 'membership',
  registration_submitted: 'membership',
};

const ICON_MAP = {
  referrals: 'i-link',
  networking: 'i-users',
  membership: 'i-check',
  events: 'i-calendar',
  recognition: 'i-medal',
};

const TABS = [
  ['all', 'All'],
  ['networking', 'Networking'],
  ['referrals', 'Referrals'],
  ['membership', 'Membership'],
  ['events', 'Events'],
  ['recognition', 'Recognition'],
];

export default function Notifications({ reload }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('all');

  function load() {
    setLoading(true);
    api.notifications().then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }

  useEffect(load, []);

  const filtered = items.filter((n) => tab === 'all' || (CATEGORY_MAP[n.type] || 'networking') === tab);

  async function markAllRead() {
    try {
      await api.readAllNotifications();
      load();
      reload?.();
    } catch {
      // best-effort
    }
  }

  async function openItem(n) {
    if (!n.read_at) {
      api.readNotification(n.id).catch(() => {});
      setItems((prev) => prev.map((it) => (it.id === n.id ? { ...it, read_at: new Date().toISOString() } : it)));
      reload?.();
    }
  }

  return (
    <main style={{ maxWidth: 880, margin: '0 auto', padding: '48px 28px 96px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 26 }}>
        <div>
          <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Inbox</p>
          <h1 style={{ margin: 0, fontSize: 'clamp(30px, 3.4vw, 44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>Notifications</h1>
        </div>
        <a href="#" onClick={(e) => { e.preventDefault(); markAllRead(); }} style={{ fontSize: 12.5, fontWeight: 700, whiteSpace: 'nowrap' }}>Mark all as read</a>
      </div>

      <div style={{ display: 'flex', gap: 4, padding: 4, border: '1px solid rgba(53,26,78,0.12)', borderRadius: 999, background: '#FFFCF5', width: 'fit-content', maxWidth: '100%', overflowX: 'auto', marginBottom: 22 }}>
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            style={{ padding: '10px 16px', border: 'none', borderRadius: 999, background: tab === key ? '#2B1740' : 'transparent', color: tab === key ? '#F6EEDF' : 'rgba(43,23,64,0.62)', fontSize: 10.5, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', overflow: 'hidden' }}>
        {loading ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)', padding: 40 }}>Loading signals…</p>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '56px 24px', textAlign: 'center' }}>
            <svg width="28" height="28" viewBox="0 0 24 24" style={{ color: 'rgba(43,23,64,0.3)' }}><use href="#i-bell" /></svg>
            <p style={{ margin: '14px 0 6px', fontSize: 16, fontWeight: 700, color: '#2B1740' }}>You&apos;re all caught up</p>
            <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.58)' }}>New activity in this category will appear here.</p>
          </div>
        ) : (
          filtered.map((n) => {
            const cat = CATEGORY_MAP[n.type] || 'networking';
            return (
              <div key={n.id} className="tglp-row" onClick={() => openItem(n)} style={{ display: 'flex', gap: 18, padding: '22px 24px', borderBottom: '1px solid rgba(53,26,78,0.08)', cursor: 'pointer' }}>
                <span style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(107,62,150,0.08)', color: '#6B3E96', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <svg width="19" height="19" viewBox="0 0 24 24"><use href={`#${ICON_MAP[cat]}`} /></svg>
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: '0 0 4px', fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{n.title}</p>
                  <p style={{ margin: '0 0 8px', fontSize: 13.5, lineHeight: 1.5, color: 'rgba(43,23,64,0.62)' }}>{n.body}</p>
                  <p style={{ margin: 0, fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.42)' }}>
                    {cat[0].toUpperCase() + cat.slice(1)} · {shortAgo(n.created_at)}
                  </p>
                </div>
                {!n.read_at && <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#C08D2E', flexShrink: 0, marginTop: 6 }} />}
              </div>
            );
          })
        )}
      </div>
    </main>
  );
}
