import { useEffect, useRef, useState } from 'react';
import IconSprite from './components/IconSprite';
import Header from './sections/Header';
import Hero from './sections/Hero';
import MarqueeBand from './sections/MarqueeBand';
import About from './sections/About';
import Positioning from './sections/Positioning';
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
import Footer from './sections/Footer';
import { submitRegistration } from './services/registrationService';

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

function daysLeft() {
  return Math.ceil((REGISTRATION_CLOSE - new Date()) / 86400000);
}

function validate(fd) {
  const errors = {};
  const name = (fd.get('name') || '').trim();
  const business = (fd.get('business') || '').trim();
  const email = (fd.get('email') || '').trim();
  const phone = (fd.get('phone') || '').trim();
  if (!name) errors.name = 'Please enter your full name.';
  if (!business) errors.business = 'Please enter your business name.';
  if (!email) errors.email = 'Please enter an email address.';
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) errors.email = 'Enter a valid email address.';
  if (!phone) errors.phone = 'Please enter a phone number.';
  else if (phone.replace(/\D/g, '').length < 10) errors.phone = 'Enter a valid 10-digit number.';
  if (!fd.get('category')) errors.category = 'Select a category.';
  if (!fd.get('employees')) errors.employees = 'Select your team size.';
  if (!fd.get('age')) errors.age = 'Select how long you have been operating.';
  const paymentProof = fd.get('paymentProof');
  if (!paymentProof || !paymentProof.size) errors.paymentProof = 'Please upload a screenshot of your payment.';
  if (!fd.get('agree')) errors.agree = 'Please acknowledge the selection and refund terms.';
  return { errors, name };
}

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submittedName, setSubmittedName] = useState('');
  const [errors, setErrors] = useState({});
  const [faq, setFaq] = useState({ 1: true, 2: false, 3: false, 4: false, 5: false, 6: false });

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
      let ms = REGISTRATION_CLOSE - new Date();
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
  }, []);

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

  const toggleMenu = () => setMenuOpen((v) => !v);
  const closeMenu = () => setMenuOpen(false);

  const toggleFaq = (n) => setFaq((s) => ({ ...s, [n]: !s[n] }));

  const resetForm = () => {
    setSubmitted(false);
    setSubmittedName('');
    setErrors({});
  };

  const onSubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const { errors: fieldErrors, name } = validate(fd);
    if (Object.keys(fieldErrors).length) {
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    await submitRegistration(Object.fromEntries(fd.entries()));
    setSubmitting(false);
    setSubmitted(true);
    setSubmittedName(name);
  };

  const days = daysLeft();
  const daysLeftLabel = days > 0 ? days + ' days remaining' : 'Registration closed';

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(180deg, #F6EEDF 0%, #FBF5E9 12%, #F7F0E2 34%, #FBF5E9 58%, #F6EEDF 78%, #F4EBDC 100%)', overflowX: 'hidden' }}>
      <IconSprite />
      <Header headerRef={headerRef} progressRef={progressRef} menuOpen={menuOpen} toggleMenu={toggleMenu} closeMenu={closeMenu} />
      <Hero tickerRef={tickerRef} daysLeftLabel={daysLeftLabel} cdD={cdD} cdH={cdH} cdM={cdM} cdS={cdS} />
      <MarqueeBand />
      <About />
      <Positioning />
      <WhyTGL />
      <Eligibility />
      <Categories />
      <Evaluation />
      <Benefits />
      <Journey />
      <Finale />
      <Register
        formRef={formRef}
        onSubmit={onSubmit}
        showForm={!submitted}
        submitted={submitted}
        submittedName={submittedName || 'founder'}
        submitting={submitting}
        submitLabel={submitting ? 'Submitting…' : 'Submit Registration'}
        errName={errors.name || ''}
        errBusiness={errors.business || ''}
        errEmail={errors.email || ''}
        errPhone={errors.phone || ''}
        errCategory={errors.category || ''}
        errEmployees={errors.employees || ''}
        errAge={errors.age || ''}
        errPaymentProof={errors.paymentProof || ''}
        errAgree={errors.agree || ''}
        resetForm={resetForm}
      />
      <Faq faq={faq} toggleFaq={toggleFaq} />
      <Contact />
      <Footer />
    </div>
  );
}
