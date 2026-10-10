#!/usr/bin/env python3
"""Publish an anonymized Roadie history snapshot. Never publishes raw SQLite."""
import base64
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

DB = Path.home() / "Downloads" / "roadie_gigs.sqlite3"
REPO = "DeployForceUs/roadie-dashboard"
INTERVAL = 60

def normalize(value):
    if not value:
        return None
    value = str(value).replace("_", "T")
    if len(value) >= 19 and value[13] == "-" and value[16] == "-":
        value = value[:13] + ":" + value[14:16] + ":" + value[17:19]
    try:
        return dt.datetime.fromisoformat(value[:19]).isoformat()
    except ValueError:
        return None

def make_payload():
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        records = db.execute("SELECT gig_key,miles,deliveries,destination,last_price,last_minutes,fit,last_seen,first_seen FROM gigs").fetchall()
        changes = db.execute("SELECT seen_at,gig_key,event,old_price,new_price FROM changes ORDER BY id DESC LIMIT 250").fetchall()
    history = []
    for row in records:
        r = dict(row)
        try:
            price = float(r["last_price"])
            miles = float(r["miles"])
            mins = float(r["last_minutes"])
            if not (price >= 0 and miles > 0 and mins > 0):
                continue
        except (ValueError, TypeError):
            continue
        fit_text = str(r["fit"] or "").upper()
        fit = "no" if "NOT A FIT" in fit_text else "unknown"
        history.append(dict(key=r["gig_key"], price=price, hour=round(price*60/mins,2),
            mile=round(price/miles,2), miles=miles, deliveries=r["deliveries"],
            minutes=int(mins), city=(r["destination"] or "Неизвестно").replace(", FL",""),
            fit=fit, last_seen=normalize(r["last_seen"]), first_seen=normalize(r["first_seen"])))
    history.sort(key=lambda x:x["last_seen"] or "",reverse=True)
    # No current snapshot until the watcher emits a verified complete-scan record.
    return dict(generated_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        current=[], current_status="not_available", history=history,
        changes=[dict(x) for x in changes], note="Current availability is not verified")

def publish(payload):
    data=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
    get=subprocess.run(["gh","api",f"repos/{REPO}/contents/data.json","--jq",".sha"],
                       capture_output=True,text=True)
    args=["gh","api","--method","PUT",f"repos/{REPO}/contents/data.json",
          "-f","message=Update Roadie anonymized history",
          "-f","content="+base64.b64encode(data.encode()).decode()]
    if get.returncode==0 and get.stdout.strip():
        args.extend(["-f","sha="+get.stdout.strip()])
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    print(dt.datetime.now().strftime("%H:%M:%S"),"published",len(payload["history"]),"history records",flush=True)

def main():
    print("Publishing anonymized history every 60s; Ctrl+C to stop",flush=True)
    while True:
        try:
            publish(make_payload())
        except Exception as exc:
            print("Publish error:",exc,file=sys.stderr,flush=True)
        time.sleep(INTERVAL)

if __name__=="__main__":
    main()
