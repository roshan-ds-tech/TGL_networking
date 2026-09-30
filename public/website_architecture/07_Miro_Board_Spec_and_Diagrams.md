# TGL · Document 07
## Miro Board Specification, MCP Integration Strategy, All Architecture Diagrams

**v2.0 note.** The board and diagrams below were specified for Vertex in isolation. Frame B1 and diagram C.10 in particular describe only the Vertex-side product and a lightweight opt-in networking feature; they predate the corrected product definition in Doc 00 §0.2 (TGL = Networking + Vertex) and Doc 01 §10 (the full Networking spec: Trust Score, Growth Points, business referrals, chapters, membership, events, awards). Treat B1 and C.10 as needing a refresh pass before the board is built, and use the three new diagrams in §C.21–C.23 below (ecosystem flywheel, membership grant pipeline, business referral lifecycle) as the source for that refresh rather than re-deriving them from the old frame.

---

# PART A — MCP capability inspection (actual, not assumed)

The Miro MCP server **is connected** in this environment. Its tools were inspected before anything in this document was written; nothing below is invented.

## A.1 Tools that actually exist

| Tool | Class | What it does |
|---|---|---|
| `canvas_get_canvas_composer_skill` | **Read (prerequisite)** | Returns the Canvas Composer SVG format spec. Must be called before any canvas write |
| `canvas_load_format_skill` | **Read** | Format-specific guidance; `format_name='diagramming'` with `notation` ∈ {flowchart, entity_relationship, uml_class, uml_sequence, free_form} |
| `canvas_read_as_svg` | **Read** | Reads board items back as SVG with `data-miro-id` on every element. Scopable via `widget_ids` |
| `canvas_create_from_svg` | **Create** | The primary creation tool. Parses Canvas Composer SVG into shapes, stickies, text, connectors, frames, tables, docs, images and Mermaid diagram widgets. Returns `result_svg` with ids stamped |
| `canvas_update_from_svg` | **Update (diff-based)** | Diffs against the live board on `data-miro-id` and applies only deltas. **Removing an element from the SVG does not delete it** — deletion requires an explicit `data-deleted="true"` per element |
| `board_create` | **Create** | Creates a board. Tool contract requires user confirmation first |
| `doc_create` | **Create** | Markdown document widget on a board |
| `comment_create` | **Create** | Canvas comment at coordinates |
| `board_show` | **Display** | Renders one interactive preview. Call once, at the end |
| `diagram_create_mermaid` / `diagram_update_mermaid` / `diagram_get_mermaid_instructions` | **Deprecated** | Superseded by the canvas path. Do not select these |
| `layout_create` / `layout_update` / `layout_get_dsl` | **Deprecated** | Superseded by the canvas path. Do not select these |

## A.2 Status in this session

`canvas_get_canvas_composer_skill` was called and **did not receive approval**, so no Miro board was created, read or modified. That is the correct outcome of a declined authorisation, and this document is written accordingly: everything below is a complete, executable specification rather than a report of work done.

**To execute it later:** approve the Miro tool calls and run the sequence in §A.4. Nothing else is required.

## A.3 Permission model to apply

| Tool | Treat as | Rule |
|---|---|---|
| `canvas_get_canvas_composer_skill`, `canvas_load_format_skill`, `canvas_read_as_svg`, `board_show` | **Read-only** | Safe to call freely |
| `canvas_create_from_svg`, `doc_create`, `comment_create` | **Additive** | Safe; creates new items, never removes |
| `canvas_update_from_svg` **without** `data-deleted` | **Additive/idempotent** | Safe; diff-based, partial documents are safe by design |
| `canvas_update_from_svg` **with** `data-deleted="true"` | **Destructive, not undoable** | Requires explicit per-item human confirmation naming the exact items. Never batch-delete |
| `board_create` | **Creates a new artefact** | Confirm with the user first, per the tool contract |

**Standing rule for this project: never send `data-deleted="true"` as part of a refresh.** Stale nodes are marked with a "SUPERSEDED" label and moved to an archive frame instead. Diagrams are cheap; an accidentally deleted board that a team has annotated is not.

## A.4 Execution plan (exact sequence)

```
 1. canvas_get_canvas_composer_skill()                          # required first, once
 2. canvas_load_format_skill('diagramming', 'flowchart')        # once
 3. canvas_load_format_skill('diagramming', 'entity_relationship')
 4. [confirm with user] board_create(name="Vertex — System Design", icon_emoji="⬡")
 5. canvas_create_from_svg(board_url, svg = frames only)        # 12 empty frames, laid out
 6. For each frame, in order B1…B12:
       canvas_create_from_svg(board_url + "?moveToWidget=<frame_id>", svg = that frame's content)
       # one call per frame — incremental, so a failure costs one frame, not the board
 7. canvas_read_as_svg(board_url)                               # VERIFY: node counts, edges, no overlaps
 8. canvas_update_from_svg(...)                                 # refine positions only; no deletions
 9. board_show(board_url)                                       # once, at the very end
```

