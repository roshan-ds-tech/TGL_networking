import { useState } from 'react';
import { go } from '../../lib/customerApi';
import { openEnquiryModal } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import { VERTEX_FILTER_GROUPS, VERTEX_PROVIDERS } from './data';

const DEFAULT_QUERY = 'I need help building a brand identity.';

function initialQuery() {
  if (typeof window === 'undefined') return DEFAULT_QUERY;
  return new URLSearchParams(window.location.search).get('q') || DEFAULT_QUERY;
}

export default function VertexSearch() {
  const [query, setQuery] = useState(initialQuery);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [checked, setChecked] = useState({});

  const providers = verifiedOnly ? VERTEX_PROVIDERS.filter((p) => p.verified) : VERTEX_PROVIDERS;

  function clearFilters() {
    setVerifiedOnly(false);
    setChecked({});
  }

  return (
    <main style={{ maxWidth: 1240, margin: '0 auto', padding: '40px 28px 96px' }}>
      <button
        type="button"
        className="tglp-navlink"
        onClick={() => go('/app/vertex')}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 0, border: 'none', background: 'none', color: '#6B3E96', fontSize: 11, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', marginBottom: 24 }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-back" /></svg>
        Vertex
      </button>

      <form
        onSubmit={(e) => e.preventDefault()}
        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 8px 8px 22px', border: '1px solid rgba(53,26,78,0.16)', borderRadius: 999, background: '#FFFCF5', boxShadow: '0 20px 40px -26px rgba(53,26,78,0.35)', marginBottom: 40 }}
      >
        <svg width="19" height="19" viewBox="0 0 24 24" style={{ color: 'rgba(43,23,64,0.65)', flexShrink: 0 }}><use href="#i-search" /></svg>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Refine your search"
          style={{ flex: 1, minWidth: 0, border: 'none', background: 'transparent', fontSize: 16, fontWeight: 600, color: '#2B1740', outline: 'none', padding: '12px 0' }}
        />
        <button type="submit" className="tglp-invert" style={{ flexShrink: 0, padding: '14px 22px', border: 'none', borderRadius: 999, background: '#2B1740', color: '#F6EEDF', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}>
          Refine
        </button>
      </form>

      <div data-grid-2="" style={{ display: 'grid', gridTemplateColumns: '260px minmax(0,1fr)', gap: 48, alignItems: 'start' }}>
        <aside data-sticky-col="" style={{ position: 'sticky', top: 110 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
            <p style={{ margin: 0, fontSize: 11, fontWeight: 700, letterSpacing: '.2em', textTransform: 'uppercase', color: '#2B1740' }}>Filters</p>
            <a href="#clear" onClick={(e) => { e.preventDefault(); clearFilters(); }} style={{ fontSize: 12.5, fontWeight: 600 }}>Clear</a>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', border: '1px solid rgba(53,26,78,0.12)', borderRadius: 14, background: '#FFFCF5', marginBottom: 22, cursor: 'pointer' }}>
            <input type="checkbox" checked={verifiedOnly} onChange={(e) => setVerifiedOnly(e.target.checked)} style={{ accentColor: '#C08D2E', width: 16, height: 16 }} />
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, fontWeight: 600, color: '#2B1740' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" style={{ color: '#A8762F' }}><use href="#i-shield" /></svg>
              TGL Verified only
            </span>
          </label>
          {VERTEX_FILTER_GROUPS.map((g) => (
            <div key={g.title} style={{ padding: '16px 0', borderTop: '1px solid rgba(53,26,78,0.1)' }}>
              <p style={{ margin: '0 0 12px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(43,23,64,0.65)' }}>{g.title}</p>
              {g.opts.map((o) => (
                <label key={o} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0', fontSize: 13.5, color: '#2B1740', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={!!checked[o]}
                    onChange={(e) => setChecked((c) => ({ ...c, [o]: e.target.checked }))}
                    style={{ accentColor: '#C08D2E', width: 15, height: 15 }}
                  />
                  {o}
                </label>
              ))}
            </div>
          ))}
        </aside>

        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 22 }}>
            <h1 style={{ margin: 0, fontSize: 'clamp(26px,3vw,36px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#2B1740' }}>Here&apos;s what could help</h1>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12.5, color: 'rgba(43,23,64,0.65)' }}>
              Sort
              <select style={{ padding: '9px 12px', border: '1px solid rgba(53,26,78,0.16)', borderRadius: 10, background: '#FFFCF5', fontSize: 13, color: '#2B1740' }}>
                <option>Relevance</option>
                <option>Recently active</option>
              </select>
            </label>
          </div>

          <p style={{ margin: '0 0 12px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Recommended service</p>
          <div className="tgl-dark-card tglp-rise-fast" style={{ display: 'flex', alignItems: 'center', gap: 22, padding: '26px 28px', borderRadius: 20, marginBottom: 40, flexWrap: 'wrap' }}>
            <span style={{ width: 54, height: 54, borderRadius: 14, background: 'rgba(224,181,88,0.16)', border: '1px solid rgba(224,181,88,0.4)', color: '#EFCB77', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="24" height="24" viewBox="0 0 24 24"><use href="#i-megaphone" /></svg>
            </span>
            <div style={{ flex: 1, minWidth: 220 }}>
              <p style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 800, color: '#FFFBF3' }}>Marketing &amp; Branding</p>
              <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: 'rgba(246,238,223,0.68)' }}>
                Brand identity work usually covers positioning, visual identity and guidelines. These providers list it as a core service.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 14 }}>
            <p style={{ margin: 0, fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Recommended providers</p>
            <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: 'rgba(43,23,64,0.65)' }}>SAMPLE DATA</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {providers.map((p) => (
              <div key={p.id} className="tglp-lift-sm tglp-rise-fast" style={{ display: 'flex', gap: 22, padding: 24, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', flexWrap: 'wrap' }}>
                <ImageSlot shape="rounded" radius={14} label="Logo" initial={p.name} style={{ width: 72, height: 72 }} fontSize={26} />
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
                    <p style={{ margin: 0, fontSize: 18, fontWeight: 800, letterSpacing: '-0.01em', color: '#2B1740' }}>{p.name}</p>
                    {p.verified && (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px 4px 8px', borderRadius: 999, background: '#22103A', color: '#EFCB77', fontSize: 9.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}>
                        <svg width="12" height="12" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
                        TGL Verified
                      </span>
                    )}
                  </div>
                  <p style={{ margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'rgba(43,23,64,0.65)' }}>
                    {p.category}
                    <span style={{ width: 3, height: 3, borderRadius: '50%', background: 'rgba(43,23,64,0.35)' }} />
                    <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-pin" /></svg>
                    {p.location}
                  </p>
                  <p style={{ margin: '0 0 14px', fontSize: 14.5, lineHeight: 1.6, color: 'rgba(43,23,64,0.72)' }}>{p.blurb}</p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {p.tags.map((t) => (
                      <span key={t} style={{ padding: '5px 11px', borderRadius: 999, background: 'rgba(53,26,78,0.06)', fontSize: 12, fontWeight: 600, color: '#35194E' }}>{t}</span>
                    ))}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, justifyContent: 'center', flexShrink: 0 }}>
                  <button type="button" className="tglp-ghost" onClick={() => go(`/app/vertex/provider/${p.id}`)} style={{ padding: '13px 20px', border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                    View Profile
                  </button>
                  <button type="button" className="tglp-gold" onClick={() => openEnquiryModal(p.name)} style={{ padding: '13px 20px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 11, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                    Send Enquiry
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
