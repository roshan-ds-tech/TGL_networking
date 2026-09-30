# TGL · Document 06
## Roadmap, MVP Scope, Repository, Standards, Testing, Analytics, Scaling, Cost, Risks, Execution

> **v2.0 scope correction.** v1.0 of this roadmap deferred Networking entirely out of MVP ("Not built" in §2) on the assumption that Vertex was the whole product. It is not (Doc 00 §0.2). The business model that actually funds the December launch is **event → TGL Membership → Networking → renewal**, not Vertex subscription revenue, which makes Networking launch-critical, not a V1 nice-to-have. §1 and §2 below are corrected accordingly (Doc 00 VD-10 tracks this as a live decision, not a settled default — confirm the December-launch scope with the founder before committing the team to either order).

---

# 1. Development roadmap (7 phases)

Durations assume **3 engineers** (1 full-stack lead, 1 backend, 1 frontend) plus a part-time designer. Scale accordingly.

## Phase 1 — Foundation (weeks 1–4)

**Goal:** a deployable skeleton with auth, schema and a pipeline. No product value yet, and that is correct.

| Stream | Work |
|---|---|
| Infra | Terraform: VPC, RDS, Redis, ECS, S3, ECR, Secrets, CloudWatch. Three environments. GitHub Actions with OIDC |
| Database | Full schema migration 001; seed the category taxonomy (~150 nodes); seed plans |
| Backend | NestJS skeleton with module boundaries; auth module (register, login, refresh with rotation, MFA scaffold); RBAC guard; audit logging; health checks |
| Frontend | Next.js skeleton, design tokens, shadcn/ui setup, auth pages, app shell with sidebar |
| Security | Argon2id, rate limiting, secret scanning and SAST in CI |
| Tests | Unit + integration on auth; CI green and enforced |

**Acceptance:** a user can register, verify email, log in, refresh, enable MFA and log out — in production. `terraform apply` builds a full environment from nothing.
**Risks:** Terraform for three environments takes longer than estimated, every time. Budget the buffer.
**Definition of done:** deployed to staging, smoke tests pass, runbook written.

## Phase 2 — Vertex interface + standard search MVP (weeks 5–8)

**Goal:** the flagship standard search and category browsing UX.

| Stream | Work |
|---|---|
| Frontend | Vertex home, standard search results, category pages, provider cards |
| Backend | `/providers` endpoint, lexical search in Postgres, basic filters |
| Tests | E2E on the search query flow; accessibility audit |

**Acceptance:** users can search for providers using text and filters, and view standard results.

## Phase 3 — Business registration + verification (weeks 9–14)

**Goal:** real supply can onboard.

| Stream | Work |
|---|---|
| Backend | Business module; multi-step onboarding with saved progress; document presign; verification state machine; check workers; KYB vendor adapter behind `KybProvider`; risk scoring |
| Frontend | W9–W11, W13; provider dashboard shell |
| Infra | Private document bucket, KMS CMK, virus scanning, OCR pipeline (Lambda) |
| Admin | Reviewer queue (W12) — the minimum viable version, but real |
| Security | Document access authorisation + audit logging; presigned URL expiry |

**Acceptance:** a real business completes onboarding, passes GSTIN verification automatically, and reaches T2 without a human; a business with only a document reaches a reviewer and is decided within SLA.
**Risks:** KYB vendor integration always takes longer than the docs suggest — sandbox behaviour differs from production. Start the vendor pilot in Phase 1, not Phase 3.

## Phase 4 — Hybrid Search (weeks 15–22)

**Goal:** improve search relevance with embeddings (MVP phase). Generative AI intent pipeline is deferred to post-MVP.

| Stream | Work |
|---|---|
| Search | Hybrid retrieval (tsvector + pgvector + RRF); ranking function with per-family profiles; provider embedding worker; `search_results` impression logging |
| Frontend | Advanced filters, comparison, full provider profile (W6, W7, W5a) |
| Tests | Search-quality tests; load test on search endpoints |

