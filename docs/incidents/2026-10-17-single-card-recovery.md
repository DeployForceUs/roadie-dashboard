# Incident Report: Single-Card Navigation Lockup & Repeated Details Prevention

Date: October 17, 2026  
Status: **NOT DEPLOYED** (Checkpoint commit created, awaiting operator deployment approval)  
Target Branch: `fix/single-card-recovery-20261017`  
Baseline Branch: `feature/roadie-periodic-recovery-20261014`  
Baseline Commit SHA: `261a9a5bf6a3f78a06a5c925c67a23de34f8d427`  
Production Process State: **UNTOUCHED / RUNNING** (Watcher, Supervisor, Publisher running on NZMAC)  
Production Execution Baseline: **UNKNOWN** (Production processes were started prior to this checkpoint; Git HEAD cannot be assumed identical to in-memory runtime)

---

## A. Incident Description

### Overview
In the Roadie Android application (Jetpack Compose UI update), tapping a direct single-gig map marker opened the gig card overlay, but the watcher repeatedly failed to return to the map. The opened single gig card remained stuck on screen while the watcher continuously tapped the same marker coordinate, which directly hit the "Details" button or card body, resulting in an infinite loop of Details reopening and zero map progression.

### Incident Gig
- **Gig Marker ID**: `76907987`
- **Coordinates**: `(892, 1290)`, Bounds: `[806,1204][978,1376]`
- **Real XML Fixture Captured**: `tests/fixtures/76907987_summary.xml`

### Timeline and Observed Symptoms (from `supervisor.log`)
```
[13:11:57] 👉 open gig 76907987 at (892,1290)
[13:12:00] 📄 verified fresh XML: 76907987_summary.xml (map)
[13:12:06] ids(6..9 digits, desc)   : 2 [('76907987', '[806,1204][978,1376]'), ('76907987', '[806,1204][978,1376]')]
[13:12:06] 👉 open gig 76907987 at (892,1290)
[13:12:09] 📄 verified fresh XML: 76907987_summary.xml (map)
[13:12:14] ids(6..9 digits, desc)   : 2 [('76907987', '[806,1204][978,1376]'), ('76907987', '[806,1204][978,1376]')]
[13:12:14] 👉 open gig 76907987 at (892,1290)
[13:12:18] 📄 verified fresh XML: 76907987_summary.xml (map)
[13:12:23] ids(6..9 digits, desc)   : 2 [('76907987', '[806,1204][978,1376]'), ('76907987', '[806,1204][978,1376]')]
[13:12:23] 👉 open gig 76907987 at (892,1290)
```
Every 6 to 8 seconds, the watcher attempted to re-open marker `76907987` because the previous card overlay was never closed.

---

## B. Root Causes

1. **Compose Resource IDs Not Recognized by UI Guard**:
   Recent Roadie Compose layouts represent single gig cards using `gig_card_pager` with children `gig_summary` or `gig_card`. Previous `classify_xml()` only recognized `position_in_stack` or `gig_summary_card`.
2. **False `Screen.MAP` Classification on Open Card**:
   Because `fragment_map_mapview` and `"Google Map"` remain mounted in the view hierarchy directly behind the card overlay, any unrecognized card layout fell through to `Screen.MAP`. As a result, `76907987_summary.xml` was logged as `(map)`.
3. **Missing `position_in_stack` on Single Gigs**:
   Single gig cards do not display a stack counter (`"1 OF N"`). `roadie_store.fields()` relied on `position_in_stack`, so it failed to identify the card position or parse fields.
4. **Early Loop Exits Skipping `back()`**:
   Inside `for e in new_ids:`, whenever `summary_screen is not Screen.CAROUSEL` or `dump_xml_checked()` failed, the loop executed `break`. This completely bypassed `back()` and `time.sleep(SLEEP_AFTER_BACK)`, leaving the card overlay open on screen.
5. **`recover_to_map()` Accepted False MAP**:
   At the start of the next cycle, `recover_to_map()` inspected the probe XML. Because `classify_xml()` returned `Screen.MAP`, it assumed the app was already on the map and did not press Back.
6. **Cluster Carousel Shrinkage**:
   When a cluster shrank from multiple gigs to a single gig, `wait_pos()` returned `None`, leaving the cluster branch without handling the remaining single card.

---

## C. Implemented Fixes

### 1. `roadie_ui_guard.py`
- Added `is_card_overlay_present(xml_text)`: explicitly checks whether `gig_card_pager` or `{"close_details", "details_container_scroll"}` is present.
- Updated `classify_xml(xml_text)`:
  - Recognizes `gig_card_pager` with Compose markers (`gig_summary`, `gig_card`, `gig_summary_card`, `position_in_stack`) as `Screen.CAROUSEL`.
  - Bare pager in transition fails closed to `Screen.UNKNOWN`.
  - Conflicting markers (card overlay coexisting with map controls or detail markers) fail closed to `Screen.UNKNOWN`.
  - Open cards never fall through to `Screen.MAP`.

