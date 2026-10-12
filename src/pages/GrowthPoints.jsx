import { useEffect, useState } from 'react';
import { api, go } from '../lib/customerApi';

// The member's Growth Points page. It always explains how points are earned; the member's own numbers appear only when the server says
// Growth Points are visible to them (the preview, or real redemption). Nothing here is computed on the client: it only shows the server's figures.
const ICONS = { send: 'i-send', phone: 'i-mail', calendar: 'i-calendar', briefcase: 'i-briefcase', repeat: 'i-network', user: 'i-user' };
const n = (v) => Number(v || 0).toLocaleString('en-IN');
const day = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '');
const KIND = { EARN: 'Earned', VOID: 'Cancelled', REVERSAL: 'Reversed', EXPIRY: 'Expired' };
const FEED_SHOWN = 6;

function Icon({ id, size = 18 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"><use href={`#${id}`} /></svg>;
}

function Ring({ percent, earned, ceiling }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="gpp-ring" role="img" aria-label={`${n(earned)} of ${n(ceiling)} points earned this subscription term (${percent} percent)`}>
      <svg viewBox="0 0 128 128" width="132" height="132" aria-hidden="true">
        <circle cx="64" cy="64" r={r} fill="none" stroke="rgba(255,255,255,0.13)" strokeWidth="6" />
        <circle cx="64" cy="64" r={r} fill="none" stroke="url(#gppGold)" strokeWidth="6" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c - (c * percent) / 100} transform="rotate(-90 64 64)" className="gpp-ring-arc" />
        <defs><linearGradient id="gppGold" x1="0" x2="1"><stop offset="0" stopColor="#F1D58A" /><stop offset="1" stopColor="#C08D2E" /></linearGradient></defs>
      </svg>
      <div className="gpp-ring-text"><span>{percent}%</span><small>of term limit</small></div>
    </div>
  );
}

function statusLabel(a) {
  if (a.kind !== 'EARN') return KIND[a.kind];
  if (a.status === 'PENDING') return 'Pending';
  if (a.status === 'CAPPED') return 'Limit reached';
  return 'Ready';
}

