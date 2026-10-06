import { useEffect, useMemo, useRef, useState } from 'react';
import { api, go, loginUrl } from './lib/customerApi';
import AppShell, { Button, Card } from './components/AppShell';
import logo from './assets/logo.png';

import Login from './pages/auth/Login';
import Signup from './pages/auth/Signup';
import ForgotPassword from './pages/auth/ForgotPassword';
import ResetPassword from './pages/auth/ResetPassword';
import VerifyEmail from './pages/auth/VerifyEmail';
import Personal from './pages/onboarding/Personal';
import Business from './pages/onboarding/Business';
import VertexHome from './pages/vertex/Home';
import VertexSearch from './pages/vertex/Search';
import VertexProvider from './pages/vertex/Provider';
import Subscription from './pages/networking/Subscription';
import NetworkingLocked from './pages/networking/Locked';
import NetworkingHome from './pages/networking/Home';
import Directory from './pages/networking/Directory';
import Member from './pages/networking/Member';
import Referrals from './pages/networking/Referrals';
import Needs from './pages/networking/Needs';
import ProfilePage from './pages/profile/Profile';
import Membership from './pages/profile/Membership';
import Verification from './pages/profile/Verification';
import Notifications from './pages/Notifications';
import Events from './pages/Events';

const PRE_AUTH_ROUTES = {
  '/login': () => <Login />,
  '/signup': () => <Signup />,
  '/forgot-password': () => <ForgotPassword />,
  '/reset-password': () => <ResetPassword />,
};

// Pages that work without a session. '/verify-email' is auth-required but
// self-contained (calls api.me() itself and manages its own no-session
// redirect), so it is listed here too: the shared guard must not redirect it.
const UNGUARDED_PATHS = new Set(['/login', '/signup', '/forgot-password', '/reset-password', '/verify-email']);

/* Account status, shared by the header (signed-in icons, unread dot) and the
   guarded pages. Refetched on every route change so the header is right on
   every screen — including /login and /signup, where a stale "signed in"
   would show the wrong controls — and so the unread count stays fresh. Only
   the first load of a guarded page shows the full-screen loader; later ones
   refresh in place. */
const STATUS_FRESH_MS = 5000;