**Verification step 7 is the one that gets skipped and shouldn't be.** Read the board back and check: every frame has its expected node count, every connector resolved to a real target, no diagram overflows its frame, no two frames overlap. A generated diagram that renders but is wrong is worse than one that failed loudly.

## A.5 Keeping the board synchronised with the documentation

The failure mode for architecture boards is drift: the board shows last quarter's architecture and nobody trusts it, so nobody updates it, so it drifts further.

**The mechanism:**
1. **Mermaid source in this repository is the source of truth.** `docs/diagrams/*.mmd`, one file per diagram, versioned in git.
2. The Miro board is a **rendered view** of those files, never edited directly for structural changes. Structural changes go through a PR on the `.mmd` file.
3. Each frame carries a footer text element: `Source: docs/diagrams/<name>.mmd · commit <sha> · updated <date>`. Anyone looking at the board can see whether it is current.
4. On merge to `main`, if any `.mmd` changed, a CI job posts a checklist item to refresh the affected frames. Frame refresh = `canvas_update_from_svg` on that one frame's diagram widget, sending its `data-miro-id` with a new Mermaid body. Additive and reversible.
5. Human annotations (stickies, comments) live **outside** the diagram widgets, in a dedicated annotation lane per frame, so a refresh never destroys team discussion.
6. Quarterly: `canvas_read_as_svg` the whole board, diff the node sets against the `.mmd` files, and report drift.

**Never do the reverse** — never treat the board as the source and try to reverse-engineer documentation from it. Diagrams edited by hand in a whiteboard tool cannot be reviewed, diffed or tested.

---

# PART B — Miro board specification

**One board: "Vertex — System Design", twelve frames in a 4×3 grid.** One board rather than twelve keeps navigation and permissions simple; frames give the separation the brief asked for.

**Layout grid:** each frame 1600×1000, 200px gutters. Row 1 y=0, row 2 y=1200, row 3 y=2400. Columns x = 0, 1800, 3600, 5400.

**Colour semantics (consistent across every frame — this is what makes the board readable at a glance):**

| Colour | Meaning |
|---|---|
| `#1D4ED8` blue | Application services / compute |
| `#059669` green | Data stores |
| `#7C3AED` purple | AI / intelligence components |
| `#D97706` amber | External third-party services |
| `#DC2626` red | Security, trust and verification boundaries |
| `#3F3F46` slate | Clients and user-facing surfaces |
| `#A1A1AA` grey | Deferred / future / not built at MVP |

Every frame contains: a title text (H1), a legend, the diagram widget, and an annotation lane on the right for stickies.

---

## Frame B1 — Product overview *(x=0, y=0)*

**Nodes:** `Entrepreneur (demand)` · `Provider (supply)` · `Vertex Platform` · `Discovery` `Verification` `Projects` `Networking` `Referrals` (capability boxes) · `Subscription revenue` · `Qualified leads`

**Edges:** Entrepreneur → Vertex (intent) · Vertex → Provider (qualified leads) · Provider → Vertex (subscription revenue) · Vertex → capability boxes (contains) · Referrals → Entrepreneur (loop back, dashed, labelled "growth loop")

**Grouping:** demand-side left, platform centre, supply-side right.
**Annotations:** three stickies stating assumptions A1, A2, A3 from Doc 00 §0.3, in amber.

## Frame B2 — User journey *(x=1800, y=0)*

Linear flowchart of the 15 screens U1–U15 (Doc 01 §3.1), with two decision diamonds: "Anonymous query limit reached?" → registration wall, and "Save as project?" → the retention branch. Colour: slate for screens, blue for decision points. A red note marks the one deliberate friction point (registration after one free query).

## Frame B3 — Business journey *(x=3600, y=0)*

The provider onboarding state machine (Doc 01 §5.1): DRAFT → PENDING_VERIFICATION → {VERIFIED, NEEDS_INFO, REJECTED} → ACTIVE, plus PAUSED / SUSPENDED / EXPIRED. Green for terminal-good states, red for terminal-bad, amber for waiting. A callout marks the deliberate sequencing decision: **verification before payment**.

## Frame B4 — Vertex AI flow *(x=5400, y=0)*

The four pipeline stages with their model class and latency budget annotated on each, plus the fallback ladder drawn as a parallel descending path in grey. Purple for AI components. A red boundary box encloses the untrusted-input zone (user query, provider content, OCR output) with the label "data, never instructions".

## Frame B5 — Search architecture *(x=0, y=1200)*

Dual retrieval paths (lexical / semantic) converging on RRF, then filters, scorer, reranker. The ranking function with its weights rendered as a table widget beside the diagram. A grey dashed box shows the OpenSearch migration path with the four migration triggers listed.

