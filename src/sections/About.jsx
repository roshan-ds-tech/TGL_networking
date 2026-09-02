import logo from '../assets/logo.png';

export default function About() {
  return (
    <section id="about" style={{ position: 'relative', overflow: 'hidden', padding: '104px 28px 108px', background: 'transparent' }}>
      <div style={{ position: 'absolute', inset: '0', pointerEvents: 'none', backgroundImage: 'linear-gradient(rgba(53,26,78,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(53,26,78,0.04) 1px, transparent 1px)', backgroundSize: '76px 76px', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 18%, rgba(0,0,0,1) 82%, rgba(0,0,0,0) 100%)', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 18%, rgba(0,0,0,1) 82%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', top: '0', left: '-140px', width: '560px', height: '560px', borderRadius: '50%', pointerEvents: 'none', background: 'radial-gradient(circle, rgba(224,181,88,0.26), rgba(224,181,88,0) 66%)', animation: 'tglGlow 10s ease-in-out infinite', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', bottom: '0', right: '-160px', width: '660px', height: '660px', borderRadius: '50%', pointerEvents: 'none', background: 'radial-gradient(circle, rgba(107,62,150,0.15), rgba(107,62,150,0) 68%)', animation: 'tglGlow 13s ease-in-out infinite 2s', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', top: '42%', left: '46%', width: '420px', height: '420px', borderRadius: '50%', pointerEvents: 'none', background: 'radial-gradient(circle, rgba(255,243,206,0.6), rgba(255,243,206,0) 70%)', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div data-reveal="" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '64px', alignItems: 'start' }}>
          <div style={{ position: 'sticky', top: '108px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '20px' }}>
              <span style={{ width: '38px', height: '1px', background: 'linear-gradient(90deg, rgba(192,141,46,0), #C08D2E)', flexShrink: '0' }}></span>
              <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#C08D2E', fontWeight: '700' }}>
                Executive Overview
              </p>
            </div>
            <h2 style={{ fontSize: 'clamp(34px, 3.8vw, 52px)', lineHeight: '1.05', letterSpacing: '-0.02em', fontWeight: '800', margin: '0 0 18px', color: '#2B1740' }}>
              What Is TGL?
            </h2>
            <p style={{ fontFamily: '\'Bodoni Moda\', \'Cormorant Garamond\', Georgia, serif', fontStyle: 'italic', fontSize: 'clamp(28px, 2.6vw, 38px)', lineHeight: '1.2', letterSpacing: '-0.015em', color: '#6B3E96', margin: '0 0 34px' }}>
              Quality over popularity.
            </p>
            <div style={{ height: '1px', marginBottom: '26px', background: 'linear-gradient(90deg, rgba(192,141,46,0.55), rgba(192,141,46,0))' }}></div>
            <p style={{ margin: '0 0 20px', fontSize: '10.5px', letterSpacing: '.26em', textTransform: 'uppercase', fontWeight: '700', color: 'rgba(43,23,64,0.42)' }}>
              Season 1 at a glance
            </p>
            <div style={{ display: 'grid', gap: '2px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px', padding: '15px 2px', borderTop: '1px solid rgba(53,26,78,0.1)' }}>
                <span style={{ flexShrink: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '11px', color: '#C08D2E', letterSpacing: '.06em' }}>
                  01
                </span>
                <span style={{ flex: '1', fontSize: '14.5px', color: 'rgba(43,23,64,0.62)' }}>
                  Host city
                </span>
                <span style={{ fontSize: '15px', fontWeight: '700', color: '#2B1740', textAlign: 'right' }}>
                  Bengaluru
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px', padding: '15px 2px', borderTop: '1px solid rgba(53,26,78,0.1)' }}>
                <span style={{ flexShrink: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '11px', color: '#C08D2E', letterSpacing: '.06em' }}>
                  02
                </span>
                <span style={{ flex: '1', fontSize: '14.5px', color: 'rgba(43,23,64,0.62)' }}>
                  Business categories
                </span>
                <span style={{ fontSize: '15px', fontWeight: '700', color: '#2B1740', textAlign: 'right' }}>
                  Ten
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px', padding: '15px 2px', borderTop: '1px solid rgba(53,26,78,0.1)' }}>
                <span style={{ flexShrink: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '11px', color: '#C08D2E', letterSpacing: '.06em' }}>
                  03
                </span>
                <span style={{ flex: '1', fontSize: '14.5px', color: 'rgba(43,23,64,0.62)' }}>
                  Judged on
                </span>
                <span style={{ fontSize: '15px', fontWeight: '700', color: '#2B1740', textAlign: 'right' }}>
                  Business potential
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px', padding: '15px 2px', borderTop: '1px solid rgba(53,26,78,0.1)', borderBottom: '1px solid rgba(53,26,78,0.1)' }}>
                <span style={{ flexShrink: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '11px', color: '#C08D2E', letterSpacing: '.06em' }}>
                  04
                </span>
                <span style={{ flex: '1', fontSize: '14.5px', color: 'rgba(43,23,64,0.62)' }}>
                  Grand finale
                </span>
                <span style={{ fontSize: '15px', fontWeight: '700', color: '#2B1740', textAlign: 'right' }}>
                  5 December 2026
                </span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '30px' }}>
              <img src={logo} alt="TGL" style={{ width: '40px', height: '40px', objectFit: 'contain', flexShrink: '0', opacity: '.9' }} />
              <p style={{ margin: '0', fontSize: '12px', lineHeight: '1.5', letterSpacing: '.12em', textTransform: 'uppercase', fontWeight: '600', color: 'rgba(43,23,64,0.5)' }}>
                Powered by
                <br />
                SkyKeen Events
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
            <p style={{ margin: '0 0 6px', fontSize: '19px', lineHeight: '1.68', color: 'rgba(43,23,64,0.82)' }}>
              The Growth League (TGL) is a structured business platform designed for emerging and growing businesses. Season 1 brings together visibility, structured evaluation, recognition, networking and growth into a single season-long journey, powered by SkyKeen Events.
            </p>
            <div style={{ position: 'relative', overflow: 'hidden', padding: '34px 34px 32px', background: 'linear-gradient(150deg, rgba(255,252,245,0.92), rgba(246,238,223,0.72))', border: '1px solid rgba(192,141,46,0.28)', borderRadius: '22px', boxShadow: '0 20px 46px -28px rgba(53,26,78,0.28)', transition: 'transform .3s cubic-bezier(.2,.7,.3,1), box-shadow .3s ease, border-color .3s ease' }} className="hv-16">
              <div style={{ position: 'absolute', top: '0', left: '34px', right: '34px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), #E0B558, rgba(224,181,88,0))' }}></div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '18px' }}>
                <span style={{ flexShrink: '0', width: '48px', height: '48px', borderRadius: '15px', background: 'rgba(192,141,46,0.12)', color: '#A8762F', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                    <use href="#i-clipboard"></use>
                  </svg>
                </span>
                <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.24em', textTransform: 'uppercase', color: '#6B3E96', fontWeight: '700' }}>
                  Why TGL exists
                </p>
              </div>
              <p style={{ margin: '0', fontSize: '16.5px', lineHeight: '1.72', color: 'rgba(43,23,64,0.8)' }}>
                Most business events measure popularity. TGL is built on a different premise — quality over popularity — evaluating businesses on clarity, growth trajectory, innovation and scalability rather than reach alone.
              </p>
            </div>
            <div style={{ position: 'relative', overflow: 'hidden', padding: '34px 34px 32px', background: 'linear-gradient(150deg, rgba(255,252,245,0.92), rgba(240,232,246,0.6))', border: '1px solid rgba(107,62,150,0.2)', borderRadius: '22px', boxShadow: '0 20px 46px -28px rgba(53,26,78,0.28)', transition: 'transform .3s cubic-bezier(.2,.7,.3,1), box-shadow .3s ease, border-color .3s ease' }} className="hv-17">
              <div style={{ position: 'absolute', top: '0', left: '34px', right: '34px', height: '1px', background: 'linear-gradient(90deg, rgba(107,62,150,0), #6B3E96, rgba(107,62,150,0))' }}></div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '18px' }}>
                <span style={{ flexShrink: '0', width: '48px', height: '48px', borderRadius: '15px', background: 'rgba(107,62,150,0.1)', color: '#6B3E96', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                    <use href="#i-store"></use>
                  </svg>
                </span>
                <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.24em', textTransform: 'uppercase', color: '#6B3E96', fontWeight: '700' }}>
                  Who it is designed for
                </p>
              </div>
              <p style={{ margin: '0', fontSize: '16.5px', lineHeight: '1.72', color: 'rgba(43,23,64,0.8)' }}>
                TGL Season 1 is designed for small businesses with ten or fewer employees, operating for at least six months, based in or around Bengaluru. It is built for founders seeking structured evaluation, professional content and exposure to a wider business community.
              </p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '14px', marginTop: '8px' }}>
              <div style={{ padding: '22px 22px 20px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: '18px', background: 'rgba(255,252,245,0.6)' }}>
                <p style={{ margin: '0 0 8px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '30px', fontWeight: '800', letterSpacing: '-0.02em', color: '#2B1740', lineHeight: '1' }}>
                  ≤ 10
                </p>
                <p style={{ margin: '0', fontSize: '12.5px', lineHeight: '1.5', letterSpacing: '.04em', color: 'rgba(43,23,64,0.6)' }}>
                  Employees to qualify
                </p>
              </div>
              <div style={{ padding: '22px 22px 20px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: '18px', background: 'rgba(255,252,245,0.6)' }}>
                <p style={{ margin: '0 0 8px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '30px', fontWeight: '800', letterSpacing: '-0.02em', color: '#2B1740', lineHeight: '1' }}>
                  6 mo
                </p>
                <p style={{ margin: '0', fontSize: '12.5px', lineHeight: '1.5', letterSpacing: '.04em', color: 'rgba(43,23,64,0.6)' }}>
                  Minimum in operation
                </p>
              </div>
              <div style={{ padding: '22px 22px 20px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: '18px', background: 'rgba(255,252,245,0.6)' }}>
                <p style={{ margin: '0 0 8px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '30px', fontWeight: '800', letterSpacing: '-0.02em', color: '#2B1740', lineHeight: '1' }}>
                  10
                </p>
                <p style={{ margin: '0', fontSize: '12.5px', lineHeight: '1.5', letterSpacing: '.04em', color: 'rgba(43,23,64,0.6)' }}>
                  Categories in Season 1
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