function useStatus(path) {
  const guarded = !UNGUARDED_PATHS.has(path);
  const [status, setStatus] = useState(null);
  const [checked, setChecked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const seq = useRef(0);
  const statusRef = useRef(null);
  const fetchedAt = useRef(0);
  statusRef.current = status;

  const load = async (silent) => {
    const id = ++seq.current; // only the latest request may write state
    const guardedNow = !UNGUARDED_PATHS.has(window.location.pathname);
    if (!silent) setLoading(true);
    setError('');
    try {
      // Signed-out visitors on /login, /signup… are expected: ask the
      // always-200 session probe there instead of eating a 401.
      // Already known to be signed in (e.g. reload() right after verifying
      // the email on /verify-email): one request, not the session probe first.
      const next = guardedNow || statusRef.current ? await api.status() : await api.optionalStatus();
      if (id === seq.current) {
        setStatus(next);
        fetchedAt.current = Date.now();
      }
    } catch (err) {
      if (id !== seq.current) return;
      if (err.status === 401) {
        setStatus(null);
        // No session on a protected page: sign in, then straight back here.
        // replace, so Back doesn't return to a page that bounces again.
        if (guardedNow) go(loginUrl(window.location.pathname + window.location.search), { replace: true });
      } else if (guardedNow) {
        setError(err.message || 'Could not load account status.');
      }
    } finally {
      if (id === seq.current) {
        setLoading(false);
        setChecked(true);
      }
    }
  };

  useEffect(() => {
    // A save that navigates (onboarding steps, profile edits) has just called
    // reload(); fetching the same account status again for the next page is a
    // wasted round trip. Reuse it if it is only seconds old.
    // Only between signed-in pages: /login etc. always re-check (e.g. after logout).
    if (guarded && statusRef.current && Date.now() - fetchedAt.current < STATUS_FRESH_MS) return;
    load(!(guarded && !statusRef.current));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  // Silent: refreshes in place after an onboarding save or notification read.
  return { status, checked, loading, error, reload: () => load(true) };
}

function Redirect({ to }) {
  useEffect(() => {
    go(to, { replace: true });
  }, [to]);
  return null;
}

function AuthedProduct({ path, status, loading, error, reload }) {
  const memberId = useMemo(() => path.match(/^\/app\/networking\/members\/(.+)$/)?.[1], [path]);
  const providerId = useMemo(() => path.match(/^\/app\/vertex\/provider\/(.+)$/)?.[1], [path]);

  if (loading) {
    return (
      <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <img src={logo} alt="The Growth League" style={{ height: 48, width: 'auto', marginBottom: 16 }} />
          <p style={{ color: '#8F6420', fontSize: 15, fontWeight: 700 }}>Loading member portal…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
        <Card style={{ maxWidth: 440, textAlign: 'center' }}>
          <h2 style={{ color: '#9A2B2B', marginTop: 0 }}>Portal Access Issue</h2>
          <p style={{ color: 'var(--tgl-text-muted)', fontSize: 14 }}>{error}</p>
          <Button onClick={() => go('/login')}>Go to Login</Button>
        </Card>
      </div>
    );
  }

  if (!status) return null;

  /* Onboarding gate. Each step has its own URL (so the header shows the right
     "Step n of 4" and Back works); anything past the first incomplete step
     redirects to it. Earlier, completed steps stay reachable for edits. */
  const pendingStep = !status.user?.email_verified_at
    ? '/verify-email'
    : !status.personal_profile
      ? '/onboarding/personal'
      : !status.business
        ? '/onboarding/business'
        : null;

  if (path === '/onboarding/personal') {
    if (pendingStep === '/verify-email') return <Redirect to={pendingStep} />;
    return <Personal initial={status.personal_profile} photoUrl={status.user?.photo_url} reload={reload} />;
  }
  if (path === '/onboarding/business') {
    if (pendingStep && pendingStep !== path) return <Redirect to={pendingStep} />;
    return <Business initial={status.business} reload={reload} />;
  }
  if (pendingStep) return <Redirect to={pendingStep} />;
  if (path.startsWith('/onboarding')) return <Redirect to="/app/vertex" />;

  const active = !!status.networking_access;
  // Registered but Networking not open yet → waiting for the Finale; anyone
  // else is offered a subscription.
  const locked = status.has_registration ? <NetworkingLocked status={status} /> : <Subscription />;

  if (path === '/app/vertex') return <VertexHome />;
  if (path === '/app/vertex/search') return <VertexSearch />;
  if (providerId) return <VertexProvider id={providerId} />;
  if (path === '/app/events') return <Events status={status} />;
  if (path === '/app/networking') return active ? <NetworkingHome status={status} /> : locked;
  if (path === '/app/networking/members') return active ? <Directory /> : locked;
  if (memberId) return active ? <Member id={memberId} /> : locked;
  if (path === '/app/referrals/new') return active ? <Referrals status={status} openGiveOnMount /> : locked;
  if (path === '/app/networking/referrals' || path === '/app/referrals') return active ? <Referrals status={status} /> : locked;
  if (path === '/app/networking/needs' || path === '/app/needs') return active ? <Needs status={status} /> : locked;
  if (path === '/app/notifications') return <Notifications reload={reload} />;
  if (path === '/app/profile/membership') return <Membership status={status} />;
  if (path === '/app/profile/verification') return <Verification status={status} reload={reload} />;
  if (path === '/app/profile') return <ProfilePage status={status} reload={reload} />;

  /* Vertex is the product's landing surface — a signed-in member with nothing
     specific in mind lands on "what business solution do you need?", not on a
     dashboard. /app and anything unmatched under it resolve there, with the
     URL corrected so the nav highlights Vertex. */
  return <Redirect to="/app/vertex" />;
}

export default function ProductApp() {
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const { status, checked, loading, error, reload } = useStatus(path);

  let content;
  if (PRE_AUTH_ROUTES[path]) {
    content = PRE_AUTH_ROUTES[path]();
  } else if (path === '/verify-email') {
    content = <VerifyEmail reload={reload} />;
  } else {
    content = <AuthedProduct path={path} status={status} loading={loading} error={error} reload={reload} />;
  }

  return (
    <AppShell path={path} status={status} authChecked={checked}>
      {content}
    </AppShell>
  );
}
