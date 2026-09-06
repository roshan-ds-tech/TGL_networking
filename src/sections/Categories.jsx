const CATEGORIES = [
  { code: '01', name: 'Fashion, Apparel & Textile Businesses' },
  { code: '02', name: 'Food, Bakery & Beverage Businesses' },
  { code: '03', name: 'Handmade, Craft & Artisan Businesses' },
  { code: '04', name: 'Jewellery & Accessories Businesses' },
  { code: '05', name: 'Home Decor, Lifestyle & Interior Businesses' },
  { code: '06', name: 'Kids Products, Toys & Parenting Brands' },
  { code: '07', name: 'Beauty, Personal Care & Wellness Businesses' },
  { code: '08', name: 'Fitness, Sports & Health Businesses' },
  { code: '09', name: 'Business, Professional & Digital Services' },
  { code: '10', name: 'Emerging, Innovative & Unique Businesses' },
];

const DEFAULT_CAPACITY = 40;

/* Slot counter shown at the end of each category row.
 *
 * Until the counts arrive (or if the request failed) this falls back to the
 * static "40 slots" label, so the section never renders a placeholder or a
 * misleading "0 filled". */
function SlotMeter({ filled, capacity }) {
  if (filled === null) {
    return (
      <span
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: '10.5px',
          letterSpacing: '.14em',
          textTransform: 'uppercase',
          color: 'rgba(43,23,64,0.4)',
          whiteSpace: 'nowrap',
        }}
      >
        {capacity} slots
      </span>
    );
  }

  const pct = Math.min(100, (filled / capacity) * 100);
  const isFull = filled >= capacity;
  const isTight = !isFull && pct >= 75;
  const accent = isFull ? '#8E3B3B' : isTight ? '#A8762F' : '#C08D2E';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: '7px',
        minWidth: '96px',
      }}
      aria-label={`${filled} of ${capacity} slots filled`}
    >
      <span
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: '11px',
          letterSpacing: '.1em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
          color: 'rgba(43,23,64,0.42)',
        }}
      >
        <strong style={{ fontSize: '13.5px', fontWeight: 700, color: accent }}>
          {isFull ? 'Full' : filled}
        </strong>
        {!isFull && <span> / {capacity} filled</span>}
      </span>
      <span
        aria-hidden="true"
        style={{
          width: '96px',
          height: '3px',
          borderRadius: '999px',
          background: 'rgba(43,23,64,0.1)',
          overflow: 'hidden',
        }}
      >
        <span
          style={{
            display: 'block',
            height: '100%',
            width: `${pct}%`,
            borderRadius: '999px',
            background: isFull
              ? 'linear-gradient(90deg, #A85252, #8E3B3B)'
              : 'linear-gradient(90deg, #E0B558, #C08D2E)',
            transition: 'width .8s cubic-bezier(.2,.7,.3,1)',
          }}
        />
      </span>
    </div>
  );
}

