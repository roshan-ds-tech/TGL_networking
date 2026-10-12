import { useEffect, useMemo, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api, go } from '../../lib/customerApi';
import ConnectionButton from '../../components/ConnectionButton';
import { useConnections } from '../../lib/connections';
import ImageSlot from '../../components/ImageSlot';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));
const SORTS = [
  ['recommended', 'Recommended'],
  ['name', 'Name A–Z'],
  ['trust', 'Most trusted'],
];

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function sortMembers(list, sort) {
  const rows = [...list];
  if (sort === 'name') return rows.sort((a, b) => a.founder_name.localeCompare(b.founder_name));
  if (sort === 'trust') return rows.sort((a, b) => (b.trust_score || 0) - (a.trust_score || 0));
  // Recommended: verified first, then trust, then mentors, so useful people lead.
  return rows.sort((a, b) => (
    (b.tgl_verified - a.tgl_verified) || ((b.trust_score || 0) - (a.trust_score || 0)) || (b.open_to_mentoring - a.open_to_mentoring)
  ));
}

function FilterGroup({ title, children }) {
  return (
    <fieldset className="nd-group">
      <legend>{title}</legend>
      {children}
    </fieldset>
  );
}

function Option({ label, count, on, onClick }) {
  return (
    <button type="button" className={`nd-opt ${on ? 'is-on' : ''}`} aria-pressed={on} onClick={onClick}>
      <span>{label}</span>
      {count != null && <span className="nd-count">{count}</span>}
    </button>
  );
}

function Toggle({ label, icon, on, onChange }) {
  return (
    <button type="button" className={`nd-toggle ${on ? 'is-on' : ''}`} role="switch" aria-checked={on} onClick={() => onChange(!on)}>
      <span className="nd-toggle-label"><Icon id={icon} size={15} />{label}</span>
      <span className="nd-switch"><span /></span>
    </button>
  );
}

