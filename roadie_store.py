#!/usr/bin/env python3
"""Offline Roadie XML -> SQLite index. No ADB or UI actions.

Usage: python3 roadie_store.py [--logs ~/Downloads/roadie_logs_nosleepy_economy]
       python3 roadie_store.py --detail ~/Downloads/roadie_detail_test.xml

Working key: exact displayed miles + delivery count. Price is NOT part of key.
"""
import argparse
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

POS = re.compile(r"^(\d+)\s+OF\s+(\d+)$", re.I)
ROUTE = re.compile(r"^(\d+(?:\.\d+)?)\s+mi\s*\((\d+)\s+min\)$", re.I)
DELIVERIES = re.compile(r"^(\d+)\s+deliver(?:y|ies)$", re.I)
CITY = re.compile(r"^[A-Za-z][A-Za-z .'-]*,\s*[A-Z]{2}$")
PRICE = re.compile(r"^\d+(?:\.\d{1,2})?$")
RE_WEIGHT = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)$", re.I)
RE_DIM_1D = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:\"?\s*([LWDHlwdh])|\s*(?:in|inches))?$", re.I)
RE_DIM_3D = re.compile(r"^(\d+(?:\.\d+)?)\"?\s*x\s*(\d+(?:\.\d+)?)\"?\s*x\s*(\d+(?:\.\d+)?)\"?$", re.I)
RE_ITEMS = re.compile(r"^(\d+)(?:\s*items?)?$", re.I)

def parse_weight_to_lbs(raw_text: str):
    if not raw_text:
        return None
    m = RE_WEIGHT.match(raw_text.strip())
    return float(m.group(1)) if m else None

def parse_dimension_to_inches(raw_text: str):
    if not raw_text:
        return None, None
    s = raw_text.strip()
    m3 = RE_DIM_3D.match(s)
    if m3:
        dims = [float(x) for x in m3.groups()]
        return max(dims), s
    m1 = RE_DIM_1D.match(s)
    if m1:
        return float(m1.group(1)), s
    return None, s

def parse_items_count(raw_text: str):
    if not raw_text:
        return None
    m = RE_ITEMS.match(raw_text.strip())
    return int(m.group(1)) if m else None

def extract_cargo(xml_source):
    """
    Extracts cargo weight and dimension fields across all UI generations:
    - Gen 3: Jetpack Compose (ComposeView testTag views: total_weight, heaviest_item, max_dimension, total_items)
    - Gen 2: Structured ViewBinding (total_weight_value, heaviest_item_value, max_dimension_value, total_items_value)
    - Gen 1: Legacy Android Views (weight_textview, item_weight_textview, dimension_textview, items_textview)
    - Item Breakdown screen: dimension_box_view with 3D envelope dimensions.

    Returns dict:
      total_weight_lbs: float | None
      max_weight_lbs: float | None (Heaviest Item)
      max_dimension_in: float | None
      max_dimension_raw: str | None (preserves '82" L', '39" W', '23in', etc.)
      total_items: int | None
    """
    cargo = {
        "total_weight_lbs": None,
        "max_weight_lbs": None,
        "max_dimension_in": None,
        "max_dimension_raw": None,
        "total_items": None
    }
    root = None
    if isinstance(xml_source, ET.Element):
        root = xml_source
    elif isinstance(xml_source, (str, Path)):
        p = Path(xml_source)
        if p.exists() and p.is_file():
            raw = p.read_bytes()
            start = raw.find(b"<hierarchy")
            end = raw.find(b"</hierarchy>", start)
            if start >= 0 and end >= 0:
                root = ET.fromstring(raw[start:end+len(b"</hierarchy>")])
            else:
                try:
                    root = ET.parse(str(p)).getroot()
                except Exception:
                    return cargo
        else:
            txt = str(xml_source)
            start = txt.find("<hierarchy")
            end = txt.find("</hierarchy>", start)
            if start >= 0 and end >= 0:
                root = ET.fromstring(txt[start:end+len("</hierarchy>")])
            else:
                return cargo
    if root is None:
        return cargo

    # 1. Gen 3: Jetpack Compose
    for node in root.iter():
        rid = (node.get("resource-id") or "").split("/")[-1]
        if rid == "total_weight":
            for c in node.iter():
                t = (c.get("text") or "").strip()
                if t and ("lb" in t.lower() or "pound" in t.lower()):
                    cargo["total_weight_lbs"] = parse_weight_to_lbs(t)
        elif rid == "heaviest_item":
            for c in node.iter():
                t = (c.get("text") or "").strip()
                if t and ("lb" in t.lower() or "pound" in t.lower()):
                    cargo["max_weight_lbs"] = parse_weight_to_lbs(t)
        elif rid == "max_dimension":
            for c in node.iter():
                t = (c.get("text") or "").strip()
                if t and t != "Max Dimension":
                    cargo["max_dimension_in"], cargo["max_dimension_raw"] = parse_dimension_to_inches(t)
        elif rid == "total_items":
            for c in node.iter():
                t = (c.get("text") or "").strip()
                if t and t != "Total Items" and t.isdigit():
                    cargo["total_items"] = int(t)

    # 2. Gen 2 & Gen 1 fallback if Compose fields were not found
    if cargo["total_weight_lbs"] is None and cargo["max_dimension_raw"] is None:
        for node in root.iter():
            rid = (node.get("resource-id") or "").split("/")[-1]
            t = (node.get("text") or "").strip()
            if not t:
                continue
            if rid in ("total_weight_value", "weight_textview"):
                cargo["total_weight_lbs"] = parse_weight_to_lbs(t)
            elif rid in ("heaviest_item_value", "item_weight_textview"):
                cargo["max_weight_lbs"] = parse_weight_to_lbs(t)
            elif rid in ("max_dimension_value", "dimension_textview"):
                cargo["max_dimension_in"], cargo["max_dimension_raw"] = parse_dimension_to_inches(t)
            elif rid in ("total_items_value", "items_textview"):
                cargo["total_items"] = parse_items_count(t)

    return cargo

