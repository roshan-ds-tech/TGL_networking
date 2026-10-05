# TGL — SYSTEM ARCHITECTURE & IMPLEMENTATION GUIDE
## Document 00 · Executive Summary, Final Architecture, ADRs, Investor Narrative

**Version:** 2.0 · **Date:** 11 September 2026 · **Status:** Design baseline for build
**Assumed primary market:** India, Bengaluru-first (stated assumption — see §0.3)
**Owner:** SkyKeen Enterprises

> **Version 2.0 note.** Version 1.0 of this document set specified the *Vertex* marketplace in isolation, as if it were the whole product. It is not. Vertex is one of two core modules of **TGL**, a single membership-and-marketplace ecosystem; the other is **Networking**, the members-only trust/referral/recognition community that is, if anything, the primary driver of the December-launch business model (event-gated membership, renewals, recognition at TGL events). Version 2.0 corrects the framing and adds Networking, Events, Awards, Podcasts and the membership model as first-class parts of the architecture, while keeping the Vertex-specific technical depth (AI pipeline, search/ranking, KYB) from v1.0 intact — it was correct, just incompletely scoped. See §0.2 for the corrected product definition and §0.2a for the full brand/product history.

---

## 0.1 How to read this document set

| Doc | Contents | Primary audience |
|---|---|---|
| **00** (this) | Executive summary, final stack, ADRs, investor narrative, corrections to the brief | Leadership, investors, tech leads |
| **01** | Product definition, taxonomy, user & business journeys, membership, Networking (trust/referrals/recognition), Vertex marketplace model, projects, resources | Product, UX |
| **02** | Vertex AI experience, intent pipeline, suggestion engine, search & ranking, AI evaluation, AI security | AI engineers, search engineers |
| **03** | Database schema + ERD, API design, events, real-time, notifications, audit, retention | Backend, data engineers |
| **04** | Cloud architecture, security, KYB/verification, payments (provider subscriptions + TGL membership), compliance, observability, CI/CD | DevOps, security, compliance |
| **05** | Frontend architecture, design system, navigation, all wireframes (Vertex + Networking + Events/Awards/Podcasts), admin | Frontend, design |
| **06** | Roadmap, MVP scope, repo, standards, testing, analytics, KPIs, scaling, cost, risks, 30/60/90 | Eng management, PM |
| **07** | Miro board specification, MCP integration strategy, all Mermaid diagrams | Architects, docs owners |

Every recommendation states **why**. Where a fact could not be verified, it is marked **[ASSUMPTION — VALIDATE]**.

---

## 0.2 What TGL is

**TGL (The Growth League)** is a business ecosystem app, owned and operated by **SkyKeen Enterprises**, built around one platform with **five core modules**:

| Module | Primary Purpose |
|---|---|
| **Vertex** | Discover business services and providers; solve business requirements (Problem → Service → Provider → Enquiry). Open to the public. |
| **Networking** | Members-only community for relationships, referrals, reputation, and recognition. |
| **Events** | Discover and participate in TGL events (e.g., Season 1). |
| **Awards & Podcasts** | Recognition, business stories, and founder interviews. |
| **Notifications & Profile** | Actionable updates and identity/account controls. |

Vertex is the open B2B Business Growth Ecosystem connecting **entrepreneurs and business owners** (demand side) with **service providers, suppliers, consultants and technology vendors** (supply side). 

At **MVP (Launch Core)**, Vertex is designed as a powerful search and discovery platform:

```
Natural language or category search
   → provider discovery
   → provider interaction
   → project workspace
   → conversion
```

In **Phase 3**, Vertex will evolve to include an AI-assisted requirement discovery layer (intent extraction → generated requirement set), but at launch, the focus is on rapidly connecting users to providers without requiring them to spend time chatting with an AI. Everything else — including Networking — is infrastructure and ecosystem around the core loops (get discovered credibly; get connected trustworthily).

---

## 0.2a Brand history and platform structure (why this version changed)

This section exists because the product brief evolved materially during discovery, and the two names below still appear in older working documents. Stated plainly, once, so nobody has to reconstruct it from Slack history:

**Early concept (August, week 1): two separate brands.** The original plan was **TGL** (community, recognition, networking, awards, events) and a *separate, independently branded* app called **BGI — Business Growth Infrastructure** (business directory, marketplace, AI-recommended service providers). The two were designed to share one account but present as two different products to the market, each with its own content strategy and positioning ("TGL = inspire/community", "BGI = enable/infrastructure").

