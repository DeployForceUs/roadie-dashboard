# Roadie Radar — Price Dynamics & Disappearance Research Plan

**Date:** 2026-10-14  
**Status:** Research plan / hypotheses, not implementation authorization  
**Scope:** Roadie Watcher → SQLite → Publisher → Dashboard. Preserve current running processes.

## 1. Objective

Build empirical statistics on how Roadie gig offers change price while visible and on the *last observed price before an offer ceases to be visible*. Investigate whether long-visible ("stale") gigs are more likely to receive increases and how observed offer disappearance relates to payout, age, time of day, distance, deliveries, and cargo characteristics.

**Crucial distinction:** last observed price is measured; actual driver acceptance, clearing price, and Roadie's motivation for increases are **not** directly observed. Disappearance is a proxy/hypothesis, not proof of acceptance.

## 2. What is implemented today

- Watcher writes observed gig snapshots and `PRICE_CHANGED` events to SQLite `changes` (`seen_at`, `gig_key`, `event`, `old_price`, `new_price`).
- Publisher emits bounded `price_history` (last 3,000 price-change event rows, grouped by gig key) into public `data.json`; it does **not** export the entire SQLite event history.
- Dashboard `Price History` shows only keys with at least two observations and at least two distinct prices; click a key to see observed price steps and a chart.
- Existing Now and History views remain separate; History does not establish present availability.
- Avoid modifying or restarting Watcher/Supervisor solely for research.

## 3. Initial observed examples (2026-10-14)

| Key | First observed price | Later observed price | Increase | Notes |
|---|---:|---:|---:|---|
| `47_75` | $168.94 at 11:48:52 | $172.30 at 12:20:58 | +$3.36 / +1.99% | Five price observations in initial SQLite query |
| `47_75` | $168.94 | $177.62 (later dashboard) | +$8.68 / +5.14% | Six observations reported by dashboard |
| `71_25` | $87.67 inferred from displayed delta | $99.10 | +$11.43 | Dashboard screenshot; verify original event data |
| `31_2` | $24.87 inferred from displayed delta | $36.36 | +$11.49 | Two observations; verify source |
| `68_1` | $38.39 inferred from displayed delta | $40.83 | +$2.44 | Two observations; verify source |

`47_75` initial price observations:
- 11:48:52 $168.94 (old_price null; first *observed* price, not necessarily original offer)
- 11:51:04 $169.21 (+$0.27)
- 12:05:54 $169.88 (+$0.67)
- 12:10:42 $170.66 (+$0.78)
- 12:20:58 $172.30 (+$1.64)

Timestamps indicate *detection time*, not the exact instant Roadie changed the offer. No example above establishes actual acceptance.

## 4. Research questions / hypotheses

1. **Time to first increase:** elapsed time from first confirmed sighting to first *distinct* price. First sighting may be later than actual posting.
2. **Increase cadence:** intervals between detected changes; variation by gig class, hour, day of week, geographic market.
3. **Increase size:** absolute $, percentage, step-size distribution; accelerating/decelerating sequences; occasional reductions/resets.
4. **Offer age:** relationship between elapsed observed time, repeated visibility, and price increases. Do not equate "stale" with confirmed unaccepted.
5. **Gig characteristics:** deliveries/stops, route miles, estimated minutes, destination, item count, weight, largest dimension, fit class, XD vs other types *only when reliably identifiable*.
6. **Disappearance proxy:** last observed payout, total increase, and time from first to last observation for gigs no longer observed after sufficiently reliable scans. Compare groups and censor uncertain cases.
7. **Temporal patterns:** morning/afternoon/evening, weekdays vs weekends; look for systematic shifts after 3 PM.
8. **Predictive modeling (later):** conditional likelihood of an additional price rise within a window, with confidence/uncertainty and holdout evaluation. Never present estimates as guaranteed or as proof of a Roadie policy.
9. **Decision support (later):** empirical tradeoff of taking a gig now vs waiting for possible increases; waiting risks the offer disappearing.

## 5. Measurement and data-quality rules

