#!/usr/bin/env python3
"""Temporary Roadie test supervisor. Owns only the watcher process it launches."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import deque

BASE = Path(__file__).resolve().parent
WATCHER = BASE / "roadie_watcher_with_destinations.py"
HEARTBEAT = Path.home() / "Downloads/roadie_logs_nosleepy_economy/_tmp/watcher_heartbeat.json"
STALE_SECONDS = int(os.getenv("ROADIE_STALE_SECONDS", "60"))
MAX_RESTARTS = 3
RESTART_WINDOW = 15 * 60
CHECK_SECONDS = 5
TOKEN = os.getenv("ROADIE_TELEGRAM_BOT_TOKEN", "")
CHAT = os.getenv("ROADIE_TELEGRAM_CHAT_ID", "")


def notice(message):
    print(time.strftime("[%H:%M:%S]"), message, flush=True)
    if not TOKEN or not CHAT:
        return
    url = "https://api.telegram.org/bot" + TOKEN + "/sendMessage"
    body = urllib.parse.urlencode({"chat_id": CHAT, "text": message}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=7).close()
    except Exception as exc:
        print("Telegram delivery failed:", exc, flush=True)


def progress_for(pid, started):
    try:
        state = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        if state.get("pid") != pid or state.get("timestamp", 0) < started:
            return started, "STARTING"
        return float(state["timestamp"]), str(state.get("state", "UNKNOWN"))
    except (OSError, ValueError, TypeError, KeyError):
        return started, "NO_HEARTBEAT"


def stop_child(child):
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def restart_budget_exhausted(history, now, max_restarts=MAX_RESTARTS, window=RESTART_WINDOW):
    """Expire old failures and decide whether another start is permitted."""
    while history and now - history[0] > window:
        history.popleft()
    return len(history) >= max_restarts


def main():
    if not WATCHER.is_file():
        sys.exit("Watcher script not found: " + str(WATCHER))
    history = deque()
    child = None
    notice("Roadie test watchdog started; Telegram " + ("enabled" if TOKEN and CHAT else "NOT configured"))
    try:
        while True:
            now = time.time()
            if restart_budget_exhausted(history, now):
                notice("ROADIE ALERT: 3 restarts in 15 minutes. Supervisor stopped; manual inspection required.")
                return 2
            child = subprocess.Popen([sys.executable, "-u", str(WATCHER)], cwd=str(BASE))
            started = time.time()
            notice(f"Roadie watcher started, PID {child.pid}")
            reason = ""
            while True:
                time.sleep(CHECK_SECONDS)
                code = child.poll()
                if code is not None:
                    reason = f"process exited (code {code})"
                    break
                last, state = progress_for(child.pid, started)
                if time.time() - last > STALE_SECONDS:
                    reason = f"no successful progress for {int(time.time()-last)}s; last state {state}"
                    break
            notice(f"ROADIE ALERT: {reason}. Restarting supervised watcher.")
            stop_child(child)
            history.append(time.time())
            time.sleep(2)
    except KeyboardInterrupt:
        notice("Supervisor stopped by operator.")
        return 0
    finally:
        if child is not None:
            stop_child(child)


if __name__ == "__main__":
    sys.exit(main())
