#!/usr/bin/env python3
"""Read-only Roadie supervision snapshot. No ADB, restarts or database writes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

HEARTBEAT = Path.home() / "Downloads/roadie_logs_nosleepy_economy/_tmp/watcher_heartbeat.json"
WATCHER_NAME = "roadie_watcher_with_destinations.py"
SUPERVISOR_NAME = "roadie_test_watchdog.py"


def process_rows():
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        capture_output=True, text=True, timeout=10, check=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, ppid, command = parts
        if not (pid.isdigit() and ppid.isdigit()):
            continue
        # Exclude this diagnostic command and incidental grep-like strings.
        if not ("python" in command.lower() and
                (WATCHER_NAME in command or SUPERVISOR_NAME in command)):
            continue
        rows.append({"pid": int(pid), "ppid": int(ppid),
                     "role": "watcher" if WATCHER_NAME in command else "watchdog"})
    return rows


def heartbeat_snapshot(path=HEARTBEAT, now=None):
    now = time.time() if now is None else now
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        timestamp = float(value["timestamp"])
        pid = int(value["pid"])
        if not 0 < timestamp <= now + 30 or pid <= 0:
            raise ValueError("invalid heartbeat values")
        return {"pid": pid, "age_seconds": round(max(0, now - timestamp), 1),
                "state": str(value.get("state", "UNKNOWN"))}
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"error": type(exc).__name__}


def snapshot(rows, heartbeat, stale_seconds=60):
    watcher_pids = {r["pid"] for r in rows if r["role"] == "watcher"}
    watchdog_pids = {r["pid"] for r in rows if r["role"] == "watchdog"}
    hb_pid = heartbeat.get("pid")
    return {
        "watcher_pids": sorted(watcher_pids),
        "watchdog_pids": sorted(watchdog_pids),
        "heartbeat": heartbeat,
        "heartbeat_matches_running_watcher": hb_pid in watcher_pids,
        "heartbeat_stale": heartbeat.get("age_seconds", float("inf")) > stale_seconds,
        "supervision_present": bool(watchdog_pids),
        "note": "A fresh heartbeat does not prove successful gig processing or Android app health.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", type=Path, default=HEARTBEAT)
    parser.add_argument("--stale-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        rows = process_rows()
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": f"process listing unavailable: {type(exc).__name__}"}))
        return 2
    print(json.dumps(snapshot(rows, heartbeat_snapshot(args.heartbeat),
                              args.stale_seconds), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
