import { useEffect, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { timeAgo, trustTier } from '../../lib/format';
import { Eyebrow, openConnectModal, showToast } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));
const STAGES = ['GIVEN', 'ACCEPTED', 'MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED'];
const STAGE_LABELS = ['Given', 'Accepted', 'Meeting Done', 'Business Closed', 'Revenue Generated'];

export default function NetworkingHome({ status }) {
  const [members, setMembers] = useState([]);
  const [needs, setNeeds] = useState([]);
  const [referrals, setReferrals] = useState([]);
  const [connections, setConnections] = useState(new Set());
  const [helped, setHelped] = useState(new Set());

  useEffect(() => {
    api.members({}).then((rows) => setMembers(rows.slice(0, 3))).catch(() => setMembers([]));
    api.needs().then((rows) => setNeeds(rows.slice(0, 3))).catch(() => setNeeds([]));
    api.referrals().then(setReferrals).catch(() => setReferrals([]));
    api.listConnections().then((rows) => setConnections(new Set(rows.map((c) => c.target_user_id)))).catch(() => {});
  }, []);

  const tier = trustTier(status.networking_profile?.trust_score || 0);
  const pipeline = STAGES.map((s, i) => ({ label: STAGE_LABELS[i], n: '0' + (i + 1), count: referrals.filter((r) => r.status === s).length }));

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
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '52px 28px 96px' }}>
        <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.2fr) minmax(0,1fr)', gap: 48, alignItems: 'end', marginBottom: 44 }}>
          <div>
            <Eyebrow>TGL&apos;s private business community</Eyebrow>
            <h1 style={{ margin: '0 0 16px', fontSize: 'clamp(32px,4vw,52px)', lineHeight: 1.04, letterSpacing: '-0.035em', fontWeight: 800, color: '#2B1740' }}>
              Build relationships that move business{' '}
              <span style={{ fontFamily: "'Kaushan Script', cursive", fontWeight: 500, color: '#8F6420', letterSpacing: 0 }}>forward.</span>
            </h1>
            <p style={{ margin: 0, maxWidth: 520, fontSize: 16, lineHeight: 1.65, color: 'rgba(43,23,64,0.68)' }}>
              Discover members, exchange referrals and build meaningful business relationships within the TGL ecosystem.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <button type="button" className="tglp-gold" onClick={() => go('/app/referrals/new')} style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '15px 24px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-plus" /></svg>
              Give Referral
            </button>
            <button type="button" className="tglp-ghost" onClick={() => go('/app/networking/members')} style={{ padding: '15px 24px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              Find Members
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 60 }}>
          <div className="tgl-dark-card" style={{ padding: 24, borderRadius: 18 }}>
            <p style={{ margin: '0 0 14px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#E0B558' }}>Membership</p>
            <p style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 800, color: '#FFFBF3' }}>Active</p>
            <p style={{ margin: 0, fontSize: 13, color: 'rgba(246,238,223,0.65)' }}>
              {status.membership?.expires_at ? `Season 1 · until ${new Date(status.membership.expires_at).toLocaleDateString()}` : 'Season 1 registrant'}
            </p>
          </div>
          <div style={{ padding: 24, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
            <p style={{ margin: '0 0 14px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#6B3E96' }}>
              <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
              Trust Score
            </p>
            <p style={{ margin: '0 0 12px', fontSize: 22, fontWeight: 800, color: '#2B1740' }}>{tier.label}</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 4, marginBottom: 8 }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <span key={n} style={{ height: 4, borderRadius: 2, background: n <= tier.filled ? '#6B3E96' : 'rgba(107,62,150,0.15)' }} />
              ))}
            </div>
            <p style={{ margin: 0, fontSize: 12, color: 'rgba(43,23,64,0.65)' }}>Reflects relationship history. Not a rating.</p>
          </div>
          <div style={{ padding: 24, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
            <p style={{ margin: '0 0 14px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#A8762F' }}>
              <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-chart" /></svg>
              Growth Points
            </p>
            <p style={{ margin: '0 0 4px', fontSize: 30, fontWeight: 800, color: '#8F6420', fontVariantNumeric: 'tabular-nums' }}>{status.networking_profile?.growth_points || 0}</p>
            <p style={{ margin: 0, fontSize: 12, color: 'rgba(43,23,64,0.65)' }}>Earned through referrals and closed business.</p>
          </div>
          <div style={{ padding: 24, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
            <p style={{ margin: '0 0 14px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#35194E' }}>
              <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-medal" /></svg>
              Membership level
            </p>
            <p style={{ margin: '0 0 4px', fontSize: 22, fontWeight: 800, color: '#2B1740' }}>Season 1 Member</p>
            <p style={{ margin: 0, fontSize: 12, color: 'rgba(43,23,64,0.65)' }}>Complimentary · 3 months</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginBottom: 22 }}>
          <div>
            <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Curated for you</p>
            <h2 style={{ margin: 0, fontSize: 'clamp(24px,2.6vw,32px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#2B1740' }}>Who should you meet?</h2>
          </div>
          <a href="/app/networking/members" onClick={(e) => { e.preventDefault(); go('/app/networking/members'); }} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
            All members
            <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
          </a>
        </div>
        {members.length === 0 ? (
          <p style={{ fontSize: 14, color: 'var(--tgl-text-muted)', marginBottom: 64 }}>No other members yet — check back after more Season 1 founders activate.</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16, marginBottom: 64 }}>
            {members.map((m) => {
              const requested = connections.has(m.user_id);
              return (
                <div key={m.member_id} className="tglp-lift" style={{ border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', overflow: 'hidden' }}>
                  <div style={{ position: 'relative', height: 220 }}>
                    <ImageSlot shape="rect" label="Member photo" initial={m.founder_name || m.business_name} fontSize={64} />
                  </div>
                  <div style={{ padding: 22 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <p style={{ margin: 0, fontSize: 17, fontWeight: 800, color: '#2B1740' }}>{m.founder_name}</p>
                      {m.tgl_verified && <svg width="16" height="16" viewBox="0 0 24 24" style={{ color: '#A8762F' }}><use href="#i-shield" /></svg>}
                    </div>
                    <p style={{ margin: '0 0 12px', fontSize: 13, color: 'rgba(43,23,64,0.65)' }}>{m.business_name}</p>
                    <p style={{ margin: '0 0 18px', fontSize: 14, lineHeight: 1.55, color: 'rgba(43,23,64,0.72)' }}>{m.headline || 'No headline yet.'}</p>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button type="button" className="tglp-ghost" onClick={() => go(`/app/networking/members/${m.member_id}`)} style={{ flex: 1, padding: 12, border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                        View Profile
                      </button>
                      <button
                        type="button"
                        disabled={requested}
                        onClick={() => openConnectModal(m.business_name, m.user_id)}
                        style={{ flex: 1, padding: 12, border: 'none', borderRadius: 999, background: '#2B1740', color: '#F6EEDF', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: requested ? 'default' : 'pointer', whiteSpace: 'nowrap', opacity: requested ? 0.6 : 1 }}
                      >
                        {requested ? 'Requested' : 'Connect'}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 40 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginBottom: 18 }}>
              <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Business needs</h2>
              <a href="/app/networking/needs" onClick={(e) => { e.preventDefault(); go('/app/networking/needs'); }} style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}>Need Board</a>
            </div>
            {needs.length === 0 ? (
              <p style={{ fontSize: 14, color: 'var(--tgl-text-muted)' }}>No open needs right now.</p>
            ) : (
              <div style={{ borderTop: '1px solid rgba(53,26,78,0.12)' }}>
                {needs.map((n) => {
                  const isOwn = n.poster_user_id === status?.user?.id;
                  const done = helped.has(n.id);
                  return (
                    <div key={n.id} className="tglp-row-slide" style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '20px 8px', borderBottom: '1px solid rgba(53,26,78,0.1)' }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ margin: '0 0 4px', fontSize: 15.5, fontWeight: 700, color: '#2B1740' }}>{n.title}</p>
                        <p style={{ margin: 0, fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>
                          {n.poster_name} · {CATEGORY_MAP.get(n.category) || n.category} · {timeAgo(n.created_at)}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="tglp-help"
                        disabled={isOwn || done}
                        onClick={() => offerHelp(n)}
                        style={{ flexShrink: 0, padding: '11px 18px', border: '1px solid #C08D2E', borderRadius: 999, background: 'transparent', color: '#8A5A18', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: isOwn || done ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
                      >
                        {isOwn ? 'Your Need' : done ? 'Offer Sent' : 'I Can Help'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginBottom: 18 }}>
              <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Referral pipeline</h2>
              <a href="/app/networking/referrals" onClick={(e) => { e.preventDefault(); go('/app/networking/referrals'); }} style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}>Open</a>
            </div>
            <div style={{ padding: '8px 24px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
              {pipeline.map((p) => (
                <div key={p.label} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 0', borderBottom: '1px solid rgba(53,26,78,0.07)' }}>
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: 'rgba(43,23,64,0.65)' }}>{p.n}</span>
                  <span style={{ flex: 1, fontSize: 14, fontWeight: 600, color: '#2B1740' }}>{p.label}</span>
                  <span style={{ fontSize: 17, fontWeight: 800, color: '#6B3E96', fontVariantNumeric: 'tabular-nums' }}>{p.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
