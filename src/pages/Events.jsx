const CELL_LABEL = { margin: '0 0 6px', fontSize: 10, letterSpacing: '.18em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.55)' };

function cell(label, value, gold) {
  return { label, value, gold };
}

export default function Events({ status }) {
  const reg = status.event_registration;
  const registered = !!reg || !!status.has_registration;
  const paid = reg?.payment_status === 'CONFIRMED' || !!status.registration_verified;
  const confirmed = reg?.status === 'CONFIRMED' || paid;
  const m = status.membership;
  const networkingOpen = !!status.networking_access;

  const cells = [
    cell('Grand Finale', networkingOpen ? 'Completed' : '5 Dec 2026', networkingOpen),
    cell('Registration', registered ? (confirmed ? 'Confirmed' : 'In review') : 'Not started', registered),
    cell('Payment', registered ? (paid ? 'Confirmed' : 'Awaiting') : '—', paid),
    cell('Networking', networkingOpen ? 'Open' : 'After Finale', networkingOpen),
  ];

  return (
    <main style={{ maxWidth: 1240, margin: '0 auto', padding: '48px 28px 96px' }}>
      <p style={{ margin: '0 0 8px', fontSize: 10.5, fontWeight: 700, letterSpacing: '.26em', textTransform: 'uppercase', color: '#8F6420' }}>TGL Events</p>
      <h1 style={{ margin: '0 0 30px', fontSize: 'clamp(30px,3.4vw,44px)', fontWeight: 800, letterSpacing: '-0.035em', color: '#2B1740' }}>My registrations</h1>

      <div className="tglp-framed" style={{ maxWidth: 760 }}>
        <div className="tgl-dark-card" style={{ padding: 34, borderRadius: 22, boxShadow: '0 30px 60px rgba(34,16,58,0.28)' }}>
          <p style={{ margin: '0 0 8px', fontSize: 10.5, letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: 700 }}>Season 1 · Bengaluru</p>
          <h2 style={{ margin: '0 0 26px', fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em', color: '#FFFBF3' }}>
            {status.event?.name || 'The Growth League — Season 1'}
          </h2>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 1, background: 'rgba(224,181,88,0.25)', borderRadius: 14, overflow: 'hidden', marginBottom: 26 }}>
            {cells.map((c) => (
              <div key={c.label} style={{ padding: 16, background: '#2A1542' }}>
                <p style={CELL_LABEL}>{c.label}</p>
                <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: c.gold ? '#EFCB77' : '#FFFBF3' }}>{c.value}</p>
              </div>
            ))}
          </div>

          {registered ? (
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6, color: 'rgba(246,238,223,0.72)' }}>
              {networkingOpen ? (
                <>
                  The Grand Finale is complete and your Networking membership is <strong style={{ color: '#FFFBF3' }}>active</strong>
                  {m?.expires_at ? ` until ${new Date(m.expires_at).toLocaleDateString()}` : ''}.
                </>
              ) : (
                <>
                  Your Season 1 entry is <strong style={{ color: '#FFFBF3' }}>{(reg?.status || 'registered').toLowerCase()}</strong>. Networking membership activates after the Grand Finale and runs for three months.
                </>
              )}
            </p>
          ) : (
            <>
              <p style={{ margin: '0 0 20px', fontSize: 13.5, lineHeight: 1.6, color: 'rgba(246,238,223,0.72)' }}>
                You haven&apos;t registered for Season 1 yet. Registration and payment happen on the main site — your name and business details are already filled in from your account.
              </p>
              <a
                href="/#register-form"
                className="tglp-gold"
                style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '15px 24px', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}
              >
                Register for Season 1
                <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
              </a>
            </>
          )}

          {registered && (
            <a
              href="/"
              className="tglp-gold"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginTop: 22, padding: '15px 24px', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 11.5, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase' }}
            >
              Season 1 details
              <svg width="15" height="15" viewBox="0 0 24 24"><use href="#i-arrow" /></svg>
            </a>
          )}
        </div>
      </div>

      <p style={{ margin: '40px 0 0', fontSize: 13, color: 'rgba(43,23,64,0.65)' }}>
        Full Events listing, Season 1 detail and the in-app registration flow are still to come.
      </p>
    </main>
  );
}
