# TGL · Document 04
## Cloud Infrastructure, Verification/KYB, Security, Payments (Vertex subscriptions + TGL Membership), Compliance, Observability, CI/CD

---

# 1. Cloud architecture

## 1.1 Region

**Primary: `ap-south-1` (Mumbai). DR: `ap-south-2` (Hyderabad).**

| Criterion | Reasoning |
|---|---|
| Latency | Sub-30ms to Bengaluru, Mumbai, Delhi, Hyderabad, Chennai |
| Data residency | DPDP compliance is far simpler when personal data never leaves India. This is a design choice, not a claimed legal requirement — **[the DPDP Rules' cross-border provisions require counsel review; do not assert a specific legal mandate]** |
| AI residency | (cite index="29-1">Bedrock India Geo inference profiles route requests only within the India geography, across Mumbai and Hyderabad, keeping data processed within India for data residency</cite> — this is the reason to use Bedrock rather than a direct vendor API |
| Model availability | (cite index="26-1">ap-south-1 hosts 61 models from 14 publishers on Bedrock</cite>. **[VALIDATE current availability at build time — this changes monthly]** |
| Cost | India regions run modestly above `us-east-1` for some services. **[VALIDATE against the current AWS pricing calculator]** Accepted for latency and residency |
| Availability zones | 3 AZs available — sufficient for Multi-AZ RDS and spread ECS placement |

**Expansion path:** if Vertex adds a second country, add a region rather than serving cross-border. Provider data is inherently local; there is no benefit to a global write path and a lot of latency cost.

## 1.2 Services actually used (and the ones deliberately not)

| Service | Purpose | Why required |
|---|---|---|
| Route 53 | DNS, health checks, failover records | — |
| CloudFront | Static assets, Next.js output, public provider pages | Origin offload + India edge locations |
| AWS WAF | Managed rules + rate rules on the ALB and CloudFront | First line against bots, injection, credential stuffing |
| ALB | HTTPS termination, path routing to ECS services | Simpler and cheaper than API Gateway for a container backend |
| ECS Fargate | `api`, `intelligence` (Phase 3), `workers` | No servers, no cluster to operate |
| Lambda | Webhook receivers, scheduled jobs, document post-processing | Bursty, short, event-driven — exactly the serverless fit |
| RDS PostgreSQL 16 | Primary datastore, Multi-AZ, 1 read replica | — |
| RDS Proxy | Connection pooling | Fargate tasks scale out and exhaust Postgres connections without it |
| ElastiCache Redis | Cache, sessions, rate limits, locks | — |
| S3 | Documents (private), assets (via CloudFront OAC), backups, logs | — |
| SQS | Work queues + FIFO for ordered domain events | — |
| EventBridge | Fan-out and scheduled rules | — |
| Secrets Manager | All credentials, rotated | — |
| KMS | CMKs: one for S3 documents, one for RDS, one for application-level field encryption | Separate keys = separate blast radius |
| CloudWatch | Logs, metrics, alarms, dashboards | — |
| X-Ray | Distributed tracing | — |
| Bedrock | LLM + embeddings, India Geo profiles | — |
| ECR | Container registry with image scanning | — |
| VPC / NAT / SGs | Network isolation | — |
| Backup | Centralised backup policy, cross-region copy | — |

**Deliberately not used at MVP:** API Gateway (ALB is sufficient and cheaper for containers), OpenSearch (see ADR-005), Cognito (a custom auth module gives control over the role model, which is unusual here — and MFA/OAuth are solved libraries), Step Functions (the verification state machine lives in application code where it can be tested), Kinesis (SQS is enough), Aurora (RDS Postgres is enough at this scale), AppSync, MSK, SageMaker.

## 1.3 Network topology

```
Internet
  └─ Route 53
      └─ CloudFront (+ WAF, managed rules)      → S3 static (OAC), /api/* → ALB
          └─ ALB (public subnets, HTTPS only, WAF attached)
              └─ ECS Fargate services (PRIVATE subnets, no public IP)
                  ├─ api            (NestJS)
                  ├─ intelligence   (FastAPI, Phase 3)  ← reachable only from api's SG
                  └─ workers        (queue consumers, no inbound)
                      └─ Data tier (PRIVATE, ISOLATED subnets — no route to NAT)
                          ├─ RDS Postgres (Multi-AZ) via RDS Proxy
                          ├─ ElastiCache Redis
                          └─ VPC endpoints: S3, SQS, Secrets Manager, KMS, Bedrock, ECR
```

**Subnet layout across 3 AZs:** public (ALB, NAT only) · private-app (ECS, Lambda-in-VPC) · private-data (RDS, Redis — **no route to a NAT gateway at all**).

**Security group rules, stated as intent:**
- ALB SG: inbound 443 from CloudFront prefix list only. Not `0.0.0.0/0` — that lets an attacker bypass WAF by hitting the ALB directly.
- api SG: inbound from ALB SG only.
- intelligence SG: inbound from api SG only. Nothing else can reach the AI service.
- data SG: inbound Postgres/Redis ports from api SG and workers SG only.
- Egress: default-deny where practical, allowed to VPC endpoints and an explicit allow-list of external APIs (Razorpay, KYB vendor, Google Maps) via NAT.

**VPC endpoints matter for cost as well as security.** S3 and Bedrock traffic through a NAT gateway is billed per GB; through a gateway/interface endpoint it is not, and it never leaves the AWS network.

## 1.4 Compute placement: containers vs serverless

| Workload | Runtime | Why |
|---|---|---|
| Product API | Fargate | Long-lived connections, DB connection pooling, steady traffic, predictable latency |
| Intelligence service (Phase 3) | Fargate | Loads models/tokenisers; cold starts would be user-visible on the core product surface |
| Queue workers | Fargate | Long-running, high-throughput, benefit from warm connections |
| Payment/KYB webhooks | **Lambda** | Bursty, tiny, must be always-available even when the API is scaling; isolates a spike in webhook traffic from user traffic |
| Scheduled jobs (metrics recompute, retention sweeps, reconciliation) | **Lambda** + EventBridge Scheduler | Periodic; paying for idle containers makes no sense |
| Document post-processing (OCR trigger, thumbnails) | **Lambda** on S3 events | Event-driven by nature |
| Reindex / bulk backfill | Fargate one-off task | Exceeds Lambda's time limit |

The rule: **Lambda for spiky, short, event-driven work; containers for anything with warm state, long execution, or user-facing latency sensitivity.**

## 1.5 Disaster recovery

| | MVP target | Enterprise target |
|---|---|---|
| **RPO** | 5 minutes (PITR) | 1 minute (cross-region replica) |
| **RTO** | 4 hours | 30 minutes |
| Backups | RDS automated, 30-day PITR; daily snapshot copied to `ap-south-2` | + continuous cross-region read replica |
| S3 | Versioning + cross-region replication for the document bucket | Same |
| Redis | Not backed up — it is a cache by design | Snapshot only if used for anything durable (it should not be) |
| IaC | Full environment rebuildable from Terraform | Same |
| Secrets | Replicated to DR region | Same |

**Recovery drill: quarterly, mandatory, timed.** Restore a snapshot into a scratch environment, run smoke tests, record the actual RTO, fix whatever was slower than the target. A DR plan that has never been executed is a document, not a capability. Also verify backups are *restorable*, not merely *present* — automated monthly restore-and-checksum job.

## 1.6 Performance and global expansion

| Layer | Approach |
|---|---|
| CDN | CloudFront for static assets and **public provider profile pages** (60s TTL). Personalised and search responses **bypass the edge cache** — the personalisation term in ranking makes any shared cache entry wrong for someone |
| API cache | Redis for hot query results (1h), category tree (1h), provider profiles (5min), with event-driven invalidation from the outbox |
| Database | RDS Proxy pooling; a read replica for analytics and heavy reads; a strict rule that no report query runs on the primary |
| Search | Postgres HNSW tuned (`ef_search`) per latency budget; OpenSearch at the migration trigger |
| Images | S3 + CloudFront + on-the-fly resize via Lambda@Edge or a Next.js image loader; WebP/AVIF |
| Frontend | RSC + streaming, route-level code splitting, lazy loading below the fold |
| International | Add a region with its own data plane; keep provider data local; a shared control plane only if genuinely needed. Do **not** build an active-active global write path for a marketplace whose inventory is geographically bound |

---

# 2. Verification / KYB architecture

## 2.1 What Vertex verifies (India-specific)

| Layer | Evidence | Source |
|---|---|---|
| **Business identity** | Legal name, entity type, incorporation status, directors | MCA21 via CIN; UDYAM portal; GSTIN registry |
| **Tax identity** | GSTIN status, registration date, filing history, trade name | GST registry |
| **Physical address** | Address on the certificate vs. submitted address; geocode confidence; utility bill | Registry + geocoding + document |
| **Contact** | Phone OTP; business email domain matching the website; domain ownership (DNS TXT) | Platform |
| **Digital presence** | Website liveness, domain age, social profiles, name consistency | WHOIS/RDAP, HTTP checks |
| **Banking** | Penny-drop: name on the account vs. legal name | Bank verification API |
| **Beneficial owner** | Director/proprietor ID verification | IDV provider |

**Clear distinction the brief asked for:**
- **Company verification** — does this legal entity exist and is it active? (MCA21/GST/UDYAM)
- **Beneficial-owner verification** — who actually owns and controls it? (director list → natural persons)
- **Identity verification (KYC)** — is this individual who they claim to be? (ID document + liveness)
- **Bank verification** — does this account exist and belong to this entity? (penny drop)

These are four different checks with four different failure modes. Conflating them is how a verification system approves a real company controlled by an impostor.

## 2.2 State machine

```
DRAFT ──submit──► SUBMITTED ──auto──► AUTOMATED_CHECK
                                          │
        ┌─────────────────────────────────┼──────────────────────────────┐
        │ all pass, low risk              │ partial / medium risk        │ hard fail
        ▼                                 ▼                              ▼
     APPROVED                      DOCUMENT_REVIEW                   REJECTED
        │                                 │                              │
        │                        ┌────────┴─────────┐                    │
        │                        ▼                  ▼                    │
        │                MANUAL_REVIEW      MORE_INFORMATION_REQUIRED    │
        │                     │  │                  │                    │
        │        ┌────────────┘  └──────────┐       └──► SUBMITTED       │
        │        ▼                          ▼            (attempt+1)     │
        │    APPROVED                   REJECTED ◄────────────────────────┘
        │
        ├── time ──► EXPIRED ──► REVERIFICATION_REQUIRED ──► SUBMITTED
        └── fraud/abuse ──► SUSPENDED
```

**Transition authority:**

| Transition | Who/what may trigger |
|---|---|
| `DRAFT → SUBMITTED` | Provider |
| `SUBMITTED → AUTOMATED_CHECK` | System (queue worker) |
| `AUTOMATED_CHECK → *` | System, by rule on check results + risk score |
| `DOCUMENT_REVIEW → MANUAL_REVIEW` | System (low OCR confidence) or reviewer |
| `* → APPROVED` at T3 | **Reviewer only.** Never automated |
| `* → APPROVED` at T1/T2 | System, if all checks pass and risk is low |
| `* → REJECTED` | Reviewer only (with a mandatory written reason) |
| `* → MORE_INFORMATION_REQUIRED` | System or reviewer |
| `APPROVED → EXPIRED` | Scheduled job at `expires_at` |
| `* → SUSPENDED` | Moderator or fraud engine |

**T3 requires a human.** The highest trust badge must never be issuable by an automated pipeline alone, because that badge is what users rely on when spending money.

## 2.3 Implementation approach comparison

| | **A. API-based** | **B. Document + OCR + AI** | **C. Manual** | **D. Hybrid ← recommended** |
|---|---|---|---|---|
| Architecture | Call registry APIs via a KYB aggregator | Upload → scan → OCR → extract → confidence | Reviewer reads everything | API first, OCR second, human last |
| Speed | Seconds | Minutes | Hours to days | Seconds for most, hours for the tail |
| Cost | Per-check fee | Compute + partial human | Fully loaded human cost | Lowest blended cost |
| Accuracy | Very high (registry is authoritative) | Medium-high, degrades on poor scans | High but inconsistent between reviewers | High |
| Coverage | **Only registered entities** | Anything with a document | Anything | **Full** |
| Complexity | Low | High | Low tech, high ops | Medium-high |
| Dependency risk | Vendor outage blocks onboarding | Self-contained | None | Mitigated by fallback to B and C |
| Fraud resistance | High (registry data can't be forged) | Medium (documents can be) | Medium (reviewers can be fooled) | High |

**Decision matrix (1 = poor, 5 = excellent):**

| Criterion | A | B | C | **D** |
|---|---|---|---|---|
| Implementation difficulty | 4 | 2 | 5 | 2 |
| Cost at scale | 3 | 4 | 1 | **4** |
| Reliability | 4 | 3 | 3 | **5** |
| Speed | 5 | 3 | 1 | **4** |
| Scalability | 5 | 4 | 1 | **5** |
| Compliance defensibility | 4 | 3 | 4 | **5** |
| Coverage (Indian SMB long tail) | 2 | 5 | 5 | **5** |
| Fraud resistance | 5 | 3 | 3 | **5** |
| **Weighted total** | 32 | 27 | 23 | **35** |

**Recommendation: D (hybrid), for the reason in Doc 00 Correction 4** — API-only verification excludes the unregistered long tail, which is most of your supply.

## 2.4 Vendor selection

(cite index="15-1">Key providers in the Indian market include BeFiSc, HyperVerge, Signzy, Karza/Perfios, IDfy, and Surepass; evaluate on regulatory certification, real-time data access, uptime SLA, and API documentation quality rather than brand recognition alone.</cite> (cite index="11-1">Positioning differs by strength: Signzy for bank-grade enterprise KYB, Karza for financial due diligence, AuthBridge for deep background checks, IDfy for KYB with fraud detection.</cite>

**Process, not a pick:** shortlist three, run a pilot against 50 real provider files spanning a private limited company, an LLP, a partnership, a GST-registered proprietorship and an unregistered proprietorship. Measure per-vendor: match rate, false positives, false negatives, p95 latency, per-check cost, uptime, and how they behave when the underlying registry is down. Choose on the pilot, not the sales deck. Build behind a `KybProvider` interface with at least two implementations so vendor switching is a config change.

## 2.5 Fraud risk scoring

```
risk_score (0–100) = Σ weighted signals

Identity signals
  duplicate GSTIN/CIN across accounts              +40
  document sha256 seen on another account          +35
  legal name ≠ name on bank account                +30
  registry status inactive/struck-off/cancelled    +50
  director disqualified (MCA §164(2))              +45

Contact signals
  disposable email domain                          +20
  domain age < 30 days                             +15
  phone already on N other accounts                +25
  business email domain ≠ website domain           +10

Behavioural signals
  >3 accounts from one IP in 24h                   +30
  impossible-travel signup pattern                 +20
  verification resubmitted >3 times                 +15
  profile edited immediately after approval        +25   ← classic bait-and-switch

Address signals
  geocode confidence < 0.5                         +15
  address matches a known virtual-office cluster   +10
  address shared with >5 other accounts            +20

Mitigating signals
  GSTIN active with 12+ months of filing history   −25
  penny drop passed with exact name match          −20
  domain age > 2 years                             −15
  website live, consistent, with matching contact  −10
```

```
score < 30   → LOW    : automatic approval path (T1/T2 eligible)
30 ≤ s < 60  → MEDIUM : additional verification required, then manual review
score ≥ 60   → HIGH   : manual review mandatory; no auto-approval at any tier
```

**Two rules that matter more than the weights:**
1. **No single signal auto-rejects.** Real businesses trip individual signals constantly — a legitimate new company has a 20-day-old domain. Rejecting on one signal produces false positives that cost you supply.
2. **Every score is explainable.** The reviewer UI shows which signals fired and their contribution. A score with no explanation is a score nobody trusts, and reviewers will start ignoring it.

Weights start hand-tuned and are recalibrated quarterly against confirmed-fraud outcomes.

## 2.6 Reviewer tooling and SLA

Queue with priority ordering (risk score, SLA age, provider tier) · side-by-side view of extracted data vs. registry response vs. document image · one-click approve/reject with a **mandatory** reason from a controlled list plus free text · escalation to a senior reviewer · every action audit-logged with the actor · reviewer performance metrics (throughput, reversal rate) reviewed for quality drift, not for speed pressure.

Target SLAs: T1 auto (seconds) · T2 auto or <4 business hours if reviewed · T3 <24 business hours · `MORE_INFORMATION_REQUIRED` responses <8 business hours.

**Staff this from launch.** An unstaffed queue silently becomes a rubber stamp, and the badge stops meaning anything — which destroys the moat described in Doc 00 §0.8.

---

# 3. Security architecture

## 3.1 Authentication

| Control | Implementation |
|---|---|
| Password hashing | **Argon2id** (memory-hard). bcrypt cost ≥12 acceptable as a fallback. Never SHA-anything |
| Password policy | Minimum 12 characters, checked against a breached-password list. No forced rotation, no composition rules — both reduce real-world security |
| Access token | JWT, 15 min, RS256, `kid` in the header, keys rotated, minimal claims (`sub`, `roles`, `jti`) |
| Refresh token | Opaque, 30 days, httpOnly + Secure + SameSite=Lax cookie, rotated on use, **family reuse detection** revokes the family |
| MFA | TOTP; optional for users; **mandatory for all admin, reviewer and moderator roles** |
| OAuth | Google, with PKCE and a state parameter |
| Lockout | Progressive delay after 5 failures, then a 15-min lock; alert on distributed credential-stuffing patterns |
| Session revocation | Server-side session registry in Redis; a role change or password reset invalidates all sessions immediately |

## 3.2 Authorisation (RBAC + ownership)

| Role | Scope | Key permissions |
|---|---|---|
| `USER` | Self | Search, save, contact, project CRUD, review own contacts |
| `BUSINESS_OWNER` | One business | Full control, billing, team management, verification submission |
| `BUSINESS_ADMIN` | One business | Everything except billing and deletion |
| `BUSINESS_STAFF` | One business | Read dashboard, respond to leads |
| `VERIFICATION_REVIEWER` | Global, verification only | Read cases and documents, decide, escalate. **No** access to payments or user PII beyond the case |
| `MODERATOR` | Global, content only | Review reviews, suspend listings, handle reports |
| `SUPPORT_AGENT` | Global, read-mostly | Read accounts, trigger resends. **No** document access, no refunds |
| `SUPER_ADMIN` | Global | Everything, including role grants. MFA mandatory, all actions audited, **minimum count of holders** |

**Two rules:**
- Authorisation is **role + ownership**, always both. Holding `BUSINESS_OWNER` is not enough; you must own *that* business. Every handler resolves the resource and checks the relationship.
- **Least privilege inside the admin surface too.** A support agent who can read verification documents is a data-breach surface with no corresponding business need.

## 3.3 STRIDE threat model

| Surface | Threat | Mitigation |
|---|---|---|
| **Auth** | *Spoofing:* credential stuffing | Rate limits, lockout, breached-password check, MFA, WAF bot rules |
| | *Elevation:* JWT tampering | RS256, signature verification, short expiry, no role claims trusted without a server check on sensitive actions |
| | *Repudiation:* "I didn't do that" | Audit log with IP, UA, request ID |
| **Provider registration** | *Spoofing:* impersonating a real business | KYB registry checks, penny drop, document review, duplicate detection |
| | *Tampering:* editing after approval | Material edits (legal name, GSTIN, bank) trigger re-verification and drop the tier pending re-check |
| **Verification** | *Information disclosure:* document leakage | Private bucket, presigned URLs ≤5 min, per-access authorisation, access audit log, no documents in logs or error messages |
| | *Tampering:* forged documents | Registry cross-check is authoritative over the document; OCR-vs-registry mismatch escalates |
| **Document upload** | *DoS:* huge or malicious files | Presigned PUT with content-length and content-type constraints, virus scan before readability, image/PDF re-render to strip embedded content |
| **Payments** | *Tampering:* client-side amount manipulation | Amount set server-side; webhook signature verification; **entitlements granted only on verified webhook** |
| | *Repudiation:* disputed charges | Full payment audit trail, invoice immutability |
| **Search** | *DoS:* expensive query flooding | Rate limits, query cost budget, timeouts, circuit breaker on spend |
| | *Information disclosure:* enumerating provider contacts | Contact reveal is authenticated, quota-limited, and logged |
| **Reviews** | *Tampering:* fake reviews | `contact_id` requirement, fraud scoring, moderation |
| **Referrals** | *Tampering:* self-referral | Device/IP/payment fingerprinting, clawback window, manual approval above a threshold |
| **Admin** | *Elevation:* compromised admin account | MFA mandatory, IP allow-list option, session timeout, all actions audited, alerting on bulk reads |
| **APIs** | *Tampering:* IDOR | Ownership checks on every resource fetch; UUIDs are not authorisation |
| | *DoS* | WAF, per-endpoint rate limits, ALB + Fargate autoscaling |
| **AI layer** | Prompt injection, exfiltration | Doc 02 §7 |
| **Third parties** | Vendor compromise or outage | Secrets rotation, least-privilege API keys, timeouts, circuit breakers, graceful degradation |

## 3.4 Document security — precise language

The brief correctly warns against using "end-to-end encryption" loosely. For Vertex:

| Term | Where it applies | What it actually means here |
|---|---|---|
| **TLS 1.2+** | All network traffic | Protects data in transit. Enforced everywhere, including internal service calls |
| **Encryption at rest** | S3 (SSE-KMS), RDS (KMS), EBS, backups, snapshots | Protects against physical/storage-layer compromise. Does **not** protect against an application-layer compromise, because the application can decrypt |
| **Application-level (envelope) encryption** | Bank account numbers, PAN, MFA secrets, government ID numbers | Encrypted by the application with a KMS data key before the database write. A database dump alone is insufficient to read them. This is the meaningful extra layer |
| **Client-side / end-to-end encryption** | **Not used, and not appropriate** | Verification documents exist to be read by an OCR pipeline and a human reviewer. True E2E would make the product impossible. Claiming it would be false |

**Say this exactly this way in any customer-facing security page.** Overclaiming encryption is both a trust risk and, if it reaches marketing copy, a misrepresentation risk.

**S3 document bucket controls:** Block Public Access at the account level · SSE-KMS with a dedicated CMK · bucket policy denying any request without the CMK and any non-TLS request · versioning on · Object Lock (governance) on verification evidence · lifecycle to Glacier after 90 days, expiry per retention policy · access exclusively via presigned URLs from the API after an authorisation check · **every issuance audit-logged** · key structure `verification/{business_id}/{case_id}/{document_id}` (never a guessable path, never a filename containing PII).

## 3.5 Rate limiting

Token bucket in Redis, keyed by user, IP and API key, with burst and sustained limits stated separately.

| Endpoint | Anonymous | Authenticated | Burst | Rationale |
|---|---|---|---|---|
| `POST /auth/register` | 5/hour/IP | — | 2 | Account-farm prevention |
| `POST /auth/login` | 10/hour/IP | — | 5 | Credential stuffing |
| `POST /vertex/query` | **3/day/IP+fingerprint** | 50/day (tier-dependent) | 3 | **The expensive one.** Denial-of-wallet is the real threat |
| `GET /vertex/suggestions` | 60/min | 120/min | 20 | Cheap, cached |
| `GET /providers` | 60/min/IP | 300/min | 30 | — |
| `POST /providers/{id}/contact` | — | 20/day | 5 | Spam protection for providers |
| `POST /business/verification` | — | **3/day/business** | 1 | Each attempt costs real money |
| Document upload | — | 20/day/business | 5 | — |
| `POST /referrals` | — | 10/day | 3 | Fraud |
| Reviews | — | 5/day | 2 | — |

**Burst vs sustained:** burst allows a short spike (a user opening five provider pages quickly) without a 429; sustained enforces the real budget. A single fixed limit either blocks legitimate bursts or permits sustained abuse — you need both.

429 responses always include `Retry-After`. Anonymous Vertex queries return a friendly "sign up to continue" rather than a bare error — that limit is a conversion surface as much as a control.

---

# 4. Payments

**Provider: Razorpay** (rationale and evidence in Doc 00 Correction 1 / ADR-009), used for **two separate money flows that must not share a code path**: Vertex provider subscriptions (§4.1 below) and TGL Membership renewals (§4.1a). They have different entitlement targets (`entitlements` on a `business_id` vs. `tgl_memberships` on a `user_id`), different plan tables (`plans` vs. `membership_plans`, Doc 03 §2.4 / §2.6a), and different webhook handlers, even though both go through the same `PaymentProvider` interface and the same "frontend callback grants nothing, only the verified webhook does" rule.

## 4.1 Vertex provider subscription flow

```
Provider selects plan
  → POST /subscriptions/checkout
      → server creates Razorpay subscription (amount, plan from OUR database, never from the client)
      → returns checkout params
  → Provider completes payment on Razorpay's hosted checkout (card data never touches Vertex)
  → Frontend receives a success callback  ──►  UI shows "confirming…"  [GRANTS NOTHING]
  → Razorpay POSTs webhook  ──►  signature verified  ──►  persisted to webhook_events
      ──►  deduped on provider_event_id  ──►  processed async
          ──►  subscription ACTIVE  ──►  entitlements materialised  ──►  invoice generated
          ──►  business status → ACTIVE  ──►  notification sent
```

**The frontend callback is a UI hint and nothing more.** It updates a spinner. Every state change flows from the verified webhook. This is the single most important rule in the payment design, and it is the one most commonly broken under deadline pressure.

## 4.1a TGL Membership flow (event registration + renewal)

Two entry points into the same `tgl_memberships` table (Doc 03 §2.6a):

```
Path A — Event registration (Phase 1, primary)
  Member selects a TGL event
    → POST /events/{id}/register
        → server creates Razorpay order (event fee, from OUR database)
    → Attendee completes payment on Razorpay's hosted checkout
    → Webhook confirms payment.captured
        → EventRegistrationConfirmed emitted (Doc 03 §5.1)
        → tgl_memberships row created: pathway=EVENT_REGISTRATION,
          status = PENDING until Grand Finale completion;
          then starts_at = completed_at and expires_at = +3 calendar months
        → NetworkingProfile auto-created (Doc 01 §10.1)

Path B — Renewal (recurring, after the complimentary period)
  Member selects a duration (3 / 6 / 12 months, Doc 01 §13.2)
    → POST /memberships/renew
        → server creates Razorpay order (amount from membership_plans, never the client)
    → Member pays on hosted checkout
    → Webhook confirms payment.captured
        → tgl_memberships.current_period_end extended
        → Growth Points redemption applied server-side if requested, capped at 20–30% of the amount (Doc 01 §13.3)
```

**Same non-negotiable rule as §4.1:** the frontend success callback updates a spinner only. Membership status changes exclusively on the verified webhook. This matters more here than on the provider side, because a membership grant is also an *access* grant to a closed community (Networking) — an optimistic grant that later has to be revoked because a payment failed is a much worse experience than a delayed "confirming…" state.

**Event registration is not optional-context for membership — it is the membership pipeline.** Model it as such: `event_registrations.membership_granted_id` is a real foreign key, not a side effect inferred later from a join, so a support agent (or an auditor) can answer "why does this person have a membership" with one row lookup.

## 4.2 Controls

| Control | Implementation |
|---|---|
| Webhook signature | HMAC verified against the endpoint secret from Secrets Manager, constant-time comparison, before any parsing |
| Idempotency | Unique index on `(provider, provider_event_id)`; a replayed webhook is a no-op |
| Out-of-order events | Every subscription state transition checks the event timestamp against the current state; a late `payment.authorized` after `payment.captured` is discarded, not applied |
| Amount integrity | Amount always read from `plans`, never from the request |
| Refunds | Initiated only through the admin UI with a reason; recorded as a `payments` row; entitlements adjusted through the same event path |
| Reconciliation | Nightly job comparing Razorpay settlements against `payments`; discrepancies alert to finance, not to a log file nobody reads |
| PCI scope | Hosted checkout only. Vertex never sees, stores or transmits card data — this keeps you at the lowest SAQ tier. **[VALIDATE the exact SAQ classification with your acquirer]** |
| Dunning | D+1, D+3, D+7 retries with notification; grace to D+7; `EXPIRED` at D+8 |
| Tax | GST computed server-side; customer GSTIN captured for B2B input credit; invoice numbering gapless and immutable **[VALIDATE with a CA]** |
| Provider abstraction | `PaymentProvider` interface; `RazorpayProvider` implemented, `StripeProvider` stubbed for a future international entity |

**Open item (repeat of ADR-009):** the RBI e-mandate additional-factor threshold for recurring card debits must be verified against current circulars before plan prices are set, because a plan priced above the threshold requires customer action on every renewal. **[VALIDATE]**

---

# 5. Compliance and privacy

## 5.1 Applicable regime

**Primary: India's DPDP Act 2023 + DPDP Rules 2025.** (cite index="21-1">The Rules were notified 13 November 2025, starting an 18-month clock ending 13 May 2027 for full substantive compliance; the Data Protection Board of India already exists and functions.</cite> (cite index="19-1">The Consent Manager Framework becomes operational on 13 November 2026.</cite> (cite index="18-1">November 2026 is widely expected to mark the end of the initial soft-enforcement phase, with legacy data management a key focus — businesses expected to ensure personal data collected before the framework is supported by valid notice and consent.</cite>

GDPR/CCPA apply only if Vertex takes EU/California users. Building to DPDP first, with a purpose-scoped consent model, makes a later GDPR overlay largely additive rather than a rebuild.

## 5.2 Implementation

| Requirement | Implementation |
|---|---|
| **Itemised notice** | A standalone privacy notice, separate from the Terms of Service, in plain language, listing each data category and its purpose. Versioned; `notice_version` recorded on every consent row |
| **Granular consent** | One consent record per purpose (`ACCOUNT`, `MARKETING_EMAIL`, `WHATSAPP`, `NETWORKING_VISIBILITY`, `ANALYTICS`). **No pre-ticked boxes, no bundled "I agree"** |
| **Withdrawal** | As easy as granting. A settings page toggle writes a new append-only consent row and takes effect immediately |
| **Data minimisation** | Collect only what a stated purpose requires. Concretely: do not store full PAN when last-4 plus a verification result suffices; do not retain a document once the decision is recorded and the retention period expires |
| **Purpose limitation** | Verification documents are used for verification only — never for marketing, never for model training, never for analytics |
| **Access / export** | `GET /me/export` produces a machine-readable archive of the user's data, delivered via a short-lived presigned link |
| **Correction** | Profile editing plus a support path for verification-derived fields |
| **Deletion** | `DELETE /me` → 30-day soft delete → anonymisation. Financial and verification records are retained under a stated legal basis and the user is told exactly what is retained and why |
| **Breach notification** | Documented incident-response runbook with defined roles and timelines to notify the Data Protection Board and affected individuals. **[Timelines require counsel — do not guess them]** |
| **Consent Manager readiness** | Consent records are already structured to be exportable to, and reconcilable with, a registered Consent Manager ahead of the 13 November 2026 framework date |
| **Processor agreements** | Every vendor touching personal data (KYB, payments, email, SMS, WhatsApp, LLM, analytics) needs a data-processing agreement with security provisions |
| **Cookies** | Essential cookies only by default; analytics cookies behind consent; a preference centre |

**This section is an engineering plan, not legal advice.** The DPDP Rules impose specific obligations whose application to Vertex must be confirmed by qualified Indian counsel (Decision VD-5). Two dates are fixed and should be on the roadmap now: **13 November 2026** and **13 May 2027**.

---

# 6. Observability

## 6.1 The three signals

| Signal | Tool | What is collected |
|---|---|---|
| **Logs** | Structured JSON → CloudWatch Logs | `request_id`, `user_id`, `route`, `status`, `duration_ms`, `error`. **Never** PII, tokens, documents, or full prompts |
| **Metrics** | OpenTelemetry → CloudWatch | RED (rate, errors, duration) per endpoint; USE (utilisation, saturation, errors) per resource; business metrics |
| **Traces** | OpenTelemetry → X-Ray | Full request path: API → intelligence → Bedrock → Postgres → Redis, with the `correlation_id` linking async continuations |

Instrument with the OpenTelemetry SDK from day one. It costs a day and makes changing observability backends a configuration change rather than a re-instrumentation project.

## 6.2 What to watch

| Category | Metrics |
|---|---|
| API | Request rate, error rate (4xx/5xx separately), p50/p95/p99 latency per route |
| Search | Query latency, zero-result rate, candidate counts, fallback-level distribution |
| AI | Time-to-first-token, total latency, tokens in/out, **cost per query**, cache hit rate, model error rate, fallback rate |
| Database | Connections, slow queries, replication lag, deadlocks, index hit ratio, table bloat |
| Cache | Hit rate, evictions, memory, latency |
| Queues | Depth, oldest-message age, **DLQ depth**, processing time |
| Verification | Cases by state, SLA breaches, auto-approval rate, reviewer throughput, **per-check vendor cost** |
| Payments | Success rate, failure reasons, webhook processing lag, reconciliation discrepancies |
| Business | Signups, queries per user, contact rate, provider activations, MRR, churn |

## 6.3 Alerts that page a human

| Alert | Threshold | Why it pages |
|---|---|---|
| API 5xx rate | >2% for 5 min | User-visible outage |
| p95 API latency | >2s for 10 min | Degradation before outage |
| AI fallback level ≥2 | >1% of queries | Core product quality is broken |
| **AI daily spend** | >150% of budget | Denial-of-wallet or a runaway loop |
| DLQ depth | >0 | Data loss in progress |
| Payment webhook lag | >5 min | Customers paid and got nothing |
| DB connections | >80% of max | Imminent outage |
| Verification SLA breach | >10% of queue | Supply onboarding is stalling |
| Reconciliation mismatch | Any | Money is wrong |

Everything else goes to a dashboard. **An alert that does not require immediate human action is not an alert** — it is noise that trains people to ignore the real ones.

---

# 7. CI/CD

## 7.1 Environments

```
local        docker-compose: postgres + redis + localstack; seeded data
development  Auto-deploy from `develop`; shared; synthetic data only
staging      Auto-deploy from `main`; production-shaped; anonymised data; where E2E and load tests run
production   Manual approval; blue/green via ECS; automatic rollback on alarm
```

**No production data in any lower environment, ever.** Anonymise on copy. This is a DPDP requirement and also removes an entire class of accidental-disclosure incident.

## 7.2 Pipeline

```
PR opened
 ├─ lint + typecheck              (fail fast)
 ├─ unit tests + coverage gate
 ├─ dependency audit + license check
 ├─ secret scanning (gitleaks)
 ├─ SAST (CodeQL / Semgrep)
 ├─ IaC scan (tfsec / Checkov)
 ├─ build container + Trivy image scan
 ├─ integration tests (ephemeral Postgres + Redis)
 ├─ AI eval suite  ← blocks merge on regression against the judgement set
 └─ preview environment deployed for review

Merge to main
 ├─ build + push to ECR (immutable tag = git SHA)
 ├─ terraform plan → apply (staging)
 ├─ DB migration (expand phase only — see below)
 ├─ deploy staging → smoke tests → E2E → load test
 └─ manual approval → blue/green production deploy
      └─ canary 10% → health checks → 100% → auto-rollback on alarm
```

**Database migrations use expand/contract**, always: add the new column, deploy code that writes both and reads the new, backfill, deploy code that reads only the new, then drop the old in a later release. Never a destructive migration in the same deploy as the code that depends on it — that combination has no safe rollback.

## 7.3 Secrets

Secrets Manager only. No secrets in code, env files in the repo, CI variables, or container images. Injected into ECS tasks as secret references (never as plaintext env vars in the task definition). Rotated on a schedule for database credentials, and immediately on any suspicion. GitHub Actions authenticates to AWS by **OIDC federation with a scoped role** — no long-lived AWS access keys in CI, ever.

## 7.4 IaC

**Terraform.** Chosen over CDK (which would tie infrastructure to the TypeScript build and to CloudFormation's failure modes) and over Pulumi (smaller ecosystem, smaller hiring pool). Terraform's module registry and provider coverage win on practical grounds.

```
infrastructure/
├── modules/
│   ├── networking/       # VPC, subnets, NAT, endpoints, SGs
│   ├── database/         # RDS, RDS Proxy, parameter groups, backups
│   ├── cache/            # ElastiCache
│   ├── compute/          # ECS cluster, services, task definitions, autoscaling
│   ├── storage/          # S3 buckets, policies, lifecycle, replication
│   ├── messaging/        # SQS, EventBridge, DLQs
│   ├── cdn/              # CloudFront, WAF, ACM
│   ├── observability/    # log groups, alarms, dashboards
│   └── security/         # IAM roles, KMS keys, Secrets Manager
├── environments/
│   ├── dev/ staging/ prod/     # main.tf, variables.tf, terraform.tfvars, backend.tf
└── README.md
```

State in S3 with DynamoDB locking, per-environment. Production changes require a reviewed plan; no `terraform apply` from a laptop.

## 7.5 IAM (least privilege)

| Role | May do | May **not** do |
|---|---|---|
| `vertex-api-task` | RDS via Proxy, Redis, S3 read/write on `verification/*` and `assets/*`, SQS send, Secrets read (its own secrets only), KMS decrypt on named keys, Bedrock invoke | Delete buckets, modify IAM, read other services' secrets |
| `vertex-intelligence-task` (Phase 3) | Bedrock invoke, Redis, **read-only** Postgres on embedding tables | Write product tables, read S3 documents, read payment secrets |
| `vertex-worker-task` | SQS receive/delete, RDS write, S3 read/write, Secrets read | Modify infrastructure |
| `vertex-verification-worker` | S3 read on `verification/*`, KYB vendor secret, RDS write on verification tables | Read payment data, read user PII outside the case |
| `vertex-document-processor` | S3 read/write on `verification/*`, Textract/OCR invoke | Database access of any kind |
| `github-actions-deploy` (OIDC) | ECR push, ECS update-service, Terraform state, limited resource creation | Read production data, read Secrets values, delete RDS |
| `developer` | Read-only production; full dev; break-glass with approval | Write production data directly |
| `analytics` | Read replica, warehouse | Any write; any access to documents or payment identifiers |

**Never** attach `AdministratorAccess` to a workload role. Break-glass admin access is a separate, MFA-gated, time-boxed, alerted role that a human assumes deliberately and that pages the team when assumed.

---

# 8. Failure modes and graceful degradation

| Failure | Impact if unhandled | Degradation |
|---|---|---|
| **LLM provider unavailable** | Core product dead | Fallback ladder (Doc 02 §2.5): secondary model → rules-based extraction → static templates → lexical search. Banner: "Smart search is limited right now." **The product still returns providers** |
| **Search index unavailable** (post-migration) | No results | Fall back to Postgres retrieval; slower, still correct |
| **PostgreSQL primary unavailable** | Total outage | Multi-AZ automatic failover (~60–120s). Reads served from the replica during failover where the code path is read-only. Status page auto-updates |
| **Redis unavailable** | Latency spike, session loss | Cache misses fall through to Postgres. Rate limiting **fails closed** on a conservative in-process limit (never fails open — that invites abuse during an incident). Sessions degrade to token-only validation |
| **Payment provider unavailable** | No new subscriptions | Checkout disabled with a clear message; existing subscriptions unaffected; webhooks queue and replay on recovery. **Never** grant entitlements optimistically |
| **KYB vendor unavailable** | Onboarding stalls | Queue checks with backoff; route new cases to document + manual review; notify providers of a longer SLA rather than failing them |
| **Email provider unavailable** | Missed notifications | Queue with retry; in-app notification always written regardless; critical emails (password reset) fail over to a secondary provider |
| **SMS/WhatsApp unavailable** | OTP failures | Email OTP fallback for login; queue non-critical messages |
| **Maps API unavailable** | No geocoding | Cache previous geocodes; accept the address unverified with a flag; retry asynchronously. Never block registration on a maps outage |
| **SQS unavailable** | Async work stops | Outbox retains events; relay retries; nothing is lost. Synchronous paths unaffected |
| **S3 unavailable** | Uploads fail | Clear error, retry guidance; existing verification unaffected (metadata is in Postgres) |
| **Bedrock quota exhausted** | AI degraded | Circuit breaker → fallback ladder; alert; per-user quotas already limit blast radius |

**Design principle: every external dependency has a timeout, a circuit breaker, and a defined degraded behaviour.** A dependency without a defined failure behaviour is an outage waiting for a vendor's bad day. Test these with fault injection in staging, quarterly — the degradation paths are the least-exercised code in the system and therefore the most likely to be broken when needed.