## Frame B6 — ER diagram *(x=1800, y=1200)*

Mermaid `erDiagram` of the core entities (§C.14). Grouped visually into five clusters matching module ownership: Identity · Marketplace · Trust · Commerce · Engagement. Module ownership boundaries drawn as coloured containers — this frame is the one engineers will reference most, so the clustering matters more than completeness.

## Frame B7 — API architecture *(x=3600, y=1200)*

Endpoint groups as containers with their auth requirements, rate limits and idempotency requirements on each. A separate lane shows the three protocols (REST / SSE / webhook) and what uses each. Red highlight on the webhook path with the label "the only path that grants entitlements".

## Frame B8 — Service interaction *(x=5400, y=1200)*

Sequence diagram: the full query flow across Browser → API → Intelligence → Bedrock → Postgres → Redis, with the SSE stream drawn as repeated returns. A second sequence below it shows the payment webhook flow, which is the other interaction most likely to be implemented wrongly.

## Frame B9 — AWS infrastructure *(x=0, y=2400)*

VPC with three subnet tiers across 3 AZs, drawn as nested containers. Every AWS service from Doc 04 §1.2 placed in its correct subnet. Security-group relationships drawn as red dashed arrows. VPC endpoints shown explicitly. A note lists the services **deliberately not used** and why — that list prevents more architecture debates than the diagram itself.

## Frame B10 — Verification pipeline *(x=1800, y=2400)*

The state machine from Doc 04 §2.2, with a parallel swimlane showing which actor may trigger each transition (System / Reviewer / Provider / Webhook). The risk-score bands and their routing rendered as a decision block. Red for the T3-requires-a-human rule.

## Frame B11 — Security architecture *(x=3600, y=2400)*

Defence-in-depth as concentric layers: Edge (WAF/CloudFront) → Network (VPC/SG) → Application (authn/authz/validation) → Data (encryption/KMS) → Audit. The STRIDE table as a table widget. The trust boundary between trusted and untrusted input drawn explicitly in red, matching B4.

## Frame B12 — Deployment architecture *(x=5400, y=2400)*

CI/CD pipeline left to right: PR gates → merge → build → staging → approval → blue/green production, with the rollback path drawn in red. The four environments as containers. The expand/contract migration pattern shown as an inset.

---

# PART C — All architecture diagrams (Mermaid)

Store each as `docs/diagrams/<name>.mmd`.

## C.1 High-level system architecture

```mermaid
flowchart TB
    subgraph Clients
        WEB[Web · Next.js]
        PWA[Mobile PWA]
        ADM[Admin Console]
    end
    CDN[CloudFront + WAF]
    ALB[Application Load Balancer]

    subgraph API["API — NestJS modular monolith (ECS Fargate)"]
        AUTH[Auth & Users]
        BIZ[Business & Providers]
        SRCH[Search & Matching]
        VER[Verification]
        PAY[Subscriptions & Payments]
        PROJ[Projects]
        NET[Networking]
        REF[Referrals]
        NOTIF[Notifications]
        ADMIN[Admin & Moderation]
    end

    INTEL[Intelligence Service · FastAPI (Phase 3)]
    WORK[Queue Workers · Fargate]
    LAM[Lambda · webhooks, schedules, S3 triggers]

    subgraph Data
        PG[(PostgreSQL 16<br/>+ pgvector + PostGIS)]
        RDS_R[(Read Replica)]
        REDIS[(Redis)]
        S3[(S3 · private documents)]
        OS[(OpenSearch<br/>future)]
    end

    subgraph External
        BR[Amazon Bedrock<br/>India Geo profiles]
        RZP[Razorpay]
        KYB[KYB provider<br/>GSTIN · MCA21 · UDYAM]
        MAPS[Google Maps]
        SES[SES · SMS · WhatsApp]
    end

    WEB --> CDN
    PWA --> CDN
    ADM --> CDN
    CDN --> ALB --> API
    API --> INTEL
    API --> PG
    API --> REDIS
    API --> S3
    API -->|outbox| SQS[[SQS / EventBridge]]
    SQS --> WORK
    SQS --> LAM
    WORK --> PG
    WORK --> KYB
    WORK --> SES
    INTEL --> BR
    INTEL --> PG
    INTEL --> REDIS
    API --> RZP
    RZP -.webhook.-> LAM
    API --> MAPS
    API --> RDS_R
    WORK -.future.-> OS
    SRCH -.future.-> OS
```

## C.2 AWS architecture