export default function Directory({ status }) {
  const me = status?.user?.id;
  const [items, setItems] = useState([]);
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [view, setView] = useState('grid');
  const [sort, setSort] = useState('recommended');
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [mentorsOnly, setMentorsOnly] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const net = useConnections();

  // Wait for a pause in typing before asking the server, and keep the old
  // results on screen meanwhile so the grid doesn't flash empty per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setDenied(false);
    api.members({ q: debouncedQ })
      .then((rows) => live && setItems(rows))
      .catch((err) => {
        if (!live) return;
        setItems([]);
        if (err.status === 403) setDenied(true);
      })
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [debouncedQ]);

  const categories = useMemo(() => {
    const counts = new Map();
    items.forEach((m) => m.category && counts.set(m.category, (counts.get(m.category) || 0) + 1));
    return [...counts].map(([code, n]) => ({ code, n, label: CATEGORY_MAP.get(code) || code })).sort((a, b) => b.n - a.n);
  }, [items]);

  const cities = useMemo(() => {
    const counts = new Map();
    items.forEach((m) => m.city && counts.set(m.city, (counts.get(m.city) || 0) + 1));
    return [...counts].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n);
  }, [items]);

  const visible = useMemo(() => sortMembers(items.filter((m) => (
    (!category || m.category === category)
    && (!city || m.city === city)
    && (!verifiedOnly || m.tgl_verified)
    && (!mentorsOnly || m.open_to_mentoring)
  )), sort), [items, category, city, verifiedOnly, mentorsOnly, sort]);

  const activeChips = [
    category && { key: 'c', label: CATEGORY_MAP.get(category) || category, clear: () => setCategory('') },
    city && { key: 'l', label: city, clear: () => setCity('') },
    verifiedOnly && { key: 'v', label: 'TGL Verified', clear: () => setVerifiedOnly(false) },
    mentorsOnly && { key: 'm', label: 'Open to mentoring', clear: () => setMentorsOnly(false) },
  ].filter(Boolean);

  function clearAll() {
    setCategory(''); setCity(''); setVerifiedOnly(false); setMentorsOnly(false); setQ('');
  }

  function Actions({ m }) {
    return (
      <div className="nd-actions" onClick={(e) => e.stopPropagation()}>
        {m.user_id === me ? (
          <span className="nd-you">This is you</span>
        ) : (
          <ConnectionButton prefix="nd" relation={net.relation(m.user_id)} userId={m.user_id} name={m.founder_name} businessName={m.business_name} />
        )}
      </div>
    );
  }

  const open = (m) => go(`/app/networking/members/${m.member_id}`);
  const onKey = (m) => (e) => { if (e.key === 'Enter') open(m); };

  return (
    <>
      <NetTabs active="Members" />
      <main className="nd">
        <div className="nd-head">
          <div>
            <h1>Members</h1>
            <p>Founders in the Season 1 network. Find the right person, then ask for an introduction.</p>
          </div>
          <div className="nd-search">
            <Icon id="i-search" size={17} />
            <input type="text" placeholder="Search by name, business or skill" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search members" />
            {q && <button type="button" aria-label="Clear search" onClick={() => setQ('')}><Icon id="i-x" size={14} /></button>}
          </div>
        </div>

        <div className="nd-layout">
          <aside className={`nd-rail ${filtersOpen ? 'is-open' : ''}`} aria-label="Filters">
            <FilterGroup title="Category">
              <Option label="All categories" on={!category} onClick={() => setCategory('')} />
              {categories.map((c) => <Option key={c.code} label={c.label} count={c.n} on={category === c.code} onClick={() => setCategory(category === c.code ? '' : c.code)} />)}
            </FilterGroup>
            {cities.length > 0 && (
              <FilterGroup title="Location">
                <Option label="Anywhere" on={!city} onClick={() => setCity('')} />
                {cities.map((c) => <Option key={c.name} label={c.name} count={c.n} on={city === c.name} onClick={() => setCity(city === c.name ? '' : c.name)} />)}
              </FilterGroup>
            )}
            <FilterGroup title="Show only">
              <Toggle label="TGL Verified" icon="i-shield" on={verifiedOnly} onChange={setVerifiedOnly} />
              <Toggle label="Open to mentoring" icon="i-bulb" on={mentorsOnly} onChange={setMentorsOnly} />
            </FilterGroup>
          </aside>

          <section className="nd-results" aria-live="polite">
            <div className="nd-bar">
              <button type="button" className="nd-filter-btn" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((v) => !v)}>
                <Icon id="i-list" size={15} /> Filters{activeChips.length > 0 && <span className="nd-badge">{activeChips.length}</span>}
              </button>
              <p className="nd-total"><strong>{loading && !items.length ? '–' : visible.length}</strong> {visible.length === 1 ? 'member' : 'members'}</p>
              <label className="nd-sort">
                <span>Sort</span>
                <select value={sort} onChange={(e) => setSort(e.target.value)}>
                  {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </label>
              <div className="nd-view" role="group" aria-label="Layout">
                {[['grid', 'i-grid', 'Grid view'], ['list', 'i-list', 'List view']].map(([key, icon, label]) => (
                  <button key={key} type="button" aria-label={label} aria-pressed={view === key} className={view === key ? 'is-on' : ''} onClick={() => setView(key)}>
                    <Icon id={icon} size={16} />
                  </button>
                ))}
              </div>
            </div>

            {activeChips.length > 0 && (
              <div className="nd-chips">
                {activeChips.map((c) => (
                  <button key={c.key} type="button" className="nd-chip" onClick={c.clear} aria-label={`Remove filter ${c.label}`}>
                    {c.label} <Icon id="i-x" size={12} />
                  </button>
                ))}
                <button type="button" className="nd-clear" onClick={clearAll}>Clear all</button>
              </div>
            )}

            {denied ? (
              <div className="nd-empty">
                <span className="nd-empty-icon"><Icon id="i-lock" size={22} /></span>
                <h2>The directory unlocks with your membership</h2>
                <p>Once your Networking membership is active you can browse and connect with every Season 1 founder.</p>
              </div>
            ) : loading && items.length === 0 ? (
              <div className="nd-grid">
                {[0, 1, 2].map((i) => <div key={i} className="nd-card nd-card--skeleton" aria-hidden="true"><span className="nd-sk nd-sk--avatar" /><span className="nd-sk" /><span className="nd-sk nd-sk--short" /></div>)}
              </div>
            ) : visible.length === 0 ? (
              <div className="nd-empty">
                <span className="nd-empty-icon"><Icon id="i-search" size={22} /></span>
                <h2>No members match</h2>
                <p>Try a different search, or remove a filter to widen the results.</p>
                {(activeChips.length > 0 || q) && <button type="button" className="nd-btn" onClick={clearAll}>Clear filters</button>}
              </div>
            ) : view === 'grid' ? (
              <div className="nd-grid" style={{ opacity: loading ? 0.6 : 1 }}>
                {visible.map((m) => (
                  <article key={m.member_id} className="nd-card" tabIndex={0} onClick={() => open(m)} onKeyDown={onKey(m)}>
                    <div className="nd-card-top">
                      <ImageSlot shape="circle" initial={m.founder_name || m.business_name} src={m.photo_url} style={{ width: 60, height: 60 }} fontSize={22} />
                      <div className="nd-id">
                        <h3>{m.founder_name}{m.tgl_verified && <span className="nd-verified" title="TGL Verified"><Icon id="i-shield" size={14} /></span>}</h3>
                        <p>{m.business_name}</p>
                      </div>
                    </div>
                    <p className="nd-headline">{m.headline || 'Founder in the TGL Season 1 network.'}</p>
                    <div className="nd-tags">
                      <span className="nd-tag">{CATEGORY_MAP.get(m.category) || m.category}</span>
                      {m.city && <span className="nd-tag nd-tag--ghost"><Icon id="i-pin" size={12} />{m.city}</span>}
                      {m.open_to_mentoring && <span className="nd-tag nd-tag--mentor">Mentor</span>}
                    </div>
                    <div className="nd-card-foot">
                      <span className="nd-view-link">View profile <Icon id="i-arrow" size={13} /></span>
                      <Actions m={m} />
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <ul className="nd-list" style={{ opacity: loading ? 0.6 : 1 }}>
                {visible.map((m) => (
                  <li key={m.member_id} className="nd-item" tabIndex={0} onClick={() => open(m)} onKeyDown={onKey(m)}>
                    <ImageSlot shape="circle" initial={m.founder_name || m.business_name} src={m.photo_url} style={{ width: 48, height: 48 }} fontSize={18} />
                    <div className="nd-item-main">
                      <h3>{m.founder_name}{m.tgl_verified && <span className="nd-verified" title="TGL Verified"><Icon id="i-shield" size={14} /></span>}{m.open_to_mentoring && <span className="nd-tag nd-tag--mentor">Mentor</span>}</h3>
                      <p>{m.business_name}{m.headline ? ` · ${m.headline}` : ''}</p>
                    </div>
                    <span className="nd-item-cat">{CATEGORY_MAP.get(m.category) || m.category}</span>
                    <span className="nd-item-city">{m.city}</span>
                    <Actions m={m} />
                  </li>
                ))}
              </ul>
            )}

            {!denied && !loading && visible.length > 0 && (
              <div className="nd-cta">
                <div>
                  <h3>Can&apos;t find who you need?</h3>
                  <p>Post a business need and let members come to you.</p>
                </div>
                <button type="button" className="nd-btn nd-btn--primary" onClick={() => go('/app/networking/needs')}>Post a need</button>
              </div>
            )}
          </section>
        </div>
      </main>
    </>
  );
}
