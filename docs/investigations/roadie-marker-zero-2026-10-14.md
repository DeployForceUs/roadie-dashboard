# Roadie Watcher — investigation checkpoint (2026-10-14)

Status: **OPEN / investigation paused; no production code changes authorized.**

## Symptom observed by driver
On Oct 13, Roadie map repeatedly refreshed: the Refresh icon visibly spun, confirming the app reacted to the refresh tap. A circular map marker remained, but no gig card/carousel opened. When a marker is actually tapped manually, a card normally opens almost immediately. No screenshots from the incident are available.

## Roadie marker semantics (driver's confirmed observations)
- Number-only circle (1, 2, 3, 4, 5+, etc.) = cluster/carousel.
- Number plus abbreviated miles = single gig.
- An internal numeric gig ID is not the map marker label.
- Empty map has **no circular markers at all**. Do not characterize '0' as a normal empty-cluster marker without evidence.

## Evidence
- Local logs: `~/Downloads/roadie_logs_nosleepy_economy/`, session folders with `start.xml` and `carousel_01.xml`.
- 674 `start.xml` files examined with a numeric `content-desc="0"`; their set of numeric descriptions was exactly `('0',)`. This **does not** mean 674 distinct gigs or 674 missed orders.
- At least one `0` sample dates back to **2026-10-12 13:12:59**, not just Oct 13.
- Oct 13 `0` occupied three stable XML bounds during different periods: `[584,1431][756,1603]`, `[854,1160][1026,1332]`, `[703,1258][875,1430]`. Supervisor restarts/repositions app, explaining coordinate changes; do not re-investigate restarts as a new discovery.
- Example `start.xml` and post-tap `carousel_01.xml` at `2026-10-13_14-33-07.82` both retained Google Map and `0` at `[703,1258][875,1430]`; no carousel position. No verified card opening.
- Oct 14 independently captured true empty map XML contained `Google Map` but **no** `0`.
- `0` sample node: `class="android.view.View" content-desc="0" clickable="true" enabled="true" bounds="[428,1505][600,1677]"` (Oct 12).
- Historical numeric cluster samples (1 through 96, from Jul/Aug 2025) had same `android.view.View` class and generally 172x172 bounds, but `clickable="false"`. This is a **difference in the samples**, not proof of meaning or tap behavior; note historical app version may differ.

## Code verified (local path)
`~/roadie-memory-supervisor/roadie_watcher_with_destinations.py`
- `debug_detect` classifies numeric descriptions 0..99 as clusters; 6..9-digit descriptions as single IDs.
- Cluster path around lines 679–769: calculate center from XML bounds, `tap(cx,cy)`, sleep `SLEEP_AFTER_TAP=1.0`, dump detail XML, copy as `carousel_01.xml`, call `wait_pos`. If no verified carousel: log `no verified carousel after tap`, request map rescan, defer singles that cycle.
- `tap` invokes `adb("shell input tap x y")`. `adb` uses `subprocess.run(..., shell=True, stdout=PIPE, stderr=STDOUT)` but does **not** check `returncode`; `tap DONE` alone does not confirm success.
- `wait_pos(xml_path)` repeatedly parses **the same saved XML file**, without redumping UI between attempts. This is a diagnostic/late-opening limitation, but user observes normal cards open almost immediately.
- Refresh is also `tap`; observed refresh spinner makes total ADB failure less plausible, though does not establish cluster-tap success.
- Singles have revisit/retry logic (e.g. `MARKER_REVISIT_SECONDS=120`), but **do not infer `0` was a remembered single ID**: code treats it as cluster.

## What remains unknown
1. What was **visually drawn** for `content-desc="0"`? No screenshots; historical XML alone cannot conclusively reconstruct appearance.
2. Was `0` ever successfully opened in earlier saved sessions? Search paired `start.xml` / `carousel_01.xml` across dates and compare carousel positions.
3. Why did the `0` tap not open a card: failed ADB input, nonresponsive/stale map element, app state, or other reason? **Not established.**
4. Is `clickable=true` vs `false` relevant, or simply an app-version difference?

## Next session — minimal plan
1. Search historical `0` sessions for **successful post-tap carousel**, compare with successful numeric-cluster sessions and timestamps.
2. Inspect evidence only; avoid circling back to refresh, supervisor restarts, or generic timing theories.
3. If still inconclusive, with explicit permission add screenshot capture **only on unsuccessful marker opening**, plus ADB return code/error logging. No behavior changes without approval.

**No code, processes, or device state modified as part of this checkpoint.**
