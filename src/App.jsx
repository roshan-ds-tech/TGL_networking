import { useEffect, useRef, useState } from 'react';
import IconSprite from './components/IconSprite';
import UrgencyPopup from './components/UrgencyPopup';
import ModuleModal from './components/ModuleModal';
import SiteHeader from './components/SiteHeader';
import Hero from './sections/Hero';
import MarqueeBand from './sections/MarqueeBand';
import About from './sections/About';
import WhyTGL from './sections/WhyTGL';
import Eligibility from './sections/Eligibility';
import Categories from './sections/Categories';
import Evaluation from './sections/Evaluation';
import Benefits from './sections/Benefits';
import Journey from './sections/Journey';
import Finale from './sections/Finale';
import Register from './sections/Register';
import Faq from './sections/Faq';
import Contact from './sections/Contact';
import Sponsors from './sections/Sponsors';
import Footer from './sections/Footer';
import { submitRegistration } from './services/registrationService';
import useAvailability from './hooks/useAvailability';
import { api } from './lib/customerApi';

const REGISTRATION_CLOSE = new Date('2026-11-20T23:59:59');
const CATEGORY_TICKER_ITEMS = [
  'Fashion, Apparel & Textile',
  'Food, Bakery & Beverage',
  'Handmade, Craft & Artisan',
  'Jewellery & Accessories',
  'Home Decor & Lifestyle',
  'Kids Products & Toys',
  'Beauty, Care & Wellness',
  'Fitness, Sports & Health',
  'Professional & Digital Services',
  'Emerging & Innovative',
];

function daysLeft(closesAtMs) {
  return Math.ceil((closesAtMs - Date.now()) / 86400000);
}

/* Mirrors the server's phone rule (see schemas.RegistrationCreate._phone):
   strip the +91 country code or a trunk 0, then expect ten digits. Keeping the
   two in step matters because the user has already paid by the time they
   submit — a rule the browser accepts but the server rejects strands them. */
function normalisePhone(raw) {
  let digits = (raw || '').replace(/\D/g, '');
  if (digits.length === 12 && digits.startsWith('91')) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
  return digits;
}

function validate(fd, availability, authed) {
  const errors = {};
  const name = (fd.get('name') || '').trim();
  // Identity/business fields are hidden inputs pre-filled from the account's
  // saved (already-validated) profile when logged in — and the server
  // ignores whatever is submitted there anyway for an authenticated
  // request, re-deriving from the profile server-side. Nothing here can be
  // wrong, so skip re-validating it.
  if (!authed) {
    const business = (fd.get('business') || '').trim();
    const email = (fd.get('email') || '').trim();
    const phone = (fd.get('phone') || '').trim();
    // Length floors mirror the server's, so a one-character entry is caught here
    // instead of coming back as a 422 after the upload has already been sent.
    if (!name) errors.name = 'Please enter your full name.';
    else if (name.length < 2) errors.name = 'Please enter your full name.';
    if (!business) errors.business = 'Please enter your business name.';
    else if (business.length < 2) errors.business = 'Please enter your business name.';
    if (!email) errors.email = 'Please enter an email address.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) errors.email = 'Enter a valid email address.';
    if (!phone) errors.phone = 'Please enter a phone number.';
    else if (normalisePhone(phone).length !== 10) errors.phone = 'Enter a valid 10-digit mobile number.';
    const category = fd.get('category');
    if (!category) errors.category = 'Select a category.';
    else {
      // The dropdown already disables full categories, but its data is only
      // fetched once on page load — if a category filled up since then, catch
      // it here too rather than letting the upload happen for nothing. The
      // server enforces this for real; this is purely a faster "no" for the user.
      const stat = availability?.categories?.find((c) => c.category === category);
      if (stat && stat.filled >= stat.capacity) {
        errors.category = 'This category just filled up. Please choose another category.';
      }
    }
    const employees = fd.get('employees');
    if (!employees) errors.employees = 'Select your team size.';
    // Season 1 eligibility caps team size at 10. Say so here rather than letting
    // the server reject it, and don't quietly drop the option — a business with
    // 12 staff should learn it isn't eligible, not be nudged into picking "7-10".
    else if (employees === '10+') {
      errors.employees = 'TGL Season 1 is open to businesses with 10 or fewer employees.';
    }
    if (!fd.get('age')) errors.age = 'Select how long you have been operating.';
  }
  const paymentProof = fd.get('paymentProof');
  if (!paymentProof || !paymentProof.size) errors.paymentProof = 'Please upload a screenshot of your payment.';

  if (!fd.get('agree')) errors.agree = 'Please acknowledge the selection and refund terms.';
  if (!fd.get('mediaConsent')) errors.mediaConsent = 'Please grant permission to use your footage.';
  return { errors, name };
}

