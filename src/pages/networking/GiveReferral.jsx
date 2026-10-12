import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../../lib/customerApi';
import { CATEGORIES } from '../../data/categories';
import ImageSlot from '../../components/ImageSlot';
import MemberCombobox from './MemberCombobox';
import {
  CONTACT_METHODS, CONTACT_METHOD_LABEL, DESCRIPTION_MAX, DESCRIPTION_MIN, EMAIL_RE, INTRO_LABEL, INTRO_METHODS,
  PERMISSIONS, PERMISSION_LABEL, RELATIONSHIPS, RELATIONSHIP_LABEL, URGENCY, URGENCY_LABEL, VALUE_LABEL, VALUE_RANGES,
  checkPhone, formatPhone,
} from '../../lib/referralMeta';
import { shortDate } from '../../lib/format';

const STEPS = ['Recipient', 'Prospect', 'Opportunity', 'Introduction', 'Review'];
const CATEGORY_NAME = Object.fromEntries(CATEGORIES.map((c) => [c.code, c.name]));
// Which step owns which API field, to send a server-side rejection back to the right place.
const FIELD_STEP = {
  receiver_user_id: 0,
  prospect_name: 1, prospect_phone: 1, prospect_email: 1, prospect_company: 1, prospect_role: 1, prospect_location: 1,
  preferred_contact_method: 1, relationship: 1, relationship_other: 1,
  opportunity_description: 2, category: 2, urgency: 2, value_range: 2, note: 2,
  intro_method: 3, intro_call_preference: 3, contact_permission: 3, consent_confirmed: 3,
};

const EMPTY = {
  prospect_name: '', prospect_phone: '', prospect_email: '', prospect_company: '', prospect_role: '', prospect_location: '',
  preferred_contact_method: '', relationship: '', relationship_other: '',
  opportunity_description: '', category: '', urgency: 'UNSURE', value_range: 'UNKNOWN', note: '',
  intro_method: 'EMAIL', intro_call_preference: '', contact_permission: '', consent_confirmed: false,
};

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function validate(step, form, recipient) {
  const e = {};
  if (step === 0 && !recipient) e.recipient = 'Choose the TGL member who should receive this referral.';
  if (step === 1) {
    if (form.prospect_name.trim().length < 2 || !/\p{L}/u.test(form.prospect_name)) e.prospect_name = "Enter the contact person's full name.";
    const phone = checkPhone(form.prospect_phone);
    if (!phone.ok) e.prospect_phone = phone.error;
    if (form.prospect_email.trim() && !EMAIL_RE.test(form.prospect_email.trim())) e.prospect_email = 'Enter a valid email address, or leave it blank.';
    if (!form.relationship) e.relationship = 'Tell us how you know this person.';
  }
  if (step === 2) {
    const n = form.opportunity_description.trim().length;
    if (n < DESCRIPTION_MIN) e.opportunity_description = `Add a little more detail — at least ${DESCRIPTION_MIN} characters (${n} so far).`;
    if (n > DESCRIPTION_MAX) e.opportunity_description = `Please keep this under ${DESCRIPTION_MAX} characters.`;
  }
  if (step === 3) {
    if (!form.contact_permission) e.contact_permission = 'Tell the recipient whether they may contact the prospect.';
    if (!form.consent_confirmed) e.consent_confirmed = 'Please confirm before sharing these contact details.';
  }
  return e;
}

function Field({ label, optional, error, hint, htmlFor, children }) {
  const errId = `${htmlFor}-err`;
  return (
    <div className="rf-field">
      <label htmlFor={htmlFor}>{label}{optional && <em>Optional</em>}</label>
      {children}
      {hint && !error && <small className="rf-hint">{hint}</small>}
      {error && <small id={errId} className="rf-err" role="alert">{error}</small>}
    </div>
  );
}

function Text({ id, value, onChange, error, ...rest }) {
  return (
    <div className={`rf-input ${error ? 'is-error' : ''}`}>
      <input id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error || undefined} aria-describedby={error ? `${id}-err` : undefined} {...rest} />
    </div>
  );
}

