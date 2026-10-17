# Roadie cluster experiment (isolated branch)

Goal: distinguish whether Roadie loads cluster data before tapping, on tap, or while paging cards. A network capture on the Android phone is required; ADB alone cannot capture decrypted HTTP traffic.

## Prerequisites
- macOS with `adb` and a single authorized Android device.
- PCAPdroid installed on Android. Start capture manually, filter to Roadie, and save/export PCAP when done.
- **Stop production Supervisor and Watcher through their known safe procedure before testing.** The script refuses to tap while either process is detected. Publisher is not stopped. Do not kill Watcher alone while Supervisor is running, because Supervisor may recover/restart it.
- Use only your own device/account and respect service terms.

## Run
```bash
cd ~/roadie-dashboard
python3 experiments/cluster_probe.py
```

The script waits for Enter. Position the cluster in the **center of the screen** (default tap location) first. If necessary supply `--x 500 --y 1200` with your verified pixel coordinates. It takes XML before and after one tap and records UTC timestamps in `~/Downloads/roadie_cluster_probes/<timestamp>/events.jsonl`.

Optionally use `--swipes 3` to move through three carousel cards after tapping, but start with **zero swipes** to isolate the first network request.

## Interpretation
- Compare packet timestamps before and after `tap_start`.
- Standard PCAP generally reveals IP/ports/traffic timing, not HTTPS URLs, request bodies or JSON.
- PCAPdroid TLS decryption, if supported and authorized, may require additional configuration and may fail for apps using certificate pinning. **This script does not bypass TLS or pinning.**
- A lack of traffic after tapping does not prove data was cached: look at earlier capture, retries, multiplexed connections and app behavior.
- Keep PCAP, XML and diagnostics private; they may contain addresses, tokens and order details.

## Scope
No production code changes, no automatic Supervisor/Watcher shutdown, no PCAPdroid automation, no network routing changes. Resume production only after stopping the capture and restoring the normal Roadie map state.