def parse(path):
    raw = Path(path).read_bytes()
    start = raw.find(b"<hierarchy")
    end = raw.find(b"</hierarchy>", start)
    if start < 0 or end < 0:
        raise ValueError(f"No complete hierarchy: {path}")
    root = ET.fromstring(raw[start:end+len(b"</hierarchy>")])
    return [(n.get("resource-id", "").split("/")[-1],
             n.get("text", "").strip(), n.get("content-desc", "").strip())
            for n in root.iter()]

def key(miles, deliveries):
    return f"{miles}_{int(deliveries)}"

def fields(nodes):
    """Return candidate cards. Ambiguous/incomplete fragments are ignored."""
    positions = [(i, int(m.group(1)), int(m.group(2)))
                 for i,(rid,t,d) in enumerate(nodes)
                 if rid == "position_in_stack" and (m := POS.match(t))]
    # A single AVAILABLE GIG summary has no position_in_stack. Only synthesize
    # 1 OF 1 when exactly one visible gig_summary_card exists.
    if not positions:
        try:
            root = ET.parse(path).getroot()
            summaries = [
                n for n in root.iter()
                if n.get("resource-id", "").split("/")[-1] == "gig_summary_card"
                and n.get("bounds", "") not in ("", "[0,0][0,0]")
            ]
            if len(summaries) == 1:
                start = next((i for i, (rid, _, _) in enumerate(nodes)
                              if rid == "gig_summary_card"), None)
                if start is not None:
                    positions = [(start, 1, 1)]
        except (OSError, ET.ParseError):
            pass
    out = {}
    for k,(idx,number,total) in enumerate(positions):
        end = positions[k+1][0] if k+1 < len(positions) else len(nodes)
        seg = nodes[idx:end]
        miles = minutes = deliveries = price = fit = None
        for rid,t,d in seg:
            if (m := ROUTE.match(t)):
                miles,minutes = m.groups()
            if (m := DELIVERIES.match(t)):
                deliveries = int(m.group(1))
            if rid == "consolidation_price" and PRICE.fullmatch(t):
                price = t
            if "FIT FOR FORD" in t.upper():
                fit = t
        if miles is not None and deliveries is not None and price is not None:
            out[number] = dict(key=key(miles, deliveries), miles=miles,
                               minutes=int(minutes), deliveries=deliveries,
                               price=price, fit=fit or "", position=number, total=total)
    return positions, out

