# Phase A: recording connections, business needs and help offers (facts only)

Status: implemented locally, **not deployed anywhere**. It awards no Growth Points, creates no ledger event, adds no rule version and changes no financial behaviour. `docs/GROWTH_POINTS_BUSINESS_POLICY_PROPOSAL.md` is still a draft and nothing here approves any value in it. `GROWTH_POINTS_FINAL_SPEC.md` is unchanged.

**An observation period has not started.** It starts only when this release runs in an authorised environment that receives real member activity, and the admin report says so itself.

## 1. What was built

| Area | Before | Now |
|---|---|---|
| Connections | Request, accept, decline; removal and withdrawal **hard-deleted** the rows, so history was lost | The current-state table works exactly as before, and every change also writes an **append-only history event** in the same transaction. A removed pair is remembered, so a later request is recognised as a **reconnection** |
| Needs | `POST` created an always-`OPEN` row (no limits, no moderation, no states) | A real lifecycle (`OPEN`, `RESOLVED`, `CANCELLED`, `REMOVED`), 80-character minimum description, duplicate detection, a tracked monthly-quality field, moderation by an identified admin, per-hour and per-day safety limits |
| "I can help" | A notification only; repeatable; nothing stored | A durable **offer** (`need_help_offers`) with a status machine, one offer per helper per need, the poster's accept / decline / helpful / not helpful, withdrawal, and resolution with an optional credited helper |
| Observation | None | Admin **Community activity** tab and `GET /api/admin/community/report`: aggregate, anonymous, genuine members only |

## 2. Lifecycles

**Connections** (state in `connections`, history in `community_events`)

| Action | Who | State change | Event |
|---|---|---|---|
| Request | any active member | new `PENDING` row | `REQUESTED` (`reconnection` if the pair was ever connected) |
| Request back at someone who asked you | the other member | their row becomes `ACCEPTED` | `REQUESTED` (crossing) + `ACCEPTED` |
| Accept | the target only | `PENDING` or `DECLINED` → `ACCEPTED` | `ACCEPTED` |
| Decline | the target only | `PENDING` → `DECLINED` (silent, as before) | `DECLINED` |
| Withdraw | the sender only | row deleted | `WITHDRAWN` (with the status it had) |
| Remove | either member | both rows deleted | `REMOVED` (who removed it) |

Safety: both members are row-locked in a fixed order, every status change is a compare-and-set, and a partial unique index on the hashed pair stops two live rows for one pair on any database. A request that loses a race re-reads once and accepts or reports a duplicate.

**Needs** (`business_needs.status`)

| From | Action | Who | To | Event |
|---|---|---|---|---|
| (new) | publish | member (validated) | `OPEN` | `PUBLISHED` (or `REJECTED` with a reason) |
| `OPEN` | resolve (optionally credit one **confirmed-helpful** offer) | the poster only | `RESOLVED` | `RESOLVED` |
| `OPEN` | cancel | the poster only | `CANCELLED` | `CANCELLED` |
| `OPEN`, `RESOLVED` | remove (reason required) | an admin | `REMOVED` | `REMOVED` (admin id, reason, audit entry) |
| `REMOVED` | restore (reason required) | an admin | `RESOLVED` if it had been resolved, else `OPEN` | `RESTORED` |

Needs that existed before this release are untouched: `OPEN`, listed, helpable, cancellable. There is no draft state (the existing design has none) and no route changes a need's owner or text.

**Help offers** (`need_help_offers.status`)

| From | Action | Who | To |
|---|---|---|---|
| (new) | offer (`POST /networking/needs/{id}/help`, optional message) | any active member except the poster | `OFFERED` |
| `OFFERED` | accept / decline | the poster | `ACCEPTED` / `DECLINED` |
| `OFFERED`, `ACCEPTED` | withdraw | the helper | `WITHDRAWN` |
| `ACCEPTED` | confirm helpful / not helpful | the poster | `CONFIRMED_HELPFUL` / `NOT_HELPFUL` |

