# Growth Points: shadow-period eligibility, subscription-page redemption, and demo data

**REAL REDEMPTION IS DISABLED.** Nothing in this document enables it. No cutoff has been officially approved, so none is configured.

## 1. Final decision: shadow-period points do not carry over

* Points calculated during the shadow period are **historical records only**: analytics, audit, reconciliation, fraud review. They are **permanently ineligible** for real redemption. They are never transferred, converted or grandfathered into a redeemable balance.
* Only points whose `event_at` is **at or after the officially approved cutoff** can qualify, and then only under the existing rules (earning ceilings, cycle, expiry, plan cap of 15 % of the NEW invoice, FIFO, fraud/dispute reversal, one use per cycle).
* The line is enforced in **three places**, not in the front end:
  1. **Database:** `growth_point_redemption_epoch` holds the approved cutoff, **once**, immutably (singleton row, append-only triggers, CHECK `cutoff_at >= recorded_at` so it can never be back-dated). Migration 0012. Whether a lot is shadow-period is a plain query: `event_at < epoch.cutoff_at`.
  2. **Business logic:** the redemption service builds its eligible lots only from `event_at >= cutoff` (`service._lot_filter`). Shadow-period lots are never offered, never consumed, and are reported as "excluded" so the member sees why.
  3. **Configuration:** `GROWTH_POINTS_REDEEMABLE_FROM` is honoured only when it **equals** the recorded cutoff. A later value, an earlier value (an attempt to pull shadow points in) or an unreadable value all mean *nothing is redeemable*.
* Recording the cutoff is a deliberate act: `POST /api/admin/growth-points/redemption/epoch` (programme owner only; needs `MANAGEMENT_MODEL` in `GROWTH_POINTS_APPROVALS`; explicit UTC offset; not in the past; once only; audited). **Do not call it without a written management approval of the exact instant.** It does not enable redemption.

## 2. `GROWTH_POINTS_REDEEMABLE_FROM` (exact semantics, from the code)

| Question | Answer |
|---|---|
| Format | An **ISO-8601 datetime with an explicit UTC offset or `Z`**, e.g. `2027-01-01T00:00:00+05:30` or `2026-12-31T18:30:00Z`. Read by `app.config.parse_cutoff` (Python `datetime.fromisoformat`, then required to be offset-aware) |
| Date only (`2027-01-01`), no offset (`2027-01-01T00:00:00`), text, impossible dates | **Refused at startup** (the application will not start). Previously a bare date was silently read as midnight UTC; that ambiguity was removed |
| Meaning | The earliest instant a point may have been earned (`growth_point_ledger.event_at`) and still be redeemable |
| Boundary | **Inclusive**: a point earned exactly at the cutoff qualifies; one second before does not (tested) |
| Timezone | Compared in **UTC**; the offset in the value fixes the instant. Business calendars elsewhere (daily/monthly ceilings) remain IST, unrelated to this value |
| Empty (the default) | Nothing is redeemable |
| Set but no matching row in `growth_point_redemption_epoch` | Nothing is redeemable (`cutoff_not_recorded`) |
| Set but different from the recorded cutoff (earlier or later) | Nothing is redeemable (`cutoff_mismatch`) |
| Unreadable at runtime (e.g. changed in memory) | Nothing is redeemable (`cutoff_unreadable`); never an error for the member |
| Applied to the ledger | Never edits it. The ledger stays append-only; the cutoff only filters which lots the redemption calculation may use |
| Applied to renewals / expiry | A renewal quote and a redemption use only lots with `event_at >= cutoff` that are also available, unexpired and in the OLD cycle; expiry is unchanged (shadow-period lots still expire like any other) |
| Current live value | **Empty. No cutoff has been officially approved or provided, so none was set.** What is needed: a written management approval of the exact instant (with offset), `MANAGEMENT_MODEL` recorded in `GROWTH_POINTS_APPROVALS`, then the programme owner records it with the endpoint above and the same value is set in `GROWTH_POINTS_REDEEMABLE_FROM` |

