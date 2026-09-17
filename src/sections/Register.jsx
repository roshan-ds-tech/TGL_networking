import { useState } from 'react';
import { CATEGORIES } from '../data/categories';

export default function Register({
  formRef,
  onSubmit,
  showForm,
  registrationClosed,
  submitted,
  submittedName,
  submitting,
  submitLabel,
  availability,
  errName,
  errBusiness,
  errEmail,
  errPhone,
  errCategory,
  errEmployees,
  errAge,
  errPaymentProof,
  errUtr,
  errAgree,
  errMediaConsent,
  errForm,
  resetForm,
}) {
  const [paymentProofName, setPaymentProofName] = useState('');
  const byCode = new Map((availability?.categories ?? []).map((c) => [c.category, c]));

  return (
    <section id="register" style={{ position: 'relative', overflow: 'hidden', padding: '104px 28px 100px', background: 'linear-gradient(180deg, #35194E, #22103A)', color: '#F6EEDF' }}>
      <span aria-hidden="true" style={{ position: 'absolute', top: '0', left: '0', right: '0', height: '150px', pointerEvents: 'none', background: 'linear-gradient(180deg, rgba(246,238,223,0.1), rgba(246,238,223,0))' }}></span>
      <span aria-hidden="true" style={{ position: 'absolute', bottom: '0', left: '0', right: '0', height: '150px', pointerEvents: 'none', background: 'linear-gradient(0deg, rgba(246,238,223,0.1), rgba(246,238,223,0))' }}></span>
      <div aria-hidden="true" style={{ position: 'absolute', top: '0', left: '50%', transform: 'translateX(-50%)', width: '900px', height: '560px', background: 'radial-gradient(ellipse at 50% 0%, rgba(224,181,88,0.18), rgba(224,181,88,0) 66%)', pointerEvents: 'none', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)', WebkitMaskImage: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,1) 16%, rgba(0,0,0,1) 84%, rgba(0,0,0,0) 100%)' }}></div>
      <div style={{ position: 'relative', maxWidth: '1240px', margin: '0 auto' }}>
        <div data-reveal="" style={{ textAlign: 'center', maxWidth: '760px', margin: '0 auto 46px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '14px', marginBottom: '22px' }}>
            <span aria-hidden="true" style={{ width: '48px', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), #E0B558)' }}></span>
            <p style={{ margin: '0', fontSize: '11px', letterSpacing: '.28em', textTransform: 'uppercase', color: '#E0B558', fontWeight: '700' }}>
              Registration & Pricing
            </p>
            <span aria-hidden="true" style={{ width: '48px', height: '1px', background: 'linear-gradient(90deg, #E0B558, rgba(224,181,88,0))' }}></span>
          </div>
          <h2 style={{ fontSize: 'clamp(26px, 3vw, 38px)', lineHeight: '1.06', letterSpacing: '-0.018em', fontWeight: '800', margin: '0 0 2px', color: '#FFFBF3', textTransform: 'uppercase' }}>
            Register For
          </h2>
          <p style={{ margin: '0 0 20px', fontFamily: "'Kaushan Script', cursive", fontWeight: '500', fontSize: 'clamp(46px, 6vw, 84px)', lineHeight: '1', letterSpacing: '-0.02em', background: 'linear-gradient(100deg, #A8762F 6%, #E0B558 24%, #FFF9E8 36%, #E0B558 48%, #A8762F 68%)', backgroundSize: '240% 100%', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', animation: 'tglShimmer 8s linear infinite' }}>
            Season 1
          </p>
          <p style={{ margin: '0 auto', maxWidth: '620px', fontSize: '17px', lineHeight: '1.72', color: 'rgba(246,238,223,0.75)', textWrap: 'pretty' }}>
            Registration closes 20 November 2026. Early / launch pricing of ₹2,499 applies now — the price rises in tiers as each category's slots fill.
          </p>
        </div>
        <div data-reveal="" style={{ position: 'relative', overflow: 'hidden', display: 'flex', flexWrap: 'wrap', marginBottom: '44px', border: '1px solid rgba(224,181,88,0.34)', borderRadius: '24px', background: 'rgba(255,251,243,0.05)', boxShadow: '0 20px 46px rgba(0,0,0,0.22)' }}>
          <span aria-hidden="true" style={{ position: 'absolute', top: '0', left: '0', right: '0', height: '1px', background: 'linear-gradient(90deg, rgba(224,181,88,0), rgba(224,181,88,0.7), rgba(224,181,88,0))' }}></span>
          <div style={{ flex: '1 1 210px', minWidth: '0', position: 'relative', padding: '30px 28px', background: 'linear-gradient(158deg, rgba(224,181,88,0.18), rgba(107,62,150,0.1) 70%, rgba(34,16,58,0))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '11px', marginBottom: '18px' }}>
              <span style={{ flexShrink: '0', width: '34px', height: '34px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(150deg, #E0B558, #A8762F)', color: '#2B1740' }}>
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
                  <use href="#i-tag"></use>
                </svg>
              </span>
              <p style={{ margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.2em', lineHeight: '1.5', textTransform: 'uppercase', color: '#EFCB77' }}>
                Early / launch price
              </p>
            </div>
            <p style={{ margin: '0 0 6px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '38px', fontWeight: '800', lineHeight: '1.05', letterSpacing: '-0.03em', color: '#FFF3CE' }}>
              ₹2,499
            </p>
            <p style={{ margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.42)' }}>
              Available now
            </p>
          </div>
          <div aria-hidden="true" style={{ width: '1px', alignSelf: 'stretch', background: 'linear-gradient(180deg, rgba(224,181,88,0), rgba(224,181,88,0.4), rgba(224,181,88,0))' }}></div>
          <div style={{ flex: '1 1 210px', minWidth: '0', position: 'relative', padding: '30px 28px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '11px', marginBottom: '18px' }}>
              <span style={{ flexShrink: '0', width: '34px', height: '34px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(224,181,88,0.12)', color: '#E0B558' }}>
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
                  <use href="#i-calendar"></use>
                </svg>
              </span>
              <p style={{ margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.2em', lineHeight: '1.5', textTransform: 'uppercase', color: 'rgba(246,238,223,0.62)' }}>
                Registration deadline
              </p>
            </div>
            <p style={{ margin: '0 0 6px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '25px', fontWeight: '800', lineHeight: '1.05', letterSpacing: '-0.03em', color: '#FFFBF3' }}>
              20 Nov 2026
            </p>
            <p style={{ margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.42)' }}>
              Entries close
            </p>
          </div>
          <div aria-hidden="true" style={{ width: '1px', alignSelf: 'stretch', background: 'linear-gradient(180deg, rgba(224,181,88,0), rgba(224,181,88,0.4), rgba(224,181,88,0))' }}></div>
          <div style={{ flex: '1 1 210px', minWidth: '0', position: 'relative', padding: '30px 28px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '11px', marginBottom: '18px' }}>
              <span style={{ flexShrink: '0', width: '34px', height: '34px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(224,181,88,0.12)', color: '#E0B558' }}>
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
                  <use href="#i-trophy"></use>
                </svg>
              </span>
              <p style={{ margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.2em', lineHeight: '1.5', textTransform: 'uppercase', color: 'rgba(246,238,223,0.62)' }}>
                Grand finale
              </p>
            </div>
            <p style={{ margin: '0 0 6px', fontFamily: 'Archivo, Helvetica, sans-serif', fontSize: '25px', fontWeight: '800', lineHeight: '1.05', letterSpacing: '-0.03em', color: '#FFFBF3' }}>
              5 Dec 2026
            </p>
            <p style={{ margin: '0', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(246,238,223,0.42)' }}>
              Award show, Bengaluru
            </p>
          </div>
        </div>
        <div data-reveal="" style={{ position: 'relative', overflow: 'hidden', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '20px 26px', marginBottom: '44px', padding: '26px 30px', border: '1px solid rgba(224,181,88,0.5)', borderRadius: '20px', background: 'linear-gradient(120deg, rgba(224,181,88,0.16), rgba(107,62,150,0.1) 70%, rgba(34,16,58,0))' }}>
          <span aria-hidden="true" style={{ flexShrink: '0', width: '44px', height: '44px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'linear-gradient(150deg, #E0B558, #A8762F)', color: '#2B1740' }}>
            <svg width="21" height="21" viewBox="0 0 24 24">
              <use href="#i-clock"></use>
            </svg>
          </span>
          <div style={{ flex: '1 1 320px', minWidth: '0' }}>
            <p style={{ margin: '0 0 6px', fontFamily: "'IBM Plex Mono', monospace", fontSize: '9.5px', letterSpacing: '.2em', textTransform: 'uppercase', fontWeight: '500', color: '#EFCB77' }}>
              Early-bird pricing is limited
            </p>
            <p style={{ margin: '0', fontSize: '16px', lineHeight: '1.68', color: 'rgba(246,238,223,0.88)', textWrap: 'pretty' }}>
              Each category has <strong style={{ color: '#FFF3CE', fontWeight: '700' }}>40 slots</strong>. The first <strong style={{ color: '#FFF3CE', fontWeight: '700' }}>20 slots</strong> are priced at the early / launch rate of <strong style={{ color: '#FFF3CE', fontWeight: '700' }}>₹2,499</strong>. Once those fill, the price for that category rises to <strong style={{ color: '#FFCB5C', fontWeight: '700' }}>₹3,499</strong> — and for the <strong style={{ color: '#FFB5B5', fontWeight: '700' }}>final 3 slots</strong>, it rises again to an even higher rate. Register early to lock in the lowest price.
            </p>
          </div>
          <div style={{ flexShrink: '0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '14px', padding: '8px 16px', border: '1px solid rgba(224,181,88,0.45)', borderRadius: '999px', background: 'rgba(34,16,58,0.35)', fontFamily: "'IBM Plex Mono', monospace", fontSize: '10.5px', letterSpacing: '.1em', textTransform: 'uppercase', color: '#EFCB77' }}>
              Slots 1–20 <strong>₹2,499</strong>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '14px', padding: '8px 16px', border: '1px solid rgba(255,203,92,0.5)', borderRadius: '999px', background: 'rgba(34,16,58,0.35)', fontFamily: "'IBM Plex Mono', monospace", fontSize: '10.5px', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFCB5C' }}>
              Slots 21–37 <strong>₹3,499</strong>
            </span>
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '14px', padding: '8px 16px', border: '1px solid rgba(255,181,181,0.55)', borderRadius: '999px', background: 'rgba(74,20,20,0.35)', fontFamily: "'IBM Plex Mono', monospace", fontSize: '10.5px', letterSpacing: '.1em', textTransform: 'uppercase', color: '#FFB5B5' }}>
              Final 3 slots <strong>Higher</strong>
            </span>
          </div>
        </div>
        <div id="register-form" data-reveal="" style={{ display: 'flex', flexWrap: 'wrap', gap: '28px', alignItems: 'flex-start' }}>
          <div data-register-panel="form" style={{ flex: '1 1 540px', minWidth: '0', background: '#FFFBF3', color: '#2B1740', padding: '44px 42px', borderRadius: '20px', boxShadow: '0 30px 70px rgba(0,0,0,0.28)' }}>
            {registrationClosed && (
              /* Shown instead of the form once the deadline passes. The server
                 refuses late submissions anyway, but the payment happens before
                 the form is filled in — so the form has to disappear here, or
                 someone pays for a registration that can no longer be made. */
              <div>
                <h3 style={{ margin: '0 0 8px', fontSize: '25px', fontWeight: '800', color: '#2B1740' }}>
                  Registration Has Closed
                </h3>
                <p style={{ margin: '0 0 20px', fontSize: '15px', lineHeight: '1.7', color: 'rgba(43,23,64,0.7)' }}>
                  Season 1 entries closed on 20 November 2026. Please do not make a
                  payment for Season 1 — it can no longer be accepted.
                </p>
                <p style={{ margin: '0', fontSize: '15px', lineHeight: '1.7', color: 'rgba(43,23,64,0.7)' }}>
                  Already paid, or want to hear about Season 2?{' '}
                  <a href="#contact" style={{ color: '#6B3E96', fontWeight: '700' }}>
                    Get in touch
                  </a>
                  .
                </p>
              </div>
            )}
            {showForm && !registrationClosed && (
              <div>
                <h3 style={{ margin: '0 0 8px', fontSize: '25px', fontWeight: '800', color: '#2B1740' }}>
                  Season 1 Registration
                </h3>
                <p style={{ margin: '0 0 30px', fontSize: '15px', lineHeight: '1.6', color: 'rgba(43,23,64,0.66)' }}>
                  Tell us about your business. Fields marked <span style={{ color: '#B8863B', fontWeight: '700' }}>*</span> are required. Registration does not guarantee selection.
                </p>
                <form ref={formRef} onSubmit={onSubmit} noValidate style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: '22px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label htmlFor="tgl-name" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Full name<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <input id="tgl-name" name="name" maxLength={120} type="text" autoComplete="name" placeholder="Your full name" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-66" />
                    {errName && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errName}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label htmlFor="tgl-business" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Business name<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <input id="tgl-business" name="business" maxLength={160} type="text" autoComplete="organization" placeholder="Registered or trade name" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-67" />
                    {errBusiness && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errBusiness}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label htmlFor="tgl-email" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Email<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <input id="tgl-email" name="email" maxLength={255} type="email" autoComplete="email" placeholder="you@business.com" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-68" />
                    {errEmail && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errEmail}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label htmlFor="tgl-phone" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Phone<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <input id="tgl-phone" name="phone" type="tel" autoComplete="tel" placeholder="10-digit mobile number" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-69" />
                    {errPhone && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errPhone}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', gridColumn: '1 / -1' }}>
                    <label htmlFor="tgl-category" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Category<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <select id="tgl-category" name="category" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-70">
                      <option value="">Select one of the 10 categories</option>
                      {CATEGORIES.map(({ code, name }) => {
                        const stat = byCode.get(code);
                        const full = stat ? stat.filled >= stat.capacity : false;
                        return (
                          <option key={code} value={code} disabled={full}>
                            {code} · {name}{full ? ' — Full, registration closed' : ''}
                          </option>
                        );
                      })}
                    </select>
                    {errCategory && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errCategory}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label htmlFor="tgl-employees" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Number of employees<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <select id="tgl-employees" name="employees" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-71">
                      <option value="">Select</option>
                      <option value="1-3">1–3</option>
                      <option value="4-6">4–6</option>
                      <option value="7-10">7–10</option>
                      <option value="10+">More than 10</option>
                    </select>
                    {errEmployees && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errEmployees}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label htmlFor="tgl-age" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Months in business<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <select id="tgl-age" name="age" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-72">
                      <option value="">Select</option>
                      <option value="lt6">Less than 6 months</option>
                      <option value="6-12">6–12 months</option>
                      <option value="1-3y">1–3 years</option>
                      <option value="3y+">More than 3 years</option>
                    </select>
                    {errAge && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errAge}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', gridColumn: '1 / -1' }}>
                    <label htmlFor="tgl-city" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      City / area <span style={{ fontWeight: '500', textTransform: 'none', letterSpacing: '0', color: 'rgba(43,23,64,0.5)' }}>(optional)</span>
                    </label>
                    <input id="tgl-city" name="city" maxLength={120} type="text" placeholder="e.g. Indiranagar, Bengaluru" style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }} className="hv-73" />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', gridColumn: '1 / -1' }}>
                    <label htmlFor="tgl-payment-proof" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      Payment screenshot<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <div style={{ position: 'relative' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', border: '1px dashed rgba(53,26,78,0.35)', background: '#F6EEDF', padding: '15px 16px', fontSize: '14.5px', color: paymentProofName ? '#2B1740' : 'rgba(43,23,64,0.55)', borderRadius: '12px', minHeight: '52px' }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: '0', color: '#6B3E96' }}>
                          <use href="#i-camera"></use>
                        </svg>
                        {paymentProofName || 'Upload a screenshot of your payment (JPG, PNG or PDF)'}
                      </div>
                      <input
                        id="tgl-payment-proof"
                        name="paymentProof"
                        type="file"
                        accept="image/*,.pdf"
                        required
                        onChange={(ev) => setPaymentProofName(ev.target.files[0] ? ev.target.files[0].name : '')}
                        style={{ position: 'absolute', inset: '0', width: '100%', height: '100%', opacity: '0', cursor: 'pointer' }}
                      />
                    </div>
                    {errPaymentProof && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errPaymentProof}</span>}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', gridColumn: '1 / -1' }}>
                    <label htmlFor="tgl-utr" style={{ fontSize: '12.5px', letterSpacing: '.1em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                      UTR / UPI reference number<span style={{ color: '#B8863B' }}>*</span>
                    </label>
                    <input
                      id="tgl-utr"
                      name="utr"
                      type="text"
                      autoComplete="off"
                      spellCheck="false"
                      maxLength={40}
                      placeholder="e.g. 402912345678"
                      aria-describedby="tgl-utr-hint"
                      style={{ border: '1px solid rgba(53,26,78,0.24)', background: '#F6EEDF', padding: '15px 16px', fontSize: '15.5px', letterSpacing: '.04em', color: '#2B1740', borderRadius: '12px', minHeight: '52px' }}
                      className="hv-73"
                    />
                    <span id="tgl-utr-hint" style={{ fontSize: '12.5px', lineHeight: '1.55', color: 'rgba(43,23,64,0.58)' }}>
                      Your payment app shows this as the UTR, UPI reference ID or transaction ID — usually 12 digits. It lets us match your payment to this registration.
                    </span>
                    {errUtr && <span role="alert" style={{ fontSize: '13px', color: '#9A2B2B', fontWeight: '600' }}>{errUtr}</span>}
                  </div>
                  <label style={{ gridColumn: '1 / -1', display: 'flex', gap: '12px', alignItems: 'flex-start', fontSize: '14.5px', lineHeight: '1.6', color: 'rgba(43,23,64,0.72)', cursor: 'pointer' }}>
                    <input name="agree" type="checkbox" style={{ width: '20px', height: '20px', marginTop: '2px', accentColor: '#6B3E96', flexShrink: '0' }} />
                    <span>
                      I understand that registration does not guarantee selection, that final selection is subject to the TGL evaluation and judging process, and that registration payment is non-refundable once payment is confirmed.
                      <span style={{ color: '#B8863B', fontWeight: '700' }}> *</span>
                    </span>
                  </label>
                  {errAgree && <span role="alert" style={{ gridColumn: '1 / -1', fontSize: '13px', color: '#9A2B2B', fontWeight: '600', marginTop: '-10px' }}>{errAgree}</span>}
                  <label style={{ gridColumn: '1 / -1', display: 'flex', gap: '12px', alignItems: 'flex-start', fontSize: '14.5px', lineHeight: '1.6', color: 'rgba(43,23,64,0.72)', cursor: 'pointer' }}>
                    <input name="mediaConsent" type="checkbox" style={{ width: '20px', height: '20px', marginTop: '2px', accentColor: '#6B3E96', flexShrink: '0' }} />
                    <span>
                      I give TGL and SkyKeen Events permission to use my submitted raw footage, photographs and the edited video — with my consent — across social media, promotional material and event coverage.
                      <span style={{ color: '#B8863B', fontWeight: '700' }}> *</span>
                    </span>
                  </label>
                  {errMediaConsent && <span role="alert" style={{ gridColumn: '1 / -1', fontSize: '13px', color: '#9A2B2B', fontWeight: '600', marginTop: '-10px' }}>{errMediaConsent}</span>}
                  {errForm && (
                    <p role="alert" style={{ gridColumn: '1 / -1', margin: '0', padding: '14px 16px', borderRadius: '12px', background: 'rgba(154,43,43,0.08)', border: '1px solid rgba(154,43,43,0.3)', fontSize: '14px', fontWeight: '600', color: '#9A2B2B' }}>
                      {errForm}
                    </p>
                  )}
                  <div style={{ gridColumn: '1 / -1', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '18px', marginTop: '4px' }}>
                    <button type="submit" disabled={submitting} style={{ display: 'inline-flex', alignItems: 'center', gap: '12px', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', border: 'none', color: '#22103A', fontWeight: '700', fontSize: '14px', letterSpacing: '.08em', textTransform: 'uppercase', padding: '18px 40px', borderRadius: '999px', cursor: 'pointer', minHeight: '56px', boxShadow: '0 10px 26px rgba(192,141,46,0.3)', transition: 'transform .2s ease, box-shadow .2s ease' }} className="hv-74">
                      {submitting && <span style={{ width: '16px', height: '16px', border: '2px solid rgba(34,16,58,0.28)', borderTopColor: '#22103A', borderRadius: '50%', display: 'inline-block', animation: 'tglSpin .7s linear infinite' }}></span>}
                      {submitLabel}
                    </button>
                    <p style={{ margin: '0', fontSize: '13.5px', color: 'rgba(43,23,64,0.6)' }}>
                      Early / launch price ₹2,499 · closes 20 Nov 2026
                    </p>
                  </div>
                </form>
              </div>
            )}
            {submitted && (
              <div style={{ textAlign: 'center', padding: '30px 0' }}>
                <div style={{ width: '68px', height: '68px', margin: '0 auto 26px', borderRadius: '50%', background: 'linear-gradient(135deg, #E0B558, #C08D2E)', color: '#22103A', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '30px', fontWeight: '700' }}>
                  ✓
                </div>
                <h3 style={{ margin: '0 0 14px', fontSize: '30px', fontWeight: '800', color: '#2B1740' }}>
                  Registration Successful!
                </h3>
                <p style={{ margin: '0 auto 30px', maxWidth: '460px', fontSize: '16px', lineHeight: '1.7', color: 'rgba(43,23,64,0.7)' }}>
                  Thank you, {submittedName}. Your Season 1 entry has been received.
                </p>
                <div style={{ maxWidth: '480px', margin: '0 auto 30px', textAlign: 'left', border: '1px solid rgba(53,26,78,0.16)', borderRadius: '18px', padding: '26px 28px', background: '#F6EEDF' }}>
                  <p style={{ margin: '0 0 14px', fontSize: '11px', letterSpacing: '.22em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                    What happens next
                  </p>
                  <p style={{ margin: '0 0 10px', fontSize: '15px', lineHeight: '1.6', color: 'rgba(43,23,64,0.78)' }}>
                    1 — Complete your business profile / submission.
                  </p>
                  <p style={{ margin: '0 0 10px', fontSize: '15px', lineHeight: '1.6', color: 'rgba(43,23,64,0.78)' }}>
                    2 — Your business enters the TGL evaluation process.
                  </p>
                  <p style={{ margin: '0', fontSize: '15px', lineHeight: '1.6', color: 'rgba(43,23,64,0.78)' }}>
                    3 — Selected businesses receive the shoot guide for their professional video.
                  </p>
                </div>
                <p style={{ margin: '0 0 22px', fontSize: '13.5px', lineHeight: '1.6', color: 'rgba(43,23,64,0.55)' }}>
                  Registration does not guarantee selection. Final selection is subject to the TGL evaluation and judging process. The judges' decision is final and binding.
                </p>
                <button type="button" onClick={resetForm} style={{ background: 'none', border: '1px solid rgba(53,26,78,0.3)', color: '#35194E', fontWeight: '600', fontSize: '13px', letterSpacing: '.08em', textTransform: 'uppercase', padding: '15px 30px', borderRadius: '999px', cursor: 'pointer', minHeight: '48px' }} className="hv-75">
                  Register another business
                </button>
              </div>
            )}
          </div>
          <div data-register-panel="qr" style={{ flex: '1 1 280px', minWidth: '0', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ background: '#FFFBF3', color: '#2B1740', padding: '34px 30px', borderRadius: '20px', textAlign: 'center' }}>
              <p style={{ margin: '0 0 6px', fontSize: '11px', letterSpacing: '.24em', textTransform: 'uppercase', fontWeight: '700', color: '#6B3E96' }}>
                Scan to register
              </p>
              <p style={{ margin: '0 0 22px', fontSize: '13.5px', color: 'rgba(43,23,64,0.6)' }}>
                Point your camera at the code.
              </p>
              <div style={{ width: '100%', maxWidth: '240px', aspectRatio: '921 / 1280', margin: '0 auto 20px', border: '2px solid #35194E', borderRadius: '18px', overflow: 'hidden' }}>
                <img src="/images/QR_code.jpeg" alt="Registration QR Code" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
              </div>
            </div>
            <div style={{ border: '1px solid rgba(224,181,88,0.35)', padding: '28px 26px', borderRadius: '20px' }}>
              <p style={{ margin: '0 0 12px', fontSize: '11px', letterSpacing: '.22em', textTransform: 'uppercase', fontWeight: '700', color: '#E0B558' }}>
                Selection disclaimer
              </p>
              <p style={{ margin: '0 0 18px', fontSize: '14px', lineHeight: '1.65', color: 'rgba(246,238,223,0.75)' }}>
                Registration does not guarantee selection. Final selection is subject to the TGL evaluation and judging process. The judges' decision is final and binding.
              </p>
              <p style={{ margin: '0 0 12px', fontSize: '11px', letterSpacing: '.22em', textTransform: 'uppercase', fontWeight: '700', color: '#E0B558' }}>
                Refund policy
              </p>
              <p style={{ margin: '0', fontSize: '14px', lineHeight: '1.65', color: 'rgba(246,238,223,0.75)' }}>
                Registration payment is non-refundable once payment is confirmed.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
