import { useState } from 'react';
import { go } from '../../lib/customerApi';
import { Eyebrow } from '../../components/AppShell';
import { VERTEX_CATEGORIES, VERTEX_CHIPS } from './data';

const HOW_IT_WORKS = [
  { n: '01', t: 'Your business problem', d: 'Plain language, no categories to learn.' },
  { n: '02', t: 'Guided to a service', d: 'AI reads the need and names the service that fits.' },
  { n: '03', t: 'Real providers', d: 'Only listed businesses — nothing generated.' },
  { n: '04', t: 'Direct enquiry', d: 'Talk to the provider. People do the work.' },
];

export default function VertexHome() {
  const [query, setQuery] = useState('');

  function search(q) {
    const term = (q ?? query).trim();
    go(term ? `/app/vertex/search?q=${encodeURIComponent(term)}` : '/app/vertex/search');
  }

  return (
    <>
      <section style={{ position: 'relative', overflow: 'hidden' }}>
        <div
          aria-hidden="true"
          className="tglp-glow"
          style={{ position: 'absolute', top: -80, right: -140, width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle, rgba(224,181,88,0.28), rgba(224,181,88,0) 65%)', pointerEvents: 'none' }}
        />
        <div
          aria-hidden="true"
          style={{ position: 'absolute', bottom: -120, left: -160, width: 480, height: 480, borderRadius: '50%', background: 'radial-gradient(circle, rgba(107,62,150,0.14), rgba(107,62,150,0) 68%)', pointerEvents: 'none' }}
        />
        <div data-grid-2="" style={{ position: 'relative', maxWidth: 1240, margin: '0 auto', padding: '72px 28px 64px', display: 'grid', gridTemplateColumns: 'minmax(0,1.25fr) minmax(0,0.9fr)', gap: 60, alignItems: 'center' }}>
          <div className="tglp-rise">
            <Eyebrow>Vertex · Open B2B Discovery</Eyebrow>
            <h1 style={{ margin: '0 0 22px' }}>
              <span style={{ display: 'block', fontSize: 'clamp(34px,4.4vw,60px)', lineHeight: 1, letterSpacing: '-0.035em', fontWeight: 800, textTransform: 'uppercase', color: '#2B1740' }}>
                What business solution do you
              </span>
              <span className="tgl-script-word" style={{ display: 'block', marginTop: 4, fontSize: 'clamp(56px,7.4vw,104px)', lineHeight: 1 }}>need?</span>
            </h1>
            <p style={{ margin: '0 0 30px', maxWidth: 540, fontSize: 17, lineHeight: 1.65, color: 'rgba(43,23,64,0.7)' }}>
              Describe the problem in your own words. Vertex points you to the right service and to real businesses that deliver it.
            </p>
            <form
              onSubmit={(e) => { e.preventDefault(); search(); }}
              style={{ display: 'flex', alignItems: 'center', gap: 10, maxWidth: 620, padding: '8px 8px 8px 22px', border: '1px solid rgba(53,26,78,0.16)', borderRadius: 999, background: '#FFFCF5', boxShadow: '0 20px 40px -24px rgba(53,26,78,0.35)', marginBottom: 20 }}
            >
              <svg width="19" height="19" viewBox="0 0 24 24" style={{ color: 'rgba(43,23,64,0.65)', flexShrink: 0 }}><use href="#i-search" /></svg>
              <input
                type="text"
                placeholder="Tell us what your business needs..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Describe what your business needs"
                style={{ flex: 1, minWidth: 0, border: 'none', background: 'transparent', fontSize: 15.5, color: '#2B1740', outline: 'none', padding: '12px 0' }}
              />
              <button
                type="submit"
                className="tglp-gold"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 10, flexShrink: 0, padding: '15px 24px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
              >
                Search
                <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
              </button>
            </form>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, maxWidth: 640 }}>
              {VERTEX_CHIPS.map((label) => (
                <button
                  key={label}
                  type="button"
                  className="tglp-chip"
                  onClick={() => search(label)}
                  style={{ padding: '9px 16px', border: '1px solid rgba(53,26,78,0.14)', borderRadius: 999, background: 'rgba(255,252,245,0.7)', color: '#35194E', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="tglp-rise-3" style={{ position: 'relative' }}>
            <div aria-hidden="true" style={{ position: 'absolute', inset: '14px -14px -14px 14px', border: '1px solid rgba(192,141,46,0.6)', borderRadius: 20 }} />
            <div className="tgl-dark-card" style={{ position: 'relative', borderRadius: 20, padding: '38px 36px', boxShadow: '0 30px 60px rgba(34,16,58,0.28)' }}>
              <p style={{ margin: '0 0 24px', fontSize: 10.5, letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: 700 }}>How Vertex works</p>
              {HOW_IT_WORKS.map((step, i) => (
                <div key={step.n} style={{ display: 'flex', gap: 18, paddingBottom: i < HOW_IT_WORKS.length - 1 ? 18 : 0, marginBottom: i < HOW_IT_WORKS.length - 1 ? 18 : 0, borderBottom: i < HOW_IT_WORKS.length - 1 ? '1px dashed rgba(224,181,88,0.35)' : 'none' }}>
                  <span style={{ fontSize: 30, fontWeight: 800, color: '#EFCB77', lineHeight: 1, minWidth: 46 }}>{step.n}</span>
                  <div>
                    <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#FFFBF3' }}>{step.t}</p>
                    <p style={{ margin: '4px 0 0', fontSize: 13, color: 'rgba(246,238,223,0.62)' }}>{step.d}</p>
                  </div>
                </div>
              ))}
              <div style={{ marginTop: 28, padding: '16px 20px', background: 'linear-gradient(135deg,#E0B558,#C08D2E)', borderRadius: 14 }}>
                <p style={{ margin: 0, fontSize: 12, fontWeight: 800, letterSpacing: '.2em', textTransform: 'uppercase', color: '#22103A' }}>AI guides. Humans deliver.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '24px 28px 96px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap', marginBottom: 28 }}>
          <div>
            <p style={{ margin: '0 0 10px', fontSize: 11, letterSpacing: '.28em', textTransform: 'uppercase', fontWeight: 700, color: '#8F6420' }}>Browse</p>
            <h2 style={{ margin: 0, fontSize: 'clamp(26px,3vw,38px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#2B1740' }}>Explore business solutions</h2>
          </div>
          <p style={{ margin: 0, maxWidth: 380, fontSize: 14.5, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
            Fourteen service areas covering what growing businesses most often need.
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
          {VERTEX_CATEGORIES.map((cat) => (
            <button
              key={cat.code}
              type="button"
              className="tglp-lift"
              onClick={() => search(cat.name)}
              style={{ textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 26, padding: '22px 22px 20px', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, background: '#FFFCF5', cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', width: '100%' }}>
                <span style={{ width: 44, height: 44, borderRadius: 12, background: 'rgba(192,141,46,0.12)', color: '#A8762F', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="21" height="21" viewBox="0 0 24 24"><use href={`#${cat.icon}`} /></svg>
                </span>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: 'rgba(43,23,64,0.65)' }}>{cat.code}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 10, width: '100%' }}>
                <span style={{ fontSize: 15.5, fontWeight: 700, lineHeight: 1.3, color: '#2B1740' }}>{cat.name}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" style={{ color: '#8F6420', flexShrink: 0 }}><use href="#i-arrow" /></svg>
              </div>
            </button>
          ))}
        </div>
      </main>
    </>
  );
}