**Why that changed.** Working through naming for the second module (candidates evaluated: *TGL Marketplace*, *TGL Connect*, *TGL Growth*, *TGL Catalyst*, *TGL Vertex*), the decision was made **not to run two brands**. A second, unfamiliar brand name (BGI) forces users to learn and trust a second identity before a single business relationship has been created — pure acquisition friction with no offsetting benefit, since both products serve the same member base and the same parent company. The resolution: **everything stays under the TGL name.** The business-growth module was renamed and folded in as **Vertex** — "the point where businesses, professionals and opportunities connect" — and re-scoped from *marketplace* to **business journey platform**: instead of asking "do you need a CA?", Vertex asks what stage the business is in (Start → Set Up → Technology → Market → Build Team → Operations → Finance → Legal → Mentors) and guides from there. "BGI" is retired terminology; do not use it in product surfaces, code, or new documentation. Where it appears in historical planning material, read it as an early working name for what is now the Vertex module inside TGL.

**Current structure:**

```
SkyKeen Enterprises (parent company)
├── SkyKeen Events
├── TGL — The Growth League                 ← the app documented in this set
│   ├── Networking   (members-only community, trust/referrals/recognition)
│   └── Vertex        (open business-journey platform)
├── SkyKeen Media
```

Surrounding both modules, and reachable from either, sit **Events**, **Awards**, **Podcasts**, **Notifications** and **Profile** — see Doc 01 §Navigation and Doc 05 §Frontend architecture for the exact information architecture (five bottom tabs: Vertex · Networking · Events · Notifications · Profile, with Awards and Podcasts nested one level in).

**The ecosystem flywheel this is designed to produce:**

```
TGL event → participation/recognition → TGL Verified badge → Networking reputation
   → Vertex profile credibility → discovered by a Vertex user → enquiry → business closed
   → success story → TGL Podcast / Media → more awareness → more businesses join → next event
```

**Product discipline carried over from the original brief and still binding:** do not build another social-media app, another generic directory, an endless AI chatbot, a bare vendor list, a gamification system with no business purpose, an automatic reputation-punishment system with no human review, or any feature whose impact cannot be measured. Every feature should answer: does this build trust, or does it build business? If neither, it does not belong (Doc 01 §Product principle).

---

## 0.3 Stated assumptions

The brief left these open. Production-grade assumptions have been made and are stated explicitly so they can be overturned deliberately rather than by accident.

| # | Assumption | Why it matters | Overturn if… |
|---|---|---|---|
| A1 | **India-first, Bengaluru-launch, INR-denominated** | Drives payments, KYB, cloud region, compliance regime — all four change if this is wrong | You are launching US/EU-first |
| A2 | **Providers pay; entrepreneurs use it free** | Determines who the conversion funnel targets and where trust conflicts arise | You intend a take-rate model on transactions |
| A3 | **Vertex does not process transactions between the two sides at MVP** | Removes escrow, payouts, PA licensing and dispute-settlement from scope entirely | You want to intermediate the actual deal |
| A4 | **Team size at start: 2–4 engineers** | Rules out microservices and Kubernetes at MVP | You have 10+ engineers on day one |
| A5 | **Target scale in year 1: <50k users, <20k providers** | Rules out a dedicated search cluster at MVP | You have a bulk provider-data acquisition path |
| A6 | **No regulated financial product** (no lending, no payments intermediation) | Keeps you outside RBI PA/PPI licensing | You add financing, escrow or BNPL |

**A3 is the single most important scope decision in this document.** The moment Vertex holds or routes money between a user and a provider, it becomes a payment aggregator in India, which brings RBI authorisation into scope and adds 12+ months and a compliance function. Vertex at MVP is a **discovery and lead platform** that charges providers a subscription. That is a fundamentally simpler business to build and license.

---

## 0.4 Four corrections to the brief

The brief specified some defaults that do not survive contact with an India-first deployment. Each is corrected here with evidence.

### Correction 1 — Stripe is not the right primary payment provider

The brief says "Prefer Stripe unless a compelling reason exists." There is one.

<cite index="7-1">Stripe moved to an invite-only model in India in May 2024, and Indian businesses cannot use Stripe for domestic sales within India</cite>. <cite index="8-1">New Indian business approvals are rare, and Indian alternatives for domestic collection are Razorpay, Cashfree, PayU and Instamojo</cite>. <cite index="4-1">Stripe's self-serve signup is unavailable in India and UPI collection is not supported</cite>.

For a marketplace selling INR subscriptions to Indian SMBs, UPI is not optional — it is the dominant rail.

> **Recommendation: Razorpay as the primary payment and subscription provider. Stripe is retained as a designed-for, not-built-yet, secondary provider behind a `PaymentProvider` interface, activated only for international expansion or a foreign entity.**

Everything the brief asks for regarding Stripe — server-side verification, webhook validation, idempotency, entitlements, never trusting the frontend — applies identically to Razorpay. The *discipline* transfers; the *vendor* does not. Detail in Doc 04 §M.

### Correction 2 — DPDP, not GDPR, is the governing privacy regime

