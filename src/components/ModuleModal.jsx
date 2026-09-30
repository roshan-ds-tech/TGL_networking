import { useEffect } from 'react';

const MODULE_DATA = {
  vertex: {
    title: 'Vertex',
    badge: 'Public · B2B Ecosystem',
    tagline: 'Open Business Growth & Solutions Ecosystem',
    journey: 'Problem → Service → Provider → Enquiry',
    overview:
      'Vertex is the open/public B2B Business Growth Ecosystem. It helps individuals starting a business or established enterprises identify exact service needs, compare verified providers, and submit structured enquiries.',
    features: [
      {
        title: 'Comprehensive B2B Taxonomy',
        desc: 'Finance & CA, Legal & Compliance, HR & Recruitment, Marketing & Branding, Technology & AI, Property, Architecture, Events, and Fire & Safety.',
      },
      {
        title: 'Requirement-Based Search',
        desc: 'Search by natural language need, category, and location with transparent TGL Verified status and client reviews.',
      },
      {
        title: 'Outcome-Driven Enquiries',
        desc: 'Send targeted requirements directly to providers with complete delivery tracking and audit history.',
      },
    ],
    primaryAction: { label: 'Explore Events', href: '/#events' },
  },
  networking: {
    title: 'Networking',
    badge: 'Members · Closed Community',
    tagline: 'Exclusive Business Community & Reputation Engine',
    journey: 'People → Relationships → Referrals → Reputation',
    overview:
      'Networking is TGL’s exclusive, closed community for verified business owners. Members cultivate high-trust peer relationships, exchange tracked referrals, and build lasting business reputation.',
    features: [
      {
        title: 'End-to-End Referral Engine',
        desc: 'Give, request, track, and close referrals with category alerts, status updates, and confirmed win tracking.',
      },
      {
        title: 'Trust Score & Growth Points',
        desc: 'Transparent, non-resetting points model reflecting active community contribution, verified closures, and ethical conduct.',
      },
      {
        title: 'Leaderboards & Community Feed',
        desc: 'Weekly, monthly, and annual rankings recognizing top contributors, alongside weekly business updates and member directory.',
      },
    ],
    primaryAction: { label: 'Join via Season 1', href: '/#register-form' },
  },
  events: {
    title: 'Events',
    badge: 'Public + Registered · Season 1',
    tagline: 'Structured Business Platform & Grand Stage',
    journey: 'Discover → Register/Participate → Experience',
    overview:
      'Events are a core pillar of the TGL ecosystem. Season 1 brings together 400 emerging businesses in Bengaluru across 10 industry categories, culminating in the Grand Finale on 5 December 2026.',
    features: [
      {
        title: '10 Curated Competition Categories',
        desc: '40 businesses per category evaluated on structured criteria including business health, innovation, and founder vision.',
      },
      {
        title: '60 Finalists to Grand Finale',
        desc: 'Top 6 finalists from each category pitch live on the main stage to industry leaders, investors, and peers.',
      },
      {
        title: 'Participant Video Journey',
        desc: 'Professional 90-second founder video showcase with production support and widespread digital exposure.',
      },
    ],
    primaryAction: { label: 'Register for Season 1', href: '/#register-form' },
  },
  notifications: {
    title: 'Notifications',
    badge: 'Authenticated Users · Real-time',
    tagline: 'Actionable Business Signals & Alerts',
    journey: 'Signal → Action',
    overview:
      'A streamlined, noise-free notification center delivering high-priority signals on business enquiries, referrals, event milestones, and recognition without promotional spam.',
    features: [
      {
        title: 'Referral & Enquiry Signals',
        desc: 'Instant notifications when a new referral is assigned to you or an inbound enquiry arrives on your Vertex profile.',
      },
      {
        title: 'Event & Shortlist Milestones',
        desc: 'Real-time alerts regarding Season 1 registration confirmation, shortlist announcements, and jury schedules.',
      },
      {
        title: 'Reputation & Leaderboard Updates',
        desc: 'Stay informed on earned badges, Growth Points transactions, and leaderboard positioning.',
      },
    ],
    primaryAction: { label: 'Get Started with Season 1', href: '/#register-form' },
  },
  profile: {
    title: 'Profile & Account',
    badge: 'Authenticated Users · Control Center',
    tagline: 'Unified Business & Member Identity',
    journey: 'Identity → Activity → Management',
    overview:
      'A modular control center separating personal credentials from business profiles, enabling multi-user business management, service showcases, and verified community credentials.',
    features: [
      {
        title: 'Multi-Entity Architecture',
        desc: 'Logical separation between user account and business profile, built for multi-user business accounts.',
      },
      {
        title: 'Vertex Provider Showcase',
        desc: 'Manage services offered, portfolio samples, client reviews, contact info, and TGL Verified application.',
      },
      {
        title: 'Networking Reputation Record',
        desc: 'View personal Trust Score, cumulative Growth Points, referral ledger, and past event achievements.',
      },
    ],
    primaryAction: { label: 'Register Your Business', href: '/#register-form' },
  },
  awards: {
    title: 'Awards',
    badge: 'Public Discovery · Recognition',
    tagline: 'Business Excellence Recognition & History',
    journey: 'Discover → Engage → Recognise',
    overview:
      'The TGL Awards honor exceptional emerging enterprises across Season 1 categories. Awards create public credibility and permanently attach verified accolades to business profiles.',
    features: [
      {
        title: '10 Category Awards',
        desc: 'Dedicated trophies and titles for standout businesses across fashion, food, wellness, services, and tech.',
      },
      {
        title: 'Public & Jury Evaluation',
        desc: 'Transparent recognition combining jury scoring with public finalist engagement and showcase.',
      },
      {
        title: 'Permanent Profile Accolades',
        desc: 'Finalists and winners carry permanent verification badges on their Vertex and Networking profiles.',
      },
    ],
    primaryAction: { label: 'View Season 1 Categories', href: '/#categories' },
  },
  podcasts: {
    title: 'Podcasts & Stories',
    badge: 'Public · Media Ecosystem',
    tagline: 'Founder Journeys & Business Masterclasses',
    journey: 'Discover → Watch/Listen → Explore Business',
    overview:
      'Official TGL-produced interviews and founder stories showcasing real business journeys, scaling insights, and behind-the-scenes founder playbooks powered by SkyKeen.',
    features: [
      {
        title: 'High-Production Founder Interviews',
        desc: 'Structured video & audio interviews highlighting emerging entrepreneurs and breakthrough business models.',
      },
      {
        title: 'Connected Business Profiles',
        desc: 'Every episode links directly to the featured founder’s Vertex provider profile and Networking presence.',
      },
      {
        title: 'SkyKeen Media Distribution',
        desc: 'Multi-channel broadcast amplifying participating founders across social platforms and industry networks.',
      },
    ],
    primaryAction: { label: 'Participate in Season 1', href: '/#register-form' },
  },
};

