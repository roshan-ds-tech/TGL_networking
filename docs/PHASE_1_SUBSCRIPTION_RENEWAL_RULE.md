# Phase 1: subscription renewal rule for Growth Points

**REAL FINANCIAL EFFECT = ₹0.** Everything below is shadow mode: calculated and recorded, never applied to an invoice or a payment. Member preview is OFF.
This replaces the earlier "Option A" wording. Source: management decision lock (renewal-based plan change).

## The rule in one page

| Topic | Rule |
|---|---|
| **Plan changes** | **Only at renewal.** There is no normal mid-cycle upgrade or downgrade. A member stays on the current plan until the renewal window, then chooses the same plan, an upgrade or a downgrade. Renewal creates the next subscription cycle |
| **Old points** | Stay associated **permanently** with the cycle they were earned in. They are not moved into the new cycle's earning balance, do not raise its ceiling, and are not its starting balance |
| **Renewal redemption** | Eligible old-cycle points **may be redeemed against the NEW renewal invoice** (hypothetical in Phase 1) |
| **New cycle** | Starts with **zero transferred earning points** and its own ceilings (3,600 / 6,000 / 12,000) |
| **Redemption ceiling** | **15 % of the NEW plan's invoice price** in points: 4,500 / 7,500 / 15,000. It limits how many eligible points can be used on one renewal invoice. It is not an earning limit |
| **Earning ceiling** | 12 % of the price of the plan of the cycle **in which the points were earned**; never transferred |
| **Formula** | `redeemable_points = MIN(eligible_old_cycle_points, new_plan_redemption_cap_points)`. The OLD cycle decides how many points exist; the NEW plan decides how many can be used |
| **Point value** | 1 point = ₹0.10 (10 points = ₹1) |
| **Order of use** | FIFO: oldest eligible lot first, then the next. Newer lots are never touched while an older eligible lot has points |
| **Renewal window** | 30 days before the term ends to 30 days after. Points unused when the window closes expire, each expiry a new ledger row. Expired points are never restored |
| **Non-renewal** | No new cycle starts; the old points stay eligible only through the window, then expire. A later re-subscription is a new cycle and gets none of them |

## Worked examples (all hypothetical)

| Renewal | Old-cycle points | New invoice | Cap | Used | Hypothetical payable | Left (old cycle) | New cycle ceiling |
|---|---|---|---|---|---|---|---|
| Connect → Connect | 3,600 (₹360) | ₹3,000 | 4,500 (₹450) | 3,600 (₹360) | ₹2,640 | 0 | 3,600 |
| Connect → Growth | 3,600 (₹360) | ₹5,000 | 7,500 (₹750) | 3,600 (₹360) | ₹4,640 | 0 | 6,000 |
| Growth → Elite | 6,000 (₹600) | ₹10,000 | 15,000 (₹1,500) | 6,000 (₹600) | ₹9,400 | 0 | 12,000 |
| Elite → Growth (above the cap) | 12,000 (₹1,200) | ₹5,000 | 7,500 (₹750) | 7,500 (₹750) | ₹4,250 | 4,500 (₹450) | 6,000 |
| Growth → Connect (above the cap) | 6,000 (₹600) | ₹3,000 | 4,500 (₹450) | 4,500 (₹450) | ₹2,550 | 1,500 (₹150) | 3,600 |
| Growth → Connect (exactly at the cap) | 4,500 (₹450) | ₹3,000 | 4,500 | 4,500 | ₹2,550 | 0 | 3,600 |

Points left over above the cap are **not** moved into the new cycle; they follow the expiry rule (they expire when the old cycle's window closes). All six cases are tests.

## Real redemption (Phase 2, built, disabled)

The same rule is implemented for real in `app/redemption/` and `POST /api/v1/renewal/confirm`, behind every gate (see `PHASE_2_REDEMPTION_READINESS.md`). A renewal can be raised in the last 30 days of the running term (it starts when that term ends) or up to 30 days after it; plan changes happen only there. Points redeemed become a discount line on the NEW invoice (≤ 15 % of its list price); a refunded or cancelled renewal restores them only up to their original expiry.

## What is built for the shadow period (Phase 1)

* `app/rewards/renewal.py` computes the calculation (no writes) and records it once per renewal subscription.
* One **`growth_point_renewals`** record per renewal: old cycle, current plan, new plan, new price and term, eligible points, new-plan ceiling, points used, points left, hypothetical discount, hypothetical amount payable, when it was decided, the old points' expiry, the rule version, an idempotency key. Append-only (database triggers), `shadow = true` (CHECK), and it can never use more than the eligible points or the new ceiling (CHECK). It holds ids only; there is deliberately **no foreign key** to any invoice, payment, subscription or plan table.
* One **`SIM_REDEEM`** ledger row per lot consumed, pointing at the earning lot (`parent_id`), the old cycle and the renewal record. The earning rows are never edited or deleted. The ceilings count earning only, so using points never frees earning room.
* The sweep (`python -m app.rewards.jobs`, or the admin Sweep button) records new renewals **before** it expires anything.
* Admin only: `GET /api/admin/growth-points/renewal-preview?member_id=&plan_code=` shows exactly what the renewal invoice would show (current plan, new plan, new price and duration, eligible old-cycle points, point value, the new plan's ceiling, points to be used, hypothetical discount, hypothetical amount payable, the lots consumed), and `GET /api/admin/growth-points/renewals` lists the records.
* Idempotent: double clicks, refreshes, API replays, payment or invoice retries, repeated sweeps and six concurrent runs leave one record and one set of rows (tested).

## Edge cases (decided conservatively; flagged for management)

1. **Not a renewal → nothing is used.** A subscription raised before the window opens, after it closes, or after an administrative refund and replacement is recorded as `NOT_A_RENEWAL` and uses nothing, so an admin replacement can never become a way to spend points.
2. **A refunded term's points are never eligible** (`REFUNDED_CYCLE`). They stay in the old cycle and expire there.
3. **A renewal that is later refunded**: the shadow use is **not** restored in Phase 1; the sweep raises a `RENEWAL_REFUNDED` review flag. Restoration (only up to the original expiry, never resurrecting expired points, as a new event) is a Phase 2 policy decision.
4. **Early renewal.** The Phase 0 subscription flow refuses a second subscription while one is live, so a member can renew from the term's end (up to 30 days after), not in the 30 days before it. The rule's "30 days before" is honoured by the calculation but cannot occur until the subscription flow supports early renewal (Phase 2/3 work).
5. **Points expired before the renewal was recorded** (a sweep ordering accident) are flagged `RENEWAL_AFTER_EXPIRY` rather than silently lost.
6. **The member must see the calculation before confirming** (the renewal-invoice screen) cannot be shown to members while the member preview is OFF. Until management enables it, only admins see the calculation. This is a Phase 2 build item and a management decision.

## Tests

`backend/test_phase1.py` (renewal section): the five transitions plus the exact-cap case; below/at/above the cap; FIFO with partial consumption; old cycle unchanged, new cycle starts at zero and gets its own ceiling; renewal inside the window, outside it (before and after) and with the grace boundary; non-renewal and expiry; mid-cycle upgrade, downgrade and member cancellation all rejected; admin refund-and-replace creates no loophole; idempotency and no double spending; the real invoice stays at full price with discount 0 while the hypothetical payable differs; redemption endpoint still refuses; reconciliation ties every record to its ledger rows.