The brief asks for GDPR/CCPA. For an India-first product with Indian users, the operative law is the Digital Personal Data Protection Act 2023 and its Rules.

<cite index="21-1">MeitY notified the DPDP Rules 2025 on 13 November 2025, converting the draft into binding law and starting an 18-month clock ending 13 May 2027, the date by which full substantive compliance is due. The Data Protection Board of India already exists and functions, so a data principal can file a complaint today.</cite> <cite index="19-1">The Consent Manager Framework becomes operational on 13 November 2026, and full compliance is required by 13 May 2027.</cite> <cite index="20-1">Non-compliance penalties can reach ₹250 crore per violation.</cite>

Vertex handles exactly the data DPDP is about: identity documents, business registration data, bank details, contact information. Build to DPDP from schema day one — granular purpose-scoped consent, itemised notice, retention limits, deletion and export. GDPR is then mostly a superset you can add later if you take EU users.

**This is a compliance-timeline statement, not legal advice. A qualified Indian privacy counsel must review the final design.**

### Correction 3 — the verification vendors named in the brief are the wrong ones for India

Trulioo, Jumio and Onfido are identity-verification providers with limited depth on Indian *business* registries. Indian KYB runs against MCA21, the GSTIN database and the UDYAM portal.

<cite index="14-1">A comprehensive KYB check in India covers legal entity verification through MCA21 (companies and LLPs), the GSTIN database (GST-registered entities), and the UDYAM portal (MSMEs). A GST Verification API queries the GSTIN database in real time, returning registration status, business type, and filing history; a CIN Verification API queries MCA21 for incorporation status, registered address, and director details.</cite> <cite index="15-1">Key providers in the Indian market include BeFiSc, HyperVerge, Signzy, Karza/Perfios, IDfy, and Surepass.</cite>

> **Recommendation: an India-native KYB aggregator (Signzy, IDfy, Surepass, Deepvue or Karza/Perfios) as primary, evaluated by pilot against real provider files. Global IDV vendors are only relevant if Vertex expands outside India.** Full decision matrix in Doc 04 §G.

Note also: <cite index="15-1">a 'verified' API response is not a risk determination — liveness, device intelligence, and cross-signal checks must layer on top of document verification.</cite> That principle is baked into the fraud-scoring design.

### Correction 4 — most Vertex providers will not have a CIN

The brief's verification design implicitly assumes registered companies. In the Indian SMB long tail — the exact segment Vertex serves — a large share of providers are sole proprietorships or partnerships with **no CIN, and often no GST registration** (below the turnover threshold).

A verification pipeline that requires CIN + GSTIN will reject most of your supply side, and a marketplace with no supply has no demand. The design therefore uses **tiered verification with graded badges** (Doc 01 §Trust, Doc 04 §G) rather than a binary verified/unverified gate:

`Registered` → `Contact Verified` → `Business Verified` → `Fully Verified`

Each tier unlocks ranking weight and profile surface area. Nobody is blocked from listing; only unverified providers rank low and carry a visible badge state. This is the single most important supply-side design decision in the document.

---

## 0.5 The recommended architecture in one paragraph

Networking, Vertex, and Events are product experiences on **one shared platform** — one auth system, one user, one database, one deploy. A **TypeScript modular monolith** (NestJS on ECS Fargate) owns all product surface area (both modules, plus Events/Awards/Podcasts/membership) and writes to a **single PostgreSQL 16 database on RDS Multi-AZ**. Search is **hybrid inside PostgreSQL** at MVP — `tsvector` lexical + `pgvector` semantic, fused with Reciprocal Rank Fusion — with a designed migration to **OpenSearch** at the point where facet complexity or index size makes Postgres the wrong tool. (In Phase 3, a **separate Python FastAPI intelligence service** will be added to own the generative AI intent pipeline). Redis (ElastiCache) handles sessions, rate limits and suggestion caching. Asynchronous work runs through the **transactional outbox → SQS → workers** pattern, so a domain event is never lost between a database commit and a queue publish. **AWS ap-south-1 (Mumbai)** hosts everything. Payments are **Razorpay**. Verification is a **hybrid pipeline**: India-native KYB APIs first, document OCR second, human review last, with an explicit state machine and full audit trail. The whole thing is deployed by **Terraform** from a **pnpm + Turborepo monorepo** through GitHub Actions.

Nothing in that paragraph is chosen for novelty. Each choice is defended in the ADRs below.

---

## 0.6 Final Vertex stack

