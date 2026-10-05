# TGL · Document 01
## Product Definition, Taxonomy, Journeys, Membership, Networking, Vertex Marketplace Model, Trust

**Scope of this document.** TGL is one platform, two products: **Networking** (members-only community — §10) and **Vertex** (open business-journey marketplace — §1–§9). §11–§15 cover what wraps around both: Projects, Resources, Membership, Events/Awards/Podcasts, and user types. See Doc 00 §0.2 and §0.2a for the platform-level framing and brand history (including why an earlier working name, "BGI", no longer exists as a separate brand — it is now the Vertex module).

---

# 0. Product principle (binding on every feature decision below)

Every feature proposed for either module is filtered through one question: **does this build trust, or does it build business?** If it does neither, it does not belong, regardless of how much engagement it might generate.

**Explicitly out of scope, by product decision, not by phase:**

| Do not build | Why |
|---|---|
| Another social-media-style feed | TGL is a business accountability and referral ecosystem, not an entertainment feed. Activity posts exist to create visibility and accountability ("closed ₹3.2L project"), not to maximise scroll time |
| Another generic business directory | Both modules exist because directories don't convert — Vertex adds requirement-generation and verification; Networking adds trust and warm introduction |
| An endless AI chatbot | AI guides, vendors deliver. The AI's job is to shorten *problem → provider → enquiry*, never to become a general-purpose conversation partner (Doc 02 §2.4 "out of domain" handling) |
| A bare vendor/member list | Every listing — provider or member — carries verification/trust context, not just contact details |
| Gamification with no business purpose | Points are awarded for **impact** (a completed referral, a genuine review, an award) not for **activity** (a post, a like). See §10.4 |
| Automatic, un-reviewed reputation penalties | Trust Score can decrease, but never without a human-review step — an unreviewed accusation system is both a trust liability and a fairness problem |
| Features that cannot be measured | If there's no metric that shows whether it worked, it does not ship |

---

# 1. Product definition — Vertex

## 1.1 The two sides

| | **Demand — Users** | **Supply — Businesses (Providers)** |
|---|---|---|
| Who | Aspiring founders, early-stage owners, expanding SMBs | Suppliers, manufacturers, landlords, consultants, agencies, SaaS vendors, professionals |
| Job to be done | "I don't know what I need, who's good, or what it costs" | "I need qualified leads from people who are actually starting something" |
| Pays | No (free) at MVP | Yes — subscription |
| Success metric | Provider contacted, project progressed | Qualified leads received, conversion |
| Cold-start difficulty | Medium (marketing solves it) | **Hard (only manual recruitment solves it)** |

## 1.2 Why an entrepreneur uses Vertex instead of Google

Google answers the question you know how to ask. The defining condition of a first-time founder is **not knowing which questions to ask**. Vertex's value is requirement generation: turning one sentence of intent into a structured, prioritised, sequenced list of everything that intent implies — then filling that list with verified providers and keeping it as a living workspace.

## 1.3 Why a provider pays

| Provider objection | Vertex's answer |
|---|---|
| "I already get leads from JustDial/IndiaMART" | Those are broadcast enquiries. Vertex leads arrive with business type, stage, location, budget band and stated requirement — pre-qualified by the intent pipeline. |
| "Directories don't convert" | Vertex shows the provider a project context, not an anonymous phone number. |
| "Everyone claims verified" | Verification tier is visible, evidence-backed, and materially affects rank. |

**This promise is a product obligation.** If Vertex passes unqualified leads, providers churn in one cycle. Lead quality is the retention metric, not lead volume — see Doc 06 KPIs.

---

# 2. Category taxonomy

## 2.1 Structure

Three levels: **Domain (L1) → Category (L2) → Subcategory (L3)**. L3 is where providers actually attach. L1/L2 exist for navigation, requirement generation and reporting.

Every node carries: `id`, `slug`, `parent_id`, `path` (ltree), `name`, `description`, `synonyms[]`, `search_aliases[]`, `typical_business_stages[]`, `typical_budget_band`, `embedding`, `is_active`, `display_order`.

**`synonyms` vs `search_aliases`:** synonyms are true equivalents used for query expansion and embedding enrichment ("CA" ≡ "chartered accountant"). Search aliases are *user-language* variants that are not strictly synonymous but should match — "shop rent", "kirana space", "godown" → warehouse. Keeping them separate stops a fuzzy alias from polluting the semantic embedding of the node.

## 2.2 The taxonomy (v1)