**Acceptance:** NDCG@10 > 0.70 on the judgement set.
**Note on AI:** The generative AI intent pipeline (taxonomy RAG, requirement generation) is explicitly moved out of MVP to V2 (Phase 8+).

## Phase 5 — Payments + subscriptions (weeks 23–27)

| Stream | Work |
|---|---|
| Backend | Razorpay integration; plans and entitlements; checkout; webhook processor with signature verification and dedupe; invoices with GST; dunning; reconciliation job |
| Frontend | W14–W16; billing settings |
| Security | Webhook signature, idempotency, entitlement enforcement on every gated endpoint |
| Tests | Full webhook test matrix including replay, out-of-order and signature-failure cases |

**Acceptance:** a provider subscribes, entitlements apply **only** after the verified webhook, an invoice is generated, a failed payment triggers dunning, and nightly reconciliation reports zero discrepancies.

## Phase 6 — Projects, Networking, membership, events, referrals (weeks 28–34)

**If Doc 00 VD-10 resolves toward Networking-first (see banner above), pull the Networking/membership/events streams below into Phase 1–3 instead, ahead of Vertex's AI pipeline** — this phase ordering assumes Vertex ships first, which may not be the right call for a December, event-driven launch.

| Stream | Work |
|---|---|
| Backend | Projects with requirements/shortlist/tasks; project AI context injection; `tgl_memberships` + `membership_plans` + event-registration → membership-grant pipeline; `networking_profiles` extensions (Trust Score, Growth Points, chapter); `business_referrals` state machine; `city_chapters`; `leaderboard_snapshots` recompute job; `events`/`awards`/`podcasts`; connections/matching; growth-referral engine (Doc 01 §9) with attribution, clawback and fraud checks |
| Frontend | W17–W21 (Projects/Networking/Referrals) plus Networking-specific screens: member directory, member profile, leaderboards, Business Need Board, events, awards (Doc 05) |
| Payments | Membership renewal checkout against `membership_plans` (Doc 04 §4), separate flow from provider subscriptions |
| Analytics | Full event instrumentation, **renewal rate as a first-class funnel** (Doc 01 §13.4) |

**Acceptance:** a query can be saved as a project; follow-up queries inside it use its context; an event registration grants a complimentary membership automatically; a business referral flows through its full status lifecycle and awards Growth Points on close; a growth/acquisition referral flows end-to-end to a paid reward with clawback protection; a leaderboard reflects a real recomputation, not a live aggregate query.

## Phase 7 — Hardening + launch (weeks 35–40)

| Stream | Work |
|---|---|
| Performance | Query optimisation, index review, caching, CDN, image pipeline; load test to 10× expected launch traffic |
| Security | External penetration test; threat-model review; secrets rotation; WAF tuning |
| Compliance | DPDP: consent flows, notice, export, deletion, retention automation; counsel review |
| Reliability | DR drill (timed), fault-injection tests on every degradation path, runbooks, on-call rotation |
| Observability | Dashboards, alerts, SLOs |
| Launch | Beta with a controlled provider cohort → staged public launch |

**Acceptance:** SLOs defined and met in staging under load; pen-test findings remediated; DR drill hits RTO; all runbooks written and rehearsed.

---

# 2. MVP vs V1 vs V2

