#!/usr/bin/env python3
"""Publish an anonymized Roadie history snapshot. Never publishes raw SQLite."""
import base64
import datetime as dt
import json
import os
import re
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
    # Current view comes from the last observed map, never from historical gigs alone.
    # A direct map ID must match a captured detail; clusters require a separate
    # verified full-map pass and must not be silently omitted.
    current = []
    current_status = "not_available"
    scan_at = None
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "map_scans" in tables:
            scan = db.execute("SELECT observed_at,direct_ids_json,cluster_count FROM map_scans ORDER BY scan_id DESC LIMIT 1").fetchone()
            if scan:
                scan_at = scan["observed_at"]
                ids = json.loads(scan["direct_ids_json"])
                details = {}
                if "direct_gig_details" in tables:
                    for row in db.execute("SELECT gig_id,details_json FROM direct_gig_details"):
                        try:
                            details[row["gig_id"]] = json.loads(row["details_json"])
                        except (ValueError,TypeError):
                            pass
                missing = 0
                for gig_id in ids:
                    d = details.get(str(gig_id))
                    if not d:
                        missing += 1
                        continue
                    def number(field):
                        match = re.search(r"\\d+(?:[.,]\\d+)?",str(d.get(field,"")))
                        return float(match.group().replace(",",".")) if match else None
                    price, miles, mins = number("Price"),number("Distance"),number("Time")
                    if not price or not miles or not mins:
                        missing += 1
                        continue
                    current.append(dict(key=str(gig_id),price=price,
                        hour=round(price*60/mins,2),mile=round(price/miles,2),
                        miles=miles,deliveries=0,minutes=int(mins),
                        city=str(d.get("To","Неизвестно")).replace(", FL",""),
                        fit="unknown"))
                if scan["cluster_count"]:
                    current_status = "partial_clusters"
                elif missing:
                    current_status = "partial_details"
                else:
                    current_status = "map_direct_only"
    return dict(generated_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        current=current, current_status=current_status, scan_at=scan_at, history=history,
        changes=[dict(x) for x in changes], note="Current is based on latest observed direct IDs; cluster coverage and detail freshness are not guaranteed")

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