```
L1: PHYSICAL INFRASTRUCTURE                    [INFRA]
  L2: Commercial Rentals          → retail space, shop, showroom, kiosk, mall unit
  L2: Office Space                → private office, coworking desk, managed office
  L2: Warehousing & Storage       → warehouse, godown, cold storage, fulfilment centre
  L2: Utilities & Fit-out         → electrical, plumbing, interior fit-out, signage
  L2: Equipment                   → machinery purchase, equipment rental, leasing

L1: SUPPLY CHAIN                               [SUPPLY]
  L2: Manufacturers               → garment mfg, food processing, contract mfg, private label
  L2: Wholesalers & Distributors  → wholesale apparel, FMCG distribution, B2B trading
  L2: Raw Materials               → textiles & fabric, packaging materials, food ingredients
  L2: Packaging                   → boxes & cartons, labels, sustainable packaging
  L2: Logistics                   → last-mile, freight, 3PL, courier aggregation, cold chain

L1: BUSINESS SERVICES                          [BIZSVC]
  L2: Legal                       → company law, contracts, IP & trademark, litigation
  L2: Accounting & Taxation       → bookkeeping, GST filing, income tax, audit, payroll
  L2: Registration & Licensing    → company incorporation, GST reg, FSSAI, trade licence, Udyam
  L2: Consulting                  → business strategy, ops consulting, franchise consulting
  L2: Marketing & Branding        → digital marketing, brand identity, content, PR, photography

L1: TECHNOLOGY                                 [TECH]
  L2: Point of Sale               → retail POS, restaurant POS, billing software
  L2: Inventory & Operations      → inventory mgmt, warehouse mgmt, ERP
  L2: CRM & Sales                 → CRM, sales automation, lead management
  L2: E-commerce                  → storefront platforms, marketplace onboarding, D2C enablement
  L2: Payments & Fintech          → payment gateway, POS terminals, invoicing, business banking
  L2: Web & Software              → website development, app development, custom software
  L2: Business SaaS               → HR software, accounting software, comms tools

L1: HUMAN RESOURCES                            [HR]
  L2: Recruitment                 → permanent hiring, blue-collar hiring, executive search
  L2: Staffing                    → temp staffing, contract staffing, gig workforce
  L2: Payroll & Compliance        → payroll processing, PF/ESI, labour compliance
  L2: Training                    → skill training, sales training, compliance training
```

**Category ID convention:** `INFRA.RENTAL.RETAIL`, `SUPPLY.MFG.GARMENT`, `BIZSVC.TAX.GST`. Human-readable, stable, sortable, and directly usable as an ltree path. Never renumber; deprecate with `is_active = false` and a `superseded_by` pointer.

## 2.3 Category embedding strategy

Each L3 node is embedded from a composed document, not from its name alone:

```
{name}. {description}. Also known as: {synonyms}. 
Commonly needed by: {typical_business_types}. 
Typically required at: {business_stages}. 
Example needs: {3-5 real user phrasings}
```

The "example needs" line is what makes semantic matching work for real queries. "I need someone to do my GST" is far closer to that composed document than to the bare string "GST filing".

Re-embed the whole taxonomy whenever the embedding model changes, and version it: `category_embeddings(category_id, model_version, embedding)`. Never mix embedding models in one index — the vectors are not comparable, and the failure is silent.

---

# 3. User (demand-side) journey

```
Landing → Role selection → Registration → Profile setup → Vertex home
  → Search by requirement/category/location → Results
  → Provider profile → Save / Compare / Contact
  → My Projects → Shortlist & plan → (if a TGL Member) Networking
```

Networking is reached from Vertex, not the other way round, because Vertex is the open, no-membership-required surface — it is the wider funnel that a Networking membership sells into, not a feature bolted onto the community.

## 3.1 Screen-by-screen

| # | Screen | Purpose | Key actions | Success signal |
|---|---|---|---|---|
| U1 | Landing | Explain the product in one screen | Try a sample query, sign up | Query attempted |
| U2 | Role selection | Route to the correct onboarding | "I need services" / "I provide services" | Correct role chosen |
| U3 | Registration | Create account | Email+password, Google OAuth, phone OTP | Account created |
| U4 | Profile setup (progressive) | Collect personalisation signal without a wall | Business stage, interest area, city — all skippable | Completed or skipped fast |
| U5 | **Vertex home** | The product | Search by service, category, or business requirement | Query submitted |
| U6 | (Phase 3) AI Assistant | Guided requirement generation | Answer AI questions to find requirements | Reaches provider |
| U7 | Requirements view | Turn intent into a checklist | Expand a requirement, dismiss one, add one | ≥1 requirement expanded |
| U8 | Results | Providers matching search/requirement | Filter, sort, save, compare | ≥1 provider viewed |
| U9 | Provider profile | Evaluate | Read, check verification, save, contact | Contact initiated |
| U10 | Compare | Decide between 2–4 | Side-by-side attributes | Selection made |
| U11 | Contact | Convert | Reveal contact / send enquiry | Enquiry sent |
| U12 | My Projects | Retain | Create project, organise shortlist, track tasks | Project revisited |
| U13 | Networking (members only) | Community, trust, business referrals | Member directory, give/receive a referral, weekly update | Referral tracked to a stage |
| U14 | Growth referrals (acquisition) | Bring a new user or provider into TGL | Share link, track status | Referral converted |
| U15 | Resources | Support + SEO | Read guide, download template | Return visit |

**Two different things are both called "referrals" in this product and must not be conflated in code or copy:** **U13 Networking referrals** are one member introducing a business opportunity to another member (Given → Accepted → Meeting Done → Business Closed → Revenue Generated — §10.3), tracked for Trust Score and community value. **U14 Growth referrals** are the standard bring-a-friend acquisition mechanic (§9) with a cash/credit reward and a fraud clawback window. They have separate data models (Doc 03) and separate screens (Doc 05 W20/W21 vs. the Networking referral tracker, §10.3).

**Registration timing is a product decision.** Let anonymous users run **one full query** before asking for an account. The value must be demonstrated before the wall. Rate-limit anonymous queries hard by IP + fingerprint (Doc 04 §Rate limiting) — this is your most expensive endpoint and the most obvious abuse target.