| | **MVP (Phases 1–5)** | **V1 (Phase 6–7)** | **V2 / Scale** |
|---|---|---|---|
| Auth | Email + Google, MFA | + phone login | + SSO for enterprise |
| Vertex AI | **Deferred (Standard Search MVP)** | Intent pipeline, RAG | + voice input, multi-lingual |
| Search | Hybrid in Postgres | + saved searches, alerts | OpenSearch, learned ranking |
| Providers | Profile, search, contact | + comparison, similar | + rich catalogue |
| Verification | T0–T3 hybrid | + re-verification automation | + continuous registry monitoring |
| Payments | Subscriptions, invoices | + annual plans, coupons | + usage billing |
| Projects | **Simplified**: shortlist + requirements | Full workspace | + collaboration |
| **Networking** | **Built for launch** *(v2.0 correction — see banner above)*: member directory, Trust Score, Growth Points, business referrals (§10.3), city chapters, weekly/monthly/yearly leaderboards | + AI Business Match, mentorship matching | + groups beyond city chapters |
| **TGL Membership** | **Built for launch**: event-registration pathway only, 3/6/12-month renewal, complimentary period | + application/corporate/mentor/investor pathways (Doc 01 §13.1 Phase 2) | — |
| **Events / Awards** | **Built for launch**: registration, event-linked membership grant, award recording | Full awards committee workflow, national awards | — |
| Podcasts | Static list, manually published | + related-content linking | CMS |
| Growth referrals (acquisition, Doc 01 §9) | **Not built** | Full engine | + tiered rewards |
| Resources | **Static markdown** | + search, recommendations | CMS |
| Admin | Verification queue + user lookup, **+ Trust Score review queue, award committee view** | Full admin | + analytics suite |
| Messaging | **Contact reveal only**; Networking uses connection-request + note (Doc 01 §10.9), not open messaging | Structured enquiries | In-app messaging (maybe) |
| Mobile | Responsive PWA | Same | Native, if retention justifies |

**Mocked or simplified at MVP:** requirement generation falls back to curated templates for the top 20 business types when confidence is low (better quality *and* cheaper than a pure model approach at launch) · reviews collected but shown only above a minimum count · analytics via a SaaS tool, not built · resources as repo markdown · Networking's AI Business Match (Doc 01 §10.5) is explicitly **not** MVP — ship the deterministic match-score composite first.

**Why Networking moved into MVP in this correction:** the December launch's actual user acquisition path is *TGL event → membership → Networking*, not organic Vertex marketplace traffic. Shipping Vertex alone at launch, with Networking deferred to V1, would mean the event audience — the only audience the business currently has a proven way to reach — lands in a product with nothing to renew into. Vertex's AI marketplace remains the harder, higher-risk engineering effort (Phase 4 below) and can legitimately follow Networking to market if team capacity forces a sequencing choice; that trade-off is Doc 00 VD-10, not resolved by this document alone.

---

# 3. Repository structure

```
vertex/
├── apps/
│   ├── web/                 # Next.js — user + provider surfaces
│   ├── admin/               # Next.js — internal admin (separate deploy, separate auth policy)
│   └── api/                 # NestJS modular monolith
├── services/
│   ├── intelligence/        # Python FastAPI — AI pipeline
│   ├── workers/             # TypeScript queue consumers
│   └── functions/           # Lambda handlers (webhooks, scheduled, S3 triggers)
├── packages/
│   ├── ui/                  # shared React components + design tokens
│   ├── contracts/           # Zod schemas → TS types → OpenAPI (single source of truth)
│   ├── database/            # Prisma/Drizzle schema, migrations, seeds
│   ├── config/              # eslint, tsconfig, tailwind presets
│   └── analytics/           # typed event definitions
├── infrastructure/          # Terraform (modules/ + environments/)
├── docs/                    # this document set; ADRs; runbooks
├── scripts/                 # dev tooling, data seeding, one-off migrations
└── tests/
    ├── e2e/                 # Playwright
    ├── load/                # k6
    └── eval/                # AI evaluation datasets + harness
```

**Why a monorepo:** the contract between `web` and `api` changes constantly at this stage. `packages/contracts` makes a schema change and both sides of it one atomic PR. The cost is build tooling complexity, which Turborepo largely absorbs.

**`admin` is a separate app deliberately** — different auth policy (MFA mandatory, optional IP allow-list), different deploy cadence, and a smaller blast radius if the public app is compromised.

---

# 4. Coding standards