| Layer | Recommendation | Why (one line) | Reconsider when |
|---|---|---|---|
| **Frontend** | Next.js 15 (App Router) + React + TypeScript + Tailwind CSS + shadcn/ui | SSR/streaming for AI responses, one language across the stack, RSC keeps provider pages cheap to render | Never for this product shape |
| **State/data** | TanStack Query + Zustand (UI state only) + React Hook Form + Zod | Server state and client state are different problems; Zod schemas are shared with the backend | — |
| **Backend (product)** | Node.js 22 + TypeScript + NestJS, modular monolith | Type sharing with the frontend, strong DI/module boundaries that make later extraction mechanical | Team >15 engineers, or a module needs independent scaling |
| **Backend (AI)** | Python 3.12 + FastAPI — *intelligence service only* | The AI/eval/embedding ecosystem is Python-native; isolating it keeps the product API in one language | Never merge it back into the monolith |
| **Database** | PostgreSQL 16 (RDS Multi-AZ), Prisma or Drizzle ORM | Relational integrity for money, entitlements and verification; JSONB where the shape is genuinely dynamic | Read load exceeds a large instance + replicas |
| **Vector** | pgvector (HNSW) in the same PostgreSQL | Provider count at MVP is thousands, not millions; avoids a second datastore and a sync path | >2–5M vectors or vector QPS dominates DB load |
| **Search** | Hybrid: PostgreSQL FTS + pgvector, fused with RRF → **OpenSearch** at scale | One datastore, no eventual consistency, no sync bugs at MVP | >500k providers, heavy faceting, or geo+facet+text queries slow down |
| **Cache** | Redis 7 (ElastiCache) | Sessions, rate limits, suggestion cache, embedding cache, distributed locks | — |
| **Object storage** | S3 (private, SSE-KMS, per-tenant prefixes, presigned URLs only) | Verification documents must never be publicly reachable | — |
| **AI — generation** | Amazon Bedrock, **India Geo inference profiles** (`in.` prefix) | <cite index="29-1">India Geo inference profiles route requests only within the India geography, across Mumbai and Hyderabad, keeping data processed within India for data residency</cite> — directly serves DPDP | If a needed model is not offered on an India profile |
| **AI — classification** | Small/fast model on Bedrock, or a fine-tuned local classifier at volume | 80% of AI calls are classification, not generation; do not pay generation prices for them | — |
| **AI — embeddings** | Bedrock-hosted embedding model (Titan / Cohere), cached in Redis + stored in pgvector | Residency + cost; embeddings are the highest-volume AI call | — |
| **AI — fallback** | Direct Anthropic API and/or OpenAI API behind the same gateway interface | Provider outage must degrade, not break — see failure modes | — |
| **Queue/events** | Transactional outbox → SQS (FIFO where ordering matters) + EventBridge for fan-out | Outbox eliminates the commit-then-publish failure that silently loses events | — |
| **Cloud** | AWS, **ap-south-1 (Mumbai)**, ap-south-2 (Hyderabad) as DR | Latency to Indian users, India data residency, Bedrock India profiles, mature managed services | — |
| **Compute** | ECS Fargate (services + workers), Lambda for webhooks and scheduled jobs | No cluster to operate; a 3-engineer team should not run Kubernetes | Multi-team platform needs, or genuine multi-cloud portability |
| **Payments** | **Razorpay** (Subscriptions + UPI Autopay/e-mandate), Stripe behind an interface for later | Stripe is not self-serve available to Indian businesses for domestic sales | International entity or non-India launch |
| **Verification** | Hybrid: India KYB APIs → OCR → human review | Automated where the registry answers; human where it does not | — |
| **Email / SMS** | Amazon SES (transactional) + an India-registered DLT-compliant SMS provider; WhatsApp Business API for provider comms | SMS in India requires DLT template registration; WhatsApp is where Indian SMBs actually read messages | — |
| **Maps** | Google Maps Platform (Places, Geocoding) | Best Indian POI and address coverage; Mapbox for display tiles if cost bites | — |
| **IaC** | Terraform | Largest module ecosystem, provider-agnostic, hiring pool | — |
| **CI/CD** | GitHub Actions + Docker + ECR | Already where the code is; no extra system to run | — |
| **Observability** | OpenTelemetry SDK → CloudWatch + AWS X-Ray (MVP), Grafana Cloud/Datadog later | Instrument once with OTel, change backends without touching code | — |
| **Repo** | pnpm + Turborepo monorepo | Shared types between web, admin, api; one PR changes contract + both sides | — |

---

## 0.7 Architectural Decision Records

Format: Context · Decision · Alternatives · Trade-offs · Consequences.

### ADR-001 — Frontend: Next.js App Router

**Context.** Vertex's home surface is a streaming AI conversation; its provider pages are SEO-critical, largely public, and cacheable; the admin and dashboard surfaces are private and interaction-heavy. Three different rendering profiles in one product.

**Decision.** Next.js 15 App Router with React Server Components. Provider profiles and category pages use ISR (public, cacheable, SEO). The Vertex conversation is a client component consuming an SSE stream. Dashboards are client-rendered behind auth.