function RecipientCard({ member, onChange, heading = 'Referral recipient' }) {
  return (
    <div className="rf-picked" aria-live="polite">
      <ImageSlot shape="circle" initial={member.name} src={member.photo_url} style={{ width: 44, height: 44 }} fontSize={16} />
      <span>
        <em className="rf-picked-k"><Icon id="i-check" size={12} /> {heading}</em>
        <strong>{member.name}</strong>
        <small>{member.business_name}</small>
        {(member.profession || member.category_name) && <small>{[member.profession, member.category_name].filter(Boolean).join(' · ')}</small>}
      </span>
      {onChange && <button type="button" onClick={onChange}>Change</button>}
    </div>
  );
}

function SummaryRow({ k, v }) {
  if (!v) return null;
  return <div><dt>{k}</dt><dd>{v}</dd></div>;
}

// The page content sits in a z-index:1 wrapper (AppShell), under the sticky site header. Rendering
// into the shell root instead lets the dialog cover the header like a real modal.
function inShell(node) {
  return createPortal(node, document.querySelector('.tgl-portal-root') || document.body);
}

export default function GiveReferral({ initialTarget, onClose, onViewReferral, onSent }) {
  const [step, setStep] = useState(initialTarget ? 1 : 0);
  const [recipient, setRecipient] = useState(
    initialTarget ? { user_id: initialTarget.user_id, name: initialTarget.founder_name || initialTarget.business_name, business_name: initialTarget.business_name, photo_url: initialTarget.photo_url || null } : null,
  );
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState(null); // { kind: 'error' | 'duplicate' | 'similar', ... }
  const [done, setDone] = useState(null);
  const dialog = useRef(null);
  const heading = useRef(null);
  const categoryTouched = useRef(false);
  const returnFocus = useRef(document.activeElement);
  const inFlight = useRef(false); // set synchronously, so a double-click can't send twice

  const set = (key) => (value) => {
    setForm((f) => ({ ...f, [key]: value }));
    if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }));
  };

  // Modal behaviour: lock scroll, Escape closes, Tab stays inside, focus returns on close.
  // Mounted once; the latest onClose/submitting are read through a ref so a parent
  // re-render never tears this down (and never yanks focus back to the trigger).
  const latest = useRef({ onClose, submitting });
  useEffect(() => { latest.current = { onClose, submitting }; });
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const trigger = returnFocus.current;
    const onKey = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && !latest.current.submitting) { latest.current.onClose(); return; }
      if (e.key !== 'Tab' || !dialog.current) return;
      const nodes = [...dialog.current.querySelectorAll('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter((n) => !n.disabled && n.offsetParent !== null);
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const here = document.activeElement;
      if (!dialog.current.contains(here)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && (here === first || here === heading.current)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && here === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      if (trigger && typeof trigger.focus === 'function') trigger.focus();
    };
  }, []);

  // On every step change, move focus to the step heading (or the first field) for screen readers and keyboards.
  useEffect(() => {
    const first = dialog.current?.querySelector('[data-autofocus]');
    (first || heading.current)?.focus();
    dialog.current?.scrollTo?.({ top: 0 });
  }, [step, done]);

  // A duplicate warning or error appears below the fold of a long review: bring it into view.
  useEffect(() => {
    if (problem) dialog.current?.querySelector('.rf-alert, .rf-error')?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [problem]);

  function pickRecipient(member) {
    setRecipient(member);
    setErrors((e) => ({ ...e, recipient: undefined }));
    if (!categoryTouched.current && member.category) setForm((f) => ({ ...f, category: member.category }));
  }

  function next() {
    const found = validate(step, form, recipient);
    setErrors(found);
    if (Object.keys(found).length) {
      requestAnimationFrame(() => dialog.current?.querySelector('[aria-invalid="true"], .rf-err')?.closest('.rf-field')?.querySelector('input, select, textarea, button')?.focus());
      return;
    }
    setProblem(null);
    setStep((s) => s + 1);
  }

  const payload = useMemo(() => {
    const blank = (v) => (typeof v === 'string' && !v.trim() ? null : typeof v === 'string' ? v.trim() : v);
    const phone = checkPhone(form.prospect_phone);
    return {
      receiver_user_id: recipient?.user_id,
      prospect_name: form.prospect_name.trim(),
      prospect_phone: phone.ok ? phone.value : form.prospect_phone,
      prospect_email: blank(form.prospect_email),
      prospect_company: blank(form.prospect_company),
      prospect_role: blank(form.prospect_role),
      prospect_location: blank(form.prospect_location),
      preferred_contact_method: blank(form.preferred_contact_method),
      relationship: form.relationship,
      relationship_other: form.relationship === 'OTHER' ? blank(form.relationship_other) : null,
      opportunity_description: form.opportunity_description.trim(),
      category: blank(form.category),
      urgency: form.urgency,
      value_range: form.value_range === 'UNKNOWN' ? null : form.value_range,
      intro_method: form.intro_method,
      intro_call_preference: form.intro_method === 'CALL' ? blank(form.intro_call_preference) : null,
      contact_permission: form.contact_permission,
      note: blank(form.note),
      consent_confirmed: form.consent_confirmed,
    };
  }, [form, recipient]);

  async function submit(confirmDuplicate = false) {
    if (inFlight.current) return;
    inFlight.current = true;
    setProblem(null);
    setSubmitting(true);
    try {
      const created = await api.createReferral({ ...payload, confirm_duplicate: confirmDuplicate });
      setDone(created);
      onSent?.(created);
    } catch (err) {
      const detail = err.payload?.detail;
      if (err.status === 409 && detail?.code === 'duplicate_referral') {
        setProblem({ kind: 'duplicate', message: detail.message, id: detail.existing_referral_id });
      } else if (err.status === 409 && detail?.code === 'possible_duplicate') {
        setProblem({ kind: 'similar', message: detail.message, matches: detail.matches || [] });
      } else if (err.status === 422 && Array.isArray(detail)) {
        const mapped = {};
        let target = 4;
        for (const d of detail) {
          const field = d.loc?.[1];
          if (field in FIELD_STEP) {
            mapped[field] = (d.msg || 'Please check this field.').replace(/^Value error, /, '');
            target = Math.min(target, FIELD_STEP[field]);
          }
        }
        setErrors(mapped);
        setProblem({ kind: 'error', message: 'Some details need another look.' });
        if (target < 4) setStep(target);
      } else {
        setProblem({ kind: 'error', message: err.message || 'Could not send the referral. Please try again.' });
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  const desc = form.opportunity_description.length;
  const stepLabel = `Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`;
  const category = form.category ? CATEGORY_NAME[form.category] : null;

  /* ------------------------------ success ------------------------------ */
  if (done) {
    const prospect = [done.prospect_name, done.prospect_company].filter(Boolean).join(' / ');
    return inShell(
      <div className="rf-backdrop">
        <div className="rf-modal rf-modal--wide" role="dialog" aria-modal="true" aria-labelledby="rf-title" ref={dialog}>
          <div className="rf-done">
            <span className="rf-done-icon"><Icon id="i-check" size={26} /></span>
            <h2 id="rf-title" tabIndex={-1} ref={heading}>Referral sent successfully</h2>
            <p>{done.receiver_name} has received your referral for {prospect}.</p>
            <dl className="rf-done-meta">
              <div><dt>Referral ID</dt><dd>{done.id.slice(0, 8).toUpperCase()}</dd></div>
              <div><dt>Status</dt><dd>Submitted</dd></div>
              <div><dt>Submitted</dt><dd>{shortDate(done.created_at)}</dd></div>
            </dl>
            <p className="rf-done-next"><strong>What happens next:</strong> {done.receiver_name?.split(' ')[0]} is notified now. You’ll get a notification when they accept it{done.intro_method === 'EMAIL' ? ', and you can send your introduction email in the meantime' : ''}.</p>
            <div className="rf-modal-foot rf-modal-foot--center">
              <button type="button" className="rf-btn" onClick={onClose} data-autofocus>Done</button>
              <button type="button" className="rf-btn rf-btn--primary" onClick={() => onViewReferral(done)}>View referral</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------ the steps ------------------------------ */
  return inShell(
    <div className="rf-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !submitting) onClose(); }}>
      <form className="rf-modal rf-modal--wide" role="dialog" aria-modal="true" aria-labelledby="rf-title" ref={dialog} noValidate onSubmit={(e) => { e.preventDefault(); if (step < 4) next(); else submit(false); }}>
        <header className="rf-modal-head">
          <div>
            <h2 id="rf-title" tabIndex={-1} ref={heading}>Give a referral</h2>
            <p>Introduce a business opportunity to a fellow TGL member.</p>
          </div>
          <button type="button" className="rf-x" onClick={onClose} aria-label="Close" disabled={submitting}><Icon id="i-x" size={16} /></button>
        </header>

        <ol className="rf-progress" aria-label="Progress">
          {STEPS.map((label, i) => (
            <li key={label} className={i < step ? 'done' : i === step ? 'now' : ''} aria-current={i === step ? 'step' : undefined}>
              <span>{i < step ? <Icon id="i-check" size={11} /> : i + 1}</span><b>{label}</b>
            </li>
          ))}
        </ol>
        <p className="rf-sr" role="status" aria-live="polite">{stepLabel}</p>

        {/* STEP 1 — recipient */}
        {step === 0 && (
          <div role="group" aria-labelledby="rf-s0">
            <h3 id="rf-s0" className="rf-step-h">Who should receive this referral?</h3>
            <p className="rf-step-p">Choose the TGL member whose product or service fits this opportunity. You’ll add the prospective customer next.</p>
            <div className="rf-field">
              <label htmlFor="rf-recipient">TGL member receiving this referral</label>
              {recipient ? (
                <RecipientCard member={recipient} onChange={() => setRecipient(null)} />
              ) : (
                <MemberCombobox id="rf-recipient" onSelect={pickRecipient} invalid={!!errors.recipient} describedBy={errors.recipient ? 'rf-recipient-err' : undefined} />
              )}
              {errors.recipient && <small id="rf-recipient-err" className="rf-err" role="alert">{errors.recipient}</small>}
            </div>
          </div>
        )}

        {/* STEP 2 — prospect */}
        {step === 1 && (
          <div role="group" aria-labelledby="rf-s1">
            <h3 id="rf-s1" className="rf-step-h" >Who is the business opportunity for?</h3>
            <p className="rf-callout">Tell us about the person or business that needs the product or service. <strong>This is the prospective customer, not the TGL member receiving the referral.</strong></p>
            {recipient && <RecipientCard member={recipient} heading="Referral recipient" />}
            <h4 className="rf-sub">Prospective customer</h4>
            <div className="rf-grid">
              <Field label="Contact person’s full name" htmlFor="rf-pname" error={errors.prospect_name}>
                <Text id="rf-pname" data-autofocus value={form.prospect_name} onChange={set('prospect_name')} error={errors.prospect_name} maxLength={120} autoComplete="off" placeholder="e.g. Priya Sharma" />
              </Field>
              <Field label="Mobile / phone number" htmlFor="rf-pphone" error={errors.prospect_phone} hint="Indian numbers work with or without +91. Other countries: start with +country code.">
                <Text id="rf-pphone" type="tel" inputMode="tel" value={form.prospect_phone} onChange={set('prospect_phone')} error={errors.prospect_phone} maxLength={25} autoComplete="off" placeholder="+91 98765 43210"
                  onBlur={() => { const p = checkPhone(form.prospect_phone); if (p.ok) setForm((f) => ({ ...f, prospect_phone: formatPhone(p.value) })); }} />
              </Field>
              <Field label="Email address" optional htmlFor="rf-pemail" error={errors.prospect_email}>
                <Text id="rf-pemail" type="email" inputMode="email" value={form.prospect_email} onChange={set('prospect_email')} error={errors.prospect_email} maxLength={255} autoComplete="off" placeholder="name@company.com" />
              </Field>
              <Field label="Company / business name" optional htmlFor="rf-pcompany">
                <Text id="rf-pcompany" value={form.prospect_company} onChange={set('prospect_company')} maxLength={160} autoComplete="off" placeholder="e.g. XYZ Restaurant" />
              </Field>
              <Field label="Job title / role" optional htmlFor="rf-prole">
                <Text id="rf-prole" value={form.prospect_role} onChange={set('prospect_role')} maxLength={120} autoComplete="off" placeholder="e.g. Owner" />
              </Field>
              <Field label="Location" optional htmlFor="rf-ploc">
                <Text id="rf-ploc" value={form.prospect_location} onChange={set('prospect_location')} maxLength={120} autoComplete="off" placeholder="e.g. Indiranagar, Bengaluru" />
              </Field>
              <Field label="Preferred contact method" optional htmlFor="rf-pmethod">
                <div className="rf-input"><select id="rf-pmethod" value={form.preferred_contact_method} onChange={(e) => set('preferred_contact_method')(e.target.value)}>
                  <option value="">No preference</option>
                  {CONTACT_METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></div>
              </Field>
              <Field label="How do you know this person?" htmlFor="rf-prel" error={errors.relationship}>
                <div className={`rf-input ${errors.relationship ? 'is-error' : ''}`}><select id="rf-prel" value={form.relationship} onChange={(e) => set('relationship')(e.target.value)} aria-invalid={!!errors.relationship || undefined} aria-describedby={errors.relationship ? 'rf-prel-err' : undefined}>
                  <option value="">Select…</option>
                  {RELATIONSHIPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></div>
              </Field>
            </div>
            {form.relationship === 'OTHER' && (
              <Field label="Tell us a little more" optional htmlFor="rf-prelo">
                <Text id="rf-prelo" value={form.relationship_other} onChange={set('relationship_other')} maxLength={120} autoComplete="off" placeholder="e.g. Met at a trade fair" />
              </Field>
            )}
            <p className="rf-hint rf-hint--lock"><Icon id="i-lock" size={13} /> Only the recipient and you can see these contact details. Please don’t add passwords, card, bank or ID numbers.</p>
          </div>
        )}

        {/* STEP 3 — opportunity */}
        {step === 2 && (
          <div role="group" aria-labelledby="rf-s2">
            <h3 id="rf-s2" className="rf-step-h">What is the opportunity?</h3>
            <Field label="What does this person/business need?" htmlFor="rf-desc" error={errors.opportunity_description}
              hint="Be specific: who needs what, by when, and why. “Needs website” is vague; “ABC Restaurant wants a responsive website with online table booking and WhatsApp integration before opening its second location next month” gives the recipient something to act on.">
              <textarea id="rf-desc" data-autofocus rows={5} maxLength={DESCRIPTION_MAX + 200} placeholder="Describe the problem, requirement, product or service they are looking for..."
                value={form.opportunity_description} onChange={(e) => set('opportunity_description')(e.target.value)}
                aria-invalid={!!errors.opportunity_description || undefined} aria-describedby={errors.opportunity_description ? 'rf-desc-err' : 'rf-desc-count'} className={errors.opportunity_description ? 'is-error' : ''} />
              <small id="rf-desc-count" className={`rf-counter ${desc > DESCRIPTION_MAX ? 'is-over' : desc >= DESCRIPTION_MIN ? 'is-ok' : ''}`}>{desc}/{DESCRIPTION_MAX}{desc < DESCRIPTION_MIN ? ` · minimum ${DESCRIPTION_MIN}` : ''}</small>
            </Field>
            <div className="rf-grid">
              <Field label="What type of opportunity is this?" optional htmlFor="rf-cat">
                <div className="rf-input"><select id="rf-cat" value={form.category} onChange={(e) => { categoryTouched.current = true; set('category')(e.target.value); }}>
                  <option value="">Not sure</option>
                  {CATEGORIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                </select></div>
              </Field>
              <Field label="Estimated opportunity value" optional htmlFor="rf-val">
                <div className="rf-input"><select id="rf-val" value={form.value_range} onChange={(e) => set('value_range')(e.target.value)}>
                  {VALUE_RANGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select></div>
              </Field>
            </div>
            <fieldset className="rf-field">
              <legend>How soon is this opportunity?</legend>
              <div className="rf-tiles">
                {URGENCY.map((u) => (
                  <label key={u.value} className={form.urgency === u.value ? 'is-on' : ''}>
                    <input type="radio" name="urgency" value={u.value} checked={form.urgency === u.value} onChange={() => set('urgency')(u.value)} />
                    <span className="rf-tile-t">{u.icon} {u.label}</span><small>{u.hint}</small>
                  </label>
                ))}
              </div>
            </fieldset>
            <Field label="Anything else the recipient should know?" optional htmlFor="rf-note" hint="Decision-maker, timing, previous conversations, constraints. No need to repeat what you’ve already entered.">
              <textarea id="rf-note" rows={3} maxLength={1000} value={form.note} onChange={(e) => set('note')(e.target.value)} />
            </Field>
          </div>
        )}

        {/* STEP 4 — introduction */}
        {step === 3 && (
          <div role="group" aria-labelledby="rf-s3">
            <h3 id="rf-s3" className="rf-step-h">How should the introduction happen?</h3>
            <fieldset className="rf-field">
              <legend>How will you introduce them?</legend>
              <div className="rf-choices">
                {INTRO_METHODS.map((m, i) => (
                  <label key={m.value} className={form.intro_method === m.value ? 'is-on' : ''}>
                    <input type="radio" name="intro" value={m.value} checked={form.intro_method === m.value} onChange={() => set('intro_method')(m.value)} data-autofocus={i === 0 || undefined} />
                    <span>{m.label}<small>{m.hint}</small></span>
                  </label>
                ))}
              </div>
            </fieldset>
            {form.intro_method === 'CALL' && (
              <Field label="Preferred date / time for the call" optional htmlFor="rf-call" hint="e.g. “Tuesday after 4 pm”. Adding a time records this as a meeting arranged.">
                <Text id="rf-call" value={form.intro_call_preference} onChange={set('intro_call_preference')} maxLength={120} autoComplete="off" />
              </Field>
            )}
            <fieldset className="rf-field">
              <legend>May the recipient contact this prospect?</legend>
              <div className="rf-choices" aria-describedby={errors.contact_permission ? 'rf-perm-err' : undefined}>
                {PERMISSIONS.map(([v, l]) => (
                  <label key={v} className={form.contact_permission === v ? 'is-on' : ''}>
                    <input type="radio" name="permission" value={v} checked={form.contact_permission === v} onChange={() => set('contact_permission')(v)} aria-invalid={!!errors.contact_permission || undefined} />
                    <span>{l}</span>
                  </label>
                ))}
              </div>
              {errors.contact_permission && <small id="rf-perm-err" className="rf-err" role="alert">{errors.contact_permission}</small>}
            </fieldset>
            <div className="rf-field">
              <label className={`rf-check ${errors.consent_confirmed ? 'is-error' : ''}`}>
                <input type="checkbox" checked={form.consent_confirmed} onChange={(e) => set('consent_confirmed')(e.target.checked)} aria-invalid={!!errors.consent_confirmed || undefined} aria-describedby={errors.consent_confirmed ? 'rf-consent-err' : undefined} />
                <span>I confirm I have a good reason to share these contact details with TGL and the selected member — for example, the prospect asked me for an introduction or expects to hear from them.</span>
              </label>
              {errors.consent_confirmed && <small id="rf-consent-err" className="rf-err" role="alert">{errors.consent_confirmed}</small>}
            </div>
          </div>
        )}

        {/* STEP 5 — review */}
        {step === 4 && (
          <div role="group" aria-labelledby="rf-s4">
            <h3 id="rf-s4" className="rf-step-h">Review your referral</h3>
            <p className="rf-step-p">Check the details below. Nothing is sent until you press “Send referral”.</p>
            <div className="rf-review">
              <div className="rf-rv-block">
                <h4>You are referring to <button type="button" className="rf-edit" onClick={() => setStep(0)}>Edit</button></h4>
                <RecipientCard member={recipient} heading="Referral recipient" />
              </div>
              <div className="rf-rv-block">
                <h4>Prospective customer <button type="button" className="rf-edit" onClick={() => setStep(1)}>Edit</button></h4>
                <dl>
                  <SummaryRow k="Contact" v={form.prospect_name.trim()} />
                  <SummaryRow k="Business" v={form.prospect_company.trim()} />
                  <SummaryRow k="Phone" v={formatPhone(checkPhone(form.prospect_phone).value)} />
                  <SummaryRow k="Email" v={form.prospect_email.trim()} />
                  <SummaryRow k="Role" v={form.prospect_role.trim()} />
                  <SummaryRow k="Location" v={form.prospect_location.trim()} />
                  <SummaryRow k="Prefers" v={CONTACT_METHOD_LABEL[form.preferred_contact_method]} />
                  <SummaryRow k="You know them as" v={form.relationship === 'OTHER' && form.relationship_other.trim() ? `Other — ${form.relationship_other.trim()}` : RELATIONSHIP_LABEL[form.relationship]} />
                </dl>
              </div>
              <div className="rf-rv-block">
                <h4>Opportunity <button type="button" className="rf-edit" onClick={() => setStep(2)}>Edit</button></h4>
                <p className="rf-rv-text">{form.opportunity_description.trim()}</p>
                <dl>
                  <SummaryRow k="Type" v={category} />
                  <SummaryRow k="Timing" v={URGENCY_LABEL[form.urgency]} />
                  <SummaryRow k="Value" v={form.value_range !== 'UNKNOWN' ? VALUE_LABEL[form.value_range] : null} />
                  <SummaryRow k="Notes" v={form.note.trim()} />
                </dl>
              </div>
              <div className="rf-rv-block">
                <h4>Introduction <button type="button" className="rf-edit" onClick={() => setStep(3)}>Edit</button></h4>
                <dl>
                  <SummaryRow k="Introduction" v={INTRO_LABEL[form.intro_method]} />
                  <SummaryRow k="Call time" v={form.intro_method === 'CALL' ? form.intro_call_preference.trim() : null} />
                  <SummaryRow k="Contact permission" v={PERMISSION_LABEL[form.contact_permission]} />
                </dl>
              </div>
            </div>

            {problem?.kind === 'similar' && (
              <div className="rf-alert" role="alert">
                <strong>This looks similar to an existing referral.</strong>
                <ul>
                  {problem.matches.map((m) => (
                    <li key={m.id}>
                      {[m.prospect_name, m.prospect_company].filter(Boolean).join(' / ')} → {m.receiver_name || 'a member'} · {m.status.toLowerCase().replace(/_/g, ' ')} · {shortDate(m.created_at)}{' '}
                      <button type="button" className="rf-link-btn" onClick={() => onViewReferral({ id: m.id })}>View</button>
                    </li>
                  ))}
                </ul>
                <div className="rf-alert-actions">
                  <button type="button" className="rf-btn" onClick={() => setProblem(null)}>Go back</button>
                  <button type="button" className="rf-btn rf-btn--dark" disabled={submitting} onClick={() => submit(true)}>{submitting ? 'Sending…' : 'This is different — send anyway'}</button>
                </div>
              </div>
            )}
            {problem?.kind === 'duplicate' && (
              <div className="rf-alert" role="alert">
                <strong>{problem.message}</strong>
                <div className="rf-alert-actions"><button type="button" className="rf-btn rf-btn--dark" onClick={() => onViewReferral({ id: problem.id })}>View existing referral</button></div>
              </div>
            )}
            {problem?.kind === 'error' && <p className="rf-error" role="alert">{problem.message}</p>}
          </div>
        )}

        <footer className="rf-modal-foot">
          {step > 0 ? (
            <button type="button" className="rf-btn" onClick={() => { setProblem(null); setStep(step - 1); }} disabled={submitting}>Back</button>
          ) : (
            <button type="button" className="rf-btn" onClick={onClose}>Cancel</button>
          )}
          {step < 4 ? (
            <button type="submit" className="rf-btn rf-btn--primary">Continue<Icon id="i-arrow" size={14} /></button>
          ) : (
            <button type="submit" className="rf-btn rf-btn--primary" disabled={submitting || problem?.kind === 'similar' || problem?.kind === 'duplicate'}>{submitting ? 'Sending…' : 'Send referral'}<Icon id="i-send" size={14} /></button>
          )}
        </footer>
      </form>
    </div>
  );
}