def db_open(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS gigs (
        gig_key TEXT PRIMARY KEY,
        miles TEXT NOT NULL,
        deliveries INTEGER NOT NULL,
        destination TEXT,
        origin TEXT,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        last_price TEXT,
        last_minutes INTEGER,
        fit TEXT,
        total_weight_lbs REAL,
        max_weight_lbs REAL,
        max_dimension_in REAL,
        max_dimension_raw TEXT,
        total_items INTEGER
    );
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY,
        seen_at TEXT NOT NULL,
        gig_key TEXT NOT NULL,
        event TEXT NOT NULL,
        old_price TEXT,
        new_price TEXT,
        source TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS event_once
      ON changes(seen_at,gig_key,event,new_price);
    """)
    # Backward-compatible migrations: ensure cargo columns exist in existing DB
    cols = {row[1] for row in con.execute("PRAGMA table_info(gigs)")}
    new_cols = [
        ("total_weight_lbs", "REAL"),
        ("max_weight_lbs", "REAL"),
        ("max_dimension_in", "REAL"),
        ("max_dimension_raw", "TEXT"),
        ("total_items", "INTEGER")
    ]
    for col_name, col_type in new_cols:
        if col_name not in cols:
            con.execute(f"ALTER TABLE gigs ADD COLUMN {col_name} {col_type}")
    return con

def ingest_session(con, directory):
    xmls = sorted(directory.glob("carousel_*.xml"))
    cards, max_total, observed = {}, 0, set()
    for path in xmls:
        try:
            positions, found = fields(parse(path))
        except (ValueError, ET.ParseError):
            continue
        observed.update(p for _,p,_ in positions)
        max_total = max([max_total]+[t for _,_,t in positions])
        for pos,card in found.items():
            # Conflicting records at same carousel position -> refuse ambiguous data.
            if pos in cards and cards[pos]["key"] != card["key"]:
                return 0, "AMBIGUOUS"
            cards[pos] = card
    if not max_total or not set(range(1,max_total+1)).issubset(observed):
        return 0, "INCOMPLETE"
    if not set(range(1,max_total+1)).issubset(cards):
        return 0, "MISSING_FIELDS"
    if len({v["key"] for v in cards.values()}) != max_total:
        return 0, "DUPLICATE_KEY"
    # Timestamp is stable per session so rerunning import does not duplicate events.
    seen_at = directory.name
    changes = 0
    with con:
        for pos,card in sorted(cards.items()):
            old = con.execute("SELECT last_price,last_seen FROM gigs WHERE gig_key=?",
                              (card["key"],)).fetchone()
            # Historical imports must not overwrite newer observations.
            if old and old[1] > seen_at:
                continue
            if not old:
                event,old_price = "NEW",None
            elif old[0] != card["price"]:
                event,old_price = "PRICE_CHANGED",old[0]
            else:
                event,old_price = None,None
            con.execute("""
                INSERT INTO gigs(gig_key,miles,deliveries,first_seen,last_seen,last_price,last_minutes,fit)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(gig_key) DO UPDATE SET
                  last_seen=excluded.last_seen,last_price=excluded.last_price,
                  last_minutes=excluded.last_minutes,fit=excluded.fit
            """, (card["key"],card["miles"],card["deliveries"],seen_at,seen_at,
                  card["price"],card["minutes"],card["fit"]))
            if event:
                con.execute("""INSERT OR IGNORE INTO changes
                    (seen_at,gig_key,event,old_price,new_price,source)
                    VALUES(?,?,?,?,?,?)""",
                    (seen_at,card["key"],event,old_price,card["price"],directory.name))
                changes += 1
    return changes, "OK"

def import_detail(con,path):
    nodes = parse(path)
    texts = [t for _,t,_ in nodes if t]
    cities = [t for t in texts if CITY.fullmatch(t)]
    route = next((ROUTE.match(t) for t in texts if ROUTE.match(t)), None)
    deliveries = next((int(m.group(1)) for t in texts
                       if (m := DELIVERIES.match(t))), None)
    if len(cities) < 2 or not route or deliveries is None:
        raise ValueError("Detail lacks route cities/miles/deliveries")
    k = key(route.group(1),deliveries)
    origin,destination = cities[:2]
    cargo = extract_cargo(path)
    now = datetime.now(timezone.utc).isoformat()
    with con:
        existing = con.execute("SELECT gig_key FROM gigs WHERE gig_key=?",(k,)).fetchone()
        if existing:
            con.execute("""UPDATE gigs SET origin=?,destination=?,
                          total_weight_lbs=coalesce(?,total_weight_lbs),
                          max_weight_lbs=coalesce(?,max_weight_lbs),
                          max_dimension_in=coalesce(?,max_dimension_in),
                          max_dimension_raw=coalesce(?,max_dimension_raw),
                          total_items=coalesce(?,total_items)
                        WHERE gig_key=?""",
                        (origin, destination, cargo["total_weight_lbs"], cargo["max_weight_lbs"],
                         cargo["max_dimension_in"], cargo["max_dimension_raw"], cargo["total_items"], k))
        else:
            con.execute("""INSERT INTO gigs
              (gig_key,miles,deliveries,origin,destination,
               total_weight_lbs,max_weight_lbs,max_dimension_in,max_dimension_raw,total_items,
               first_seen,last_seen)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
              (k,route.group(1),deliveries,origin,destination,
               cargo["total_weight_lbs"], cargo["max_weight_lbs"],
               cargo["max_dimension_in"], cargo["max_dimension_raw"], cargo["total_items"],
               now,now))
    return k,destination

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--logs",type=Path,default=Path.home()/"Downloads/roadie_logs_nosleepy_economy")
    p.add_argument("--db",type=Path,default=Path.home()/"Downloads/roadie_gigs.sqlite3")
    p.add_argument("--detail",type=Path)
    args=p.parse_args()
    con=db_open(args.db)
    if args.detail:
        k,city=import_detail(con,args.detail)
        print(f"DETAIL {k} -> {city}")
    else:
        count=0
        for folder in sorted(args.logs.glob("2026-*")):
            n,status=ingest_session(con,folder)
            if status=="OK":
                count+=1
                print(f"{folder.name}: {status}, {n} changes")
        print(f"Complete sessions indexed: {count}")
    print(f"Database: {args.db}")
    print("Gigs:",con.execute("SELECT COUNT(*) FROM gigs").fetchone()[0])
    print("Events:",con.execute("SELECT COUNT(*) FROM changes").fetchone()[0])

if __name__=="__main__":
    main()
