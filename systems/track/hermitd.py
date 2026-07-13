"""
hermitd.py — Hermit Crab local daemon.

Runs continuously: capture TZ Pro every 5s → OCR → segment state → batch buffer.
Syncs to D1 on a slow heartbeat (every hour by default).
Serves a localhost dashboard at http://localhost:8654

Usage:
    python hermitd.py              # foreground daemon
    python hermitd.py --daemon     # background (detached)
    python hermitd.py --once       # single capture + flush
    python hermitd.py --status     # quick status
"""

from __future__ import annotations

import json, logging, os, sys, time, signal, threading, re
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Optional

# ── workspace ──
WORKSPACE = Path(__file__).parent.resolve()
sys.path.insert(0, str(WORKSPACE))

from tzpro_extract import extract, capture_via_powershell, DEFAULT_TESSERACT
from PIL import Image

# ── config ──
CFG = {
    "interval": 5,
    "heartbeat": 3600,
    "port": 8654,
}
BUFFER_PATH = WORKSPACE / "cold" / "buffer.jsonl"
STATE_PATH = WORKSPACE / "activetrack_state.json"
CAPTURE_SCRIPT = WORKSPACE / "capture_monitor2.ps1"

log = logging.getLogger("hermitd")

# ── live state (shared between capture loop and dashboard) ──
live = {
    "current": None,        # latest sample dict
    "segment": None,        # current open segment
    "segment_history": [],  # last 20 closed segments (in-memory)
    "samples": [],          # last 300 samples (~25 min at 5s)
    "events": [],           # last 50 events
    "uptime": time.time(),
    "captures": 0,
    "errors": 0,
}
_live_lock = threading.Lock()

# ── sample model ──
def make_sample(result) -> dict:
    f = result.fields
    return {
        "ts": result.capture_timestamp,
        "lat": f["latitude"]["value"],
        "lon": f["longitude"]["value"],
        "sog": f["sog"]["value"],
        "depth": f["depth"]["value"],
        "tide": f["tide_height"]["value"],
        "chart_scale": f["chart_scale"]["value"],
        "conf": {
            "lat": f["latitude"]["confidence"],
            "lon": f["longitude"]["confidence"],
            "sog": f["sog"]["confidence"],
            "tide": f["tide_height"]["confidence"],
        },
    }

# ── segment state machine ──
def new_segment(sample: dict) -> dict:
    return {
        "id": f"seg_{datetime.now():%Y%m%d_%H%M%S}",
        "start_ts": sample["ts"],
        "start_lat": sample["lat"],
        "start_lon": sample["lon"],
        "sog_sum": sample["sog"] or 0,
        "sog_sum_sq": (sample["sog"] or 0) ** 2,
        "sog_n": 1,
        "samples": 1,
        "end_lat": sample["lat"],
        "end_lon": sample["lon"],
        "tide_sum": sample["tide"] or 0,
        "depth_sum": sample["depth"] or 0,
        "chart_scale": sample["chart_scale"],
        "lat_prev": sample["lat"],
        "lon_prev": sample["lon"],
        "sog_base": sample["sog"],
        "sog_sustain": 0,
        "tags": [],
    }

def update_segment(seg: dict, sample: dict) -> bool:
    """Update segment with sample. Returns True if segment should close."""
    seg["samples"] += 1
    seg["end_lat"] = sample["lat"]
    seg["end_lon"] = sample["lon"]
    s = sample["sog"] or 0
    seg["sog_sum"] += s
    seg["sog_sum_sq"] += s ** 2
    seg["sog_n"] += 1
    seg["tide_sum"] += sample["tide"] or 0
    seg["depth_sum"] += sample["depth"] or 0

    # SOG delta check
    if seg["sog_base"] is not None and sample["sog"] is not None:
        delta = abs(sample["sog"] - seg["sog_base"])
        if delta > 0.3:
            seg["sog_sustain"] += 1
        else:
            seg["sog_sustain"] = 0
            seg["sog_base"] = sample["sog"]
        if seg["sog_sustain"] >= 3:
            return True

    # Elapsed time check (15 min max)
    try:
        start = datetime.fromisoformat(seg["start_ts"])
        now = datetime.fromisoformat(sample["ts"])
        if (now - start).total_seconds() > 900:
            return True
    except: pass

    return False