**Alternatives.** (a) Vite + React SPA — loses SEO on the provider pages, which is a primary organic acquisition channel for a marketplace. (b) Remix — comparable, smaller ecosystem, weaker RSC story. (c) Astro + islands — excellent for the public side, awkward for the app side.

**Trade-offs.** App Router has real complexity: the server/client boundary is a genuine source of bugs, and caching semantics have changed across versions. Accepted because the SEO + streaming combination has no better answer.

**Consequences.** Team needs RSC literacy. A strict rule is enforced: **no business logic in the frontend** — the frontend renders and validates, the API decides.

### ADR-002 — Backend: TypeScript monolith + Python intelligence service

**Context.** The brief asks to choose between Node+TS and Python+FastAPI. The honest answer is that the product API and the AI pipeline have different centres of gravity.

**Decision.** NestJS (TypeScript) owns auth, users, providers, subscriptions, verification orchestration, projects, networking, referrals, admin. A separate FastAPI service owns intent extraction, embeddings, reranking, suggestion generation and AI evaluation. They communicate over internal HTTP (with SSE for streaming) inside the VPC.

**Alternatives.** (a) All Python — viable, but the frontend is TypeScript, and sharing Zod/TS types across the API boundary is a real velocity multiplier that would be lost. (b) All TypeScript including AI — possible, but evaluation harnesses, embedding tooling, notebooks and any future local model work all live in Python; you would fight the ecosystem monthly. (c) Two full stacks — unnecessary duplication.

**Trade-offs.** Two languages means two toolchains, two CI paths, two dependency surfaces, and a hiring requirement for both. Accepted because the boundary is clean and narrow: the intelligence service exposes about six endpoints and owns no product state.

**Consequences.** The intelligence service is **stateless** and owns no tables. All persistence goes through the monolith. This is a hard rule; violating it turns a clean boundary into a distributed database.

### ADR-003 — Modular monolith at MVP, selective extraction later

**Context.** The brief lists thirteen "services." At 2–4 engineers, thirteen deployable services means thirteen pipelines, thirteen dashboards, distributed transactions, and a team that ships nothing.

**Decision.**
```
MVP (0–12 months):    Modular monolith + background workers + intelligence service
Growth (12–24 months): Extract search/indexing and notifications if load justifies it
Scale (24+ months):    Extract only modules with independent scaling or team ownership
```

**Alternatives.** Microservices from day one — the failure mode is well documented: you pay all the operational cost of distribution before you have the scale or the team size that distribution buys you anything for.

**Trade-offs.** A monolith can rot into a ball of mud. Prevented structurally: each NestJS module owns its tables, exposes a typed service interface, and **may not import another module's repositories**. Cross-module reads go through the owning module's service; cross-module writes go through domain events. Enforced in CI by dependency-cruiser rules, not by good intentions.

**Consequences.** Extraction later is mechanical rather than archaeological — the seams already exist.

### ADR-004 — PostgreSQL as the primary datastore

**Context.** Subscriptions, entitlements, verification decisions and audit logs all require transactional integrity. Provider profiles are semi-structured. Search needs both lexical and vector retrieval.

**Decision.** PostgreSQL 16 on RDS, Multi-AZ, with PostGIS (geo), pg_trgm (fuzzy text) and pgvector (embeddings). JSONB used only where the shape is genuinely open (provider service attributes, verification provider payloads); everything else is properly columned and constrained.

**Alternatives.** MongoDB — the flexible-schema argument loses badly the first time you need "which providers on an active Professional plan have an expired verification"; that query is trivially relational. DynamoDB — excellent at known access patterns, wrong for a product whose access patterns are still being discovered.

**Trade-offs.** A single primary database is a scaling ceiling and a blast radius. Mitigated by read replicas, connection pooling (PgBouncer/RDS Proxy), and the module-owns-its-tables rule that makes later splitting possible.

**Consequences.** Indexing strategy is a first-class design artefact, not an afterthought (Doc 03).

### ADR-005 — Hybrid search in PostgreSQL first, OpenSearch when earned

**Context.** The brief asks to evaluate Postgres FTS, OpenSearch, a vector DB, pgvector, and hybrid.

**Decision.** MVP: hybrid retrieval entirely inside PostgreSQL. Lexical candidates from `tsvector` + `pg_trgm`; semantic candidates from `pgvector` HNSW; the two lists fused with Reciprocal Rank Fusion; then a scoring pass, then optional LLM reranking of the top ~30. Migrate to OpenSearch when a stated trigger fires.

**Migration triggers (write these into the runbook):**
- Provider count > ~500k, **or**
- p95 search latency > 400ms after index tuning, **or**
- More than ~6 simultaneous facets are needed, **or**
- Search read load is materially degrading transactional write performance.