```mermaid
flowchart TB
    U((Users)) --> R53[Route 53]
    R53 --> CF[CloudFront + WAF]
    CF --> S3A[(S3 · static assets<br/>via OAC)]
    CF --> ALB[ALB · public subnets]

    subgraph VPC["VPC · ap-south-1 · 3 AZs"]
        subgraph PUB["Public subnets"]
            ALB
            NAT[NAT Gateway]
        end
        subgraph APP["Private-app subnets"]
            API[ECS · api]
            INT[ECS · intelligence]
            WRK[ECS · workers]
            LMB[Lambda · in-VPC]
        end
        subgraph DAT["Private-data subnets · no NAT route"]
            PROXY[RDS Proxy] --> RDS[(RDS Postgres<br/>Multi-AZ)]
            RDS --> REP[(Read Replica)]
            EC[(ElastiCache Redis)]
        end
        VPE[VPC Endpoints<br/>S3 · SQS · Secrets · KMS · Bedrock · ECR]
    end

    ALB --> API
    API --> INT
    API --> PROXY
    API --> EC
    WRK --> PROXY
    API --> VPE
    INT --> VPE
    WRK --> NAT --> EXT[External APIs<br/>Razorpay · KYB · Maps]
    LMB --> PROXY
```

## C.3 User journey

```mermaid
flowchart TD
    A[Landing] --> B{Role?}
    B -->|I need services| C[User registration]
    B -->|I provide services| Z[Business onboarding]
    C --> D[Progressive profile]
    D --> E[Vertex home]
    E --> F[Natural language query]
    F --> G[Intent extraction]
    G --> H{Confidence?}
    H -->|high| J[Requirements generated]
    H -->|medium| I[Show assumptions inline] --> J
    H -->|low| K[Clarify with options] --> J
    J --> L[Search results per requirement]
    L --> M[Provider profile]
    M --> N{Action}
    N -->|Save| O[Shortlist]
    N -->|Compare| P[Comparison]
    N -->|Contact| Q[Enquiry sent]
    O --> R[My Projects]
    P --> R
    Q --> R
    R --> S[Networking]
    R --> T[Referrals]
    R --> E
```

## C.4 Business onboarding flow

```mermaid
stateDiagram-v2
    [*] --> DRAFT: register
    DRAFT --> PENDING_VERIFICATION: submit
    PENDING_VERIFICATION --> VERIFIED: checks pass, low risk
    PENDING_VERIFICATION --> NEEDS_INFO: missing / unreadable
    PENDING_VERIFICATION --> REJECTED: reviewer decision
    NEEDS_INFO --> PENDING_VERIFICATION: resubmit
    REJECTED --> DRAFT: appeal
    VERIFIED --> ACTIVE: subscription active + profile complete
    ACTIVE --> PAUSED: provider hides listing
    PAUSED --> ACTIVE: resume
    ACTIVE --> SUSPENDED: fraud / abuse
    SUSPENDED --> ACTIVE: resolved
    ACTIVE --> EXPIRED: subscription lapsed
    EXPIRED --> ACTIVE: renewal
```

## C.5 Vertex AI query flow (Phase 3)

```mermaid
flowchart TD
    Q[Raw query] --> P[Preprocess · deterministic<br/>normalise, lakh/crore, spellcheck, PII strip]
    P --> I[Intent + entity extraction<br/>small LLM · JSON schema · temp 0]
    I --> C{Confidence}
    C -->|"< 0.40"| CLR[Clarify with options]
    C -->|">= 0.40"| CAT[Category resolution<br/>embeddings + kNN]
    CAT --> AMB{Top-1 vs top-2 close?}
    AMB -->|yes| DIS[LLM disambiguation]
    AMB -->|no| REQ
    DIS --> REQ[Requirement generation<br/>mid LLM + taxonomy RAG]
    REQ --> SQ[Structured Query]
    SQ --> RET[Retrieval]
    RET --> RNK[Ranking]
    RNK --> RR[Rerank top-30]
    RR --> GEN[Streaming narration]
    GEN --> OUT[SSE to client]

    I -.timeout/error.-> FB1[Rules-based extraction]
    FB1 -.-> FB2[Static requirement template]
    FB2 -.-> FB3[Lexical search only]
    FB3 -.-> FB4[Category browse]
```

## C.6 Search architecture

```mermaid
flowchart TD
    SQ[Structured Query] --> LEX[Lexical retrieval<br/>tsvector + pg_trgm · top 200]
    SQ --> EMB[Embed query]
    EMB --> VEC[Vector retrieval<br/>pgvector HNSW cosine · top 200]
    LEX --> RRF[Reciprocal Rank Fusion · k=60]
    VEC --> RRF
    RRF --> DEDUP[Deduplicate<br/>GSTIN / phone / name trigram]
    DEDUP --> FILT[Hard filters<br/>geo radius · category · active · subscription]
    FILT --> SCORE[Weighted scorer<br/>per-category-family profile]
    SCORE --> TOP[Top 30]
    TOP --> RERANK[Cross-encoder rerank]
    RERANK --> PROMO[Insert promoted slots<br/>reserved, labelled, capped 20%]
    PROMO --> RESULTS[Top 10 shown]
    RESULTS --> LOG[(search_results<br/>impression log)]
    LOG --> EVAL[Offline eval · NDCG@10]
```