def close_segment(seg: dict) -> dict:
    """Finalize segment stats."""
    n = max(seg["sog_n"], 1)
    mean = seg["sog_sum"] / n
    var = (seg["sog_sum_sq"] / n) - (mean ** 2)
    if var < 0: var = 0
    duration_s = 0
    try:
        start = datetime.fromisoformat(seg["start_ts"])
        end = datetime.fromisoformat(seg.get("end_ts") or seg["start_ts"])
        duration_s = int((end - start).total_seconds())
    except: pass
    # Approximate distance (naive — fine for short segments)
    dlat = seg["end_lat"] - seg["start_lat"]
    dlon = seg["end_lon"] - seg["start_lon"]
    distance_nm = math.sqrt(dlat**2 + (dlon * 0.57)**2) * 60
    tide_mean = seg["tide_sum"] / n if n > 0 else None
    depth_mean = seg["depth_sum"] / n if n > 0 else None
    return {
        "id": seg["id"],
        "start_ts": seg["start_ts"],
        "end_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_lat": seg["start_lat"],
        "start_lon": seg["start_lon"],
        "end_lat": seg["end_lat"],
        "end_lon": seg["end_lon"],
        "sog_mean": round(mean, 2),
        "sog_var": round(var, 4),
        "tide_mean": round(tide_mean, 2) if tide_mean else None,
        "depth_mean": round(depth_mean, 1) if depth_mean else None,
        "duration_s": duration_s,
        "distance_nm": round(distance_nm, 3),
        "chart_scale": seg["chart_scale"],
        "samples": seg["samples"],
        "tags": seg["tags"],
    }

# ── buffer ──
def buffer_append(sample: dict) -> None:
    BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BUFFER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample, separators=(",", ":")) + "\n")

