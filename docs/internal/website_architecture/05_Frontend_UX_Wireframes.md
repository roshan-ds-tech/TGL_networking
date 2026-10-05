# TGL · Document 05
## Frontend Architecture, Design System, Wireframes, Admin Platform

**Navigation (v2.0 correction).** v1.0 specified a Vertex-only sidebar (`Vertex · My Projects · Networking · Referrals · Resources`). The finalised TGL navigation is a **five-item bottom tab bar** — `Vertex · Networking · Events · 🔔 Notifications · 👤 Profile` — with Awards and Podcasts reachable from within Vertex/Networking/Events/profiles rather than as top-level tabs, and My Projects/Resources reachable from within Vertex (Doc 01 §4 has the full rationale). §1.1's route tree and every wireframe below are updated to this structure.

---

# 1. Frontend architecture

## 1.1 Structure

```
apps/web/
├── app/
│   ├── (marketing)/            # public, ISR, SEO
│   │   ├── page.tsx                       # landing
│   │   ├── providers/[slug]/page.tsx      # public provider profile (ISR 60s)
│   │   ├── categories/[code]/page.tsx     # category landing (SEO)
│   │   └── resources/[slug]/page.tsx
│   ├── (auth)/
│   │   ├── login/ register/ forgot-password/
│   ├── (app)/                  # authenticated shell with 5-tab bottom nav (Doc 01 §4)
│   │   ├── layout.tsx                     # bottom tab bar (mobile) / left nav (desktop) + topbar + auth guard
│   │   ├── vertex/page.tsx                # Vertex tab — THE main open surface
│   │   ├── vertex/[conversationId]/page.tsx
│   │   ├── vertex/projects/ vertex/resources/     # nested under Vertex, not top-level (Doc 01 §4.2)
│   │   ├── networking/                    # Networking tab — membership-gated
│   │   │   ├── page.tsx                             # directory + feed
│   │   │   ├── [memberId]/page.tsx                  # member profile
│   │   │   ├── referrals/ need-board/ leaderboards/
│   │   ├── events/ events/[slug]/         # Events tab
│   │   ├── awards/                        # reachable from events/networking/profiles, not a tab
│   │   ├── podcasts/                      # reachable from vertex home/profiles, not a tab
│   │   ├── notifications/                 # Notifications tab
│   │   └── profile/ profile/membership/   # Profile tab, incl. TGL Membership status (Doc 01 §13)
│   ├── (business)/             # Vertex provider surfaces
│   │   ├── onboarding/[step]/ dashboard/ profile/
│   │   ├── verification/ leads/ subscription/
│   └── api/                    # BFF routes only: auth cookie handling, SSE proxy
├── components/ui/              # shadcn/ui primitives
├── components/                 # shared composites
├── features/                   # feature-scoped: components + hooks + api + types
│   ├── vertex/ providers/ projects/ verification/ networking/ membership/ events/ awards/ podcasts/ referrals/ billing/
├── lib/                        # api client, auth, utils, analytics
├── hooks/  types/  store/  styles/  public/
```

**`features/` is the important directory.** Feature-scoped colocation (component + hook + API call + types in one folder) is what keeps a large Next.js app navigable. A flat `components/` folder with 200 files is where frontend velocity goes to die.

## 1.2 Server vs client components

| Concern | Choice |
|---|---|
| Landing, provider profiles, category pages, resources | **Server components + ISR.** SEO-critical, cacheable, no interactivity beyond links |
| Vertex conversation | **Client component.** Consumes SSE, holds streaming state |
| Dashboards, forms, filters | Client components inside a server-rendered shell |
| Auth check | Middleware + server-side session read; never a client-only guard (a client-only guard is a UI convenience, not security) |
| Data fetching | Server components fetch directly; client components use TanStack Query |

## 1.3 State management

| State | Tool |
|---|---|
| Server data | **TanStack Query** — caching, invalidation, optimistic updates |
| Streaming AI response | Local `useReducer` in the Vertex feature |
| Global UI (sidebar, modals, toasts) | **Zustand**, small store |
| Forms | **React Hook Form + Zod**, schemas imported from `packages/contracts` so client and server validate identically |
| URL state (filters, pagination) | **Search params.** Filters must be shareable and back-button-safe |

No Redux. The state here is server state plus a small amount of UI state, and TanStack Query plus Zustand covers both with a fraction of the ceremony.