**TypeScript:** `strict` on, `noUncheckedIndexedAccess` on, `any` banned (lint error, `unknown` + narrowing instead) · named exports only · `PascalCase` components, `camelCase` functions, `SCREAMING_SNAKE` constants, `kebab-case` files · Zod validation at every boundary (HTTP, queue, external API) — never trust a shape you did not validate.

**Python:** ruff + black + mypy strict · Pydantic models at every boundary · type hints mandatory.

**Errors:** typed error classes mapped to HTTP codes at one place in the framework layer · never swallow an error silently · never leak internals to a client · every error logged with `request_id` · user-facing messages state what to do next.

**Logging:** structured JSON only · levels used meaningfully (error = a human must look; warn = degraded; info = business events; debug = off in production) · never log PII, tokens, documents or full prompts.

**Git:** trunk-based with short-lived branches · Conventional Commits · squash merge · PRs under ~400 lines where possible · at least one approval · CI green is mandatory, not advisory.

**Review rules:** correctness → security → tests → readability → performance, in that order. Blocking comments must state what to change. Non-blocking suggestions prefixed `nit:`.

---

# 5. Testing strategy

| Layer | Tool | Scope | Target |
|---|---|---|---|
| Unit | Vitest / pytest | Pure logic: ranking maths, risk scoring, entitlements, state machines | 80% on business logic; coverage is a smell detector, not a goal |
| Integration | Vitest + Testcontainers | Modules against a real Postgres and Redis | All repositories and workers |
| API | Supertest | Endpoint contracts, authz, validation, error shapes | Every endpoint, including the 403 and 429 paths |
| Database | pgTAP / SQL tests | Constraints, indexes, migration up **and down** | Every migration |
| Search quality | Custom harness | NDCG@10, Recall@50 against the judgement set | Runs in CI, blocks on regression |
| AI evaluation | Custom harness | Intent accuracy, entity F1, requirement precision/recall, hallucination rate | Runs in CI on any prompt/model/ranking change |
| E2E | Playwright | Critical journeys: signup → query → contact; provider onboarding → verification → subscribe | Green before every production deploy |
| Security | OWASP ZAP + Semgrep + Trivy + gitleaks | Automated scanning in CI; annual external pen test | No high findings merged |
| Load | k6 | `/vertex/query`, `/providers`, checkout at 10× expected peak | p95 within SLO |
| Chaos | Fault injection in staging | Kill the LLM provider, Redis, a DB replica, the KYB vendor | Every degradation path verified quarterly |

**The two tests most teams skip and most need here:** migration *down* tests (an unrollbackable migration is a production incident waiting to happen) and degradation-path tests (the code that runs when a vendor is down is the least-exercised code in the system).

---

# 6. Analytics and KPIs

## 6.1 Event taxonomy

`user_registered` · `onboarding_completed` · `vertex_query_submitted` · `vertex_query_completed` · `suggestion_clicked` · `requirement_expanded` · `provider_viewed` · `provider_saved` · `provider_contacted` · `comparison_created` · `project_created` · `project_revisited` · `business_registered` · `verification_started` · `verification_completed` · `subscription_started` · `subscription_cancelled` · `payment_failed` · `referral_created` · `referral_converted` · `network_connection_created` · `review_submitted`

Every event carries: `user_id` (or anonymous id), `session_id`, `timestamp`, `source`, `device`, and event-specific properties. Event schemas live in `packages/analytics` as typed definitions — an untyped event taxonomy drifts within a month and becomes unanalysable.

## 6.2 Funnels

```
Demand:  visit → query → results → provider view → contact → project created → return within 7d
Supply:  visit → register → profile complete → verification submitted → verified → subscribed → first lead → renewed
```

## 6.3 KPIs