**Alternatives.** OpenSearch from day one — adds a cluster to operate, an index to keep in sync, and an eventual-consistency class of bug, in exchange for capabilities you do not need at 5,000 providers. A dedicated vector DB (Pinecone/Weaviate/Qdrant) — a third datastore for a workload pgvector handles comfortably at this scale.

**Trade-offs.** Postgres will eventually be the wrong tool. The design accepts that and pre-builds the seam: all retrieval sits behind a `SearchProvider` interface with `PostgresSearchProvider` and (later) `OpenSearchProvider` implementations, and the outbox already emits `ProviderProfileUpdated` events that an indexer can consume from day one, even though nothing consumes them yet.

**Consequences.** The migration becomes a config change plus a backfill, not a rewrite.

### ADR-006 — AI model strategy: routed, hosted in India, no fine-tuning at MVP

**Context.** The brief warns against blindly recommending fine-tuning. Correct.

**Decision.** A model **router** in the intelligence service picks the cheapest model that can do each job:

| Job | Model class | Why |
|---|---|---|
| Intent + entity extraction | Small/fast model, structured JSON output, temperature 0 | High volume, narrow task, schema-constrained |
| Business-type classification | Embedding + kNN against a labelled category set; LLM only on low confidence | 10–100× cheaper than an LLM call, and more consistent |
| Requirement generation | Mid-size model, prompt + retrieved category graph (RAG) | Needs reasoning, but grounded in your taxonomy, not model memory |
| Conversational refinement | Mid-size model with conversation state | Quality is user-visible here |
| Reranking top-30 | Cross-encoder reranker, or a mid model with a compact prompt | Precision at the top of the list is what users judge |
| Response narration | Streaming, mid-size model | Perceived latency matters more than absolute latency |

**No fine-tuning at MVP.** Fine-tuning is justified only when (a) prompt + RAG has been measured and plateaued, (b) you have ≥5–10k labelled in-domain examples, and (c) the task is narrow and stable. Vertex has none of those on day one — the taxonomy will change monthly. Revisit for the intent classifier once you have six months of labelled production queries; that is the one task where the economics may work.

**Hosting.** Bedrock with India Geo inference profiles, so prompt content — which will contain business details and sometimes personal data — is processed in India. Direct vendor APIs are the configured fallback.

**Trade-offs.** Bedrock adds an abstraction layer and can lag direct APIs on newest-model availability. Accepted for residency, IAM-native auth, and one bill.

**Consequences.** Every AI call goes through the AI Gateway. No service calls a model provider directly — that is what makes routing, caching, budgets and evaluation possible at all.

### ADR-007 — AWS, ap-south-1 (Mumbai)

**Context.** Users, providers, latency and data residency are all Indian.

**Decision.** AWS ap-south-1 primary. ap-south-2 (Hyderabad) for cross-region backup and as the DR target. Bedrock India Geo profiles for inference.

**Alternatives.** GCP — strong AI story and good India presence; loses on the breadth of managed primitives Vertex actually uses (RDS/ElastiCache/SQS/ECS as one coherent IAM surface). Azure — no advantage here absent an enterprise agreement.

**Trade-offs.** Vendor lock-in is real and is accepted deliberately. Mitigation is limited to keeping the *domain* portable (containers, standard Postgres, standard Redis, S3-compatible API) — not to a fake multi-cloud abstraction layer, which costs more than it ever saves.

### ADR-008 — ECS Fargate, not EKS

**Context.** The brief asks for a comparison and warns against blindly choosing Kubernetes.

**Decision.** ECS Fargate for MVP and growth. Revisit EKS only at a stated trigger.

| Dimension | ECS Fargate | EKS |
|---|---|---|
| Time to first deploy | Hours | Days to weeks |
| Ops burden | AWS runs the control plane and the nodes | You own upgrades, add-ons, node groups, CNI, ingress |
| Team requirement | Any backend engineer | At least one person who knows Kubernetes properly |
| Cost at low scale | Lower (no cluster fee, no idle nodes) | Cluster fee + idle capacity |
| Portability | AWS-specific task definitions | Portable manifests |
| Ecosystem | Smaller | Very large |

**Triggers to revisit EKS:** >8 independently deployed services, multiple teams needing namespace isolation, a genuine multi-cloud requirement, or a dependence on Kubernetes-only operators.

**Consequences.** Containers are built to be runtime-agnostic (12-factor, config from environment, no ECS-specific assumptions in application code), so an EKS move later is an infrastructure project, not an application rewrite.

### ADR-009 — Razorpay as primary payment provider

**Context and evidence.** See Correction 1 (§0.4).

