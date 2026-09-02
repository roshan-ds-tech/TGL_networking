import logo from '../assets/logo.png';

export default function Header({ headerRef, progressRef, menuOpen, toggleMenu, closeMenu }) {
  return (
    <header ref={headerRef} style={{ position: 'sticky', top: '0', zIndex: '60', background: 'linear-gradient(180deg, rgba(252,246,234,0.95), rgba(246,238,223,0.88))', backdropFilter: 'blur(18px) saturate(1.35)', WebkitBackdropFilter: 'blur(18px) saturate(1.35)', borderBottom: '1px solid rgba(192,141,46,0.22)', transition: 'box-shadow .3s ease, background .3s ease' }}>
      <div style={{ position: 'absolute', left: '0', right: '0', top: '0', height: '1px', pointerEvents: 'none', background: 'linear-gradient(90deg, rgba(192,141,46,0), rgba(224,181,88,0.65) 50%, rgba(192,141,46,0))' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto', padding: '13px 28px', display: 'flex', alignItems: 'center', gap: '24px' }}>
        <a href="#top" style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: '0' }}>
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
        <nav data-nav-desktop="" data-nav-rail="" aria-label="Primary" style={{ display: 'flex', alignItems: 'center', gap: '26px', marginLeft: 'auto', padding: '10px 24px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: '999px', background: 'rgba(255,252,245,0.55)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.6)', fontSize: '11.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase' }}>
          <a data-navlink="" href="#about" style={{ color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' }} className="hv-1">
            About
          </a>
          <a data-navlink="" href="#why" style={{ color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' }} className="hv-2">
            Why TGL
          </a>
          <a data-navlink="" href="#categories" style={{ color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' }} className="hv-3">
            Categories
          </a>
          <a data-navlink="" href="#journey" style={{ color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' }} className="hv-4">
            Journey
          </a>
          <a data-navlink="" href="#finale" style={{ color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' }} className="hv-5">
            Finale
          </a>
          <a data-navlink="" href="#contact" style={{ color: 'rgba(43,23,64,0.78)', transition: 'color .2s ease' }} className="hv-6">
            Contact
          </a>
        </nav>
        <a data-nav-desktop="" href="#register" style={{ position: 'relative', overflow: 'hidden', flexShrink: '0', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: '10px', background: 'linear-gradient(135deg, #EFCB77, #E0B558 45%, #C08D2E)', color: '#22103A', fontWeight: '700', fontSize: '12px', letterSpacing: '.14em', textTransform: 'uppercase', padding: '14px 24px', borderRadius: '999px', boxShadow: '0 8px 22px -8px rgba(192,141,46,0.7), inset 0 1px 0 rgba(255,255,255,0.45)', transition: 'transform .2s ease, box-shadow .2s ease' }} className="hv-7">
          Register Now
          <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0' }}>
            <use href="#i-arrow"></use>
          </svg>
        </a>
        <button data-nav-mobile="" type="button" aria-label="Open menu" aria-expanded={menuOpen} onClick={toggleMenu} style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '5px', background: 'rgba(255,252,245,0.7)', border: '1px solid rgba(53,26,78,0.16)', borderRadius: '999px', width: '48px', height: '48px', color: '#2B1740', cursor: 'pointer' }}>
          <span style={{ display: 'block', width: '18px', height: '1.5px', borderRadius: '2px', background: '#2B1740' }}></span>
          <span style={{ display: 'block', width: '18px', height: '1.5px', borderRadius: '2px', background: '#2B1740' }}></span>
          <span style={{ display: 'block', width: '11px', height: '1.5px', borderRadius: '2px', background: '#C08D2E' }}></span>
        </button>
      </div>
      {menuOpen && (
        <div data-nav-mobile="" style={{ borderTop: '1px solid rgba(192,141,46,0.22)', background: 'linear-gradient(180deg, #FFFCF5, #F6EEDF)', padding: '14px 28px 26px', display: 'flex', flexDirection: 'column', gap: '2px', boxShadow: '0 24px 40px -28px rgba(53,26,78,0.4)' }}>
          <a href="#about" onClick={closeMenu} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '15px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' }} className="hv-8">
            About TGL
          </a>
          <a href="#why" onClick={closeMenu} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '15px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' }} className="hv-9">
            Why TGL
          </a>
          <a href="#categories" onClick={closeMenu} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '15px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' }} className="hv-10">
            Categories
          </a>
          <a href="#journey" onClick={closeMenu} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '15px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' }} className="hv-11">
            Participant Journey
          </a>
          <a href="#finale" onClick={closeMenu} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '15px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' }} className="hv-12">
            Grand Finale
          </a>
          <a href="#contact" onClick={closeMenu} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#2B1740', padding: '15px 2px', fontSize: '12.5px', fontWeight: '700', letterSpacing: '.16em', textTransform: 'uppercase', borderBottom: '1px solid rgba(53,26,78,0.09)' }} className="hv-13">
            Contact
          </a>
          <a href="#register" onClick={closeMenu} style={{ marginTop: '14px', textAlign: 'center', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', color: '#22103A', fontWeight: '700', letterSpacing: '.06em', textTransform: 'uppercase', padding: '16px', borderRadius: '999px' }}>
            Register Now
          </a>
        </div>
      )}
      <div style={{ position: 'absolute', left: '0', right: '0', bottom: '-1px', height: '2px', overflow: 'hidden', pointerEvents: 'none' }}>
        <div ref={progressRef} style={{ height: '100%', width: '100%', transform: 'scaleX(0)', transformOrigin: 'left', background: 'linear-gradient(90deg, #6B3E96, #C08D2E 55%, #EFCB77)' }}></div>
      </div>
    </header>
  );
}