`GROWTH_POINTS_DEMO_CUTOFF` (same format) is separate: development/test only, refused in production, used only by the simulation below.

## 3. The subscription-page flow (`/app/subscription`)

1. The member sees **Your subscription** (plan, price, term, start and end) and **Renewal**: current plan, the renewal window, a plan chooser and the price of the chosen plan.
2. If they have **eligible, unexpired, redeemable** points and renewal is open, a **Redeem Growth Points** button sits beside the price. Otherwise there is no active button and a plain explanation is shown (no points; points earned before redemption began can never be redeemed; renewal not open).
3. Clicking it shows the calculation: eligible points, the most that can be applied (15 % of the new plan), points used, original price, discount, points left, **final amount payable**.
4. **Confirm redemption** sends only what the member saw. The backend recomputes everything (member, plan, cycle, lots, cutoff, expiry, cap, floor); if anything changed it refuses (`calculation_changed`). Otherwise one transaction creates the renewal subscription, an invoice with the points discount line, a payment for the reduced amount, the redemption record and lot lines, and the audit entry. If any step fails, nothing is saved (tested).
5. The confirmation says the points were used as a subscription discount and **were not converted into cash**; the pending renewal invoice follows with the payment-proof step. The member can instead renew at full price.
6. Three modes, always labelled: **REAL** (open for this member: every gate, Gate A included), **SIMULATION** (demo accounts in development, below) and **PREVIEW** (hypothetical, no button). Before approval only SIMULATION and PREVIEW can occur; the real confirm is refused with `redemption_disabled`.

## 4. Demo data (development / test databases only)

