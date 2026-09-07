/* The six cards were previously a near-transparent cream wash (10% white) over
   the purple field, which just read as slightly-lighter purple — cards and
   background blurred into one another. They are now deep warm-onyx panels:
   dark and warm enough to sit clearly apart from the purple, with a gold
   hairline, a gold top accent and a deep shadow so they read as raised,
   premium surfaces rather than tinted rectangles. */
const OUTCOMES = [
  { icon: 'i-store', title: 'Showcase', body: 'Present your business and story.' },
  { icon: 'i-eye', title: 'Visibility', body: 'Gain opportunities for meaningful brand exposure.' },
  { icon: 'i-medal', title: 'Recognition', body: 'Build credibility and recognition.' },
  { icon: 'i-network', title: 'Networking', body: 'Connect with the wider business community.' },
  { icon: 'i-megaphone', title: 'Promotion', body: 'Gain professional digital content and promotional exposure.' },
  { icon: 'i-chart', title: 'Growth', body: 'Work toward stronger market positioning and growth opportunities.' },
];

const CARD_STYLE = {
  position: 'relative',
  overflow: 'hidden',
  background: 'linear-gradient(158deg, #2C2132 0%, #1F1726 54%, #171018 100%)',
  border: '1px solid rgba(224,181,88,0.3)',
  borderRadius: '22px',
  padding: '34px 32px 32px',
  boxShadow: '0 30px 60px -32px rgba(0,0,0,0.95), inset 0 1px 0 rgba(255,243,206,0.12)',
  transition: 'transform .3s cubic-bezier(.2,.7,.3,1), background .3s ease, border-color .3s ease, box-shadow .3s ease',
};

export default function WhyTGL() {
  return (
    <section id="why" style={{ position: 'relative', overflow: 'hidden', padding: '108px 28px 116px', background: 'linear-gradient(168deg, #4A2568 0%, #35194E 26%, #261139 58%, #1A0B2B 86%, #150822 100%)', color: '#F6EEDF' }}>
      <span aria-hidden="true" style={{ position: 'absolute', top: '0', left: '0', right: '0', height: '150px', pointerEvents: 'none', background: 'linear-gradient(180deg, rgba(246,238,223,0.1), rgba(246,238,223,0))' }}></span>
      <span aria-hidden="true" style={{ position: 'absolute', bottom: '0', left: '0', right: '0', height: '150px', pointerEvents: 'none', background: 'linear-gradient(0deg, rgba(246,238,223,0.06), rgba(246,238,223,0))' }}></span>
      <div style={{ position: 'absolute', left: '0', right: '0', top: '0', height: '1px', pointerEvents: 'none', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.55) 50%, rgba(224,181,88,0))' }}></div>
      <div style={{ position: 'absolute', top: '0', right: '-140px', width: '640px', height: '640px', borderRadius: '50%', pointerEvents: 'none', background: 'radial-gradient(circle, rgba(224,181,88,0.2), rgba(224,181,88,0) 66%)', animation: 'tglGlow 12s ease-in-out infinite', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', bottom: '0', left: '-180px', width: '620px', height: '620px', borderRadius: '50%', pointerEvents: 'none', background: 'radial-gradient(circle, rgba(126,74,176,0.32), rgba(126,74,176,0) 68%)', animation: 'tglGlow 15s ease-in-out infinite 2s', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div data-reveal="" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', justifyContent: 'space-between', gap: '34px', marginBottom: '58px' }}>
          <div style={{ maxWidth: '680px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
              <span style={{ width: '38px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), #E0B558)', flexShrink: '0' }}></span>
              <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: '700' }}>
                Why TGL
              </p>
            </div>
            <h2 style={{ fontSize: 'clamp(32px, 3.6vw, 48px)', lineHeight: '1.06', letterSpacing: '-0.02em', fontWeight: '800', margin: '0 0 4px', color: '#FFFBF3' }}>
              Why Should A Business
            </h2>
            <p style={{ margin: '0 0 22px', fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: 'clamp(42px, 5.4vw, 72px)', lineHeight: '1', letterSpacing: '-0.02em', background: 'linear-gradient(100deg, #A8762F 8%, #E0B558 26%, #FFF3CE 36%, #E0B558 46%, #A8762F 66%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 8s linear infinite' }}>
              Join?
            </p>
            <p style={{ margin: '0', fontSize: '16.5px', lineHeight: '1.72', maxWidth: '560px', color: 'rgba(246,238,223,0.7)' }}>
              Six outcomes a Season 1 participant works toward across the journey.
            </p>
          </div>
          <a href="#register" style={{ flexShrink: '0', display: 'inline-flex', alignItems: 'center', gap: '12px', padding: '15px 28px', borderRadius: '999px', border: '1px solid rgba(224,181,88,0.45)', background: 'rgba(224,181,88,0.08)', color: '#E0B558', fontSize: '12px', letterSpacing: '.14em', textTransform: 'uppercase', fontWeight: '700', transition: 'background .25s ease, border-color .25s ease, transform .25s ease, color .25s ease' }} className="hv-26">
            Register Now
            <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0' }}>
              <use href="#i-arrow"></use>
            </svg>
          </a>
        </div>
        <div data-reveal="" data-cards="" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: '20px' }}>
          {OUTCOMES.map((outcome, i) => (
            <div key={outcome.title} style={CARD_STYLE} className={`hv-${27 + i}`}>
              <span aria-hidden="true" style={{ position: 'absolute', top: '0', left: '28px', right: '28px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.75), rgba(224,181,88,0))' }}></span>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '26px', color: '#E0B558' }}>
                <span style={{ flexShrink: '0', width: '54px', height: '54px', borderRadius: '999px', border: '1px solid rgba(224,181,88,0.42)', background: 'radial-gradient(circle at 34% 26%, rgba(239,203,119,0.34), rgba(224,181,88,0.05))', boxShadow: 'inset 0 1px 0 rgba(255,243,206,0.32)', color: '#EFCB77', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="25" height="25" viewBox="0 0 24 24" aria-hidden="true">
                    <use href={`#${outcome.icon}`}></use>
                  </svg>
                </span>
                <span style={{ fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '12px', color: 'rgba(224,181,88,0.75)' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
              </div>
              <h3 style={{ margin: '0 0 10px', fontSize: '20px', fontWeight: '700', letterSpacing: '.04em', textTransform: 'uppercase', color: '#FFFBF3' }}>
                {outcome.title}
              </h3>
              <p style={{ margin: '0', fontSize: '15.5px', lineHeight: '1.65', color: 'rgba(246,238,223,0.72)' }}>
                {outcome.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