**Decision.** Razorpay Subscriptions for recurring provider plans; UPI Autopay and card e-mandate for auto-debit; Razorpay-hosted checkout to keep card data entirely out of Vertex's PCI scope. All payment state is derived **server-side from verified webhooks**, never from a frontend callback. A `PaymentProvider` interface isolates the vendor so Stripe can be added for an international entity without touching subscription logic.

**Alternatives.** Cashfree, PayU, Instamojo — all viable Indian options; Razorpay chosen for subscription API maturity and documentation quality. **[ASSUMPTION — VALIDATE:** run a commercial comparison of MDR, settlement cycle and subscription feature parity before signing.**]**

**Open item requiring verification.** RBI e-mandate rules impose an additional-factor-of-authentication threshold on recurring card debits above a specified amount, and that threshold has been revised more than once. **[VALIDATE against current RBI circulars and Razorpay documentation before pricing plans]** — because if a plan's monthly amount sits above the threshold, every renewal needs customer action, which will destroy your renewal rate. This is a pricing decision disguised as a technical one.

### ADR-010 — Hybrid verification with tiered badges

**Context.** See Corrections 3 and 4 (§0.4).

**Decision.** A four-tier trust ladder, driven by a hybrid pipeline: India KYB APIs where a registry can answer (GSTIN, CIN/MCA21, UDYAM, penny-drop bank verification), OCR + extraction where a document is the only evidence, and a human reviewer queue for everything ambiguous or high-risk. AI **assists** review; AI is never the system of record for a verification decision. Every decision is an immutable, attributable audit record.

**Consequences.** You need a staffed review function from launch. Budget it (Doc 06 cost model) — an unstaffed review queue is how marketplaces quietly stop verifying anyone.

### ADR-011 — S3, private by default, presigned access only

**Decision.** Every verification document lands in a private bucket, SSE-KMS encrypted with a dedicated CMK, Block Public Access on at the account level, versioning on, lifecycle rules to Glacier then expiry per the retention policy. Access is exclusively via short-lived presigned URLs (≤5 minutes) issued by the API after an authorisation check, and **every issuance is audit-logged with the actor, the document, and the reason**. Uploads are virus-scanned before they are readable by a reviewer.

**On "end-to-end encryption"** — the brief rightly says not to use the phrase casually. For Vertex: TLS 1.2+ in transit; SSE-KMS at rest; **application-level envelope encryption** for the most sensitive fields (bank account numbers, government ID numbers) so a database dump alone is not enough. True client-side E2E encryption is **inappropriate** for verification documents, because the entire purpose is for a reviewer and an automated pipeline to read them. Claiming E2E here would be false. Say what is actually true.

### ADR-012 — Transactional outbox → SQS

**Decision.** Domain events are written to an `outbox` table **in the same transaction as the state change**. A relay process polls the outbox and publishes to SQS/EventBridge, marking rows dispatched. Consumers are idempotent, keyed on `event_id`. Failures retry with backoff into a DLQ that is alarmed and has a documented replay procedure.

**Why not publish directly from the service.** Because "commit to the database, then publish to the queue" has two outcomes when the publish fails: a lost event, or a rollback that loses the write. The outbox makes the event durable with the state change and moves the failure into a place where it can be retried safely.

**Trade-offs.** Adds a relay process and small publish latency (sub-second with short polling). Cheap insurance for payment, verification and referral events, where a lost event means lost money or a broken promise to a customer.

---

## 0.8 Investor technical narrative

Vertex's defensibility is not the AI layer — anyone can call a model. It is the **compounding proprietary assets** the AI layer produces.

**1. Structured business taxonomy.** A hierarchical, synonym-rich, embedding-backed map of what businesses actually need, refined by real query data. A generic model can guess that a clothing business needs suppliers; only Vertex's data knows which thirteen requirements Bengaluru clothing founders actually act on, in what order.

**2. Intent → requirement mapping, learned from behaviour.** Every query where a user clicked, saved, or contacted a provider is a labelled training example for requirement generation. This dataset does not exist anywhere else and cannot be bought.

**3. The verified provider graph.** Verification is expensive and slow — which is precisely why it is a moat. A competitor can copy the UI in a month and cannot copy 20,000 KYB-verified providers with bank-verified accounts and two years of response-rate history in under two years.

**4. The trust graph.** Verification tier × review integrity × response behaviour × completed-project history. Ranking quality is a function of this data, so ranking quality itself compounds.

**5. Project context.** "My Clothing Brand" — budget, stage, location, shortlist, decisions — is durable, personal, and grows in value with use. It is both a retention mechanism and the personalisation signal that makes results better for that user than for a stranger.

**6. Marketplace flywheel.** More users → more qualified leads → more provider value → more providers subscribe → better coverage → better results → more users. Standard, but real, and the AI layer accelerates the middle of it by improving lead qualification.

