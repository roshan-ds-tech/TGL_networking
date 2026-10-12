# Community rewards: implementation-ready specification (CANDIDATE, NOT APPROVED)

> **DRAFT BUSINESS POLICY — NOT APPROVED FOR PRODUCTION.** Nothing in this document is built, enabled or awarded. It turns the values proposed in `docs/GROWTH_POINTS_BUSINESS_POLICY_PROPOSAL.md` (revision 2) into a contract an engineer can implement **after** management approves them and **after** a genuine observation period. `docs/GROWTH_POINTS_FINAL_SPEC.md` (rule version `growth-points-v3`) stays the only approved rule set. No community activity earns a Growth Point today; Phase A (`docs/PHASE_A_COMMUNITY_ACTIVITY_RECORDING.md`) only records facts.

Executable companions (all local, none writes a ledger row):

| File | What it does |
|---|---|
| `docs/growth_points_model/community_candidate_model.py` | Pure reference model of the candidate rules: the **deterministic cap order**, requested versus awarded, and the recorded cap trace |
| `backend/test_candidate_policy_invariants.py` | 19 checks: determinism, every ceiling on 75 randomised streams over all three plans, headroom, scenarios S1/S2/S3/S6, reciprocal, pair budget, prerequisite, per-pair limits |
| `backend/scripts/community_candidate_evaluation.py` | **Shadow-only, read-only** replay of the genuine Phase A history through the model; aggregate output labelled HYPOTHETICAL; creates no table and no row |
| `backend/test_candidate_evaluator.py` | 10 checks: empty history, synthetic and backfill excluded, anonymous, labelled, byte-for-byte read-only, `--since` |

## 1. Sequencing (observation first)

1. **Phase A (built locally, undeployed):** record facts. No awards.
2. **Deploy Phase A to an authorised observation environment** and let genuine members use it. The observation clock starts at the first genuine event the admin report shows, and only then. Synthetic demo members and `BACKFILL` events never count.
3. **Observe** at least one full calendar quarter (two preferred) with the Community activity report and, optionally, the shadow evaluator.
4. **Management decision** on the values, limits and the items in section 10.
5. **Only then build** what section 8 lists, as an immutable `growth-points-v4` (never an edit to v3), in shadow first.
6. **Redemption** stays behind its own gate (approved cutoff, written approvals); this specification sets none.

Awards during steps 1–3 are **not permitted**, and the evaluator is not an award.

## 2. Per-reward contract

Points: 1 point = ₹0.10. "Today" is what Phase A already records. All values are **proposed**.

| ID | Event type | Trigger (the verifiable fact) | Recipient | Points | Verification level | Pending / void window | Idempotency key | Rule-specific limits | Today (Phase A) | Missing before it can be built |
|---|---|---|---|---:|---|---|---|---|---|---|
| C2 | `CONNECTION_ACCEPTED` (new) | `community_events` CONNECTION/`ACCEPTED`, first ever for the pair | both members | 10 each | L1 counterparty acceptance | 7 days; removal ≤ 7 days → `VOID`, later → none | `CONNECTION_ACCEPTED:connection:{pair_hash}:{member}` | once per pair for life; 6 a month; participation sub-limit; community pair budget | recorded, with reconnection flag | profile-completeness and ≥ 7-day-access checks; rule version, event type |
| N1 | `NEED_PUBLISHED` (new) | NEED/`PUBLISHED` with no `reason_code` | poster | 20 | L1 system validation (80-char description, duplicate, limits) | 7 days; removed ≤ 7 days → `VOID`, ≤ 60 days → `REVERSAL` | `NEED_PUBLISHED:need:{need_id}:{poster}` | 2 a month; (proposed, not built: 1 per category per 30 days, 3 days apart, 30-day re-post lock) | recorded; monthly limit **tracked, not enforced** | enforcement decision; category and spacing rules; moderation sample |
| H2 | `NEED_HELP_CONFIRMED` (new) | HELP/`CONFIRMED_HELPFUL` (poster marks the offer helpful) | helper | 25 | L1 poster confirmation | 7 days; withdrawn/removed ≤ 7 days → `VOID` | `NEED_HELP_CONFIRMED:offer:{offer_id}:{helper}` | 8 a month; ≤ 2 per poster→helper pair per quarter; reciprocal 50%; (not built: ≤ 3 helpers per need, 60-char/12-word minimum response) | recorded; offer text is kept in `need_help_offers` | response-text rule; per-need helper limit; poster-lapse reminder |
| H4a | `NEED_RESOLVED` (exists, disabled in v3) | NEED/`RESOLVED` with a credited, already-`CONFIRMED_HELPFUL` offer | helper | 45 (v3 future value 60) | L2 poster resolution; helper acknowledgement | 7 days; dispute → `VOID`; fraud ≤ 60 days → `REVERSAL` | `NEED_RESOLVED:need:{need_id}:{helper}` | 4 a quarter; 1 per poster→helper pair per quarter; reciprocal 50% | recorded; no helper acknowledgement step | acknowledgement step; poster note ≥ 40 chars; linked-referral exclusion; changes an approved future value |
| H4b | `NEED_CLOSED` (new) | same event | poster | 10 | same | same | `NEED_CLOSED:need:{need_id}:{poster}` | 2 a month; participation sub-limit | recorded | as above |
| H3a/b | `SUCCESSFUL_INTRODUCTION` (exists, disabled) and meeting bonus | both parties confirm; both confirm a meeting ≤ 60 days | connector | 30 (+45) | L2 both members | 7 days; dispute → `VOID` | `…:need_response:{id}:{helper}` (+`:meeting`) | 2 a quarter; once per introduced pair; **the meeting bonus requires its introduction to have been rewarded** | **not recorded** (no workflow) | the whole workflow; changes an approved future value |
| O2 | `BUSINESS_VERIFIED` (new) | admin sets verified | member | 75 | L4 admin | admin revoke → `REVERSAL` ≤ 60 days | `BUSINESS_VERIFIED:member:{user}:{user}` | once | admin route exists; no stored approval event | stored approval event |
| Zero | connection request, decline, withdraw, offer, unconfirmed response, view, login | any | none | 0 | | | | | | `ZERO_POINT_ACTIONS` test must still hold for every non-reward action |

