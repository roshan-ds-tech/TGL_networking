const PHASES = [
  {
    label: 'Phase I — Entry & Submission',
    steps: [
      { title: 'Registration', icon: 'i-clipboard' },
      { title: 'Business Profile / Submission', icon: 'i-doc' },
    ],
  },
  {
    label: 'Phase II — Production & Promotion',
    steps: [
      { title: 'Shoot Guide / Raw Footage', icon: 'i-camera' },
      { title: 'Professional Video Production', icon: 'i-video' },
      { title: 'Digital Promotion', icon: 'i-broadcast' },
    ],
  },
  {
    label: 'Phase III — Evaluation & Finale',
    steps: [
      { title: 'Evaluation', icon: 'i-target' },
      { title: 'Selection', icon: 'i-check' },
      { title: 'Public Engagement / Voting', icon: 'i-vote' },
      { title: 'Grand Finale', icon: 'i-trophy', highlight: true },
      { title: 'Post-Event Exposure', icon: 'i-eye' },
    ],
  },
];

const HOVER_CLASSES = ['hv-56', 'hv-57', 'hv-58', 'hv-59', 'hv-60', 'hv-61', 'hv-62', 'hv-63', 'hv-64', 'hv-65'];

const TOTAL_STEPS = PHASES.reduce((n, p) => n + p.steps.length, 0);

