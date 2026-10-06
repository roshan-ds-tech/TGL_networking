import { useEffect, useRef, useState } from 'react';
import { go } from '../lib/customerApi';
import { moduleClickHandler } from '../lib/moduleNav';
import logo from '../assets/logo.png';

/* The one navbar for the whole site — the marketing homepage and every
   product screen (/login, onboarding, /app/*) render this same header, so the
   links never change under the user as they move between the two.

   Signed in: Vertex · Networking · Events · More, plus bell + profile icons.
   Signed out: same links, plus a Create Account (or Sign In) button. Vertex
   and Networking go through moduleClickHandler, which sends a signed-out
   visitor to /login?next=… and back to the page they clicked. */

const LINK_STYLE = { color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' };
const MOBILE_ROW = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '14px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' };
const MOBILE_TAG = { fontSize: '10px', color: '#C08D2E', letterSpacing: '.08em', fontWeight: '600' };
const MOBILE_CHIP = { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '10px 14px', borderRadius: '10px', background: 'rgba(53,26,78,0.05)', border: '1px solid rgba(53,26,78,0.1)', color: '#2B1740', fontSize: '11px', fontWeight: '700', letterSpacing: '.12em', textTransform: 'uppercase' };
const MORE_ITEM = { padding: '8px 12px', borderRadius: '8px', color: '#2B1740', fontSize: '11px', fontWeight: '700', letterSpacing: '.14em', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '8px', transition: 'background .18s ease, color .18s ease' };
const ICON_BTN = { position: 'relative', width: 44, height: 44, borderRadius: '50%', border: '1px solid rgba(53,26,78,0.14)', background: 'rgba(255,252,245,0.7)', color: '#2B1740', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 };

const isVertex = (p) => p.startsWith('/app/vertex');
const isNetworking = (p) => p.startsWith('/app/networking') || p.startsWith('/app/referrals') || p.startsWith('/app/needs');
const isEvents = (p) => p === '/app/events';

function moreHover(on) {
  return (e) => {
    e.currentTarget.style.background = on ? 'rgba(192,141,46,0.12)' : 'transparent';
    e.currentTarget.style.color = on ? '#6B3E96' : '#2B1740';
  };
}

