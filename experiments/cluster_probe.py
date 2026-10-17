#!/usr/bin/env python3
"""Roadie cluster probe: synchronized UI markers for an independently running Android packet capture.

Requires: macOS, adb, PCAPdroid capture started manually on Android.
Never starts/stops PCAPdroid, Roadie, Supervisor, Watcher, or Publisher.
Refuses to tap while Supervisor/Watcher is running.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import time

def run(cmd, timeout=20, binary=False):
    return subprocess.run(cmd, capture_output=True, timeout=timeout,
                          check=True, text=not binary)

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

def check_production():
    out = run(["ps", "-axo", "command"]).stdout
    busy = [line.strip() for line in out.splitlines()
            if re.search(r"(?:^|[/ ])roadie_(?:memory_supervisor|watcher_with_destinations)\.py(?:\s|$)", line)
            and "cluster_probe.py" not in line]
    if busy:
        sys.exit("REFUSING TO TAP: production Supervisor/Watcher still running:\n" + "\n".join(busy))

def adb(*args, timeout=25, binary=False):
    return run(["adb", *args], timeout=timeout, binary=binary)

def xml_capture(folder, label):
    # Dump is read-only with respect to Roadie UI, but uses ADB; no concurrent Watcher permitted.
    remote = "/sdcard/window_roadie_probe.xml"
    adb("shell", "uiautomator", "dump", remote, timeout=35)
    data = adb("exec-out", "cat", remote, timeout=20, binary=True).stdout
    (folder / f"{label}.xml").write_bytes(data)

def event(folder, label, **info):
    row = {"utc": stamp(), "event": label, **info}
    with (folder / "events.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(row["utc"], label, info, flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--x", type=int, help="Cluster center X (default: center of screen)")
    p.add_argument("--y", type=int, help="Cluster center Y (default: center of screen)")
    p.add_argument("--swipes", type=int, default=0, choices=range(0, 6),
                   metavar="0..5", help="Optional carousel swipes (default: none)")
    args = p.parse_args()
    check_production()
    devices = adb("devices").stdout.splitlines()[1:]
    ready = [x for x in devices if x.endswith("\tdevice")]
    if len(ready) != 1:
        sys.exit(f"Expected exactly one authorized ADB device, got: {devices}")
    size = adb("shell", "wm", "size").stdout
    m = re.search(r"(\d+)x(\d+)", size)
    if not m:
        sys.exit(f"Cannot determine screen size: {size}")
    w, h = map(int, m.groups())
    x = args.x if args.x is not None else w // 2
    y = args.y if args.y is not None else h // 2
    if not (0 <= x < w and 0 <= y < h):
        sys.exit("Tap coordinates outside screen")
    folder = pathlib.Path.home() / "Downloads" / "roadie_cluster_probes" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True)
    print(f"Capture output: {folder}\nTap point: ({x}, {y}) of {w}x{h}")
    print("1. On Android start PCAPdroid capture filtered to Roadie.")
    print("2. Position the desired cluster exactly at tap point.")
    print("3. Ensure Supervisor AND Watcher are stopped; Publisher may remain running.")
    print("4. Press Enter to capture BEFORE XML, tap once, and capture AFTER XML.")
    input("READY? Press Enter (Ctrl-C cancels): ")
    check_production()
    event(folder, "start", x=x, y=y, screen=f"{w}x{h}")
    xml_capture(folder, "before")
    event(folder, "before_xml_saved")
    event(folder, "tap_start", x=x, y=y)
    adb("shell", "input", "tap", str(x), str(y))
    event(folder, "tap_done")
    time.sleep(2)
    xml_capture(folder, "after_tap")
    event(folder, "after_tap_xml_saved")
    for i in range(args.swipes):
        check_production()
        # Horizontal swipe inside card area; explicitly opt-in only.
        event(folder, "swipe_start", index=i + 1)
        adb("shell", "input", "swipe", str(int(w * .82)), str(int(h * .77)),
            str(int(w * .18)), str(int(h * .77)), "450")
        time.sleep(1.5)
        xml_capture(folder, f"after_swipe_{i+1:02d}")
        event(folder, "swipe_done", index=i + 1)
    event(folder, "end")
    print("\nDone. Stop PCAPdroid and export PCAP separately; align packets to UTC events.jsonl.")
    print("Do not upload raw PCAP/XML publicly: may contain tokens, addresses, and customer data.")
    print(folder)

if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        sys.exit(f"Probe stopped: {exc}")
