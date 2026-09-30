import { useEffect, useState } from 'react';
import { CATEGORIES } from '../../data/categories';
import { api } from '../../lib/customerApi';
import { timeAgo } from '../../lib/format';
import { Field, showToast } from '../../components/AppShell';
import NetTabs from './NetTabs';

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.code, c.name]));

export default function Needs({ status }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', category: '', description: '' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [helpingId, setHelpingId] = useState(null);
  const [helpedIds, setHelpedIds] = useState(new Set());
  const [openId, setOpenId] = useState(null);

  function load() {
    setLoading(true);
    api.needs().then(setItems).catch(() => setItems([])).finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function submit(ev) {
    ev.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await api.createNeed(form);
      setForm({ title: '', category: '', description: '' });
      setShowForm(false);
      load();
    } catch (err) {
      setError(err.message || 'Could not post your need.');
    } finally {
      setSubmitting(false);
    }
  }

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

  return (
    <>
      <NetTabs active="Need Board" />
      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '48px 28px 96px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap', marginBottom: 34 }}>
          <div>
            <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#C08D2E' }}>Business Need Board · Members only</p>
            <h1 style={{ margin: 0, fontSize: 'clamp(30px,3.4vw,44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>What does your business need?</h1>
          </div>
          <button
            type="button"
            className="tglp-gold"
            onClick={() => setShowForm((v) => !v)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '15px 24px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24"><use href={showForm ? '#i-x' : '#i-plus'} /></svg>
            {showForm ? 'Close' : 'Post a Need'}
          </button>
        </div>

        {showForm && (
          <form onSubmit={submit} className="tglp-rise-fast" style={{ padding: 34, border: '1px solid rgba(192,141,46,0.4)', borderRadius: 22, background: '#FFFCF5', marginBottom: 34, boxShadow: '0 30px 60px -30px rgba(34,16,58,0.3)' }}>
            <h2 style={{ margin: '0 0 24px', fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Post a need</h2>
            <div className="tgl-portal-grid-2" style={{ marginBottom: 18 }}>
              <Field label="01 · What do you need?">
                <input className="tgl-input" placeholder="e.g. Looking for a CA for GST filing" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
              </Field>
              <Field label="02 · Category">
                <select className="tgl-input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required>
                  <option value="">Select a category</option>
                  {CATEGORIES.map((c) => (
                    <option key={c.code} value={c.code}>{c.name}</option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="03 · Details" optional>
              <textarea className="tgl-input" rows={3} style={{ resize: 'vertical' }} placeholder="Add any context that will help another member respond…" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            {error && <div className="tgl-alert-error" role="alert" style={{ marginTop: 18 }}><span>{error}</span></div>}
            <button
              type="submit"
              className="tglp-gold"
              disabled={submitting}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginTop: 26, padding: '16px 28px', border: 'none', borderRadius: 999, background: 'linear-gradient(135deg,#E0B558,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
            >
              {submitting ? 'Posting…' : 'Post Need'}
              <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
            </button>
          </form>
        )}

        {loading ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)' }}>Loading needs…</p>
        ) : items.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--tgl-text-muted)', padding: 48 }}>No open needs right now. Be the first to post one.</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
            {items.map((n) => {
              const isOwn = n.poster_user_id === status?.user?.id;
              const done = helpedIds.has(n.id);
              const expanded = openId === n.id;
              return (
                <div key={n.id} className="tglp-lift" style={{ display: 'flex', flexDirection: 'column', padding: 26, border: '1px solid rgba(53,26,78,0.1)', borderRadius: 20, background: '#FFFCF5' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
                    <span style={{ padding: '6px 12px', borderRadius: 999, background: 'rgba(107,62,150,0.08)', fontSize: 10.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: '#6B3E96' }}>
                      {CATEGORY_MAP.get(n.category) || n.category}
                    </span>
                    <span style={{ fontSize: 12, color: 'rgba(43,23,64,0.45)' }}>{timeAgo(n.created_at)}</span>
                  </div>
                  <p style={{ margin: '0 0 10px', fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.25, color: '#2B1740' }}>{n.title}</p>
                  {expanded && n.description && (
                    <p style={{ margin: '0 0 14px', fontSize: 14, lineHeight: 1.6, color: 'rgba(43,23,64,0.72)' }}>{n.description}</p>
                  )}
                  <p style={{ margin: '0 0 24px', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'rgba(43,23,64,0.58)', flex: 1 }}>
                    {n.poster_name}
                    <span style={{ width: 3, height: 3, borderRadius: '50%', background: 'rgba(43,23,64,0.35)' }} />
                    <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-pin" /></svg>
                    {n.city || n.business_name}
                  </p>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      type="button"
                      className="tglp-ghost"
                      onClick={() => setOpenId(expanded ? null : n.id)}
                      style={{ flex: 1, padding: 12, border: '1px solid rgba(53,26,78,0.3)', borderRadius: 999, background: 'transparent', color: '#35194E', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap' }}
                    >
                      {expanded ? 'Hide Need' : 'View Need'}
                    </button>
                    <button
                      type="button"
                      className="tglp-gold"
                      disabled={isOwn || helpingId === n.id || done}
                      onClick={() => offerHelp(n.id)}
                      style={{ flex: 1, padding: 12, border: 'none', borderRadius: 999, background: isOwn || done ? 'rgba(53,26,78,0.1)' : 'linear-gradient(135deg,#E0B558,#C08D2E)', color: isOwn || done ? 'rgba(43,23,64,0.5)' : '#22103A', fontSize: 10.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', cursor: isOwn || done ? 'default' : 'pointer', whiteSpace: 'nowrap', boxShadow: isOwn || done ? 'none' : undefined }}
                    >
                      {isOwn ? 'Your Need' : done ? 'Offer Sent' : helpingId === n.id ? 'Sending…' : 'I Can Help'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}