- Distinguish **first seen**, **last seen**, **first observed price**, **last observed price**, and **last detected change**.
- An initial `PRICE_CHANGED` row with `old_price=NULL` is a baseline, **not** evidence of an increase.
- At least two distinct observed prices are required to count a gig as price-changed. Two observations are sufficient if distinct; six identical observations are not.
- Preserve each step and timestamp; do not assume equal sampling intervals.
- `gig_key` such as `47_75` may be a derived composite (e.g. miles/deliveries) rather than a stable Roadie offer ID. **Audit key generation and collision/reuse** before treating all rows sharing a key as the same physical gig.
- Account for map clusters, carousel starvation, map-only/partial scans, stale XML, ADB disconnects, UI state errors, watcher/supervisor restarts, and gaps in collection. An empty scan is not automatically proof of no available gigs.
- Visibility may depend on account, vehicle, location, Roadie targeting, filters, and other unknown factors.
- `last_price` before a disappearance is an *upper/lower?* **neither** bound on a transaction price unless additional evidence exists; a later unseen increase may have occurred.
- Do not treat disappearance as accepted/completed/sold; competing causes include cancellation, expiry, visibility filtering, temporary scanning gaps, or assignment to another driver.
- Record scan coverage and confidence when feasible; distinguish an observed absence from an absence of observation.
- Avoid exposing sensitive location/account data in public `data.json`; aggregate/anonymize outputs.

## 6. Proposed derived metrics (no new states yet)

Per key (subject to identity validation):
- `first_seen_at`, `last_seen_at`, `first_observed_price`, `last_observed_price`
- `observed_duration_minutes` = last_seen - first_seen (not true posting lifetime)
- `price_change_count` = number of actual distinct successive changes
- `total_delta_usd`, `total_delta_pct`
- `time_to_first_detected_increase_minutes`
- `inter_increase_intervals_minutes` and `increment_usd` series
- `last_confirmed_visible_at`, `next_reliable_scan_at`, `observation_gap_minutes` where available
- `coverage_quality` and `disappearance_evidence` as **analytical annotations only**, not Watcher lifecycle statuses

Group statistics:
- Median and quantiles (not just mean) for delay, increase magnitude, change count and observed duration.
- Counts/denominators, missing-data rates, time-window coverage, and uncertainty intervals.
- Segment by order features, local time and day, with sample-size thresholds.

## 7. Explicitly deferred / undecided

- **No new operational gig statuses** such as `MISSING_UNCONFIRMED` or `DISAPPEARED_CONFIRMED` at this stage. The user questions whether these are justified or useful.
- No assertion that the last seen price "found a buyer."
- No changes to Watcher scanning logic, Supervisor recovery logic, live database schema, or Publisher process merely to add speculative statuses.
- No inference of exact acceptance time from last_seen.
- No auto-accept or trade/action recommendations based on weak correlations.

## 8. Phased roadmap

**Phase A — Observe (now):**
Keep existing collector and price-history UI running. Preserve SQLite backups and logs. Accumulate days/weeks of coverage. Avoid changing collection behavior for the sake of a hypothesis.

**Phase B — Data audit:**
Validate gig identity/key collisions, event ordering, repeated values, timestamp/timezone normalization, gaps, restarts, cluster coverage, and retention. Determine whether price events can be safely joined to gig details and map scans. Audit first/last seen semantics.

**Phase C — Offline exploratory report:**
Read SQLite read-only. Produce price-increase frequencies, delays, step distributions, gig-type comparisons, hourly/day-of-week patterns, and a cohort of last-observed-price-before-disappearance cases with explicit caveats. Separate price-changing vs non-price-changing gigs to avoid selection bias. Compare yesterday vs today and after-3-PM cohorts.

**Phase D — Disappearance study:**
Develop a *measurement definition* for reliably unobserved gigs using scan coverage/gaps; test false positives against gigs that reappear. Keep this as an analytical model without adding runtime states unless evidence and operational need warrant it. Consider right-censoring for gigs still visible or monitoring interrupted.

**Phase E — Optional dashboard analytics:**
Add aggregate charts and drill-downs (increase rate, median lag, observed last price, price vs duration), quality badges only when evidence-backed, and exportable anonymized research summaries. Prefer precomputed aggregates if full histories exceed current bounded JSON.

**Phase F — Forecasting only after validation:**
Train and evaluate on held-out days; report calibration, confidence, failure modes and risk of disappearing offers. Do not confuse correlations with causal Roadie pricing policy.

## 9. Next review checklist

- [ ] Audit `gig_key` derivation and collision rate.
- [ ] Verify SQLite schema, timestamp timezone, and price event semantics.
- [ ] Establish collector uptime and map coverage metrics.
- [ ] Count gigs with 0, 1, 2+ genuine price increases (including non-increasers).
- [ ] Examine examples `47_75`, `71_25`, `31_2`, `68_1` against raw DB.
- [ ] Check disappearance/reappearance cases before using any acceptance proxy.
- [ ] Define data retention/backup policy; Publisher currently exports only 3,000 recent event rows.
- [ ] Produce first offline report after sufficient observations.

## 10. Decision record

**2026-10-14:** Proceed with observational research and dashboard price-change filtering. Preserve the disappearance/last-price hypothesis. **Do not add new gig lifecycle statuses now.** Treat any future status design as a separate decision requiring evidence.