---

# 4. Navigation

TGL's navigation spans **both** products plus the surrounding modules, and is deliberately kept to five destinations so the app does not feel crowded — a lesson taken directly from how the tab set was pared down during design.

## 4.1 Bottom tab bar (mobile — primary surface) / left nav (desktop)

| Tab | Who sees it | Contents |
|---|---|---|
| **Vertex** | Everyone (public + members) | Search, categories, business-stage journeys, requirement results, vendor profiles, enquiries, reviews, My Projects |
| **Networking** | Members (public sees a locked/join preview) | Feed, member directory, referrals, leaderboard, my dashboard, recognition |
| **Events** | Everyone | Upcoming/past TGL events, registration, event info, galleries |
| **🔔 Notifications** | Logged-in users | Referrals, enquiries, events, achievements, updates — role- and category-scoped (Doc 03 §6) |
| **👤 Profile** | Logged-in users | Personal/business profile, membership status, settings |

## 4.2 Reachable from within, not a top-level tab

| Item | Reached from |
|---|---|
| **Awards** | Events, Networking, and member/vendor profiles (an award is content that lives on the profile it was earned by, not a destination in its own right) |
| **Podcasts** | Vertex home and profiles |
| **My Projects** | Inside Vertex (project list → workspace) |
| **Resources** | Inside Vertex (guides, templates, funding) |

**Why not eight top-level tabs.** Vertex, Networking, Events, Awards, Podcasts, Notifications and Profile were all candidate top-level destinations. Awards and Podcasts are *content types that attach to other things* (a business, a member, an event), not independent user journeys — putting them in the bar dilutes the five destinations people actually return to daily. This mirrors the reasoning that cut U13/U14 below out of the sidebar in v1.0 of this document, generalised to the whole app.

**Public vs. member surface.** A public (non-member) visitor gets the full five-tab bar, but Networking renders as a locked preview ("Become a TGL Member") rather than being hidden — hiding it entirely would hide the product's second half from the exact audience most likely to convert into it (Doc 01 §13 Membership).

---

# 5. Business (supply-side) journey

```
Role selection → Business registration → Business information → Category selection
  → Location → Contact details → Documents → Verification
  → Subscription selection → Payment → Profile completion → Approval → Dashboard
```

## 5.1 Onboarding states (backend)

| State | Meaning | Entered by | Exits to |
|---|---|---|---|
| `DRAFT` | Account created, profile incomplete | Registration | `PENDING_VERIFICATION` |
| `PENDING_VERIFICATION` | Submitted, verification running | Provider submits | `VERIFIED` / `NEEDS_INFO` / `REJECTED` |
| `NEEDS_INFO` | Something is missing or unreadable | Automated check or reviewer | `PENDING_VERIFICATION` |
| `VERIFIED` | Passed at some tier | Automated or reviewer | `ACTIVE` |
| `REJECTED` | Failed with a stated reason | Reviewer | `DRAFT` (appeal) |
| `ACTIVE` | Live and discoverable | Subscription active + profile complete | `PAUSED` / `SUSPENDED` / `EXPIRED` |
| `PAUSED` | Provider-initiated hide | Provider | `ACTIVE` |
| `SUSPENDED` | Platform-initiated (fraud, abuse, disputes) | Moderator | `ACTIVE` / terminated |
| `EXPIRED` | Subscription lapsed | Billing | `ACTIVE` on renewal |

**Critical sequencing decision: allow profile creation and verification *before* payment.** Asking an Indian SMB owner to pay before they have seen their own listing is a conversion killer. Let them build the profile, complete verification, see the preview, then hit the paywall to go live. Verification cost is real, so protect it with a rate limit on verification attempts per account and per document hash.

## 5.2 Provider dashboard (first screen after approval)

Leads received (with source) · profile views · search impressions · verification tier and what the next tier unlocks · subscription status · response rate and response time (both public) · profile completeness score with the exact next action.

Response rate and time being **publicly visible** is deliberate: it is the cheapest possible mechanism for enforcing lead-quality reciprocity. Providers who ignore leads lose rank automatically, without a human policing anything.

---

# 6. Vertex provider subscription model

**Not to be confused with TGL Membership (§13).** This is what a *Vertex provider* pays for listing/leads. TGL Membership is what a *Networking member* pays (or receives free with event registration) for community access. A single business can pay for both, on two separate subscription rows (Doc 03).

## 6.1 Pricing strategy (not prices)

**Pricing dimensions**, in the order they should be used:

1. **Lead volume** — the thing the provider actually buys. Primary meter.
2. **Category breadth** — how many L3 categories the provider can list under.
3. **Location breadth** — how many service areas.
4. **Visibility features** — priority placement (see the trust caveat in §8.3), featured badge.
5. **Profile richness** — media, catalogue items, documents, case studies.
6. **Team seats** — for agencies with multiple staff.
7. **Analytics depth** — basic counts vs. search-term and competitive insight.

**Do not price on "listings."** Price on **qualified leads delivered**, because that is the value received and it aligns Vertex's incentives with the provider's. A provider who receives zero leads on a paid plan should be able to see that plainly — and Vertex should feel it, because that provider will churn.

## 6.2 Feature matrix (structure; example numbers are illustrative only)

