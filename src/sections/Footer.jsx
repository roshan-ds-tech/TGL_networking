export default function Footer() {
  return (
    <footer style={{ position: 'relative', overflow: 'hidden', background: 'linear-gradient(180deg, #22103A 0%, #1A0B2E 100%)', color: '#F6EEDF', padding: '78px 28px 34px' }}>
      <span aria-hidden="true" style={{ position: 'absolute', top: '0', left: '0', right: '0', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.7), rgba(224,181,88,0))' }}></span>
      <div aria-hidden="true" style={{ position: 'absolute', top: '0', left: '50%', transform: 'translateX(-50%)', width: '900px', height: '460px', background: 'radial-gradient(ellipse at 50% 0%, rgba(224,181,88,0.16), rgba(224,181,88,0) 68%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div aria-hidden="true" style={{ position: 'absolute', bottom: '0', right: '-120px', width: '520px', height: '520px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(107,62,150,0.34), rgba(107,62,150,0) 70%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '48px', paddingBottom: '44px', borderBottom: '1px solid rgba(224,181,88,0.25)' }}>
          <div style={{ flex: '2 1 340px', minWidth: '0' }}>
            <p style={{ margin: '0 0 10px', fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: '27px', lineHeight: '1.2', letterSpacing: '-0.01em', color: '#E0B558' }}>
              A stage for recognition.
            </p>
            <p style={{ margin: '0 0 26px', fontSize: '15px', lineHeight: '1.72', color: 'rgba(246,238,223,0.6)', maxWidth: '390px', textWrap: 'pretty' }}>
              A platform for visibility. A stage for recognition. An ecosystem for growth. Season 1, powered by SkyKeen Events.
            </p>
            <a href="#register" style={{ display: 'inline-flex', alignItems: 'center', gap: '12px', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', color: '#22103A', fontWeight: '700', fontSize: '13px', letterSpacing: '.08em', textTransform: 'uppercase', padding: '16px 32px', borderRadius: '999px', textDecoration: 'none', boxShadow: '0 12px 28px rgba(192,141,46,0.28)', transition: 'transform .22s ease, box-shadow .22s ease' }} className="hv-85">
              Register Now
              <span aria-hidden="true" style={{ width: '5px', height: '5px', background: '#22103A', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
            </a>
          </div>
          <div style={{ flex: '1 1 180px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
              <p style={{ margin: '0', fontSize: '10.5px', letterSpacing: '.24em', textTransform: 'uppercase', fontWeight: '700', color: '#E0B558' }}>
                Explore
              </p>
              <span aria-hidden="true" style={{ flex: '1', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0.5), rgba(224,181,88,0))' }}></span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '13px', fontSize: '15px' }}>
              <a href="#about" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'rgba(246,238,223,0.72)', textDecoration: 'none', transition: 'color .22s ease, transform .22s ease' }} className="hv-86">
                <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
                About TGL
              </a>
              <a href="#why" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'rgba(246,238,223,0.72)', textDecoration: 'none', transition: 'color .22s ease, transform .22s ease' }} className="hv-87">
                <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
                Why TGL
              </a>
              <a href="#categories" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'rgba(246,238,223,0.72)', textDecoration: 'none', transition: 'color .22s ease, transform .22s ease' }} className="hv-88">
                <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
                Categories
              </a>
              <a href="#journey" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'rgba(246,238,223,0.72)', textDecoration: 'none', transition: 'color .22s ease, transform .22s ease' }} className="hv-89">
                <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
                Participant Journey
              </a>
              <a href="#finale" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'rgba(246,238,223,0.72)', textDecoration: 'none', transition: 'color .22s ease, transform .22s ease' }} className="hv-90">
                <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
                Grand Finale
              </a>
              <a href="#faq" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'rgba(246,238,223,0.72)', textDecoration: 'none', transition: 'color .22s ease, transform .22s ease' }} className="hv-91">
                <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
                FAQ
              </a>
            </div>
          </div>
          <div style={{ flex: '1 1 260px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
              <p style={{ margin: '0', fontSize: '10.5px', letterSpacing: '.24em', textTransform: 'uppercase', fontWeight: '700', color: '#E0B558' }}>
                Season 1
              </p>
              <span aria-hidden="true" style={{ flex: '1', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0.5), rgba(224,181,88,0))' }}></span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '16px', padding: '11px 0', borderBottom: '1px solid rgba(224,181,88,0.16)' }}>
                <span style={{ fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.45)' }}>
                  Registration closes
                </span>
                <span style={{ fontSize: '13.5px', fontWeight: '600', color: 'rgba(246,238,223,0.85)', textAlign: 'right' }}>
                  20 Nov 2026
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '16px', padding: '11px 0', borderBottom: '1px solid rgba(224,181,88,0.16)' }}>
                <span style={{ fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.45)' }}>
                  Grand Finale
                </span>
                <span style={{ fontSize: '13.5px', fontWeight: '600', color: 'rgba(246,238,223,0.85)', textAlign: 'right' }}>
                  5 Dec 2026
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '16px', padding: '11px 0', borderBottom: '1px solid rgba(224,181,88,0.16)' }}>
                <span style={{ fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.45)' }}>
                  Location
                </span>
                <span style={{ fontSize: '13.5px', fontWeight: '600', color: 'rgba(246,238,223,0.85)', textAlign: 'right' }}>
                  Bengaluru, India
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '16px', padding: '11px 0' }}>
                <span style={{ fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.45)' }}>
                  Social links
                </span>
                <span style={{ fontSize: '13.5px', fontWeight: '600', color: 'rgba(246,238,223,0.85)', textAlign: 'right' }}>
                  To Be Announced
                </span>
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px 24px', justifyContent: 'space-between', alignItems: 'center', paddingTop: '26px', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '12.5px', letterSpacing: '.08em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.62)' }}>
          <span>
            © 2026 The Growth League · Powered by SkyKeen Events
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}>
            <span aria-hidden="true" style={{ width: '4px', height: '4px', background: 'rgba(224,181,88,0.7)', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
            Registration does not guarantee selection.
          </span>
        </div>
      </div>
    </footer>
  );
}