## C.7 Verification pipeline

```mermaid
flowchart TD
    S[SUBMITTED] --> AC[AUTOMATED_CHECK]
    AC --> G1[GSTIN lookup]
    AC --> G2[CIN / MCA21 lookup]
    AC --> G3[UDYAM lookup]
    AC --> G4[Penny drop]
    AC --> G5[Domain + email]
    AC --> G6[Address geocode]
    G1 & G2 & G3 & G4 & G5 & G6 --> RISK[Risk score 0-100]
    RISK --> D{Band}
    D -->|"< 30 LOW"| APP[APPROVED · T1/T2 auto]
    D -->|"30-59 MEDIUM"| DR[DOCUMENT_REVIEW]
    D -->|">= 60 HIGH"| MR[MANUAL_REVIEW]
    DR --> OCR[OCR + extraction]
    OCR --> CONF{Extraction confidence}
    CONF -->|high, matches registry| APP
    CONF -->|low or mismatch| MR
    MR --> DEC{Reviewer decision}
    DEC -->|approve| APP
    DEC -->|reject| REJ[REJECTED + reason]
    DEC -->|need more| MI[MORE_INFORMATION_REQUIRED] --> S
    APP --> EXP[EXPIRED at expires_at] --> RV[REVERIFICATION_REQUIRED] --> S
```

## C.8 Subscription and payment flow

```mermaid
sequenceDiagram
    participant P as Provider
    participant W as Web
    participant A as API
    participant R as Razorpay
    participant L as Webhook Lambda
    participant DB as PostgreSQL

    P->>W: Select plan
    W->>A: POST /subscriptions/checkout
    A->>DB: Read plan (amount from OUR db)
    A->>R: Create subscription
    R-->>A: subscription_id + checkout params
    A-->>W: Checkout params
    W->>R: Hosted checkout (card data never touches Vertex)
    P->>R: Pay (UPI / card / netbanking)
    R-->>W: Success callback
    Note over W: UI shows "Confirming…" — GRANTS NOTHING
    R->>L: Webhook payment.captured
    L->>L: Verify HMAC signature
    L->>DB: Insert webhook_events (dedupe on provider_event_id)
    L->>DB: Subscription ACTIVE
    L->>DB: Materialise entitlements
    L->>DB: Generate invoice
    L->>W: (via SSE) Activated
```

## C.9 Referral flow

```mermaid
stateDiagram-v2
    [*] --> CREATED: referrer generates code
    CREATED --> CLICKED: link opened
    CLICKED --> SIGNED_UP: account created (30d first-touch window)
    SIGNED_UP --> QUALIFIED: verification submitted
    QUALIFIED --> CONVERTED: first payment captured
    CONVERTED --> REWARD_PENDING: 30d clawback window opens
    REWARD_PENDING --> REWARD_PAID: window elapsed, no reversal
    REWARD_PENDING --> REVERSED: refund / chargeback / fraud
    SIGNED_UP --> REJECTED: fraud detected
    QUALIFIED --> REJECTED: fraud detected
```

## C.10 Networking flow

```mermaid
flowchart TD
    A[User] --> B{Opt in to networking?}
    B -->|no| Z[Not listed anywhere]
    B -->|yes| C[Create networking profile]
    C --> D[Matching engine]
    D --> E[Industry overlap 0.25]
    D --> F[Stage complementarity 0.20]
    D --> G[Location proximity 0.20]
    D --> H[Interest overlap 0.15]
    D --> I[Activity recency 0.10]
    D --> J[Mutual connections 0.10]
    E & F & G & H & I & J --> K[Ranked suggestions]
    K --> L[Connection request + mandatory note]
    L --> M{Response}
    M -->|accept| N[Connected · messaging enabled]
    M -->|decline| O[Throttle sender on repeats]
    M -->|block| P[Moderation queue]
```

## C.11 Project architecture

```mermaid
erDiagram
    USER ||--o{ USER_PROJECT : owns
    USER_PROJECT ||--o{ PROJECT_REQUIREMENT : contains
    USER_PROJECT ||--o{ PROJECT_PROVIDER : shortlists
    USER_PROJECT ||--o{ PROJECT_TASK : tracks
    USER_PROJECT ||--o{ CONVERSATION : contextualises
    PROJECT_REQUIREMENT ||--o{ PROJECT_PROVIDER : "grouped by"
    PROJECT_REQUIREMENT }o--|| CATEGORY : "maps to"
    PROJECT_PROVIDER }o--|| BUSINESS : references
```

