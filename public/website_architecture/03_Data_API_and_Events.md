# TGL · Document 03
## Database, API, Events, Real-time, Notifications, Audit, Retention

---

# 1. Database design principles

| Principle | Rule |
|---|---|
| **Identity** | UUID v7 primary keys (`id`) — time-sortable, index-friendly, safe to expose |
| **Timestamps** | Every table: `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL` (trigger-maintained) |
| **Soft delete** | `deleted_at timestamptz NULL` on user-facing entities only. Partial indexes `WHERE deleted_at IS NULL`. **Never** soft-delete audit logs, payments, or verification events |
| **Money** | `numeric(14,2)` + `currency char(3)`. Never floats. Never a bare integer without a documented unit |
| **Enums** | Postgres enums for closed, stable sets (verification status); lookup tables for sets that product will change (categories, plans) |
| **JSONB** | Only where the shape is genuinely open: category-specific provider attributes, raw vendor payloads, event payloads. Everything else gets real columns |
| **Module ownership** | Each NestJS module owns its tables. Cross-module reads go through the owning service, never a foreign repository. Enforced in CI |
| **Constraints** | Every FK declared, `ON DELETE` chosen deliberately (mostly `RESTRICT`), unique constraints on every natural key, `CHECK` constraints on ranges and enums |
| **Multi-tenancy** | Not multi-tenant. A provider organisation is an ordinary entity; `business_id` scoping is enforced in the application layer, with RLS available as defence-in-depth if the model expands |

---

# 2. Core schema

## 2.1 Identity and users

```sql
CREATE TYPE user_role AS ENUM (
  'USER','BUSINESS_OWNER','BUSINESS_ADMIN','BUSINESS_STAFF',
  'VERIFICATION_REVIEWER','MODERATOR','SUPPORT_AGENT','SUPER_ADMIN');

CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  email             CITEXT NOT NULL,
  email_verified_at TIMESTAMPTZ,
  phone             VARCHAR(20),
  phone_verified_at TIMESTAMPTZ,
  password_hash     TEXT,                       -- NULL for OAuth-only accounts
  primary_role      user_role NOT NULL DEFAULT 'USER',
  status            VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','SUSPENDED','DELETED')),
  mfa_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
  mfa_secret_enc    BYTEA,                      -- application-level encrypted
  last_login_at     TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_users_email ON users (email) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_users_phone ON users (phone) WHERE phone IS NOT NULL AND deleted_at IS NULL;

CREATE TABLE user_profiles (
  user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  full_name         VARCHAR(160),
  avatar_url        TEXT,
  business_stage    VARCHAR(20) CHECK (business_stage IN ('IDEA','LAUNCH','EARLY','GROWTH','ESTABLISHED')),
  interested_categories UUID[],
  city              VARCHAR(80),
  location          GEOGRAPHY(POINT,4326),
  preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',
  onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_roles (             -- a user may hold several roles
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  role    user_role NOT NULL,
  scope_business_id UUID,             -- role scoped to one business, where applicable
  granted_by UUID REFERENCES users(id),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role, COALESCE(scope_business_id,'00000000-0000-0000-0000-000000000000'::uuid))
);

CREATE TABLE refresh_tokens (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,           -- store the hash, never the token
  family_id UUID NOT NULL,            -- rotation family, for reuse detection
  device_fingerprint TEXT,
  ip INET,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_user_active ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
```

**Refresh-token families** enable reuse detection: if a token from a family is presented after that family has been rotated, the whole family is revoked and the user is forced to re-authenticate. This is the standard defence against stolen refresh tokens and costs one extra column.

## 2.2 Businesses (providers)

```sql
CREATE TYPE business_status AS ENUM (
  'DRAFT','PENDING_VERIFICATION','NEEDS_INFO','VERIFIED','REJECTED',
  'ACTIVE','PAUSED','SUSPENDED','EXPIRED');

CREATE TABLE businesses (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_user_id     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  legal_name        VARCHAR(255) NOT NULL,
  trade_name        VARCHAR(255),
  slug              VARCHAR(255) NOT NULL,
  entity_type       VARCHAR(40) CHECK (entity_type IN
                      ('SOLE_PROPRIETORSHIP','PARTNERSHIP','LLP','PRIVATE_LIMITED','PUBLIC_LIMITED','OPC','TRUST','OTHER')),
  -- India registry identifiers, all optional: most SMB providers have only some
  gstin             VARCHAR(15),
  cin               VARCHAR(21),
  udyam_number      VARCHAR(25),
  pan_last4         VARCHAR(4),        -- full PAN is application-level encrypted, stored separately
  status            business_status NOT NULL DEFAULT 'DRAFT',
  verification_tier SMALLINT NOT NULL DEFAULT 0 CHECK (verification_tier BETWEEN 0 AND 3),
  verified_at       TIMESTAMPTZ,
  verification_expires_at TIMESTAMPTZ,
  founded_year      SMALLINT,
  employee_band     VARCHAR(20),
  website           TEXT,
  website_verified_at TIMESTAMPTZ,
  risk_score        SMALLINT NOT NULL DEFAULT 0 CHECK (risk_score BETWEEN 0 AND 100),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_businesses_slug  ON businesses(slug) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_businesses_gstin ON businesses(gstin) WHERE gstin IS NOT NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX uq_businesses_cin   ON businesses(cin)   WHERE cin   IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX idx_businesses_status_tier ON businesses(status, verification_tier) WHERE deleted_at IS NULL;

CREATE TABLE business_profiles (
  business_id     UUID PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
  tagline         VARCHAR(200),
  description     TEXT,
  logo_url        TEXT,
  cover_url       TEXT,
  media           JSONB NOT NULL DEFAULT '[]',
  price_band      VARCHAR(10) CHECK (price_band IN ('LOW','MID','HIGH','PREMIUM')),
  attributes      JSONB NOT NULL DEFAULT '{}',   -- category-specific: moq_inr, lead_time_days, capacity…
  languages       TEXT[],
  completeness    SMALLINT NOT NULL DEFAULT 0,
  search_text     TEXT,                            -- maintained by trigger
  search_tsv      TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(search_text,''))) STORED,
  embedding       VECTOR(1024),
  embedding_model_version VARCHAR(20),
  embedded_at     TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_bp_tsv ON business_profiles USING GIN (search_tsv);
CREATE INDEX idx_bp_embedding ON business_profiles
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
CREATE INDEX idx_bp_attributes ON business_profiles USING GIN (attributes jsonb_path_ops);

CREATE TABLE categories (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  code          VARCHAR(60) NOT NULL UNIQUE,      -- 'SUPPLY.WHOLESALE.APPAREL'
  parent_id     UUID REFERENCES categories(id),
  path          LTREE NOT NULL,
  level         SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 3),
  name          VARCHAR(120) NOT NULL,
  description   TEXT,
  synonyms      TEXT[] NOT NULL DEFAULT '{}',
  search_aliases TEXT[] NOT NULL DEFAULT '{}',
  typical_stages TEXT[],
  ranking_profile VARCHAR(40) NOT NULL DEFAULT 'default',  -- per-family weight profile
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  superseded_by UUID REFERENCES categories(id),
  display_order SMALLINT NOT NULL DEFAULT 0
);
CREATE INDEX idx_categories_path ON categories USING GIST (path);

CREATE TABLE category_embeddings (
  category_id   UUID REFERENCES categories(id) ON DELETE CASCADE,
  model_version VARCHAR(20) NOT NULL,
  embedding     VECTOR(1024) NOT NULL,
  PRIMARY KEY (category_id, model_version)
);
CREATE INDEX idx_cat_emb ON category_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE business_categories (
  business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
  category_id UUID REFERENCES categories(id) ON DELETE RESTRICT,
  is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (business_id, category_id)
);
CREATE UNIQUE INDEX uq_bc_primary ON business_categories(business_id) WHERE is_primary;

CREATE TABLE business_locations (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  label VARCHAR(80),
  address_line1 TEXT, address_line2 TEXT,
  area VARCHAR(120), city VARCHAR(80) NOT NULL,
  state VARCHAR(80), pincode VARCHAR(10), country CHAR(2) NOT NULL DEFAULT 'IN',
  geo GEOGRAPHY(POINT,4326),
  geocode_confidence NUMERIC(3,2),
  service_radius_km SMALLINT NOT NULL DEFAULT 25,
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  address_verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_bl_geo ON business_locations USING GIST (geo);
CREATE INDEX idx_bl_city ON business_locations(city);

CREATE TABLE provider_services (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  category_id UUID NOT NULL REFERENCES categories(id),
  name VARCHAR(160) NOT NULL,
  description TEXT,
  price_from NUMERIC(14,2), price_to NUMERIC(14,2), currency CHAR(3) DEFAULT 'INR',
  price_unit VARCHAR(30),          -- 'per_month','per_sqft','per_piece','per_project'
  min_order_value NUMERIC(14,2),
  lead_time_days SMALLINT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE provider_metrics (    -- denormalised, recomputed nightly + on event
  business_id UUID PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
  rating_avg NUMERIC(3,2), rating_count INT NOT NULL DEFAULT 0,
  rating_bayesian NUMERIC(3,2),
  response_rate_90d NUMERIC(4,3), median_response_hours NUMERIC(6,2),
  leads_90d INT NOT NULL DEFAULT 0, contacts_90d INT NOT NULL DEFAULT 0,
  conversions_90d INT NOT NULL DEFAULT 0,
  profile_views_90d INT NOT NULL DEFAULT 0,
  disputes_open INT NOT NULL DEFAULT 0,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Why `provider_metrics` is a separate denormalised table:** ranking needs these numbers on every search. Computing `response_rate_90d` from a contacts table at query time would put an aggregate scan in the hot path. Recompute nightly plus event-driven on contact/review, and accept minutes-stale metrics — nobody's ranking is materially wrong because a response rate is four hours old.

## 2.3 Verification

```sql
CREATE TYPE verification_status AS ENUM (
  'DRAFT','SUBMITTED','AUTOMATED_CHECK','DOCUMENT_REVIEW','MANUAL_REVIEW',
  'APPROVED','REJECTED','MORE_INFORMATION_REQUIRED','EXPIRED','SUSPENDED','REVERIFICATION_REQUIRED');