export default function ModuleModal({ moduleKey, onClose }) {
  const data = moduleKey ? MODULE_DATA[moduleKey] : null;

  useEffect(() => {
    if (!data) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', handleKeyDown);
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = originalOverflow;
    };
  }, [data, onClose]);

  if (!data) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-module-title"
      style={{
        position: 'fixed',
        inset: '0',
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        background: 'rgba(23, 9, 36, 0.78)',
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        animation: 'tglRise .28s cubic-bezier(.16,1,.3,1)',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '680px',
          maxHeight: '90vh',
          overflowY: 'auto',
          overflowX: 'hidden',
          background: 'linear-gradient(170deg, #2A1344 0%, #1D0C30 55%, #150824 100%)',
          color: '#F6EEDF',
          borderRadius: '24px',
          border: '1px solid rgba(224, 181, 88, 0.38)',
          boxShadow: '0 32px 70px -20px rgba(10, 2, 20, 0.85), inset 0 1px 0 rgba(255, 255, 255, 0.15)',
          padding: 'clamp(24px, 4vw, 36px)',
        }}
      >
        {/* Glow accent */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: '0',
            right: '0',
            width: '240px',
            height: '240px',
            borderRadius: '50%',
            background: 'radial-gradient(circle at 100% 0%, rgba(224, 181, 88, 0.22) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />

        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          style={{
            position: 'absolute',
            top: '20px',
            right: '20px',
            width: '38px',
            height: '38px',
            borderRadius: '999px',
            background: 'rgba(246, 238, 223, 0.08)',
            border: '1px solid rgba(224, 181, 88, 0.28)',
            color: '#F6EEDF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            transition: 'background .2s ease, border-color .2s ease',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <path d="M1 1l12 12M13 1L1 13" />
          </svg>
        </button>

        {/* Header Section */}
        <div style={{ marginBottom: '18px' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '5px 12px', borderRadius: '999px', background: 'rgba(192, 141, 46, 0.18)', border: '1px solid rgba(224, 181, 88, 0.4)', marginBottom: '12px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#E0B558' }} />
            <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '.14em', textTransform: 'uppercase', color: '#E0B558' }}>
              {data.badge}
            </span>
          </div>

          <h2
            id="modal-module-title"
            style={{
              margin: '0 0 6px',
              fontSize: 'clamp(26px, 3.2vw, 34px)',
              fontWeight: '800',
              fontFamily: 'Archivo, Helvetica, sans-serif',
              letterSpacing: '-0.02em',
              color: '#FFFFFF',
              lineHeight: '1.15',
            }}
          >
            {data.title}
          </h2>

          <p
            style={{
              margin: '0',
              fontSize: '14px',
              fontWeight: '600',
              color: 'rgba(246, 238, 223, 0.72)',
              letterSpacing: '.02em',
            }}
          >
            {data.tagline}
          </p>
        </div>

        {/* Core Journey Rail */}
        <div
          style={{
            padding: '10px 16px',
            borderRadius: '12px',
            background: 'rgba(53, 26, 78, 0.45)',
            border: '1px solid rgba(192, 141, 46, 0.22)',
            fontSize: '12px',
            fontFamily: "'IBM Plex Mono', monospace",
            letterSpacing: '.06em',
            color: '#E0B558',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ color: 'rgba(246, 238, 223, 0.5)', textTransform: 'uppercase', fontSize: '10px', letterSpacing: '.16em' }}>
            Core Journey:
          </span>
          <span>{data.journey}</span>
        </div>

        {/* Overview */}
        <p
          style={{
            fontSize: '14.5px',
            lineHeight: '1.65',
            color: 'rgba(246, 238, 223, 0.85)',
            margin: '0 0 24px',
          }}
        >
          {data.overview}
        </p>

        {/* Feature Cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '28px' }}>
          {data.features.map((feat, idx) => (
            <div
              key={idx}
              style={{
                padding: '14px 16px',
                borderRadius: '14px',
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid rgba(255, 255, 255, 0.07)',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
              }}
            >
              <div
                style={{
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  background: 'rgba(224, 181, 88, 0.15)',
                  border: '1px solid rgba(224, 181, 88, 0.4)',
                  color: '#E0B558',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: '0',
                  marginTop: '2px',
                  fontSize: '10px',
                  fontWeight: '700',
                }}
              >
                ✓
              </div>
              <div>
                <h4 style={{ margin: '0 0 3px', fontSize: '13.5px', fontWeight: '700', color: '#F6EEDF' }}>
                  {feat.title}
                </h4>
                <p style={{ margin: '0', fontSize: '12.5px', lineHeight: '1.5', color: 'rgba(246, 238, 223, 0.65)' }}>
                  {feat.desc}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px', flexWrap: 'wrap', borderTop: '1px solid rgba(224, 181, 88, 0.2)', paddingTop: '20px' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '12px 20px',
              borderRadius: '999px',
              background: 'transparent',
              border: '1px solid rgba(246, 238, 223, 0.22)',
              color: 'rgba(246, 238, 223, 0.8)',
              fontSize: '12px',
              fontWeight: '600',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >
            Close
          </button>
          <a
            href={data.primaryAction.href}
            onClick={onClose}
            style={{
              padding: '12px 24px',
              borderRadius: '999px',
              background: 'linear-gradient(135deg, #E0B558, #C08D2E)',
              color: '#22103A',
              fontSize: '12px',
              fontWeight: '700',
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              textDecoration: 'none',
              boxShadow: '0 8px 20px -6px rgba(192, 141, 46, 0.6)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            {data.primaryAction.label}
            <span aria-hidden="true" style={{ width: '4px', height: '4px', background: '#22103A', transform: 'rotate(45deg)' }} />
          </a>
        </div>
      </div>
    </div>
  );
}
