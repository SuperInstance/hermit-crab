#!/usr/bin/env python3
"""
activetrack.py — Segment-based position logger for Hermit Crab.

Replaces the naive ring-buffer tracker with a state machine that emits
segments, anomalies, and events to Cloudflare D1.

Architecture
------------
1. Sample loop: every 5 seconds, capture screen -> extract lat/lon/SOG/depth/
   tide via the sibling tzpro_extract.py.
2. Rolling window: 15-second buffer of the last 3 samples for current
   heading/SOG smoothing.
3. Segment state machine: an open segment accumulates start point, duration,
   running mean/var of SOG and COG. It CLOSES when any threshold is crossed:
   SOG delta > 0.3 kn sustained 3+ samples, COG change > 5 deg, depth change
   > 2 fm, elapsed > 15 minutes, or a manual event. On close, compute distance
   from start, write segment to D1, start a new segment.
4. Anomalies: when thresholds cross, emit an anomaly record to D1.
5. Events: logged manually via --event / --catch flags; attached to current
   segment.

Usage
-----
    # Start continuous capture loop
    python activetrack.py

    # Or capture once
    python activetrack.py --once

    # Log an event (attaches to current segment)
    python activetrack.py --event "gear in the water" --tags "trolling,chinook"

    # Log a catch
    python activetrack.py --catch 2 --species "king salmon"

    # Current status
    python activetrack.py --status
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import math
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Sibling modules live in the same directory as this script.
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORKSPACE)

import tzpro_extract  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_NAME = "hermit-crab-memory-db"

# wrangler is invoked as `wrangler.exe` from PATH per build instructions.
WRANGLER_BIN = shutil.which("wrangler.exe") or shutil.which("wrangler") or "wrangler.exe"

CAPTURE_SCRIPT = os.path.join(WORKSPACE, "capture_monitor2.ps1")
SCREENSHOT_PATH = os.path.join(
    os.environ.get("TEMP", "/tmp"), "tzpro_monitor2.png"
)

STATE_FILE = os.path.join(WORKSPACE, "activetrack_state.json")

SAMPLE_INTERVAL_S = 5          # capture loop cadence
ROLLING_WINDOW_SAMPLES = 3     # last N samples for smoothing (~15s)

# Segment thresholds
THRESH_SOG_KN = 0.3            # sustained SOG change
THRESH_SOG_SUSTAINED_N = 3     # samples required to confirm a SOG change
THRESH_COG_DEG = 5.0           # COG change
THRESH_DEPTH_FM = 2.0          # depth band change
THRESH_ELAPSED_S = 15 * 60     # force-close after 15 minutes

# Screenshot policy: at most one per hour unless conditions change.
SCREENSHOT_MIN_GAP_S = 3600


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def build_logger(verbose: bool = False) -> logging.Logger:
    log = logging.getLogger("activetrack")
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    return log


LOG = build_logger()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Sample:
    """A single extracted navigation sample."""
    ts: str                       # ISO-8601 timestamp
    lat: Optional[float]
    lon: Optional[float]
    sog: Optional[float]          # knots
    cog: Optional[float]          # degrees magnetic
    depth: Optional[float]        # fathoms
    tide: Optional[float]         # feet
    chart_scale: Optional[float]
    confidence: dict[str, str] = field(default_factory=dict)

    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass
class Segment:
    """An open or closed segment."""
    id: str
    start_ts: str
    start_lat: Optional[float]
    start_lon: Optional[float]
    end_ts: Optional[str] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None
    sog_samples: list[float] = field(default_factory=list)
    cog_samples: list[float] = field(default_factory=list)
    depth_samples: list[float] = field(default_factory=list)
    tide_samples: list[float] = field(default_factory=list)
    chart_scale: Optional[float] = None
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    closed: bool = False

    # --- statistics ------------------------------------------------------
    def mean(self, xs: list[float]) -> Optional[float]:
        return sum(xs) / len(xs) if xs else None

    def variance(self, xs: list[float]) -> Optional[float]:
        if len(xs) < 2:
            return 0.0
        m = self.mean(xs) or 0.0
        return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)

    def cog_mean(self) -> Optional[float]:
        # Circular mean for headings.
        if not self.cog_samples:
            return None
        i = sum(math.sin(math.radians(c)) for c in self.cog_samples)
        c = sum(math.cos(math.radians(c)) for c in self.cog_samples)
        if c == 0 and i == 0:
            return self.mean(self.cog_samples)
        deg = math.degrees(math.atan2(i, c))
        return (deg + 360.0) % 360.0

    def sog_mean(self) -> Optional[float]:
        return self.mean(self.sog_samples)

    def sog_var(self) -> Optional[float]:
        return self.variance(self.sog_samples)

    def cog_var(self) -> Optional[float]:
        return self.variance(self.cog_samples)

    def depth_mean(self) -> Optional[float]:
        return self.mean(self.depth_samples)

    def depth_var(self) -> Optional[float]:
        return self.variance(self.depth_samples)

    def tide_mean(self) -> Optional[float]:
        return self.mean(self.tide_samples)

    def duration_s(self) -> int:
        if not self.end_ts:
            return 0
        try:
            start = _dt.datetime.fromisoformat(self.start_ts)
            end = _dt.datetime.fromisoformat(self.end_ts)
            return int((end - start).total_seconds())
        except ValueError:
            return 0

    def distance_nm(self) -> float:
        """Great-circle distance from start to end in nautical miles."""
        if self.start_lat is None or self.start_lon is None:
            return 0.0
        if self.end_lat is None or self.end_lon is None:
            return 0.0
        return haversine_nm(
            self.start_lat, self.start_lon, self.end_lat, self.end_lon
        )

    def vector(self) -> list[float]:
        if None in (self.start_lat, self.start_lon, self.end_lat, self.end_lon):
            return [0.0, 0.0]
        return [
            round((self.end_lat or 0.0) - (self.start_lat or 0.0), 6),
            round((self.end_lon or 0.0) - (self.start_lon or 0.0), 6),
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "start_lat": self.start_lat,
            "start_lon": self.start_lon,
            "end_lat": self.end_lat,
            "end_lon": self.end_lon,
            "vector": self.vector(),
            "sog_mean": self.sog_mean(),
            "sog_var": self.sog_var(),
            "cog_mean": self.cog_mean(),
            "cog_var": self.cog_var(),
            "depth_mean": self.depth_mean(),
            "depth_var": self.depth_var(),
            "tide_mean": self.tide_mean(),
            "chart_scale": self.chart_scale,
            "duration_s": self.duration_s(),
            "distance_nm": round(self.distance_nm(), 3),
            "tags": ",".join(self.tags),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two lat/lon points in nautical miles."""
    R_NM = 3440.065  # Earth radius in nautical miles
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2.0 * R_NM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def cog_delta(a: float, b: float) -> float:
    """Smallest absolute difference between two headings in degrees."""
    d = (b - a + 360.0) % 360.0
    if d > 180.0:
        d = 360.0 - d
    return d


