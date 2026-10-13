#!/usr/bin/env python3
"""Read-only Roadie Memory Guardian. Never starts/stops Roadie or the Watcher.

All thresholds are experimental. This program logs hypothetical recovery
decisions only; no live recovery mode is implemented.
"""
import argparse
import datetime
import subprocess
import time

from roadie_memory_monitor import parse_meminfo


def sample(package, timeout):
    output = subprocess.run(
        ["adb", "shell", "dumpsys", "meminfo", package],
        check=True, capture_output=True, text=True, timeout=timeout,
    ).stdout
    info = parse_meminfo(output)
    if info["pss_kib"] is None:
        raise ValueError("TOTAL PSS unavailable")
    return info["pss_kib"] / 1024.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="com.roadie.drive.android.app")
    parser.add_argument("--pss-limit-mib", type=float, default=700.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--consecutive", type=int, default=3)
    parser.add_argument("--cooldown-seconds", type=float, default=300.0)
    parser.add_argument("--samples", type=int, default=0,
                        help="0 means continuous; otherwise exit after N samples")
    args = parser.parse_args()
    if args.pss_limit_mib <= 0 or args.interval_seconds <= 0 or args.consecutive <= 0 or args.cooldown_seconds < 0 or args.samples < 0:
        parser.error("invalid threshold, interval, consecutive count, cooldown or samples")

    print("OBSERVE ONLY: no Android control actions; Watcher untouched", flush=True)
    over = 0
    last_event = float("-inf")
    count = 0
    while args.samples == 0 or count < args.samples:
        count += 1
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            pss = sample(args.package, max(20.0, args.interval_seconds))
            over = over + 1 if pss >= args.pss_limit_mib else 0
            now = time.monotonic()
            print(f"{stamp} PSS={pss:.1f} MiB threshold={args.pss_limit_mib:.1f} consecutive={over}/{args.consecutive}", flush=True)
            if over >= args.consecutive and now - last_event >= args.cooldown_seconds:
                print(f"{stamp} WOULD_RESTART (simulation only): sustained high PSS; no action taken", flush=True)
                last_event = now
                over = 0
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            over = 0
            print(f"{stamp} MEMORY_UNAVAILABLE: {exc}; no recovery", flush=True)
        if args.samples == 0 or count < args.samples:
            time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