export default function SiteHeader({ path, authUser, authChecked, unread = 0, onOpenModule, headerRef, progressRef }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef(null);

  const isHome = path === '/';
  const signedIn = !!authUser;
  const openModule = moduleClickHandler({ authUser, authChecked, onOpenModule });
  const closeMenu = () => setMenuOpen(false);

  useEffect(() => {
    const handleDocClick = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false);
    };
    document.addEventListener('click', handleDocClick);
    return () => document.removeEventListener('click', handleDocClick);
  }, []);

  // Close the mobile menu whenever the route changes underneath it.
  useEffect(() => {
    setMenuOpen(false);
    setMoreOpen(false);
  }, [path]);

  function goHome(e) {
    e.preventDefault();
    closeMenu();
    if (isHome) window.scrollTo({ top: 0, behavior: 'smooth' });
    else go('/');
  }

  // Signed in, Events is the member's Season 1 page. Signed out it is the
  // homepage section — an in-page anchor there, a full link from elsewhere.
  const eventsHref = signedIn ? '/app/events' : isHome ? '#events' : '/#events';
  function openEvents(e) {
    closeMenu();
    if (signedIn) {
      e.preventDefault();
      go('/app/events');
    }
  }

  const cta = path === '/signup'
    ? { label: 'Sign In', to: '/login' }
    : { label: 'Create Account', to: '/signup' };

  function openCta(e) {
    e.preventDefault();
    closeMenu();
    go(cta.to);
  }

  return (
    <header ref={headerRef} style={{ position: 'sticky', top: '0', zIndex: '60', background: 'linear-gradient(180deg, rgba(252,246,234,0.95), rgba(246,238,223,0.88))', backdropFilter: 'blur(18px) saturate(1.35)', WebkitBackdropFilter: 'blur(18px) saturate(1.35)', borderBottom: '1px solid rgba(192,141,46,0.22)', transition: 'box-shadow .3s ease, background .3s ease', animation: 'tglNavIn .32s ease' }}>
      <div style={{ position: 'absolute', left: '0', right: '0', top: '0', height: '1px', pointerEvents: 'none', background: 'linear-gradient(90deg, rgba(192,141,46,0), rgba(224,181,88,0.65) 50%, rgba(192,141,46,0))' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto', padding: '13px 28px', display: 'flex', alignItems: 'center', gap: '24px' }}>
        <a href="/" onClick={goHome} aria-label="The Growth League — home" style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: '0' }}>
          <img src={logo} alt="The Growth League logo" style={{ height: '44px', width: 'auto', display: 'block' }} />
          <span data-nav-desktop="" data-nav-wordmark="" style={{ width: '1px', height: '30px', background: 'linear-gradient(180deg, rgba(53,26,78,0), rgba(53,26,78,0.22), rgba(53,26,78,0))' }}></span>
          <span data-nav-desktop="" data-nav-wordmark="" style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '12.5px', fontWeight: '800', letterSpacing: '.16em', textTransform: 'uppercase', color: '#2B1740', lineHeight: '1' }}>
              The Growth League
            </span>
            <span style={{ fontSize: '9.5px', fontWeight: '700', letterSpacing: '.28em', textTransform: 'uppercase', color: '#C08D2E', lineHeight: '1' }}>
              Season 1 · Bengaluru
            </span>
          </span>
        </a>

        <nav data-nav-desktop="" data-nav-rail="" aria-label="Primary" style={{ display: 'flex', alignItems: 'center', gap: '22px', marginLeft: 'auto', padding: '10px 22px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: '999px', background: 'rgba(255,252,245,0.55)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.6)', fontSize: '11.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase' }}>
          <a data-navlink="" data-active={isVertex(path) ? '' : undefined} href="/app/vertex" onClick={openModule('vertex')} style={LINK_STYLE} className="hv-1">
            Vertex
          </a>
          <a data-navlink="" data-active={isNetworking(path) ? '' : undefined} href="/app/networking" onClick={openModule('networking')} style={LINK_STYLE} className="hv-2">
            Networking
          </a>
          <a data-navlink="" data-active={isEvents(path) ? '' : undefined} href={eventsHref} onClick={openEvents} style={LINK_STYLE} className="hv-3">
            Events
          </a>

          {/* Secondary menu for Awards & Podcasts */}
          <div ref={moreRef} style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <button
              type="button"
              data-navlink=""
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              aria-label="More navigation links"
              style={{ background: 'none', border: 'none', padding: '0', cursor: 'pointer', font: 'inherit', color: 'rgba(43,23,64,0.78)', letterSpacing: 'inherit', textTransform: 'inherit', fontWeight: 'inherit', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
              className="hv-6"
            >
              More
              <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ transform: moreOpen ? 'rotate(180deg)' : 'none', transition: 'transform .2s ease' }}>
                <path d="M2 3.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {moreOpen && (
              <div style={{ position: 'absolute', top: 'calc(100% + 14px)', right: '-10px', minWidth: '150px', background: 'linear-gradient(180deg, #FFFCF5, #F6EEDF)', border: '1px solid rgba(192,141,46,0.3)', borderRadius: '14px', boxShadow: '0 16px 36px -12px rgba(53,26,78,0.28)', padding: '6px', display: 'flex', flexDirection: 'column', gap: '2px', zIndex: 70 }}>
                <a href="#awards" onClick={openModule('awards', () => setMoreOpen(false))} style={MORE_ITEM} onMouseEnter={moreHover(true)} onMouseLeave={moreHover(false)}>
                  Awards
                </a>
                <a href="#podcasts" onClick={openModule('podcasts', () => setMoreOpen(false))} style={MORE_ITEM} onMouseEnter={moreHover(true)} onMouseLeave={moreHover(false)}>
                  Podcasts
                </a>
              </div>
            )}
          </div>
        </nav>

        {/* On mobile the rail is hidden; this spacer pushes the right-hand
            controls to the edge in its place. */}
        <span data-nav-mobile="" style={{ marginLeft: 'auto' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
          {signedIn ? (
            <>
              <button type="button" className="tglp-icon-btn" onClick={() => go('/app/notifications')} aria-label={unread > 0 ? `Notifications (${unread} unread)` : 'Notifications'} aria-current={path === '/app/notifications' ? 'page' : undefined} style={ICON_BTN}>
                <svg width="18" height="18" viewBox="0 0 24 24"><use href="#i-bell" /></svg>
                {unread > 0 && (
                  <span style={{ position: 'absolute', top: 10, right: 11, width: 7, height: 7, borderRadius: '50%', background: '#C08D2E', boxShadow: '0 0 0 2px #FBF5E9' }} />
                )}
              </button>
              <button type="button" onClick={() => go('/app/profile')} aria-label="Profile" aria-current={path.startsWith('/app/profile') ? 'page' : undefined} style={{ width: 44, height: 44, borderRadius: '50%', border: '1px solid rgba(192,141,46,0.5)', padding: 2, background: 'transparent', cursor: 'pointer', flexShrink: 0 }}>
                <span style={{ width: 38, height: 38, borderRadius: '50%', background: '#2B1740', color: '#EFCB77', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
                  {authUser?.photo_url ? (
                    <img src={authUser.photo_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24"><use href="#i-user" /></svg>
                  )}
                </span>
              </button>
            </>
          ) : (
            <a data-nav-desktop="" href={cta.to} onClick={openCta} style={{ position: 'relative', overflow: 'hidden', flexShrink: '0', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: '10px', background: 'linear-gradient(135deg, #EFCB77, #E0B558 45%, #C08D2E)', color: '#22103A', fontWeight: '700', fontSize: '12px', letterSpacing: '.14em', textTransform: 'uppercase', padding: '14px 24px', borderRadius: '999px', boxShadow: '0 8px 22px -8px rgba(192,141,46,0.7), inset 0 1px 0 rgba(255,255,255,0.45)', transition: 'transform .35s cubic-bezier(.34,1.56,.64,1), box-shadow .3s ease, filter .3s ease' }} className="hv-7">
              {cta.label}
              <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0' }}>
                <use href="#i-arrow"></use>
              </svg>
            </a>
          )}
          <button data-nav-mobile="" type="button" aria-label="Open menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '5px', background: 'rgba(255,252,245,0.7)', border: '1px solid rgba(53,26,78,0.16)', borderRadius: '999px', width: '48px', height: '48px', color: '#2B1740', cursor: 'pointer' }}>
            <span style={{ display: 'block', width: '18px', height: '1.5px', borderRadius: '2px', background: '#2B1740' }}></span>
            <span style={{ display: 'block', width: '18px', height: '1.5px', borderRadius: '2px', background: '#2B1740' }}></span>
            <span style={{ display: 'block', width: '11px', height: '1.5px', borderRadius: '2px', background: '#C08D2E' }}></span>
          </button>
        </div>
      </div>

      {menuOpen && (
        <div data-nav-mobile="" style={{ borderTop: '1px solid rgba(192,141,46,0.22)', background: 'linear-gradient(180deg, #FFFCF5, #F6EEDF)', padding: '14px 28px 26px', display: 'flex', flexDirection: 'column', gap: '2px', boxShadow: '0 24px 40px -28px rgba(53,26,78,0.4)' }}>
          <a href="/app/vertex" onClick={openModule('vertex', closeMenu)} style={MOBILE_ROW} className="hv-8">
            <span>Vertex</span>
            <span style={MOBILE_TAG}>B2B Ecosystem</span>
          </a>
          <a href="/app/networking" onClick={openModule('networking', closeMenu)} style={MOBILE_ROW} className="hv-9">
            <span>Networking</span>
            <span style={MOBILE_TAG}>Community</span>
          </a>
          <a href={eventsHref} onClick={openEvents} style={MOBILE_ROW} className="hv-10">
            <span>Events</span>
            <span style={MOBILE_TAG}>Season 1</span>
          </a>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', padding: '12px 0 6px' }}>
            <a href="#awards" onClick={openModule('awards', closeMenu)} style={MOBILE_CHIP} className="hv-8">
              Awards
            </a>
            <a href="#podcasts" onClick={openModule('podcasts', closeMenu)} style={MOBILE_CHIP} className="hv-9">
              Podcasts
            </a>
          </div>
          {!signedIn && (
            <a href={cta.to} onClick={openCta} style={{ marginTop: '12px', textAlign: 'center', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', color: '#22103A', fontWeight: '700', letterSpacing: '.06em', textTransform: 'uppercase', padding: '16px', borderRadius: '999px' }}>
              {cta.label}
            </a>
          )}
        </div>
      )}

      {progressRef && (
        <div style={{ position: 'absolute', left: '0', right: '0', bottom: '-1px', height: '2px', overflow: 'hidden', pointerEvents: 'none' }}>
          <div ref={progressRef} style={{ height: '100%', width: '100%', transform: 'scaleX(0)', transformOrigin: 'left', background: 'linear-gradient(90deg, #6B3E96, #C08D2E 55%, #EFCB77)' }}></div>
        </div>
      )}
    </header>
  );
}
