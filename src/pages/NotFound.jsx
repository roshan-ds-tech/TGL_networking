import logo from '../assets/logo.png';

/* Any path that isn't the marketing page or a member-app route. The server
   sends this shell with a real 404 status (backend/app/main.py), so crawlers
   don't index it; this is what a person sees. */
export default function NotFound() {
  return (
    <main style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px 20px', background: '#F6EEDF', color: '#2B1740', textAlign: 'center' }}>
      <div style={{ maxWidth: 520 }}>
        <img src={logo} alt="The Growth League" style={{ height: 56, width: 'auto', marginBottom: 28 }} />
        <p style={{ margin: '0 0 10px', fontSize: 11, fontWeight: 700, letterSpacing: '.28em', textTransform: 'uppercase', color: '#8F6420' }}>Error 404</p>
        <h1 style={{ margin: '0 0 14px', fontSize: 'clamp(28px, 6vw, 44px)', fontWeight: 800, letterSpacing: '-0.03em', color: '#2B1740' }}>This page doesn&apos;t exist</h1>
        <p style={{ margin: '0 0 32px', fontSize: 16, lineHeight: 1.6, color: 'rgba(43,23,64,0.65)' }}>
          The link may be broken or the page may have moved.
        </p>
        <a
          href="/"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '16px 28px', borderRadius: 999, background: 'linear-gradient(135deg,#EFCB77,#E0B558 45%,#C08D2E)', color: '#22103A', fontSize: 12, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', textDecoration: 'none' }}
        >
          Back to The Growth League
        </a>
      </div>
    </main>
  );
}