* **Seed:** `python scripts/seed_demo_members.py --database-url sqlite+aiosqlite:///./var/tgl_demo.db` (idempotent; keyed by email; reuses the demo cutoff stored in `var/demo_seed_manifest.json`). To use it: run the backend with `DATABASE_URL=sqlite+aiosqlite:///./var/tgl_demo.db GROWTH_POINTS_SHADOW_MODE=true GROWTH_POINTS_MEMBER_PREVIEW=true GROWTH_POINTS_DEMO_CUTOFF=<demo_cutoff from the manifest>`. A separate demo database was used so the main development database is untouched.
* **Safety:** refuses production, Supabase photo storage, and any database that is not a local SQLite file or localhost PostgreSQL (`assert_safe`, tested). Seeding staging needs a separate, explicit decision and is not enabled. **Never** seed production.
* **Accounts:** 30 members `demo-01@demo.example.com` … `demo-30@demo.example.com` (the reserved `example.com` space; the `.test` TLD was tried first and is refused by the app's own email validation). Local-only password `Demo-Local-Only-2026!`, documented here because the seed can not run where a real credential could matter. Each has a personal profile, business (all ten categories), networking profile (tags, interests, mentoring flag), founder story, a profile picture and an active subscription with an invoice at full price numbered `DEMO-xxxx` and **no payment row**.
* **Six Growth Points scenarios** (members 01-06, through the normal reward engine, shadow rows, clearly synthetic): no points; eligible post-cutoff points (2,400); shadow-period-only points (2,400, excluded); expired; dispute-reversed; cap-hit (6,000 earned, 4,500 usable on a Connect renewal).
* **Pictures:** DiceBear **"lorelei"** illustrated avatars by Lisa Wischofsky, **CC0 1.0** (public domain, no attribution required; https://www.dicebear.com/styles/lorelei/), downloaded once to `var/demo_assets/` and stored through the app's own photo pipeline (re-encoded, size-limited, local storage, no third-party hotlinks). They are illustrations, not photographs, and do not depict real people; no real member photograph was used. If a download fails a generated initials avatar is stored instead; the app's own initials fallback also covers a missing or failed image.
* **Cleanup:** `python scripts/seed_demo_members.py --database-url … --cleanup` deactivates the synthetic accounts and removes their photos. Subscription, invoice and ledger rows are append-only / RESTRICT by design, so to remove everything delete the demo database file (`var/tgl_demo.db`, `var/demo_seed_manifest.json`, `var/demo_assets/`).

## 5. Simulated versus real

| | Simulated (demo) | Real |
|---|---|---|
| Who | `@demo.example.com` accounts, development only, `GROWTH_POINTS_DEMO_CUTOFF` set | genuine members, every gate open |
| Endpoint | `POST /api/v1/renewal/simulate`: the real confirm code, then an unconditional rollback | `POST /api/v1/renewal/confirm` |
| Saves | **nothing** (no subscription, invoice, redemption, lot line, point or audit row: tested) | the renewal, invoice discount, redemption record, lot lines |
| Label | "SIMULATION: nothing is applied", "SIMULATION COMPLETE: nothing was applied" | the confirmation text above |
| Exists in production | **no** (404; the demo cutoff is refused at startup) | only after Phase 3 approval |

**Synthetic data never counts as genuine observation.** Demo members are recognised by their reserved domain; Gate A, the objective gates and the review's sufficiency count **genuine members only** (`app/demo.py: real_stats`), and say how many synthetic members and ledger rows were excluded. The gate rules were not changed to make Phase 3 look ready (tested: with 30 synthetic members present Gate A is still NOT MET).

## 6. Remaining gates (unchanged)

Gate A (30 genuine active members, 30 days of genuine observation, clean data quality); no external approval recorded (management model, accounting/GST, backup, rollback test, member Terms, monitoring owner); migrations 0010-0012 not yet run on staging or production; kill switch and rollback not rehearsed on a real environment; **no official eligibility cutoff approved**. `python -m app.rewards.gates` shows the live status.

## Admin "Demo members" tab, the member Growth Points page, and finale members

- **Admin → Demo members** lists the synthetic members with email, the shared local-only password (`DEMO_PASSWORD` in `app/demo.py`, hidden until "Show"), plan, business, city, points and scenario. In production the endpoint (`GET /api/admin/growth-points/demo-members`) returns `enabled: false`, no rows and no password. If none exist yet it shows the command: `python scripts/seed_demo_members.py` (from `backend/`).
- Demo members have no payment rows, so they do not appear under **Admin → Subscriptions** (that list is payment-based).
- **Member page:** the Networking overview "Growth Points" card opens `/app/growth-points` (`GET /api/v1/growth-points/overview`): total, ring to the term limit, how points are earned, what does not earn, activity feed. A member sees their own numbers only while the preview is on (or real redemption is open); otherwise the page only explains how it works.
- **Why referrals did not raise points:** (1) recording is off unless `GROWTH_POINTS_SHADOW_MODE=true` (set in the local `backend/.env`); (2) members whose Networking access is the Season 1 finale window have no subscription or membership row, so they had no term and every reward was refused (`NO_ACTIVE_CYCLE`). They now get the one complimentary 3-month term (Connect ceilings) from the finale window; (3) creating a referral earns nothing by design: points arrive when it is accepted, contacted, met or closed and verified.
- Tests that need the shipped defaults now pin `GROWTH_POINTS_SHADOW_MODE` / `GROWTH_POINTS_MEMBER_PREVIEW` to false (`test_phase0.py`), so a developer's local `.env` cannot change results. `test_growth_points_page.py` covers the page, the finale-member fix and the demo list.

## Demo photo isolation (local development)

* Demo profile pictures are stored in their own directory, `<UPLOAD_DIR>/demo_photos/` (locally `backend/var/uploads/demo_photos/`), under `demo-<hex>.jpg` names. Genuine member photos stay in `<UPLOAD_DIR>/photos/` under plain names. The photo store (`app/storage.py`) routes by name, so a demo name can only ever read, write or delete inside the demo directory, and a genuine upload can never produce a demo name. Demo photos are local-only: never written to or served from Supabase.
* Each database has its own manifest, `backend/var/demo_seed_manifest.<database-file-stem>.json`, listing its synthetic members, their photo file and the file's SHA-256.
* `python scripts/seed_demo_members.py --database-url sqlite+aiosqlite:///./var/<db>.db` seeds (idempotent; reactivates members after a cleanup; restores a missing demo photo).
* `... --cleanup` deactivates the synthetic members and removes only the demo-directory photos they reference whose checksum still matches the manifest. A synthetic member still pointing at an older plain-name file in the shared directory is left untouched and reported.
* `... --migrate-photos [--dry-run]` moves older demo photos out of the shared directory. Ownership is proven first (synthetic member; no genuine user in any local database uses the file); the copy is verified byte for byte, the row repointed, and only then is the old file removed, and only if nothing still references it. Unreferenced files are never touched.
* The `--database-url` option is now honoured (nothing from `app` is imported before it is applied; previously it could be ignored).
* Restart the backend after pulling this change: an older running server does not know the `demo-` names and would show fallback avatars until restarted.
* Tests: `backend/test_demo_isolation.py` (23 checks; SQLite and PostgreSQL).

## Admin Demo tab photos, and the dev-database invoice rule

* **Admin photos.** The Demo members tab loads each picture from `GET /api/admin/growth-points/demo-members/{user_id}/photo`, not from the members-only `/api/v1/members/{id}/photo` (which is unchanged and still needs a member session). The admin route needs an administrator session (401 otherwise: anonymous visitors and ordinary members are refused), exists only outside production, serves only a synthetic member whose stored name is in the `demo-` namespace (a genuine member's id, an unknown id, a path-like id or a missing file all give 404), is read-only, and reads through the existing photo store, which validates the stored name. The client sends an id only, never a file name or path.
* **Dev-database invoice rule.** A development SQLite database created before Phase 2 still has the Phase 0 rule `CHECK (discount_minor = 0)` on `invoices`; it makes the redemption *simulation* fail with a 409 (the database is refusing a discount, which is also why nothing is ever saved). Production and staging get the Phase 2 rules from migration 0011. For a local dev database, back it up and run once (it backs up to `var/backups/` itself, rebuilds only the `invoices` table, and verifies every row is identical):

  ```bash
  cd backend
  .venv/bin/python scripts/upgrade_dev_invoice_checks.py --database-url sqlite+aiosqlite:///./var/tgl.db --dry-run
  .venv/bin/python scripts/upgrade_dev_invoice_checks.py --database-url sqlite+aiosqlite:///./var/tgl.db
  ```
  `var/tgl_demo.db` already has the current rules. The simulation also needs `GROWTH_POINTS_DEMO_CUTOFF` (the date in `var/demo_seed_manifest.<db>.json`) in `backend/.env`; without it the subscription page correctly shows the plain PREVIEW and `POST /api/v1/renewal/simulate` returns 404.
* Tests: `test_demo_isolation.py` (34 checks, includes the admin / member / anonymous matrix) and `test_dev_invoice_upgrade.py` (12 checks).

## Synthetic members and community activity (Phase A)

* Synthetic demo members (the reserved `@demo.example.com` domain, the same `demo.synthetic_clause()` Gate A uses) are **excluded from every figure** of the admin Community activity report and from the shadow evaluator `scripts/community_candidate_evaluation.py`, whether they are the actor or the other party of an event. Their events are only *counted* separately (`synthetic_events_excluded`).
* Demo-member connections, needs and offers (if anyone creates them in a development database) are **not observation**. History that was backfilled when migration 0013 was installed (`reason_code = BACKFILL`) is excluded the same way.
* Neither the demo data nor any development database starts the observation period, and neither can be used to claim Gate A. Observation starts only after deployment to an authorised environment with genuine members (`PHASE_A_COMMUNITY_ACTIVITY_RECORDING.md`, section 10).
* `backend/var/tgl_demo.db` has no community tables until it is migrated; `var/tgl.db` received them additively. Neither has been reset or reseeded.
* Tests: `test_community_phase_a.py` (synthetic exclusion in the report), `test_candidate_evaluator.py` (synthetic and backfilled rows excluded from the replay).