| Category | Metric | Why it matters |
|---|---|---|
| **Acquisition** | Signups, CAC by channel, organic share | Organic share is the health test for the resources/SEO strategy |
| **Engagement** | Queries per active user, requirement expansion rate, provider view rate, save rate, D7/D30 retention | Query→view→contact is the core value chain |
| **Marketplace** | Provider density per category per city, **match rate** (queries returning ≥5 relevant providers), **coverage gap count**, supply/demand ratio | Density per category per city is *the* marketplace health metric — a national average hides a dead category |
| **Conversion** | Contact rate per query, provider response rate, lead→conversion | — |
| **Revenue** | MRR, ARR, ARPU, provider retention, churn, LTV:CAC | — |
| **Trust** | Verification completion rate, T2+ share, dispute rate, fraud rate, review hold rate | — |
| **Networking / Membership** | **Renewal rate** (Doc 01 §13.4), event registrations → membership conversion, business referrals given/closed, Growth Points distribution (watch for farming concentration), chapter activation status | Renewal rate is the single most-watched number for this half of the product — see below |
| **AI** | Intent accuracy, requirement precision, NDCG@10, hallucination rate, **cost per query**, cache hit rate | Cost per query belongs next to quality, not in a finance report |
| **Reliability** | Uptime, p95 latency, error rate, DLQ depth | — |

**The three numbers to watch above all others in year one:**
1. **Provider density per category per city (Vertex).** Everything downstream fails if a category is empty, and an aggregate number will hide it until a user complains.
2. **Provider renewal rate at month 2 (Vertex).** It is the only honest measure of whether the leads were actually worth paying for. Everything else can be flattered; this cannot.
3. **TGL Membership renewal rate after the complimentary period (Networking).** The equivalent, and arguably more important, number for the other half of the product — see Doc 01 §13.4. Track it per event cohort, not just in aggregate, so a bad event or a bad city doesn't hide inside a healthy overall number.

---

# 7. Scalability plan

| Stage | Architecture changes |
|---|---|
| **0 → 10k users** | As designed. Single RDS instance (Multi-AZ), 2–4 Fargate tasks, Postgres search. Optimise nothing yet; measure everything |
| **10k → 100k** | Add a read replica; route analytics and heavy reads to it. Scale Fargate horizontally. Tune HNSW `ef_search`. Raise cache hit rates. Extract the search indexer as a separate worker. Consider OpenSearch if the migration triggers fire |
| **100k → 1M** | OpenSearch cluster; extract search and notification services; partition high-volume tables (`searches`, `search_results`, `audit_logs`) by month; move analytics to a warehouse (Redshift/Athena over S3); CDN tuning; possibly extract the verification service (its own scaling profile and compliance boundary) |
| **1M+** | Selective microservices where teams and scaling profiles justify it; consider Aurora or sharding by geography; multi-region if international; dedicated ML infrastructure for learned ranking; provisioned Bedrock throughput |

**Discipline:** every change on this ladder is triggered by a **measured** threshold, not by anticipation. Pre-scaling is the most expensive form of premature optimisation because it costs both money and velocity.

---

# 8. Cost model

**Every figure below is an assumption for shaping decisions, not a quote. Validate against the AWS pricing calculator and current vendor pricing before budgeting.**

Relative monthly infrastructure cost, expressed as proportions rather than absolutes, because the proportions are what should drive decisions:

| Component | 10k MAU | 100k MAU | 1M MAU | Notes |
|---|---|---|---|---|
| Compute (Fargate) | ~15% | ~15% | ~12% | Scales with traffic |
| RDS Postgres | ~20% | ~18% | ~15% | Multi-AZ doubles instance cost |
| ElastiCache | ~6% | ~5% | ~4% | — |
| Search (OpenSearch) | 0% | ~8% | ~12% | Zero at MVP by design |
| S3 + CloudFront | ~4% | ~5% | ~6% | Documents grow with providers, not users |
| SQS/EventBridge | <1% | <1% | ~1% | Negligible |
| **AI (Bedrock)** | **~35%** | **~30%** | **~25%** | **Largest single driver** |
| **KYB verification** | **~12%** | **~10%** | **~10%** | Per-check, scales with *providers* not users |
| Email/SMS/WhatsApp | ~4% | ~5% | ~7% | WhatsApp templates are per-message |
| Maps | ~2% | ~2% | ~3% | Geocoding cached aggressively |
| Monitoring | ~2% | ~2% | ~3% | Log volume grows faster than traffic |

