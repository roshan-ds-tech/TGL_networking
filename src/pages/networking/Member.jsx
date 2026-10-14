import { useEffect, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { trustTier } from '../../lib/format';
import { openConnectModal, showToast } from '../../components/AppShell';
import { connectionsChanged, useConnections } from '../../lib/connections';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));

/* An empty profile field: a quiet line for visitors, a nudge to fill it for the member themselves. */
function Missing({ isMe, text, cta }) {
  return (
    <p className="mp-missing">
      {isMe ? 'You haven\u2019t added this yet.' : text}
      {isMe && <button type="button" className="mp-missing-cta" onClick={() => go('/app/profile')}>{cta} →</button>}
    </p>
  );
}

export default function Member({ id, status }) {
  const myId = status?.user?.id;
  const [member, setMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const net = useConnections();
  const [requesting, setRequesting] = useState(false);
  const [responding, setResponding] = useState(false);

  useEffect(() => {
    setLoading(true);
    setDenied(false);
    api.member(id)
      .then(setMember)
      .catch((err) => {
        setMember(null);
        if (err.status === 403) setDenied(true);
      })
      .finally(() => setLoading(false));
  }, [id]);

  async function respond(rel, action) {
    setResponding(true);
    try {
      await api.respondConnection(rel.id, action);
      showToast(action === 'accept' ? `You're now connected with ${member.founder_name}.` : 'Request ignored.');
    } catch (err) {
      showToast(err.message || 'Could not update this request.');
    } finally {
      setResponding(false);
      connectionsChanged();
    }
  }

  async function requestReferral() {
    if (!member) return;
    setRequesting(true);
    try {
      await api.createReferralRequest({ target_user_id: member.user_id });
      showToast('Referral request sent.');
    } catch (err) {
      showToast(err.message || 'Could not send the request.');
    } finally {
      setRequesting(false);
    }
  }

  if (loading) {
    return (
      <>
        <NetTabs active="Members" />
        <main style={{ maxWidth: 1240, margin: '0 auto', padding: '40px 28px 96px', textAlign: 'center', color: 'var(--tgl-text-muted)' }}>Loading member profile…</main>
      </>
    );
  }

  if (!member) {
    return (
      <>
        <NetTabs active="Members" />
        <main style={{ maxWidth: 1240, margin: '0 auto', padding: '40px 28px 96px', textAlign: 'center' }}>
          <p>{denied ? 'This profile unlocks once your Networking membership is active.' : 'Member not found.'}</p>
          <button type="button" className="tglp-ghost" onClick={() => go('/app/networking/members')} style={{ padding: '13px 24px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', cursor: 'pointer' }}>
            ← Back to Member Directory
          </button>
        </main>
      </>
    );
  }

  const isMe = !!member && member.user_id === myId;
  const rel = member ? net.relation(member.user_id) : { kind: 'none' };
  const tier = trustTier(member.trust_score || 0);
  const interests = (member.interests || '').split(',').map((s) => s.trim()).filter(Boolean);

  return (
    <>
      <NetTabs active="Members" />
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '40px 28px 96px' }}>
        <button
          type="button"
          className="tglp-navlink"
          onClick={() => go('/app/networking/members')}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 0, border: 'none', background: 'none', color: '#6B3E96', fontSize: 11, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', marginBottom: 28 }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-back" /></svg>
          Members
        </button>

        <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: '340px minmax(0,1fr)', gap: 56, alignItems: 'start' }}>
          <aside data-sticky-col="" style={{ position: 'sticky', top: 110 }}>
            <div className="tglp-framed">
              <div className="tgl-dark-card" style={{ borderRadius: 22, overflow: 'hidden', boxShadow: '0 30px 60px rgba(34,16,58,0.28)' }}>
                <div style={{ position: 'relative', height: 320 }}>
                  <ImageSlot shape="rect" label="Member photo" initial={member.founder_name || member.business_name} src={member.photo_url} fontSize={88} />
                </div>
                <div style={{ padding: 26 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
                    <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em', color: '#FFFBF3' }}>{member.founder_name}</h1>
                  </div>
                  <p style={{ margin: '0 0 14px', fontSize: 14, color: 'rgba(246,238,223,0.7)' }}>{member.business_name}</p>
                  {member.tgl_verified && (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px 6px 10px', borderRadius: 999, background: 'rgba(224,181,88,0.16)', border: '1px solid rgba(224,181,88,0.5)', color: '#EFCB77', fontSize: 10, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}>
                      <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
                      TGL Verified
                    </span>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, margin: '20px 0 22px', paddingTop: 18, borderTop: '1px dashed rgba(224,181,88,0.3)', fontSize: 13, color: 'rgba(246,238,223,0.7)' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" style={{ color: '#E0B558' }}><use href="#i-tag" /></svg>
                      {CATEGORY_MAP.get(member.category) || member.category}
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" style={{ color: '#E0B558' }}><use href="#i-pin" /></svg>
                      {member.city || 'Bengaluru'}
                    </span>
                  </div>
                  {isMe ? (
                    <>
                      <p style={{ margin: '0 0 12px', fontSize: 13, lineHeight: 1.55, color: 'rgba(246,238,223,0.72)' }}>This is how other members see you.</p>
                      <button
                        type="button"
                        className="tglp-gold"
                        onClick={() => go('/app/profile')}
                        style={{ width: '100%', padding: 15, border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                      >
                        Edit your profile
                      </button>
                    </>
                  ) : (
                    <>
                  {rel.kind === 'received' ? (
                    <div style={{ marginBottom: 10 }}>
                      <p style={{ margin: '0 0 10px', fontSize: 13, lineHeight: 1.55, color: 'rgba(246,238,223,0.78)' }}>{member.founder_name.split(' ')[0]} wants to connect with you.{rel.note ? ` “${rel.note}”` : ''}</p>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <button type="button" className="tglp-gold" disabled={responding} onClick={() => respond(rel, 'accept')} style={{ ...{ width: '100%', padding: 15, border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', whiteSpace: 'nowrap' }, cursor: responding ? 'default' : 'pointer', padding: 14 }}>{responding ? '…' : 'Accept'}</button>
                        <button type="button" className="tglp-ghost-dark" disabled={responding} onClick={() => respond(rel, 'decline')} style={{ padding: 14, border: '1px solid rgba(246,238,223,0.3)', borderRadius: 999, background: 'transparent', color: '#F6EEDF', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: responding ? 'default' : 'pointer', whiteSpace: 'nowrap' }}>Ignore</button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="tglp-gold"
                      disabled={rel.kind !== 'none'}
                      onClick={() => openConnectModal(member.business_name, member.user_id)}
                      style={{ width: '100%', padding: 15, border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', whiteSpace: 'nowrap', cursor: rel.kind === 'none' ? 'pointer' : 'default', marginBottom: 10, opacity: rel.kind === 'none' ? 1 : 0.7 }}
                    >
                      {rel.kind === 'loading' ? '…' : rel.kind === 'connected' ? '✓ Connected' : rel.kind === 'sent' ? 'Requested' : 'Connect'}
                    </button>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <button
                      type="button"
                      className="tglp-ghost-dark"
                      onClick={() => {
                        sessionStorage.setItem('tgl_referral_target', JSON.stringify({ user_id: member.user_id, business_name: member.business_name, founder_name: member.founder_name }));
                        go('/app/referrals/new');
                      }}
                      style={{ padding: '13px 8px', border: '1px solid rgba(246,238,223,0.3)', borderRadius: 999, background: 'transparent', color: '#F6EEDF', fontSize: 10, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                    >
                      Give Referral
                    </button>
                    <button
                      type="button"
                      className="tglp-ghost-dark"
                      disabled={requesting}
                      onClick={requestReferral}
                      style={{ padding: '13px 8px', border: '1px solid rgba(246,238,223,0.3)', borderRadius: 999, background: 'transparent', color: '#F6EEDF', fontSize: 10, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', cursor: requesting ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
                    >
                      {requesting ? 'Sending…' : 'Request Referral'}
                    </button>
                  </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </aside>

          <div className="mp">
            <header className="mp-intro">
              <p className="mp-eyebrow">About the business</p>
              <h2 className="mp-headline">{member.headline || `Building ${member.business_name}`}</h2>
              {member.business_description ? (
                <p className="mp-lead">{member.business_description}</p>
              ) : (
                <Missing isMe={isMe} text="No business description yet." cta="Describe your business" />
              )}
              {(member.open_to_mentoring || member.seeking_mentor) && (
                <div className="mp-flags">
                  {member.open_to_mentoring && <span className="mp-flag mp-flag--gold"><svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-bulb" /></svg>Open to mentoring</span>}
                  {member.seeking_mentor && <span className="mp-flag"><svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-compass" /></svg>Seeking a mentor</span>}
                </div>
              )}
            </header>

            <section className="mp-stats" aria-label="Network standing">
              <div className="mp-stat">
                <p className="mp-stat-label"><span className="mp-stat-ico mp-stat-ico--violet"><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-shield" /></svg></span>Trust standing</p>
                <p className="mp-stat-value mp-stat-value--text">{tier.label}</p>
                <div className="mp-meter" role="img" aria-label={`Trust level ${tier.filled} of 5`}>
                  {[1, 2, 3, 4, 5].map((n) => <span key={n} className={n <= tier.filled ? 'is-on' : ''} />)}
                </div>
              </div>
              <div className="mp-stat">
                <p className="mp-stat-label"><span className="mp-stat-ico"><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-send" /></svg></span>Referrals given</p>
                <p className="mp-stat-value">{member.referrals_given || 0}</p>
                <p className="mp-stat-sub">Introductions made</p>
              </div>
              <div className="mp-stat">
                <p className="mp-stat-label"><span className="mp-stat-ico"><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-users" /></svg></span>Referrals received</p>
                <p className="mp-stat-value">{member.referrals_received || 0}</p>
                <p className="mp-stat-sub">Introductions received</p>
              </div>
              <div className="mp-stat">
                <p className="mp-stat-label"><span className="mp-stat-ico mp-stat-ico--gold"><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-chart" /></svg></span>Growth Points</p>
                {/* The member's ledger balance, shown under the same rule as the viewer's own Growth Points page. */}
                {member.growth_points_visible ? (
                  <>
                    <p className="mp-stat-value mp-stat-value--gold">{(member.growth_points || 0).toLocaleString('en-IN')}</p>
                    <p className="mp-stat-sub">{member.growth_points_preview ? 'Preview · not redeemable yet' : 'Points held'}</p>
                  </>
                ) : (
                  <>
                    <p className="mp-stat-value mp-stat-value--soon">Soon</p>
                    <p className="mp-stat-sub">Not active yet</p>
                  </>
                )}
              </div>
            </section>
            <p className="mp-footnote">Updated from live network activity. Trust standing is defined by TGL.</p>

            <section className="mp-card">
              <h3 className="mp-card-title">Founder story</h3>
              {member.founder_story ? (
                <blockquote className="mp-quote">{member.founder_story}</blockquote>
              ) : (
                <Missing isMe={isMe} text={`${member.founder_name.split(' ')[0]} hasn't shared their story yet.`} cta="Add your founder story" />
              )}
            </section>

            <section className="mp-card">
              <h3 className="mp-card-title">Ways to work together</h3>
              <div className="mp-tiles">
                <div className="mp-tile mp-tile--violet">
                  <p className="mp-tile-label"><svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-search" /></svg>Looking for</p>
                  <p className={member.seeking_mentor ? 'mp-tile-text' : 'mp-tile-text is-empty'}>
                    {member.seeking_mentor ? 'Mentoring and guidance from experienced founders.' : 'Nothing listed right now.'}
                  </p>
                </div>
                <div className="mp-tile mp-tile--gold">
                  <p className="mp-tile-label"><svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-link" /></svg>Can help with</p>
                  <p className={member.open_to_mentoring ? 'mp-tile-text' : 'mp-tile-text is-empty'}>
                    {member.open_to_mentoring ? 'Mentoring other Season 1 founders.' : 'Nothing listed right now.'}
                  </p>
                </div>
              </div>
              <div className="mp-interests">
                <p className="mp-sub-title">Interests</p>
                {interests.length === 0 ? (
                  <p className="mp-muted">None listed yet.</p>
                ) : (
                  <ul className="mp-chips">
                    {interests.map((t) => <li key={t}>{t}</li>)}
                  </ul>
                )}
              </div>
            </section>

            <section className="mp-card mp-card--row">
              <span className="mp-trophy"><svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-trophy" /></svg></span>
              <div>
                <h3 className="mp-card-title mp-card-title--tight">Achievements</h3>
                <p className="mp-muted">No achievements yet. They appear here as they&apos;re earned.</p>
              </div>
            </section>
          </div>
        </div>
      </main>
    </>
  );
}
