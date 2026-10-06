import { CATEGORIES } from '../../data/categories';
import { useRef, useState } from 'react';
import { api, go } from '../../lib/customerApi';
import { showToast } from '../../components/AppShell';
import { PHOTO_TYPES, photoError, shrinkPhoto } from '../../lib/photo';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));

const VERIF_META = {
  NOT_STARTED: { label: 'Not verified', tone: 'neutral', hint: 'Add a trust badge to your profile.', cta: 'Start verification' },
  PENDING: { label: 'In review', tone: 'info', hint: 'Our team is reviewing your documents.', cta: 'View status' },
  NEEDS_INFO: { label: 'Needs information', tone: 'warn', hint: 'One more document is needed.', cta: 'Review request' },
  VERIFIED: { label: 'Verified', tone: 'success', hint: 'The TGL Verified badge is live on your profile.', cta: 'View details' },
  REJECTED: { label: 'Not approved', tone: 'danger', hint: 'You can resubmit with updated documents.', cta: 'Resubmit' },
};

const MEMBERSHIP_META = {
  ACTIVE: { label: 'Active', tone: 'success' },
  PENDING: { label: 'Pending', tone: 'warn' },
  EXPIRING: { label: 'Expiring', tone: 'warn' },
  EXPIRED: { label: 'Expired', tone: 'danger' },
};

