# Roadie project handoff — read first

Repository: DeployForceUs/roadie-dashboard. Read docs/WATCHER_STATE.md and CHANGELOG.md before changing any code.

## Operating rules
- Communicate with the operator in Russian; keep commands concise, safe for Termius/macOS.
- Do not invent successful tests, running processes, or Git state. Distinguish tested from untested.
- Do not use `set -e` or `exit` in terminal snippets; never risk closing the user's SSH session.
- Do not stop/restart/modify the separate Publisher (`publish.py`), Watchdog, or production database without explicit permission.
- The operator uses Mac NZMAC, Android Roadie via ADB, and `~/roadie-watcher-test` as local checkout.
- Prefer a single main branch and monotonically numbered `watch-v1.0.x` releases. A historical fix branch currently contains unmerged changes; do not claim they are on main.
- Fail closed on unknown Android screens; never blind-tap or swipe without verified screen/position.
- When updating Mac checkout, verify commit SHA explicitly; `git fetch` alone does not update working files.
- Current state and actual test results: docs/WATCHER_STATE.md.