# ---------------------------------------------------------------------------
# SOG smoother (rolling median filter)
# ---------------------------------------------------------------------------

class SogSmoother:
    """
    Rolling median filter for SOG values to smooth ±0.1 kn OCR noise.

    Tesseract OCR on the dark-theme SOG font fluctuates by ±0.1 kn between
    consecutive captures even when the actual vessel speed is steady. This
    filter applies a rolling median over the last N samples to suppress
    those spikes before they reach the segment state machine.

    The median is preferred over the mean because it is robust to single-sample
    OCR spikes (e.g. 1.5 -> 9.5 from a stray character). The window size of 3
    (default) adds one sample of latency (~5 s) which is negligible for
    segment-based tracking.
    """

    def __init__(self, window_size: int = 3):
        self._window: list[float] = []
        self.window_size = max(1, window_size)

    def smooth(self, raw_sog: Optional[float]) -> Optional[float]:
        """Return the median of the rolling window, or None if raw is None."""
        if raw_sog is None:
            # Keep window intact; a None sample shouldn't reset history.
            return None
        self._window.append(raw_sog)
        if len(self._window) > self.window_size:
            self._window.pop(0)
        sorted_vals = sorted(self._window)
        return sorted_vals[len(sorted_vals) // 2]

    def reset(self) -> None:
        self._window.clear()


# ---------------------------------------------------------------------------
# Wrangler / D1 bridge
# ---------------------------------------------------------------------------

def _sql_escape(value: Any) -> str:
    """Render a Python value as a SQL literal for SQLite/D1."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        # NaN/inf guard
        if isinstance(value, float) and not math.isfinite(value):
            return "NULL"
        return repr(value)
    s = str(value)
    # SQLite uses single quotes for string literals; double single quotes inside.
    return "'" + s.replace("'", "''") + "'"


def d1_execute(sql: str, log: logging.Logger = LOG) -> bool:
    """Run a SQL statement against D1 via wrangler. Returns True on success."""
    if not sql.strip():
        return True
    cmd = [
        WRANGLER_BIN,
        "d1", "execute", DB_NAME,
        "--command", sql,
        "--remote",
    ]
    log.debug("wrangler cmd: %s", " ".join(shlex.quote(c) for c in cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        log.error("wrangler not found on PATH (%s)", WRANGLER_BIN)
        return False
    except subprocess.TimeoutExpired:
        log.error("wrangler timed out executing SQL")
        return False

    stderr_text = proc.stderr.strip() if proc.stderr else ""
    stdout_text = proc.stdout.strip() if proc.stdout else ""
    if proc.returncode != 0:
        log.error("wrangler exit %d: %s", proc.returncode, stderr_text)
        return False
    log.debug("wrangler stdout: %s", stdout_text)
    return True


# ---------------------------------------------------------------------------
# D1 writers
# ---------------------------------------------------------------------------

def upsert_track_point(s: Sample, log: logging.Logger = LOG) -> bool:
    sql = (
        "INSERT OR REPLACE INTO track_points "
        "(ts, lat, lon, sog, depth, tide) VALUES "
        f"({_sql_escape(s.ts)}, {_sql_escape(s.lat)}, {_sql_escape(s.lon)}, "
        f"{_sql_escape(s.sog)}, {_sql_escape(s.depth)}, {_sql_escape(s.tide)});"
    )
    return d1_execute(sql, log)


def upsert_segment(seg: Segment, log: logging.Logger = LOG) -> bool:
    d = seg.to_dict()
    sql = (
        "INSERT OR REPLACE INTO segments "
        "(id, start_ts, end_ts, start_lat, start_lon, end_lat, end_lon, "
        "sog_mean, sog_var, cog_mean, cog_var, depth_mean, tide_mean, "
        "duration_s, distance_nm, chart_scale, tags, notes) VALUES "
        f"({_sql_escape(d['id'])}, {_sql_escape(d['start_ts'])}, "
        f"{_sql_escape(d['end_ts'])}, {_sql_escape(d['start_lat'])}, "
        f"{_sql_escape(d['start_lon'])}, {_sql_escape(d['end_lat'])}, "
        f"{_sql_escape(d['end_lon'])}, {_sql_escape(d['sog_mean'])}, "
        f"{_sql_escape(d['sog_var'])}, {_sql_escape(d['cog_mean'])}, "
        f"{_sql_escape(d['cog_var'])}, {_sql_escape(d['depth_mean'])}, "
        f"{_sql_escape(d['tide_mean'])}, {_sql_escape(d['duration_s'])}, "
        f"{_sql_escape(d['distance_nm'])}, {_sql_escape(d['chart_scale'])}, "
        f"{_sql_escape(d['tags'])}, {_sql_escape(d['notes'])});"
    )
    return d1_execute(sql, log)


def insert_anomaly(
    anom_id: str,
    ts: str,
    lat: Optional[float],
    lon: Optional[float],
    atype: str,
    magnitude: Optional[float],
    segment_id: str,
    sog_before: Optional[float] = None,
    sog_after: Optional[float] = None,
    cog_before: Optional[float] = None,
    cog_after: Optional[float] = None,
    details: str = "",
    log: logging.Logger = LOG,
) -> bool:
    sql = (
        "INSERT OR REPLACE INTO anomalies "
        "(id, ts, lat, lon, type, magnitude, segment_id, sog_before, "
        "sog_after, cog_before, cog_after, details) VALUES "
        f"({_sql_escape(anom_id)}, {_sql_escape(ts)}, {_sql_escape(lat)}, "
        f"{_sql_escape(lon)}, {_sql_escape(atype)}, {_sql_escape(magnitude)}, "
        f"{_sql_escape(segment_id)}, {_sql_escape(sog_before)}, "
        f"{_sql_escape(sog_after)}, {_sql_escape(cog_before)}, "
        f"{_sql_escape(cog_after)}, {_sql_escape(details)});"
    )
    return d1_execute(sql, log)


def insert_event(
    evt_id: str,
    ts: str,
    lat: Optional[float],
    lon: Optional[float],
    etype: str,
    description: str,
    tags: str,
    segment_id: str,
    catch_count: Optional[int] = None,
    species: str = "",
    log: logging.Logger = LOG,
) -> bool:
    sql = (
        "INSERT OR REPLACE INTO events "
        "(id, ts, lat, lon, type, description, tags, segment_id, "
        "catch_count, species) VALUES "
        f"({_sql_escape(evt_id)}, {_sql_escape(ts)}, {_sql_escape(lat)}, "
        f"{_sql_escape(lon)}, {_sql_escape(etype)}, {_sql_escape(description)}, "
        f"{_sql_escape(tags)}, {_sql_escape(segment_id)}, "
        f"{_sql_escape(catch_count)}, {_sql_escape(species)});"
    )
    return d1_execute(sql, log)


# ---------------------------------------------------------------------------
# ID generators
# ---------------------------------------------------------------------------

def _id(prefix: str) -> str:
    return f"{prefix}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"


def new_segment_id() -> str:
    return _id("seg")


def new_anomaly_id() -> str:
    return _id("anom")


def new_event_id() -> str:
    return _id("evt")


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def state_to_dict(seg: Segment, window: list[Sample],
                  sog_sustain_count: int, sog_sustain_baseline: Optional[float],
                  last_screenshot_ts: Optional[str],
                  last_chart_scale: Optional[float]) -> dict[str, Any]:
    return {
        "segment": asdict(seg) if False else _segment_to_state(seg),
        "window": [_sample_to_state(s) for s in window],
        "sog_sustain_count": sog_sustain_count,
        "sog_sustain_baseline": sog_sustain_baseline,
        "last_screenshot_ts": last_screenshot_ts,
        "last_chart_scale": last_chart_scale,
    }


def _segment_to_state(seg: Segment) -> dict[str, Any]:
    return {
        "id": seg.id,
        "start_ts": seg.start_ts,
        "start_lat": seg.start_lat,
        "start_lon": seg.start_lon,
        "end_ts": seg.end_ts,
        "end_lat": seg.end_lat,
        "end_lon": seg.end_lon,
        "sog_samples": seg.sog_samples,
        "cog_samples": seg.cog_samples,
        "depth_samples": seg.depth_samples,
        "tide_samples": seg.tide_samples,
        "chart_scale": seg.chart_scale,
        "tags": seg.tags,
        "notes": seg.notes,
        "closed": seg.closed,
    }


def _sample_to_state(s: Sample) -> dict[str, Any]:
    return {
        "ts": s.ts,
        "lat": s.lat,
        "lon": s.lon,
        "sog": s.sog,
        "cog": s.cog,
        "depth": s.depth,
        "tide": s.tide,
        "chart_scale": s.chart_scale,
        "confidence": s.confidence,
    }


def _sample_from_state(d: dict[str, Any]) -> Sample:
    return Sample(
        ts=d.get("ts", ""),
        lat=d.get("lat"),
        lon=d.get("lon"),
        sog=d.get("sog"),
        cog=d.get("cog"),
        depth=d.get("depth"),
        tide=d.get("tide"),
        chart_scale=d.get("chart_scale"),
        confidence=d.get("confidence", {}),
    )


def _segment_from_state(d: dict[str, Any]) -> Segment:
    return Segment(
        id=d["id"],
        start_ts=d["start_ts"],
        start_lat=d.get("start_lat"),
        start_lon=d.get("start_lon"),
        end_ts=d.get("end_ts"),
        end_lat=d.get("end_lat"),
        end_lon=d.get("end_lon"),
        sog_samples=d.get("sog_samples", []),
        cog_samples=d.get("cog_samples", []),
        depth_samples=d.get("depth_samples", []),
        tide_samples=d.get("tide_samples", []),
        chart_scale=d.get("chart_scale"),
        tags=d.get("tags", []),
        notes=d.get("notes", ""),
        closed=d.get("closed", False),
    )


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, default=str)
    os.replace(tmp, STATE_FILE)


def load_state() -> Optional[dict[str, Any]]:
    if not os.path.isfile(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_sample(log: logging.Logger = LOG) -> Optional[Sample]:
    """Capture monitor 2 via tzpro_extract and return a Sample."""
    try:
        result = tzpro_extract.extract(SCREENSHOT_PATH, log=LOG)
    except Exception as exc:  # noqa: BLE001
        log.error("extraction failed: %s", exc)
        return None

    fields = result.fields

    def _val(name: str) -> Optional[float]:
        f = fields.get(name)
        if not f:
            return None
        v = f.get("value") if isinstance(f, dict) else getattr(f, "value", None)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _conf(name: str) -> str:
        f = fields.get(name)
        if not f:
            return "NONE"
        c = f.get("confidence") if isinstance(f, dict) else getattr(f, "confidence", "NONE")
        return c or "NONE"

    lat = _val("latitude")
    lon = _val("longitude")
    sog = _val("sog")
    cog = _val("bearing")
    depth = _val("depth")
    tide = _val("tide_height")
    chart_scale = _val("chart_scale")

    sample = Sample(
        ts=result.capture_timestamp or now_iso(),
        lat=lat,
        lon=lon,
        sog=sog,
        cog=cog,
        depth=depth,
        tide=tide,
        chart_scale=chart_scale,
        confidence={
            "latitude": _conf("latitude"),
            "longitude": _conf("longitude"),
            "sog": _conf("sog"),
            "bearing": _conf("bearing"),
            "depth": _conf("depth"),
            "tide_height": _conf("tide_height"),
        },
    )
    return sample


# ---------------------------------------------------------------------------
# Screenshot policy
# ---------------------------------------------------------------------------

def should_save_screenshot(
    state: dict[str, Any],
    sample: Sample,
    first_capture: bool,
    log: logging.Logger = LOG,
) -> bool:
    """Apply the screenshot policy from the design doc."""
    if first_capture:
        log.info("screenshot: first capture")
        return True

    last_ts = state.get("last_screenshot_ts")
    last_scale = state.get("last_chart_scale")

    # Chart scale change
    if sample.chart_scale is not None and last_scale is not None:
        if abs(sample.chart_scale - last_scale) > 1.0:
            log.info("screenshot: chart scale changed (%s -> %s)",
                     last_scale, sample.chart_scale)
            return True

    # Low confidence across all fields -> dialog/alert suspected
    confs = list(sample.confidence.values())
    if confs and all(c in ("LOW", "NONE") for c in confs):
        log.info("screenshot: low confidence across all fields")
        return True

    # Rate limit: max 1 per hour unless conditions change.
    if last_ts:
        try:
            last_dt = _dt.datetime.fromisoformat(last_ts)
            now_dt = _dt.datetime.fromisoformat(sample.ts) if sample.ts else _dt.datetime.now()
            if (now_dt - last_dt).total_seconds() < SCREENSHOT_MIN_GAP_S:
                return False
        except ValueError:
            pass

    return False


def save_screenshot(sample: Sample, log: logging.Logger = LOG) -> str:
    """Copy the live capture PNG into a dated archive."""
    if not os.path.isfile(SCREENSHOT_PATH):
        return ""
    archive_dir = os.path.join(WORKSPACE, "screenshots")
    os.makedirs(archive_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(archive_dir, f"tzpro_{stamp}.png")
    try:
        shutil.copyfile(SCREENSHOT_PATH, dest)
        log.info("screenshot saved: %s", dest)
        return dest
    except OSError as exc:
        log.warning("screenshot copy failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Segment state machine
# ---------------------------------------------------------------------------

def open_new_segment(sample: Sample) -> Segment:
    return Segment(
        id=new_segment_id(),
        start_ts=sample.ts,
        start_lat=sample.lat,
        start_lon=sample.lon,
        chart_scale=sample.chart_scale,
    )


def close_segment(seg: Segment, sample: Sample, log: logging.Logger = LOG) -> Segment:
    """Close the current segment, write it to D1, and open a new one."""
    seg.end_ts = sample.ts
    seg.end_lat = sample.lat
    seg.end_lon = sample.lon
    seg.closed = True
    upsert_segment(seg, log)
    log.info("closed segment %s (%.2f nm, %ds)",
             seg.id, seg.distance_nm(), seg.duration_s())
    return open_new_segment(sample)


def check_thresholds(
    seg: Segment,
    sample: Sample,
    window: list[Sample],
    sog_sustain_count: int,
    sog_sustain_baseline: Optional[float],
    log: logging.Logger = LOG,
) -> tuple[bool, Optional[str], Optional[dict[str, Any]], int, Optional[float]]:
    """
    Returns (should_close, anomaly_type, anomaly_context, new_sustain_count,
    new_sustain_baseline).
    """
    # --- SOG sustained change -------------------------------------------
    new_count = sog_sustain_count
    new_baseline = sog_sustain_baseline
    if sample.sog is not None:
        if sog_sustain_baseline is None:
            new_baseline = sample.sog
            new_count = 0
        else:
            delta = sample.sog - sog_sustain_baseline
            if abs(delta) > THRESH_SOG_KN:
                new_count += 1
            else:
                # Reset baseline when we return to steady state.
                new_baseline = sample.sog
                new_count = 0

        if new_count >= THRESH_SOG_SUSTAINED_N:
            ctx = {
                "sog_before": sog_sustain_baseline,
                "sog_after": sample.sog,
                "cog_before": window[-2].cog if len(window) >= 2 else None,
                "cog_after": sample.cog,
            }
            return (True, "speed_change", ctx, new_count, new_baseline)

    # --- COG change ------------------------------------------------------
    if len(window) >= 2 and window[-2].cog is not None and sample.cog is not None:
        if cog_delta(window[-2].cog, sample.cog) > THRESH_COG_DEG:
            ctx = {
                "sog_before": window[-2].sog,
                "sog_after": sample.sog,
                "cog_before": window[-2].cog,
                "cog_after": sample.cog,
            }
            return (True, "heading_change", ctx, new_count, new_baseline)

    # --- Depth change ----------------------------------------------------
    if seg.depth_samples and sample.depth is not None:
        prev_depth = seg.depth_samples[-1]
        if abs(sample.depth - prev_depth) > THRESH_DEPTH_FM:
            ctx = {
                "sog_before": seg.sog_samples[-1] if seg.sog_samples else None,
                "sog_after": sample.sog,
                "cog_before": seg.cog_samples[-1] if seg.cog_samples else None,
                "cog_after": sample.cog,
            }
            return (True, "depth_change", ctx, new_count, new_baseline)

    # --- Elapsed time ----------------------------------------------------
    try:
        start_dt = _dt.datetime.fromisoformat(seg.start_ts)
        now_dt = _dt.datetime.fromisoformat(sample.ts)
        if (now_dt - start_dt).total_seconds() >= THRESH_ELAPSED_S:
            ctx = {
                "sog_before": seg.sog_samples[0] if seg.sog_samples else None,
                "sog_after": sample.sog,
                "cog_before": seg.cog_samples[0] if seg.cog_samples else None,
                "cog_after": sample.cog,
            }
            return (True, "elapsed_timeout", ctx, new_count, new_baseline)
    except ValueError:
        pass

    return (False, None, None, new_count, new_baseline)


def emit_anomaly(
    seg: Segment,
    sample: Sample,
    atype: str,
    ctx: dict[str, Any],
    log: logging.Logger = LOG,
) -> None:
    if atype == "speed_change":
        magnitude = (ctx.get("sog_after") or 0.0) - (ctx.get("sog_before") or 0.0)
    elif atype == "heading_change":
        a = ctx.get("cog_before")
        b = ctx.get("cog_after")
        magnitude = cog_delta(a, b) if a is not None and b is not None else None
    elif atype == "depth_change":
        a = ctx.get("sog_before")  # placeholder; magnitude set below
        magnitude = None
        if seg.depth_samples and sample.depth is not None:
            magnitude = abs(sample.depth - seg.depth_samples[-1])
    else:
        magnitude = None

    insert_anomaly(
        anom_id=new_anomaly_id(),
        ts=sample.ts,
        lat=sample.lat,
        lon=sample.lon,
        atype=atype,
        magnitude=magnitude,
        segment_id=seg.id,
        sog_before=ctx.get("sog_before"),
        sog_after=ctx.get("sog_after"),
        cog_before=ctx.get("cog_before"),
        cog_after=ctx.get("cog_after"),
        details=json.dumps({"type": atype}, separators=(",", ":")),
        log=log,
    )
    log.info("anomaly %s (%s) on segment %s", atype,
             f"{magnitude:.2f}" if magnitude is not None else "?", seg.id)


# ---------------------------------------------------------------------------
# Sample ingestion
# ---------------------------------------------------------------------------

def ingest_sample(
    sample: Sample,
    seg: Segment,
    window: list[Sample],
    sog_sustain_count: int,
    sog_sustain_baseline: Optional[float],
    log: logging.Logger = LOG,
) -> tuple[Segment, int, Optional[float]]:
    """Process a single sample through the state machine."""
    # Cold-store the raw track point.
    upsert_track_point(sample, log)

    # Append to rolling window.
    window.append(sample)
    if len(window) > ROLLING_WINDOW_SAMPLES:
        window.pop(0)

    # If we have no open segment yet, start one.
    if seg.closed or seg.start_ts == "":
        seg = open_new_segment(sample)

    # Check thresholds BEFORE accumulating this sample (so the "before" value
    # is the previous steady state).
    should_close, atype, ctx, new_count, new_baseline = check_thresholds(
        seg, sample, window, sog_sustain_count, sog_sustain_baseline, log
    )

    if should_close and atype:
        # Emit anomaly attached to the segment about to close.
        emit_anomaly(seg, sample, atype, ctx or {}, log)
        seg = close_segment(seg, sample, log)
        # New segment starts fresh; reset sustain tracking.
        return seg, 0, sample.sog

    # Accumulate into the open segment.
    if sample.sog is not None:
        seg.sog_samples.append(sample.sog)
    if sample.cog is not None:
        seg.cog_samples.append(sample.cog)
    if sample.depth is not None:
        seg.depth_samples.append(sample.depth)
    if sample.tide is not None:
        seg.tide_samples.append(sample.tide)
    if seg.chart_scale is None and sample.chart_scale is not None:
        seg.chart_scale = sample.chart_scale

    return seg, new_count, new_baseline


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_once(log: logging.Logger = LOG) -> int:
    """Capture a single sample, ingest, persist state, exit."""
    state = load_state() or {}
    seg = _segment_from_state(state["segment"]) if state.get("segment") else None
    window = [_sample_from_state(s) for s in state.get("window", [])]
    sog_count = state.get("sog_sustain_count", 0)
    sog_base = state.get("sog_sustain_baseline")
    sog_smoother = SogSmoother()

    sample = extract_sample(log)
    if sample is None:
        return 1

    # Apply SOG smoothing before ingestion to suppress OCR noise.
    sample.sog = sog_smoother.smooth(sample.sog)

    if seg is None or seg.closed:
        seg = open_new_segment(sample)

    seg, sog_count, sog_base = ingest_sample(
        sample, seg, window, sog_count, sog_base, log
    )

    save_state(state_to_dict(
        seg, window, sog_count, sog_base,
        state.get("last_screenshot_ts"), state.get("last_chart_scale"),
    ))
    log.info("sample ingested: %s", _sample_to_state(sample))
    return 0


def run_loop(log: logging.Logger = LOG) -> int:
    """Continuous capture loop: one sample every SAMPLE_INTERVAL_S seconds."""
    state = load_state() or {}
    seg = _segment_from_state(state["segment"]) if state.get("segment") else None
    window = [_sample_from_state(s) for s in state.get("window", [])]
    sog_count = state.get("sog_sustain_count", 0)
    sog_base = state.get("sog_sustain_baseline")
    last_screenshot_ts = state.get("last_screenshot_ts")
    last_chart_scale = state.get("last_chart_scale")
    first_capture = not bool(state)
    sog_smoother = SogSmoother()

    log.info("activetrack loop starting (interval=%ds)", SAMPLE_INTERVAL_S)
    try:
        while True:
            sample = extract_sample(log)
            if sample is None:
                time.sleep(SAMPLE_INTERVAL_S)
                continue

            # Apply SOG smoothing before ingestion to suppress ±0.1 kn OCR noise.
            sample.sog = sog_smoother.smooth(sample.sog)

            if seg is None or seg.closed:
                seg = open_new_segment(sample)

            seg, sog_count, sog_base = ingest_sample(
                sample, seg, window, sog_count, sog_base, log
            )

            # Screenshot policy.
            if should_save_screenshot(
                {"last_screenshot_ts": last_screenshot_ts,
                 "last_chart_scale": last_chart_scale},
                sample, first_capture, log,
            ):
                path = save_screenshot(sample, log)
                if path:
                    last_screenshot_ts = sample.ts
                    last_chart_scale = sample.chart_scale
                first_capture = False
            elif first_capture:
                first_capture = False

            save_state(state_to_dict(
                seg, window, sog_count, sog_base,
                last_screenshot_ts, last_chart_scale,
            ))
            time.sleep(SAMPLE_INTERVAL_S)
    except KeyboardInterrupt:
        log.info("loop interrupted by user")
        # Close the current segment on shutdown so D1 has a clean record.
        if seg and not seg.closed:
            last = window[-1] if window else None
            if last:
                close_segment(seg, last, log)
        save_state(state_to_dict(
            seg, window, sog_count, sog_base,
            last_screenshot_ts, last_chart_scale,
        ))
        return 0


def cmd_event(description: str, tags: str, log: logging.Logger = LOG) -> int:
    """Attach a manual event to the current open segment."""
    state = load_state() or {}
    seg_state = state.get("segment")
    if not seg_state:
        log.error("no open segment; start the tracker first")
        return 1
    seg = _segment_from_state(seg_state)

    sample = extract_sample(log)
    ts = sample.ts if sample else now_iso()
    lat = sample.lat if sample else seg.end_lat
    lon = sample.lon if sample else seg.end_lon

    if sample:
        upsert_track_point(sample, log)

    etype = "manual"
    if any(k in description.lower() for k in ("gear in", "gear down", "deploy")):
        etype = "gear_deployed"
    elif any(k in description.lower() for k in ("gear out", "gear up", "retrieve")):
        etype = "gear_retrieved"

    insert_event(
        evt_id=new_event_id(),
        ts=ts,
        lat=lat,
        lon=lon,
        etype=etype,
        description=description,
        tags=tags,
        segment_id=seg.id,
        log=log,
    )
    if tags:
        for t in tags.split(","):
            t = t.strip()
            if t and t not in seg.tags:
                seg.tags.append(t)
    save_state(state_to_dict(
        seg,
        [_sample_from_state(s) for s in state.get("window", [])],
        state.get("sog_sustain_count", 0),
        state.get("sog_sustain_baseline"),
        state.get("last_screenshot_ts"),
        state.get("last_chart_scale"),
    ))
    log.info("event logged on %s: %s", seg.id, description)
    return 0


def cmd_catch(count: int, species: str, log: logging.Logger = LOG) -> int:
    """Log a catch event attached to the current segment."""
    state = load_state() or {}
    seg_state = state.get("segment")
    if not seg_state:
        log.error("no open segment; start the tracker first")
        return 1
    seg = _segment_from_state(seg_state)

    sample = extract_sample(log)
    ts = sample.ts if sample else now_iso()
    lat = sample.lat if sample else seg.end_lat
    lon = sample.lon if sample else seg.end_lon

    if sample:
        upsert_track_point(sample, log)

    description = f"Caught {count} {species}".strip()
    insert_event(
        evt_id=new_event_id(),
        ts=ts,
        lat=lat,
        lon=lon,
        etype="catch",
        description=description,
        tags=species,
        segment_id=seg.id,
        catch_count=count,
        species=species,
        log=log,
    )
    if species and species not in seg.tags:
        seg.tags.append(species)
    save_state(state_to_dict(
        seg,
        [_sample_from_state(s) for s in state.get("window", [])],
        state.get("sog_sustain_count", 0),
        state.get("sog_sustain_baseline"),
        state.get("last_screenshot_ts"),
        state.get("last_chart_scale"),
    ))
    log.info("catch logged on %s: %d %s", seg.id, count, species)
    return 0


def cmd_status(log: logging.Logger = LOG) -> int:
    """Print the current tracker state as JSON."""
    state = load_state()
    if not state:
        print(json.dumps({"status": "no state — tracker has not been started"},
                         indent=2))
        return 0
    seg = _segment_from_state(state.get("segment", {}))
    window = [_sample_from_state(s) for s in state.get("window", [])]
    out = {
        "segment": seg.to_dict() if seg.start_ts else None,
        "window": [_sample_to_state(s) for s in window],
        "sog_sustain_count": state.get("sog_sustain_count", 0),
        "sog_sustain_baseline": state.get("sog_sustain_baseline"),
        "last_screenshot_ts": state.get("last_screenshot_ts"),
        "last_chart_scale": state.get("last_chart_scale"),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="ActiveTrack — segment-based position logger for Hermit Crab."
    )
    p.add_argument("--once", action="store_true",
                   help="Capture a single sample and exit.")
    p.add_argument("--event", metavar="DESCRIPTION",
                   help="Log a manual event attached to the current segment.")
    p.add_argument("--tags", default="",
                   help="Comma-separated tags for --event.")
    p.add_argument("--catch", type=int, metavar="N",
                   help="Log N fish caught (attaches to current segment).")
    p.add_argument("--species", default="",
                   help="Species for --catch (e.g. 'king salmon').")
    p.add_argument("--status", action="store_true",
                   help="Print current tracker state as JSON and exit.")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable debug logging.")
    args = p.parse_args(argv)

    global LOG
    LOG = build_logger(args.verbose)

    if args.status:
        return cmd_status(LOG)
    if args.event is not None:
        return cmd_event(args.event, args.tags, LOG)
    if args.catch is not None:
        return cmd_catch(args.catch, args.species, LOG)
    if args.once:
        return run_once(LOG)
    return run_loop(LOG)


if __name__ == "__main__":
    raise SystemExit(main())
