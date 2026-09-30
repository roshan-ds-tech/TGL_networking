import { useEffect, useMemo, useRef, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import { openConnectModal } from '../../components/AppShell';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));

const CHIP = { display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', border: '1px solid rgba(53,26,78,0.14)', borderRadius: 999, background: '#FFFCF5', fontSize: 13, fontWeight: 600, color: '#35194E', cursor: 'pointer', whiteSpace: 'nowrap' };

/* The design source shows six filter chips. Only the three backed by data on
   a member record are rendered: the other three (industry, business stage,
   interests) have nothing to filter on yet, and a chip that opens an empty
   menu is worse than one that isn't there. */
function SelectChip({ label, value, options, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const active = !!value;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        className="tglp-chip"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{ ...CHIP, borderColor: active ? '#C08D2E' : 'rgba(53,26,78,0.14)', color: active ? '#8A5A18' : '#35194E' }}
      >
        {active ? `${label}: ${options.find((o) => o.value === value)?.label ?? value}` : label}
        <svg width="12" height="12" viewBox="0 0 24 24" style={{ transform: 'rotate(90deg)' }}><use href="#i-arrow" /></svg>
      </button>
      {open && (
        <div style={{ position: 'absolute', zIndex: 20, top: 'calc(100% + 8px)', left: 0, minWidth: 220, maxHeight: 280, overflowY: 'auto', padding: 8, border: '1px solid rgba(53,26,78,0.14)', borderRadius: 16, background: '#FFFCF5', boxShadow: '0 26px 52px -26px rgba(53,26,78,0.4)' }}>
          <button type="button" className="tglp-row" onClick={() => { onChange(''); setOpen(false); }} style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 12px', border: 'none', borderRadius: 10, background: 'transparent', font: 'inherit', fontSize: 13.5, color: 'rgba(43,23,64,0.6)', cursor: 'pointer' }}>
            All
          </button>
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              className="tglp-row"
              onClick={() => { onChange(o.value); setOpen(false); }}
              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '9px 12px', border: 'none', borderRadius: 10, background: 'transparent', font: 'inherit', fontSize: 13.5, fontWeight: o.value === value ? 700 : 500, color: '#2B1740', cursor: 'pointer' }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Directory() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState('');
  const [view, setView] = useState('grid');
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [connections, setConnections] = useState(new Set());

  useEffect(() => {
    api.listConnections().then((rows) => setConnections(new Set(rows.map((c) => c.target_user_id)))).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setDenied(false);
    api.members({ q })
      .then(setItems)
      .catch((err) => {
        setItems([]);
        if (err.status === 403) setDenied(true);
      })
      .finally(() => setLoading(false));
  }, [q]);

  const cityOptions = useMemo(() => {
    const seen = [...new Set(items.map((m) => m.city).filter(Boolean))].sort();
    return seen.map((c) => ({ value: c, label: c }));
  }, [items]);

  const categoryOptions = useMemo(() => {
    const seen = new Set(items.map((m) => m.category).filter(Boolean));
    return CATEGORIES.filter((c) => seen.has(c.code)).map((c) => ({ value: c.code, label: c.name }));
  }, [items]);

  const visible = items.filter((m) => (
    (!category || m.category === category)
    && (!city || m.city === city)
    && (!verifiedOnly || m.tgl_verified)
  ));

  function Actions({ m, compact }) {
    const requested = connections.has(m.user_id);
    return (
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          className="tglp-ghost"
          onClick={() => go(`/app/networking/members/${m.member_id}`)}
          style={{ flex: compact ? undefined : 1, padding: compact ? '10px 16px' : 12, border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
        >
          {compact ? 'View' : 'View Profile'}
        </button>
        <button
          type="button"
          disabled={requested}
          onClick={() => openConnectModal(m.business_name, m.user_id)}
          style={{ flex: compact ? undefined : 1, padding: compact ? '10px 16px' : 12, border: 'none', borderRadius: 999, background: '#2B1740', color: '#F6EEDF', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: requested ? 'default' : 'pointer', whiteSpace: 'nowrap', opacity: requested ? 0.6 : 1 }}
        >
          {requested ? 'Requested' : 'Connect'}
        </button>
      </div>
    );
  }

  return (
    <>
      <NetTabs active="Members" />
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '48px 28px 96px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap', marginBottom: 26 }}>
          <div>
            <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Directory</p>
            <h1 style={{ margin: 0, fontSize: 'clamp(30px,3.4vw,44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>Find Members</h1>
          </div>
          <div style={{ display: 'flex', padding: 4, border: '1px solid rgba(53,26,78,0.14)', borderRadius: 999, background: '#FFFCF5' }}>
            {[['grid', 'i-grid', 'Grid view'], ['list', 'i-list', 'List view']].map(([key, icon, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key)}
                aria-label={label}
                aria-pressed={view === key}
                style={{ width: 40, height: 36, border: 'none', borderRadius: 999, background: view === key ? '#2B1740' : 'transparent', color: view === key ? '#F6EEDF' : '#2B1740', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <svg width="17" height="17" viewBox="0 0 24 24"><use href={`#${icon}`} /></svg>
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 6px 6px 20px', border: '1px solid rgba(53,26,78,0.16)', borderRadius: 999, background: '#FFFCF5', marginBottom: 16 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" style={{ color: 'rgba(43,23,64,0.45)', flexShrink: 0 }}><use href="#i-search" /></svg>
          <input
            type="text"
            placeholder="Search businesses, founders or expertise..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search members"
            style={{ flex: 1, minWidth: 0, border: 'none', background: 'transparent', fontSize: 15, color: '#2B1740', outline: 'none', padding: '12px 0' }}
          />
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 30 }}>
          <SelectChip label="Category" value={category} options={categoryOptions} onChange={setCategory} />
          <SelectChip label="Location" value={city} options={cityOptions} onChange={setCity} />
          <button
            type="button"
            className="tglp-chip"
            aria-pressed={verifiedOnly}
            onClick={() => setVerifiedOnly((v) => !v)}
            style={{ ...CHIP, borderColor: verifiedOnly ? '#C08D2E' : 'rgba(53,26,78,0.14)', color: verifiedOnly ? '#8A5A18' : '#35194E' }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24"><use href="#i-shield" /></svg>
            TGL Verified
          </button>
        </div>

        <p style={{ margin: '0 0 14px', fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: 'rgba(43,23,64,0.45)' }}>
          {visible.length} MEMBER{visible.length === 1 ? '' : 'S'}
        </p>

        {loading ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)', padding: 40 }}>Loading members…</p>
        ) : denied ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)', padding: 48 }}>The member directory unlocks once your Networking membership is active.</p>
        ) : visible.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)', padding: 48 }}>No members found.</p>
        ) : view === 'grid' ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))', gap: 16 }}>
            {visible.map((m) => (
              <div key={m.member_id} className="tglp-lift" style={{ padding: 24, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
                  <ImageSlot shape="circle" label="Photo" initial={m.founder_name || m.business_name} style={{ width: 56, height: 56 }} fontSize={20} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <p style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#2B1740' }}>{m.founder_name}</p>
                      {m.tgl_verified && <svg width="15" height="15" viewBox="0 0 24 24" style={{ color: '#A8762F' }}><use href="#i-shield" /></svg>}
                    </div>
                    <p style={{ margin: '2px 0 0', fontSize: 12.5, color: 'rgba(43,23,64,0.58)' }}>{m.business_name}</p>
                  </div>
                </div>
                <p style={{ margin: '0 0 6px', fontSize: 11, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: '#6B3E96' }}>{CATEGORY_MAP.get(m.category) || m.category}</p>
                <p style={{ margin: '0 0 6px', display: 'flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: 'rgba(43,23,64,0.55)' }}>
                  <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-pin" /></svg>
                  {m.city || 'Bengaluru'}
                </p>
                <p style={{ margin: '0 0 20px', fontSize: 14, lineHeight: 1.55, color: 'rgba(43,23,64,0.72)', flex: 1 }}>{m.headline || 'No headline yet.'}</p>
                <Actions m={m} />
              </div>
            ))}
          </div>
        ) : (
          <div style={{ border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5', overflow: 'hidden' }}>
            {visible.map((m) => (
              <div key={m.member_id} className="tglp-row" style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '16px 22px', borderBottom: '1px solid rgba(53,26,78,0.08)', flexWrap: 'wrap' }}>
                <ImageSlot shape="circle" label="Photo" initial={m.founder_name || m.business_name} style={{ width: 44, height: 44 }} fontSize={16} />
                <div style={{ flex: '1 1 200px', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <p style={{ margin: 0, fontSize: 15, fontWeight: 800, color: '#2B1740' }}>{m.founder_name}</p>
                    {m.tgl_verified && <svg width="14" height="14" viewBox="0 0 24 24" style={{ color: '#A8762F' }}><use href="#i-shield" /></svg>}
                  </div>
                  <p style={{ margin: '2px 0 0', fontSize: 12.5, color: 'rgba(43,23,64,0.58)' }}>{m.business_name}</p>
                </div>
                <p style={{ flex: '1 1 200px', margin: 0, fontSize: 13, color: 'rgba(43,23,64,0.62)' }}>{CATEGORY_MAP.get(m.category) || m.category}</p>
                <p style={{ flex: '0 0 110px', margin: 0, fontSize: 13, color: 'rgba(43,23,64,0.62)' }}>{m.city || 'Bengaluru'}</p>
                <Actions m={m} compact />
              </div>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