**7. Referral graph.** Provider-to-provider and founder-to-founder referrals produce distribution at a lower cost than paid acquisition, and the graph itself becomes a ranking signal.

**8. The Networking trust graph — the harder-to-copy half.** Verification tier, review integrity and response behaviour are a Vertex-side moat; Networking's is a member-side one: Trust Score, Growth Points, tracked referral outcomes (given → accepted → meeting → closed → revenue) and event-linked recognition compound into a reputation graph a competitor cannot clone by copying the UI. The revenue this produces is also the more predictable of the two: membership renewals (annual, event-gated) versus provider subscriptions (usage-linked, more churn-sensitive). Track **renewal rate**, not member count, as the health metric — see Doc 01 §Membership and Doc 06 §KPIs.

**Honest limits.** The flywheel does not spin at zero, on either side. Vertex has a **hard cold-start problem on the supply side**: the first thousand providers must be manually recruited and manually verified. Networking has the equivalent problem on the demand side: the first cohort of members exists only because they registered for a TGL event, so member-base growth is capped by event cadence and registration volume (illustratively, ~350–450 per event × ~4 events/year) until a direct-application membership pathway is deliberately opened (Doc 01 §Membership, Phase 2). No amount of architecture solves either cold start. The AI layer is a differentiator in experience, not a technical barrier — the barrier is the data both sides accumulate. Any pitch that claims otherwise will not survive a technical diligence conversation.

---

## 0.9 What not to build (the discipline list)

| Do not build at MVP | Why | When it becomes right |
|---|---|---|
| A generic AI chatbot | Users should not spend time chatting with AI before reaching providers; Vertex is a routing layer, not a conversational agent (Phase 3). | Phase 3, as a strict requirement-generation tool |
| Generic directory with no outcomes | A directory without an enquiry/lead layer provides no monetizable value to providers. | Never |
| Microservices | 4 engineers cannot operate 13 services | >15 engineers, multiple teams |
| Kubernetes | Fargate does the job without a platform hire | >8 services or multi-cloud |
| Fine-tuned models | Prompt + RAG is unmeasured; taxonomy is unstable | 6 months of labelled query data |
| In-app messaging between users and providers | Enormous scope; contact reveal + tracking is 5% of the work for 70% of the value | Post-PMF |
| Escrow / transaction processing | Triggers RBI payment-aggregator scope (see A3) | A deliberate, funded, licensed decision |
| A mobile app | PWA covers it; two more codebases will not | Real retention that needs push and offline |
| A CMS for Resources | Markdown files in the repo work fine for 30 articles | Non-engineers need to publish weekly |
| Automatic, un-reviewed reputation penalties | A Trust Score that drops without human review is a liability | Never without a human-review step |
| Open membership (pay-and-join, no gate) | Exclusivity is a deliberate differentiator | A validated case that it won't dilute quality |
| Event participation = Networking membership | Event participation is a pathway, but not the only route; and it does not automatically grant TGL Verified. | Never |

---

## 0.10 Immediate open decisions

| ID | Decision | Owner | Why it blocks work |
|---|---|---|---|
| VD-1 | Confirm India-first / INR / Bengaluru launch (A1) | Founder | Determines payments, KYB, region, compliance |
| VD-2 | Confirm Vertex does **not** intermediate transactions (A3) | Founder | Determines whether RBI licensing enters scope |
| VD-3 | Pick the KYB vendor after a real pilot | Eng + Founder | Verification is on the critical path for supply onboarding |
| VD-4 | Verify the RBI e-mandate AFA threshold against current circulars, then set plan prices | Founder | Renewal rate depends on it |
| VD-5 | Engage Indian privacy counsel on the DPDP design | Founder | 13 Nov 2026 and 13 May 2027 are fixed dates |
| VD-6 | Decide the paid-placement policy before building ranking | Founder | Retrofitting ad slots into a ranker corrupts it — see Doc 01 §Trust |
| VD-7 | Commit to the supply-side seeding plan (first 500 providers) | Founder | No architecture solves cold start |
| VD-8 | Confirm TGL membership pricing (3/6/12-month renewal tiers) and the free-months-with-event-registration policy | Founder | Drives the subscriptions schema, Razorpay plan setup and the renewal-rate KPI baseline (Doc 01 §Membership) |
| VD-9 | Confirm the city-chapter activation threshold (illustratively 100+ active members before a city gets its own chapter/leaderboard) | Founder | Determines the City/National data model and leaderboard rollout order (Doc 01 §Networking structure) |
| VD-10 | Decide whether Networking ships in the MVP (December launch) or after Vertex | Founder + Eng lead | The chat-derived business model is Networking-first (event → membership → renewal); Doc 06 v1.0 deferred Networking to V1 — this is now a live conflict to resolve, not a default (Doc 06 §2) |
