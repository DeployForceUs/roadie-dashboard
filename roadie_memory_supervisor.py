#!/usr/bin/env python3
"""Opt-in Roadie collector supervisor: memory-triggered Android recovery.

Never accepts gigs. Preserves the SQLite history and publisher. Not enabled by default.
"""
import argparse
from collections import deque
import os
from pathlib import Path
import subprocess
import sys
import time

from roadie_memory_monitor import parse_meminfo
from roadie_test_watchdog import progress_for, stop_child, restart_budget_exhausted

BASE = Path(__file__).resolve().parent
WATCHER = BASE / "roadie_watcher_with_destinations.py"
# Verified map route. 'z' invokes the existing local rmap double-tap.
MOVES = [
    ("swipe", 140, 1500, 940, 700, 600),
    ("rmap", "g"), ("rmap", "h"), ("rmap", "t"),
    ("rmap", "g"), ("rmap", "t"), ("rmap", "g"),
    ("rmap", "f"), ("rmap", "g"),
    ("swipe", 540, 1200, 540, 600, 900),
    ("swipe", 440, 1100, 840, 1100, 600),
]

def run(*args, timeout=20):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout

def adb(*args, timeout=20):
    return run("adb", *args, timeout=timeout)

def memory_mib(package):
    info = parse_meminfo(adb("shell", "dumpsys", "meminfo", package))
    if info["pss_kib"] is None:
        raise ValueError("TOTAL PSS unavailable")
    return info["pss_kib"] / 1024

def ready(package, timeout=90):
    """Confirm the Roadie activity is actually resumed on screen."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = adb("shell", "dumpsys", "activity", "activities", timeout=12)
            resumed = [line for line in state.splitlines()
                       if "topResumedActivity=" in line or "mResumedActivity=" in line]
            if any(package in line for line in resumed):
                print("Roadie foreground confirmed", flush=True)
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(3)
    return False

def fix_map(rmap):
    if not Path(rmap).is_file():
        raise FileNotFoundError(rmap)
    for move in MOVES:
        if move[0] == "rmap":
            run(rmap, move[1], timeout=15)
        else:
            adb("shell", "input", move[0], *map(str, move[1:]), timeout=15)
        time.sleep(.4)

def recover(package, activity, rmap):
    adb("shell", "am", "force-stop", package)
    time.sleep(3)
    # Activity must be verified on the device. No guessed launcher component.
    adb("shell", "am", "start", "-n", activity)
    if not ready(package):
        raise RuntimeError("Roadie foreground not confirmed")
    time.sleep(8)  # allow UI settling; map readiness still requires live verification
    fix_map(rmap)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--activity", required=True, help="Verified package/activity")
    ap.add_argument("--pss-limit-mib", required=True, type=int)
    ap.add_argument("--rmap", default=str(Path.home() / "bin/rmap"))
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--confirm-live", action="store_true")
    args = ap.parse_args()
    if args.pss_limit_mib <= 0:
        ap.error("measured positive PSS threshold required")
    if not args.dry_run and not args.confirm_live:
        ap.error("use --dry-run or explicitly --confirm-live")
    if not WATCHER.is_file():
        ap.error("watcher missing")
    if args.dry_run:
        print("DRY RUN: no watcher started or Android actions executed", flush=True)
        while True:
            try:
                print(f"PSS {memory_mib(args.package):.1f} MiB, limit {args.pss_limit_mib}", flush=True)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                print(f"memory unavailable: {exc}", flush=True)
            time.sleep(10)

    # One supervisor per checkout. Avoid duplicate watcher launch.
    lock = BASE / ".roadie_memory_supervisor.lock"
    import fcntl
    with lock.open("w") as lockfile:
        try:
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            ap.error("another memory supervisor owns this checkout")
        history = deque()
        child = None
        over = 0
        try:
            while True:
                if restart_budget_exhausted(history, time.time()):
                    print("restart budget exhausted; stop", flush=True)
                    return 2
                child = subprocess.Popen([sys.executable, "-u", str(WATCHER)], cwd=BASE)
                started = time.time()
                print(f"watcher started pid={child.pid}", flush=True)
                while True:
                    time.sleep(10)
                    if child.poll() is not None:
                        reason = "watcher exited"
                        break
                    last, state = progress_for(child.pid, started)
                    if time.time() - last > 90:
                        reason = f"stale heartbeat ({state})"
                        break
                    try:
                        pss = memory_mib(args.package)
                        over = over + 1 if pss >= args.pss_limit_mib else 0
                        print(f"PSS={pss:.1f} MiB over={over}/3", flush=True)
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        over = 0
                        print(f"memory unavailable; no memory-triggered recovery: {exc}", flush=True)
                    if over >= 3:
                        reason = "memory threshold exceeded 3 consecutive checks"
                        break
                print(f"RECOVERY: {reason}", flush=True)
                stop_child(child)
                child = None
                history.append(time.time())
                over = 0
                try:
                    recover(args.package, args.activity, args.rmap)
                except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
                    print(f"recovery failed; no watcher relaunch until next budgeted attempt: {exc}", flush=True)
                    time.sleep(10)
        except KeyboardInterrupt:
            return 0
        finally:
            if child is not None:
                stop_child(child)

if __name__ == "__main__":
    sys.exit(main())