## C.12 Notification architecture

```mermaid
flowchart LR
    EV[Domain event] --> DISP[Notification dispatcher]
    DISP --> PREF{Check user preferences<br/>per category}
    PREF -->|in-app always| IA[(notifications table)]
    PREF -->|email allowed| EM[SES]
    PREF -->|sms allowed| SM[DLT-registered SMS]
    PREF -->|whatsapp opted-in| WA[WhatsApp Business API]
    PREF -->|push allowed| PU[Web Push]
    IA --> SSE[SSE to client]
    EM & SM & WA & PU --> LOG[(delivery log<br/>template_id + version)]
    note1[SECURITY category<br/>cannot be disabled] -.-> PREF
```

## C.13 Event-driven architecture

```mermaid
flowchart LR
    subgraph TX["Single database transaction"]
        ST[State change] --> OB[(outbox row)]
    end
    OB --> REL[Outbox relay · polls undispatched]
    REL --> SQS[[SQS standard]]
    REL --> FIFO[[SQS FIFO<br/>MessageGroupId = aggregate_id]]
    SQS --> C1[Notification worker]
    SQS --> C2[Search indexer]
    SQS --> C3[Analytics sink]
    FIFO --> C4[Verification state worker]
    FIFO --> C5[Subscription worker]
    C1 & C2 & C3 & C4 & C5 --> IDEM{Seen event_id?}
    IDEM -->|yes| SKIP[Skip · idempotent]
    IDEM -->|no| PROC[Process]
    PROC -->|fail x5| DLQ[[Dead letter queue]]
    DLQ --> ALARM[Alarm on depth > 0]
    ALARM --> REPLAY[Documented replay runbook]
```

## C.14 ER diagram (core)

```mermaid
erDiagram
    USER ||--o| USER_PROFILE : has
    USER ||--o{ USER_ROLE : holds
    USER ||--o{ CONSENT : grants
    USER ||--o{ BUSINESS : owns
    USER ||--o{ USER_PROJECT : creates
    USER ||--o{ SEARCH : performs
    USER ||--o{ PROVIDER_CONTACT : initiates
    USER ||--o{ REVIEW : writes
    USER ||--o| NETWORKING_PROFILE : "opts into"
    USER ||--o{ REFERRAL : refers

    BUSINESS ||--o| BUSINESS_PROFILE : has
    BUSINESS ||--o{ BUSINESS_CATEGORY : "listed in"
    BUSINESS ||--o{ BUSINESS_LOCATION : "operates at"
    BUSINESS ||--o{ PROVIDER_SERVICE : offers
    BUSINESS ||--o| PROVIDER_METRICS : "measured by"
    BUSINESS ||--o{ VERIFICATION_CASE : "verified through"
    BUSINESS ||--o| SUBSCRIPTION : pays
    BUSINESS ||--o| ENTITLEMENT : granted
    BUSINESS ||--o{ PAYMENT : makes
    BUSINESS ||--o{ REVIEW : receives

    CATEGORY ||--o{ CATEGORY : "parent of"
    CATEGORY ||--o{ BUSINESS_CATEGORY : classifies
    CATEGORY ||--o{ CATEGORY_EMBEDDING : "embedded as"

    VERIFICATION_CASE ||--o{ VERIFICATION_DOCUMENT : evidences
    VERIFICATION_CASE ||--o{ VERIFICATION_CHECK : runs
    VERIFICATION_CASE ||--o{ VERIFICATION_EVENT : "audited by"

    SUBSCRIPTION }o--|| PLAN : "instance of"
    PAYMENT ||--o| INVOICE : generates

    SEARCH ||--o{ SEARCH_RESULT : produces
    SEARCH_RESULT }o--|| BUSINESS : ranks
    PROVIDER_CONTACT ||--o| REVIEW : "gates"

    USER_PROJECT ||--o{ PROJECT_REQUIREMENT : contains
    USER_PROJECT ||--o{ PROJECT_PROVIDER : shortlists
    REFERRAL ||--o{ REFERRAL_EVENT : logs
    REFERRAL ||--o| REFERRAL_REWARD : earns
```

## C.15 Deployment architecture

```mermaid
flowchart LR
    DEV[Developer] --> PR[Pull request]
    PR --> G1[Lint + typecheck]
    PR --> G2[Unit + integration]
    PR --> G3[SAST · secrets · deps · IaC scan]
    PR --> G4[Container build + Trivy]
    PR --> G5[AI eval suite]
    G1 & G2 & G3 & G4 & G5 --> REV[Review + approval]
    REV --> MAIN[Merge to main]
    MAIN --> ECR[Push to ECR · tag = git SHA]
    MAIN --> TF[terraform apply · staging]
    TF --> MIG[DB migration · expand phase only]
    MIG --> STG[Deploy staging]
    STG --> SMOKE[Smoke + E2E + load]
    SMOKE --> APPR{Manual approval}
    APPR -->|yes| CAN[Canary 10%]
    CAN --> HC{Health checks + alarms}
    HC -->|pass| FULL[100% blue/green]
    HC -->|fail| RB[Automatic rollback]
```