**The three cost lessons in that table:**

1. **AI is the dominant cost at every scale.** It is also the most controllable — cache hit rate and model routing move it more than any infrastructure decision. This is why cost per query is a first-class dashboard metric (Doc 02 §5).
2. **KYB cost scales with providers, not users, and it is spent *before* the provider pays you.** If a full T3 verification costs more than a provider's first month, the unit economics are inverted. Track `verification_checks.cost_paise` against first-payment value from day one. This is the most under-modelled cost in marketplace plans.
3. **Not running OpenSearch at MVP removes an entire fixed cost line** — and it is a fixed cost, paid whether anyone searches or not.

---

# 9. Technical risk register

| Risk | Prob. | Impact | Severity | Mitigation | Owner | Early warning signal |
|---|---|---|---|---|---|---|
| **Marketplace cold start (supply)** | High | Critical | **Critical** | Manual recruitment of the first 500 providers; launch one city and 3 categories deep, not 10 shallow; free tier for founding providers | Founder | Coverage-gap count rising; queries returning <5 results |
| **AI hallucination / wrong requirements** | Med | High | High | LLM never selects providers; taxonomy RAG grounding; eval suite in CI; hallucination rate monitored | AI lead | Hallucination rate >1%; user corrections rising |
| **Provider quality (verified but bad)** | High | High | High | Response-rate ranking; reviews gated on real contact; dispute tracking; suspension policy | Product | Contact→response rate falling |
| **Fraudulent registrations** | Med | High | High | Risk scoring, KYB registry checks, manual review above threshold | Security | Rejection rate spike; duplicate-document hits |
| **KYB cost exceeds provider LTV** | Med | High | High | Per-check cost tracking; tiered verification so cheap checks cover most providers; charge for T3 | Founder | Cost-per-verified-provider vs first-payment value |
| **Cloud cost overrun** | Med | Med | Med | Budgets and alarms at 70/85/100%; cost per query on the main dashboard; monthly review | Eng lead | AI spend trending above budget |
| **Search relevance below expectations** | High | High | High | Judgement set + NDCG in CI; per-family ranking profiles; iterate on real queries | Search lead | NDCG regression; zero-result rate rising |
| **DPDP non-compliance by May 2027** | Med | Critical | **Critical** | Consent model from schema day one; counsel engaged early; the two fixed dates on the roadmap | Founder | Milestones slipping past Q1 2027 |
| **Payment provider dependency** | Low | High | Med | `PaymentProvider` interface; secondary provider evaluated | Eng lead | Razorpay incident frequency |
| **LLM vendor lock-in / price change** | Med | Med | Med | AI Gateway abstraction; Bedrock multi-model; prompts portable | AI lead | Vendor pricing announcements |
| **Postgres becomes the bottleneck** | Med | High | High | Documented migration triggers; `SearchProvider` seam pre-built; outbox events already emitted | Eng lead | p95 search latency; replica lag |
| **Verification review under-staffed** | High | Med | High | SLA monitoring; queue-depth alerting; capacity planned per provider-signup forecast | Ops | SLA breach rate >10% |
| **Key-person dependency** | High | High | High | ADRs; runbooks; pairing; no single-owner subsystems | Eng lead | Bus factor of 1 on any critical module |
| **Scope creep** | **Very high** | High | **Critical** | The "do not build" list (Doc 00 §0.9) as a standing agenda item in planning | Founder | Phases slipping without scope being cut |
| **Networking cold start (member side)** | High | Critical | **Critical** | Member base is capped by event cadence until a direct-application pathway opens (Doc 01 §13.1 Phase 2); do not market Networking ahead of the first event's registration numbers | Founder | City chapter stuck below the activation threshold (Doc 00 VD-9) for more than one season |
| **Membership renewal rate below plan** | Med | Critical | **Critical** | Renewal rate tracked from day one as the primary KPI (Doc 01 §13.4), not member count; product roadmap prioritises referral quality (§10.3) and directory usefulness (§10.5) over engagement features that don't move renewal | Founder + Product | Complimentary-period members not converting to paid renewal at the modelled rate |

