import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import ImageSlot from '../../components/ImageSlot';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));

const VERIF_LABELS = {
  NOT_STARTED: 'Not started',
  PENDING: 'Pending review',
  NEEDS_INFO: 'Needs information',
  VERIFIED: 'Verified',
  REJECTED: 'Not approved',
};

const MEMBERSHIP_META = {
  ACTIVE: { bg: '#C08D2E', color: '#22103A', label: 'Active' },
  PENDING: { bg: 'rgba(224,181,88,0.16)', color: '#EFCB77', label: 'Pending' },
  EXPIRING: { bg: 'rgba(224,181,88,0.16)', color: '#EFCB77', label: 'Expiring' },
  EXPIRED: { bg: 'rgba(142,59,59,0.14)', color: '#8E3B3B', label: 'Expired' },
};

async function logout() {
  await api.logout().catch(() => {});
  go('/login');
}

export default function Profile({ status }) {
  const p = status.personal_profile;
  const b = status.business;
  const membershipStatus = status.membership?.status || 'PENDING';
  const meta = MEMBERSHIP_META[membershipStatus] || MEMBERSHIP_META.PENDING;
  const verifLabel = VERIF_LABELS[b?.verification_status] || 'Not started';

  const completeness = [!!p, !!b, !!p?.short_bio, !!b?.description].filter(Boolean).length;
  const pct = Math.round((completeness / 4) * 100);

  return (
    <main style={{ maxWidth: 1240, margin: '0 auto', padding: '48px 28px 96px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap', paddingBottom: 34, borderBottom: '1px solid rgba(53,26,78,0.12)', marginBottom: 36 }}>
        <ImageSlot shape="circle" label="Photo" initial={p?.full_name || 'F'} style={{ width: 96, height: 96 }} fontSize={34} />
        <div style={{ flex: 1, minWidth: 220 }}>
          <p style={{ margin: '0 0 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Your profile</p>
          <h1 style={{ margin: '0 0 6px', fontSize: 'clamp(28px, 3.2vw, 40px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#2B1740' }}>{p?.full_name || 'Founder'}</h1>
          <p style={{ margin: 0, fontSize: 14.5, color: 'rgba(43,23,64,0.6)' }}>{p?.role || 'Founder'} · {b?.business_name || 'Your Business'} · {p?.city || b?.city || 'Bengaluru'}</p>
        </div>
        <div style={{ minWidth: 220, padding: '20px 22px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
            <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.55)' }}>Profile completeness</span>
            <span style={{ fontSize: 20, fontWeight: 800, color: '#2B1740' }}>{pct}%</span>
          </div>
          <div style={{ height: 5, borderRadius: 999, background: 'rgba(53,26,78,0.1)', overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: 'linear-gradient(90deg,#C08D2E,#EFCB77)' }} />
          </div>
          <p style={{ margin: '10px 0 0', fontSize: 12, color: 'rgba(43,23,64,0.5)' }}>Add a business story to finish. Not required to use Networking.</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
        <div style={{ padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5' }}>
          <p style={{ margin: '0 0 18px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 800, color: '#2B1740' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: '#6B3E96' }}><use href="#i-user" /></svg>
            Personal information
          </p>
          <p style={{ margin: '0 0 8px', fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{status.user.email}</p>
          <p style={{ margin: '0 0 8px', fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{p?.phone || 'Not specified'}</p>
          <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{p?.city || 'Not specified'}</p>
        </div>

        <div style={{ padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5' }}>
          <p style={{ margin: '0 0 18px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 800, color: '#2B1740' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: '#6B3E96' }}><use href="#i-briefcase" /></svg>
            Business information
          </p>
          <p style={{ margin: '0 0 8px', fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{b?.business_name || 'Not specified'}</p>
          <p style={{ margin: '0 0 8px', fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{CATEGORY_MAP.get(b?.category) || b?.category || 'General'}</p>
          <p style={{ margin: 0, fontSize: 14, color: 'rgba(43,23,64,0.7)' }}>{b?.employee_band ? `${b.employee_band} people` : 'Team size not specified'}</p>
        </div>

        <button
          type="button"
          onClick={() => go('/app/profile/membership')}
          className="tgl-dark-card tglp-lift-flat"
          style={{ textAlign: 'left', padding: 26, border: 'none', borderRadius: 20, cursor: 'pointer' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
            <p style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 800, color: '#FFFBF3' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: '#E0B558' }}><use href="#i-network" /></svg>
              Membership
            </p>
            <svg width="16" height="16" viewBox="0 0 24 24" style={{ color: '#E0B558' }}><use href="#i-arrow" /></svg>
          </div>
          <span style={{ display: 'inline-block', padding: '6px 12px', borderRadius: 999, background: meta.bg, color: meta.color, fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', marginBottom: 10 }}>
            {meta.label}
          </span>
          <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, color: 'rgba(246,238,223,0.7)' }}>
            {membershipStatus === 'ACTIVE'
              ? `Active until ${new Date(status.membership.expires_at).toLocaleDateString()}.`
              : 'Activates after the Grand Finale on 5 December 2026.'}
          </p>
        </button>

        <button
          type="button"
          onClick={() => go('/app/profile/verification')}
          className="tglp-lift-flat"
          style={{ textAlign: 'left', padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', cursor: 'pointer' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
            <p style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 800, color: '#2B1740' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: '#A8762F' }}><use href="#i-shield" /></svg>
              Business verification
            </p>
            <svg width="16" height="16" viewBox="0 0 24 24" style={{ color: '#C08D2E' }}><use href="#i-arrow" /></svg>
          </div>
          <p style={{ margin: '0 0 6px', fontSize: 15, fontWeight: 700, color: '#2B1740' }}>{verifLabel}</p>
          <p style={{ margin: 0, fontSize: 13.5, color: 'rgba(43,23,64,0.58)' }}>Optional · separate from membership</p>
        </button>

        <div style={{ padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5' }}>
          <p style={{ margin: '0 0 18px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 800, color: '#2B1740' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: '#6B3E96' }}><use href="#i-trophy" /></svg>
            Achievements
          </p>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'rgba(43,23,64,0.58)' }}>
            Nothing yet. Achievements are awarded for real contribution in Networking and Events.
          </p>
        </div>
      </div>

      <div style={{ marginTop: 16, padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', display: 'flex', flexWrap: 'wrap', gap: '12px 28px', alignItems: 'center' }}>
        <p style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#2B1740', flex: '1 1 200px' }}>Account settings</p>
        {/* The design source also lists "Notification preferences" and
            "Delete account" here. Neither has an endpoint behind it yet, and
            a settings link that does nothing is worse than its absence. */}
        <a href="/forgot-password" onClick={(e) => { e.preventDefault(); go('/forgot-password'); }} style={{ fontSize: 13.5, fontWeight: 600 }}>Change password</a>
        <a href="/login" onClick={(e) => { e.preventDefault(); logout(); }} style={{ fontSize: 13.5, fontWeight: 600 }}>Sign out</a>
      </div>
    </main>
  );
}