A reward is only ever issued from a **stored fact**. If the fact is later removed, the reward is voided or reversed by a **new** ledger row. Nothing is edited or deleted.

## 3. The cap order (deterministic; executable in the reference model)

A reward is cut by the **first** rule that reduces it; every rule that reduces it is recorded in order in `cap_trace`; `requested_points` is never changed; `capped_by` names the first. The cycle ceiling is last so no combination can exceed it.

| # | Rule (`capped_by`) | Effect |
|---:|---|---|
| 1 | `IDEMPOTENCY` | the same key is decided once; a repeat awards 0 and changes no total |
| 2 | `PREREQUISITE` | the meeting bonus pays only if its introduction was itself rewarded |
| 3 | `PAIR_ONCE` | a connection pays once per pair per member, for life |
| 4 | `PAIR_RECIPROCAL` | help returned within 60 days pays 50% |
| 5 | `PAIR_COMMUNITY` | community budget 150 points per pair per quarter, both directions combined |
| 6 | `PAIR_LOW_ASSURANCE` | existing v3 budget 1,500 per pair per quarter (low-assurance points) |
| 7 | `FREQUENCY_LIMIT` | monthly or quarterly count per member (connections 6/month, needs 2/month, helps 8/month, closes 2/month, resolutions 4/quarter, introductions 2/quarter); per-pair quarter limits (helps 2, resolutions 1) |
| 8 | `COMMUNITY_PARTICIPATION` | connection, need published, poster close: at most 5% of the cycle ceiling |
| 9 | `COMMUNITY_POOL` | those plus confirmed help: at most 12% of the cycle ceiling |
| 10 | `CATEGORY_SUBCEILING` | PROCESS 25% / CLOSURE 60% / OTHER 20%; the Community pool is **nested in OTHER**, so non-closure stays 45% |
| 11 | `DAILY_CEILING` | 500 a day, low-assurance points only |
| 12 | `MONTHLY_CEILING` | 3,000 a month, all points |
| 13 | `CYCLE_CEILING` | 12% of the plan price: always last |

Plan limits (points): ceiling 3,600 / 6,000 / 12,000; pool 432 / 720 / 1,440; participation 180 / 300 / 600; OTHER 720 / 1,200 / 2,400. Closure headroom (100% − 45%) is 1,980 / 3,300 / 6,600, which covers the largest single referrer closure reward (1,890) on every plan. A separate 8% category (the first draft) would not on Connect.

Proved by `test_candidate_policy_invariants.py`: determinism; `0 ≤ awarded ≤ requested`; trace in the documented order; no ceiling exceeded on 75 randomised streams; a member who has filled every non-closure category as hard as possible is still paid a 1,890 closure in full. **Existing v3 interaction, not caused by the proposal:** the monthly 3,000 limit can still trim a 1,890 closure in a month in which the member already holds more than 1,110 other points.

**Implementation note.** The reference model is not the engine. The engine already implements steps 1, 3 (`once_per`), 4 (`pair_adjust`), 6, 7 (per-event limits), 10–13 and the cap trace; the additions are step 2, per-pair community budget and per-pair quarter limits, and the two nested pools. Whatever is built must produce the **same decisions as the model on the same events**; the model's randomised streams are the equivalence test.

## 4. Requested versus awarded

A capped reward still writes a ledger row: `requested_points` (the base value), `points_delta` (awarded, possibly 0 with status `CAPPED`), `capped_points`, `capped_by`, `cap_trace`. Members and admins can therefore always see **why** a reward was less than its value.

## 5. Reversal, void and expiry