**The two Critical-severity rows are not technical problems.** Cold start is solved by recruitment, and DPDP is solved by counsel plus calendar discipline. No amount of architecture addresses either — which is exactly why they are the ones most likely to be neglected by an engineering-led team.

---

# 10. Epics and implementation order

| Epic | Purpose | Depends on | Key tables | Acceptance |
|---|---|---|---|---|
| **EPIC-014 Infrastructure** | Deployable environments | — | — | `terraform apply` builds an environment from zero |
| **EPIC-001 Authentication** | Identity, sessions, RBAC | 014 | users, user_roles, refresh_tokens | Register → MFA → login → refresh → revoke |
| **EPIC-015 Security baseline** | Audit, rate limits, secrets | 001 | audit_logs | Every sensitive action audited |
| **EPIC-002 User profiles** | Personalisation base | 001 | user_profiles, consents | Progressive onboarding, consent captured |
| **EPIC-005 Vertex AI** | Intent → requirements | 002 | searches, conversations, messages | Structured query produced; eval targets met |
| **EPIC-006 Search** | Retrieval + ranking | 005, 007 | search_results, category_embeddings | NDCG@10 > 0.70 |
| **EPIC-007 Provider profiles** | Supply data | 001 | businesses, business_profiles, categories, locations, services | Profile creatable, searchable, viewable |
| **EPIC-003 Business onboarding** | Supply acquisition | 007 | businesses (state machine) | Multi-step flow with saved progress |
| **EPIC-004 Verification** | Trust | 003 | verification_* | T1/T2 automated; T3 reviewed; audited |
| **EPIC-009 Payments** | Revenue | 003 | plans, subscriptions, entitlements, payments, invoices, webhook_events | Entitlements granted only on verified webhook |
| **EPIC-008 Projects** | Retention | 005 | user_projects, project_* | Query → project → contextual follow-up |
| **EPIC-013 Admin** | Operations | 004, 009 | — | Reviewer queue, user lookup, audit view, Trust Score review queue |
| **EPIC-010 Networking** | Community, trust, business referrals | 002, 016 | networking_profiles, connections, mentorship_matches, business_referrals, growth_points_ledger, trust_score_events | Member directory live, business referral lifecycle tracked, Growth Points awarded on close |
| **EPIC-011 Referrals (growth/acquisition)** | Growth | 001, 009 | referrals, referral_events, referral_rewards | End-to-end with clawback — **distinct epic from EPIC-010**, do not merge |
| **EPIC-012 Resources** | SEO + education | — | — | Markdown pages, ISR, tagged to categories |
| **EPIC-016 Membership** | TGL Membership access gate | 001, 017 | tgl_memberships, membership_plans | Event registration grants a complimentary membership automatically; renewal checkout works |
| **EPIC-017 Events** | Acquisition pipeline for Membership | 001, 009 | events, event_registrations | Registration → payment → `EventRegistrationConfirmed` → membership grant, auditable end to end |
| **EPIC-018 Awards & leaderboards** | Recognition | 010 | awards, leaderboard_snapshots | Scheduled recompute job live; committee-review flag enforced before an award is public |
| **EPIC-019 Podcasts** | Content | — | podcasts | Publish, link to business/member/event |

**Order (Vertex-first assumption, as in Phase 1–7 above):** 014 → 001 → 015 → 002 → 007 → 005 → 006 → 003 → 004 → 009 → 013 → 008 → 011 → 017 → 016 → 010 → 018 → 012 → 019.

