import { useState } from 'react';
import { go } from '../../lib/customerApi';
import { showToast } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import { PROVIDER_SERVICES, PROVIDER_SPECS, VERTEX_PROVIDERS } from './data';

const FACTS = [
  ['Established', '—'],
  ['Team size', '—'],
  ['Service areas', 'Bengaluru · Remote'],
  ['Website', 'example.com'],
];

export default function VertexProvider({ id }) {
  const provider = VERTEX_PROVIDERS.find((p) => p.id === id) || VERTEX_PROVIDERS[0];
  const [note, setNote] = useState('');

  return (
    <>
      <section className="tgl-dark-card">
        <div style={{ maxWidth: 1240, margin: '0 auto', padding: '36px 28px 44px' }}>
          <button
            type="button"
            onClick={() => go('/app/vertex/search')}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 0, border: 'none', background: 'none', color: '#EFCB77', fontSize: 11, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', marginBottom: 30 }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-back" /></svg>
            Results
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 26, flexWrap: 'wrap' }}>
            <div style={{ padding: 4, borderRadius: 20, background: '#FFFCF5', flexShrink: 0 }}>
              <ImageSlot shape="rounded" radius={16} label="Logo" initial={provider.name} style={{ width: 100, height: 100, display: 'block' }} fontSize={36} />
            </div>
            <div style={{ flex: 1, minWidth: 240 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>
                <h1 style={{ margin: 0, fontSize: 'clamp(28px,3.4vw,42px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#FFFBF3' }}>{provider.name}</h1>
                {provider.verified && (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px 6px 10px', borderRadius: 999, background: 'rgba(224,181,88,0.16)', border: '1px solid rgba(224,181,88,0.5)', color: '#EFCB77', fontSize: 10, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}>
                    <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
                    TGL Verified
                  </span>
                )}
              </div>
              <p style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: 14.5, color: 'rgba(246,238,223,0.7)' }}>
                {provider.category}
                <span style={{ width: 3, height: 3, borderRadius: '50%', background: 'rgba(246,238,223,0.4)' }} />
                <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-pin" /></svg>
                {provider.location}
              </p>
            </div>
            <button
              type="button"
              className="tglp-gold"
              onClick={() => { document.getElementById('provider-enquiry')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 12, padding: '17px 28px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', boxShadow: '0 10px 26px rgba(192,141,46,0.35)' }}
            >
              Send Enquiry
              <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
            </button>
          </div>
          <p style={{ margin: '22px 0 0', fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: 'rgba(246,238,223,0.45)' }}>
            SAMPLE PROFILE — replace with a real Vertex listing
          </p>
        </div>
      </section>

      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '52px 28px 96px' }}>
        <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr)', gap: 56, alignItems: 'start' }}>
          <div>
            <p style={{ margin: '0 0 12px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>About</p>
            <p style={{ margin: '0 0 40px', fontSize: 17, lineHeight: 1.7, color: 'rgba(43,23,64,0.78)' }}>{provider.blurb}</p>

            <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, padding: '32px 0', borderTop: '1px solid rgba(53,26,78,0.12)', borderBottom: '1px solid rgba(53,26,78,0.12)', marginBottom: 40 }}>
              <div>
                <p style={{ margin: '0 0 14px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Services</p>
                {PROVIDER_SERVICES.map((sv) => (
                  <p key={sv} style={{ margin: 0, padding: '9px 0', display: 'flex', alignItems: 'center', gap: 10, fontSize: 15, fontWeight: 600, color: '#2B1740', borderBottom: '1px solid rgba(53,26,78,0.07)' }}>
                    <svg width="15" height="15" viewBox="0 0 24 24" style={{ color: '#C08D2E' }}><use href="#i-check" /></svg>
                    {sv}
                  </p>
                ))}
              </div>
              <div>
                <p style={{ margin: '0 0 14px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Specializations</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {PROVIDER_SPECS.map((sp) => (
                    <span key={sp} style={{ padding: '8px 14px', border: '1px solid rgba(53,26,78,0.14)', borderRadius: 999, fontSize: 13, fontWeight: 600, color: '#35194E', background: '#FFFCF5' }}>{sp}</span>
                  ))}
                </div>
              </div>
            </div>

            <p style={{ margin: '0 0 18px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Business information</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 1, background: 'rgba(53,26,78,0.1)', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 18, overflow: 'hidden', marginBottom: 40 }}>
              {FACTS.map(([label, value]) => (
                <div key={label} style={{ padding: 20, background: '#FFFCF5' }}>
                  <p style={{ margin: '0 0 6px', fontSize: 10.5, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.5)' }}>{label}</p>
                  <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: label === 'Website' ? '#6B3E96' : '#2B1740' }}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          <aside data-sticky-col="" style={{ position: 'sticky', top: 110 }}>
            <div id="provider-enquiry" className="tglp-framed">
              <div style={{ background: '#FFFCF5', border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, padding: 30, boxShadow: '0 30px 60px -30px rgba(34,16,58,0.3)' }}>
                <p style={{ margin: '0 0 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Enquiry</p>
                <h3 style={{ margin: '0 0 20px', fontSize: 21, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>What do you need help with?</h3>
                <textarea
                  className="tgl-input"
                  rows={4}
                  style={{ resize: 'vertical', marginBottom: 12 }}
                  placeholder="A few lines on the project and where you are today."
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 20 }}>
                  <select className="tgl-input" style={{ padding: 12, fontSize: 13 }} defaultValue="">
                    <option value="">Budget (optional)</option>
                    <option>Under ₹50k</option>
                    <option>₹50k–2L</option>
                    <option>₹2L+</option>
                  </select>
                  <select className="tgl-input" style={{ padding: 12, fontSize: 13 }} defaultValue="">
                    <option value="">Timeline (optional)</option>
                    <option>This month</option>
                    <option>1–3 months</option>
                    <option>Flexible</option>
                  </select>
                </div>
                <button
                  type="button"
                  className="tglp-gold"
                  onClick={() => { setNote(''); showToast(`Enquiry sent to ${provider.name}.`); }}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 16, border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                >
                  Submit Enquiry
                  <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-send" /></svg>
                </button>
                <p style={{ margin: '14px 0 0', fontSize: 12, lineHeight: 1.5, color: 'rgba(43,23,64,0.5)' }}>
                  Goes straight to the provider. TGL doesn&apos;t sell your details.
                </p>
              </div>
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