const fmtDate = (iso) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
const hostOf = (url) => url.replace(/^https?:\/\/(www\.)?/i, '').replace(/\/$/, '');
const hrefOf = (url) => (/^https?:\/\//i.test(url) ? url : `https://${url}`);

async function logout() {
  await api.logout().catch(() => {});
  go('/login');
}

function Icon({ id, size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>
  );
}

function Pill({ tone = 'neutral', children }) {
  return <span className={`pf-pill pf-pill--${tone}`}>{children}</span>;
}

function Card({ title, icon, action, children, className = '' }) {
  return (
    <article className={`pf-card ${className}`}>
      <header className="pf-card-head">
        <h2 className="pf-card-title">
          {icon && <Icon id={icon} size={17} />}
          {title}
        </h2>
        {action}
      </header>
      {children}
    </article>
  );
}

function EditLink({ to, label = 'Edit' }) {
  return (
    <a
      href={to}
      className="pf-link"
      onClick={(e) => { e.preventDefault(); go(to); }}
    >
      {label}
    </a>
  );
}

function Row({ label, children }) {
  return (
    <div className="pf-row">
      <dt>{label}</dt>
      <dd>{children || <span className="pf-empty">Not added</span>}</dd>
    </div>
  );
}

function Strength({ pct, items }) {
  const R = 30;
  const C = 2 * Math.PI * R;
  const next = items.find((i) => !i.done);
  return (
    <Card title="Profile strength" icon="i-target">
      <div className="pf-strength">
        <div className="pf-ring" role="img" aria-label={`${pct}% complete`}>
          <svg width="76" height="76" viewBox="0 0 76 76">
            <circle cx="38" cy="38" r={R} fill="none" stroke="rgba(53,26,78,0.1)" strokeWidth="6" />
            <circle
              cx="38" cy="38" r={R} fill="none" stroke="url(#pfGold)" strokeWidth="6" strokeLinecap="round"
              strokeDasharray={C} strokeDashoffset={C * (1 - pct / 100)} transform="rotate(-90 38 38)"
            />
            <defs>
              <linearGradient id="pfGold" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#E0B558" />
                <stop offset="1" stopColor="#C08D2E" />
              </linearGradient>
            </defs>
          </svg>
          <span>{pct}%</span>
        </div>
        <p className="pf-strength-copy">
          {next ? <>Next up: <strong>{next.label.toLowerCase()}</strong>. Fuller profiles get more introductions.</> : 'Your profile is complete. Nicely done.'}
        </p>
      </div>
      <ul className="pf-checklist">
        {items.map((i) => (
          <li key={i.label} className={i.done ? 'is-done' : ''}>
            <span className="pf-tick">{i.done && <Icon id="i-check" size={11} />}</span>
            {i.done || !i.to ? (
              <span>{i.label}</span>
            ) : (
              <a href={i.to} onClick={(e) => { e.preventDefault(); go(i.to); }}>{i.label}</a>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function Profile({ status, reload }) {
  const photoInput = useRef(null);
  const [photoBusy, setPhotoBusy] = useState(false);

  async function pickPhoto(ev) {
    const file = ev.target.files?.[0];
    ev.target.value = '';
    if (!file) return;
    const problem = photoError(file);
    if (problem) {
      showToast(problem);
      return;
    }
    setPhotoBusy(true);
    try {
      await api.uploadPhoto(await shrinkPhoto(file));
      await reload?.();
      showToast('Profile photo updated.');
    } catch (err) {
      showToast(err?.message || 'Could not upload the photo.');
    } finally {
      setPhotoBusy(false);
    }
  }

  async function removePhoto() {
    setPhotoBusy(true);
    try {
      await api.removePhoto();
      await reload?.();
      showToast('Profile photo removed.');
    } catch (err) {
      showToast(err?.message || 'Could not remove the photo.');
    } finally {
      setPhotoBusy(false);
    }
  }

  const p = status.personal_profile;
  const b = status.business;
  const user = status.user;
  const membershipStatus = status.membership?.status || 'PENDING';
  const mMeta = MEMBERSHIP_META[membershipStatus] || MEMBERSHIP_META.PENDING;
  const verifStatus = b?.verification_status || 'NOT_STARTED';
  const vMeta = VERIF_META[verifStatus] || VERIF_META.NOT_STARTED;
  const hasLinks = !!(b?.website || b?.linkedin || b?.instagram);

  const items = [
    { label: 'Create your profile', done: !!p, to: '/onboarding/personal' },
    { label: 'Add a profile photo', done: !!user.photo_url, to: '/onboarding/personal' },
    { label: 'Add your business', done: !!b, to: '/onboarding/business' },
    { label: 'Write a short bio', done: !!p?.short_bio, to: '/onboarding/personal' },
    { label: 'Share your founder story', done: !!b?.founder_story, to: '/onboarding/business#founder-story' },
    { label: 'Link your website or socials', done: hasLinks, to: '/onboarding/business#links' },
    { label: 'Verify your business', done: verifStatus === 'VERIFIED', to: '/app/profile/verification' },
  ];
  const pct = Math.round((items.filter((i) => i.done).length / items.length) * 100);

  const name = p?.full_name || 'Founder';
  const initials = name.split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  const location = p?.city || b?.city;

  return (
    <main className="pf">
      <div className="pf-hero">
        <div className="pf-cover" />
        <div className="pf-hero-body">
          <div className="pf-avatar" aria-hidden="true" style={user.photo_url ? { overflow: 'hidden', padding: 0 } : undefined}>
            {user.photo_url ? (
              <img src={user.photo_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%', display: 'block' }} />
            ) : (
              initials
            )}
          </div>
          <div className="pf-ident">
            <h1>{name}</h1>
            <p className="pf-headline">
              {p?.role || 'Founder'}{b?.business_name ? <> at <strong>{b.business_name}</strong></> : null}
            </p>
            <ul className="pf-meta">
              {location && <li><Icon id="i-pin" size={14} />{location}</li>}
              {b?.category && <li><Icon id="i-briefcase" size={14} />{CATEGORY_MAP.get(b.category) || b.category}</li>}
              <li><Icon id="i-mail" size={14} />{user.email}</li>
            </ul>
            <div className="pf-badges">
              <Pill tone={mMeta.tone}>Membership · {mMeta.label}</Pill>
              <Pill tone={vMeta.tone}>{verifStatus === 'VERIFIED' && <Icon id="i-shield" size={12} />}{vMeta.label}</Pill>
            </div>
          </div>
          <div className="pf-hero-actions">
            <button type="button" className="pf-btn pf-btn--primary" onClick={() => go('/onboarding/personal')}>Edit profile</button>
            <button type="button" className="pf-btn" onClick={() => go('/onboarding/business')}>Edit business</button>
            <button type="button" className="pf-btn" disabled={photoBusy} onClick={() => photoInput.current?.click()}>
              {photoBusy ? 'Saving…' : user.photo_url ? 'Change photo' : 'Add photo'}
            </button>
            {user.photo_url && (
              <button type="button" className="pf-btn" disabled={photoBusy} onClick={removePhoto}>Remove photo</button>
            )}
            <input ref={photoInput} type="file" accept={PHOTO_TYPES.join(',')} onChange={pickPhoto} hidden />
          </div>
        </div>
      </div>

      <div className="pf-grid">
        <div className="pf-col">
          <Card title="About" icon="i-user" action={<EditLink to="/onboarding/personal" />}>
            {p?.short_bio ? <p className="pf-prose">{p.short_bio}</p> : <p className="pf-empty">Add a short bio so members know who you are.</p>}
          </Card>

          <Card title="Business" icon="i-briefcase" action={<EditLink to="/onboarding/business" />}>
            {b?.description && <p className="pf-prose pf-prose--lead">{b.description}</p>}
            <dl className="pf-rows">
              <Row label="Business">{b?.business_name}</Row>
              <Row label="Category">{b ? CATEGORY_MAP.get(b.category) || b.category : null}</Row>
              <Row label="Stage">{b?.business_stage}</Row>
              <Row label="Team size">{b?.employee_band ? `${b.employee_band} people` : null}</Row>
              <Row label="In business">{b?.business_age}</Row>
            </dl>
            {b?.founder_story && (
              <div className="pf-story">
                <h3>Founder story</h3>
                <p className="pf-prose">{b.founder_story}</p>
              </div>
            )}
          </Card>

          <Card title="Contact &amp; links" icon="i-link">
            <dl className="pf-rows">
              <Row label="Email">
                {user.email}
                {user.email_verified_at && <span className="pf-inline-ok"><Icon id="i-check" size={11} /> Verified</span>}
              </Row>
              <Row label="Phone">{p?.phone}</Row>
              <Row label="Website">{b?.website && <a className="pf-link" href={hrefOf(b.website)} target="_blank" rel="noopener noreferrer">{hostOf(b.website)}</a>}</Row>
              <Row label="LinkedIn">{b?.linkedin && <a className="pf-link" href={hrefOf(b.linkedin)} target="_blank" rel="noopener noreferrer">{hostOf(b.linkedin)}</a>}</Row>
              <Row label="Instagram">{b?.instagram && <a className="pf-link" href={hrefOf(b.instagram)} target="_blank" rel="noopener noreferrer">{hostOf(b.instagram)}</a>}</Row>
            </dl>
          </Card>
        </div>

        <aside className="pf-col">
          <Strength pct={pct} items={items} />

          <Card title="Membership" icon="i-network" action={<Pill tone={mMeta.tone}>{mMeta.label}</Pill>}>
            <p className="pf-side-copy">
              {membershipStatus === 'ACTIVE'
                ? `Season 1 Networking is active until ${fmtDate(status.membership.expires_at)}.`
                : 'Networking activates after the Grand Finale on 5 December 2026.'}
            </p>
            <a className="pf-link pf-link--arrow" href="/app/profile/membership" onClick={(e) => { e.preventDefault(); go('/app/profile/membership'); }}>
              Membership details <Icon id="i-arrow" size={14} />
            </a>
          </Card>

          <Card title="Verification" icon="i-shield" action={<Pill tone={vMeta.tone}>{vMeta.label}</Pill>}>
            <p className="pf-side-copy">{vMeta.hint} Optional, and separate from membership.</p>
            <a className="pf-link pf-link--arrow" href="/app/profile/verification" onClick={(e) => { e.preventDefault(); go('/app/profile/verification'); }}>
              {vMeta.cta} <Icon id="i-arrow" size={14} />
            </a>
          </Card>

          <Card title="Achievements" icon="i-trophy">
            <p className="pf-side-copy">Nothing yet. Achievements are earned through real contribution in Networking and Events.</p>
          </Card>

          <Card title="Account" icon="i-lock">
            {/* Notification preferences and account deletion have no endpoint
                yet; a control that does nothing is worse than its absence. */}
            <ul className="pf-account">
              <li>
                <a href="/forgot-password" onClick={(e) => { e.preventDefault(); go('/forgot-password'); }}>
                  <Icon id="i-lock" size={15} /> Change password <Icon id="i-arrow" size={14} />
                </a>
              </li>
              <li>
                <button type="button" onClick={logout}>
                  <Icon id="i-back" size={15} /> Sign out
                </button>
              </li>
            </ul>
          </Card>
        </aside>
      </div>
    </main>
  );
}
