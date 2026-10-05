import { useCallback, useEffect, useRef, useState } from 'react';
import { api, go } from '../lib/customerApi';
import { shortAgo } from '../lib/format';

const CATEGORY_MAP = {
  referral_received: 'referrals',
  referral_status_changed: 'referrals',
  referral_accepted: 'referrals',
  referral_requested: 'referrals',
  need_help_offered: 'networking',
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

// What kind of message this is, in words — shown as the detail view's eyebrow.
const KIND_LABEL = {
  connection_request: 'Connection request',
  referral_requested: 'Referral request',
  referral_received: 'Referral received',
  referral_accepted: 'Referral accepted',
  referral_status_changed: 'Referral update',
  need_help_offered: 'Offer of help',
  membership_activated: 'Membership',
  registration_confirmed: 'Registration',
  registration_submitted: 'Registration',
};

const REF_STATUS = {
  GIVEN: 'Awaiting response',
  ACCEPTED: 'Accepted',
  MEETING_DONE: 'Meeting done',
  BUSINESS_CLOSED: 'Business closed',
  REVENUE_GENERATED: 'Revenue generated',
  DECLINED: 'Declined',
  CANCELLED: 'Cancelled',
};

const TABS = [
  ['all', 'All'],
  ['networking', 'Networking'],
  ['referrals', 'Referrals'],
  ['membership', 'Membership'],
  ['events', 'Events'],
  ['recognition', 'Recognition'],
];

const EYEBROW = { margin: '0 0 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#8F6420' };
const LABEL = { margin: '0 0 6px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' };
const GOLD_BTN = { display: 'inline-flex', alignItems: 'center', gap: 10, padding: '14px 24px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' };
const GHOST_BTN = { padding: '13px 22px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' };

const initialsOf = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

function Avatar({ actor, cat, size = 42 }) {
  if (actor) {
    return (
      <span aria-hidden="true" style={{ width: size, height: size, borderRadius: '50%', background: 'linear-gradient(135deg,#35194E,#6B3E96)', color: '#EFCB77', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: size * 0.36, fontWeight: 800 }}>
        {initialsOf(actor.name)}
      </span>
    );
  }
  return (
    <span aria-hidden="true" style={{ width: size, height: size, borderRadius: 12, background: 'rgba(107,62,150,0.08)', color: '#6B3E96', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      <svg width={size * 0.45} height={size * 0.45} viewBox="0 0 24 24"><use href={`#${ICON_MAP[cat]}`} /></svg>
    </span>
  );
}

/* The primary and secondary next steps for a notification — so the detail view
   always answers "what do I do about this?". */
function actionsFor(n) {
  const profile = n.actor?.member_id
    ? { label: `View ${n.actor.name.split(' ')[0]}'s profile`, to: `/app/networking/members/${n.actor.member_id}` }
    : null;
  switch (n.type) {
    case 'connection_request':
      return [profile].filter(Boolean);
    case 'referral_requested':
      return [{ label: 'Give a referral', to: '/app/referrals/new' }, profile].filter(Boolean);
    case 'referral_received':
    case 'referral_accepted':
    case 'referral_status_changed':
      return [{ label: 'Open referrals', to: '/app/networking/referrals' }, profile].filter(Boolean);
    case 'need_help_offered':
      return [profile, { label: 'My needs', to: '/app/networking/needs' }].filter(Boolean);
    case 'membership_activated':
      return [{ label: 'Open Networking', to: '/app/networking' }, { label: 'Membership details', to: '/app/profile/membership' }];
    case 'registration_confirmed':
    case 'registration_submitted':
      return [{ label: 'View registration', to: '/app/events' }];
    default:
      return [];
  }
}

function DetailRows({ n }) {
  const d = n.detail || {};
  const rows = [];
  if (d.business_need) rows.push(['Business need', d.business_need]);
  if (d.status) rows.push(['Referral status', REF_STATUS[d.status] || d.status]);
  if (d.you_are) rows.push(['Your role', d.you_are === 'receiver' ? 'You received this referral' : 'You gave this referral']);
  if (d.need_title) rows.push(['Your need', d.need_title]);
  if (d.need_description) rows.push(['Details', d.need_description]);
  if (!rows.length) return null;
  return (
    <dl style={{ margin: '0 0 22px', display: 'grid', gap: 1, background: 'rgba(53,26,78,0.1)', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 14, overflow: 'hidden' }}>
      {rows.map(([k, v]) => (
        <div key={k} style={{ padding: '14px 16px', background: '#FFFCF5' }}>
          <dt style={LABEL}>{k}</dt>
          <dd style={{ margin: 0, fontSize: 14.5, lineHeight: 1.55, color: '#2B1740', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function NotificationDetail({ n, onClose }) {
  const cat = CATEGORY_MAP[n.type] || 'networking';
  const closeRef = useRef(null);
  const actions = actionsFor(n);
  // A personal message from the sender, when there is one, is the heart of
  // the notification; otherwise the stored body says what happened.
  const message = n.detail?.note || (n.detail?.business_need ? null : n.body);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  function goTo(to) {
    onClose();
    go(to);
  }

  return (
    <div className="tgl-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="notif-title">
      <div className="tgl-modal-card" style={{ maxWidth: 560, maxHeight: 'calc(100vh - 40px)', overflowY: 'auto' }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, marginBottom: 20 }}>
          <div style={{ minWidth: 0 }}>
            <p style={EYEBROW}>{KIND_LABEL[n.type] || cat}</p>
            <h2 id="notif-title" style={{ margin: 0, fontSize: 23, lineHeight: 1.25, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740', overflowWrap: 'anywhere' }}>{n.title}</h2>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close" style={{ width: 36, height: 36, flexShrink: 0, border: '1px solid rgba(53,26,78,0.15)', borderRadius: '50%', background: 'transparent', color: '#35194E', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>
            ×
          </button>
        </div>

        {n.actor && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: 16, marginBottom: 20, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 16, background: 'rgba(107,62,150,0.05)' }}>
            <Avatar actor={n.actor} cat={cat} size={48} />
            <div style={{ minWidth: 0 }}>
              <p style={{ ...LABEL, margin: '0 0 3px' }}>From</p>
              <p style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#2B1740' }}>{n.actor.name}</p>
              <p style={{ margin: '2px 0 0', fontSize: 13, color: 'rgba(43,23,64,0.65)' }}>
                {[n.actor.business_name, n.actor.city].filter(Boolean).join(' · ') || 'TGL member'}
              </p>
            </div>
          </div>
        )}

        {message && (
          <div style={{ marginBottom: 22 }}>
            {n.detail?.note && <p style={LABEL}>Message</p>}
            <p style={{ margin: 0, padding: n.detail?.note ? '14px 16px' : 0, borderLeft: n.detail?.note ? '3px solid #E0B558' : 'none', background: n.detail?.note ? '#F6EEDF' : 'transparent', borderRadius: n.detail?.note ? '0 12px 12px 0' : 0, fontSize: 15, lineHeight: 1.65, color: '#2B1740', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {message}
            </p>
          </div>
        )}

        <DetailRows n={n} />

        <p style={{ margin: '0 0 24px', fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>
          {new Date(n.created_at).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
        </p>

        {actions.length > 0 && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {actions.map((a, i) => (
              <button key={a.to} type="button" className={i === 0 ? 'tglp-gold' : 'tglp-ghost'} style={i === 0 ? GOLD_BTN : GHOST_BTN} onClick={() => goTo(a.to)}>
                {a.label}
                {i === 0 && <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Notifications({ reload }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('all');
  const [open, setOpen] = useState(null);
  // Stable, so the dialog's keyboard/focus effect runs once per opening.
  const closeDetail = useCallback(() => setOpen(null), []);

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

  function openItem(n) {
    setOpen(n);
    if (!n.read_at) {
      api.readNotification(n.id).then(() => reload?.()).catch(() => {});
      setItems((prev) => prev.map((it) => (it.id === n.id ? { ...it, read_at: new Date().toISOString() } : it)));
    }
  }

  return (
    <main style={{ maxWidth: 880, margin: '0 auto', padding: '48px 28px 96px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 26 }}>
        <div>
          <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Inbox</p>
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
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)', padding: 40 }}>Loading notifications…</p>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '56px 24px', textAlign: 'center' }}>
            <svg width="28" height="28" viewBox="0 0 24 24" style={{ color: 'rgba(43,23,64,0.65)' }}><use href="#i-bell" /></svg>
            <p style={{ margin: '14px 0 6px', fontSize: 16, fontWeight: 700, color: '#2B1740' }}>You&apos;re all caught up</p>
            <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.65)' }}>New activity in this category will appear here.</p>
          </div>
        ) : (
          filtered.map((n) => {
            const cat = CATEGORY_MAP[n.type] || 'networking';
            const preview = n.detail?.note || n.body;
            const unread = !n.read_at;
            return (
              <button
                key={n.id}
                type="button"
                className="tglp-row"
                onClick={() => openItem(n)}
                aria-label={`${unread ? 'Unread: ' : ''}${n.title}`}
                style={{ display: 'flex', gap: 16, width: '100%', textAlign: 'left', padding: '20px 24px', border: 'none', borderBottom: '1px solid rgba(53,26,78,0.08)', background: unread ? 'rgba(224,181,88,0.07)' : 'transparent', cursor: 'pointer', font: 'inherit' }}
              >
                <Avatar actor={n.actor} cat={cat} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: '0 0 4px', fontSize: 15, fontWeight: unread ? 800 : 700, color: '#2B1740' }}>{n.title}</p>
                  {n.actor?.business_name && (
                    <p style={{ margin: '0 0 4px', fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>
                      {[n.actor.business_name, n.actor.city].filter(Boolean).join(' · ')}
                    </p>
                  )}
                  <p style={{ margin: '0 0 8px', fontSize: 13.5, lineHeight: 1.5, color: 'rgba(43,23,64,0.65)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{preview}</p>
                  <p style={{ margin: 0, fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>
                    {KIND_LABEL[n.type] || cat} · {shortAgo(n.created_at)}
                  </p>
                </div>
                {unread && <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#C08D2E', flexShrink: 0, marginTop: 6 }} />}
              </button>
            );
          })
        )}
      </div>

      {open && <NotificationDetail n={open} onClose={closeDetail} />}
    </main>
  );
}