`DECLINED`, `WITHDRAWN`, `CONFIRMED_HELPFUL` and `NOT_HELPFUL` are final. An offer is **not** evidence that help was given; only the poster's "helpful" confirmation counts as a useful contribution. A credited helper on a resolved need must already be `CONFIRMED_HELPFUL`.

## 3. Schema: migration `0013_community_activity` (additive; nothing existing is changed)

* `business_needs`: 12 nullable columns (`published_at`, `resolved_at`, `cancelled_at`, `removed_at`, `removed_by_admin_id`, `removed_reason`, `resolved_offer_id`, `title_hash`, `description_hash`, `publish_month_key`, `qualifies_for_future_reward`, `quality_note`) and the partial unique index `uq_need_live_title` (only rows that carry a hash). Only `published_at` is filled (from `created_at`).
* `connections`: nullable `pair_key` and the partial unique index `uq_connection_pair_live` (only rows that carry a key; existing rows, including any legacy mutual pair, are never affected).
* `need_help_offers`: new; unique `(need_id, helper_user_id)`, status CHECK.
* `community_events`: new, **append-only** (UPDATE / DELETE refused by trigger on SQLite and PostgreSQL; TRUNCATE too on PostgreSQL), ORM guard, row-level security on PostgreSQL, ids and codes only. Existing connections are seeded into it **once**, marked `BACKFILL` (5 rows become 5 `REQUESTED`, plus one `ACCEPTED` per connected pair and `DECLINED` rows), and are never reported as observation.
* Downgrade is refused once real activity is recorded (`TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1` overrides, after an export).
* `app.migrate.HEAD` is `0013`. Development databases get the same objects from `create_all` plus `sync_schema` (no history is backfilled there).

`community_events.kind` by domain: CONNECTION `REQUESTED ACCEPTED DECLINED WITHDRAWN REMOVED`; NEED `PUBLISHED REJECTED CANCELLED REMOVED RESTORED RESOLVED`; HELP `OFFERED ACCEPTED DECLINED WITHDRAWN CONFIRMED_HELPFUL NOT_HELPFUL`; SIGNAL `CONNECTION_BURST RECONNECT_CYCLING NEED_CROSS_MEMBER_DUPLICATE HELP_BURST HELP_PAIR_REPEAT HELP_RECIPROCAL`. `reason_code` carries rejection reasons (`TOO_SHORT_DESCRIPTION`, `DUPLICATE_RECENT`, `NEAR_DUPLICATE_RECENT`, `DAILY_CAP`), `MONTHLY_LIMIT`, `BACKFILL`.

## 4. Limits and signals (all in `app/community.py`; none is a reward rule)

| Control | Value | Notes |
|---|---|---|
| Need description | ≥ 80 characters, before publication | Validation; a rejection is recorded |
| Duplicate need | same normalised title or description hash, or ≥ 85% word overlap, with the member's own need in the last 90 days | **Cancelled and removed needs count**, so delete-and-repost does not bypass it. Concurrent identical posts are stopped by the live-need index |
| Tracked monthly limit | 2 qualifying posts per member per calendar month (business time) | **Tracked, not enforced** (see section 7); a third post is still published and flagged `MONTHLY_LIMIT`; cancelling does not free a slot |
| Publication safety cap | 10 needs per member per 24 hours (database count, cancelled included); 10 attempts per hour (in-process) | `DAILY_CAP` is recorded |
| Connection requests | 30 per hour (in-process) | |
| Help offers | 30 per hour (in-process); 40 per 24 hours (database count) | One offer per helper per need |
| Signals (recorded, never acted on) | burst of ≥ 20 connection requests or ≥ 15 offers in 24 h; a pair connected ≥ 2 times before and requesting again; same need text posted by another member; ≥ 3 offers between one pair in 30 days; confirmed help in both directions within 60 days | |

