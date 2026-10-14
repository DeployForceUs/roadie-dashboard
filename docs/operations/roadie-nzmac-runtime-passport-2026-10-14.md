# Roadie NZMAC runtime passport — 2026-10-14

## Scope and provenance
Observed from live `ps` and `lsof` output supplied on 2026-10-14, and source code on branch `feature/roadie-periodic-recovery-20261014`. PIDs are snapshots, not permanent identifiers. **No passwords, tokens, or credentials stored here.** Runtime state may change; always recheck before acting.

## Repository and host
- GitHub: `DeployForceUs/roadie-dashboard`
- Runtime/source branch: `feature/roadie-periodic-recovery-20261014`, last locally confirmed commit `746554d093b6bdb8f1ac4a44bfd3ee59d922ecc4`.
- Mac host: `NZMAC`; account: `dmitriikarpov`.
- Working directory: `/Users/dmitriikarpov/roadie-memory-supervisor`.
- Android package: `com.roadie.drive.android.app`; activity: `com.roadie.drive.android.app/.home.HomeActivity`.
- Android connected through ADB; watcher collects Android UI XML.
- Main DB read by Publisher: `/Users/dmitriikarpov/Downloads/roadie_gigs.sqlite3`.
- Watcher XML sessions observed under `/Users/dmitriikarpov/Downloads/roadie_logs_nosleepy_economy/`.

## Confirmed running processes (2026-10-14, ~12:08 local)
| Component | PID | Parent | Runtime command / role |
|---|---:|---:|---|
| Memory Supervisor | 76253 | 512 | `python -u roadie_memory_supervisor.py --package com.roadie.drive.android.app --activity com.roadie.drive.android.app/.home.HomeActivity --pss-limit-mib 700 --periodic-restart-minutes 90 --confirm-live` |
| Watcher | 76258 | 76253 | `python -u /Users/dmitriikarpov/roadie-memory-supervisor/roadie_watcher_with_destinations.py` |
| Publisher | 53898 | 53796 | `python -u -c 'import fcntl,os,runpy; f=open("/tmp/roadie-publisher.lock","w"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB); print("Publisher lock acquired",flush=True); runpy.run_path("publish.py",run_name="__main__")'` |
| Log viewer (not a service) | 76630 | 13815 | `tail -n 30 -f /Users/dmitriikarpov/roadie-memory-supervisor/supervisor.log` |

Publisher cwd confirmed with `lsof -a -p 53898 -d cwd,1,2` as `/Users/dmitriikarpov/roadie-memory-supervisor`. Its stdout/stderr were attached to `/dev/ttys006`, **not** supervisor.log. Its process existed for ~1 day 10 hours at observation, but **successful recent GitHub publishing was not yet verified**.

## Supervisor functionality (verified from source)
- Starts Watcher as its child and keeps an exclusive `.roadie_memory_supervisor.lock`; refuses startup if another Watcher already exists.
- Every 10 seconds checks Watcher liveness, heartbeat, Android app process, and Android app total PSS memory.
- Triggers recovery when PSS >=700 MiB on three consecutive checks; Roadie Android process absent for two checks; Watcher exited; heartbeat stale >90s.
- Configured with `--periodic-restart-minutes 90`: after 90 minutes from child launch, attempts scheduled preventive recovery when its cycle-completion condition is met. **Not a guaranteed hard 90-minute timer**; if cycle boundary is not recognized, it waits, unless another failure triggers recovery.
- Recovery stops child Watcher, force-stops Android Roadie app, launches specified activity, verifies foreground, waits for UI settling, runs `~/bin/rmap` and ADB swipes to restore map, then starts a new Watcher. Failure to confirm recovery prevents watcher relaunch.
- Recovery has a restart budget (implementation in `roadie_test_watchdog.py`); exhausted budget stops supervisor.
- Does not accept gigs and does not intentionally reset the SQLite history or Publisher.
- **Known limitations:** periodic boundary detection depends on `progress_for` observing `CYCLE_DONE`; this may be missed or may not guarantee no in-progress UI work. No special rule for interesting gigs. No independent dedicated repair for absent Refresh button. These require separate testing.

