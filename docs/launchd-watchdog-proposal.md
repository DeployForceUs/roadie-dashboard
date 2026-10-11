# macOS launchd: supervised Roadie test watcher

**Status: proposed, not installed.** This document does not authorize launching,
restarting, or modifying any running production process.

## Design

A per-user LaunchAgent owns exactly one instance of `roadie_test_watchdog.py`.
The watchdog in turn owns the watcher subprocess it starts. Closing Terminal
does not stop a process managed by launchd.

Safety choices:
- `KeepAlive=false`: when watchdog exits after its restart budget is exhausted,
  launchd **must not** immediately restart it and erase the budget.
- `RunAtLoad=true`: once the operator explicitly installs and loads the agent,
  it starts at login. This is *not* enabled merely by checking out the repository.
- No `StartInterval` or `StartCalendarInterval`: no automatic resurrection.
- Separate test-specific label, working directory, and logs.
- Never enable while another watcher/watchdog instance is running.
- ADB connectivity, app OOM and Android UI state are *not* fixed by launchd.

## Proposed plist (template, do not load as-is)

Save as `~/Library/LaunchAgents/us.deployforce.roadie-test-watchdog.plist`
only after replacing both placeholders with the **actual** Mac username and
absolute Python interpreter path. Verify that the interpreter has the
required modules and ADB available on launchd's PATH. Prefer an explicit
`PATH` matching the validated environment.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>us.deployforce.roadie-test-watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>__ABSOLUTE_PYTHON_PATH__</string>
    <string>-u</string>
    <string>/Users/__MAC_USERNAME__/roadie-watcher-test/roadie_test_watchdog.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/__MAC_USERNAME__/roadie-watcher-test</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key>
  <string>/Users/__MAC_USERNAME__/Library/Logs/roadie-test-watchdog.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/__MAC_USERNAME__/Library/Logs/roadie-test-watchdog.err.log</string>
</dict>
</plist>
```

## Read-only preflight before any operator-approved installation

```bash
command -v python3
command -v adb
pgrep -af 'roadie_watcher_with_destinations.py|roadie_test_watchdog.py'
plutil -lint ~/Library/LaunchAgents/us.deployforce.roadie-test-watchdog.plist
```

Note: `pgrep -af` syntax/behavior varies by platform; on macOS, use
`ps -axo pid,ppid,command | grep -E '[r]oadie_watcher_with_destinations|[r]oadie_test_watchdog'`
if needed.

## Operator approval gate

Before enabling: verify test-vs-production paths, whether an existing supervisor
is active, which Android device ADB targets, the correct interpreter and PATH,
log destinations, and explicit permission to start the test watcher.

A normal watchdog stop (including restart budget exhaustion) will **stay
stopped** until manually started again or the next login load. This preserves
the budget within a session, but a new login resets the in-memory history.
A future revision should persist restart budget state if unattended operation
across logins is required.

## Known limitations

- The existing heartbeat can be fresh even without meaningful gig processing.
- The watchdog's 60-second default staleness threshold may be too aggressive
  for slow ADB/UI captures; measure before deployment.
- The watchdog does not currently distinguish Android app OOM from watcher stall.
- A launcher does not address Android Java heap OOM.
- No automatic recovery has been deployed or tested by this document.