### 2. `roadie_store.py`
- In `fields(nodes)`, added support for Compose markers: synthesizes `(summaries[0], 1, 1)` for `("gig_summary_card", "gig_summary", "gig_card")`.
- Supported Compose price formats: matches `consolidation_price`, `dollar_amount`, `price`, and `$`-prefixed prices (`$XX.XX`).
- Preserved existing route-time parser fix (`X hr Y min` -> `hours * 60 + mins`).

### 3. `roadie_watcher_with_destinations.py`
- Added `is_genuine_map_screen(path)`: validates `classify_xml(...) is Screen.MAP` **and** `not is_card_overlay_present(...)`.
- Enforced `is_genuine_map_screen(start_tmp)` in `main()`: blocks any marker scanning or tapping if a card overlay is detected on the map.
- Rewrote the single gig processing loop (`for e in new_ids:`):
  - Wrapped marker processing in `try: ... finally:`.
  - Guaranteed execution of `back()`, `time.sleep(SLEEP_AFTER_BACK)`, and `recover_to_map()`.
  - If map restoration fails, sets `map_needs_rescan = True` and breaks out of the loop immediately.
- Updated `open_destination_if_needed()`: candidate selection and return verification recognize Compose single-card markers (`gig_summary`, `gig_card`, `gig_summary_card`).
- Fixed cluster branch for shrunk carousels: when `wait_pos()` returns `None` and a single card is present, processes the card and verifies map restoration via `recover_to_map()`.
- Added `direct_marker_retry_after` 120-second cooldown on unexpected screens.
- Refactored file reads to context managers (`with open(...)`) to eliminate `ResourceWarning` leaks.

---

## D. Safety Mechanisms

1. **Fresh XML Verification After Every Back Action**:
   Every navigation step verifies fresh XML before proceeding.
2. **Bounded Map Recovery (`recover_to_map(max_attempts=5)`)**:
   Checks probe XML on each attempt. Presses Back only on positively verified `CAROUSEL`, `DETAIL`, or card overlays. Terminates with `False` after at most 5 attempts to prevent infinite loops.
3. **Strict Gate Before Marker Tapping**:
   If `is_genuine_map_screen()` is False, the watcher skips marker detection and avoids tapping.
4. **Fail-Closed on Ambiguity**:
   Any conflicting or unknown screen returns `Screen.UNKNOWN`, blocking speculative taps or swipes.
5. **120-Second Direct Marker Cooldown**:
   Failing direct markers are throttled for 120 seconds (`DIRECT_MARKER_RETRY_SECONDS`), preventing rapid repeated taps.

---

## E. Regression Tests

1. **`test_single_card_classifier.py`**:
   - Single card Compose markers (`gig_summary`, `gig_card`, `gig_summary_card`) -> `Screen.CAROUSEL`.
   - Bare `gig_card_pager` -> `Screen.UNKNOWN`.
   - Real fixture `76907987_summary.xml` -> `Screen.CAROUSEL` and `is_card_overlay_present == True`.
   - Conflicting markers fail closed.
2. **`tests/test_single_card_regression.py`** (New suite, 12 tests):
   - Screen classification & genuine map validation.
   - `roadie_store` parsing for single Compose cards and `X hr Y min` route formats.
   - Bounded recovery tests for `Screen.MAP`, `Screen.CAROUSEL`, and `Screen.DETAIL`.
   - **Repeated Details bug simulation**: verifies bounded recovery terminates at `max_attempts` and halts marker tapping when card fails to close.
   - Guarantee that `finally` block runs cleanup on errors/early exits.
3. **Fixture**:
   - `tests/fixtures/76907987_summary.xml`: Real XML from incident gig 76907987.

---

## F. Test Results

- `python3 -m unittest discover -s tests -p "test_*.py"`: **64 / 64 PASS**
- `python3 test_single_card_classifier.py`: **8 / 8 PASS**
- Python AST syntax checks (`ast.parse`): **PASS** across all modified files
- Unrelated working tree changes (`publish.py`): **UNTOUCHED / PRESERVED**

---

## G. Rollback Instructions

> [!IMPORTANT]
> Rollback requires an explicitly authorized procedure and must never be executed blindly while production processes are active.

1. **Previous Baseline Commit**:
   `261a9a5bf6a3f78a06a5c925c67a23de34f8d427`
2. **New Checkpoint Commit**:
   See `git rev-parse HEAD` on branch `fix/single-card-recovery-20261017`.
3. **File Restoration Command** (if needed during authorized rollback):
   ```bash
   git checkout 261a9a5bf6a3f78a06a5c925c67a23de34f8d427 -- roadie_ui_guard.py roadie_store.py roadie_watcher_with_destinations.py test_single_card_classifier.py
   ```
4. **Do NOT execute rollback without explicit operator approval.**

---

## H. Deployment Status

- **Status**: **NOT DEPLOYED**
- **Production Processes**: Untouched and running.
- **Next Steps**: Awaiting operator decision and approval before deploying to `~/roadie-watcher-test` or restarting Watcher.