| Capability | Basic | Professional | Enterprise |
|---|---|---|---|
| Public profile | ✓ | ✓ | ✓ |
| L3 categories | 1 | up to 5 | unlimited |
| Service locations | 1 | up to 5 | unlimited |
| Qualified leads / month | low cap *(e.g. 10)* | higher cap *(e.g. 50)* | unlimited / negotiated |
| Verification tier eligible | Contact Verified | Business Verified | Fully Verified |
| Media (images/video) | 3 | 20 | unlimited |
| Catalogue items | — | ✓ | ✓ |
| Priority placement | — | ✓ (disclosed) | ✓ (disclosed) |
| Analytics | Views, leads | + search terms, conversion | + competitive benchmarks, API |
| Team seats | 1 | 3 | custom |
| Support | Email | Priority email | Named contact, SLA |
| Overage | Blocked | Pay-per-lead | Negotiated |

*All numbers above are **examples** to show the shape of the tiering, not recommended prices. Set real numbers after measuring actual lead volume in the first 90 days — pricing before you know your lead-delivery capacity is guessing.*

## 6.3 Billing lifecycle rules

| Event | Behaviour |
|---|---|
| **Trial** | 14-day full-feature trial, no card required, hard feature lock at expiry (not a silent downgrade — silent downgrades generate support tickets and distrust) |
| **Upgrade** | Immediate, prorated, entitlements applied on the webhook — never on the redirect |
| **Downgrade** | Takes effect at period end; entitlements above the new plan are marked `pending_removal` with an explicit warning showing exactly what will be lost |
| **Failed payment** | Dunning: retry D+1, D+3, D+7; provider notified each time; grace period to D+7; `EXPIRED` at D+8 with profile hidden but **all data retained** |
| **Cancellation** | Effective at period end; profile hidden; data retained per the retention policy; one-click reactivation |
| **Refunds** | Policy decision, executed only through the provider's dashboard with an audit record. Never partial-refund by hand in the payment console — that path leaves no trace in your system |
| **Invoices** | Generated server-side on `payment.captured`, GST-compliant, immutable, stored in S3, linked from the dashboard |
| **Tax** | GST on SaaS to Indian businesses; B2B customers need their GSTIN captured for input credit. **[VALIDATE with a CA — the GSTIN field on the invoice is a legal requirement, not a nice-to-have]** |
| **Entitlements** | Materialised in a table, derived from webhook-confirmed subscription state, cached in Redis with a short TTL, checked server-side on every gated action |

**The entitlement rule:** the frontend may hide a button. Only the API may decide. Every gated endpoint independently checks entitlements. A hidden button is UX; an unchecked endpoint is a vulnerability.

---

# 7. Marketplace monetisation and the trust conflict

| Model | Fit for Vertex | Note |
|---|---|---|
| **Provider subscriptions** | **Primary** | Predictable, no transaction scope, aligns with A3 |
| Pay-per-qualified-lead | Secondary, as overage | Requires an airtight "qualified" definition and a dispute process |
| Premium placement | Tertiary, **only if disclosed** | See below |
| Sponsored visibility | Later | Same disclosure rule |
| Referral fees from providers | Later | Creates a ranking conflict — treat carefully |
| Transaction / take rate | **Out of scope** | Triggers payment-aggregator scope (Doc 00 A3) |
| Premium entrepreneur features | Later | Do not tax the demand side before the flywheel spins |

## 7.1 The paid-placement conflict, resolved explicitly

A marketplace that lets money buy rank destroys its own result quality, and users detect it faster than operators expect. Vertex's rule:

1. **Paid placement occupies reserved, visually distinct slots** — labelled "Promoted", above or inside the list but never blended into it.
2. **Paid placement never alters the organic ranking function.** Not a weight, not a tie-breaker, not a boost.
3. **A provider must meet a minimum quality bar to buy placement** — verification tier, response rate above threshold, no open disputes. You cannot buy your way past being bad.
4. **Promoted slots are capped** at a fixed fraction of visible results (recommend ≤20%).
5. **The policy is published** on a public page.

Build this rule into the ranking service before selling a single placement. Retrofitting ad slots into a ranker is how ranking quality dies — because once revenue depends on the boost, nobody is allowed to remove it.

---

# 8. Trust framework — Vertex provider verification

**Not to be confused with Networking's Trust Score (§10.2).** This section covers *provider* (vendor) verification — is this business real, and how much of it has TGL confirmed. §10.2 covers *member* reputation — has this person been a good actor in the community. A business can hold both: a T2 Vertex verification tier **and** a Networking Trust Score, on the same underlying `businesses` row, because the same business can be both a Vertex-listed provider and a Networking member. The **TGL Verified** badge (§10.2, criteria owned by TGL admin, typically event-participation-linked) is a third, separate flag that can appear on either profile type.

## 8.1 Verification tiers

| Tier | Badge | Requirements | Rank effect | Profile unlocks |
|---|---|---|---|---|
| **T0 Registered** | grey | Email verified only | Baseline (low) | Minimal profile |
| **T1 Contact Verified** | blue | + phone OTP + business email domain match | Small positive | Contact reveal enabled |
| **T2 Business Verified** | green | + GSTIN **or** CIN **or** UDYAM validated against the registry + address confidence | Meaningful positive | Full profile, catalogue |
| **T3 Fully Verified** | gold | + bank penny-drop + director/proprietor ID + document review passed | Strongest positive | Featured eligibility, Enterprise features |

