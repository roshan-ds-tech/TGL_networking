import { useEffect, useState } from 'react';
import IconSprite from './IconSprite';
import ModuleModal from './ModuleModal';
import SiteHeader from './SiteHeader';
import { api } from '../lib/customerApi';

/* -------------------------------------------------------------------------
   Toast — a tiny global registry rather than React context, matching this
   codebase's existing preference for lightweight state over prop-drilling.
   Safe against navigation races because AppShell itself never unmounts
   between product-app page changes (only its children swap) — see
   ProductApp.jsx, which renders one AppShell for every route.
   ------------------------------------------------------------------------- */

let _toastListener = null;
export function showToast(msg) {
  if (_toastListener) _toastListener(msg);
}

function ToastHost() {
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    let timer;
    _toastListener = (m) => {
      setMsg(m);
      clearTimeout(timer);
      timer = setTimeout(() => setMsg(null), 2800);
    };
    return () => {
      _toastListener = null;
      clearTimeout(timer);
    };
  }, []);

  if (!msg) return null;
  return (
    <div className="tgl-toast" role="status">
      <span style={{ width: 24, height: 24, borderRadius: '50%', background: '#E0B558', color: '#22103A', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width="13" height="13" viewBox="0 0 24 24"><use href="#i-check" /></svg>
      </span>
      {msg}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Modals (Enquiry, Connect) — same registry pattern as the toast.
   ------------------------------------------------------------------------- */

let _modalListener = null;
export function openEnquiryModal(targetName) {
  if (_modalListener) _modalListener({ type: 'enquiry', target: targetName });
}
export function openConnectModal(targetName, targetUserId) {
  if (_modalListener) _modalListener({ type: 'connect', target: targetName, targetUserId });
}

function ModalHost() {
  const [modal, setModal] = useState(null);
  const [sent, setSent] = useState(false);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    _modalListener = (m) => {
      setModal(m);
      setSent(false);
      setNote('');
      setError('');
    };
    return () => {
      _modalListener = null;
    };
  }, []);

  if (!modal) return null;

  function close() {
    setModal(null);
  }

  async function confirmConnect() {
    setSubmitting(true);
    setError('');
    try {
      await api.createConnection({ target_user_id: modal.targetUserId, note: note || null });
      close();
      showToast(`Connection request sent to ${modal.target}.`);
    } catch (err) {
      setError(err.message || 'Could not send the request.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="tgl-modal-overlay"
      onClick={close}
      role="dialog"
      aria-modal="true"
    >
      <div className="tgl-modal-card" style={{ maxWidth: modal.type === 'connect' ? 460 : 500 }} onClick={(e) => e.stopPropagation()}>
        {modal.type === 'enquiry' && (
          sent ? (
            <>
              <span style={{ width: 56, height: 56, borderRadius: '50%', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', color: '#22103A', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 20 }}>
                <svg width="24" height="24" viewBox="0 0 24 24"><use href="#i-check" /></svg>
              </span>
              <h3 style={{ margin: '0 0 10px', fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Enquiry sent</h3>
              <p style={{ margin: '0 0 26px', fontSize: 15, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
                {modal.target} will reply to you directly. You&apos;ll get a notification when they respond.
              </p>
              <Button variant="ghost" onClick={close}>Done</Button>
            </>
          ) : (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, marginBottom: 22 }}>
                <div>
                  <p style={{ margin: '0 0 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Enquiry to</p>
                  <h3 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>{modal.target}</h3>
                </div>
                <CloseBtn onClick={close} />
              </div>
              <Field label="What do you need help with?">
                <textarea className="tgl-input" rows={4} style={{ resize: 'vertical' }} placeholder="Describe the project briefly." value={note} onChange={(e) => setNote(e.target.value)} />
              </Field>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, margin: '12px 0 24px' }}>
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
              <Button
                style={{ width: '100%' }}
                onClick={() => {
                  setSent(true);
                  showToast(`Enquiry sent to ${modal.target}.`);
                }}
              >
                Submit Enquiry
              </Button>
            </>
          )
        )}

        {modal.type === 'connect' && (
          <>
            <p style={{ margin: '0 0 6px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>Connect</p>
            <h3 style={{ margin: '0 0 18px', fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#2B1740' }}>Send a request to {modal.target}</h3>
            <Field label="Add a note" optional>
              <textarea className="tgl-input" rows={3} style={{ resize: 'vertical' }} placeholder="Why you'd like to connect." value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
            {error && (
              <div className="tgl-alert-error" role="alert" style={{ marginTop: 14 }}>
                <span>{error}</span>
              </div>
            )}
            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              <Button variant="ghost" onClick={close}>Cancel</Button>
              <Button style={{ flex: 1 }} disabled={submitting} onClick={confirmConnect}>
                {submitting ? 'Sending…' : 'Send Request'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CloseBtn({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Close"
      style={{ width: 36, height: 36, borderRadius: '50%', border: '1px solid rgba(53,26,78,0.14)', background: 'transparent', color: '#2B1740', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24"><use href="#i-x" /></svg>
    </button>
  );
}

/* -------------------------------------------------------------------------
   Shared primitives (used across every product-app page)
   ------------------------------------------------------------------------- */

export function Card({ children, className = '', style = {}, interactive = false, onClick }) {
  return (
    <section className={`tgl-portal-card ${interactive ? 'tgl-portal-card-interactive' : ''} ${className}`} style={style} onClick={onClick}>
      {children}
    </section>
  );
}

export function Button({ children, variant = 'primary', className = '', ...props }) {
  const cls = variant === 'ghost' ? `tgl-btn-ghost ${className}` : `tgl-btn-gold ${className}`;
  return (
    <button {...props} className={cls}>
      {children}
    </button>
  );
}

export function Field({ label, optional = false, error = '', children, className = '' }) {
  return (
    <label className={`tgl-field ${className}`}>
      <span className="tgl-label">
        {label}
        {optional && <span className="tgl-label-optional">(optional)</span>}
      </span>
      {children}
      {error && <span role="alert" className="tgl-field-error">{error}</span>}
    </label>
  );
}

export function Eyebrow({ children, center = false }) {
  return (
    <div className={`tgl-eyebrow ${center ? 'tgl-eyebrow--center' : ''}`}>
      <span className="tgl-eyebrow-line" />
      <span className="tgl-eyebrow-dot" />
      <span className="tgl-eyebrow-text">{children}</span>
    </div>
  );
}

export function HeroMeta() {
  return (
    <div className="tgl-hero-meta">
      <div>
        <p className="tgl-hero-meta-label">Grand Finale</p>
        <p className="tgl-hero-meta-value">5 December 2026</p>
        <p className="tgl-hero-meta-sub">On-site award show</p>
      </div>
      <div>
        <p className="tgl-hero-meta-label">Registration closes</p>
        <p className="tgl-hero-meta-value">20 November 2026</p>
        <p className="tgl-hero-meta-sub">Season 1 · Bengaluru</p>
      </div>
    </div>
  );
}

export function Stepper({ steps, currentStep }) {
  return (
    <div className="tgl-stepper" aria-label="Progress">
      {steps.map((label, i) => {
        const num = i + 1;
        const isCompleted = currentStep > num;
        const isActive = currentStep === num;
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className={`tgl-step-item ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}>
              <div className="tgl-step-dot">{isCompleted ? '✓' : num}</div>
              <span className="tgl-step-title">{label}</span>
            </div>
            {i < steps.length - 1 && <div className={`tgl-step-line ${currentStep > num ? 'completed' : ''}`} />}
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------
   Root shell — mounted once by ProductApp for every route; only its
   children swap on navigation, which is what keeps the toast/modal state
   in ModalHost/ToastHost stable across page changes. The header is the same
   SiteHeader the homepage uses, so the navbar never changes between them.
   ------------------------------------------------------------------------- */

export default function AppShell({ path, status, authChecked, children }) {
  const [activeModule, setActiveModule] = useState(null);
  return (
    <div className="tgl-portal-root">
      <IconSprite />
      <SiteHeader
        path={path}
        authUser={status?.user}
        authChecked={authChecked}
        unread={status?.unread_notifications || 0}
        onOpenModule={setActiveModule}
      />
      <div style={{ position: 'relative', zIndex: 1 }}>{children}</div>
      <ToastHost />
      <ModalHost />
      {activeModule && <ModuleModal moduleKey={activeModule} onClose={() => setActiveModule(null)} />}
    </div>
  );
}
