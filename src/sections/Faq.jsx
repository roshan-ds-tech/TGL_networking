import faqItems from '../data/faq';

const HOVER_CLASSES = ['hv-78', 'hv-79', 'hv-80', 'hv-81', 'hv-82', 'hv-83'];

export default function Faq({ faq, toggleFaq }) {
  return (
    <section id="faq" style={{ position: 'relative', overflow: 'hidden', padding: '104px 28px 100px', background: 'transparent' }}>
      <div aria-hidden="true" style={{ position: 'absolute', top: '40px', left: '-160px', width: '520px', height: '520px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(107,62,150,0.1), rgba(107,62,150,0) 70%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div aria-hidden="true" style={{ position: 'absolute', bottom: '0', right: '-140px', width: '540px', height: '540px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(192,141,46,0.13), rgba(192,141,46,0) 68%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '48px', alignItems: 'start' }}>
        <div data-reveal="" style={{ position: 'sticky', top: '108px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
            <span style={{ width: '38px', height: '1px', background: 'linear-gradient(90deg, rgba(192,141,46,0), #C08D2E)', flexShrink: '0' }}></span>
            <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#C08D2E', fontWeight: '700' }}>
              FAQ
            </p>
          </div>
          <h2 style={{ fontSize: 'clamp(26px, 2.8vw, 36px)', lineHeight: '1.08', letterSpacing: '-0.018em', fontWeight: '800', margin: '0 0 2px', color: '#2B1740', textTransform: 'uppercase' }}>
            Questions About
          </h2>
          <p style={{ margin: '0 0 26px', fontFamily: "'Bodoni Moda', 'Cormorant Garamond', Georgia, serif", fontStyle: 'italic', fontWeight: '500', fontSize: 'clamp(44px, 5.4vw, 74px)', lineHeight: '1', letterSpacing: '-0.02em', background: 'linear-gradient(100deg, #A8762F 8%, #E0B558 26%, #FFF3CE 36%, #E0B558 46%, #A8762F 66%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 8s linear infinite' }}>
            Season 1
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '18px 22px', border: '1px solid rgba(192,141,46,0.36)', borderRadius: '18px', background: 'rgba(246,238,223,0.6)', maxWidth: '340px' }}>
            <span style={{ flexShrink: '0', width: '40px', height: '40px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(150deg, #FFF6E2, #EBD9B4)', border: '1px solid rgba(192,141,46,0.5)', color: '#8A5F22' }}>
              <svg width="19" height="19" viewBox="0 0 24 24" aria-hidden="true">
                <use href="#i-mail"></use>
              </svg>
            </span>
            <div>
              <p style={{ margin: '0 0 3px', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)' }}>
                Something else?
              </p>
              <a href="#contact" style={{ fontSize: '14.5px', fontWeight: '700', color: '#6B3E96', textDecoration: 'none' }} className="hv-77">
                Reach the TGL team →
              </a>
            </div>
          </div>
        </div>
        <div data-reveal="" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {faqItems.map((item, i) => {
            const n = i + 1;
            const open = !!faq[n];
            return (
              <div key={n} style={{ position: 'relative', overflow: 'hidden', border: '1px solid rgba(192,141,46,0.32)', borderRadius: '20px', background: 'linear-gradient(158deg, rgba(246,238,223,0.7) 0%, rgba(255,252,245,0.55) 100%)', transition: 'border-color .28s ease, box-shadow .28s ease' }} className={HOVER_CLASSES[i]}>
                <button type="button" onClick={() => toggleFaq(n)} aria-expanded={open} style={{ width: '100%', background: 'none', border: 'none', textAlign: 'left', display: 'flex', alignItems: 'center', gap: '18px', padding: '24px 26px', cursor: 'pointer', minHeight: '68px' }}>
                  <span aria-hidden="true" style={{ flexShrink: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '10.5px', letterSpacing: '.16em', color: '#C08D2E' }}>
                    {'Q.0' + n}
                  </span>
                  <span style={{ flex: '1', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '18px', fontWeight: '700', letterSpacing: '-0.012em', lineHeight: '1.35', color: '#2B1740', textWrap: 'pretty' }}>
                    {item.q}
                  </span>
                  <span style={{ flexShrink: '0', width: '38px', height: '38px', borderRadius: '50%', border: '1px solid rgba(192,141,46,0.5)', background: 'rgba(255,252,245,0.7)', color: '#A8762F', fontSize: '18px', lineHeight: '1', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background .25s ease, border-color .25s ease, color .25s ease' }}>
                    {open ? '−' : '+'}
                  </span>
                </button>
                {open && (
                  <div style={{ padding: '0 26px 26px 74px' }}>
                    <div aria-hidden="true" style={{ height: '1px', marginBottom: '18px', background: 'linear-gradient(90deg, rgba(192,141,46,0.6), rgba(192,141,46,0))' }}></div>
                    <p style={item.mono
                      ? { margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', lineHeight: '1.78', color: 'rgba(43,23,64,0.6)' }
                      : { margin: '0', fontSize: '16px', lineHeight: '1.78', color: 'rgba(43,23,64,0.72)' }}>
                      {item.a}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
