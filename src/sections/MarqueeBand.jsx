import { SPONSORS } from '../data/sponsors';

/* Sponsor logo card for the marquee track.
 *
 * The cards are a fixed, uniform size so the band keeps an even rhythm as it
 * scrolls, while each logo is sized individually (sponsor.marqueeHeight) so
 * a wide wordmark and a square mark read at the same optical weight.
 *
 * The card background is pure white on purpose: two of the three logos have
 * an opaque white background baked into the artwork, so anything off-white
 * would show as a visible pale rectangle inside the card. Falls back to the
 * sponsor's name if the image fails to load, matching the Sponsors section. */
function MarqueeLogo({ sponsor }) {
  const showFallback = (ev) => {
    ev.currentTarget.style.display = 'none';
    const fallback = ev.currentTarget.nextElementSibling;
    if (fallback) fallback.style.display = 'flex';
  };

  return (
    <div data-sponsor-card="" style={{ '--logo-h': sponsor.marqueeHeight, flexShrink: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '232px', height: '98px', padding: '10px 26px', background: '#FFFFFF', border: '1px solid rgba(224,181,88,0.35)', borderRadius: '18px', boxShadow: '0 18px 34px -18px rgba(12,4,24,0.75), inset 0 1px 0 rgba(255,255,255,0.9)' }}>
      <img
        src={sponsor.file}
        alt={sponsor.name}
        onError={showFallback}
        style={{ height: 'var(--logo-h)', width: 'auto', maxWidth: '100%', objectFit: 'contain', display: 'block' }}
      />
      <span style={{ display: 'none', alignItems: 'center', justifyContent: 'center', textAlign: 'center', fontSize: '14px', fontWeight: '700', lineHeight: '1.3', letterSpacing: '-0.005em', color: '#2B1740' }}>
        {sponsor.name}
      </span>
    </div>
  );
}

function LogoGroup({ ariaHidden }) {
  return (
    <div aria-hidden={ariaHidden || undefined} style={{ display: 'flex', alignItems: 'center', gap: '26px', paddingRight: '26px', whiteSpace: 'nowrap' }}>
      {SPONSORS.map((sponsor) => (
        <MarqueeLogo key={sponsor.name} sponsor={sponsor} />
      ))}
    </div>
  );
}

export default function MarqueeBand() {
  return (
    <div data-marquee="" style={{ background: 'linear-gradient(180deg, #3B1D55 0%, #2E1544 55%, #22103A 100%)', color: '#F6EEDF', overflow: 'hidden', position: 'relative', borderTop: '1px solid rgba(224,181,88,0.32)', borderBottom: '1px solid rgba(224,181,88,0.32)' }}>
      <div style={{ position: 'absolute', inset: '0', pointerEvents: 'none', background: 'radial-gradient(ellipse 60% 160% at 50% 50%, rgba(224,181,88,0.13), rgba(224,181,88,0) 70%)', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', left: '0', right: '0', top: '0', height: '1px', pointerEvents: 'none', background: 'linear-gradient(90deg, rgba(224,181,88,0), #E0B558 50%, rgba(224,181,88,0))' }}></div>
      <div style={{ position: 'absolute', inset: '0', zIndex: '3', pointerEvents: 'none', background: 'linear-gradient(90deg, #2E1544, rgba(46,21,68,0) 12%, rgba(46,21,68,0) 88%, #2E1544)' }}></div>
      <div style={{ position: 'relative', zIndex: '2', padding: '30px 0 26px' }}>
        {/* Slower than the text row below: the logo cards are much wider than
            the words, so a matching duration would read as a rush past. */}
        <div data-marquee-track="" style={{ display: 'flex', width: 'max-content', animation: 'tglMarquee 52s linear infinite' }}>
          <LogoGroup />
          <LogoGroup ariaHidden="true" />
        </div>
        <div style={{ height: '1px', margin: '28px 0 22px', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.28) 20%, rgba(224,181,88,0.28) 80%, rgba(224,181,88,0))' }}></div>
        <div data-marquee-track="" style={{ display: 'flex', width: 'max-content', animation: 'tglMarqueeRev 46s linear infinite' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '46px', paddingRight: '46px', whiteSpace: 'nowrap' }}>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Visibility
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Evaluation
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: '27px', letterSpacing: '-0.01em', color: '#E0B558' }}>
              Quality over popularity
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Recognition
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Networking
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Growth
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
          </div>
          <div aria-hidden="true" style={{ display: 'flex', alignItems: 'baseline', gap: '46px', paddingRight: '46px', whiteSpace: 'nowrap' }}>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Visibility
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Evaluation
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: '27px', letterSpacing: '-0.01em', color: '#E0B558' }}>
              Quality over popularity
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Recognition
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Networking
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '21px', fontWeight: '800', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Growth
            </span>
            <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', alignSelf: 'center', flexShrink: '0' }}></span>
          </div>
        </div>
      </div>
    </div>
  );
}