export default function App() {
  const [activeModule, setActiveModule] = useState(null);
  const [authStatus, setAuthStatus] = useState(null);
  // False until the session check below settles, so nav clicks made before
  // then aren't mistaken for "logged out".
  const [authChecked, setAuthChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // True while the sleeping backend is starting (see lib/apiBase.js).
  const [serverWaking, setServerWaking] = useState(false);
  useEffect(() => {
    const on = () => setServerWaking(true);
    const off = () => setServerWaking(false);
    window.addEventListener('tgl:backend-waking', on);
    window.addEventListener('tgl:backend-awake', off);
    return () => {
      window.removeEventListener('tgl:backend-waking', on);
      window.removeEventListener('tgl:backend-awake', off);
    };
  }, []);
  const [submitted, setSubmitted] = useState(false);
  const [submittedName, setSubmittedName] = useState('');
  const [errors, setErrors] = useState({});
  const [faq, setFaq] = useState({ 1: true, 2: false, 3: false, 4: false, 5: false, 6: false });

  // One request per page load, shared by the Categories grid and the popup.
  const [availability, refreshAvailability] = useAvailability();

  // The product app and this marketing site share one origin and one
  // customer session cookie, so a visitor who is already logged in should
  // see that reflected here too — instead of "Create Account" and nav links
  // that dump them into an OTP wall for an account they already verified.
  // The full status (not just identity) is fetched so the registration form
  // below can pre-fill and lock itself from the account's saved profile.
  useEffect(() => {
    let cancelled = false;
    api.optionalStatus()
      .then((s) => { if (!cancelled && s) setAuthStatus(s); })
      .catch(() => {}) // not logged in — keep the anonymous UI
      .finally(() => { if (!cancelled) setAuthChecked(true); });
    return () => { cancelled = true; };
  }, []);

  /* The deadline the whole page counts down to. The server owns it (it is what
     actually refuses late submissions), so use its value once the counters
     load and fall back to the constant above only if that request failed —
     otherwise changing the date on the backend would leave the countdown here
     still showing the old one. Kept as a timestamp so it can be a stable
     effect dependency. */
  const serverClose = availability?.registration_closes_at
    ? new Date(availability.registration_closes_at).getTime()
    : NaN;
  const closesAtMs = Number.isNaN(serverClose) ? REGISTRATION_CLOSE.getTime() : serverClose;

  const formRef = useRef(null);
  const progressRef = useRef(null);
  const headerRef = useRef(null);
  const tickerRef = useRef(null);
  const cdD = useRef(null);
  const cdH = useRef(null);
  const cdM = useRef(null);
  const cdS = useRef(null);

  // countdown clock
  useEffect(() => {
    const pad = (n) => (n < 10 ? '0' + n : String(n));
    const tick = () => {
      let ms = closesAtMs - Date.now();
      if (ms < 0) ms = 0;
      const s = Math.floor(ms / 1000);
      const set = (ref, v) => { if (ref.current && ref.current.textContent !== v) ref.current.textContent = v; };
      set(cdD, pad(Math.floor(s / 86400)));
      set(cdH, pad(Math.floor(s / 3600) % 24));
      set(cdM, pad(Math.floor(s / 60) % 60));
      set(cdS, pad(s % 60));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [closesAtMs]);

  // rotating category ticker
  useEffect(() => {
    let i = 0;
    const id = setInterval(() => {
      const el = tickerRef.current;
      if (!el) return;
      el.style.opacity = '0';
      el.style.transform = 'translateY(-6px)';
      setTimeout(() => {
        i = (i + 1) % CATEGORY_TICKER_ITEMS.length;
        el.textContent = CATEGORY_TICKER_ITEMS[i];
        el.style.transform = 'translateY(6px)';
        requestAnimationFrame(() => { el.style.opacity = '1'; el.style.transform = 'none'; });
      }, 400);
    }, 2800);
    return () => clearInterval(id);
  }, []);

  // scroll progress bar + header shadow
  useEffect(() => {
    let raf = null;
    const tick = () => {
      raf = null;
      const doc = document.documentElement;
      const max = (doc.scrollHeight - window.innerHeight) || 1;
      const p = Math.min(1, Math.max(0, window.scrollY / max));
      if (progressRef.current) progressRef.current.style.transform = 'scaleX(' + p + ')';
      if (headerRef.current) {
        const on = window.scrollY > 12;
        headerRef.current.style.boxShadow = on ? '0 10px 30px rgba(53,26,78,0.10)' : 'none';
        headerRef.current.style.background = on ? 'rgba(248,241,228,0.96)' : 'rgba(248,241,228,0.92)';
      }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(tick); };
    window.addEventListener('scroll', onScroll, { passive: true });
    tick();
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // animated stat counters
  useEffect(() => {
    const els = Array.prototype.slice.call(document.querySelectorAll('[data-count]'));
    if (!els.length) return;
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) return;
    const run = (el) => {
      const target = parseInt(el.getAttribute('data-count'), 10);
      if (!isFinite(target)) return;
      const dur = 1200;
      const t0 = performance.now();
      const step = (t) => {
        const k = Math.min(1, (t - t0) / dur);
        const eased = 1 - Math.pow(1 - k, 3);
        el.textContent = String(Math.round(target * eased));
        if (k < 1) requestAnimationFrame(step);
        else el.textContent = String(target);
      };
      requestAnimationFrame(step);
    };
    const timers = els.map((el) => setTimeout(() => run(el), 450));
    return () => timers.forEach(clearTimeout);
  }, []);

  // reveal-on-scroll
  useEffect(() => {
    const els = document.querySelectorAll('[data-reveal]');
    els.forEach((el) => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(22px)';
      el.style.transition = 'opacity .7s cubic-bezier(.2,.7,.3,1), transform .7s cubic-bezier(.2,.7,.3,1)';
    });
    let ioFired = false;
    const revealAll = () => {
      els.forEach((el) => { el.style.opacity = '1'; el.style.transform = 'none'; });
      io.disconnect();
    };
    const safety = setTimeout(() => { if (!ioFired) revealAll(); }, 1500);
    const onVis = () => { if (document.visibilityState === 'visible') return; revealAll(); };
    document.addEventListener('visibilitychange', onVis);

    const io = new IntersectionObserver((entries) => {
      ioFired = true;
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.style.opacity = '1';
          e.target.style.transform = 'none';
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });

    if (document.visibilityState !== 'visible') {
      revealAll();
    } else {
      els.forEach((el) => io.observe(el));
    }

    return () => {
      io.disconnect();
      clearTimeout(safety);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);


  const toggleFaq = (n) => setFaq((s) => ({ ...s, [n]: !s[n] }));

  const resetForm = () => {
    setSubmitted(false);
    setSubmittedName('');
    setErrors({});
  };

  const onSubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const { errors: fieldErrors, name } = validate(fd, availability, !!authStatus?.user);
    if (Object.keys(fieldErrors).length) {
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    try {
      // Post the FormData itself so the payment screenshot is included.
      await submitRegistration(fd);
      setSubmitted(true);
      setSubmittedName(name);
    } catch (err) {
      // Never show the success screen when the server rejected the submission.
      setErrors(
        Object.keys(err.fieldErrors || {}).length
          ? err.fieldErrors
          : { form: err.message || 'Something went wrong. Please try again.' },
      );
      // A rejection may mean a category just filled up — pull fresh counts so
      // the dropdown and the Categories section reflect it immediately,
      // instead of waiting for the next natural reload.
      refreshAvailability();
    } finally {
      setSubmitting(false);
    }
  };

  const days = daysLeft(closesAtMs);
  const daysLeftLabel = days > 0 ? days + ' days remaining' : 'Registration closed';
  // The server decides when registration is over; REGISTRATION_CLOSE is only
  // the fallback for when the counters could not be fetched, so the two can't
  // drift apart if the date is ever changed on the backend.
  /* Only trust registration_open when the API actually sent a boolean.
     An older backend omits the field entirely, and `!undefined` is `true` —
     which shut registration down on a site whose counters were otherwise
     loading fine. A missing field means "this backend can't tell us", so fall
     back to the date. Failing open is also the safe direction here: the server
     is what actually refuses late submissions, so the worst case is the form
     staying visible slightly too long, not registration disappearing while
     it is still meant to be running. */
  const registrationClosed =
    typeof availability?.registration_open === 'boolean'
      ? !availability.registration_open
      : days <= 0;

  return (
    <div className="tgl-shell" style={{ minHeight: '100vh', background: 'linear-gradient(180deg, #F6EEDF 0%, #FBF5E9 12%, #F7F0E2 34%, #FBF5E9 58%, #F6EEDF 78%, #F4EBDC 100%)' }}>
      <IconSprite />
      <SiteHeader path="/" headerRef={headerRef} progressRef={progressRef} onOpenModule={setActiveModule} authUser={authStatus?.user} authChecked={authChecked} unread={authStatus?.unread_notifications || 0} />
      {/* Landmark only — <main> is display:block by default, so this adds a
          semantic wrapper without introducing any box that affects layout.
          Header stays outside it so its position:sticky still resolves
          against the same ancestor it did before. */}
      <main>
        <Hero tickerRef={tickerRef} daysLeftLabel={daysLeftLabel} cdD={cdD} cdH={cdH} cdM={cdM} cdS={cdS} />
      <MarqueeBand />
      <About />
      <WhyTGL />
      <Eligibility />
      <Categories availability={availability} />
      <Evaluation />
      <Benefits />
      <Journey />
      <Finale />
      <Register
        formRef={formRef}
        onSubmit={onSubmit}
        authStatus={authStatus}
        showForm={!submitted}
        registrationClosed={registrationClosed}
        submitted={submitted}
        submittedName={submittedName || 'founder'}
        submitting={submitting}
        submitLabel={submitting ? (serverWaking ? 'Waking up the server…' : 'Submitting…') : 'Submit Registration'}
        availability={availability}
        errName={errors.name || ''}
        errBusiness={errors.business || ''}
        errEmail={errors.email || ''}
        errPhone={errors.phone || ''}
        errCategory={errors.category || ''}
        errEmployees={errors.employees || ''}
        errAge={errors.age || ''}
        errPaymentProof={errors.paymentProof || ''}
        errAgree={errors.agree || ''}
        errMediaConsent={errors.mediaConsent || ''}
        errForm={errors.form || ''}
        resetForm={resetForm}
      />
      <Faq faq={faq} toggleFaq={toggleFaq} />
      <Sponsors />
        <Contact />
      </main>
      <Footer onOpenModule={setActiveModule} authUser={authStatus?.user} authChecked={authChecked} />
      <UrgencyPopup availability={availability} deadline={new Date(closesAtMs)} />
      {activeModule && (
        <ModuleModal moduleKey={activeModule} onClose={() => setActiveModule(null)} />
      )}
    </div>
  );
}
