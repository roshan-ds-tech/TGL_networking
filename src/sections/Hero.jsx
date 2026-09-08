export default function Hero({ tickerRef, daysLeftLabel, cdD, cdH, cdM, cdS }) {
  return (
    <section id="top" style={{ position: 'relative', overflow: 'hidden', background: 'transparent' }}>
      <div style={{ position: 'absolute', top: '0', right: '-140px', width: '640px', height: '640px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(224,181,88,0.3), rgba(224,181,88,0) 65%)', animation: 'tglGlow 9s ease-in-out infinite', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', bottom: '0', left: '-160px', width: '520px', height: '520px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(107,62,150,0.16), rgba(107,62,150,0) 68%)', animation: 'tglGlow 11s ease-in-out infinite 1.5s', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'absolute', inset: '-10% -30%', overflow: 'hidden', pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', top: '0', bottom: '0', width: '320px', background: 'linear-gradient(100deg, rgba(255,251,243,0) 0%, rgba(255,248,224,0.85) 45%, rgba(255,251,243,0) 100%)', filter: 'blur(28px)', animation: 'tglSweep 14s ease-in-out infinite 2s' }}></div>
      </div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto', padding: '96px 28px 104px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(340px, 100%), 1fr))', gap: '60px', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '30px', animation: 'tglRise .7s cubic-bezier(.2,.7,.3,1) both' }}>
            <span style={{ width: '46px', height: '1px', background: 'linear-gradient(90deg, rgba(192,141,46,0), #C08D2E)', flexShrink: '0' }}></span>
            <span style={{ width: '6px', height: '6px', background: '#C08D2E', transform: 'rotate(45deg)', display: 'block', flexShrink: '0', animation: 'tglGlow 2.6s ease-in-out infinite' }}></span>
            <span style={{ fontSize: '11.5px', letterSpacing: 'clamp(.12em, 1.4vw, .32em)', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96', lineHeight: '1.5', minWidth: '0' }}>
              Season 1 · Bengaluru
            </span>
          </div>
          <p style={{ margin: '0 0 14px', fontSize: '12px', letterSpacing: '.42em', textTransform: 'uppercase', fontWeight: '600', color: 'rgba(43,23,64,0.45)', animation: 'tglRise .7s cubic-bezier(.2,.7,.3,1) both .08s' }}>
            The Growth League
          </p>
          <h1 style={{ margin: '0 0 28px', animation: 'tglRise .85s cubic-bezier(.2,.7,.3,1) both .16s' }}>
            <span style={{ display: 'block', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: 'clamp(38px, 5vw, 70px)', lineHeight: '1', letterSpacing: '-0.035em', fontWeight: '800', textTransform: 'uppercase', color: '#2B1740' }}>
              Where Businesses
            </span>
            <span style={{ display: 'block', marginTop: '4px', fontFamily: "'Kaushan Script', cursive", fontWeight: '500', fontSize: 'clamp(62px, 9vw, 128px)', lineHeight: '0.94', letterSpacing: '-0.015em', background: 'linear-gradient(100deg, #A8762F 6%, #E0B558 24%, #FFF3CE 33%, #E0B558 42%, #A8762F 62%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 7s linear infinite' }}>
              Rise.
            </span>
          </h1>
          <p style={{ fontSize: 'clamp(17px, 1.5vw, 20px)', lineHeight: '1.6', maxWidth: '520px', margin: '0 0 14px', color: 'rgba(43,23,64,0.8)', animation: 'tglRise .8s cubic-bezier(.2,.7,.3,1) both .24s' }}>
            A platform for visibility. A stage for recognition. An ecosystem for growth.
          </p>
          <p style={{ fontSize: '16px', lineHeight: '1.7', maxWidth: '520px', margin: '0 0 26px', color: 'rgba(43,23,64,0.62)', animation: 'tglRise .8s cubic-bezier(.2,.7,.3,1) both .32s' }}>
            The Growth League (TGL) is a structured business platform designed for emerging and growing businesses. Season 1 brings visibility, structured evaluation, recognition, networking and growth into a single season-long journey.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', margin: '0 0 34px', padding: '14px 20px 14px 18px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: '999px', background: 'rgba(255,251,243,0.66)', maxWidth: '520px', animation: 'tglRise .8s cubic-bezier(.2,.7,.3,1) both .38s' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '9px', flexShrink: '0', fontSize: '10.5px', letterSpacing: '.22em', textTransform: 'uppercase', fontWeight: '700', color: '#C08D2E', whiteSpace: 'nowrap' }}>
              <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#C08D2E', animation: 'tglTick 1.6s ease-in-out infinite' }}></span>
              Now open
            </span>
            <span style={{ width: '1px', height: '20px', background: 'rgba(53,26,78,0.16)', flexShrink: '0' }}></span>
            <span ref={tickerRef} style={{ fontSize: '15px', fontWeight: '600', color: '#35194E', lineHeight: '1.35', transition: 'opacity .4s ease, transform .4s ease' }}>
              Fashion, Apparel & Textile
            </span>
          </div>
          <div data-cta-row="" style={{ display: 'flex', flexWrap: 'wrap', gap: '14px', marginBottom: '38px', animation: 'tglRise .8s cubic-bezier(.2,.7,.3,1) both .44s' }}>
            <a href="#register" style={{ background: 'linear-gradient(135deg, #E0B558, #C08D2E)', color: '#22103A', fontWeight: '700', fontSize: '14px', letterSpacing: '.08em', textTransform: 'uppercase', padding: '18px clamp(20px, 5vw, 36px)', borderRadius: '999px', boxShadow: '0 10px 26px rgba(192,141,46,0.35)', transition: 'transform .2s ease, box-shadow .2s ease', display: 'inline-flex', alignItems: 'center', gap: '12px', whiteSpace: 'nowrap' }} className="hv-14">
              Register for Season 1
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0' }}>
                <use href="#i-arrow"></use>
              </svg>
            </a>
            <a href="#about" style={{ border: '1px solid rgba(53,26,78,0.3)', color: '#35194E', fontWeight: '600', fontSize: '14px', letterSpacing: '.08em', textTransform: 'uppercase', padding: '18px clamp(20px, 5vw, 36px)', borderRadius: '999px', display: 'inline-flex', alignItems: 'center', whiteSpace: 'nowrap', transition: 'background .2s ease, border-color .2s ease' }} className="hv-15">
              Learn More
            </a>
          </div>
          <div
            data-hero-meta=""
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              flexWrap: 'nowrap',
              gap: 'clamp(14px, 2.4vw, 32px)',
              paddingTop: '26px',
              borderTop: '1px solid rgba(53,26,78,0.14)',
              animation: 'tglRise .8s cubic-bezier(.2,.7,.3,1) both .48s',
            }}
          >
            <div style={{ flex: '0 0 auto' }}>
              <p style={{ margin: '0 0 4px', fontSize: '11px', letterSpacing: '.22em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)', fontWeight: '600', whiteSpace: 'nowrap' }}>
                Grand Finale
              </p>
              <p style={{ margin: '0', fontSize: '18px', fontWeight: '700', color: '#2B1740', whiteSpace: 'nowrap' }}>
                5 December 2026
              </p>
              <p style={{ margin: '2px 0 0', fontSize: '13px', color: 'rgba(43,23,64,0.6)', whiteSpace: 'nowrap' }}>
                On-site award show
              </p>
            </div>
            <div style={{ flex: '0 0 auto' }}>
              <p style={{ margin: '0 0 4px', fontSize: '11px', letterSpacing: '.22em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)', fontWeight: '600', whiteSpace: 'nowrap' }}>
                Registration closes
              </p>
              <p style={{ margin: '0', fontSize: '18px', fontWeight: '700', color: '#2B1740', whiteSpace: 'nowrap' }}>
                20 November 2026
              </p>
              <p style={{ margin: '2px 0 0', fontSize: '13px', color: 'rgba(43,23,64,0.6)', whiteSpace: 'nowrap' }}>
                {daysLeftLabel}
              </p>
            </div>
            <div style={{ flex: '0 0 auto' }}>
              <p style={{ margin: '0 0 4px', fontSize: '11px', letterSpacing: '.22em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)', fontWeight: '600', whiteSpace: 'nowrap' }}>
                Location
              </p>
              <p style={{ margin: '0', fontSize: '18px', fontWeight: '700', color: '#2B1740', whiteSpace: 'nowrap' }}>
                Bengaluru
              </p>
              <p style={{ margin: '2px 0 0', fontSize: '12.5px', color: 'rgba(43,23,64,0.6)', whiteSpace: 'nowrap' }}>
                [VENUE TO BE CONFIRMED]
              </p>
            </div>
          </div>
        </div>
        <div style={{ position: 'relative', animation: 'tglRise .9s cubic-bezier(.2,.7,.3,1) both .34s' }}>
          <div style={{ position: 'absolute', inset: '14px -14px -14px 14px', border: '1px solid rgba(192,141,46,0.6)', borderRadius: '20px' }}></div>
          <div data-wide-pad="" style={{ position: 'relative', background: 'linear-gradient(165deg, #35194E, #22103A)', borderRadius: '20px', padding: '40px 38px', boxShadow: '0 30px 60px rgba(34,16,58,0.28)' }}>
            <div style={{ margin: '0 0 30px', paddingBottom: '28px', borderBottom: '1px solid rgba(224,181,88,0.24)' }}>
              <p style={{ margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: '10px', fontSize: '10.5px', letterSpacing: '.26em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.6)', fontWeight: '600' }}>
                <span style={{ color: '#E0B558', display: 'flex' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0' }}>
                    <use href="#i-clock"></use>
                  </svg>
                </span>
                Registration closes in
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
                <div style={{ textAlign: 'center', background: 'rgba(255,251,243,0.06)', border: '1px solid rgba(224,181,88,0.2)', borderRadius: '14px', padding: '14px 4px 12px' }}>
                  <span ref={cdD} style={{ display: 'block', fontSize: '26px', fontWeight: '800', lineHeight: '1', color: '#FFFBF3', fontVariantNumeric: 'tabular-nums' }}>
                    00
                  </span>
                  <span style={{ display: 'block', marginTop: '7px', fontSize: '9px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.5)', fontWeight: '700' }}>
                    Days
                  </span>
                </div>
                <div style={{ textAlign: 'center', background: 'rgba(255,251,243,0.06)', border: '1px solid rgba(224,181,88,0.2)', borderRadius: '14px', padding: '14px 4px 12px' }}>
                  <span ref={cdH} style={{ display: 'block', fontSize: '26px', fontWeight: '800', lineHeight: '1', color: '#FFFBF3', fontVariantNumeric: 'tabular-nums' }}>
                    00
                  </span>
                  <span style={{ display: 'block', marginTop: '7px', fontSize: '9px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.5)', fontWeight: '700' }}>
                    Hrs
                  </span>
                </div>
                <div style={{ textAlign: 'center', background: 'rgba(255,251,243,0.06)', border: '1px solid rgba(224,181,88,0.2)', borderRadius: '14px', padding: '14px 4px 12px' }}>
                  <span ref={cdM} style={{ display: 'block', fontSize: '26px', fontWeight: '800', lineHeight: '1', color: '#FFFBF3', fontVariantNumeric: 'tabular-nums' }}>
                    00
                  </span>
                  <span style={{ display: 'block', marginTop: '7px', fontSize: '9px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.5)', fontWeight: '700' }}>
                    Min
                  </span>
                </div>
                <div style={{ textAlign: 'center', background: 'rgba(224,181,88,0.14)', border: '1px solid rgba(224,181,88,0.4)', borderRadius: '14px', padding: '14px 4px 12px' }}>
                  <span ref={cdS} style={{ display: 'block', fontSize: '26px', fontWeight: '800', lineHeight: '1', color: '#EFCB77', fontVariantNumeric: 'tabular-nums' }}>
                    00
                  </span>
                  <span style={{ display: 'block', marginTop: '7px', fontSize: '9px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(239,203,119,0.7)', fontWeight: '700' }}>
                    Sec
                  </span>
                </div>
              </div>
            </div>
            <p style={{ margin: '0 0 26px', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: '600' }}>
              Season 1, by the numbers
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px', paddingBottom: '22px', borderBottom: '1px dashed rgba(224,181,88,0.35)' }}>
                <span data-count="10" style={{ fontSize: '52px', fontWeight: '800', lineHeight: '1', color: '#EFCB77', minWidth: 'clamp(62px, 17vw, 108px)', fontVariantNumeric: 'tabular-nums' }}>
                  10
                </span>
                <span style={{ fontSize: '13px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,251,243,0.82)', fontWeight: '600' }}>
                  Categories
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px', paddingBottom: '22px', borderBottom: '1px dashed rgba(224,181,88,0.35)' }}>
                <span data-count="40" style={{ fontSize: '52px', fontWeight: '800', lineHeight: '1', color: '#EFCB77', minWidth: 'clamp(62px, 17vw, 108px)', fontVariantNumeric: 'tabular-nums' }}>
                  40
                </span>
                <span style={{ fontSize: '13px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,251,243,0.82)', fontWeight: '600' }}>
                  Slots per category
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '18px' }}>
                <span data-count="400" style={{ fontSize: '52px', fontWeight: '800', lineHeight: '1', color: '#EFCB77', minWidth: 'clamp(62px, 17vw, 108px)', fontVariantNumeric: 'tabular-nums' }}>
                  400
                </span>
                <span style={{ fontSize: '13px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,251,243,0.82)', fontWeight: '600' }}>
                  Businesses total
                </span>
              </div>
            </div>
            <div style={{ marginTop: '32px', padding: '20px 22px', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
              <div>
                <p style={{ margin: '0 0 6px', fontSize: '10.5px', letterSpacing: '.2em', lineHeight: '1.5', textTransform: 'uppercase', color: 'rgba(34,16,58,0.75)', fontWeight: '700' }}>
                  Early / launch price
                </p>
                <p style={{ margin: '0', fontSize: '34px', fontWeight: '800', color: '#22103A', lineHeight: '1' }}>
                  ₹2,499
                </p>
              </div>
              <p style={{ margin: '0', fontSize: '12px', textAlign: 'right', color: 'rgba(34,16,58,0.78)', fontWeight: '600', lineHeight: '1.5' }}>
                Standard price
                <br />
                ₹2,999
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
