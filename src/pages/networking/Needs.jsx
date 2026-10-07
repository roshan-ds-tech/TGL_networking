import { useEffect, useMemo, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api } from '../../lib/customerApi';
import { timeAgo } from '../../lib/format';
import { showToast } from '../../components/AppShell';
import NetTabs from './NetTabs';
import ImageSlot from '../../components/ImageSlot';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));
const DAY = 24 * 60 * 60 * 1000;
const LONG_TEXT = 150;

const TIPS = [
  'Be specific: "GST-ready CA for exports" beats "finance help".',
  'Say what a good answer looks like: timeline, budget range or location.',
  'Reply to members who offer help so the board stays active.',
];

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

/* ------------------------------ Post a need ------------------------------ */

function PostNeedModal({ onClose, onPosted }) {
  const [form, setForm] = useState({ title: '', category: '', description: '' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !submitting) onClose(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose, submitting]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const ready = form.title.trim().length >= 4 && !!form.category;

  async function submit(ev) {
    ev.preventDefault();
    if (!ready) return;
    setError('');
    setSubmitting(true);
    try {
      await api.createNeed({ title: form.title.trim(), category: form.category, description: form.description.trim() || undefined });
      onPosted();
    } catch (err) {
      setError(err.message || 'Could not post your need.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rf-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !submitting) onClose(); }}>
      <form className="rf-modal" role="dialog" aria-modal="true" aria-labelledby="nb-post-title" onSubmit={submit}>
        <header className="rf-modal-head">
          <div>
            <h2 id="nb-post-title">Post a need</h2>
            <p>Tell the network what you&apos;re looking for. Members who can help will reach out.</p>
          </div>
          <button type="button" className="rf-x" onClick={onClose} aria-label="Close"><Icon id="i-x" size={16} /></button>
        </header>

        <div className="rf-field">
          <label htmlFor="nb-title"><span>1</span> What do you need?</label>
          <div className="rf-input"><input id="nb-title" maxLength={200} placeholder="e.g. Looking for a CA for GST filing" value={form.title} onChange={set('title')} autoFocus required /></div>
        </div>

        <div className="rf-field">
          <label htmlFor="nb-cat"><span>2</span> Category</label>
          <div className="rf-input">
            <select id="nb-cat" value={form.category} onChange={set('category')} required>
              <option value="">Select a category</option>
              {CATEGORIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
            </select>
          </div>
        </div>

        <div className="rf-field">
          <label htmlFor="nb-desc"><span>3</span> Details <em>Optional</em></label>
          <textarea id="nb-desc" rows={4} maxLength={2000} placeholder="Add context that helps someone respond: scope, timeline, budget, location." value={form.description} onChange={set('description')} />
          <small className="rf-count">{form.description.length}/2000</small>
        </div>

        {error && <p className="rf-error" role="alert">{error}</p>}

        <footer className="rf-modal-foot">
          <button type="button" className="rf-btn" onClick={onClose} disabled={submitting}>Cancel</button>
          <button type="submit" className="rf-btn rf-btn--primary" disabled={submitting || !ready}>{submitting ? 'Posting…' : 'Post need'}<Icon id="i-send" size={14} /></button>
        </footer>
      </form>
    </div>
  );
}

/* ---------------------------------- Page ---------------------------------- */

export default function Needs({ status }) {
  const me = status?.user?.id;
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [postOpen, setPostOpen] = useState(false);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [mineOnly, setMineOnly] = useState(false);
  const [sort, setSort] = useState('new');
  const [helpingId, setHelpingId] = useState(null);
  const [helpedIds, setHelpedIds] = useState(new Set());
  const [openId, setOpenId] = useState(null);
  const [now] = useState(Date.now); // one clock per visit keeps render pure

  function load(silent) {
    if (!silent) setLoading(true);
    api.needs().then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }
  useEffect(() => { load(false); }, []);

  async function offerHelp(id) {
    setHelpingId(id);
    try {
      await api.helpNeed(id);
      setHelpedIds((prev) => new Set(prev).add(id));
      showToast('Response sent. The member will be notified.');
    } catch (err) {
      showToast(err.message || 'Could not send your response.');
    } finally {
      setHelpingId(null);
    }
  }

  const categories = useMemo(() => {
    const counts = new Map();
    items.forEach((n) => counts.set(n.category, (counts.get(n.category) || 0) + 1));
    return [...counts].map(([code, n]) => ({ code, n, label: CATEGORY_MAP.get(code) || code })).sort((a, b) => b.n - a.n);
  }, [items]);

  const mine = useMemo(() => items.filter((n) => n.poster_user_id === me), [items, me]);
  const thisWeek = items.filter((n) => now - new Date(n.created_at).getTime() < 7 * DAY).length;

  const visible = useMemo(() => {
    const term = q.trim().toLowerCase();
    const rows = items.filter((n) => (
      (!category || n.category === category)
      && (!mineOnly || n.poster_user_id === me)
      && (!term || `${n.title} ${n.description || ''} ${n.poster_name} ${n.business_name}`.toLowerCase().includes(term))
    ));
    return rows.sort((a, b) => (sort === 'new' ? 1 : -1) * (new Date(b.created_at) - new Date(a.created_at)));
  }, [items, q, category, mineOnly, sort, me]);

  const filtered = !!(q || category || mineOnly);
  function clearFilters() { setQ(''); setCategory(''); setMineOnly(false); }

  return (
    <>
      <NetTabs active="Need Board" />
      <main className="nb">
        <div className="nb-top">
          <div>
            <h1>Need board</h1>
            <p>Ask the network for what your business needs, or be the member who solves it.</p>
          </div>
          <button type="button" className="rf-btn rf-btn--primary" onClick={() => setPostOpen(true)}>
            <Icon id="i-plus" size={15} /> Post a need
          </button>
        </div>

        <div className="nb-layout">
          <section className="nb-main" aria-live="polite">
            <div className="nb-search">
              <Icon id="i-search" size={17} />
              <input type="text" placeholder="Search needs, members or businesses" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search needs" />
              {q && <button type="button" aria-label="Clear search" onClick={() => setQ('')}><Icon id="i-x" size={14} /></button>}
            </div>

            <div className="nb-chips" role="group" aria-label="Filter by category">
              <button type="button" className={!category && !mineOnly ? 'is-on' : ''} aria-pressed={!category && !mineOnly} onClick={() => { setCategory(''); setMineOnly(false); }}>
                All <span>{items.length}</span>
              </button>
              {mine.length > 0 && (
                <button type="button" className={mineOnly ? 'is-on' : ''} aria-pressed={mineOnly} onClick={() => { setMineOnly((v) => !v); setCategory(''); }}>
                  My needs <span>{mine.length}</span>
                </button>
              )}
              {categories.map((c) => (
                <button key={c.code} type="button" className={category === c.code ? 'is-on' : ''} aria-pressed={category === c.code} title={c.label} onClick={() => { setCategory(category === c.code ? '' : c.code); setMineOnly(false); }}>
                  <em>{c.label}</em> <span>{c.n}</span>
                </button>
              ))}
            </div>

            <div className="nb-bar">
              <p><strong>{loading ? '–' : visible.length}</strong> open {visible.length === 1 ? 'need' : 'needs'}</p>
              <label>
                <span>Sort</span>
                <select value={sort} onChange={(e) => setSort(e.target.value)}>
                  <option value="new">Newest first</option>
                  <option value="old">Oldest first</option>
                </select>
              </label>
            </div>

            {loading ? (
              <div className="nb-list">{[0, 1, 2].map((i) => <div key={i} className="nb-card nb-card--sk" aria-hidden="true"><span className="rf-sk rf-sk--a" /><span className="rf-sk-l"><span className="rf-sk" /><span className="rf-sk rf-sk--s" /></span></div>)}</div>
            ) : visible.length === 0 ? (
              items.length === 0 ? (
                <div className="rf-empty">
                  <span className="rf-empty-icon"><Icon id="i-megaphone" size={24} /></span>
                  <h2>No open needs yet</h2>
                  <p>Looking for a supplier, a partner or your next client? Be the first to ask the network.</p>
                  <button type="button" className="rf-btn rf-btn--primary" onClick={() => setPostOpen(true)}><Icon id="i-plus" size={15} /> Post a need</button>
                </div>
              ) : (
                <div className="rf-empty rf-empty--sm">
                  <h2>No needs match</h2>
                  <p>Try a different search, or clear the filters to see everything.</p>
                  {filtered && <button type="button" className="rf-btn" onClick={clearFilters}>Clear filters</button>}
                </div>
              )
            ) : (
              <ul className="nb-list">
                {visible.map((n) => {
                  const isOwn = n.poster_user_id === me;
                  const done = helpedIds.has(n.id);
                  const long = (n.description || '').length > LONG_TEXT;
                  const expanded = openId === n.id;
                  const fresh = now - new Date(n.created_at).getTime() < 2 * DAY;
                  return (
                    <li key={n.id} className="nb-card">
                      <div className="nb-card-top">
                        <ImageSlot shape="circle" initial={n.poster_name} src={n.poster_photo_url} style={{ width: 40, height: 40 }} fontSize={15} />
                        <div className="nb-poster">
                          <strong>{n.poster_name}</strong>
                          <span>{[n.business_name, n.city].filter(Boolean).join(' · ')}</span>
                        </div>
                        {fresh && <span className="nb-new">New</span>}
                        <span className="nb-time">{timeAgo(n.created_at)}</span>
                      </div>

                      <h3>{n.title}</h3>
                      {n.description && <p className={`nb-desc ${expanded ? 'is-open' : ''}`}>{n.description}</p>}

                      <div className="nb-card-foot">
                        <span className="nb-cat" title={CATEGORY_MAP.get(n.category) || n.category}>{CATEGORY_MAP.get(n.category) || n.category}</span>
                        <div className="nb-actions">
                          {long && <button type="button" className="rf-link-btn" onClick={() => setOpenId(expanded ? null : n.id)}>{expanded ? 'Show less' : 'Read more'}</button>}
                          <button
                            type="button"
                            className={`rf-btn ${isOwn || done ? '' : 'rf-btn--dark'}`}
                            disabled={isOwn || helpingId === n.id || done}
                            onClick={() => offerHelp(n.id)}
                          >
                            {isOwn ? 'Your need' : done ? <><Icon id="i-check" size={13} /> Offer sent</> : helpingId === n.id ? 'Sending…' : 'I can help'}
                          </button>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <aside className="nb-side">
            <section className="rf-panel nb-stats">
              <h2>The board right now</h2>
              <dl>
                <div><dt>Open needs</dt><dd>{loading ? '–' : items.length}</dd></div>
                <div><dt>New this week</dt><dd>{loading ? '–' : thisWeek}</dd></div>
                <div><dt>Categories</dt><dd>{loading ? '–' : categories.length}</dd></div>
              </dl>
            </section>

            {mine.length > 0 && (
              <section className="rf-panel nb-mine">
                <h2>Your open needs</h2>
                <ul>
                  {mine.slice(0, 3).map((n) => (
                    <li key={n.id}><strong>{n.title}</strong><span>{timeAgo(n.created_at)}</span></li>
                  ))}
                </ul>
              </section>
            )}

            <section className="nb-tips tgl-dark-card">
              <h2><Icon id="i-bulb" size={17} /> Getting good responses</h2>
              <ul>{TIPS.map((t) => <li key={t}>{t}</li>)}</ul>
              <button type="button" onClick={() => setPostOpen(true)}>Post a need <Icon id="i-arrow" size={13} /></button>
            </section>
          </aside>
        </div>
      </main>

      {postOpen && (
        <PostNeedModal
          onClose={() => setPostOpen(false)}
          onPosted={() => { setPostOpen(false); showToast('Your need is on the board.'); clearFilters(); setSort('new'); load(true); }}
        />
      )}
    </>
  );
}