export default function GrowthPoints() {
  const [d, setD] = useState(undefined);
  const [error, setError] = useState('');
  const [all, setAll] = useState(false);
  useEffect(() => {
    let live = true;
    api.growthPointsOverview().then((r) => live && setD(r)).catch((e) => live && (setError(e.message || 'Could not load Growth Points.'), setD(null)));
    return () => { live = false; };
  }, []);

  if (d === undefined) return <main className="gpp"><p className="gpp-muted" style={{ padding: 40 }}>Loading your Growth Points…</p></main>;
  if (d === null) return <main className="gpp"><p role="alert" className="gpp-muted" style={{ padding: 40 }}>{error}</p></main>;

  const visible = d.visible;
  const b = d.balance;
  const cyc = d.cycle;
  const maxBar = Math.max(1, ...(d.earned_by_activity || []).map((a) => a.points));
  const feed = visible ? (all ? d.activity : d.activity.slice(0, FEED_SHOWN)) : [];
  const planLabel = cyc ? (cyc.plan === 'complimentary' ? 'Season 1 membership' : `${cyc.plan} plan`) : '';

  return (
    <main className="gpp">
      <button type="button" className="gpp-back" onClick={() => go('/app/networking')}><Icon id="i-back" size={14} /> Networking</button>

      <section className="gpp-hero" aria-label="Your Growth Points">
        <div className="gpp-hero-main">
          <p className="gpp-eyebrow">Growth Points</p>
          {visible ? (
            <>
              <h1 className="gpp-total">{n(b.total)}<small>points</small></h1>
              <p className="gpp-hero-sub">Rewards for the business your networking creates. Use them for up to {d.redemption.cap_percent}% off your renewal.</p>
              <dl className="gpp-trio">
                <div><dt>Ready to use</dt><dd>{n(b.available)}</dd></div>
                <div><dt>Pending</dt><dd>{n(b.pending)}</dd></div>
                <div><dt>Expiring in 30 days</dt><dd>{n(b.expiring_within_30_days)}</dd></div>
              </dl>
            </>
          ) : (
            <>
              <h1 className="gpp-total gpp-total--soon">Coming soon</h1>
              <p className="gpp-hero-sub">{d.message} Here is how Growth Points will work.</p>
            </>
          )}
        </div>
        {visible && cyc && (
          <div className="gpp-hero-side">
            <Ring percent={cyc.percent} earned={cyc.earned} ceiling={cyc.ceiling} />
            <p className="gpp-ring-note">{n(cyc.earned)} of {n(cyc.ceiling)} this term<span>{planLabel} · ends {day(cyc.ends_at)}</span></p>
          </div>
        )}
        {visible && d.preview_only && <p className="gpp-hero-foot"><i aria-hidden="true" />Preview: not active yet, so nothing here changes what you pay.</p>}
        {visible && !d.recording && <p className="gpp-hero-foot gpp-hero-foot--warn"><i aria-hidden="true" />Points are not being recorded right now, so new activity will not appear.</p>}
      </section>

      <div className="gpp-grid">
        <div className="gpp-col">
          {visible ? (
            <section className="gpp-card" aria-labelledby="gpp-activity">
              <header className="gpp-card-head"><h2 id="gpp-activity">Recent activity</h2>{d.activity.length > 0 && <span className="gpp-count">{d.activity.length} {d.activity.length === 1 ? 'entry' : 'entries'}</span>}</header>
              {d.activity.length === 0 ? (
                <div className="gpp-empty">
                  <p>Nothing earned yet. Your first points arrive when a referral you gave is accepted.</p>
                  <ol className="gpp-path">
                    <li><span><Icon id="i-send" /></span>Give a referral</li>
                    <li><span><Icon id="i-mail" /></span>It is accepted</li>
                    <li><span><Icon id="i-medal" /></span>Points arrive</li>
                  </ol>
                  <button type="button" className="gpp-btn gpp-btn--ghost" onClick={() => go('/app/networking/referrals')}>Give a referral <Icon id="i-arrow" size={14} /></button>
                </div>
              ) : (
                <>
                  <ul className="gpp-feed">
                    {feed.map((a, i) => (
                      <li key={i}>
                        <span className={`gpp-mark gpp-mark--${a.kind === 'EARN' ? 'earn' : 'out'}`} aria-hidden="true">{a.points >= 0 ? '+' : '−'}</span>
                        <div className="gpp-feed-body">
                          <p className="gpp-feed-title">{a.title}<span className={`gpp-chip gpp-chip--${(a.status || '').toLowerCase()}`}>{statusLabel(a)}</span></p>
                          <p className="gpp-muted">{day(a.date)}{a.status === 'PENDING' && a.usable_from ? ` · usable from ${day(a.usable_from)}` : ''}{a.expires_at && a.kind === 'EARN' && a.status !== 'CAPPED' ? ` · expires ${day(a.expires_at)}` : ''}</p>
                          {a.note && <p className="gpp-note">{a.note}</p>}
                        </div>
                        <span className={a.points >= 0 ? 'gpp-plus' : 'gpp-minus'}>{a.points >= 0 ? '+' : '−'}{n(Math.abs(a.points))}</span>
                      </li>
                    ))}
                  </ul>
                  {d.activity.length > FEED_SHOWN && <button type="button" className="gpp-more" onClick={() => setAll((v) => !v)}>{all ? 'Show less' : `Show all ${d.activity.length}`}</button>}
                </>
              )}
            </section>
          ) : (
            <section className="gpp-card" aria-labelledby="gpp-what">
              <header className="gpp-card-head"><h2 id="gpp-what">What are Growth Points?</h2></header>
              <p className="gpp-lead">Growth Points reward the real business your networking creates on TGL. You earn them when something verified happens, never for clicks or activity alone, and you can use them as a discount when you renew.</p>
            </section>
          )}

          <section className="gpp-card gpp-use" aria-labelledby="gpp-use">
            <div>
              <h2 id="gpp-use">Using your points</h2>
              <p className="gpp-lead">{d.redemption.explanation}</p>
              <p className="gpp-muted">{d.redemption.state === 'OPEN' ? 'Redemption is open for your account. Choose it when you renew.' : 'Redemption is not open yet. Your points stay safe in your record until it is.'}</p>
            </div>
            <button type="button" className="gpp-btn" onClick={() => go('/app/subscription')}>Subscription <Icon id="i-arrow" size={14} /></button>
          </section>
        </div>

        <aside className="gpp-col">
          <section className="gpp-card" aria-labelledby="gpp-earn">
            <header className="gpp-card-head"><h2 id="gpp-earn">How you earn</h2></header>
            <ul className="gpp-earn">
              {d.ways_to_earn.map((w) => (
                <li key={w.key}>
                  <details>
                    <summary>
                      <span className="gpp-icon"><Icon id={ICONS[w.icon] || 'i-medal'} size={16} /></span>
                      <span className="gpp-earn-text"><span className="gpp-earn-title">{w.title}</span><span className="gpp-pts">{w.points}</span></span>
                      <span className="gpp-chev" aria-hidden="true" />
                    </summary>
                    <p className="gpp-muted gpp-earn-detail">{w.detail}</p>
                  </details>
                </li>
              ))}
            </ul>
            <p className="gpp-not">No points for: {d.not_earning.join(', ').toLowerCase()}.</p>
          </section>

          {visible && d.earned_by_activity.length > 0 && (
            <section className="gpp-card" aria-labelledby="gpp-where">
              <header className="gpp-card-head"><h2 id="gpp-where">Where it came from</h2></header>
              <ul className="gpp-bars">
                {d.earned_by_activity.map((a) => (
                  <li key={a.key}>
                    <div className="gpp-bar-head"><span>{a.title}{a.times > 1 && <small> ×{a.times}</small>}</span><span className="gpp-bar-val">{n(a.points)}</span></div>
                    <div className="gpp-bar"><i style={{ width: `${Math.max(4, (a.points * 100) / maxBar)}%` }} /></div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="gpp-card" aria-labelledby="gpp-limits">
            <header className="gpp-card-head"><h2 id="gpp-limits">Limits and expiry</h2></header>
            <dl className="gpp-facts">
              <div><dt>Per day</dt><dd>{n(d.limits.daily)}</dd></div>
              <div><dt>Per month</dt><dd>{n(d.limits.monthly)}</dd></div>
              <div><dt>Per term</dt><dd>{cyc ? n(cyc.ceiling) : `${d.limits.per_cycle_percent_of_price}% of plan`}</dd></div>
              {visible && cyc && <div><dt>Renewal window</dt><dd>{day(cyc.renewal_opens_at)} – {day(cyc.grace_ends_at)}</dd></div>}
            </dl>
            <p className="gpp-muted">{d.limits.expiry}</p>
          </section>
        </aside>
      </div>
    </main>
  );
}
