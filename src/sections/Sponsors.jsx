/* maxHeight is tuned per logo: the wordmark logos are wide banners, while the
   Saffron mark is square with generous internal padding, so it needs more
   height to read at a comparable size. */
const SPONSORS = [
  { name: 'Shami Equibooks', file: '/images/sponsor_shamiequibooks.png', maxHeight: '54px' },
  { name: 'Creme Bliss', file: '/images/sponsor_creme_bliss.jpeg', maxHeight: '120px' },
  { name: 'Saffron Technologies', file: '/images/sponsor_saffrontechnologies.png', maxHeight: '120px' },
];

const HOVER_CLASSES = ['hv-46', 'hv-47', 'hv-48'];

/* Each tile renders the official logo when the file is present in public/images/.
   Until then it falls back to a styled wordmark so the band stays presentable. */
function SponsorTile({ sponsor, hoverClass }) {
  const showFallback = (ev) => {
    ev.currentTarget.style.display = 'none';
    const fallback = ev.currentTarget.nextElementSibling;
    if (fallback) fallback.style.display = 'block';
  };

  return (
    <div
      style={{ flex: '1 1 220px', maxWidth: '300px', minWidth: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '148px', padding: '24px', background: '#FFFBF3', border: '1px solid rgba(53,26,78,0.1)', borderRadius: '20px', boxShadow: '0 18px 44px -32px rgba(53,26,78,0.45)', transition: 'transform .3s cubic-bezier(.2,.7,.3,1), box-shadow .3s ease, border-color .3s ease' }}
      className={hoverClass}
    >
      <img
        src={sponsor.file}
        alt={sponsor.name}
        onError={showFallback}
        style={{ maxWidth: '100%', maxHeight: sponsor.maxHeight || '64px', width: 'auto', height: 'auto', objectFit: 'contain', display: 'block' }}
      />
      <span style={{ display: 'none', textAlign: 'center', fontSize: '17px', fontWeight: '700', letterSpacing: '-0.01em', lineHeight: '1.35', color: '#2B1740', textWrap: 'pretty' }}>
        {sponsor.name}
      </span>
    </div>
  );
}

export default function Sponsors() {
  return (
    <section id="sponsors" style={{ position: 'relative', overflow: 'hidden', padding: '92px 28px 96px', background: 'transparent' }}>
      <div aria-hidden="true" style={{ position: 'absolute', top: '0', left: '50%', transform: 'translateX(-50%)', width: '820px', height: '420px', borderRadius: '50%', pointerEvents: 'none', background: 'radial-gradient(ellipse at 50% 0%, rgba(224,181,88,0.2), rgba(224,181,88,0) 68%)', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div data-reveal="" style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 46px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '14px', marginBottom: '18px' }}>
            <span aria-hidden="true" style={{ width: '42px', height: '1px', background: 'linear-gradient(90deg, rgba(192,141,46,0), #C08D2E)' }}></span>
            <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#C08D2E', fontWeight: '700' }}>
              Side Sponsors
            </p>
            <span aria-hidden="true" style={{ width: '42px', height: '1px', background: 'linear-gradient(90deg, #C08D2E, rgba(192,141,46,0))' }}></span>
          </div>
          <h2 style={{ fontSize: 'clamp(26px, 3vw, 38px)', lineHeight: '1.08', letterSpacing: '-0.018em', fontWeight: '800', margin: '0 0 4px', color: '#2B1740', textTransform: 'uppercase' }}>
            Season 1 Is Backed By
          </h2>
          <p style={{ margin: '0 0 18px', fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: 'clamp(38px, 4.6vw, 60px)', lineHeight: '1.05', letterSpacing: '-0.02em', background: 'linear-gradient(100deg, #A8762F 8%, #E0B558 26%, #FFF3CE 36%, #E0B558 46%, #A8762F 66%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 8s linear infinite' }}>
            Our Partners
          </p>
          <p style={{ margin: '0 auto', maxWidth: '560px', fontSize: '16.5px', lineHeight: '1.7', color: 'rgba(43,23,64,0.7)', textWrap: 'pretty' }}>
            Season 1 is supported by partners who share our belief in structured growth for emerging businesses.
          </p>
        </div>
        <div data-reveal="" data-cards-flex="" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'stretch', gap: '20px' }}>
          {SPONSORS.map((s, i) => (
            <SponsorTile key={s.name} sponsor={s} hoverClass={HOVER_CLASSES[i]} />
          ))}
        </div>
      </div>
    </section>
  );
}
