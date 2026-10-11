#!/usr/bin/env python3
# =============================================================================
# roadie_watcher_fast_XML_ONLY_min.py
# Version 3.7.2 (2025‑08‑12)  ← правка: POS читает из файлов сессии; зеркалим TMP→session
#
# Изменения (к 3.7.1):
# - wait_pos() логирует путь файла.
# - Перед вызовами wait_pos() делаем дамп в TMP, зеркалим в папку сессии
#   (carousel_01.xml, carousel_02.xml, …) и читаем POS уже из них.
# - maybe_save_detail() теперь получает тот же файл из сессии (единая точка правды).
# - В fallback ветке повторение считаем по тексту из файлов сессии.
# - Для одиночных также зеркалим detail в сессию (gid.xml) и сохраняем оттуда.
# =============================================================================

import os, time, subprocess, xml.etree.ElementTree as ET, re, sys, shutil, hashlib, sqlite3, json
from roadie_store import db_open, parse as store_parse, fields as store_fields, CITY, ROUTE, DELIVERIES, key as gig_key, extract_cargo
from datetime import datetime
from time import perf_counter
from roadie_ui_guard import Screen, classify_xml, allowed_action
from roadie_capture import capture_xml, CaptureError

# ===================== ТЮНЕРЫ =====================
SWIPE_MS             = 220
SLEEP_AFTER_TAP      = 1.0
SLEEP_AFTER_SWIPE    = 0.7
SLEEP_AFTER_BACK     = 0.8
SLEEP_AFTER_REFRESH  = 0.6

MAX_CARDS            = 200  # safety cap only
FALLBACK_MAX_CARDS   = 0    # never swipe without verified carousel
MAX_STALL_SWIPES      = 3

# ожидание POS
POS_WAIT_TRIES       = 4
POS_WAIT_DELAY       = 0.5

REFRESH_X, REFRESH_Y     = 120, 2437
CAR_SWIPE_X1, CAR_SWIPE_X2 = 900, 200
CAR_SWIPE_Y               = 2300

DUMP_RETRY            = 1
MIN_XML_BYTES         = 3600
# ==================================================

# ======= High‑res timing / трассировка =======
LOG_TIMING = True
_T0 = perf_counter()
_last = _T0
def tick(msg: str):
    global _last
    if not LOG_TIMING:
        return
    now = perf_counter()
    total_ms = (now - _T0) * 1000.0
    delta_ms = (now - _last) * 1000.0
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] ⏱ {msg} | +{delta_ms:.2f} ms | total {total_ms:.2f} ms", flush=True)
    _last = now
# ============================================