All as in the proposal §7.1, using the existing append-only ledger: pending is derived from `available_at`; `VOID` while pending; `REVERSAL` ≤ 60 days after the window; `EXPIRY` at the end of the renewal grace; ceilings count `EARN + VOID + REVERSAL`, so a void frees the room; re-instatement is a new versioned key; **no ledger row is ever edited or deleted**. Community lots below `REVIEW_MIN_POINTS` are not individually reviewed unless part of a flagged pattern.

## 6. Abuse signals

| Signal | Source | Status |
|---|---|---|
| Connection burst, reconnect cycling, help burst, repeated help pair, reciprocal help, cross-member duplicate need | `community_events` SIGNAL rows | **Recorded in Phase A**, non-punitive, never acted on |
| Closed cluster, instant confirmation (< 5 min, repeated), self-answered need, resolved without content | none | New; build with `fraud.raise_flag` |
| Same-phone match between accounts | `users.phone` (not unique, unverified) | Flag only, never refuses |
| IP or device hash on accounts; relationship-cluster analysis; retention of need and response text as evidence | not collected | **Requires privacy approval** (section 10); Phase A deliberately does not do these |

Proportionality: rewards of 10–75 points do not justify evidence uploads. The defences are the small sub-limits and structural ceilings; the worst fully coordinated ring of five paying members earns about 710 points (₹71) per Connect cycle in the model (scenario S6), against a ₹3,000 membership.

## 7. Analytics (what to measure; needs no new table in Phase A)

Participation quality, outcomes, retention, programme health and integrity, as proposal §12. Available **now** from Phase A: connections accepted, reconnections, needs published/rejected/over the tracked limit, time to first offer / helpful / resolution with sample sizes, offers versus confirmed help, repeated and reciprocal pairs, signals. Available **after** build: void/reversal rate, Community share of issuance, cost per confirmed meeting and per verified closure.

**Shadow evaluator.** `scripts/community_candidate_evaluation.py` replays genuine history through the model and prints, in aggregate, the points the proposed rules *would* have requested and awarded, the number of events each rule reduced, and a per-member distribution. It is **not** an award: it is labelled HYPOTHETICAL, uses no table, writes nothing, excludes synthetic and `BACKFILL` events, and says "no genuine activity" until there is some. It cannot see introductions or the Process/Closure points that share the monthly and cycle limits, so its figures are a **lower bound** for exposure. Use it to check the proposal's activity assumptions against measured behaviour before the decision in step 4; never as evidence that the proposal is approved or that Gate A is met.

## 8. Build list (after approval; in this order)

1. `rules.py`: `growth-points-v4` as a **new** immutable version (v3 untouched); new event types; nested pool and participation limits; community pair budget; per-pair quarter limits; `REVIEW_MIN_POINTS`; `ZERO_POINT_ACTIONS` narrowed.
2. Migration (next revision after `0013`): extend the ledger `event_type` CHECK (append-only table with triggers: rebuild and re-verify them); pool/participation ceilings on `growth_point_cycles` (cycles are frozen when created: v4 applies to cycles that start after the effective date, or derives the ceilings from `ceiling_points` when the columns are empty). Rehearse on a restored copy with `scripts/verify_phase0_migration.py`.
3. Engine: step 2 prerequisite, per-pair community budget, per-pair quarter limits, two nested pools (see the implementation note in section 3).
4. Sync hooks: `connection_changed`, `need_changed`, `offer_changed`; branches in `events.still_invalid` and `jobs.resync_pending`; a missing reference counts as invalid.
5. Missing workflows (Phase B): helper acknowledgement on resolution, introductions, moderation queue, new fraud flags, stored `VERIFIED` approval event.
6. Tests: every event for duplicate, concurrent, remove-and-reconnect (pays once), self/alternate account, reciprocal, cap order (must equal the reference model), void/reversal/expiry, demo exclusion, closure-headroom, update "nothing that must earn 0 is a reward event".
7. v4 in **shadow** only, reconciliation clean for 60 days, then member preview copy, then — as a separate decision — anything about redemption.

## 9. Blockers that are not code

* A real observation period on a deployed environment (none has started; Gate A is not met).
* Management approval of every value, limit, pool and the changes to approved future values (`NEED_RESOLVED` 60 → 45, introductions 75/+150 → 30/+45).
* Privacy decisions (IP/device hash, text retention, cluster analysis) and a staffed moderation queue with a stated response time.
* Accounting/legal wording (points for activity rather than purchase).

## 10. Open questions for management

Reverse the v3 zero rule for connections and need posting? Accept that Community displaces the approved future events for High/Top members inside the shared OTHER pool? Block or merely track the third monthly need? Calendar month or rolling 30 days? Does a moderator-removed need keep its slot? Do community points count toward the 3% cost threshold? Effective date and treatment of cycles that already exist? (Full register: proposal §16 and the decision register in this repository's handoff documents.)