Tiers are **re-evaluated**, not permanent: GSTIN status can change, directors can be disqualified, bank accounts close. Re-verification cadence: T2 every 12 months, T3 every 6 months, plus event-driven re-checks on registry-status change where the vendor supports webhooks. A tier that expires drops the provider to the tier below with a notification, not silently.

## 8.2 Trust signals beyond verification

| Signal | Source | Gameable? | Mitigation |
|---|---|---|---|
| Verification tier | Registry + review | Hard | Evidence retained, audited |
| Business age | Registry incorporation/GST date | No | — |
| Review rating | Users | **Yes** | Anti-fraud system §9 |
| Review count | Users | Yes | Same |
| Response rate | Platform-observed | Slightly | Measure on platform-initiated contacts only |
| Response time | Platform-observed | Slightly | Median, not mean; rolling 90-day window |
| Completed projects | User confirmation | Yes | Both-sides confirmation required |
| Dispute history | Platform | No | Weighted negatively, decays over time |
| Profile completeness | Platform | No | Weak positive signal only |
| Platform activity | Platform | Yes | Weak signal only; never a primary ranking factor |

**Design rule:** platform-observed behavioural signals are worth more than self-reported ones, and registry-verified facts are worth more than both. Weight accordingly (Doc 02 §Ranking).

## 8.3 Anti-review-fraud architecture

| Attack | Detection | Response |
|---|---|---|
| Fake positive reviews (self/paid) | New accounts, no interaction history with that provider, burst timing, similar text embeddings, shared device/IP | Hold for moderation; do not count toward rating |
| Competitor attack (fake negatives) | Reviewer has no contact record with the provider; cluster of negatives in a short window; reviewer account age | Hold; notify provider; investigate |
| Incentivised reviews | Text-similarity clustering; referral-graph proximity between reviewer and provider | Flag; enforce policy |
| Repeat reviews | One review per (user, provider, project) enforced at the DB level with a unique constraint | Blocked at write time |
| Bot reviews | Rate limits, device fingerprinting, behavioural signals | Blocked or held |

**Core structural defence: reviews require a verified interaction.** A user can only review a provider they actually contacted through Vertex, on a recorded contact event, after a cooling period. This eliminates the majority of review fraud at the schema level rather than at the moderation level — which is the only place it can be eliminated cheaply.

Moderation flow: `SUBMITTED → AUTO_SCREEN → (PUBLISHED | HELD) → HUMAN_REVIEW → (PUBLISHED | REJECTED)`. Provider gets a right of reply (published alongside, never replacing). Ratings are displayed with count and distribution — never a bare star average, which hides a 5.0-from-one-review.

---

# 9. Growth referral system (acquisition — distinct from Networking referrals)

This is the standard bring-a-friend acquisition mechanic — a user or provider invites someone new to TGL and earns a reward once that signup converts. **This is not the same feature as a Networking member referring a business opportunity to another member** (§10.3); see the callout at the end of §3.1. This section covers acquisition only.

```
Referrer → referral link/code → prospect lands → signup (attributed)
  → qualified (business registered + verification submitted)
  → converted (first payment) → reward (after clawback window)
```

## 9.1 States and rules

| State | Trigger | Notes |
|---|---|---|
| `CREATED` | Referrer generates a code | Unique, non-guessable |
| `CLICKED` | Link opened | First-touch attribution stored |
| `SIGNED_UP` | Account created with attribution | Attribution window: **30 days**, first-touch |
| `QUALIFIED` | Referee submits verification | Prevents rewarding junk signups |
| `CONVERTED` | First successful payment | Reward becomes claimable |
| `REWARD_PENDING` | Clawback window running (**30 days**) | Protects against refund/chargeback abuse |
| `REWARD_PAID` | Window elapsed | Recorded, audited |
| `REVERSED` | Refund, chargeback, or fraud found | Reward clawed back |
| `REJECTED` | Fraud detected | Reason recorded |

**Why reward at CONVERTED plus a clawback window, not at SIGNED_UP:** rewarding signups pays for fraud. Rewarding conversions with a delay pays for revenue.

## 9.2 Anti-fraud

Self-referral detection (device, IP, payment instrument, email similarity, phone) · velocity limits per referrer · circular-referral graph detection · disposable-email-domain blocking · a manual review threshold above which no reward auto-pays · full audit of every state transition. Rewards **never** auto-pay above a set value without human approval.

---

# 10. Networking — the members-only community

Networking is TGL's **business accountability and referral ecosystem** — deliberately not a general networking app. Every design choice below optimises for one outcome per member per week: *"did I give or receive something of real business value here?"* If the honest answer is no for most members for a few weeks running, the product has failed regardless of DAU.

## 10.1 Access model

Membership is what unlocks Networking (full rules in §13). In short: **granted through TGL event participation**, not a self-serve signup, and **not the same thing as Vertex's `TGL Verified` badge** (a business can be a Networking member without being TGL Verified, and vice versa via other admin-controlled verification paths — Doc 01 §8).