## Watcher functionality (observed from live log)
- Collects verified fresh Android `uiautomator` XML; detects map direct IDs and clusters, opens cards/carousels, swipes, parses position and gig data, tracks duplicate entries and price changes, saves session files and history, returns to map and refreshes/rescans.
- Sample log: carousel `2 OF 4`, progress to `4/4`, `DUP -> skip`, `PRICE_CHANGED`, `cycle 6 done`.
- **Known issue under investigation:** cluster detection may identify marker text `0` as a cluster and tap it; this has been observed and is not by itself proof of a stale map. Prior investigation: `docs/investigations/roadie-marker-zero-2026-10-14.md`.

## Publisher functionality (verified from `publish.py` source)
- Independent of Supervisor/Watcher; holds nonblocking exclusive `/tmp/roadie-publisher.lock`.
- Every 60 seconds reads `~/Downloads/roadie_gigs.sqlite3` in read-only mode and constructs an anonymized `data.json` snapshot.
- Includes historical gigs (price, miles, time, destination, fit, cargo dimensions/weights where present), up to 250 change events, and best-effort current map data with explicit freshness/coverage status (`verified_carousel`, `partial_clusters`, `partial_details`, `map_direct_only`, `not_available`).
- Publishes via `gh api` to `DeployForceUs/roadie-dashboard` file `data.json` on the repository **default branch**, using current SHA. This is not necessarily the feature branch.
- Prints `HH:MM:SS published N history records` on success, `Publish error:` on failure; both currently go to `/dev/ttys006`. Publishing success/failure not yet verified by live output or latest commit timestamp.
- Publisher does not send Telegram messages directly in this file; any downstream Telegram integration needs separate verification.

## Logs, checks, and safe operating procedures
- Supervisor+Watcher combined log: `/Users/dmitriikarpov/roadie-memory-supervisor/supervisor.log`.
- Follow live: `tail -n 30 -f ~/roadie-memory-supervisor/supervisor.log`; Ctrl+C exits only the viewer.
- Recovery events: `grep 'RECOVERY:' ~/roadie-memory-supervisor/supervisor.log`. The current supervisor's `RECOVERY:` lines **do not include a built-in timestamp**; correlate with surrounding watcher timestamps or improve logging before asserting precise restart times.
- Process check: `ps -axo pid,ppid,etime,command | grep -Ei '[r]oadie|[p]ublisher|[p]ublish_github|[t]elegram'`.
- Publisher cwd/stdio: `lsof -a -p <publisher-PID> -d cwd,1,2`.
- To confirm publication: inspect publisher terminal output for `published`/`Publish error`, or inspect recent GitHub `data.json` commit / `generated_at` (and distinguish new content generation from successful remote update).
- Avoid launching a second Watcher or Publisher. Never remove lock files to bypass active locks. Preserve the running process until a controlled change is planned.

## Startup and recovery commands (reference; do not run if already active)
```bash
cd ~/roadie-memory-supervisor && nohup python3 -u roadie_memory_supervisor.py --package com.roadie.drive.android.app --activity com.roadie.drive.android.app/.home.HomeActivity --pss-limit-mib 700 --periodic-restart-minutes 90 --confirm-live >> supervisor.log 2>&1 < /dev/null &
```
The currently running Publisher command is documented above, but **do not rerun it** while PID 53898 or any successor owns the publisher lock.

## Open verification items
1. Confirm Publisher has successfully updated `data.json` recently; process existence alone is insufficient.
2. Check that 90-minute preventive recovery fires after a genuine safe cycle boundary, and records a durable timestamp.
3. Investigate zero cluster marker and map-without-Refresh behavior.
4. Verify how Publisher is started automatically after host reboot (if at all); no launchd configuration confirmed.
