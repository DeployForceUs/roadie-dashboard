# Roadie Watcher — operational state and handoff
Updated 2026-10-11, after ~17:00 ET. This is the canonical handoff; keep it current with every material debugging discovery.

## System and repo
- GitHub: `DeployForceUs/roadie-dashboard`, existing fix branch `fix/single-marker-carousel-cooldown`.
- Mac: NZMAC, working checkout `~/roadie-watcher-test`, local branch `test/supervision-diagnostics`. Last **confirmed** checkout update was commit `58be45a`, via explicit SHA fetch + fast-forward merge. Do not assume future GitHub commits are present on Mac.
- Main Python files: `roadie_watcher_with_destinations.py`, `roadie_store.py`, `roadie_ui_guard.py`, `roadie_capture.py`. Publisher `publish.py` is separate; do not touch.
- Operator wants one main branch and release tags `watch-v1.0.0` (baseline), `watch-v1.0.1` (fix), rather than ongoing branch sprawl. **Not completed**. Avoid claiming main contains these fixes.
- Watchdog was stopped before live trial; live Watcher was launched in foreground at 16:59:48. Operator reported it resumed after manually refreshing Roadie UI; **current process status not independently verified**. Do not restart another copy blindly.

## Observed single-card XML
File on Mac: `~/Downloads/roadie_logs_nosleepy_economy/_tmp/rejected_xml/76510555_detail_758f7017f64a.xml`.
- Map marker `content-desc="76510555"` and `gig_card_pager` / `gig_summary_card` / `gig_card` are present together.
- `position_in_stack` **absent**. First visible card says AVAILABLE GIG, sender ROADIEXD, price 150.30, 76 mi (190 min), 11 deliveries, EASY FIT FOR FORD MUSTANG MACH-E.
- Internal `gig_key` is `76_11` (displayed miles + delivery count), **not** Roadie marker ID `76510555`.
- Prior classifier demanded `gig_card_pager` AND `position_in_stack`, so rejected this real summary as UNKNOWN.
- Parser `fields(nodes)` previously depended entirely on position counter; now synthesizes position 1/total 1 when exactly one `gig_summary_card` tuple exists. Important limitation: `parse()` discards bounds, so visibility cannot be proven inside `fields()` alone. Do not claim otherwise.

## Intended behavior
1. Tap a verified map marker/cluster.
2. Capture and process **first** visible AVAILABLE GIG summary immediately; never skip first card.
3. Use `gigs.destination` lookup by `gig_key` to open Details only if destination unknown; on return, verify same card/key.
4. If verified `position_in_stack` says `N>1`, swipe only through remaining verified positions; abort/rescan if total changes. If no verified counter, **no speculative swipe**.
5. Do not publish incomplete/ambiguous snapshots or act on UNKNOWN screen.
6. Preserve existing cluster handling and `direct_gig_details` behavior where required. **Regression risk**: new direct-marker implementation may no longer populate `direct_gig_details`; audit before declaring done.

## Actual tests
- Initial test against old Mac commit `ed791b3` returned UNKNOWN and empty cards. Git `origin/fix/... ` had also appeared as `ed791b3`; explicit fetch by commit SHA and fast-forward merge was required.
- First updated parser failed with `NameError: name 'path' is not defined`. Fixed in GitHub commit `58be45a`; Mac fetched/merged it.
- Real XML passed: `Screen.CAROUSEL`; `POSITIONS: [(24,1,1)]`; `CARDS: {1: {'key':'76_11','miles':'76','minutes':190,'deliveries':11,'price':'150.30','fit':'EASY FIT FOR FORD MUSTANG MACH-E','position':1,'total':1}}`.
- Independent in-memory SQLite rule test passed for unknown/known destination and no swipe. This was **not** a call to Watcher's actual function.
- Live run: at 16:59:50 the initial summary was recognized as CAROUSEL and Watcher pressed Back. Afterwards several `screen_probe` captures rejected as UNKNOWN; operator saw blank Roadie map with missing Refresh. Switching away/back and moving map restored UI and Watcher resumed. No direct gig tested yet.
- Rejected empty-map XML examples: `_tmp/rejected_xml/screen_probe_7d38ed304dd2.xml`, `screen_probe_91721fdf5327.xml`. Inspect before changing MAP classifier. Never loosen guard merely because map looks empty.

## Important known risks and next actions
- **Top priority**: observe next live direct single gig and verify actual capture, DB lookup, Details behavior, Back and recovery.
- Investigate missing Refresh button after Back: classify only with reliable XML evidence; possible transient Roadie UI state. Do not add blind taps.
- Check multi-card swipe loop on real cluster; ensure first card is processed and total changes abort safely.
- Audit `open_destination_if_needed` for handling of no-counter single summaries, including post-Details verification.
- Audit `record_cards_if_complete()` and whether synthetic 1/1 might accidentally mark a multi-card carousel complete when counter absent; fail-closed on ambiguity.
- Audit `direct_gig_details` regression, duplicated keys, and the exact code path used by single markers.
- Commit any future fixes to the canonical repo, then merge to main only after testing and explicit operator agreement. Tag releases only when actually created.
- Keep publisher, database and watchdog untouched unless explicitly authorized.

## Safety / user preferences
- Commands for Termius must not contain `exit` or `set -e`.
- No premature restarts, no unverified success claims, no random branch proliferation.
- Keep responses short, practical, Russian. Preserve exact SHA when guiding `git fetch` and `git merge --ff-only`.