`NetworkingProfile` (created automatically on membership grant, distinct from the base `UserProfile`/`BusinessProfile`) carries: business story/founder story, industry tags, business stage, city/chapter, interests, headline, bio, `open_to_mentoring`, `seeking_mentor`, and a visibility setting. **Profile visibility within the directory is opt-in per field** (e.g. a member can show Trust Score but hide revenue-adjacent activity) — full membership is the access gate; field-level visibility is the DPDP purpose-limitation control on top of it (Doc 04 §5).

## 10.2 Member profile, Trust Score and TGL Verified

Every member profile should answer, at a glance: what does this business do, where, founder story, services, categories, awards, referral score, review score, activity score — **LinkedIn profile + BNI relationship history + Trustpilot rating**, in one view. Concretely, a profile surfaces: Trust Score, Growth Points, Membership Level, Referrals Given/Received/Closed, Reviews, Awards, Achievements, Weekly Activity, Founder Story.

**Trust Score** is a single visible number built from meaningful behaviour, never from app usage alone:

| Positive inputs | Negative inputs (require human review before applying — §0) |
|---|---|
| Referrals given and received | False claims |
| Successful business closures | Scam/fraud reports |
| Genuine reviews | Misuse of referrals |
| Community contribution | Unprofessional conduct |
| Profile completeness | Breaking community guidelines |
| Consistent weekly updates | Failure to update a required referral status |
| Rule compliance | Repeated failure to maintain profile/activity standards |
| Verified status | |

Admin can review and override a score. **No automatic, un-reviewed penalty ever reduces a member's standing** (§0) — negative signals route to a human decision, not a formula that silently punishes.

**TGL Verified** is a separate, deliberately scarcer badge from plain membership. It is not automatically granted to every member or every Vertex vendor. The exact criteria are admin-controlled and, at launch, are tied to TGL event participation (e.g. Participant → Finalist → Winner → Speaker → Verified tiers can all surface as badges on the profile). A business can be a Networking member without ever earning TGL Verified.

## 10.3 Referrals (business introductions between members)

Distinct from the acquisition referral program in §9 — this is one member routing a real business opportunity to another. Tracked through explicit stages, each of which is a state change a member can act on:

```
Referral Given → Referral Accepted → Meeting Done → Business Closed → Revenue Generated
```

Every stage is trackable and visible according to community rules (Doc 03 models this as its own state machine, separate from the §9 growth-referral table). **Category-targeted referral requests:** a member can post "I need a lawyer in Bangalore," and relevant members in that category get notified; members who respond quickly and appropriately earn Growth Points (§10.4). A **Business Need Board** generalises this beyond one-off requests — a running list ("Looking for a digital marketing agency," "Need 5,000 custom boxes") that only members can see and respond to, turning the app from a directory into a standing opportunity engine.

## 10.4 Growth Points

Members earn Growth Points through participation that has actual business weight: weekly business updates, giving a relevant referral, responding to a category requirement, a successful referral, community contribution, maintaining required profile information, verified positive activity. Points are cumulative and lifetime (they do not reset). Points are configurable by TGL admin and may optionally be redeemable toward membership renewal (capped — see §13.3, to protect recurring revenue).

**The design rule that keeps this from becoming spam (see §0):** reward *impact*, not *activity*. Points may decrease for confirmed misuse, scam/fraud reports, false claims, serious unprofessional conduct, guideline violations, failure to maintain required profile information or failure to update referral status.

| Action | Points weight |
|---|---|
| Successful referral | High |
| Winning an award | High |
| Receiving a genuine review | Medium |
| Helping another member solve a problem | Medium |
| Weekly business update | Small |

If every action gives equal points, members start posting low-quality updates purely to farm them. Weighting by outcome is what keeps the leaderboard meaning something.

## 10.5 Member directory and matching

A weighted composite, deliberately not an ML model at MVP:

```
match_score =
    0.25 · industry_overlap        (shared L2 categories)
  + 0.20 · stage_complementarity   (mentor ahead of mentee; peers at the same stage)
  + 0.20 · location_proximity      (same chapter/city > same region)
  + 0.15 · interest_overlap
  + 0.10 · activity_recency        (active users only — dead profiles poison the experience)
  + 0.10 · mutual_connections
```

Mentorship uses `stage_complementarity` inverted: a mentor should be 2+ stages ahead, in an overlapping industry, with an `open_to_mentoring` flag and capacity limits (max active mentees) so mentors are not swamped and quietly leave.

**Stated future direction, not MVP:** an **AI Business Match** surface ("you should meet these 5 members," based on industry, location, requirements, past referrals) sitting on top of this scoring function — and, longer-term, on the same intelligence service that powers Vertex's requirement generation (Doc 00 §0.5, Doc 02). Do not build this before the deterministic composite above is live and trusted; the composite is what makes the AI layer explainable later.

**Location-aware, not location-locked.** Referral requests default to same-chapter members, but a request such as "need a manufacturer in Coimbatore" should notify relevant members there regardless of chapter — the network's value comes from being nationally connected, not siloed per city. A travelling member can optionally surface "you're visiting Hyderabad — here are 25 TGL members nearby."

## 10.6 Structure: city chapters and the national community

Do not build multiple separate city communities. Build **one national TGL community with city chapters**:

```
TGL India
├── Bangalore
├── Chennai
├── Hyderabad
├── Mumbai
├── Delhi
```