export default function Journey() {
  let stepNo = 0;

  return (
    <section id="journey" style={{ position: 'relative', overflow: 'hidden', padding: '104px 28px 100px', background: 'linear-gradient(175deg, #22103A, #35194E)', color: '#F6EEDF' }}>
      <span aria-hidden="true" style={{ position: 'absolute', top: '0', left: '0', right: '0', height: '150px', pointerEvents: 'none', background: 'linear-gradient(180deg, rgba(246,238,223,0.1), rgba(246,238,223,0))' }}></span>
      <span aria-hidden="true" style={{ position: 'absolute', bottom: '0', left: '0', right: '0', height: '150px', pointerEvents: 'none', background: 'linear-gradient(0deg, rgba(246,238,223,0.1), rgba(246,238,223,0))' }}></span>
      <div aria-hidden="true" style={{ position: 'absolute', top: '0', right: '-140px', width: '620px', height: '620px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(224,181,88,0.16), rgba(224,181,88,0) 66%)', pointerEvents: 'none', animation: 'tglDrift 15s ease-in-out infinite', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div aria-hidden="true" style={{ position: 'absolute', bottom: '0', left: '-160px', width: '560px', height: '560px', borderRadius: '50%', background: 'radial-gradient(circle, rgba(107,62,150,0.4), rgba(107,62,150,0) 70%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div data-reveal="" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', justifyContent: 'space-between', gap: '30px', marginBottom: '56px' }}>
          <div style={{ maxWidth: '680px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
              <span style={{ width: '38px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), #E0B558)', flexShrink: '0' }}></span>
              <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: '700' }}>
                Participant Journey
              </p>
            </div>
            <h2 style={{ fontSize: 'clamp(26px, 3vw, 38px)', lineHeight: '1.08', letterSpacing: '-0.018em', fontWeight: '800', margin: '0 0 2px', color: '#FFFBF3', textTransform: 'uppercase' }}>
              The TGL Participant
            </h2>
            <p style={{ margin: '0', fontFamily: '\'Kaushan Script\', cursive', fontWeight: '500', fontSize: 'clamp(48px, 6.4vw, 88px)', lineHeight: '1', letterSpacing: '-0.02em', background: 'linear-gradient(100deg, #A8762F 6%, #E0B558 24%, #FFF9E8 36%, #E0B558 48%, #A8762F 68%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 8s linear infinite' }}>
              Journey
            </p>
          </div>
          <div style={{ flexShrink: '0', display: 'flex', alignItems: 'stretch', border: '1px solid rgba(224,181,88,0.34)', borderRadius: '18px', background: 'rgba(255,251,243,0.05)', overflow: 'hidden' }}>
            <div style={{ padding: '16px 22px' }}>
              <p style={{ margin: '0 0 4px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '28px', fontWeight: '800', lineHeight: '1', letterSpacing: '-0.03em', color: '#EFCB77' }}>
                {TOTAL_STEPS}
              </p>
              <p style={{ margin: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.6)' }}>
                Stages
              </p>
            </div>
            <div style={{ width: '1px', background: 'rgba(224,181,88,0.28)' }}></div>
            <div style={{ padding: '16px 22px' }}>
              <p style={{ margin: '0 0 4px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '28px', fontWeight: '800', lineHeight: '1', letterSpacing: '-0.03em', color: '#FFFBF3' }}>
                {PHASES.length}
              </p>
              <p style={{ margin: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '9.5px', letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.6)' }}>
                Phases
              </p>
            </div>
          </div>
        </div>
        <div data-reveal="" style={{ position: 'relative', maxWidth: '860px', margin: '0 auto', paddingLeft: 'clamp(56px, 14vw, 96px)' }}>
          <span aria-hidden="true" style={{ position: 'absolute', left: '42px', top: '8px', bottom: '8px', width: '1px', background: 'linear-gradient(180deg, rgba(224,181,88,0) 0%, rgba(224,181,88,0.55) 8%, rgba(224,181,88,0.55) 92%, rgba(224,181,88,0) 100%)' }}></span>
          {PHASES.map((phase) => (
            <div key={phase.label}>
              <div style={{ position: 'relative', padding: '26px 0 14px' }}>
                <span aria-hidden="true" style={{ position: 'absolute', left: '-60px', top: '32px', width: '12px', height: '12px', background: '#E0B558', transform: 'rotate(45deg)', boxShadow: '0 0 0 6px rgba(34,16,58,1), 0 0 18px rgba(224,181,88,0.6)' }}></span>
                <p style={{ margin: '0', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '10.5px', letterSpacing: '.26em', textTransform: 'uppercase', color: 'rgba(224,181,88,0.9)' }}>
                  {phase.label}
                </p>
              </div>
              {phase.steps.map((step) => {
                const n = ++stepNo;
                const cardStyle = step.highlight
                  ? { position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '20px', marginBottom: '12px', padding: '22px 26px', border: '1px solid rgba(224,181,88,0.62)', borderRadius: '18px', background: 'linear-gradient(105deg, rgba(224,181,88,0.16), rgba(107,62,150,0.12) 70%, rgba(34,16,58,0))', boxShadow: '0 14px 34px rgba(224,181,88,0.14)', transition: 'transform .3s cubic-bezier(.2,.7,.3,1), border-color .3s ease, background .3s ease' }
                  : { position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '20px', marginBottom: '12px', padding: '22px 26px', border: '1px solid rgba(224,181,88,0.2)', borderRadius: '18px', background: 'linear-gradient(105deg, rgba(255,251,243,0.07), rgba(255,251,243,0.02))', boxShadow: 'none', transition: 'transform .3s cubic-bezier(.2,.7,.3,1), border-color .3s ease, background .3s ease' };
                return (
                  <div key={step.title} style={cardStyle} className={HOVER_CLASSES[n - 1]}>
                    <span aria-hidden="true" style={{ position: 'absolute', left: '-76px', top: '50%', marginTop: '-22px', width: '44px', height: '44px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: '\'IBM Plex Mono\', monospace', fontSize: '12px', letterSpacing: '.04em', background: '#22103A', color: '#E0B558', border: '1px solid rgba(224,181,88,0.42)', boxShadow: '0 0 0 5px #22103A' }}>
                      {String(n).padStart(2, '0')}
                    </span>
                    <span aria-hidden="true" style={{ position: 'absolute', left: '-32px', top: '50%', width: '32px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0.5), rgba(224,181,88,0.1))' }}></span>
                    <p style={{ margin: '0', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '18.5px', fontWeight: '700', letterSpacing: '-0.012em', lineHeight: '1.3', color: '#FFFBF3', textWrap: 'pretty' }}>
                      {step.title}
                    </p>
                    <span style={{ flexShrink: '0', width: '42px', height: '42px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(224,181,88,0.1)', color: '#E0B558' }}>
                      <svg width="21" height="21" viewBox="0 0 24 24" aria-hidden="true">
                        <use href={'#' + step.icon}></use>
                      </svg>
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