## C.16 Security architecture

```mermaid
flowchart TB
    subgraph L1["Layer 1 · Edge"]
        WAF[WAF managed rules + rate rules]
        CFD[CloudFront · TLS 1.2+]
        DDOS[Shield Standard]
    end
    subgraph L2["Layer 2 · Network"]
        SG[Security groups · least privilege]
        PRIV[Private subnets · no public IPs]
        ISO[Isolated data subnets · no NAT route]
    end
    subgraph L3["Layer 3 · Application"]
        AUTHN[Argon2id · JWT · refresh rotation + family reuse detection · MFA]
        AUTHZ[RBAC + ownership check on every resource]
        VAL[Zod validation at every boundary]
        RL[Redis rate limiting · burst + sustained]
    end
    subgraph L4["Layer 4 · Data"]
        TLS[TLS in transit]
        KMS[KMS · separate CMKs per domain]
        APPENC[Application-level encryption<br/>bank · PAN · MFA secrets]
        PRESIGN[Presigned URLs ≤5 min + per-access authz]
    end
    subgraph L5["Layer 5 · Detect"]
        AUDIT[Append-only audit log]
        FRAUD[Risk scoring]
        ALERT[Alarms + on-call]
    end
    L1 --> L2 --> L3 --> L4 --> L5

    UNTRUSTED[UNTRUSTED INPUT<br/>queries · provider content · documents · OCR · external APIs]
    UNTRUSTED -.->|data only, never instructions| L3
```

## C.17 CI/CD pipeline

*(Rendered as C.15; kept as a separate `.mmd` file for the Miro frame B12 so the pipeline can be refreshed independently of the deployment topology.)*

## C.18 Data flow diagram

```mermaid
flowchart LR
    U[User] -->|query text| API
    API -->|normalised, PII-stripped| INTEL[Intelligence (Phase 3)]
    INTEL -->|prompt| BR[Bedrock · India Geo (Phase 3)]
    BR -->|structured JSON| INTEL
    INTEL -->|structured query| API
    API -->|SQL + vector| PG[(PostgreSQL)]
    PG -->|candidates| API
    API -->|SSE| U

    P[Provider] -->|profile data| API
    P -->|documents| S3[(S3 private)]
    S3 -->|S3 event| OCRW[OCR worker]
    OCRW -->|extracted fields| PG
    API -->|identifiers only| KYB[KYB provider]
    KYB -->|registry result| PG

    P -->|payment| RZP[Razorpay]
    RZP -->|signed webhook| LAM[Webhook Lambda]
    LAM -->|entitlements| PG

    PG -->|events via outbox| SQS[[SQS]]
    SQS --> AN[(Analytics)]

    classDef sensitive fill:#FEE2E2,stroke:#DC2626
    class S3,KYB,RZP sensitive
```

## C.19 Provider ranking pipeline

```mermaid
flowchart TD
    CAND[~300 fused candidates] --> F[Hard filters]
    F --> S1[semantic_relevance × 0.30]
    F --> S2[category_match × 0.15]
    F --> S3[location_score × 0.12]
    F --> S4[verification_score × 0.10]
    F --> S5[rating_bayesian × 0.08]
    F --> S6[responsiveness × 0.07]
    F --> S7[availability × 0.06]
    F --> S8[price_fit × 0.05]
    F --> S9[personalization × 0.04]
    F --> S10[historical_conversion × 0.03]
    S1 & S2 & S3 & S4 & S5 & S6 & S7 & S8 & S9 & S10 --> SUM[Weighted sum]
    PEN[Penalties · disputes, strikes, stale profile] --> SUM
    SUM --> PROF[Per-category-family weight profile applied]
    PROF --> EXPL[Exploration slot · new providers, 30 days]
    EXPL --> TOP30[Top 30]
    TOP30 --> RR[Rerank]
    RR --> FINAL[Final 10]
```

## C.20 AI architecture (Phase 3)

```mermaid
flowchart TB
    FE[Frontend] --> GW[AI Gateway]
    GW --> RT{Model router}
    RT -->|classification| SM[Small model]
    RT -->|generation| MM[Mid model]
    RT -->|embedding| EMB[Embedding model]
    SM & MM & EMB --> BR[Bedrock · in. India Geo profiles]
    BR -.provider outage.-> FBK[Direct vendor API fallback]

    GW --> CACHE[(Redis<br/>embedding cache 30d<br/>query cache 1h)]
    GW --> BUD[Token budgets<br/>per user · per tenant · global]
    GW --> TEL[(Telemetry<br/>latency · tokens · cost/query)]

    EMB --> PGV[(pgvector<br/>provider + category embeddings)]
    MM --> RAG[Taxonomy RAG context]
    RAG --> PGV

    TEL --> EVALD[(Eval dataset)]
    EVALD --> CI[CI eval suite · blocks on regression]
```