Every member belongs to both their city chapter and the national community. A city chapter activates only once it reaches a healthy member count (illustratively 100+ active members — VD-9 in Doc 00); below that threshold, members participate in the national feed while still seeing chapter-relevant content, rather than a chapter that feels dead from day one. This structure is what lets the community scale from hundreds to thousands of members without a later redesign, while still supporting local recognition (see §10.7).

## 10.7 Recognition, leaderboards and awards

Three leaderboard windows — **weekly, monthly, yearly** — each rankable by more than one dimension (most active, top referrer, successful referrals, community contributor, Growth Points). The scoring formula per leaderboard is admin-configurable.

**Recognition categories**, awarded at TGL events and tied back into the member profile:

| Award | Criteria |
|---|---|
| 🏆 Community Champion | Highest overall Growth Points |
| 🤝 Referral Champion | Most verified successful referrals |
| ⭐ Most Trusted Business | Highest Trust Score |
| 🚀 Most Active Member | Consistent weekly participation |
| ❤️ Community Contributor | Most helpful member, verified contributions |
| 🌟 Rising Star | Outstanding new member |
| 📈 Growth Leader | Highest positive growth during the year |
| 💬 Knowledge Leader | Most educational posts/podcasts/workshops |

**Awards are not purely algorithmic.** Recommended split: ~70% measurable app data (Trust Score, Growth Points, verified referrals, consistency), ~30% reviewed by a TGL committee specifically to catch and exclude system gaming. A score with no human check over it is a score someone will eventually learn to farm.

**Two award tiers, mirroring the chapter structure:** city-level awards (e.g. "Referral Champion — Bangalore") at each city's event, and annual **TGL National Awards** aggregating across chapters, giving members something to strive for at both the local and national level.

This is also the closing loop of the ecosystem flywheel in Doc 00 §0.2a: register → join the community → build reputation all year → get recognised at the event → carry that recognition (badges, awards) into the next season's Vertex and Networking profile.

## 10.8 Community activity feed

A structured activity feed, not a social-media timeline: weekly business updates ("completed ₹X of business," "new client acquired," "business milestone," "new product launched"). The purpose is business visibility and accountability, not entertainment or time-on-app — see the product principle in §0. Business milestones (100 clients, 5 years, 10 employees, a new branch) are explicitly celebrated by the community as a recognition surface, feeding the same Growth Points and recognition system above.

## 10.9 Messaging boundaries

Connection request required before messaging · request includes a mandatory note (blank requests are spam) · limits on pending outbound requests · repeated rejections throttle the sender · block and report on every profile · reported users route to the moderation queue · no bulk messaging, ever.

---

# 11. My Projects

The retention surface, and the personalisation source.

```
Project "My Clothing Brand"
├── Meta:      business idea, stage, city, budget band, target launch date
├── Requirements: generated + user-edited checklist, each with status
├── Shortlist:  saved providers grouped by requirement, with notes
├── Comparisons: saved side-by-side sets
├── Tasks:     title, due date, status, linked requirement
├── Milestones: named stage gates with target dates
├── Notes:     free-form, markdown
├── Documents: user uploads (quotes, drafts) — private, S3
├── Contacts:  providers contacted, with dates and outcomes
└── AI context: the project summary injected into future queries in this project
```

**The "AI context" line is the whole point.** Once a user has a project, every subsequent Vertex query inside it is answered with the budget, stage, city and existing shortlist already known. That is the difference between a search box and an assistant, and it is a switching cost a competitor cannot copy by cloning the UI.

Data model detail in Doc 03.

---

# 12. Resources

CMS-like, but **not a CMS at MVP** (see Doc 00 §0.9). Markdown files in the repo, rendered as static pages with ISR, with structured frontmatter:

```yaml
title, slug, type: guide|template|checklist|article|funding
categories: [BIZSVC.REG.GST]
business_stages: [idea, launch]
tags, reading_time, author, published_at, updated_at, version
```

Resources serve three jobs: **SEO acquisition** (highest-intent organic entry point for a marketplace), **user education** (reduces support load), and **recommendation surface** (a query about GST registration should surface the GST guide alongside providers). The category tags are what make the third job work — they let the same retrieval layer serve resources and providers.

Move to a real CMS only when a non-engineer needs to publish weekly.

---

# 13. Membership

TGL Membership is what grants access to Networking (§10). It is deliberately **not** a self-serve purchase.

## 13.1 Access rule

**P0 correction:** Season 1 registration prepares a TGL Networking membership as `PENDING`; payment confirmation does not activate access. Membership activates only after the Grand Finale completion is recorded on 5 December 2026, using that recorded completion timestamp as `starts_at`, and lasts **3 calendar months**. Membership is never sold as a standalone product at launch — the sequence is always *account → profile → business → event registration → confirmed payment → pending membership → Grand Finale completion → active membership*, not *download → pay → in*. This exclusivity is a deliberate differentiator, not a launch limitation (Doc 00 §0.9): a purely pay-to-join community is easy to copy and cheapens the recognition mechanics in §10.7.

**Phase 2 (future, not built at launch):** additional membership pathways — direct application with approval, corporate membership, mentor membership, investor membership — all of which still resolve to the same `TGL Member` role. State this as a documented future option (`membership_pathway` enum with room to grow) rather than hard-coding "event participant" as the only possible value, so Phase 2 is a config/admin change, not a schema migration under pressure.

## 13.2 Renewal pricing (illustrative — validate before launch)