def buffer_flush() -> int:
    """Flush buffer to D1. Returns count of flushed entries."""
    if not BUFFER_PATH.exists():
        return 0
    lines = BUFFER_PATH.read_text(encoding="utf-8").strip().split("\n")
    if not lines or (len(lines) == 1 and not lines[0]):
        return 0
    entries = []
    for line in lines:
        try: entries.append(json.loads(line))
        except: pass
    if not entries:
        return 0

    # Batch insert
    sql = "INSERT OR REPLACE INTO track_points (ts, lat, lon, sog, depth, tide, source, agent_id) VALUES\n"
    vals = []
    for e in entries:
        ts = e["ts"].replace("'", "''")
        lat = e.get("lat", "NULL")
        lon = e.get("lon", "NULL")
        sog = e.get("sog", "NULL")
        dep = e.get("depth", "NULL")
        tide = e.get("tide", "NULL")
        if sog is None or sog == "None": sog = "NULL"
        if dep is None or dep == "None": dep = "NULL"
        if tide is None or tide == "None": tide = "NULL"
        vals.append(f"('{ts}',{lat},{lon},{sog},{dep},{tide},'tzpro','agent:hermit-crab')")

    sql += ",\n".join(vals) + ";"
    wrangler = shutil.which("wrangler") or r"C:\Users\casey\AppData\Roaming\npm\wrangler.CMD"
    import subprocess, shutil
    proc = subprocess.run(
        [wrangler, "d1", "execute", "hermit-crab-memory-db", "--command", sql, "--remote"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, cwd=str(WORKSPACE),
    )
    if proc.returncode == 0:
        # Clear the buffer
        BUFFER_PATH.write_text("", encoding="utf-8")
        return len(entries)
    return 0

# ── capture loop ──
def capture_once() -> Optional[dict]:
    try:
        img_path = capture_via_powershell(str(CAPTURE_SCRIPT), log)
        result = extract(img_path, log=log)
        return make_sample(result)
    except Exception as e:
        log.error("Capture failed: %s", e)
        return None

def capture_loop(stop_event: threading.Event):
    seg = None
    last_flush = time.time()
    log.info("Daemon started — capturing every %ds, syncing every %ds", CFG['interval'], CFG['heartbeat'])

    while not stop_event.is_set():
        t0 = time.time()
        sample = capture_once()
        with _live_lock:
            if sample:
                live["current"] = sample
                live["samples"].append(sample)
                if len(live["samples"]) > 300:
                    live["samples"] = live["samples"][-300:]
                live["captures"] += 1

                # Segment
                if seg is None:
                    seg = new_segment(sample)
                else:
                    seg["end_ts"] = sample["ts"]
                    if update_segment(seg, sample):
                        closed = close_segment(seg)
                        with _live_lock:
                            live["segment_history"].append(closed)
                            if len(live["segment_history"]) > 20:
                                live["segment_history"] = live["segment_history"][-20:]
                        log.info("Segment closed: %s (%.3f nm, %ds)", closed["id"], closed["distance_nm"], closed["duration_s"])
                        # Also write closed segment event to buffer
                        buffer_append({"ts": closed["end_ts"], "event": "segment_close", "segment_id": closed["id"],
                                       "lat": closed["end_lat"], "lon": closed["end_lon"],
                                       "sog_mean": closed["sog_mean"], "distance_nm": closed["distance_nm"],
                                       "duration_s": closed["duration_s"]})
                        seg = new_segment(sample)
                    else:
                        seg["lat_prev"] = sample["lat"]
                        seg["lon_prev"] = sample["lon"]

                # Buffer the sample
                buffer_append(sample)

            live["segment"] = seg

        # Heartbeat flush
        elapsed = time.time() - last_flush
        if elapsed >= CFG['heartbeat']:
            n = buffer_flush()
            if n:
                log.info("Heartbeat: flushed %d entries to D1", n)
            last_flush = time.time()

        # Pace
        dt = time.time() - t0
        sleep = max(0.1, CFG['interval'] - dt)
        stop_event.wait(sleep)

# ── HTTP dashboard ──
class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with _live_lock:
                c = live["current"]
                seg = live["segment"]
                seg_hist = list(live["segment_history"])
                samples = list(live["samples"][-60:])  # last 5 min
            self.wfile.write(self._page(c, seg, seg_hist, samples).encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with _live_lock:
                d = {
                    "current": live["current"],
                    "segment": live["segment"],
                    "segment_history": live["segment_history"][-5:],
                    "samples_5m": len(live["samples"]),
                    "captures": live["captures"],
                    "errors": live["errors"],
                    "uptime_s": int(time.time() - live["uptime"]),
                }
            self.wfile.write(json.dumps(d, indent=2, default=str).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def _page(self, current, segment, seg_hist, samples):
        lat_s = f'{current["lat"]:.6f}' if current and current.get("lat") else "---"
        lon_s = f'{current["lon"]:.6f}' if current and current.get("lon") else "---"
        sog_s = f'{current["sog"]:.1f}' if current and current.get("sog") else "---"
        tide_s = f'{current["tide"]:.2f}' if current and current.get("tide") else "---"
        depth_s = f'{current["depth"]}' if current and current.get("depth") else "---"
        scale_s = f'{current["chart_scale"]}' if current and current.get("chart_scale") else "---"
        ts_s = current["ts"] if current else "---"
        seg_id = segment["id"] if segment else "none"

        seg_html = ""
        for s in reversed(seg_hist[-5:]):
            seg_html += f"<tr><td>{s['id'][:22]}</td><td>{s['sog_mean']}</td><td>{s['distance_nm']}</td><td>{s['duration_s']}s</td><td>{s.get('tide_mean', '')}</td></tr>\n"

        sample_rows = ""
        for s in reversed(samples[-30:]):
            sample_rows += f"<tr><td>{s['ts'][11:19]}</td><td>{s.get('lat',''):.4f}</td><td>{s.get('lon',''):.4f}</td><td>{s.get('sog','')}</td><td>{s.get('tide','')}</td></tr>\n"

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<title>hermit-crab · activelog</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'SF Mono', 'Cascadia Code', monospace; background:#0d1117; color:#c9d1d9; padding:20px; }}
h1 {{ font-size:16px; color:#58a6ff; margin-bottom:12px; letter-spacing:1px; }}
h2 {{ font-size:13px; color:#8b949e; margin:16px 0 6px; text-transform:uppercase; }}
.gauge {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(160px,1fr)); gap:8px; margin-bottom:16px; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:6px; padding:12px; }}
.card .label {{ font-size:10px; color:#8b949e; text-transform:uppercase; }}
.card .value {{ font-size:22px; font-weight:600; color:#f0f6fc; margin-top:2px; }}
.card .value.tide {{ color:#79c0ff; }}
.card .value.sog {{ color:#7ee787; }}
.card .value.depth {{ color:#d2a8ff; }}
.card .value.latlon {{ color:#ffa657; font-size:16px; }}
table {{ width:100%; border-collapse:collapse; font-size:11px; }}
th {{ text-align:left; color:#8b949e; padding:4px 8px; border-bottom:1px solid #30363d; }}
td {{ padding:4px 8px; border-bottom:1px solid #21262d; }}
#meta {{ margin-top:12px; font-size:10px; color:#484f58; }}
</style></head><body>
<h1>🦀 hermit-crab · activelog</h1>
<p style="color:#8b949e;font-size:11px;margin-bottom:12px;">{ts_s} · segment: {seg_id}</p>
<div class="gauge">
  <div class="card"><div class="label">Latitude</div><div class="value latlon">{lat_s}°N</div></div>
  <div class="card"><div class="label">Longitude</div><div class="value latlon">{lon_s}°W</div></div>
  <div class="card"><div class="label">SOG</div><div class="value sog">{sog_s} kn</div></div>
  <div class="card"><div class="label">Depth</div><div class="value depth">{depth_s} fm</div></div>
  <div class="card"><div class="label">Tide</div><div class="value tide">{tide_s} ft</div></div>
  <div class="card"><div class="label">Chart Scale</div><div class="value" style="font-size:14px;">1:{scale_s}</div></div>
</div>
<h2>Recent Segments</h2>
<table><tr><th>ID</th><th>SOG</th><th>NM</th><th>Dur</th><th>Tide</th></tr>{seg_html}</table>
<h2>Samples (last 2.5 min)</h2>
<table><tr><th>Time</th><th>Lat</th><th>Lon</th><th>SOG</th><th>Tide</th></tr>{sample_rows}</table>
<div id="meta">captures: {live['captures']} · uptime: {int(time.time()-live['uptime'])}s · sync: every {CFG['heartbeat']}s · buffer: {BUFFER_PATH.name}</div>
</body></html>"""

    def log_message(self, fmt, *args): pass  # silence HTTP logs

def run_dashboard(stop_event: threading.Event):
    server = HTTPServer(("0.0.0.0", CFG['port']), DashboardHandler)
    log.info("Dashboard at http://localhost:%d", CFG['port'])
    while not stop_event.is_set():
        server.handle_request()

# ── CLI ──
def main():
    import argparse
    p = argparse.ArgumentParser(description="Hermit Crab daemon")
    p.add_argument("--once", action="store_true", help="Single capture + status")
    p.add_argument("--status", action="store_true", help="Print current state")
    p.add_argument("--flush", action="store_true", help="Force flush buffer to D1")
    p.add_argument("--interval", type=int, default=5, help="Capture interval (s)")
    p.add_argument("--heartbeat", type=int, default=3600, help="D1 sync interval (s)")
    p.add_argument("--daemon", action="store_true", help="Detach to background")
    p.add_argument("--port", type=int, default=8654, help="Dashboard port")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")

    # Override config from CLI args using a mutable config
    cfg = {"interval": args.interval, "heartbeat": args.heartbeat, "port": args.port}

    if args.flush:
        n = buffer_flush()
        print(f"Flushed {n} entries to D1")
        return

    if args.once:
        sample = capture_once()
        if sample:
            print(json.dumps(sample, indent=2, default=str))
            buffer_append(sample)
        else:
            print("Capture failed")
        return

    if args.status:
        with _live_lock:
            print(json.dumps({
                "current": live["current"],
                "segment": live["segment"],
                "segments_closed": len(live["segment_history"]),
                "samples_buffered": len(live["samples"]),
                "captures": live["captures"],
            }, indent=2, default=str))
        return

    if args.daemon:
        print("Background mode not implemented yet — run without --daemon")
        return

    # Foreground daemon
    stop = threading.Event()
    t1 = threading.Thread(target=capture_loop, args=(stop,), daemon=True)
    t2 = threading.Thread(target=run_dashboard, args=(stop,), daemon=True)

    print(f"hermitd — Hermit Crab daemon")
    print(f"  Capture:  every {cfg['interval']}s")
    print(f"  Sync:     every {cfg['heartbeat']}s ({cfg['heartbeat']//60} min)")
    print(f"  Dashboard: http://localhost:{cfg['port']}")
    print(f"  Buffer:   {BUFFER_PATH}")
    print()

    # Apply CLI overrides
    CFG['interval'] = cfg['interval']
    CFG['heartbeat'] = cfg['heartbeat']
    CFG['port'] = cfg['port']

    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop.set()
        t1.join(timeout=5)
        t2.join(timeout=1)
        n = buffer_flush()
        print(f"Flushed {n} remaining entries to D1")
        print("Done.")

if __name__ == "__main__":
    main()