The in-process rate limiter is per worker (the application's documented single-process design); the database counts and unique constraints are the authoritative limits.

## 5. Observation report

`GET /api/admin/community/report?days=N` (admin only) and the **Community activity** admin tab. Aggregate and anonymous: no id, name, e-mail or message appears. It separates **raw activity** from **outcomes** (an offer is raw activity; only `CONFIRMED_HELPFUL` is an outcome), gives medians for publication → first offer, → first helpful confirmation and → resolution with sample sizes, counts pairs with repeated or reciprocal confirmed help and the recorded signals, and states how many **synthetic** and **backfilled** events it excluded. Synthetic demo members (the reserved demo e-mail domain, exactly as Gate A) are excluded from every figure, whether they are the actor or the other party. Gate A and every launch gate are untouched.

Documented queries (read-only, run as the application's role):

```sql
-- genuine connection funnel (excludes backfill; add the synthetic filter shown in app/community.py report() for exact parity)
select kind, count(*) from community_events where domain = 'CONNECTION' and coalesce(reason_code, '') <> 'BACKFILL' group by kind;
-- needs by outcome
select status, count(*) from business_needs where published_at is not null group by status;
-- offers: raw versus outcome
select status, count(*) from need_help_offers group by status;
```

## 6. Privacy

Stored: ids, kinds, reason codes, counts. **Not stored in the history:** connection notes, need text, offer messages, names, e-mails, phone numbers. Offer messages live only in `need_help_offers` and are visible to the poster and the helper. Pair identities are a one-way hash. **Left out on purpose** (the data model and privacy policy do not support them): phone, IP, device and relationship-cluster analysis. Events keep no foreign keys, so they survive removal of a connection, a need or an account; they then hold only pseudonymous ids.

## 7. Not supported, or needing a decision

1. **The monthly limit is tracked, not enforced.** Blocking a third post would change what members can do for a reward policy that is not approved. Ambiguities to decide: block versus track; calendar month in business time (chosen) versus a rolling 30 days; whether moderator-removed posts keep their slot (they do); the draft's "1 per category per 30 days" and "3 days apart" rules are **not** implemented.
2. **History before deployment is unknown.** Existing connections are backfilled once; pairs connected and removed before the release cannot be recognised as previously connected.
3. **No draft or pre-moderation state**; moderation is after publication.
4. **No re-offer after a withdrawn or declined offer** (one offer row per helper per need).
5. **Title rules from the draft** (12 characters, 3 words) are not applied, to avoid breaking existing clients; only the 80-character description is.
6. **Offers freeze** when a need is cancelled or removed (no transition is possible); a `RESOLVED` need still allows the poster's helpful / not helpful decisions.
7. **No introductions, no mentoring, no events attendance** records (no such workflows exist).
8. Cross-process rate limiting needs a shared store if the deployment ever runs more than one worker.

## 8. Tests

`test_community_phase_a.py` (75 checks): connection lifecycle and reconnection history, duplicate and concurrent requests, authorisation, rollback, rate limits; need validation, duplicates, delete-and-repost, tracked limit, moderation attribution, compatibility with legacy needs; offer persistence, authorisation, transitions, concurrency, rollback; append-only; synthetic exclusion; report privacy and content; an empty report, account deletion leaving the history in place, and, with Growth Points recording switched **on**, that no ledger row, invoice, payment or subscription is created. `test_community_migration.py` (21 checks SQLite, 22 PostgreSQL): preservation of every existing row and column, backfill, constraints, idempotence, reversible downgrade, refusal once real activity exists. Both run on SQLite and on PostgreSQL (`TEST_DATABASE_URL`).

## 9. Deploying to an authorised observation environment (nothing here has been run on staging or production)

An authorised operator, with the target confirmed in writing:

1. **Back up** (`pg_dump -Fc`) and record the current revision (`python -m alembic current`, expected `0012`). Save row counts of `connections`, `business_needs`, `invoices`, `payments`, `subscriptions`, `growth_point_ledger`.
2. **Rehearse on a restored copy:** `python scripts/verify_phase0_migration.py --rehearse-downgrade` (it must end `N/N checks passed`) and `TEST_DATABASE_URL=<scratch> python test_community_migration.py`.
3. **Environment:** no new variable. Leave `GROWTH_POINTS_REDEEMABLE_FROM` empty, record no epoch, keep `GROWTH_POINTS_REDEMPTION_ENABLED=false`. The synthetic demo cutoff and demo data are not for this environment.
4. **Deploy:** `python -m app.migrate` (applies `0013`), confirm `alembic current` = `0013 (head)`, then start the application and rebuild both frontends (member and admin).
5. **Verify:** the counts from step 1 are identical for the existing tables; `select count(*) from community_events where reason_code = 'BACKFILL'` equals the number of connection history rows expected; a test connection, a test need and a test offer each create one event; the admin **Community activity** tab loads; `growth_point_ledger` is unchanged.
6. **Rollback precautions:** the application can be redeployed at the previous commit at any time (the changes are additive). A database downgrade is refused once real activity exists; never set `TGL_ALLOW_DESTRUCTIVE_DOWNGRADE=1` without an export and a fresh backup.
7. **Start of observation:** record the date and time of the first genuine event shown in the report. Until real members have produced activity, say that no observation has started.

## 10. Observation: start, readiness criteria, monitoring

**What starts it.** Observation starts only when this release is **deployed to an authorised environment that receives genuine member activity**. These do **not** start it and are never counted: any development database; the 30 synthetic demo members and anything they do; the one-time `BACKFILL` history written by migration 0013; an operator's own verification activity (note its last timestamp; the observation begins with the first real member's event after it). **Record the real timestamp** of the first genuine event (`observation.first_event_at` in the report) in the handoff sign-off table; never estimate or back-date it. **This repository has not started observation, Gate A is not met, and nothing is deployed.**

**Report scope.** The `observation` block is all-time and ignores the `days` filter (stated in its `scope` field); its `baseline` note says that no earlier baseline exists, so no comparison with a "before" is possible.

**Readiness criteria for the policy decision** (all must hold; none holds today):

1. At least one full calendar quarter of genuine activity (two preferred), with the start recorded as above.
2. A minimum of genuine activity to judge from, set by management in advance (suggested floor: 30 members with activity and 100 need or connection events; below that, say "insufficient data").
3. The report reviewed on the agreed cadence with no unexplained data-quality gap.
4. Signals reviewed (burst, reciprocal and repeated-pair help); no action was taken automatically.
5. The shadow replay (`scripts/community_candidate_evaluation.py`) run on the genuine history and attached, understood as a **lower bound** and **hypothetical**.
6. The decision register in the proposal (section 16) answered in writing, including the privacy and moderation items.

**Monitoring while observing.** Owner and cadence named (weekly for the first month, fortnightly after). Look at: members with activity; acceptance and reconnection rates; needs published, rejected (by reason) and over the tracked limit; offers versus confirmed help; medians to first offer, first helpful confirmation and resolution (with sample sizes); repeated and reciprocal pairs; signals. Treat a sudden jump in rejections or signals as a product or abuse question, not as a gate result.

**What this document does not do:** approve any reward, set any point value, or claim that the monthly limit of two qualifying posts is enforced (it is tracked only).

## 11. Next stage

`GROWTH_POINTS_COMMUNITY_REWARDS_IMPLEMENTATION_SPEC.md` specifies the candidate Community rewards (per-reward contract, deterministic cap order proved by `test_candidate_policy_invariants.py`, reversal, abuse signals, analytics, build list and blockers). `backend/scripts/community_candidate_evaluation.py` (tested by `test_candidate_evaluator.py`) is the read-only, shadow-only replay. **No award is made in Phase A.**
