// Vertex is a design preview this pass — no backend, no real provider
// directory (see docs/P0_IMPLEMENTATION.md's P1/P2 list). This mock data
// matches the source design's own hardcoded sample content verbatim, and
// every screen that uses it says so explicitly in its copy.

export const VERTEX_CATEGORIES = [
  { code: '01', name: 'Finance & Accounting', icon: 'i-chart' },
  { code: '02', name: 'Legal & Compliance', icon: 'i-doc' },
  { code: '03', name: 'HR & Recruitment', icon: 'i-users' },
  { code: '04', name: 'Consulting & Mentoring', icon: 'i-bulb' },
  { code: '05', name: 'Marketing & Branding', icon: 'i-megaphone' },
  { code: '06', name: 'Technology & AI', icon: 'i-globe' },
  { code: '07', name: 'Property / Workspace', icon: 'i-store' },
  { code: '08', name: 'Interior / Architecture', icon: 'i-grid' },
  { code: '09', name: 'Printing / Corporate Gifting', icon: 'i-tag' },
  { code: '10', name: 'Events / Production', icon: 'i-video' },
  { code: '11', name: 'Logistics / Operations', icon: 'i-send' },
  { code: '12', name: 'Insurance', icon: 'i-shield' },
  { code: '13', name: 'Fire & Safety', icon: 'i-target' },
  { code: '14', name: 'Other B2B Services', icon: 'i-briefcase' },
];

export const VERTEX_CHIPS = [
  'Need a CA', 'Need legal help', 'Need branding', 'Need a website',
  'Need recruitment support', 'Need workspace', 'Need business consulting', 'Need logistics support',
];

export const VERTEX_PROVIDERS = [
  { id: 'p1', name: 'Sample Provider A', category: 'Marketing & Branding', location: 'Bengaluru', blurb: 'Brand identity, visual systems and packaging for growing consumer businesses.', tags: ['Brand identity', 'Packaging', 'Guidelines'], verified: true },
  { id: 'p2', name: 'Sample Provider B', category: 'Marketing & Branding', location: 'Bengaluru · Remote', blurb: 'Positioning, naming and launch campaigns for founder-led teams.', tags: ['Positioning', 'Naming'], verified: false },
  { id: 'p3', name: 'Sample Provider C', category: 'Technology & AI', location: 'Pan-India', blurb: 'Websites and digital storefronts that carry a new brand system through.', tags: ['Websites', 'E-commerce'], verified: true },
];

export const VERTEX_FILTER_GROUPS = [
  { title: 'Category', opts: ['Marketing & Branding', 'Technology & AI', 'Consulting & Mentoring'] },
  { title: 'Location', opts: ['Bengaluru', 'Karnataka', 'Remote / Pan-India'] },
  { title: 'Experience', opts: ['Under 3 years', '3–10 years', '10+ years'] },
  { title: 'Availability', opts: ['Taking new work'] },
];

export const PROVIDER_SERVICES = ['Brand strategy', 'Visual identity', 'Packaging design', 'Brand guidelines', 'Naming'];
export const PROVIDER_SPECS = ['Consumer brands', 'Food & beverage', 'Retail packaging', 'Founder-led businesses'];