CREATE TABLE verification_cases (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
  target_tier SMALLINT NOT NULL CHECK (target_tier BETWEEN 1 AND 3),
  status verification_status NOT NULL DEFAULT 'DRAFT',
  risk_score SMALLINT CHECK (risk_score BETWEEN 0 AND 100),
  assigned_reviewer_id UUID REFERENCES users(id),
  sla_due_at TIMESTAMPTZ,
  decision VARCHAR(20) CHECK (decision IN ('APPROVED','REJECTED','NEEDS_INFO')),
  decision_reason TEXT,
  decided_by UUID REFERENCES users(id),
  decided_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  attempt_number SMALLINT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_vc_queue ON verification_cases(status, sla_due_at)
  WHERE status IN ('DOCUMENT_REVIEW','MANUAL_REVIEW');

CREATE TABLE verification_documents (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  case_id UUID NOT NULL REFERENCES verification_cases(id) ON DELETE RESTRICT,
  doc_type VARCHAR(50) NOT NULL,     -- GST_CERTIFICATE, INCORPORATION_CERT, UDYAM_CERT,
                                     -- ADDRESS_PROOF, BANK_STATEMENT, ID_PROOF, UTILITY_BILL
  s3_key TEXT NOT NULL,              -- private bucket; never a public URL
  sha256 CHAR(64) NOT NULL,          -- duplicate-document fraud signal
  mime_type VARCHAR(80), size_bytes BIGINT,
  scan_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
    CHECK (scan_status IN ('PENDING','CLEAN','INFECTED','FAILED')),
  ocr_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  extracted JSONB,                   -- {legal_name, gstin, address, confidence:{...}}
  extraction_confidence NUMERIC(3,2),
  uploaded_by UUID NOT NULL REFERENCES users(id),
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  retention_expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_vd_sha ON verification_documents(sha256);   -- same doc across accounts = fraud signal

CREATE TABLE verification_checks (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  case_id UUID NOT NULL REFERENCES verification_cases(id) ON DELETE RESTRICT,
  check_type VARCHAR(50) NOT NULL,   -- GSTIN_LOOKUP, CIN_LOOKUP, UDYAM_LOOKUP, PENNY_DROP,
                                     -- DOMAIN_OWNERSHIP, EMAIL_DOMAIN, PHONE_OTP, ADDRESS_GEOCODE
  provider VARCHAR(50),              -- which KYB vendor answered
  status VARCHAR(20) NOT NULL CHECK (status IN ('PENDING','PASSED','FAILED','ERROR','SKIPPED')),
  result JSONB,                      -- normalised result
  raw_response JSONB,                -- vendor payload, retained for audit + dispute
  confidence NUMERIC(3,2),
  cost_paise INT,                    -- per-check cost, for unit economics
  attempt SMALLINT NOT NULL DEFAULT 1,
  started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE verification_events (   -- append-only, never updated, never deleted
  id BIGSERIAL PRIMARY KEY,
  case_id UUID NOT NULL REFERENCES verification_cases(id),
  from_status verification_status,
  to_status   verification_status NOT NULL,
  actor_type VARCHAR(20) NOT NULL CHECK (actor_type IN ('SYSTEM','REVIEWER','PROVIDER','WEBHOOK')),
  actor_id UUID,
  reason TEXT,
  metadata JSONB,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`verification_checks.cost_paise` looks like a small thing. It is how you find out that KYB is costing more per provider than the provider's first month of subscription — which is a real risk and invisible without this column.

## 2.4 Subscriptions and payments

```sql
CREATE TABLE plans (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  code VARCHAR(40) NOT NULL UNIQUE,          -- BASIC_MONTHLY, PRO_ANNUAL
  name VARCHAR(80) NOT NULL,
  tier VARCHAR(20) NOT NULL CHECK (tier IN ('BASIC','PROFESSIONAL','ENTERPRISE')),
  interval VARCHAR(10) NOT NULL CHECK (interval IN ('MONTH','YEAR')),
  amount NUMERIC(14,2) NOT NULL, currency CHAR(3) NOT NULL DEFAULT 'INR',
  tax_inclusive BOOLEAN NOT NULL DEFAULT FALSE,
  entitlements JSONB NOT NULL,               -- {max_categories:5, max_leads:50, priority:true,…}
  provider_plan_id VARCHAR(80),              -- Razorpay plan id
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
  plan_id UUID NOT NULL REFERENCES plans(id),
  status VARCHAR(24) NOT NULL CHECK (status IN
    ('TRIALING','ACTIVE','PAST_DUE','PAUSED','CANCELLED','EXPIRED')),
  provider VARCHAR(20) NOT NULL DEFAULT 'RAZORPAY',
  provider_subscription_id VARCHAR(80),
  current_period_start TIMESTAMPTZ, current_period_end TIMESTAMPTZ,
  trial_ends_at TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
  cancelled_at TIMESTAMPTZ, cancellation_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_sub_active ON subscriptions(business_id)
  WHERE status IN ('TRIALING','ACTIVE','PAST_DUE');
CREATE UNIQUE INDEX uq_sub_provider ON subscriptions(provider, provider_subscription_id)
  WHERE provider_subscription_id IS NOT NULL;

CREATE TABLE entitlements (          -- materialised from subscription state
  business_id UUID PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
  max_categories SMALLINT NOT NULL DEFAULT 1,
  max_locations SMALLINT NOT NULL DEFAULT 1,
  max_leads_month INT NOT NULL DEFAULT 10,
  leads_used_period INT NOT NULL DEFAULT 0,
  max_media SMALLINT NOT NULL DEFAULT 3,
  team_seats SMALLINT NOT NULL DEFAULT 1,
  priority_placement BOOLEAN NOT NULL DEFAULT FALSE,
  analytics_level VARCHAR(20) NOT NULL DEFAULT 'BASIC',
  source_subscription_id UUID REFERENCES subscriptions(id),
  effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payments (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
  subscription_id UUID REFERENCES subscriptions(id),
  provider VARCHAR(20) NOT NULL DEFAULT 'RAZORPAY',
  provider_payment_id VARCHAR(80) NOT NULL,
  provider_order_id VARCHAR(80),
  amount NUMERIC(14,2) NOT NULL, currency CHAR(3) NOT NULL DEFAULT 'INR',
  tax_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL CHECK (status IN
    ('CREATED','AUTHORIZED','CAPTURED','FAILED','REFUNDED','PARTIALLY_REFUNDED','DISPUTED')),
  method VARCHAR(20),                -- upi, card, netbanking, wallet
  failure_reason TEXT,
  idempotency_key VARCHAR(80),
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_pay_provider ON payments(provider, provider_payment_id);
CREATE UNIQUE INDEX uq_pay_idem ON payments(idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE invoices (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id),
  payment_id UUID REFERENCES payments(id),
  invoice_number VARCHAR(40) NOT NULL UNIQUE,   -- gapless sequence, generated server-side
  subtotal NUMERIC(14,2) NOT NULL,
  tax_amount NUMERIC(14,2) NOT NULL,
  total NUMERIC(14,2) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  customer_gstin VARCHAR(15),                   -- required for B2B input credit
  place_of_supply VARCHAR(2),
  pdf_s3_key TEXT,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE webhook_events (        -- every inbound webhook, before processing
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  provider VARCHAR(20) NOT NULL,
  provider_event_id VARCHAR(120) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  signature_valid BOOLEAN NOT NULL,
  payload JSONB NOT NULL,
  processed_at TIMESTAMPTZ,
  processing_error TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_webhook_dedupe ON webhook_events(provider, provider_event_id);
```

The unique index on `(provider, provider_event_id)` is what makes webhook processing idempotent. Payment providers retry; without this you will double-credit an entitlement, and you will find out from an angry finance conversation.

## 2.5 Search, conversations, reviews

```sql
CREATE TABLE searches (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  session_id UUID,
  project_id UUID,
  raw_query TEXT NOT NULL,
  structured_query JSONB NOT NULL,
  intent VARCHAR(40), intent_confidence NUMERIC(3,2),
  ranking_profile_version VARCHAR(20) NOT NULL,
  pipeline_version VARCHAR(20) NOT NULL,
  result_count INT, latency_ms INT, cost_micro_inr INT,
  fallback_level SMALLINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_searches_user_time ON searches(user_id, created_at DESC);

CREATE TABLE search_results (        -- the impression log; the basis of all ranking evaluation
  search_id UUID NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
  business_id UUID NOT NULL REFERENCES businesses(id),
  position SMALLINT NOT NULL,
  score NUMERIC(6,4) NOT NULL,
  score_components JSONB NOT NULL,   -- every term, for debugging and for later LTR features
  is_promoted BOOLEAN NOT NULL DEFAULT FALSE,
  clicked_at TIMESTAMPTZ, saved_at TIMESTAMPTZ, contacted_at TIMESTAMPTZ,
  PRIMARY KEY (search_id, business_id)
);

CREATE TABLE conversations (         -- Phase 3
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  project_id UUID,
  title VARCHAR(200),
  context JSONB NOT NULL DEFAULT '{}',   -- accumulated structured understanding
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (              -- Phase 3
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role VARCHAR(12) NOT NULL CHECK (role IN ('user','assistant','system')),
  content TEXT NOT NULL,
  search_id UUID REFERENCES searches(id),
  tokens_in INT, tokens_out INT, model VARCHAR(60),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE provider_contacts (     -- the conversion event, and the review gate
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id),
  business_id UUID NOT NULL REFERENCES businesses(id),
  project_id UUID,
  search_id UUID REFERENCES searches(id),
  channel VARCHAR(20) NOT NULL CHECK (channel IN ('REVEAL','ENQUIRY','CALLBACK')),
  message TEXT,
  provider_responded_at TIMESTAMPTZ,
  outcome VARCHAR(20) CHECK (outcome IN ('NO_RESPONSE','RESPONDED','MEETING','CONVERTED','REJECTED')),
  counted_against_quota BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pc_business_time ON provider_contacts(business_id, created_at DESC);

CREATE TABLE reviews (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE RESTRICT,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  contact_id UUID NOT NULL REFERENCES provider_contacts(id),   -- ← the anti-fraud gate
  rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  title VARCHAR(160), body TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'AUTO_SCREEN'
    CHECK (status IN ('AUTO_SCREEN','PUBLISHED','HELD','REJECTED')),
  fraud_score SMALLINT,
  provider_reply TEXT, provider_replied_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_review_once ON reviews(business_id, user_id, contact_id) WHERE deleted_at IS NULL;
```

`reviews.contact_id NOT NULL` is the entire anti-review-fraud architecture expressed as one constraint. You cannot review someone you never contacted through the platform.

## 2.6 Projects, networking, referrals, resources, system

```sql
CREATE TABLE user_projects (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(160) NOT NULL,
  business_idea TEXT,
  stage VARCHAR(20), city VARCHAR(80),
  budget_amount NUMERIC(14,2), budget_currency CHAR(3) DEFAULT 'INR',
  target_launch_date DATE,
  ai_context JSONB NOT NULL DEFAULT '{}',   -- injected into future queries in this project
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE project_requirements (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id UUID NOT NULL REFERENCES user_projects(id) ON DELETE CASCADE,
  category_id UUID REFERENCES categories(id),
  title VARCHAR(160) NOT NULL,
  rationale TEXT,
  priority SMALLINT NOT NULL DEFAULT 2,
  status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN','IN_PROGRESS','DONE','DISMISSED')),
  source VARCHAR(12) NOT NULL DEFAULT 'AI' CHECK (source IN ('AI','USER')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_providers (
  project_id UUID REFERENCES user_projects(id) ON DELETE CASCADE,
  business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
  requirement_id UUID REFERENCES project_requirements(id) ON DELETE SET NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'SAVED'
    CHECK (status IN ('SAVED','SHORTLISTED','CONTACTED','REJECTED','SELECTED')),
  notes TEXT,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, business_id)
);

CREATE TABLE project_tasks (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id UUID NOT NULL REFERENCES user_projects(id) ON DELETE CASCADE,
  requirement_id UUID REFERENCES project_requirements(id) ON DELETE SET NULL,
  title VARCHAR(200) NOT NULL, description TEXT,
  due_date DATE,
  status VARCHAR(16) NOT NULL DEFAULT 'TODO' CHECK (status IN ('TODO','DOING','DONE')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE networking_profiles (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  is_public BOOLEAN NOT NULL DEFAULT FALSE,      -- opt-in, default off
  headline VARCHAR(160), bio TEXT,
  industry_category_ids UUID[],
  stage VARCHAR(20), city VARCHAR(80),
  interests TEXT[],
  open_to_mentoring BOOLEAN NOT NULL DEFAULT FALSE,
  seeking_mentor BOOLEAN NOT NULL DEFAULT FALSE,
  max_active_mentees SMALLINT NOT NULL DEFAULT 3,
  embedding VECTOR(1024),
  last_active_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE connections (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  requester_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  addressee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','ACCEPTED','DECLINED','BLOCKED')),
  note TEXT NOT NULL,                            -- mandatory: blank requests are spam
  responded_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (requester_id <> addressee_id)
);
CREATE UNIQUE INDEX uq_conn_pair ON connections
  (LEAST(requester_id,addressee_id), GREATEST(requester_id,addressee_id));

CREATE TABLE mentorship_matches (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  mentor_id UUID NOT NULL REFERENCES users(id),
  mentee_id UUID NOT NULL REFERENCES users(id),
  match_score NUMERIC(4,3),
  status VARCHAR(16) NOT NULL DEFAULT 'SUGGESTED'
    CHECK (status IN ('SUGGESTED','REQUESTED','ACTIVE','COMPLETED','DECLINED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE referrals (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  referrer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  code VARCHAR(20) NOT NULL UNIQUE,
  referee_user_id UUID REFERENCES users(id),
  referee_business_id UUID REFERENCES businesses(id),
  status VARCHAR(20) NOT NULL DEFAULT 'CREATED' CHECK (status IN
    ('CREATED','CLICKED','SIGNED_UP','QUALIFIED','CONVERTED','REWARD_PENDING','REWARD_PAID','REVERSED','REJECTED')),
  attributed_at TIMESTAMPTZ,
  attribution_expires_at TIMESTAMPTZ,
  fraud_score SMALLINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE referral_events (
  id BIGSERIAL PRIMARY KEY,
  referral_id UUID NOT NULL REFERENCES referrals(id),
  event_type VARCHAR(30) NOT NULL,
  metadata JSONB, ip INET, device_fingerprint TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE referral_rewards (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  referral_id UUID NOT NULL REFERENCES referrals(id),
  reward_type VARCHAR(20) NOT NULL,             -- CREDIT, DISCOUNT, CASH
  amount NUMERIC(14,2) NOT NULL, currency CHAR(3) DEFAULT 'INR',
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','APPROVED','PAID','REVERSED')),
  clawback_until TIMESTAMPTZ NOT NULL,
  approved_by UUID REFERENCES users(id),
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type VARCHAR(50) NOT NULL,
  category VARCHAR(20) NOT NULL CHECK (category IN
    ('TRANSACTIONAL','SECURITY','VERIFICATION','PAYMENT','NETWORKING','REFERRAL','PRODUCT',
     'MEMBERSHIP','EVENTS','AWARDS')),
  title VARCHAR(200) NOT NULL, body TEXT,
  action_url TEXT, metadata JSONB,
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_notif_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL;

CREATE TABLE notification_preferences (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category VARCHAR(20) NOT NULL,
  email BOOLEAN NOT NULL DEFAULT TRUE,
  sms BOOLEAN NOT NULL DEFAULT FALSE,
  whatsapp BOOLEAN NOT NULL DEFAULT FALSE,
  push BOOLEAN NOT NULL DEFAULT TRUE,
  in_app BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (user_id, category)
);

CREATE TABLE outbox (
  id BIGSERIAL PRIMARY KEY,
  aggregate_type VARCHAR(50) NOT NULL,
  aggregate_id UUID NOT NULL,
  event_type VARCHAR(60) NOT NULL,
  payload JSONB NOT NULL,
  dispatched_at TIMESTAMPTZ,
  attempts SMALLINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_outbox_pending ON outbox(created_at) WHERE dispatched_at IS NULL;

CREATE TABLE audit_logs (            -- append-only; never updated, never deleted
  id BIGSERIAL PRIMARY KEY,
  actor_user_id UUID, actor_type VARCHAR(20) NOT NULL,
  actor_ip INET, actor_user_agent TEXT,
  action VARCHAR(80) NOT NULL,
  resource_type VARCHAR(50) NOT NULL, resource_id UUID,
  before JSONB, after JSONB,
  reason TEXT, request_id UUID,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id, occurred_at DESC);
CREATE INDEX idx_audit_actor ON audit_logs(actor_user_id, occurred_at DESC);

CREATE TABLE consents (              -- DPDP: purpose-scoped, versioned, withdrawable
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose VARCHAR(60) NOT NULL,      -- ACCOUNT, MARKETING_EMAIL, WHATSAPP, NETWORKING_VISIBILITY, ANALYTICS
  granted BOOLEAN NOT NULL,
  notice_version VARCHAR(20) NOT NULL,
  source VARCHAR(30) NOT NULL,       -- SIGNUP, SETTINGS, CONSENT_MANAGER
  ip INET,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_consents_user_purpose ON consents(user_id, purpose, occurred_at DESC);
```

`consents` is append-only too. DPDP requires you to prove what a person consented to and when; an updatable row cannot prove that.

## 2.6a TGL-specific: membership, Trust Score, Growth Points, business referrals, chapters, events, awards

This section covers what is specific to the **Networking** product (Doc 01 §10, §13, §14) and has no equivalent in a generic marketplace schema. The pre-existing `networking_profiles`, `connections` and `mentorship_matches` tables above (§2.6) remain the directory/matching layer; everything here builds on top of them. `referrals` / `referral_events` / `referral_rewards` above are the **growth/acquisition** referral program (Doc 01 §9) — do not extend that table for business referrals; use `business_referrals` below instead (Doc 01 §3.1 callout on why these are two different features).

```sql
CREATE TABLE city_chapters (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  name VARCHAR(80) NOT NULL,             -- 'Bangalore'
  city VARCHAR(80) NOT NULL,
  state VARCHAR(80), country CHAR(2) NOT NULL DEFAULT 'IN',
  status VARCHAR(20) NOT NULL DEFAULT 'PRE_LAUNCH'
    CHECK (status IN ('PRE_LAUNCH','ACTIVE','DORMANT')),   -- activates at the member-count threshold, Doc 00 VD-9
  activated_at TIMESTAMPTZ,
  member_count INT NOT NULL DEFAULT 0,    -- denormalised, recomputed on membership change
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Extends networking_profiles (§2.6) rather than duplicating it
ALTER TABLE networking_profiles
  ADD COLUMN chapter_id UUID REFERENCES city_chapters(id),
  ADD COLUMN trust_score NUMERIC(6,2) NOT NULL DEFAULT 0,
  ADD COLUMN growth_points_balance INT NOT NULL DEFAULT 0,
  ADD COLUMN membership_level VARCHAR(20) NOT NULL DEFAULT 'MEMBER',
  ADD COLUMN tgl_verified BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN tgl_verified_at TIMESTAMPTZ;

CREATE TABLE tgl_memberships (          -- who is a TGL Member, and why (Doc 01 §13)
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  pathway VARCHAR(30) NOT NULL DEFAULT 'EVENT_REGISTRATION'
    CHECK (pathway IN ('EVENT_REGISTRATION','APPLICATION','CORPORATE','MENTOR','INVESTOR')),  -- Phase 2 pathways, disabled by config until opened
  source_event_registration_id UUID,     -- REFERENCES event_registrations(id), nullable for non-event pathways
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE','GRACE_PERIOD','EXPIRED','REVOKED')),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  complimentary_until TIMESTAMPTZ,        -- Season 1 P0: 3 calendar months after Grand Finale completion
  current_period_end TIMESTAMPTZ,
  approved_by UUID REFERENCES users(id),  -- required for APPLICATION/CORPORATE pathways; null for EVENT_REGISTRATION
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_membership_active ON tgl_memberships(user_id)
  WHERE status IN ('ACTIVE','GRACE_PERIOD');

CREATE TABLE membership_plans (          -- 3/6/12-month renewal tiers, Doc 01 §13.2 — distinct from Vertex `plans` (§2.4)
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  code VARCHAR(40) NOT NULL UNIQUE,      -- MEMBERSHIP_3M, MEMBERSHIP_6M, MEMBERSHIP_12M
  duration_months SMALLINT NOT NULL,
  amount NUMERIC(14,2) NOT NULL, currency CHAR(3) NOT NULL DEFAULT 'INR',
  tax_inclusive BOOLEAN NOT NULL DEFAULT TRUE,
  provider_plan_id VARCHAR(80),          -- Razorpay plan id
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE growth_points_ledger (      -- append-only; growth_points_balance above is the running total
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  points INT NOT NULL,                   -- signed: positive award, negative redemption
  reason VARCHAR(40) NOT NULL,           -- REFERRAL_SUCCESS, AWARD_WON, REVIEW_RECEIVED, WEEKLY_UPDATE, MEMBER_HELPED, RENEWAL_REDEMPTION
  reference_type VARCHAR(30), reference_id UUID,   -- polymorphic pointer to the earning/spending event
  awarded_by VARCHAR(20) NOT NULL DEFAULT 'SYSTEM' CHECK (awarded_by IN ('SYSTEM','ADMIN')),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_gpl_user ON growth_points_ledger(user_id, occurred_at DESC);

CREATE TABLE trust_score_events (        -- append-only; networking_profiles.trust_score is the running total
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  delta NUMERIC(6,2) NOT NULL,
  reason VARCHAR(40) NOT NULL,
  is_negative BOOLEAN NOT NULL DEFAULT FALSE,
  requires_review BOOLEAN NOT NULL DEFAULT FALSE,   -- TRUE for any negative signal — §0 product rule: no unreviewed penalty
  reviewed_by UUID REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  reference_type VARCHAR(30), reference_id UUID,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tse_pending_review ON trust_score_events(user_id)
  WHERE is_negative AND reviewed_at IS NULL;

CREATE TABLE business_referrals (        -- member-to-member business introductions, Doc 01 §10.3 — NOT the growth-referral table
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  referrer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  referred_to_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  category_id UUID REFERENCES categories(id),        -- reuses the Vertex taxonomy (§2.2) for category-targeted requests
  description TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'GIVEN'
    CHECK (status IN ('GIVEN','ACCEPTED','MEETING_DONE','BUSINESS_CLOSED','REVENUE_GENERATED','DECLINED','EXPIRED')),
  estimated_value NUMERIC(14,2), realized_value NUMERIC(14,2), currency CHAR(3) DEFAULT 'INR',
  chapter_id UUID REFERENCES city_chapters(id),       -- default routing scope; cross-chapter requests explicitly allowed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_br_referrer ON business_referrals(referrer_id, created_at DESC);
CREATE INDEX idx_br_referred_to ON business_referrals(referred_to_id, status);

CREATE TABLE business_need_posts (       -- the "Business Need Board", Doc 01 §10.3
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  posted_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(200) NOT NULL, description TEXT,
  category_id UUID REFERENCES categories(id),
  chapter_id UUID REFERENCES city_chapters(id),       -- NULL = national visibility
  status VARCHAR(16) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','FULFILLED','CLOSED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  name VARCHAR(200) NOT NULL, slug VARCHAR(200) NOT NULL UNIQUE,
  chapter_id UUID REFERENCES city_chapters(id),
  season VARCHAR(20),                    -- 'Season 1', groups multi-city events in one annual cycle
  starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ,
  venue TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'UPCOMING' CHECK (status IN ('UPCOMING','LIVE','PAST','CANCELLED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE event_registrations (       -- the pipeline that grants tgl_memberships.pathway = EVENT_REGISTRATION
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE RESTRICT,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  status VARCHAR(20) NOT NULL DEFAULT 'REGISTERED'
    CHECK (status IN ('REGISTERED','ATTENDED','NO_SHOW','CANCELLED')),
  payment_id UUID REFERENCES payments(id),
  membership_granted_id UUID REFERENCES tgl_memberships(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_evreg_event ON event_registrations(event_id);

CREATE TABLE awards (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  event_id UUID REFERENCES events(id),               -- NULL for annual/national awards not tied to one city event
  scope VARCHAR(10) NOT NULL DEFAULT 'CITY' CHECK (scope IN ('CITY','NATIONAL')),
  category VARCHAR(60) NOT NULL,         -- 'COMMUNITY_CHAMPION','REFERRAL_CHAMPION','MOST_TRUSTED_BUSINESS', …
  recipient_user_id UUID REFERENCES users(id),
  recipient_business_id UUID REFERENCES businesses(id),
  period VARCHAR(20),                    -- 'WEEKLY-2026-W37','MONTHLY-2026-08','YEARLY-2026'
  algorithmic_score NUMERIC(8,2),        -- the ~70% measurable component, Doc 01 §10.7
  committee_reviewed BOOLEAN NOT NULL DEFAULT FALSE,  -- the ~30% human check
  awarded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE leaderboard_snapshots (     -- materialised, recomputed on a schedule — never a live aggregate query
  id BIGSERIAL PRIMARY KEY,
  window VARCHAR(10) NOT NULL CHECK (window IN ('WEEKLY','MONTHLY','YEARLY')),
  scope VARCHAR(10) NOT NULL CHECK (scope IN ('CHAPTER','NATIONAL')),
  chapter_id UUID REFERENCES city_chapters(id),       -- NULL when scope = NATIONAL
  period VARCHAR(20) NOT NULL,
  metric VARCHAR(30) NOT NULL,           -- GROWTH_POINTS, REFERRALS_GIVEN, TRUST_SCORE, …
  rankings JSONB NOT NULL,               -- [{user_id, rank, value}, …] — small enough to snapshot whole
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_leaderboard_lookup ON leaderboard_snapshots(window, scope, chapter_id, metric, period);

CREATE TABLE podcasts (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  title VARCHAR(200) NOT NULL, slug VARCHAR(200) NOT NULL UNIQUE,
  description TEXT, media_url TEXT, thumbnail_url TEXT,
  related_business_id UUID REFERENCES businesses(id),
  related_user_id UUID REFERENCES users(id),
  related_event_id UUID REFERENCES events(id),
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Why Trust Score and Growth Points are each an append-only ledger plus a denormalised running total, not just a mutable counter:** the product rule in Doc 01 §0/§10.2 — no automatic, unreviewed penalty — is only enforceable if every change is individually attributable, reviewable and (for negative deltas) blockable pending human review. A single mutable `trust_score` column cannot answer "why did this member's score drop on 3 September," and that question will be asked, by the member, in a support ticket.

## 2.7 Index strategy summary

| Access pattern | Index |
|---|---|
| Provider lexical search | GIN on `search_tsv` |
| Provider semantic search | HNSW on `embedding` |
| Provider geo search | GIST on `business_locations.geo` |
| Category-filtered search | B-tree on `business_categories(category_id, business_id)` |
| Attribute filters (MOQ etc.) | GIN `jsonb_path_ops` on `attributes` |
| Verification queue | Partial B-tree on `(status, sla_due_at)` where in review |
| Active subscription lookup | Partial unique on `business_id` where status active |
| Unread notifications | Partial on `(user_id, created_at DESC)` where unread |
| Outbox relay | Partial on `created_at` where `dispatched_at IS NULL` |
| Audit lookups | Composite on resource and on actor |

**Rule:** every index must be justified by a named query. Unused indexes are a write tax. Review `pg_stat_user_indexes` quarterly and drop the ones with zero scans.

---

# 3. What lives where (Postgres vs search vs Redis)

| Data | Postgres | Search index (later) | Redis |
|---|---|---|---|
| Provider canonical record | **Source of truth** | Denormalised copy | Hot profile cache (5 min) |
| Categories | **Source of truth** | Copied for facets | Full tree cached (1 h) |
| Reviews | **Source of truth** | Aggregates only | — |
| Sessions | Refresh tokens only | — | **Active session data** |
| Rate-limit counters | — | — | **Only here** (ephemeral by nature) |
| Search results | Impression log (`search_results`) | — | Hot query results (1 h) |
| Embeddings | **pgvector, source of truth** | Copied at scale | Text→embedding cache (30 d) |
| Verification documents | Metadata only | Never | Never |
| Payments / invoices | **Source of truth** | Never | Never |
| Suggestion tries | Rebuilt from logs | — | **Serving copy** |

**Never only in Redis:** anything you cannot rebuild. Redis is a cache and a coordination primitive, not a database. The one grey area is rate-limit counters, which are legitimately Redis-only because losing them fails open for a few seconds, which is acceptable.

## 3.1 Postgres → search index synchronisation (for the OpenSearch phase)

```
Write to Postgres  ─┐
                    ├── same transaction ──► outbox row (ProviderProfileUpdated)
                    ┘
Outbox relay ──► SQS ──► Search Indexer ──► OpenSearch bulk upsert
```

Eventual consistency is explicit and bounded: target index lag <5s p95, alarm at >30s. The provider dashboard reads from Postgres (so a provider always sees their own edit immediately), while public search reads from the index. That split is what makes "I updated my profile but it's not showing" a non-issue for the person most likely to complain about it.

Nightly reconciliation job compares row counts and `updated_at` watermarks and re-indexes drift. Full reindex is a documented, rehearsed runbook — build it before you need it.

---

# 4. API design

## 4.1 Conventions

Base `/api/v1`. JSON only. `snake_case` fields. Cursor pagination (`?cursor=&limit=`), never offset for large sets. Bearer access token (15 min) + rotating refresh token in an httpOnly, Secure, SameSite=Lax cookie. `Idempotency-Key` header required on all POSTs that create money, contacts or verifications. `X-Request-Id` propagated end-to-end and returned on every response and every error.

Errors are a single shape:
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Human readable",
             "details": [{"field":"email","issue":"invalid_format"}],
             "request_id": "req_01J8..." } }
```

## 4.2 Endpoint catalogue

**Auth**

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — | 5/hour/IP. Email verification required before write access |
| POST | `/auth/login` | — | 10/hour/IP; account lockout after 5 fails with exponential backoff |
| POST | `/auth/refresh` | Refresh cookie | Rotation + family reuse detection |
| POST | `/auth/logout` | Bearer | Revokes the token family |
| POST | `/auth/mfa/enable` `/auth/mfa/verify` | Bearer | TOTP; **mandatory** for all admin roles |
| POST | `/auth/password/forgot` `/reset` | — | Single-use, 30-min token; no user enumeration in responses |
| GET | `/auth/oauth/google` + callback | — | State + PKCE |

**Vertex AI (Phase 3)**

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/vertex/query` | Optional | **SSE stream.** Quota-checked. The core endpoint |
| POST | `/vertex/refine` | Optional | Applies a delta to a stored structured query |
| GET | `/vertex/suggestions` | Optional | `?q=&context=` — typeahead, cached, no LLM |
| GET | `/vertex/conversations` · `/conversations/{id}` | Bearer | History |

```jsonc
// POST /api/v1/vertex/query
// Request
{ "query": "I want to start a clothing business in Bangalore with 10 lakh budget",
  "conversation_id": null, "project_id": null,
  "context": { "city": "Bengaluru", "stage": "IDEA" } }

// SSE event stream
event: stage      data: {"stage":"understanding"}
event: intent     data: {"intent":"BUSINESS_LAUNCH","confidence":0.94,
                         "entities":{"business_type":"clothing_retail","location":"Bengaluru","budget":1000000}}
event: stage      data: {"stage":"generating_requirements"}
event: requirements data: {"requirements":[{"category_path":"INFRA.RENTAL.RETAIL","priority":1,"rationale":"..."}]}
event: stage      data: {"stage":"searching"}
event: results    data: {"requirement":"INFRA.RENTAL.RETAIL","providers":[{...}],"total":42}
event: token      data: {"text":"Based on a ₹10 lakh budget, "}
event: done       data: {"search_id":"srch_...","conversation_id":"conv_...","latency_ms":3120}
```

Errors mid-stream are sent as `event: error` with a `fallback_level`, so the client can degrade the UI rather than showing a blank screen.

**Providers**

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/providers` | Optional | Filters: `category`, `city`, `lat/lng/radius`, `verification_tier`, `price_band`, `min_rating`, `q`. Cursor paginated |
| GET | `/providers/{id}` | Optional | Public profile; cached at the edge for 60s |
| POST | `/providers/{id}/save` | Bearer | Idempotent |
| POST | `/providers/{id}/contact` | Bearer | **Idempotency-Key required.** Checks provider lead quota, records `provider_contacts`, emits `LeadCreated`, notifies provider. 429 if the user exceeds the daily contact limit |
| GET | `/providers/{id}/reviews` | Optional | Published only |
| POST | `/providers/{id}/reviews` | Bearer | Requires a `contact_id` owned by the caller |

**Business / verification**

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/business/register` | Bearer | Creates business in `DRAFT`, grants `BUSINESS_OWNER` scoped to it |
| PATCH | `/business/{id}` | Bearer + owner | Partial update; triggers re-embedding via outbox |
| POST | `/business/{id}/categories` `/locations` `/services` | Bearer + owner + entitlement | Entitlement-checked server-side |
| POST | `/business/{id}/verification` | Bearer + owner | Opens a case; rate-limited per business |
| POST | `/business/{id}/verification/documents/presign` | Bearer + owner | Returns a short-lived S3 PUT URL, content-type and size constrained |
| GET | `/business/{id}/verification/status` | Bearer + owner | Status, missing items, SLA estimate |
| GET | `/business/{id}/dashboard` | Bearer + member | Leads, views, metrics |

**Subscriptions and payments**

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/plans` | — | Public |
| POST | `/subscriptions/checkout` | Bearer + owner | Creates a provider-side subscription, returns checkout parameters. **Grants nothing** |
| POST | `/subscriptions/{id}/cancel` | Bearer + owner | Sets `cancel_at_period_end` |
| GET | `/subscriptions/current` | Bearer + member | Includes entitlements and usage |
| GET | `/invoices` · `/invoices/{id}/pdf` | Bearer + owner | PDF via short-lived presigned URL |
| POST | `/webhooks/razorpay` | **Signature** | Signature verified, persisted to `webhook_events`, deduped, processed async. **The only path that grants entitlements** |

**Networking, membership, events, awards, podcasts**

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/networking/directory` | Bearer + active membership | Filters: chapter, category, stage; the match-score composite (Doc 01 §10.5) as a `?sort=match` option |
| POST | `/networking/business-referrals` | Bearer + active membership | Creates a `GIVEN` referral; **Idempotency-Key required** |
| PATCH | `/networking/business-referrals/{id}` | Bearer + participant (referrer or referred_to) | Advances status (`ACCEPTED`→`MEETING_DONE`→`BUSINESS_CLOSED`→`REVENUE_GENERATED`); triggers Growth Points award on `BUSINESS_CLOSED`+ (event-driven, §5.1) |
| GET/POST | `/networking/need-board` | Bearer + active membership | The Business Need Board (Doc 01 §10.3) |
| GET | `/networking/leaderboards` | Bearer + active membership | `?window=&scope=&chapter_id=&metric=` — reads `leaderboard_snapshots`, never a live aggregate |
| GET | `/memberships/me` | Bearer | Status, pathway, complimentary/renewal dates, Growth Points redemption available |
| POST | `/memberships/renew` | Bearer + owner | Creates a Razorpay checkout against `membership_plans`; **grants nothing** until the webhook lands (same rule as Doc 04 §4.1) |
| GET | `/events` · `/events/{slug}` | Optional | Public |
| POST | `/events/{id}/register` | Bearer | On payment confirmation, emits `EventRegistrationConfirmed` → membership grant pipeline (§5.1) |
| GET | `/awards` | Optional | Filterable by scope/period/category |
| GET | `/podcasts` · `/podcasts/{slug}` | Optional | Public, ISR-cached like Resources |

**Projects, resources, admin** follow the same conventions; full list in the OpenAPI spec (`packages/contracts/openapi.yaml`), generated from Zod schemas so the contract cannot drift from the implementation.

## 4.3 REST vs GraphQL vs realtime

| Need | Choice | Why |
|---|---|---|
| Product APIs | **REST** | Simple, cacheable, easy to secure, easy to rate-limit per endpoint. GraphQL's benefit (client-shaped queries) does not outweigh its costs here — query-depth attacks, N+1 amplification, harder per-field authorisation, harder caching |
| AI streaming | **SSE** | Unidirectional server→client, works over plain HTTP, auto-reconnects, no extra infrastructure. WebSockets are overkill for a one-way token stream |
| Verification status, notifications | **SSE** on a single `/events` stream, plus polling fallback | Low frequency; a persistent bidirectional socket is not justified |
| Networking chat (future) | **WebSockets** | Genuinely bidirectional; revisit only when that feature is built |
| Everything else | **Polling** | 30s poll for a dashboard counter is fine and costs nothing to operate |

Explicit recommendation: **no WebSockets at MVP.** SSE covers every current real-time need at a fraction of the operational cost.

---

# 5. Event-driven architecture

## 5.1 Event catalogue

| Event | Emitted by | Consumers |
|---|---|---|
| `UserRegistered` | Auth | Welcome email, analytics, referral attribution |
| `BusinessRegistered` | Business | Onboarding sequence, admin queue, analytics |
| `ProviderProfileUpdated` | Business | Re-embedding worker, search indexer, cache invalidation |
| `VerificationStarted` | Verification | KYB check workers, provider notification |
| `VerificationCheckCompleted` | Check worker | Verification state machine |
| `VerificationCompleted` | Verification | Tier update, notification, search reindex, analytics |
| `VerificationFailed` | Verification | Notification with reason, review queue |
| `SubscriptionCreated` | Payments | Entitlement materialisation, welcome, analytics |
| `PaymentSucceeded` | Webhook processor | Subscription activation, invoice generation, referral conversion |
| `PaymentFailed` | Webhook processor | Dunning sequence, notification |
| `LeadCreated` | Contacts | Provider notification, quota decrement, analytics |
| `ReviewSubmitted` | Reviews | Fraud screening, metrics recompute, provider notification |
| `ReferralCreated` / `ReferralConverted` | Referrals (growth/acquisition, Doc 01 §9) | Attribution, reward pipeline, fraud check |
| `SearchExecuted` | Search | Analytics, eval-set candidate sampling |
| `BusinessReferralStatusChanged` | Networking | Growth Points award on `BUSINESS_CLOSED`+ (Doc 01 §10.4), notification to both parties, Trust Score input |
| `EventRegistrationConfirmed` | Events | **Membership grant pipeline** — creates/extends `tgl_memberships`, sets `complimentary_until`, notification |
| `MembershipRenewed` / `MembershipExpired` | Membership webhook processor | Entitlement update, renewal-rate analytics (Doc 06 §6.3), grace-period notification sequence |
| `TrustScoreAdjusted` | Trust Score service | If `is_negative`, routes to the admin review queue rather than applying immediately (Doc 01 §0 rule) |
| `AwardGranted` | Awards / admin | Profile update, notification, feeds `leaderboard_snapshots` recompute |
| `ChapterActivated` | Scheduled job | Fires when a city crosses the member-count threshold (Doc 00 VD-9); notification to that chapter's members |

## 5.2 Envelope

```jsonc
{
  "event_id": "uuid-v7",              // idempotency key for every consumer
  "event_type": "VerificationCompleted",
  "event_version": 1,                  // schema version — never breaking-change in place
  "aggregate_type": "verification_case",
  "aggregate_id": "uuid",
  "occurred_at": "2026-08-31T10:00:00Z",
  "actor": { "type": "SYSTEM", "id": null },
  "correlation_id": "req_...",         // ties the whole causal chain together in traces
  "payload": { "business_id": "...", "tier": 2, "decision": "APPROVED" }
}
```

## 5.3 Delivery guarantees

| Concern | Approach |
|---|---|
| **Loss** | Transactional outbox — event committed with the state change |
| **Duplicates** | At-least-once delivery; consumers dedupe on `event_id` in a `processed_events` table with a TTL |
| **Ordering** | Standard SQS for most events (order does not matter). **FIFO with `MessageGroupId = aggregate_id`** for verification and subscription state transitions, where order does matter |
| **Retries** | Exponential backoff, max 5 attempts, then DLQ |
| **DLQ** | Alarmed at depth > 0. A documented replay runbook, tested quarterly. An unmonitored DLQ is a silent data-loss channel |
| **Poison messages** | Attempt count on the message; a consumer that fails on schema errors sends straight to DLQ rather than retrying 5 times |
| **Observability** | `correlation_id` propagated into traces so an event chain is one trace, not five disconnected ones |
| **Schema evolution** | Additive changes only within a version. Breaking changes get `event_version: 2` and consumers handle both until the old one is drained |

---

# 6. Notifications

| Channel | Provider | Used for | Notes |
|---|---|---|---|
| **Email** | Amazon SES | All transactional, security, verification, payment | Same region; DKIM/SPF/DMARC configured before first send or you land in spam |
| **SMS** | India DLT-registered provider | OTP, critical alerts only | **India requires DLT template registration** for transactional SMS. Templates must be pre-registered, which means SMS copy changes have lead time. Plan for it |
| **WhatsApp** | WhatsApp Business API (via a BSP) | Provider lead alerts, verification updates | This is where Indian SMB owners actually read messages. Template pre-approval required; opt-in mandatory and consent-logged |
| **Push** | Web Push | Optional, browser only | Low priority |
| **In-app** | `notifications` table + SSE | Everything | Always written, regardless of other channels |

**Category × channel preference matrix** is user-controlled, with one exception: `SECURITY` notifications cannot be disabled. A user must not be able to switch off "your password was changed".

Template management: versioned templates in the repo (not in a vendor console), rendered server-side, with a locale key. Every send is recorded with `template_id` and `template_version` so you can answer "what exactly did we send this person".

---

# 7. Audit logging

Every one of these writes an `audit_logs` row: login success/failure, MFA changes, role grants and revocations, verification decisions, **document access (who viewed which document and why)**, provider profile changes, subscription and entitlement changes, payment and refund actions, every admin action, fraud decisions, data export and deletion requests, consent changes.

```jsonc
{
  "actor": { "user_id": "...", "type": "REVIEWER", "ip": "203.0.113.5", "user_agent": "..." },
  "action": "verification.document.viewed",
  "resource": { "type": "verification_document", "id": "..." },
  "before": null,
  "after": null,
  "reason": "Manual review of case VC-1042",
  "request_id": "req_...",
  "occurred_at": "2026-08-31T10:00:00Z"
}
```

Audit logs are **append-only**: no UPDATE, no DELETE, enforced by database grants (the application role has INSERT and SELECT only). Retained 7 years for financial and verification actions. Exported to S3 with Object Lock for tamper evidence on the highest-sensitivity actions.

**Document-access logging is the one people skip and regret.** If a reviewer's account is ever compromised, the only question that matters is which documents were viewed, and only this log can answer it.

---

# 8. Data retention

| Data | Retention | Basis | Notes |
|---|---|---|---|
| Active user account | Life of account | Contract | — |
| Deleted user account | 30-day soft delete → anonymise | User right | Anonymise rather than hard-delete where rows are referenced by financial records |
| Business account | Life + 8 years after closure | Financial records | Tax and audit |
| **Verification documents** | **Shortest defensible period** — recommend 3 years post-decision, then delete; keep the *decision*, not the *document* | Compliance vs. minimisation | **[VALIDATE with counsel]** The riskiest data you hold; the decision record has almost all the value at a fraction of the risk |
| Verification decisions/events | 8 years | Audit | Never deleted |
| Payments, invoices | 8 years | Indian tax record-keeping **[VALIDATE with a CA]** | Never deleted |
| Audit logs | 7 years | Security | Append-only |
| Search history | 24 months, then aggregate | Product improvement | User-deletable |
| AI conversations | 12 months | Product improvement | User-deletable; PII redacted at write |
| Notifications | 12 months | — | — |
| Inactive projects | Retained while account active | User content | — |
| Session/refresh tokens | Expiry + 30 days | Security | — |
| Marketing consents | Life of account + 3 years | Proof of consent | Append-only |

**DPDP alignment:** purpose-scoped consent captured at collection, itemised notice separate from the terms of service, deletion and export endpoints implemented from day one (not retrofitted), retention enforced by an automated job rather than by policy documents, and a `consents` table that can prove what was agreed and when.

**Every date and duration in this table is a legal determination that requires Indian counsel. They are engineering defaults chosen to be defensible, not legal advice.**