| Duration | Price (incl. GST) | Notes |
|---|---|---|
| 3 months | ₹7,500 | Lets a new member experience the community without a long commitment |
| 6 months | ₹13,500 | Aligns with one TGL season |
| 12 months | ₹24,999 | Best value; encourages long-term participation |

**[ASSUMPTION — VALIDATE before pricing plans in Razorpay, Doc 04 §4]** Pricing should not be set low to chase volume — low pricing reduces perceived value in an intentionally exclusive community and attracts less-committed members, which in turn degrades the referral quality that makes the community worth paying for.

## 13.3 Growth Points redemption cap

Growth Points (§10.4) earned during a membership period may be redeemable as a discount on renewal, **capped at roughly 20–30% of the subscription value**. Do not allow points to cover a renewal fully — the platform needs predictable recurring revenue, and a partial cap still makes points feel rewarding without threatening it.

## 13.4 The KPI that actually matters

Not member count, not downloads, not follower count. **The percentage of members who willingly pay to continue after their free/complimentary period ends.** A community of 5,000 highly engaged members with an 80% renewal rate is healthier — and worth more — than 20,000 members with a 20% renewal rate, because renewal rate is the only honest signal that the community is delivering value nobody can fake. Track this from day one, on the same dashboard as MRR (Doc 06 §6.3).

## 13.5 What a member actually judges the product on

Interviewing the product from a member's point of view surfaces a consistent bar: a member renews if they receive genuine referrals, can find the right person quickly instead of scrolling profiles, the community stays active weekly, they get recognised for contributing, and they can see measurable value (connections, referrals, collaborations, profile views). A member churns if the feed fills with low-value posts, nobody responds to requests for help, notifications become noise, referral claims go unverified, or the app becomes something they rarely open. Every item on both lists maps directly to a section above (§10.3 referral tracking, §10.5 directory/matching, §10.8 activity feed, Doc 03 §6 notification preferences) — treat member-renewal risk as a design input, not a post-launch surprise.

---

# 14. Events, Awards and Podcasts

These three are content surfaces that attach to Networking and Vertex profiles rather than independent products (see Doc 01 §4.2 on why they are not top-level nav tabs). Kept intentionally light here; wireframes in Doc 05, data model in Doc 03.

## 14.1 Events (Season 1)

Events are a core ecosystem module. Public users can view upcoming events, register, see event information, view participating businesses, and see event galleries/content. The December 2026 Season 1 event is a key launch milestone, featuring 10 competition categories, 400 businesses, and 60 finalists, culminating in a Grand Finale in Bengaluru. 

**Season 1 Business Journey:** Register (paid) → Submit business profile → Business evaluation → Selection process → Receive shoot guide → Video production → Digital promotion → Public engagement stage (if finalist) → Grand Finale → Post-event exposure.

**Participant Video Workflow:** Participants provide raw footage (~1 min) according to the TGL shoot guide. The admin can record video submission status, production mode, asset links/files, and approval status.

Events run in multiple cities and are the primary acquisition channel for new TGL Members (§13.1) — the architecture should treat "event → registration → membership grant" as a first-class, auditable pipeline, not a manual side process.

## 14.2 Awards

Winners, recognition, award history, and event-linked awards, all surfaced back onto the member/vendor profile that earned them (§10.7). TGL-produced content (interviews, features) can reference award winners, connecting Awards to Podcasts/Media below.

## 14.3 Podcasts / Media

TGL-produced founder interviews, business interviews, expert discussions and educational content, linkable to vendor profiles, member profiles, events and awards. TGL controls publishing. The broader SkyKeen Media / YouTube channel can distribute the same content — this is a distribution relationship, not a data dependency; Podcasts content lives in TGL's own data model regardless of where it is also published.

## 14.4 Magazine (adjacent, not an app feature at launch)

A physical/editorial magazine connected to featured businesses, winners, entrepreneurs and vendors is part of the broader SkyKeen ecosystem but does not need an in-app publishing system at launch — treat it the same way as Resources (§12): out of scope for a CMS until a non-engineer needs to publish on a real cadence.

---

# 15. User types

| Type | Can do |
|---|---|
| **Public User** | Browse Vertex, search providers, view public profiles, read reviews, view Events, Awards, Podcasts |
| **Networking Member** (TGL Member) | Everything above, plus: member directory, referrals, Trust Score, Growth Points, leaderboards, community feed, member dashboard (§10, §13) |
| **Vendor / Service Provider** (Vertex) | Create/manage a Vertex profile, receive and respond to enquiries, manage services, upload portfolio, receive reviews, track profile performance (§5–§8). Independent of Networking membership — a vendor need not be a member, and a member need not be a vendor, though many will be both |
| **TGL Admin** | Full control over users, members, vendors, categories, verification, reviews, referrals, points, Trust Scores, awards, events, podcasts, content, notifications, subscriptions/membership, reports, analytics (Doc 04 §3.2 maps this onto concrete RBAC roles) |

This table is the product-level statement of roles; Doc 04 §3.2 and Doc 03 §2.1 define the corresponding database roles and permission scopes. The mapping is not 1:1 — for example, `TGL Admin` above spans several narrower RBAC roles (`MODERATOR`, `VERIFICATION_REVIEWER`, `SUPER_ADMIN`) for least-privilege reasons explained there.