---

## C.21 TGL ecosystem flywheel (new — Doc 00 §0.2a)

```mermaid
flowchart LR
    EV[TGL Event] --> REG[Registration]
    REG --> MEM[TGL Membership pending<br/>then 3 calendar months after Grand Finale]
    MEM --> NET[Networking participation<br/>Trust Score · Growth Points]
    NET --> VER[TGL Verified badge<br/>admin-controlled criteria]
    VER --> VTX[Vertex profile credibility]
    VTX --> DISC[Discovered by a Vertex user]
    DISC --> ENQ[Enquiry / business closed]
    ENQ --> STORY[Success story]
    STORY --> MEDIA[TGL Podcast / SkyKeen Media]
    MEDIA --> AWARE[More awareness]
    AWARE --> EV2[Next TGL Event]
    EV2 -.same loop.-> REG
```

## C.22 Membership grant + renewal pipeline (new — Doc 04 §4.1a)

```mermaid
sequenceDiagram
    participant M as Prospective member
    participant W as Web
    participant A as API
    participant R as Razorpay
    participant DB as PostgreSQL

    M->>W: Register for a TGL event
    W->>A: POST /events/{id}/register
    A->>R: Create order (event fee, from OUR db)
    M->>R: Pay
    R->>A: Webhook payment.captured (signature verified)
    A->>DB: event_registrations.status = REGISTERED
    A->>DB: EventRegistrationConfirmed emitted
    A->>DB: tgl_memberships row created<br/>pathway=EVENT_REGISTRATION, status=PENDING
    A->>DB: NetworkingProfile auto-created
    Note over M,DB: After Grand Finale completion — activate for 3 calendar months
    M->>W: Select 3/6/12-month plan
    W->>A: POST /memberships/renew
    A->>R: Create order (amount from membership_plans)
    M->>R: Pay
    R->>A: Webhook payment.captured
    A->>DB: current_period_end extended, Growth Points redemption applied (capped)
```

## C.23 Business referral lifecycle (new — Doc 01 §10.3)

```mermaid
stateDiagram-v2
    [*] --> GIVEN: member refers a business opportunity
    GIVEN --> ACCEPTED: referred_to member accepts
    GIVEN --> DECLINED: referred_to member declines
    ACCEPTED --> MEETING_DONE
    MEETING_DONE --> BUSINESS_CLOSED
    BUSINESS_CLOSED --> REVENUE_GENERATED
    BUSINESS_CLOSED --> [*]: Growth Points awarded (high weight, Doc 01 §10.4)<br/>Trust Score input (both parties)
    GIVEN --> EXPIRED: no response within SLA
    note right of BUSINESS_CLOSED
        Distinct from the growth/acquisition
        referral state machine (C.9) — different
        table, different trigger, different reward
    end note
```

---

# PART D — Required tables index

Every table the brief asked for, and where it lives:

| Table | Document |
|---|---|
| Technology stack + alternatives | Doc 00 §0.6 |
| Architectural decisions (12 ADRs) | Doc 00 §0.7 |
| Database entities | Doc 03 §2 |
| API endpoints | Doc 03 §4.2 |
| Roles & permissions | Doc 04 §3.2 |
| Subscription plans / feature matrix | Doc 01 §6.2 |
| Verification methods + decision matrix | Doc 04 §2.3 |
| AWS services (and services deliberately excluded) | Doc 04 §1.2 |
| Roadmap phases | Doc 06 §1 |
| Engineering epics | Doc 06 §10 |
| Security threats (STRIDE) | Doc 04 §3.3 |
| Cost assumptions | Doc 06 §8 |
| Technical risks | Doc 06 §9 |
| KPIs | Doc 06 §6.3 |
| Ranking weights + justification | Doc 02 §4.3 |
| Rate limits | Doc 04 §3.5 |
| Data retention | Doc 03 §8 |
| Failure modes | Doc 04 §8 |
| Open decisions | Doc 00 §0.10 |
| TGL brand history / platform structure | Doc 00 §0.2a |
| Networking (Trust Score, Growth Points, business referrals, chapters, awards) | Doc 01 §10 |
| Membership rules and pricing | Doc 01 §13 |
| Events, Awards, Podcasts | Doc 01 §14 |
| Navigation (5-tab structure) | Doc 01 §4, Doc 05 (header) |
| Membership/event schema | Doc 03 §2.6a |
| Membership payment flow | Doc 04 §4.1a |
| Networking-corrected MVP scope | Doc 06 §2, banner |