## 1.4 Accessibility (non-negotiable, checked in CI)

Semantic HTML · full keyboard navigation including the Vertex input and chip rows · visible focus rings · WCAG AA contrast (4.5:1 body, 3:1 large) · `aria-live="polite"` on the streaming response region so screen readers announce it without interrupting · labelled form fields with errors linked by `aria-describedby` · `prefers-reduced-motion` respected · minimum 44×44px touch targets · skip-to-content link. axe-core runs in CI and fails the build on violations.

---

# 2. Design system

**Visual direction:** modern, clean, trustworthy, premium, AI-native, business-focused. Restraint over decoration — this product asks people to spend money on providers they have not met, and visual noise reads as unseriousness.

```
COLOUR
  Ink        #0A0A0B   text primary
  Slate-700  #3F3F46   text secondary
  Slate-400  #A1A1AA   text tertiary / placeholder
  Surface    #FFFFFF   cards
  Canvas     #FAFAFA   page background
  Border     #E4E4E7
  Primary    #1D4ED8   actions, links, focus
  Primary-50 #EFF6FF   subtle fills
  Success    #059669   verified, positive
  Warning    #D97706   pending, attention
  Danger     #DC2626   errors, destructive
  Verified badge scale: T0 #A1A1AA · T1 #2563EB · T2 #059669 · T3 #B45309 (gold)

TYPE (Inter, tabular numerals for metrics)
  Display 36/44 600 · H1 30/38 600 · H2 24/32 600 · H3 20/28 600
  Body-L 16/24 400 · Body 14/20 400 · Small 13/18 400 · Caption 12/16 500 uppercase 0.04em

SPACE   4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96      (4px base)
RADIUS  sm 6 · md 8 · lg 12 · xl 16 · full 9999
SHADOW  sm 0 1 2 rgba(0,0,0,.05) · md 0 4 8 rgba(0,0,0,.06) · lg 0 12 24 rgba(0,0,0,.08)
MOTION  fast 120ms · base 200ms · slow 320ms · ease-out cubic-bezier(.16,1,.3,1)
```

**Components:** Button (primary/secondary/ghost/danger × sm/md/lg, loading and disabled states) · Input, Textarea, Select, Combobox, Checkbox, Radio, Switch · Card (default/interactive/selected) · Badge (verification tiers, status) · Chip (suggestion, filter, removable) · Alert (info/success/warning/error) · Modal, Drawer, Popover, Tooltip, Dropdown · Table (sortable, paginated, selectable) · Tabs, Accordion · Avatar, Rating, Progress, Skeleton · EmptyState (icon + heading + body + primary action — **never a bare "No results"**) · Toast.

**Loading discipline:** skeletons that match the final layout, not spinners. A spinner tells the user nothing; a skeleton tells them what is coming and stops the layout from jumping.

---

# 3. Wireframes

Notation: `[button]` `{input}` `«chip»` `▸` disclosure · `│` column divider. Viewports: desktop 1440, tablet 768, mobile 390.

