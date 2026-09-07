import { SPONSORS } from '../data/sponsors';

/* Sponsor logo pill for the marquee track. Logos are designed for a light
   background (see Sponsors.jsx), so each one sits in its own light chip
   rather than directly on the dark band. Falls back to the sponsor's name if
   the image fails to load, matching the same resilience as the Sponsors
   section tiles. */
function MarqueeLogo({ sponsor }) {
  const showFallback = (ev) => {
    ev.currentTarget.style.display = 'none';
    const fallback = ev.currentTarget.nextElementSibling;
    if (fallback) fallback.style.display = 'block';
  };

  return (
    <div style={{ flexShrink: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '148px', height: '56px', padding: '10px 26px', background: 'rgba(255,251,243,0.96)', border: '1px solid rgba(224,181,88,0.3)', borderRadius: '14px', boxShadow: '0 10px 26px -14px rgba(0,0,0,0.5)' }}>
      <img
        src={sponsor.file}
        alt={sponsor.name}
        onError={showFallback}
        style={{ maxWidth: '150px', maxHeight: '30px', width: 'auto', height: 'auto', objectFit: 'contain', display: 'block' }}
      />
      <span style={{ display: 'none', fontSize: '13px', fontWeight: '700', letterSpacing: '-0.005em', color: '#2B1740', whiteSpace: 'nowrap' }}>
        {sponsor.name}
      </span>
    </div>
  );
}

function LogoGroup({ ariaHidden }) {
  return (
    <div aria-hidden={ariaHidden || undefined} style={{ display: 'flex', alignItems: 'center', gap: '28px', paddingRight: '28px', whiteSpace: 'nowrap' }}>
      {SPONSORS.map((sponsor) => (
        <div key={sponsor.name} style={{ display: 'flex', alignItems: 'center', gap: '28px' }}>
          <MarqueeLogo sponsor={sponsor} />
          <span style={{ width: '5px', height: '5px', background: '#C08D2E', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
        </div>
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
      <div style={{ position: 'relative', zIndex: '2', padding: '26px 0 24px' }}>
        <div data-marquee-track="" style={{ display: 'flex', width: 'max-content', animation: 'tglMarquee 38s linear infinite' }}>
          <LogoGroup />
          <LogoGroup ariaHidden="true" />
        </div>
        <div style={{ height: '1px', margin: '18px 0', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.28) 20%, rgba(224,181,88,0.28) 80%, rgba(224,181,88,0))' }}></div>
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
