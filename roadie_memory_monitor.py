#!/usr/bin/env python3
"""Read-only Roadie Android memory monitor. No restart actions.

Recovery must not run until a reliable, fresh SEARCH-mode signal is implemented.
"""
import argparse
import re
import subprocess
import time

def adb(*args, timeout=12):
    return subprocess.run(["adb", *args], capture_output=True, text=True,
                          timeout=timeout, check=True).stdout

def parse_meminfo(raw):
    """Return PSS and Java heap figures in KiB, or None if absent."""
    pss = re.search(r"^\s*TOTAL\s+(\d+)\s+", raw, re.M)
    # dumpsys meminfo output varies by Android version; TOTAL PSS is required.
    heap = re.search(r"^\s*Java Heap:\s*(\d+)\s+", raw, re.M)
    return {"pss_kib": int(pss.group(1)) if pss else None,
            "java_heap_kib": int(heap.group(1)) if heap else None}

def sample(package):
    output = adb("shell", "dumpsys", "meminfo", package, timeout=20)
    return parse_meminfo(output)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="Verified Android package name")
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--pss-limit-mib", type=int, default=0,
                    help="Optional measured absolute threshold; 0 disables alert")
    args = ap.parse_args()
    if args.interval < 5 or args.pss_limit_mib < 0:
        ap.error("interval must be >=5 and limit >=0")
    print("READ-ONLY dry-run: no watcher/app restarts", flush=True)
    while True:
        try:
            m = sample(args.package)
            pss = m["pss_kib"]
            if pss is None:
                print("MEMORY UNKNOWN: no reliable TOTAL PSS; fail closed", flush=True)
            else:
                mib = pss / 1024
                alert = bool(args.pss_limit_mib and mib >= args.pss_limit_mib)
                print(f"PSS={mib:.1f} MiB JavaHeap={m['java_heap_kib']} KiB "
                      f"threshold={args.pss_limit_mib or 'disabled'} MiB "
                      f"would_recover={alert} (dry-run only)", flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"ADB/meminfo unavailable: {type(exc).__name__}; fail closed", flush=True)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