## W1 · Vertex — empty state (the flagship screen)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ⬡ Vertex          │                                        🔔  ⚙  ◐ SK  │
│───────────────────│──────────────────────────────────────────────────────│
│ ▸ Vertex          │                                                      │
│   My Projects     │                                                      │
│   Networking      │                    ⬡  V E R T E X                    │
│   Referrals       │                                                      │
│   Resources       │              What are you building?                  │
│                   │                                                      │
│ ─────────────     │   ┌────────────────────────────────────────────┐    │
│ RECENT            │   │ {Search for providers, categories...} [↑]  │    │
│  Clothing brand   │   └────────────────────────────────────────────┘    │
│  Warehouse search │                                                      │
│                   │   «Start a clothing business»  «Open a restaurant»   │
│                   │   «Find wholesale suppliers»   «Find commercial space»│
│                   │   «Register my company»        «Get GST registration»│
│ ─────────────     │                                                      │
│ ◐ Shashi          │   Trusted by 2,400+ verified businesses in Bengaluru │
└──────────────────────────────────────────────────────────────────────────┘
```

**Layout:** sidebar 260px fixed; content centred, max-width 720px; input vertically centred at ~40% viewport height (not dead centre — centred inputs feel like a search engine, slightly-above-centre feels like a workspace).
**Hierarchy:** wordmark → question → input → chips → trust line.
**States:** input focus raises elevation and shows the border in Primary; chips are keyboard-reachable and activate on Enter.
**Responsive:** mobile hides the sidebar behind a hamburger, moves the input toward the top, and shows chips in a horizontally scrollable row.
**Mobile:** bottom tab bar replaces the sidebar; the input is sticky above the keyboard.

## W2 · (Phase 3) Vertex — typing state

Chips fade to 40% opacity and stop accepting clicks. A typeahead dropdown appears directly under the input showing up to 6 completions (recent queries first with a clock icon, then popular). Send button becomes enabled and Primary. Enter submits, Shift+Enter newlines, Escape dismisses the dropdown.

## W3 · (Phase 3) Vertex — suggestion/typeahead state

```
   ┌────────────────────────────────────────────┐
   │ {I want to start a cloth|              [↑] │
   └────────────────────────────────────────────┘
   ┌────────────────────────────────────────────┐
   │ ⏱  start a clothing business in Bengaluru  │   ← recent (this user)
   │ ⌕  start a clothing brand                  │   ← popular
   │ ⌕  clothing manufacturers Bengaluru        │
   │ ⌕  cloth wholesale suppliers               │
   └────────────────────────────────────────────┘
```
Arrow keys navigate, Enter selects, the selected row is highlighted at Primary-50. Served from Redis — no model call, target <50ms.

## W4 · (Phase 3) Vertex — submitted / thinking state

```
│  You                                                            │
│  I want to start a clothing business in Bangalore with ₹10 lakh │
│                                                                 │
│  ⬡ Vertex                                                       │
│  ✓ Understanding your requirement                               │
│  ✓ Identified: Clothing retail · Bengaluru · ₹10,00,000 · New   │
│  ◐ Mapping what you'll need...                                  │
│  ○ Finding providers                                            │
└─────────────────────────────────────────────────────────────────┘
```

Stage list streams in; completed stages collapse to a single line with a tick. **The identified-entities line is clickable to correct** — this is the confidence-band UI from Doc 02 §2.4 and it is the single highest-value affordance on the screen. Cancel button available throughout. Skeleton provider cards appear under the "Finding providers" stage before results arrive.

## W5 · (Phase 3) Vertex — requirements + results

```
│  ⬡ Vertex                                                                │
│  For a ₹10 lakh clothing retail launch in Bengaluru, here's what you'll  │
│  likely need. I've started with the four that usually come first.        │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 1  Commercial retail space              ● High priority         ▾  │ │
│  │    Customer-facing space; typically 20–30% of starting capital     │ │
│  │    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │ │
│  │    │ provider card│ │ provider card│ │ provider card│  [See all 42]│ │
│  │    └──────────────┘ └──────────────┘ └──────────────┘              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 2  Wholesale clothing suppliers         ● High priority         ▸  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 3  Company registration                 ● High priority         ▸  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  … 10 more  [Show all]                          [+ Save as project]     │
│                                                                          │
│  «Show cheaper options» «Only near Whitefield» «Verified only»           │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ {Ask a follow-up...}                                          [↑]  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
```

First requirement expanded by default; the rest collapsed. Horizontal card scroll inside each requirement on desktop; vertical stack on mobile. `[+ Save as project]` is the retention hook and should be visually prominent — it is the action that converts a search into a returning user.

## W5a · Vertex — Standard Search Results (MVP)

```
│  ⬡ Vertex                                                                │
│  Results for "clothing retail"                                           │
│                                                                          │
│  «Category: Retail Space» «Verified only» «Bengaluru»                    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ ▢ logo   Sharma Textiles    ⋮                                    │ │
│  │          ✓ Business Verified                                       │ │
│  │ ★ 4.6 (34)  ·  Whitefield 4km                                      │ │
│  │ Wholesale apparel, fabric                                          │ │
│  │ MOQ ₹25,000 · Ships in 7 days                                      │ │
│  │ [Contact]        [♡ Save]                                          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
```

Standard search results page powered by the hybrid search engine. Filters at the top. Cards stacked vertically.

## W6 · Provider result card

```
┌─────────────────────────────────┐
│ ▢ logo   Sharma Textiles    ⋮  │
│          ✓ Business Verified    │
│ ★ 4.6 (34)  ·  Whitefield 4km   │
│ Wholesale apparel, fabric       │
│ MOQ ₹25,000 · Ships in 7 days   │
│ ⏱ Usually replies in 6h         │
│ [Contact]        [♡ Save]       │
└─────────────────────────────────┘
```
320×260 desktop, full-width mobile. Verification badge always in the same position — consistency is what makes a badge scannable. Hover raises elevation and reveals a quick-view affordance. Promoted cards carry a "Promoted" label in the top-right and a subtle tinted border, per the disclosure rule (Doc 01 §7.1).

## W7 · Provider profile

Two columns on desktop (main 2/3, sticky sidebar 1/3). Main: cover + logo + name + verification badge + rating · about · services with price ranges · media gallery · reviews with distribution bar and provider replies · location map · similar providers. Sidebar (sticky): `[Contact provider]` primary CTA, `[Save]`, `[Add to project]`, a verification panel listing exactly what was verified (GSTIN ✓, Address ✓, Bank ✓) with dates, response stats, and business details. Mobile: single column with a sticky bottom action bar.

**The verification panel is the trust payload.** Showing *what* was verified and *when* is far more convincing than a badge alone, and it is the thing that makes verification worth paying for on the provider side.

## W8 · User onboarding

Three progressive steps, each skippable, with a progress bar: (1) What stage are you at? (Idea / Launching / Running / Growing) · (2) What are you interested in? (multi-select L1 domains) · (3) Where are you? (city autocomplete, prefilled from IP). `[Skip for now]` always visible. Completing all three sets `onboarding_completed` and materially improves personalisation; skipping costs nothing and the user lands on W1 either way.

## W9 · Business registration (multi-step)

Steps: Business info → Categories → Location → Contact → Documents → Review. A left rail shows all steps with status; the form is on the right; progress is saved on every step so the user can leave and return. Category selection is a searchable tree with a live counter against the plan limit. Location uses Google Places autocomplete and drops a confirmable map pin. **No payment step here** — payment comes after verification (Doc 01 §5.1).

## W10 · Verification status dashboard

```
│  Verification                                       Tier: ✓ Contact Verified │
│  ●━━━━━━━━●━━━━━━━━○━━━━━━━━○                                                │
│  Submitted  Auto-check  Review   Approved                                    │
│                                                                              │
│  ✓ Phone verified                        12 Aug                              │
│  ✓ Email domain verified                 12 Aug                              │
│  ✓ GSTIN verified — active since 2021    12 Aug                              │
│  ◐ Address verification    in review     est. 4h                             │
│  ○ Bank verification       not started   [Start →]                           │
│                                                                              │
│  ⓘ Reaching Business Verified improves your search ranking and unlocks       │
│    your full profile.  [What each tier unlocks →]                            │
```

Each check shows its own state, date and (where relevant) what it proved. Blocked items show the exact action needed. **Never show a bare "Pending" with no explanation** — that generates a support ticket every time.

## W11 · Verification document upload

Drag-and-drop zone per document type, with an explicit list of accepted types and a size limit. Each uploaded file shows a thumbnail, the scan status (scanning → clean), and OCR-extracted fields for the user to confirm or correct before submission. A privacy line states plainly: who can see this document, how long it is kept, and that it is used only for verification. Errors are specific ("this looks like a bank statement, not a GST certificate") rather than generic.

## W12 · Manual review dashboard (internal)

Three panes: queue (left, sorted by risk × SLA age, with filters) · evidence (centre: document viewer with zoom, alongside extracted fields and the registry response, differences highlighted) · decision (right: risk score with the individual signals that fired and their contributions, decision buttons, mandatory reason selector, free-text notes, escalate). Keyboard shortcuts for approve/reject/next — reviewer throughput is a real operational cost and shortcuts pay for themselves in a week.

## W13 · Provider profile management

Tabs: Profile · Services · Locations · Media · Verification · Team. A completeness meter with the specific next action ("Add 3 more photos to reach 80%"). A live preview toggle showing exactly how the profile appears in search results and on the profile page. Entitlement limits shown inline ("3 of 5 categories used — upgrade for unlimited").

## W14 · Subscription pricing

Three columns, Professional highlighted as recommended, monthly/annual toggle showing the annual saving. Each plan lists included lead volume, category and location limits, verification tier eligibility, and features. A comparison table below for detail. FAQ addressing the three questions that actually block purchase: what counts as a lead, what happens if I exceed it, can I cancel.

## W15 · Subscription checkout

Order summary (plan, billing period, subtotal, GST, total) · GSTIN field for input credit · a plain statement of what happens next · `[Proceed to payment]` handing off to Razorpay's hosted checkout. Loading state during redirect. Trust markers: secure-payment note, cancellation policy, support contact.

## W16 · Payment success / pending

Because entitlements are granted on the webhook, the success screen must handle the brief window where payment succeeded but the webhook has not landed: show "Confirming your payment…" with a polling indicator, then resolve to the activated state. **Never** show "Activated" based on the frontend callback. If confirmation takes more than ~30 seconds, show a reassuring message with a support link rather than a spinner that appears stuck.

## W17 · Project workspace

```
│  My Clothing Brand                          Idea · Bengaluru · ₹10L  [⚙] │
│  ─────────────────────────────────────────────────────────────────────── │
│  Requirements  │  Shortlist  │  Tasks  │  Notes  │  Documents            │
│                                                                          │
│  ☑ Commercial retail space        3 saved · 1 contacted            ▾    │
│  ☐ Wholesale suppliers            5 saved                          ▸    │
│  ☐ Company registration           not started                      ▸    │
│  ☐ GST registration               not started                      ▸    │
│  [+ Add requirement]                                                     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ ⬡ Ask Vertex about this project...                            [↑]  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
```

The embedded Vertex input carries project context automatically — this is the feature that makes a project worth returning to.

## W18 · Networking home (members only; non-members see a locked preview)

```
│  Networking                                          Bangalore Chapter │
│  ─────────────────────────────────────────────────────────────────── │
│  Your Trust Score  742      Growth Points  1,280      Level: Growth   │
│                                                                        │
│  Community Feed                                    [Post an update]  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Kavitha helped ABC Interiors close a ₹3,20,000 project           │ │
│  │ Rohan • New client acquired this week                            │ │
│  │ TGL Verified: Sharma Textiles                                    │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  [Give a Referral]   [Request a Referral]   [Post to Need Board]     │
└────────────────────────────────────────────────────────────────────┘
```

Non-member state: same layout, feed blurred/sampled, a single prominent `[Become a TGL Member]` card explaining the event-registration path (Doc 01 §13.1) instead of a bare paywall.

## W19 · Member directory

Tabs: Directory · My connections · Mentorship · Requests. Directory shows member cards (name, headline, Trust Score, Growth Points badge, stage, industry tags, chapter, mutual connections) with `[Connect]` opening a modal that **requires** a note, and a `?sort=match` option surfacing the match-score composite (Doc 01 §10.5) as plain-language reasons, not a number ("Same industry · 3 stages ahead · Bangalore Chapter") — a raw 0.82 means nothing to a member and invites arguments. Filters by industry, stage, chapter. Mentorship mode: find a mentor / offer mentorship, with capacity shown ("2 of 3 mentee slots open").

## W20 · Member profile

```
│  [Logo]  Sharma Textiles                          ✓ TGL Verified     │
│  Founder: Kavitha R · Bangalore Chapter                              │
│  Trust Score 742 · Growth Points 1,280 · Level: Growth               │
│                                                                        │
│  Referrals Given 34 · Received 21 · Closed 12                        │
│  Reviews ★4.7 (18)   Awards 🏆 Community Champion 2025                │
│                                                                        │
│  Founder Story · Weekly Activity · Achievements                      │
│  [Send Connection Request]   [Give a Referral]                       │
```

LinkedIn-profile + BNI-relationship-history + Trustpilot-rating, in one view (Doc 01 §10.2) — every number on this screen must be explainable by tapping it (e.g. Trust Score opens the contributing-factors breakdown, never just a bare number).

## W21 · Business referral tracker

A kanban-style board of the referral lifecycle (Doc 01 §10.3): `Given → Accepted → Meeting Done → Business Closed → Revenue Generated`, plus a **Business Need Board** tab listing open requests ("Need a manufacturer in Coimbatore") that any member can respond to. Distinct from — and visually distinguishable from — the growth/acquisition referral dashboard below (W22), so members never confuse the two features.

## W22 · Leaderboards

Toggle: Weekly / Monthly / Yearly × Chapter / National (Doc 01 §10.6–§10.7). Ranked list by the selected metric (Growth Points, referrals given, Trust Score), each row showing the member's chapter badge. A banner during an active TGL event season links to the corresponding city/national award category.

## W23 · Events

List/calendar of upcoming and past TGL events by city, each card showing season, venue, registration status. Event detail: description, participating businesses, gallery (past events), `[Register]` → the account-first event-registration flow (Doc 04 §4.1a). A post-registration confirmation screen states plainly: "Your registration is confirmed. Networking unlocks after the TGL Grand Finale on 5 December 2026." After admin-recorded Grand Finale completion, membership is active for 3 calendar months.

## W24 · Awards

Grid of award categories (Community Champion, Referral Champion, Most Trusted Business, …) filterable by City / National and by year, each linking to the winning member/vendor profile. A "how awards are decided" disclosure states the ~70% algorithmic / ~30% committee-reviewed split (Doc 01 §10.7) — this transparency is what keeps the leaderboard trusted.

## W25 · Growth/acquisition referral dashboard

Referral link with copy button and share targets (WhatsApp first — it is how this will actually spread in India) · a funnel strip (Clicks → Signups → Qualified → Converted) · a rewards summary (earned / pending / paid, with the clawback window explained) · a table of individual referrals with status. **This is the Doc 01 §9 acquisition program, not the business referral tracker in W21** — label it distinctly in the UI (e.g. "Invite & Earn") to avoid member confusion between the two referral concepts.

## W26 · Growth/acquisition referral detail

Timeline of the referral's state transitions with dates, the current reward state, and the clawback expiry. If rejected, the reason is stated plainly. Transparency here prevents the "where is my reward" support load that every referral programme generates.

## W27 · Resources

Filterable grid by type (guide/template/checklist/funding) and by category, with a search box. Cards show type, title, reading time and category tags. Resource pages are server-rendered with structured data for SEO, a table of contents, and a related-providers module at the foot — the resource is an acquisition surface and should route to supply.

## W28 · Podcasts

Filterable grid (founder interviews, business interviews, expert discussions, education) with a media player, linking out to related business/member/event profiles (Doc 01 §14.3). Reached from Vertex home and from profiles, never a top-level tab (Doc 01 §4.2).

## W29 · Admin dashboard

Left nav: Overview · Users · Businesses · Verification queue · Fraud cases · Subscriptions & Payments · Reviews · Complaints · Categories · Resources · Growth Referrals · **Memberships · Trust Score review queue · Business referrals · Chapters · Events · Awards committee · Podcasts** · Audit logs · System health.

Overview shows: new signups and businesses (today/7d/30d), verification queue depth and SLA breaches, MRR/ARR and churn (both Vertex provider subscriptions and TGL Membership, shown separately — Doc 04 §4), **membership renewal rate by cohort**, open fraud cases, DLQ depth, error rate, and AI spend against budget. Every list view has filters, saved views, CSV export (audit-logged), and bulk actions gated by role.

**Trust Score review queue** (new, Doc 01 §0/§10.2): every negative `trust_score_events` row with `requires_review = true` and no `reviewed_at` sits here until a human approves or dismisses it — this queue is the literal enforcement mechanism for "no automatic, unreviewed penalty," so it cannot be optional tooling shipped later; it ships with Trust Score itself. **Awards committee** view: pending `awards` rows with `committee_reviewed = false`, side-by-side with the algorithmic score, for the ~30% human check (Doc 01 §10.7).

**Admin permissions are per-section, not global.** A support agent sees Users and Complaints; a reviewer sees Verification and Fraud; only a super admin sees Payments and Audit logs. Every admin action writes an audit row (Doc 03 §7).

---

# 4. Interaction model summary

| Interaction | Behaviour |
|---|---|
| Submit query | Optimistic user message → SSE stream → progressive stage reveal |
| Correct an inferred entity | Inline chip edit → re-runs retrieval only (not the full pipeline) |
| Expand a requirement | Lazy-loads that requirement's providers |
| Refine | Delta applied to the stored structured query; results re-rank in place with a subtle transition, never a full page reload |
| Save provider | Optimistic; rolls back with a toast on failure |
| Contact provider | Modal with a prefilled message; quota shown before sending |
| Save as project | Modal prompting a name, prefilled from the query; everything carries over |
| Error mid-stream | Inline error card in the conversation with a retry, keeping everything already streamed |
| Rate limited | Friendly card explaining the limit and offering sign-up (anonymous) or upgrade (authenticated) |