DOWNLOADS = os.path.expanduser("~/Downloads")
LOG_BASE  = os.path.join(DOWNLOADS, "roadie_logs_nosleepy_economy")
TMP_DIR   = os.path.join(LOG_BASE, "_tmp")
os.makedirs(LOG_BASE, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

HEARTBEAT_FILE = os.path.join(TMP_DIR, "watcher_heartbeat.json")

def heartbeat(state: str):
    """Successful activity only; watchdog reads this file without ADB."""
    payload = {"timestamp": time.time(), "pid": os.getpid(), "state": state}
    temp = HEARTBEAT_FILE + f".{os.getpid()}.tmp"
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(temp, HEARTBEAT_FILE)
    except OSError as exc:
        print(f"heartbeat write failed: {exc}", flush=True)

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def adb(cmd: str) -> str:
    try:
        out = subprocess.run(f"adb {cmd}", shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return out.stdout.decode(errors="ignore")
    except Exception as e:
        log(f"ADB ERROR: {e}")
        return ""

def tap(x: int, y: int):
    tick(f"tap START → ({x},{y})")
    adb(f"shell input tap {x} {y}")
    tick("tap DONE")

def swipe(x1:int,y1:int,x2:int,y2:int,ms:int=250):
    tick(f"swipe START → ({x1},{y1})→({x2},{y2}) {ms}ms")
    adb(f"shell input swipe {x1} {y1} {x2} {y2} {ms}")
    tick("swipe DONE")

def back():
    tick("back START")
    adb("shell input keyevent 4")
    tick("back DONE")

def _adb_checked(args):
    """Capture-only ADB path: no shell interpolation and no stale success."""
    return subprocess.run(['adb', *args], capture_output=True, text=True, timeout=25)

def dump_xml(dst_path: str) -> bool:
    try:
        screen = capture_xml(dst_path, _adb_checked, min_bytes=MIN_XML_BYTES)
        log(f"📄 verified fresh XML: {os.path.basename(dst_path)} ({screen.value})")
        return True
    except (CaptureError, OSError, subprocess.SubprocessError, UnicodeError) as exc:
        log(f"⚠️ XML capture rejected: {type(exc).__name__}: {exc}")
        return False

def dump_xml_checked(dst_path: str) -> bool:
    # Transitions can briefly expose UNKNOWN; retry with fresh remote paths.
    for attempt in range(3):
        if dump_xml(dst_path):
            return True
        time.sleep(0.35 * (attempt + 1))
    return False

def observed_screen(path: str) -> Screen:
    try:
        return classify_xml(open(path, encoding='utf-8').read())
    except (OSError, UnicodeError):
        return Screen.UNKNOWN

def recover_to_map() -> bool:
    """Only press Back on positively identified carousel/detail screens."""
    probe = os.path.join(TMP_DIR, 'screen_probe.xml')
    for attempt in range(4):
        if not dump_xml_checked(probe):
            log('⛔ cannot verify screen; no tap or Back')
            return False
        screen = observed_screen(probe)
        if screen is Screen.MAP:
            heartbeat("MAP")
            return True
        if screen is Screen.DETAIL and allowed_action(screen, 'close_detail'):
            log('↩️ DETAIL verified; returning toward MAP')
            back()
        elif screen is Screen.CAROUSEL and allowed_action(screen, 'back_to_map'):
            log('↩️ CAROUSEL verified; returning toward MAP')
            back()
        else:
            log('⛔ UNKNOWN screen; no blind navigation')
            return False
        time.sleep(SLEEP_AFTER_BACK)
    return False

def get_bounds_center(bounds: str):
    try:
        b = (bounds or "").strip("[]").split("][")
        (x1,y1),(x2,y2) = [list(map(int, p.split(","))) for p in b]
        return ((x1+x2)//2, (y1+y2)//2)
    except:
        return (540, 1600)

def parse_ui(path: str):
    tick(f"parse START ← {os.path.basename(path)}")
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        log(f"❌ parse_ui error: {e} | path={path}")
        tick("parse ERROR")
        return []
    els=[]
    for n in root.iter():
        a=n.attrib
        t=(a.get("text") or "").strip()
        d=(a.get("content-desc") or "").strip()
        b=a.get("bounds",""); rid=a.get("resource-id",""); cls=a.get("class","")
        if t or d: els.append({"text":t,"desc":d,"bounds":b,"rid":rid,"class":cls})
    tick(f"parse DONE ({len(els)} elems)")
    return els

def debug_detect(elements):
    ids = [ (e["desc"], e["bounds"]) for e in elements
            if e["desc"].isdigit() and 6 <= len(e["desc"]) <= 9 ]
    clusters = [ (e["desc"], e["bounds"]) for e in elements
                 if e["desc"].isdigit() and 0 <= int(e["desc"]) <= 99 ]
    def head(items,k=5): return items[:k]
    log("── DETECT DUMP ─────────────────────────────")
    log(f"ids(6..9 digits, desc)   : {len(ids)} {head(ids)}")
    log(f"clusters(0..99, desc)    : {len(clusters)} {head(clusters)}")
    log("────────────────────────────────────────────")
    mode = 'clusters' if clusters else ('single' if ids else 'single')
    reason = "found cluster numbers in content-desc (0..99)" if clusters else (
             "found direct gig ids in content-desc" if ids
             else "fallback: nothing obvious found")
    return ids, clusters, mode, reason

# --- POS "N OF M" ---
POS_RID = "card_positons"  # legacy
POS_RE = re.compile(r"^\s*(\d+)\s*OF\s*(\d+)\s*$", re.I)

def all_positions(xml_path):
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return []
    result=[]
    for n in root.iter():
        rid=n.get("resource-id","").split("/")[-1]
        if rid in ("position_in_stack","card_positons","card_positions"):
            m=POS_RE.match(n.get("text",""))
            if m: result.append((int(m.group(1)),int(m.group(2))))
    return result

def read_pos_text(xml_path: str) -> str:
    positions = all_positions(xml_path)
    if positions:
        c,t=max(positions,key=lambda p:p[0])
        return f"{c} OF {t}"
    try:
        with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except:
        return ""
    m = re.search(
        r'ViewPager[^>]*?resource-id="[^"]+/gig_card_pager"(.|\n)*?resource-id="[^"]+/' + POS_RID + r'"[^>]*?text="([^"]+)"',
        txt, re.I
    )
    if m: return m.group(2).strip()
    m2 = re.search(r'resource-id="[^"]+/' + POS_RID + r'"[^>]*?text="([^"]+)"', txt, re.I)
    return (m2.group(1).strip() if m2 else "")

def parse_pos(s: str):
    m = re.match(r'^\s*(\d+)\s*OF\s*(\d+)\s*$', s, re.I)
    if not m: return (None, None)
    return (int(m.group(1)), int(m.group(2)))

# --- сбор полей из detail.xml в мини‑CSV без pandas ---
def norm_price(raw_digits: str):
    if not raw_digits: return None
    s = raw_digits.replace("\u00A0","").replace("\u202F","").replace(",","").replace(" ","")
    if re.fullmatch(r"\d+", s): return f"{int(s)/100:.2f}"
    s2 = raw_digits.replace("\u00A0"," ").replace("\u202F"," ").replace(",",".")
    try: return f"{float(s2):.2f}"
    except: return None

def extract_support_id(txt:str):
    m=re.search(r"Support ID[:\s]+([A-Za-z0-9_-]+)", txt, re.I)
    return m.group(1) if m else ""

def collect_from_detail_xml(xml_path: str):
    els = parse_ui(xml_path)
    by_id={}
    for e in els:
        if e["rid"]:
            by_id[e["rid"].split("/")[-1]] = e
    rows=[]
    def add(key, rid):
        x = by_id.get(rid, {})
        val = x.get("text","")
        if val: rows.append((key, val))
    add("Support ID", "gig_name")
    add("From",       "starting_city_textview")
    add("To",         "ending_city_textview")
    dsig = by_id.get("dollar_sign", {}).get("text","")
    damt = by_id.get("dollar_amount", {}).get("text","")
    if dsig or damt:
        price_norm = norm_price(damt) if damt else None
        rows.append(("Price", f"${price_norm}" if price_norm else (dsig+damt)))
    add("Distance",   "number_of_miles")
    add("Time",       "time_to_complete")
    add("Size",       "size")
    sname = by_id.get("sender_name", {}).get("text","").strip()
    if sname: rows.append(("Source", sname))
    rows = [(k, extract_support_id(v) if k=="Support ID" else v) for (k,v) in rows]
    cargo = extract_cargo(xml_path)
    if cargo["total_weight_lbs"] is not None:
        rows.append(("Total Weight", f"{cargo['total_weight_lbs']:g} lbs"))
    if cargo["max_weight_lbs"] is not None:
        rows.append(("Heaviest Item", f"{cargo['max_weight_lbs']:g} lbs"))
    if cargo["max_dimension_raw"] is not None:
        rows.append(("Max Dimension", cargo["max_dimension_raw"]))
    if cargo["total_items"] is not None:
        rows.append(("Total Items", str(cargo["total_items"])))
    return rows

def save_rows_as_csv(rows, csv_out: str):
    try:
        import csv
        with open(csv_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["param","value"])
            for k,v in rows:
                w.writerow([k, v])
        log(f"📝 saved {os.path.basename(csv_out)} ({len(rows)} rows)")
    except Exception as e:
        log(f"❌ CSV save error: {e} | {csv_out}")

# ===== Helpers: чтение raw и saver с дедупом =====
def file_text_and_md5(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except Exception:
        txt = ""
    md5 = hashlib.md5(txt.encode("utf-8", errors="ignore")).hexdigest()
    return txt, md5

def maybe_save_detail(xml_path: str, out_basename: str, ensure_session_cb, global_seen: set):
    """
    Возвращает True если что-то сохранили (новое или минимальное), иначе False (дубль).
    """
    raw_txt, md5 = file_text_and_md5(xml_path)
    sig = "RAWMD5:" + md5
    if sig in global_seen:
        log(f"♻️ DUP → skip: {out_basename}")
        return False
    rows = collect_from_detail_xml(xml_path)
    session_dir = ensure_session_cb()
    if rows:
        csv_out = os.path.join(session_dir, out_basename)
        save_rows_as_csv(rows, csv_out)
        global_seen.add(sig)
        log(f"✅ NEW(saved) → {out_basename}")
        return True
    # пусто → минимальный CSV + копия raw XML (он уже в сессии, но на всякий случай)
    raw_xml_name = out_basename.replace("_info.csv", ".xml")
    try:
        if os.path.abspath(os.path.dirname(xml_path)) != os.path.abspath(session_dir):
            shutil.copy2(xml_path, os.path.join(session_dir, raw_xml_name))
    except Exception as e:
        log(f"⚠️ RAW copy error: {e}")
    minimal_csv = os.path.join(session_dir, out_basename)
    save_rows_as_csv(
        [("note","no structured fields; raw xml saved"),
         ("raw_xml", raw_xml_name),
         ("ts", datetime.now().isoformat(timespec="seconds"))],
        minimal_csv
    )
    global_seen.add(sig)
    log(f"✅ NEW(minimal) → {out_basename}")
    return True

# вспомогательная: дождаться POS с ожиданием (читает ровно тот файл, что передан)
def wait_pos(xml_path: str, want_cur=None):
    """Пытаемся прочитать POS несколько раз. Если want_cur задан, успех — когда cur==want_cur."""
    log(f"[POS] reading from: {xml_path}")
    for k in range(1, POS_WAIT_TRIES+1):
        # файл уже должен существовать; при необходимости вызывающий код обновит его копию
        pos_text = read_pos_text(xml_path)
        if pos_text:
            c, t = parse_pos(pos_text)
            log(f"[POS wait attempt {k}] raw='{pos_text}' → {c}/{t}")
            if c and t and (want_cur is None or c == want_cur):
                return (c, t, pos_text)
        else:
            log(f"[POS wait attempt {k}] not found")
        time.sleep(POS_WAIT_DELAY)
    return (None, None, "")

# ---------- основной цикл ----------
def main():
    log("🚀 FAST XML ONLY watcher (lazy sessions, no cleanup).")

    seen=set()
    # Temporary backoff for direct markers that unexpectedly open a carousel.
    # Keep map sightings and price tracking independent of this throttle.
    direct_marker_retry_after = {}
    DIRECT_MARKER_RETRY_SECONDS = 120
    saved_card_sigs=set()          # глобальный дедуп по raw‑XML
    processed_clusters=set()
    cycle=0
    last_map_sig=None
    carousel_lastN = {}            # мониторинг N (сколько карт в карусели) по bounds

    while True:
        cycle+=1
        if not recover_to_map():
            log("⛔ cannot confirm MAP; defer cycle without refresh or DB scan")
            time.sleep(2.0)
            continue
        tap(REFRESH_X, REFRESH_Y); log(f"🔄 cycle {cycle}: refresh"); tick("after REFRESH tap")
        time.sleep(SLEEP_AFTER_REFRESH)

        start_tmp = os.path.join(TMP_DIR, "start.xml")
        if not dump_xml_checked(start_tmp):
            log("⚠️ start dump failed, skip"); time.sleep(0.35); continue

        if observed_screen(start_tmp) is not Screen.MAP:
            log("⛔ refresh returned non-MAP screen; no map_scans write")
            time.sleep(1.0)
            continue
        heartbeat("MAP_REFRESHED")
        elements = parse_ui(start_tmp); tick("after START parsed")
        log(f"📄 parsed start: {len(elements)} elements")

        ids, clusters_list, mode, reason = debug_detect(elements)
        log(f"🧭 mode={mode} | ids={len(ids)} | clusters={len(clusters_list)}")
        log(f"ℹ️ reason: {reason}")

        # дедуп одинаковых баблов по bounds
        seen_bounds=set()
        clusters_list = [ (d,b) for (d,b) in clusters_list if not (b in seen_bounds or seen_bounds.add(b)) ]

        # подготовим синглы
        id_nodes = [ {"desc":d, "bounds":b} for (d,b) in ids ]
        now_mono = time.monotonic()
        direct_marker_retry_after = {
            marker: deadline for marker, deadline in direct_marker_retry_after.items()
            if deadline > now_mono
        }
        new_ids = [
            e for e in id_nodes
            if (e["desc"], e["bounds"]) not in seen
            and e["desc"] not in direct_marker_retry_after
        ]

        clusters_bounds = tuple(sorted(b for _, b in clusters_list))
        singles_bounds  = tuple(sorted(b for _, b in ids))
        map_sig = (clusters_bounds, singles_bounds)

        # Persist direct map sightings on every scan, including unchanged maps.
        # These IDs are not the same as the miles/deliveries history key.
        try:
            with db_open(os.path.join(DOWNLOADS, "roadie_gigs.sqlite3")) as sight_db:
                sight_db.execute("""CREATE TABLE IF NOT EXISTS map_scans (
                    scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT NOT NULL,
                    direct_ids_json TEXT NOT NULL,
                    cluster_count INTEGER NOT NULL
                )""")
                import json
                sight_db.execute(
                    "INSERT INTO map_scans(observed_at,direct_ids_json,cluster_count) VALUES (?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"),
                     json.dumps([e["desc"] for e in id_nodes]),len(clusters_list))
                )
                sight_db.execute("""DELETE FROM map_scans WHERE scan_id NOT IN
                    (SELECT scan_id FROM map_scans ORDER BY scan_id DESC LIMIT 500)""")
        except Exception as exc:
            log(f"⚠️ map scan metadata save failed: {exc}")

        # не пропускаем цикл, если есть карусели
        if last_map_sig == map_sig and not new_ids and not clusters_list:
            log("⏭ same layout & no new singles & no clusters → skip cycle")
            time.sleep(0.4); continue
        last_map_sig = map_sig

        session_dir=None
        def ensure_session_for_first_save():
            nonlocal session_dir
            if session_dir is None:
                ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")[:-4]
                session_dir = os.path.join(LOG_BASE, ts)
                os.makedirs(session_dir, exist_ok=True)
                shutil.copy2(start_tmp, os.path.join(session_dir, "start.xml"))
                log(f"📦 session started: {os.path.basename(session_dir)}")
            return session_dir

        saved_any=0
        map_needs_rescan=False
        # One DB connection per scan cycle. Never alter the original watcher.
        gig_db = db_open(os.path.join(DOWNLOADS, "roadie_gigs.sqlite3"))
        cycle_cards = {}
        cycle_total = None
        cycle_ambiguous = False

        def visible_position(xml_path):
            """Read the one actually visible carousel card, not XML neighbors."""
            try:
                active = []
                for node in ET.parse(xml_path).getroot().iter():
                    if node.get("resource-id", "").split("/")[-1] != "position_in_stack":
                        continue
                    bounds = node.get("bounds", "")
                    m = POS_RE.match(node.get("text", ""))
                    if m and bounds and bounds != "[0,0][0,0]":
                        active.append((int(m.group(1)), int(m.group(2))))
                return active[0] if len(active) == 1 else None
            except Exception as exc:
                log(f"⚠️ active position unavailable: {exc}")
                return None

        def capture_cards(xml_path):
            nonlocal cycle_total, cycle_ambiguous
            try:
                nodes = store_parse(xml_path)
                positions, cards = store_fields(nodes)
            except Exception as ex:
                log(f"⚠️ card parse: {ex}")
                return
            if positions:
                cycle_total = max([cycle_total or 0] + [total for _,_,total in positions])
            for pos, card in cards.items():
                if pos in cycle_cards and cycle_cards[pos]["key"] != card["key"]:
                    cycle_ambiguous = True
                cycle_cards[pos] = card

        def record_cards_if_complete():
            # No disappearance inference from failed/partial carousel scans.
            if cycle_ambiguous or not cycle_total or len(cycle_cards) != cycle_total:
                log(f"⚠️ DB scan incomplete/ambiguous: {len(cycle_cards)}/{cycle_total}")
                return
            if len({v["key"] for v in cycle_cards.values()}) != cycle_total:
                log("⚠️ DB duplicate key in carousel; skip")
                return
            stamp = datetime.now().isoformat(timespec="seconds")
            with gig_db:
                gig_db.execute("""CREATE TABLE IF NOT EXISTS verified_carousel_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT NOT NULL,
                    expected_cards INTEGER NOT NULL,
                    cards_json TEXT NOT NULL
                )""")
                import json
                snapshot = [dict(card, position=pos) for pos, card in sorted(cycle_cards.items())]
                gig_db.execute(
                    "INSERT INTO verified_carousel_snapshots (observed_at, expected_cards, cards_json) VALUES (?,?,?)",
                    (stamp, cycle_total, json.dumps(snapshot, ensure_ascii=False))
                )
                gig_db.execute("""DELETE FROM verified_carousel_snapshots WHERE id NOT IN
                    (SELECT id FROM verified_carousel_snapshots ORDER BY id DESC LIMIT 500)""")
                for card in cycle_cards.values():
                    k = card["key"]
                    old = gig_db.execute("SELECT last_price FROM gigs WHERE gig_key=?", (k,)).fetchone()
                    event = "NEW" if old is None else ("PRICE_CHANGED" if old[0] != card["price"] else None)
                    gig_db.execute("""
                      INSERT INTO gigs (gig_key,miles,deliveries,first_seen,last_seen,last_price,last_minutes,fit)
                      VALUES (?,?,?,?,?,?,?,?)
                      ON CONFLICT(gig_key) DO UPDATE SET
                        last_seen=excluded.last_seen,last_price=excluded.last_price,
                        last_minutes=excluded.last_minutes,fit=excluded.fit
                    """, (k,card["miles"],card["deliveries"],stamp,stamp,
                          card["price"],card["minutes"],card["fit"]))
                    if event:
                        gig_db.execute("""INSERT INTO changes
                          (seen_at,gig_key,event,old_price,new_price,source)
                          VALUES(?,?,?,?,?,?)""",
                          (stamp,k,event,old[0] if old else None,card["price"],"live"))
                        log(f"💾 {event}: {k} ${old[0] if old else '-'} → ${card['price']}")

        def open_destination_if_needed(xml_path):
            # False means the carousel changed or navigation is uncertain.
            # Only the visible active card, never zero-bounds neighbors.
            try:
                root = ET.parse(xml_path).getroot()
                candidates = []
                for node in root.iter():
                    rid = node.get("resource-id","").split("/")[-1]
                    if rid == "position_in_stack":
                        bounds = node.get("bounds","")
                        if bounds and bounds != "[0,0][0,0]":
                            m = POS_RE.match(node.get("text",""))
                            if m: candidates.append((int(m.group(1)),bounds))
                if not candidates:
                    summaries = [
                        n for n in root.iter()
                        if n.get("resource-id", "").split("/")[-1] == "gig_summary_card"
                        and n.get("bounds", "") not in ("", "[0,0][0,0]")
                    ]
                    if len(summaries) == 1:
                        candidates = [(1, summaries[0].get("bounds", ""))]
                if len(candidates) != 1:
                    return
                position, bounds = candidates[0]
                card = cycle_cards.get(position)
                if not card:
                    return
                k = card["key"]
                known = gig_db.execute("SELECT destination FROM gigs WHERE gig_key=?", (k,)).fetchone()
                if known and known[0]:
                    return
                # Position bounds sit in the top right; tap inside the card
                # near its price, safely inside the gig_card_pager.
                cx,cy = get_bounds_center(bounds)
                if "position_in_stack" in {n.get("resource-id", "").split("/")[-1] for n in root.iter()}:
                    tap(550, min(2180,cy+205))
                else:
                    tap(cx, cy)
                time.sleep(SLEEP_AFTER_TAP)
                detail_path = os.path.join(ensure_session_for_first_save(),
                                           f"destination_{position:03d}.xml")
                if not dump_xml_checked(detail_path):
                    log("⚠️ detail dump failed")
                    back(); time.sleep(SLEEP_AFTER_BACK)
                    return
                detail_nodes = store_parse(detail_path)
                if any(rid=="gig_card_pager" for rid,_,_ in detail_nodes):
                    log("⚠️ tap did not open detail; do not navigate blindly")
                    return
                cities = [t for _,t,_ in detail_nodes if CITY.fullmatch(t)]
                detail_texts = [t for _,t,_ in detail_nodes if t]
                route = next((ROUTE.match(t) for t in detail_texts if ROUTE.match(t)), None)
                deliveries = next((DELIVERIES.match(t) for t in detail_texts if DELIVERIES.match(t)), None)
                detail_key = gig_key(route.group(1), deliveries.group(1)) if route and deliveries else None
                if detail_key != k:
                    log(f"⚠️ detail changed: expected {k}, got {detail_key}; skipping destination")
                    cities = []
                if len(cities) >= 2:
                    stamp = datetime.now().isoformat(timespec="seconds")
                    cargo = extract_cargo(detail_path)
                    with gig_db:
                        gig_db.execute("""
                          INSERT INTO gigs(gig_key,miles,deliveries,origin,destination,
                                           total_weight_lbs,max_weight_lbs,max_dimension_in,
                                           max_dimension_raw,total_items,first_seen,last_seen)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                          ON CONFLICT(gig_key) DO UPDATE SET
                            origin=excluded.origin,
                            destination=excluded.destination,
                            total_weight_lbs=coalesce(excluded.total_weight_lbs, gigs.total_weight_lbs),
                            max_weight_lbs=coalesce(excluded.max_weight_lbs, gigs.max_weight_lbs),
                            max_dimension_in=coalesce(excluded.max_dimension_in, gigs.max_dimension_in),
                            max_dimension_raw=coalesce(excluded.max_dimension_raw, gigs.max_dimension_raw),
                            total_items=coalesce(excluded.total_items, gigs.total_items)
                        """, (k,card["miles"],card["deliveries"],cities[0],cities[1],
                              cargo["total_weight_lbs"], cargo["max_weight_lbs"],
                              cargo["max_dimension_in"], cargo["max_dimension_raw"],
                              cargo["total_items"], stamp, stamp))
                    cargo_tag = ""
                    if cargo["total_weight_lbs"] is not None:
                        cargo_tag += f" | Wt={cargo['total_weight_lbs']:g}lbs"
                    if cargo["max_dimension_raw"]:
                        cargo_tag += f" MaxDim={cargo['max_dimension_raw']}"
                    if cargo["max_weight_lbs"] is not None:
                        cargo_tag += f" Hvy={cargo['max_weight_lbs']:g}lbs"
                    log(f"📍 {k}: {cities[0]} → {cities[1]}{cargo_tag}")
                else:
                    log(f"⚠️ destination missing for {k}")
                back(); time.sleep(SLEEP_AFTER_BACK)
                verify = os.path.join(TMP_DIR,"verify_return.xml")
                if dump_xml_checked(verify):
                    positions = all_positions(verify)
                    active = []
                    for n in ET.parse(verify).getroot().iter():
                        if n.get("resource-id","").split("/")[-1] == "position_in_stack":
                            b = n.get("bounds","")
                            m = POS_RE.match(n.get("text",""))
                            if m and b != "[0,0][0,0]":
                                active.append(int(m.group(1)))
                    _, returned_cards = store_fields(store_parse(verify))
                    if not active and observed_screen(verify) is Screen.CAROUSEL:
                        summaries = [
                            n for n in ET.parse(verify).getroot().iter()
                            if n.get("resource-id", "").split("/")[-1] == "gig_summary_card"
                            and n.get("bounds", "") not in ("", "[0,0][0,0]")
                        ]
                        if len(summaries) == 1:
                            active = [1]
                    if len(active) != 1 or active[0] != position or returned_cards.get(position,{}).get("key") != k:
                        log(f"🔄 carousel changed on return: {k}, position={position}, active={active}; rescan next cycle")
                        return False
                else:
                    log("🔄 cannot verify return; rescan next cycle")
                    return False
                return True
            except Exception as ex:
                log(f"⚠️ destination lookup error: {ex}")
                return False


        # ---- 1) КЛАСТЕРЫ ----
        if clusters_list:
            for cl_desc, cl_bounds in clusters_list:
                if map_needs_rescan:
                    log("🔄 map coordinates stale after previous carousel; rescan next cycle")
                    break
                cx, cy = get_bounds_center(cl_bounds)
                log(f"📦 cluster tap '{cl_desc}' at ({cx},{cy}) [bounds={cl_bounds}]"); tick("before CLUSTER TAP")
                tap(cx,cy); time.sleep(SLEEP_AFTER_TAP); tick("after CLUSTER TAP+sleep")

                # ── карта 1: дампим TMP → зеркалим в сессию → POS по сессионному файлу
                first_xml_tmp  = os.path.join(TMP_DIR, "carousel_01_detail.xml")
                if not dump_xml_checked(first_xml_tmp):
                    log("⛔ cluster transition unverified; defer until next cycle")
                    map_needs_rescan = True
                    break
                session_dir = ensure_session_for_first_save()
                first_xml_sess = os.path.join(session_dir, "carousel_01.xml")
                try:
                    shutil.copy2(first_xml_tmp, first_xml_sess)
                    log(f"📄 mirrored TMP → session: {os.path.basename(first_xml_sess)}")
                except Exception as e:
                    log(f"⚠️ mirror error: {e}")

                heartbeat("CAROUSEL")
                c1, t1, raw1 = wait_pos(first_xml_sess)
                if c1 and t1:
                    map_needs_rescan = True
                    # N alone is not a change detector: revisit every cycle.
                    maybe_save_detail(first_xml_sess, "carousel_01_info.csv",
                                      ensure_session_for_first_save, saved_card_sigs)
                    capture_cards(first_xml_sess)
                    if open_destination_if_needed(first_xml_sess) is False:
                        log("🔄 stopping this carousel pass after change")
                        back(); time.sleep(SLEEP_AFTER_BACK)
                        continue
                    active_start = visible_position(first_xml_sess)
                    if not active_start:
                        log('⚠️ no unique active card; abandon carousel pass')
                        back(); time.sleep(SLEEP_AFTER_BACK)
                        continue
                    last_position = active_start[0]
                    total = t1
                    stall = 0
                    i = 1
                    while i < MAX_CARDS and last_position < total:
                        i += 1
                        swipe(CAR_SWIPE_X1, CAR_SWIPE_Y, CAR_SWIPE_X2, CAR_SWIPE_Y, SWIPE_MS)
                        time.sleep(SLEEP_AFTER_SWIPE)
                        cur_xml_tmp = os.path.join(TMP_DIR, f"carousel_{i:02d}_detail.xml")
                        if not dump_xml_checked(cur_xml_tmp):
                            log("⚠️ carousel dump failed; incomplete")
                            break
                        cur_xml_sess = os.path.join(session_dir, f"carousel_{i:02d}.xml")
                        shutil.copy2(cur_xml_tmp, cur_xml_sess)
                        heartbeat("CAROUSEL")
                        positions = all_positions(cur_xml_sess)
                        active_now = visible_position(cur_xml_sess)
                        if active_now:
                            current, observed_total = active_now
                            if observed_total != total:
                                log(f"🔄 carousel count changed {total} → {observed_total}; rescan next cycle")
                                cycle_ambiguous = True
                                break
                            if current > last_position:
                                last_position = current
                                stall = 0
                            else:
                                stall += 1
                        else:
                            stall += 1
                        log(f"📍 positions={positions} progress={last_position}/{total} stall={stall}")
                        maybe_save_detail(cur_xml_sess, f"carousel_{i:02d}_info.csv",
                                          ensure_session_for_first_save, saved_card_sigs)
                        capture_cards(cur_xml_sess)
                        if open_destination_if_needed(cur_xml_sess) is False:
                            log("🔄 stopping changed carousel pass")
                            break
                        if stall >= MAX_STALL_SWIPES:
                            log(f"⛔ carousel stalled; last={last_position}/{total}")
                            break
                    log(f"📍 carousel finished at {last_position}/{total}; swipes={i-1}")
                    record_cards_if_complete()
                    carousel_lastN[str(cl_bounds)] = total
                    back(); time.sleep(SLEEP_AFTER_BACK)
                    continue

                # No verified carousel: NEVER swipe the map.
                log("⛔ no verified carousel after tap: skip swipes and rescan map")
                map_needs_rescan = True
                # If already on map, BACK would leave the app; avoid blind BACK.
                continue

        # ---- 2) СИНГЛЫ ----
        if map_needs_rescan:
            log("🔄 map rescan required; defer singles to next cycle")
            new_ids=[]
        if new_ids:
            log(f"🎯 singles: total={len(id_nodes)} new={len(new_ids)}")
            for e in new_ids:
                gid=e["desc"]
                x,y=get_bounds_center(e["bounds"])
                log(f"👉 open gig {gid} at ({x},{y})")
                tap(x,y); time.sleep(SLEEP_AFTER_TAP)

                # Read the first summary BEFORE any swipe or detail tap.
                summary_tmp = os.path.join(TMP_DIR, f"{gid}_summary.xml")
                if not dump_xml_checked(summary_tmp):
                    log("⛔ direct summary capture failed; recover next cycle")
                    break
                summary_screen = observed_screen(summary_tmp)
                if summary_screen is not Screen.CAROUSEL:
                    log(f"⛔ unexpected marker result: {summary_screen}; recover next cycle")
                    break
                capture_cards(summary_tmp)
                active_card = cycle_cards.get(1)
                if not active_card:
                    log("⛔ no verified first card fields; recover next cycle")
                    break
                log(f"📦 first card {gid}: {active_card['key']} / {active_card['price']}")
                if open_destination_if_needed(summary_tmp) is False:
                    log("🔄 first card changed; recover next cycle")
                    break
                # A verified counter permits N-1 swipes. No counter means
                # one visible card and absolutely no speculative swipe.
                active_pos = visible_position(summary_tmp)
                if active_pos and active_pos[1] > 1:
                    last_position, total = active_pos
                    stall = 0
                    for i in range(2, min(MAX_CARDS, total) + 1):
                        if last_position >= total:
                            break
                        swipe(CAR_SWIPE_X1, CAR_SWIPE_Y, CAR_SWIPE_X2, CAR_SWIPE_Y, SWIPE_MS)
                        time.sleep(SLEEP_AFTER_SWIPE)
                        cur = os.path.join(TMP_DIR, f"{gid}_card_{i:03d}.xml")
                        if not dump_xml_checked(cur):
                            cycle_ambiguous = True
                            break
                        pos = visible_position(cur)
                        if not pos or pos[1] != total:
                            cycle_ambiguous = True
                            log("🔄 card count/position changed; rescan next cycle")
                            break
                        if pos[0] <= last_position:
                            stall += 1
                            if stall >= MAX_STALL_SWIPES:
                                cycle_ambiguous = True
                                break
                            continue
                        last_position = pos[0]
                        stall = 0
                        capture_cards(cur)
                        if open_destination_if_needed(cur) is False:
                            cycle_ambiguous = True
                            break
                record_cards_if_complete()
                seen.add((gid, e["bounds"]))
                back()
                time.sleep(SLEEP_AFTER_BACK)

        gig_db.close()
        heartbeat("CYCLE_DONE")
        log(f"✅ cycle {cycle} done | saved_any={saved_any}")
        time.sleep(0.5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("🛑 stopped by user")
    except Exception as e:
        log(f"💥 fatal error: {e}")
        sys.exit(1)