export default function Categories({ availability }) {
  const capacity = availability?.capacity_per_category ?? DEFAULT_CAPACITY;
  const byCode = new Map((availability?.categories ?? []).map((c) => [c.category, c]));

  return (
    <section id="categories" style={{ position: 'relative', overflow: 'hidden', padding: '104px 28px 96px', background: 'transparent' }}>
      <div aria-hidden="true" style={{ position: 'absolute', top: '0', right: '-120px', width: '520px', height: '520px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(192,141,46,0.14), rgba(192,141,46,0) 68%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div aria-hidden="true" style={{ position: 'absolute', bottom: '0', left: '-140px', width: '560px', height: '560px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(107,62,150,0.1), rgba(107,62,150,0) 70%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div data-reveal="" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', justifyContent: 'space-between', gap: '32px', marginBottom: '46px' }}>
          <div style={{ maxWidth: '640px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
              <span style={{ width: '38px', height: '1px', background: 'linear-gradient(90deg, rgba(192,141,46,0), #C08D2E)', flexShrink: '0' }}></span>
              <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#C08D2E', fontWeight: '700' }}>
                Categories
              </p>
            </div>
            <h2 style={{ fontSize: 'clamp(30px, 3.4vw, 44px)', lineHeight: '1.06', letterSpacing: '-0.02em', fontWeight: '800', margin: '0 0 2px', color: '#2B1740', textTransform: 'uppercase' }}>
              The 10
            </h2>
            <p style={{ margin: '0', fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: 'clamp(44px, 5.6vw, 76px)', lineHeight: '1', letterSpacing: '-0.02em', background: 'linear-gradient(100deg, #A8762F 8%, #E0B558 26%, #FFF3CE 36%, #E0B558 46%, #A8762F 66%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 8s linear infinite' }}>
              Categories
            </p>
          </div>
          <div data-stat-pills="" style={{ flexShrink: '0', maxWidth: '100%', display: 'flex', alignItems: 'stretch', gap: '0', border: '1px solid rgba(192,141,46,0.42)', borderRadius: '18px', background: 'rgba(246,238,223,0.55)', overflow: 'hidden' }}>
            <div style={{ padding: '18px 24px' }}>
              <p style={{ margin: '0 0 4px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '30px', fontWeight: '800', lineHeight: '1', letterSpacing: '-0.03em', color: '#2B1740' }}>
                {capacity}
              </p>
              <p style={{ margin: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '10px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.55)' }}>
                Slots / category
              </p>
            </div>
            <div style={{ width: '1px', background: 'rgba(192,141,46,0.4)' }}></div>
            <div style={{ padding: '18px 24px' }}>
              <p style={{ margin: '0 0 4px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '30px', fontWeight: '800', lineHeight: '1', letterSpacing: '-0.03em', color: '#6B3E96' }}>
                {availability?.total_capacity ?? capacity * CATEGORIES.length}
              </p>
              <p style={{ margin: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '10px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.55)' }}>
                Businesses total
              </p>
            </div>
            {availability && (
              <>
                <div style={{ width: '1px', background: 'rgba(192,141,46,0.4)' }}></div>
                <div style={{ padding: '18px 24px', background: 'rgba(224,181,88,0.14)' }}>
                  <p style={{ margin: '0 0 4px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '30px', fontWeight: '800', lineHeight: '1', letterSpacing: '-0.03em', color: '#C08D2E' }}>
                    {availability.total_filled}
                  </p>
                  <p style={{ margin: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '10px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.55)' }}>
                    Slots filled
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
        <div data-reveal="" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(400px, 100%), 1fr))', columnGap: '56px', rowGap: '0', borderBottom: '1px solid rgba(192,141,46,0.32)' }}>
          {CATEGORIES.map(({ code, name }, i) => (
            <div key={code} style={{ position: 'relative', display: 'grid', gridTemplateColumns: '68px minmax(0,1fr) auto', alignItems: 'center', gap: '18px', padding: '24px 20px 24px 14px', borderTop: '1px solid rgba(192,141,46,0.32)', borderRadius: '4px 14px 14px 4px', transition: 'background .3s ease, box-shadow .3s ease, transform .3s cubic-bezier(.2,.7,.3,1)' }} className={`hv-${36 + i}`}>
              <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '40px', fontWeight: '800', lineHeight: '1', letterSpacing: '-0.04em', color: 'transparent', WebkitTextStroke: '1.1px rgba(168,118,47,0.6)', fontVariantNumeric: 'tabular-nums' }}>
                {code}
              </span>
              <p style={{ margin: '0', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '17.5px', fontWeight: '600', lineHeight: '1.4', letterSpacing: '-0.005em', color: '#2B1740', textWrap: 'pretty' }}>
                {name}
              </p>
              <SlotMeter
                filled={byCode.has(code) ? byCode.get(code).filled : null}
                capacity={byCode.get(code)?.capacity ?? capacity}
              />
            </div>
          ))}
        </div>
        <div data-reveal="" style={{ marginTop: '44px', position: 'relative', overflow: 'hidden', borderRadius: '22px', background: 'linear-gradient(115deg, #2B1740 0%, #3A2059 52%, #4A2A6B 100%)', padding: '30px 32px', textAlign: 'center' }}>
          <div aria-hidden="true" style={{ position: 'absolute', inset: '0', background: 'radial-gradient(circle at 50% 0%, rgba(224,181,88,0.18), rgba(224,181,88,0) 62%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
          <div aria-hidden="true" style={{ position: 'absolute', top: '0', left: '0', right: '0', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.75), rgba(224,181,88,0))' }}></div>
          <div style={{ position: 'relative', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center', gap: '10px 16px' }}>
            <span style={{ fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '14px', fontWeight: '800', letterSpacing: '.16em', textTransform: 'uppercase', color: '#FFFBF3' }}>
              Every category. Equal spotlight.
            </span>
            <span style={{ width: '5px', height: '5px', background: '#E0B558', transform: 'rotate(45deg)', flexShrink: '0' }}></span>
            <span style={{ fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: '25px', lineHeight: '1.1', letterSpacing: '-0.01em', color: '#E0B558' }}>
              Every business, a chance to rise.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
