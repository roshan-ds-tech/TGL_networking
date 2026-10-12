// Vocabulary for referrals, shared by the Give-a-referral dialog and the
// Referrals page. Values mirror backend/app/schemas.py and routers/referrals.py.
//
// Three parties, always named the same way:
//   referrer  = the signed-in member giving the referral ("You")
//   recipient = the TGL member who receives it
//   prospect  = the outside person/business who needs the product or service

export const STAGES = ['GIVEN', 'ACCEPTED', 'CONTACTED', 'MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED'];

export const STATUS_LABEL = {
  GIVEN: 'Submitted',
  ACCEPTED: 'Accepted',
  CONTACTED: 'Prospect contacted',
  MEETING_DONE: 'Meeting held',
  BUSINESS_CLOSED: 'Business won',
  REVENUE_GENERATED: 'Revenue logged',
  DECLINED: 'Declined',
  CANCELLED: 'Withdrawn',
  CLOSED: 'Closed',
};

export const STAGE_HELP = {
  GIVEN: 'The referrer sends the opportunity and the member is notified.',
  ACCEPTED: 'The recipient accepts and takes it forward.',
  CONTACTED: 'The recipient reaches out to the prospect.',
  MEETING_DONE: 'Both members confirm that a meeting took place.',
  BUSINESS_CLOSED: 'The recipient reports the deal value and the referrer confirms it.',
  REVENUE_GENERATED: 'Revenue is logged against the introduction. Growth Points are coming soon.',
};

export const ACTION_LABEL = {
  ACCEPTED: 'Accept referral',
  CONTACTED: 'Mark prospect contacted',
  MEETING_DONE: 'Mark meeting done',
  BUSINESS_CLOSED: 'Mark business won',
  REVENUE_GENERATED: 'Log revenue',
  DECLINED: 'Decline',
  CLOSED: 'Close without business',
  CANCELLED: 'Withdraw',
};
// The forward step is the main button; the rest are quiet links.
export const PRIMARY_ACTIONS = ['ACCEPTED', 'CONTACTED', 'MEETING_DONE', 'BUSINESS_CLOSED', 'REVENUE_GENERATED'];

export const VIEWS = [
  ['all', 'All'],
  ['sent', 'Sent'],
  ['received', 'Received'],
  ['in_progress', 'In progress'],
  ['converted', 'Converted'],
  ['closed', 'Closed'],
];

export const URGENCY = [
  { value: 'HOT', icon: '🔴', label: 'Hot', hint: 'Needs attention within 1 week' },
  { value: 'WARM', icon: '🟠', label: 'Warm', hint: 'Likely within 1 month' },
  { value: 'DEVELOPING', icon: '🟢', label: 'Developing', hint: 'A longer-term opportunity' },
  { value: 'UNSURE', icon: '⚪', label: 'Not sure', hint: "I don't know the timing" },
];
export const URGENCY_LABEL = Object.fromEntries(URGENCY.map((u) => [u.value, `${u.icon} ${u.label}`]));

export const RELATIONSHIPS = [
  ['EXISTING_CLIENT', 'Existing client'],
  ['PREVIOUS_CUSTOMER', 'Previous customer'],
  ['BUSINESS_CONTACT', 'Business contact'],
  ['PROFESSIONAL_NETWORK', 'Professional network'],
  ['FRIEND', 'Friend'],
  ['FAMILY', 'Family / personal contact'],
  ['CONTACTED_ME', 'Someone who contacted me'],
  ['OTHER', 'Other'],
];
export const RELATIONSHIP_LABEL = Object.fromEntries(RELATIONSHIPS);

export const INTRO_METHODS = [
  { value: 'EMAIL', label: "I'll introduce them by email", hint: 'TGL notifies the recipient now. Please also send your introduction email yourself.' },
  { value: 'CALL', label: "I'll arrange a call", hint: 'You set up a call between the prospect and the recipient.' },
  { value: 'SHARE_DETAILS', label: "I'll share the recipient's contact details", hint: 'You pass the recipient’s details to the prospect.' },
  { value: 'ALREADY_KNOWS', label: 'The prospect already knows the recipient', hint: 'No introduction needed.' },
  { value: 'OTHER', label: 'Other', hint: 'Add anything useful in the notes.' },
];
export const INTRO_LABEL = Object.fromEntries(INTRO_METHODS.map((m) => [m.value, m.label]));

export const PERMISSIONS = [
  ['EXPECTING', 'Yes, they are expecting contact'],
  ['CAREFULLY', 'Yes, but please contact them carefully'],
  ['ASK_FIRST', 'Ask me before contacting them'],
  ['UNSURE', "I'm not sure"],
];
export const PERMISSION_LABEL = Object.fromEntries(PERMISSIONS);

export const VALUE_RANGES = [
  ['UNKNOWN', 'Not known'],
  ['UNDER_25K', 'Under ₹25,000'],
  ['25K_1L', '₹25,000 – ₹1,00,000'],
  ['1L_5L', '₹1,00,000 – ₹5,00,000'],
  ['OVER_5L', '₹5,00,000+'],
];
export const VALUE_LABEL = Object.fromEntries(VALUE_RANGES);

export const CONTACT_METHODS = [['PHONE', 'Phone call'], ['WHATSAPP', 'WhatsApp'], ['EMAIL', 'Email']];
export const CONTACT_METHOD_LABEL = Object.fromEntries(CONTACT_METHODS);

export const QUALITY_LABEL = {
  CONTACT_ONLY: 'Contact only',
  WARM_REFERRAL: 'Warm referral',
  DIRECT_INTRO: 'Direct introduction',
  MEETING_ARRANGED: 'Meeting arranged',
};

export const DESCRIPTION_MIN = 30;
export const DESCRIPTION_MAX = 1000;

/**
 * Same rules as the backend (schemas.normalize_phone); the server stays the
 * authority. Indian numbers may be typed 98765 43210, +91…, 91… or 098…;
 * other countries need an explicit +country-code.
 */
export function checkPhone(raw) {
  const text = (raw || '').trim();
  if (!text) return { ok: false, error: 'Enter a mobile or phone number.' };
  if (text.length > 25 || /[^\d\s+()\-.]/.test(text)) return { ok: false, error: 'Use digits only, for example +91 98765 43210.' };
  let digits = text.replace(/\D/g, '');
  const international = text.startsWith('+') || text.startsWith('00');
  if (text.startsWith('00')) digits = digits.slice(2);
  if (!international) {
    if (digits.length === 12 && digits.startsWith('91')) digits = digits.slice(2);
    else if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);
    if (!/^[6-9]\d{9}$/.test(digits)) return { ok: false, error: 'Enter a 10-digit Indian mobile number, or add the country code (+44…).' };
    digits = `91${digits}`;
  } else if (digits.startsWith('91')) {
    if (!/^91[6-9]\d{9}$/.test(digits)) return { ok: false, error: 'Indian mobile numbers have 10 digits and start with 6, 7, 8 or 9.' };
  } else if (!/^[1-9]\d{7,14}$/.test(digits)) {
    return { ok: false, error: 'Enter a valid phone number with its country code.' };
  }
  if (new Set(digits.slice(-10)).size === 1) return { ok: false, error: "That doesn't look like a real phone number." };
  return { ok: true, value: `+${digits}` };
}

/** "+919876543210" → "+91 98765 43210". */
export function formatPhone(e164) {
  if (!e164) return '';
  const m = /^\+91(\d{5})(\d{5})$/.exec(e164);
  return m ? `+91 ${m[1]} ${m[2]}` : e164;
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
