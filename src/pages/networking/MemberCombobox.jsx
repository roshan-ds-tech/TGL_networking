import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { api } from '../../lib/customerApi';
import ImageSlot from '../../components/ImageSlot';

const DEBOUNCE_MS = 250;
const PAGE = 8;

function Highlight({ text, terms }) {
  if (!terms.length || !text) return text || null;
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const parts = text.split(new RegExp(`(${escaped.join('|')})`, 'ig'));
  return parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part));
}

/**
 * Searchable picker for TGL members (WAI-ARIA 1.2 combobox with a listbox).
 * Results come from the server a page at a time, debounced, so the whole
 * member list is never loaded. The value is always a real member record —
 * free text can't be submitted.
 */
export default function MemberCombobox({ id, onSelect, invalid, describedBy }) {
  const uid = useId();
  const listId = `${uid}-list`;
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(-1);
  const wrap = useRef(null);
  const input = useRef(null);
  const seq = useRef(0);
  const ctrl = useRef(null);
  const suggestions = useRef(null); // first page for the empty query, fetched once per open dialog

  const query = text.trim();
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);

  const run = useCallback((q, offset) => {
    ctrl.current?.abort();
    const controller = new AbortController();
    ctrl.current = controller;
    const mine = ++seq.current;
    setLoading(true);
    setFailed(false);
    return api.searchMembers({ q, limit: PAGE, offset }, controller.signal)
      .then((res) => {
        if (mine !== seq.current) return;
        if (!q && offset === 0) suggestions.current = res;
        setItems((prev) => (offset ? [...prev, ...res.items] : res.items));
        setHasMore(res.has_more);
        if (!offset) setActive(res.items.length ? 0 : -1);
      })
      .catch((err) => {
        if (err?.name === 'AbortError' || mine !== seq.current) return;
        setFailed(true);
        if (!offset) { setItems([]); setHasMore(false); }
      })
      .finally(() => { if (mine === seq.current) setLoading(false); });
  }, []);

  // Typing: wait for a pause, then ask the server. The empty query reuses the
  // cached suggestions instead of asking again.
  useEffect(() => {
    if (!open) return undefined;
    if (!query && suggestions.current) {
      setItems(suggestions.current.items);
      setHasMore(suggestions.current.has_more);
      setActive(suggestions.current.items.length ? 0 : -1);
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    const t = setTimeout(() => run(query, 0), query ? DEBOUNCE_MS : 0);
    return () => clearTimeout(t);
  }, [query, open, run]);

  useEffect(() => () => ctrl.current?.abort(), []);

  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (wrap.current && !wrap.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);

  useEffect(() => {
    if (active < 0) return;
    document.getElementById(`${uid}-opt-${active}`)?.scrollIntoView({ block: 'nearest' });
  }, [active, uid]);

  function choose(member) {
    setOpen(false);
    setText('');
    onSelect(member);
  }

  function onKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive((a) => (items.length ? (a + 1) % items.length : -1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive((a) => (items.length ? (a <= 0 ? items.length - 1 : a - 1) : -1));
    } else if (e.key === 'Enter') {
      if (open && active >= 0 && items[active]) {
        e.preventDefault();
        choose(items[active]);
      }
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault();
        e.stopPropagation(); // close the list, not the dialog around it
        setOpen(false);
      }
    } else if (e.key === 'Tab') {
      setOpen(false);
    }
  }

  const showEmpty = open && !loading && !failed && items.length === 0;
  const status = loading ? 'Searching members' : failed ? 'Search failed' : items.length ? `${items.length} member${items.length === 1 ? '' : 's'} found` : 'No matching members found';

  return (
    <div className="rf-combo" ref={wrap}>
      <div className={`rf-input ${invalid ? 'is-error' : ''}`}>
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-search" /></svg>
        <input
          ref={input}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && active >= 0 ? `${uid}-opt-${active}` : undefined}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          placeholder="Search TGL members or businesses..."
          autoComplete="off"
          spellCheck={false}
          maxLength={80}
          value={text}
          onChange={(e) => { setText(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {loading && open && <span className="rf-spin" aria-hidden="true" />}
      </div>
      <span className="rf-sr" role="status" aria-live="polite">{open ? status : ''}</span>

      {open && (
        <div className="rf-pop">
          {!query && items.length > 0 && <p className="rf-pop-h">Suggested members</p>}
          <ul id={listId} role="listbox" aria-label="TGL members" className="rf-opts">
            {items.map((m, i) => (
              <li
                key={m.user_id}
                id={`${uid}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? 'is-active' : ''}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault() /* keep focus in the input */}
                onClick={() => choose(m)}
              >
                <ImageSlot shape="circle" initial={m.name} src={m.photo_url} style={{ width: 36, height: 36 }} fontSize={14} />
                <span className="rf-opt-text">
                  <strong><Highlight text={m.name} terms={terms} /></strong>
                  <small><Highlight text={m.business_name} terms={terms} /></small>
                  <small className="rf-opt-cat"><Highlight text={[m.profession, m.category_name].filter(Boolean).join(' · ')} terms={terms} /></small>
                </span>
              </li>
            ))}
          </ul>
          {loading && items.length === 0 && <p className="rf-pop-note">Searching…</p>}
          {showEmpty && <p className="rf-pop-note">No matching members found</p>}
          {failed && (
            <p className="rf-pop-note">
              Couldn’t search right now. <button type="button" className="rf-link-btn" onMouseDown={(e) => e.preventDefault()} onClick={() => run(query, 0)}>Try again</button>
            </p>
          )}
          {hasMore && !loading && (
            <button type="button" className="rf-more" onMouseDown={(e) => e.preventDefault()} onClick={() => run(query, items.length)}>Show more members</button>
          )}
        </div>
      )}
    </div>
  );
}