**Order (Networking-first alternative, if Doc 00 VD-10 resolves that way):** 014 → 001 → 015 → 002 → 017 → 016 → 010 → 018 → 013 → 007 → 019 → 012 → then 006 → 003 → 004 → 009 → 005 (Vertex AI/search/verification/payments) → 008 → 011.

Rationale for the default order: infrastructure and identity first because everything depends on them; provider profiles before AI because search needs something to search; verification before payments because supply must be trustworthy before you charge for it; events and membership before Networking because membership is the access gate Networking depends on; Networking before awards/podcasts because recognition needs someone to recognise; resources and podcasts last because they are the most deferrable content surfaces. **Pick one order explicitly before Phase 1 kicks off** — do not let it default silently by whichever engineer picks up work first.

---

# 11. 30/60/90 day execution plan

## Days 1–30 — Foundation

| | Deliverable |
|---|---|
| Week 1 | Repo, monorepo tooling, CI skeleton, ADRs written and agreed. **Start the KYB vendor pilot** and the Razorpay account application — both have external lead times |
| Week 2 | Terraform: VPC, RDS, Redis, ECS, S3. Dev environment live |
| Week 3 | Database schema + migrations + category taxonomy seed. Auth module |
| Week 4 | Auth end-to-end in staging. Design tokens and app shell. Staging pipeline green |

**Milestones:** environment reproducible from code · a user can authenticate in staging · KYB pilot underway · legal counsel engaged (VD-5).

## Days 31–60 — Core marketplace

| | Deliverable |
|---|---|
| Week 5–6 | Vertex UI standard search; category browsing |
| Week 7 | Provider data model, profile CRUD, public profile page |
| Week 8 | Business onboarding flow with saved progress |
| Week 9 | Document upload, private bucket, virus scan, OCR pipeline |
| Week 10–11 | Verification state machine, KYB adapter, risk scoring, reviewer queue v1 |
| Week 12 | **Manually onboard the first 50 real providers.** Not a demo — real supply, real verification, real feedback |

**Milestones:** flagship UX demoable · a real provider verified end-to-end · 50 providers live · verification unit cost measured.

## Days 61–90 — Intelligence and revenue

| | Deliverable |
|---|---|
| Week 13–14 | Category embeddings; semantic search evaluation harness |
| Week 15–16 | Hybrid search tuning; ranking profile implementation |
| Week 17 | Hybrid retrieval + ranking; impression logging |
| Week 18 | Results UI, filters, provider profile, contact flow |
| Week 19 | Razorpay: checkout, webhooks, entitlements, invoices |
| Week 20 | Hardening, load test, closed beta with the 50 providers and ~200 invited users |

**Milestones:** NDCG@10 > 0.70 · first paid subscription · closed beta running with instrumented funnels.

**What is deliberately *not* in the first 90 days:** networking, referrals, comparison, mobile app, resources CMS, admin analytics, OpenSearch, in-app messaging. Every one of them will be argued for; the answer is the "do not build" list.

## 11.1 Team composition

| Team size | Shape | Architecture implication |
|---|---|---|
| **2–3 engineers** | 1 full-stack lead (owns architecture + AI), 1 backend, 1 frontend. Design and DevOps contracted | Modular monolith is mandatory, not preferred. Managed everything. Buy rather than build at every opportunity. Ship Phases 1–5 in ~6 months |
| **5–7 engineers** | + dedicated AI/search engineer, + DevOps/SRE, + QA. Backend splits into platform and marketplace | Same monolith, clearer module ownership. One deployable API is still correct. Parallelise Phases 3–6 |
| **10+ engineers** | Squads: Platform (auth/infra/observability) · Marketplace (providers/search) · Intelligence (AI) · Trust (verification/fraud/moderation) · Growth (referrals/networking/analytics) | **Now** extraction becomes justified — but by team ownership boundaries, not by technical fashion. Extract search and verification first: they have distinct scaling and compliance profiles. Add a platform team before adding services, not after |

**The pattern to avoid:** extracting services because the team grew, without assigning ownership. Services without owners become everyone's problem, which means nobody's.
