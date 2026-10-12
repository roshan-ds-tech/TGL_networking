import { useState } from 'react';
import { go } from '../lib/customerApi';

const FINALE = new Date('2026-12-05T00:00:00+05:30');
const DAY = 24 * 60 * 60 * 1000;
const CRITERIA = ['Business clarity', 'Growth journey', 'Innovation', 'Scalability'];

const fmt = (d, opts = { day: 'numeric', month: 'short', year: 'numeric' }) => new Date(d).toLocaleDateString(undefined, opts);

function Icon({ id, size = 16 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function Panel({ title, icon, children }) {
  return (
    <section className="ev-panel">
      <h2>{icon && <Icon id={icon} size={17} />}{title}</h2>
      {children}
    </section>
  );
}

export default function Events({ status }) {
  const [now] = useState(Date.now); // one clock per visit keeps render pure
  const reg = status.event_registration;
  const registered = !!reg || !!status.has_registration;
  const paid = reg?.payment_status === 'CONFIRMED' || !!status.registration_verified;
  const confirmed = reg?.status === 'CONFIRMED' || paid;
  const open = !!status.networking_access;
  const m = status.membership;
  const ev = status.event || {};
  const closes = ev.registration_closes_at ? new Date(ev.registration_closes_at) : new Date('2026-11-20T23:59:00+05:30');
  const regOpen = ev.registration_open !== false && now < closes.getTime();
  const finaleDone = open || !!ev.completed_at;
  const daysLeft = Math.ceil((FINALE.getTime() - now) / DAY);

  // Milestones. Only registration, payment, the Finale and networking are tracked
  // for an account; the production and evaluation steps are run by the TGL team, so
  // they follow the Finale instead of showing a made-up status.
  const steps = [
    { t: 'Registration', d: registered ? (confirmed ? 'Confirmed' : 'Submitted and in review') : 'Not started yet', done: registered, icon: 'i-clipboard' },
    { t: 'Payment', d: paid ? 'Confirmed. Your entry is secured.' : registered ? 'Awaiting confirmation' : 'Paid when you register', done: paid, icon: 'i-tag' },
    { t: 'Video & promotion', d: 'Share raw footage from the shoot guide; the TGL team edits your 30-second video for Instagram and YouTube.', done: finaleDone, icon: 'i-video' },
    { t: 'Evaluation & selection', d: 'Judged on business clarity, growth journey, innovation and scalability.', done: finaleDone, icon: 'i-target' },
    { t: 'Grand Finale', d: finaleDone ? 'Completed' : `${fmt(FINALE, { day: 'numeric', month: 'long', year: 'numeric' })} · on-site award show, Bengaluru`, done: finaleDone, icon: 'i-trophy' },
    { t: 'Networking membership', d: open ? `Active${m?.expires_at ? ` until ${fmt(m.expires_at)}` : ''}` : 'Opens after the Finale and runs for three months.', done: open, icon: 'i-network' },
  ];
  // After the Finale there is no "next step" left to point at.
  const nowIdx = finaleDone ? -1 : steps.findIndex((s) => !s.done);

  return (
    <main className="ev">
      <header className="ev-top">
        <p className="ev-kicker">TGL Events</p>
        <h1>Events</h1>
      </header>

      <section className="ev-hero tgl-dark-card" aria-labelledby="ev-hero-title">
        <div className="ev-hero-main">
          <p className="ev-eyebrow">Season 1 · Bengaluru</p>
          <h2 id="ev-hero-title">{ev.name || 'TGL Season 1'}</h2>
          <p className="ev-lede">A structured, quality-first programme for small businesses: evaluated on what you&apos;ve built, promoted with a professional video, and celebrated at an on-site award show.</p>
          <ul className="ev-facts">
            <li><Icon id="i-calendar" size={15} />{fmt(FINALE, { day: 'numeric', month: 'long', year: 'numeric' })}</li>
            <li><Icon id="i-pin" size={15} />Bengaluru</li>
            <li><Icon id="i-trophy" size={15} />On-site award show</li>
          </ul>
          <div className="ev-cta">
            {!registered && regOpen && (
              <a className="ev-btn ev-btn--gold" href="/#register-form">Register for Season 1 <Icon id="i-arrow" size={15} /></a>
            )}
            {!registered && !regOpen && <span className="ev-closed">Registration has closed</span>}
            {registered && <a className="ev-btn ev-btn--gold" href="/">Season 1 details <Icon id="i-arrow" size={15} /></a>}
            {open && <button type="button" className="ev-btn ev-btn--ghost" onClick={() => go('/app/networking')}>Open Networking</button>}
          </div>
        </div>

        <aside className="ev-hero-side" aria-label="Your status">
          {finaleDone ? (
            <div className="ev-count">
              <span className="ev-count-label">Grand Finale</span>
              <strong className="ev-count-done"><Icon id="i-check" size={26} /> Completed</strong>
              <span className="ev-count-sub">Thanks for being part of Season 1.</span>
            </div>
          ) : (
            <div className="ev-count">
              <span className="ev-count-label">Grand Finale in</span>
              <strong>{daysLeft > 0 ? daysLeft : 0}<small> {daysLeft === 1 ? 'day' : 'days'}</small></strong>
              <span className="ev-count-sub">{fmt(FINALE, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
            </div>
          )}
          <dl className="ev-mini">
            <div><dt>Registration</dt><dd className={registered ? 'ok' : ''}>{registered ? (confirmed ? 'Confirmed' : 'In review') : 'Not started'}</dd></div>
            <div><dt>Payment</dt><dd className={paid ? 'ok' : ''}>{paid ? 'Confirmed' : registered ? 'Awaiting' : '–'}</dd></div>
            <div><dt>Networking</dt><dd className={open ? 'ok' : ''}>{open ? 'Open' : 'After Finale'}</dd></div>
          </dl>
        </aside>
      </section>

      <div className="ev-grid">
        <Panel title="Your Season 1 journey" icon="i-compass">
          <ol className="ev-steps">
            {steps.map((s, i) => (
              <li key={s.t} className={s.done ? 'is-done' : i === nowIdx ? 'is-now' : ''} aria-current={i === nowIdx ? 'step' : undefined}>
                <span className="ev-dot" aria-hidden="true">{s.done ? <Icon id="i-check" size={14} /> : <Icon id={s.icon} size={14} />}</span>
                <div>
                  <h3>{s.t}{i === nowIdx && <em>You are here</em>}</h3>
                  <p>{s.d}</p>
                </div>
              </li>
            ))}
          </ol>
        </Panel>

        <div className="ev-side">
          <Panel title="Key dates" icon="i-calendar">
            <ul className="ev-dates">
              <li>
                <span className="ev-date"><b>{fmt(closes, { day: 'numeric' })}</b><i>{fmt(closes, { month: 'short' })}</i></span>
                <span><strong>Registration closes</strong><small>{regOpen ? `${Math.max(0, Math.ceil((closes.getTime() - now) / DAY))} days left` : 'Closed'}</small></span>
              </li>
              <li>
                <span className="ev-date"><b>{fmt(FINALE, { day: 'numeric' })}</b><i>{fmt(FINALE, { month: 'short' })}</i></span>
                <span><strong>Grand Finale</strong><small>On-site award show, Bengaluru</small></span>
              </li>
              <li>
                <span className="ev-date ev-date--plain"><b>3</b><i>mo</i></span>
                <span><strong>Networking membership</strong><small>Starts after the Finale</small></span>
              </li>
            </ul>
          </Panel>

          <Panel title="How entries are judged" icon="i-target">
            <ul className="ev-criteria">{CRITERIA.map((c) => <li key={c}><Icon id="i-check" size={13} />{c}</li>)}</ul>
            <p className="ev-note">Quality over popularity. Registration does not guarantee selection, and the judges&apos; decision is final.</p>
          </Panel>

          <Panel title="At the Grand Finale" icon="i-trophy">
            <p className="ev-note ev-note--flush">Selected winners get a 10-minute stage slot for business promotion or an investor pitch, in front of evaluators and the TGL community.</p>
          </Panel>

          <p className="ev-help">Questions about Season 1? <a href="/#faq">Read the FAQ</a> or <a href="/#contact">contact the team</a>.</p>
        </div>
      </div>
    </main>
  );
}
