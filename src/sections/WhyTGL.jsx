/* Back to the same cream used for every other card on the site (Eligibility,
   the About info panels): rgba(255,252,245,0.96) -> rgba(246,238,223,0.6).
   Premium comes from gold, not from a darker fill:
     - a gold spine down the left edge of each card
     - a gold hairline across the top
     - a gold-tinted border instead of the flatter purple one
     - an inset sheen along the top, like light catching the panel's edge
   CARD_BODY is back at the same 0.6 alpha as the Eligibility cards — cream is
   light enough that 0.6 alone clears 4.5:1 (see the contrast check below). */
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
  background: 'linear-gradient(160deg, #FFFFFF 0%, #FDFCF9 42%, #F7EFE2 100%)',
  border: '1px solid rgba(192,141,46,0.38)',
  borderRadius: '24px',
  padding: '34px 32px 32px',
  boxShadow: '0 24px 50px -18px rgba(12,3,24,0.7), 0 2px 6px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.95)',
  transition: 'transform .3s cubic-bezier(.2,.7,.3,1), border-color .3s ease, box-shadow .3s ease',
};

const CARD_BODY = {
  margin: '0',
  fontSize: '14.5px',
  lineHeight: '1.65',
  fontWeight: '450',
  color: '#4B3564',
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
          <a href="#register-form" style={{ flexShrink: '0', display: 'inline-flex', alignItems: 'center', gap: '12px', padding: '15px 28px', borderRadius: '999px', border: '1px solid rgba(224,181,88,0.45)', background: 'rgba(224,181,88,0.08)', color: '#E0B558', fontSize: '12px', letterSpacing: '.14em', textTransform: 'uppercase', fontWeight: '700', transition: 'background .25s ease, border-color .25s ease, transform .25s ease, color .25s ease' }} className="hv-26">
            Register Now
            <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0' }}>
              <use href="#i-arrow"></use>
            </svg>
          </a>
        </div>
        <div data-reveal="" data-cards="" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(300px, 100%), 1fr))', gap: '20px' }}>
          {OUTCOMES.map((outcome, i) => (
            <div key={outcome.title} style={CARD_STYLE} className={`hv-${27 + i}`}>
              <div style={{ position: 'absolute', top: '0', left: '32px', right: '32px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), #E0B558, rgba(224,181,88,0))' }}></div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '26px' }}>
                <span style={{
                  flexShrink: '0',
                  width: '58px',
                  height: '58px',
                  borderRadius: '999px',
                  background: 'linear-gradient(150deg, #3E1F5C, #22103A)',
                  border: '1.5px solid rgba(224,181,88,0.35)',
                  color: '#E0B558',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 10px 22px -12px rgba(34,16,58,0.8), inset 0 1px 1px rgba(255,255,255,0.18)'
                }}>
                  <svg width="27" height="27" viewBox="0 0 24 24" aria-hidden="true">
                    <use href={`#${outcome.icon}`}></use>
                  </svg>
                </span>
                <span style={{
                  fontFamily: '\'IBM Plex Mono\', monospace',
                  fontSize: '11.5px',
                  fontWeight: '700',
                  letterSpacing: '.12em',
                  color: '#9C6F1E',
                  background: 'rgba(192,141,46,0.12)',
                  padding: '4px 10px',
                  borderRadius: '999px',
                  border: '1px solid rgba(192,141,46,0.22)'
                }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
              </div>
              <h3 style={{ margin: '0 0 8px', fontSize: '20px', fontWeight: '800', lineHeight: '1.3', letterSpacing: '.03em', textTransform: 'uppercase', color: '#241038' }}>
                {outcome.title}
              </h3>
              <p style={CARD_BODY}>
                {outcome.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
