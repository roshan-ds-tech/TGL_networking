import { useEffect, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { trustTier } from '../../lib/format';
import { openConnectModal, showToast } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));
const CAPTION = { margin: '0 0 12px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' };
const METRIC_LABEL = { margin: '0 0 10px', fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' };
const METRIC_VALUE = { margin: 0, fontSize: 24, fontWeight: 800, color: '#2B1740' };

export default function Member({ id }) {
  const [member, setMember] = useState(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [connected, setConnected] = useState(false);
  const [requesting, setRequesting] = useState(false);

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
    api.listConnections().then((rows) => {
      if (rows.some((c) => c.target_user_id === id)) setConnected(true);
    }).catch(() => {});
  }, [id]);

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
                  <button
                    type="button"
                    className="tglp-gold"
                    disabled={connected}
                    onClick={() => openConnectModal(member.business_name, member.user_id)}
                    style={{ width: '100%', padding: 15, border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: connected ? 'default' : 'pointer', whiteSpace: 'nowrap', marginBottom: 10 }}
                  >
                    {connected ? 'Requested' : 'Connect'}
                  </button>
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
                </div>
              </div>
            </div>
          </aside>

          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 1, background: 'rgba(53,26,78,0.1)', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, overflow: 'hidden', marginBottom: 14 }}>
              <div style={{ padding: 20, background: '#FFFCF5' }}>
                <p style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: '#6B3E96' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
                  Trust Score
                </p>
                <p style={{ margin: '0 0 10px', fontSize: 18, fontWeight: 800, color: '#2B1740' }}>{tier.label}</p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 3 }}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <span key={n} style={{ height: 3, background: n <= tier.filled ? '#6B3E96' : 'rgba(107,62,150,0.15)' }} />
                  ))}
                </div>
              </div>
              <div style={{ padding: 20, background: '#FFFCF5' }}>
                <p style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: '#A8762F' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-chart" /></svg>
                  Growth Points
                </p>
                <p style={{ ...METRIC_VALUE, color: '#8F6420' }}>{member.growth_points || 0}</p>
              </div>
              <div style={{ padding: 20, background: '#FFFCF5' }}>
                <p style={METRIC_LABEL}>Referrals given</p>
                <p style={METRIC_VALUE}>{member.referrals_given || 0}</p>
              </div>
              <div style={{ padding: 20, background: '#FFFCF5' }}>
                <p style={METRIC_LABEL}>Referrals received</p>
                <p style={METRIC_VALUE}>{member.referrals_received || 0}</p>
              </div>
            </div>
            <p style={{ margin: '0 0 44px', fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: 'rgba(43,23,64,0.65)' }}>
              Metrics populate from live activity. Trust Score formula is defined by TGL.
            </p>

            <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 40, marginBottom: 40 }}>
              <div>
                <p style={CAPTION}>Founder story</p>
                <p style={{ margin: 0, fontSize: 15.5, lineHeight: 1.7, color: 'rgba(43,23,64,0.75)' }}>
                  {member.founder_story || 'Not shared yet.'}
                </p>
              </div>
              <div>
                <p style={CAPTION}>Business story</p>
                <p style={{ margin: 0, fontSize: 15.5, lineHeight: 1.7, color: 'rgba(43,23,64,0.75)' }}>
                  {member.headline || 'Not shared yet.'}
                </p>
              </div>
            </div>

            <div style={{ padding: '30px 0', borderTop: '1px solid rgba(53,26,78,0.12)' }}>
              <p style={CAPTION}>What we do</p>
              <p style={{ margin: 0, fontSize: 17, lineHeight: 1.65, color: '#2B1740' }}>
                {member.business_description || 'No business description provided.'}
              </p>
            </div>

            <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: '30px 0', borderTop: '1px solid rgba(53,26,78,0.12)' }}>
              <div style={{ padding: 24, borderRadius: 18, background: 'rgba(107,62,150,0.07)' }}>
                <p style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#6B3E96' }}>
                  <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-search" /></svg>
                  Looking for
                </p>
                <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: '#2B1740' }}>
                  {member.seeking_mentor ? 'Mentoring and guidance from experienced founders.' : 'Nothing listed right now.'}
                </p>
              </div>
              <div style={{ padding: 24, borderRadius: 18, background: 'rgba(192,141,46,0.1)' }}>
                <p style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 10.5, fontWeight: 700, letterSpacing: '.22em', textTransform: 'uppercase', color: '#8A5A18' }}>
                  <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-link" /></svg>
                  Can help with
                </p>
                <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: '#2B1740' }}>
                  {member.open_to_mentoring ? 'Mentoring other Season 1 founders.' : 'Nothing listed right now.'}
                </p>
              </div>
            </div>

            <div style={{ padding: '30px 0', borderTop: '1px solid rgba(53,26,78,0.12)' }}>
              <p style={{ ...CAPTION, marginBottom: 14 }}>Interests</p>
              {interests.length === 0 ? (
                <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.65)' }}>None listed yet.</p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {interests.map((t) => (
                    <span key={t} style={{ padding: '8px 14px', border: '1px solid rgba(53,26,78,0.14)', borderRadius: 999, fontSize: 13, fontWeight: 600, color: '#35194E', background: '#FFFCF5' }}>{t}</span>
                  ))}
                </div>
              )}
            </div>

            <div style={{ padding: '30px 0 0', borderTop: '1px solid rgba(53,26,78,0.12)' }}>
              <p style={{ ...CAPTION, marginBottom: 14 }}>Achievements</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '20px 22px', border: '1px dashed rgba(53,26,78,0.2)', borderRadius: 16 }}>
                <svg width="22" height="22" viewBox="0 0 24 24" style={{ color: 'rgba(43,23,64,0.65)' }}><use href="#i-trophy" /></svg>
                <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.65)' }}>No achievements yet. They appear here as they&apos;re earned.</p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
