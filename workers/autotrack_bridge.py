#!/usr/bin/env python3
"""
autotrack_bridge.py — Bridge between ActiveTrack (vessel state) and the room
coordinator.

Reads ActiveTrack state from the JSON state file and optionally from the
NMEA TCP stream (port 6006). Periodically synthesises "observation" tasks
for the room coordinator, including:

  - Position updates (lat, lon, SOG, COG, depth, tide)
  - Anomaly flags (threshold crossings)
  - Tide / depth changes

Architecture
------------
  ActiveTrack state file --> autotrack_bridge --> tasks.json --> room_coordinator
  NMEA TCP :6006         -->                     (observation tasks)

Usage
-----
    # Standard bridge loop (30s interval, syncs every cycle)
    python autotrack_bridge.py

    # Single sync then exit
    python autotrack_bridge.py --once

    # Custom interval
    python autotrack_bridge.py --interval 60
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import socket
import struct
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HERMIT_CRAB_ROOT = Path(__file__).resolve().parent.parent
ACTIVETRACK_STATE_PATH = HERMIT_CRAB_ROOT / "activetrack_state.json"
OUTBOX_DIR = HERMIT_CRAB_ROOT / "outbox"
TASKS_PATH = OUTBOX_DIR / "tasks.json"
BRIDGE_STATE_PATH = OUTBOX_DIR / "autotrack_bridge_state.json"

NMEA_HOST = "127.0.0.1"
NMEA_PORT = 6006
NMEA_TIMEOUT_S = 3.0

DEFAULT_POLL_INTERVAL_S = 30

# Task types produced by this bridge
OBSERVATION_TASK_TYPES = {
    "position_update": "observation",
    "anomaly_flag": "structural",
    "tide_change": "prose",
    "depth_change": "structural",
    "segment_event": "synthesis",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] autotrack_bridge: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(OUTBOX_DIR / "autotrack_bridge.log")),
    ],
)
log = logging.getLogger("autotrack_bridge")


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path, default: dict | None = None) -> dict[str, Any]:
    if default is None:
        default = {}
    try:
        if not path.exists():
            return default
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read %s: %s", path, exc)
        return default


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# ActiveTrack state reader
# ---------------------------------------------------------------------------

def read_activetrack_state() -> dict[str, Any]:
    """
    Load the current vessel state from *activetrack_state.json*.

    Returns a dict with at least these fields (may be partial if file is empty):
      - segment: current segment info (id, start_ts, start_lat, start_lon, ...)
      - window: rolling window of position samples
    """
    state = _read_json(ACTIVETRACK_STATE_PATH, default={"segment": {}, "window": []})
    return state


def get_latest_sample(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the newest sample from the ActiveTrack rolling window, or None."""
    window = state.get("window", [])
    return window[-1] if window else None


# ---------------------------------------------------------------------------
# NMEA TCP reader
# ---------------------------------------------------------------------------

def read_nmea_line() -> str | None:
    """
    Attempt to read one NMEA0183 sentence from the TCP stream at
    *NMEA_HOST:NMEA_PORT*.

    Returns the raw sentence string, or *None* if the connection fails or
    times out.
    """
    try:
        sock = socket.create_connection(
            (NMEA_HOST, NMEA_PORT), timeout=NMEA_TIMEOUT_S
        )
        # NMEA sentences end with \r\n
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(1)
            if not chunk:
                break
            buf += chunk
        sock.close()
        line = buf.decode("ascii", errors="replace").strip()
        log.debug("NMEA: %s", line[:80])
        return line if line else None
    except (ConnectionRefusedError, TimeoutError, OSError) as exc:
        log.debug("NMEA read failed (%s) — skipping", exc)
        return None


def parse_nmea_position(sentence: str) -> dict[str, Any] | None:
    """
    Parse a GLL, GGA, or RMB NMEA sentence for position data.

    Returns a dict with keys *lat*, *lon*, *sog*, *depth* if parsed, else None.
    """
    if not sentence or not sentence.startswith("$"):
        return None

    fields = sentence.split(",")
    talker_id = fields[0] if fields else ""

    parsed: dict[str, Any] = {}

    # $GPGLL — Geographic Position (Latitude/Longitude)
    # $GPGLL,lat,N,lon,E,time,status*cc
    if "GLL" in talker_id and len(fields) >= 7:
        try:
            lat_raw = fields[1]
            if lat_raw:
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                parsed["lat"] = lat_deg + lat_min / 60.0
                if fields[2] == "S":
                    parsed["lat"] = -parsed["lat"]

            lon_raw = fields[3]
            if lon_raw:
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                parsed["lon"] = lon_deg + lon_min / 60.0
                if fields[4] == "W":
                    parsed["lon"] = -parsed["lon"]
        except (ValueError, IndexError):
            pass

    # $GPGGA — Global Positioning System Fix Data
    if "GGA" in talker_id and len(fields) >= 10:
        try:
            lat_raw = fields[2]
            if lat_raw:
                lat_deg = float(lat_raw[:2])
                lat_min = float(lat_raw[2:])
                parsed["lat"] = lat_deg + lat_min / 60.0
                if fields[3] == "S":
                    parsed["lat"] = -parsed["lat"]

            lon_raw = fields[4]
            if lon_raw:
                lon_deg = float(lon_raw[:3])
                lon_min = float(lon_raw[3:])
                parsed["lon"] = lon_deg + lon_min / 60.0
                if fields[5] == "W":
                    parsed["lon"] = -parsed["lon"]

            if fields[6]:
                parsed["quality"] = int(fields[6])

            if fields[9]:
                parsed["depth"] = float(fields[9])
        except (ValueError, IndexError):
            pass

    # $GPVTG — Course Over Ground and Ground Speed
    if "VTG" in talker_id and len(fields) >= 8:
        try:
            if fields[1]:
                parsed["cog"] = float(fields[1])
            if fields[5]:
                parsed["sog"] = float(fields[5])
        except (ValueError, IndexError):
            pass

    # $SDDBT / $SDDBS — Depth Below Transducer
    if "DBT" in talker_id and len(fields) >= 7:
        try:
            parsed["depth"] = float(fields[3])  # metres
        except (ValueError, IndexError):
            pass

    # $--HDM / $--HDG — Heading
    if "HDM" in talker_id and len(fields) >= 3:
        try:
            parsed["heading"] = float(fields[1])
        except (ValueError, IndexError):
            pass

    return parsed if parsed else None


# ---------------------------------------------------------------------------
# Bridge state (dedup / change detection)
# ---------------------------------------------------------------------------

def load_bridge_state() -> dict[str, Any]:
    """Load persistent bridge state (last-known sample, anomaly flags)."""
    return _read_json(BRIDGE_STATE_PATH, default={
        "last_sample_ts": None,
        "last_tide": None,
        "last_depth": None,
        "last_sog": None,
        "anomaly_count": 0,
        "tasks_created": 0,
    })


def save_bridge_state(state: dict[str, Any]) -> None:
    _write_json(BRIDGE_STATE_PATH, state)


# ---------------------------------------------------------------------------
# Task creation helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _unique_id() -> str:
    return uuid.uuid4().hex[:12]


def make_position_update_task(sample: dict[str, Any]) -> dict[str, Any]:
    """Build an observation task for a vessel position update."""
    return {
        "id": f"pos-{_unique_id()}",
        "task_type": "observation",
        "prompt": "Record vessel position update",
        "source": "autotrack",
        "created": _now_iso(),
        "context": {
            "operation": "position_update",
            "ts": sample.get("ts"),
            "lat": sample.get("lat"),
            "lon": sample.get("lon"),
            "sog": sample.get("sog"),
            "cog": sample.get("cog"),
            "depth": sample.get("depth"),
            "tide": sample.get("tide"),
            "confidence": sample.get("confidence"),
        },
    }


def make_anomaly_task(
    sample: dict[str, Any],
    anomaly_type: str,
    details: str,
) -> dict[str, Any]:
    """Build a structural / anomaly task for threshold crossings."""
    return {
        "id": f"anom-{_unique_id()}",
        "task_type": "structural",
        "prompt": f"Analyse anomaly: {anomaly_type} — {details}",
        "source": "autotrack",
        "created": _now_iso(),
        "context": {
            "operation": "anomaly_flag",
            "anomaly_type": anomaly_type,
            "details": details,
            "ts": sample.get("ts"),
            "lat": sample.get("lat"),
            "lon": sample.get("lon"),
            "sog": sample.get("sog"),
            "tide": sample.get("tide"),
            "depth": sample.get("depth"),
        },
    }


def make_tide_change_task(
    old_tide: float,
    new_tide: float,
    sample: dict[str, Any],
) -> dict[str, Any]:
    """Build a prose task describing a tide height change."""
    delta = new_tide - old_tide
    return {
        "id": f"tide-{_unique_id()}",
        "task_type": "prose",
        "prompt": f"Describe tide change: {old_tide}ft → {new_tide}ft (Δ={delta:+.1f}ft)",
        "source": "autotrack",
        "created": _now_iso(),
        "context": {
            "operation": "tide_change",
            "old_tide": old_tide,
            "new_tide": new_tide,
            "delta": delta,
            "ts": sample.get("ts"),
        },
    }


def make_depth_change_task(
    old_depth: float | None,
    new_depth: float | None,
    sample: dict[str, Any],
) -> dict[str, Any]:
    """Build a structural task for notable depth changes."""
    if old_depth is None or new_depth is None:
        return None
    delta = abs(new_depth - old_depth)
    if delta < 2.0:  # ignore sub-2-metre shifts
        return None
    return {
        "id": f"depth-{_unique_id()}",
        "task_type": "structural",
        "prompt": f"Analyse depth change: {old_depth}m → {new_depth}m (Δ={delta:.1f}m)",
        "source": "autotrack",
        "created": _now_iso(),
        "context": {
            "operation": "depth_change",
            "old_depth": old_depth,
            "new_depth": new_depth,
            "delta": delta,
            "ts": sample.get("ts"),
        },
    }


# ---------------------------------------------------------------------------
# Inject tasks into the room coordinator queue
# ---------------------------------------------------------------------------

def inject_task(task: dict[str, Any]) -> None:
    """Append a single task to the coordinator's tasks.json."""
    data = _read_json(TASKS_PATH, default={"version": 1, "tasks": []})
    if "tasks" not in data:
        data["tasks"] = []
    data["tasks"].append(task)
    _write_json(TASKS_PATH, data)
    log.info("Injected task %s (type=%s)", task["id"], task["task_type"])


def inject_tasks(tasks: list[dict[str, Any]]) -> None:
    """Append multiple tasks to the coordinator's tasks.json atomically."""
    if not tasks:
        return
    data = _read_json(TASKS_PATH, default={"version": 1, "tasks": []})
    if "tasks" not in data:
        data["tasks"] = []
    data["tasks"].extend(tasks)
    _write_json(TASKS_PATH, data)
    log.info("Injected %d task(s) into coordinator queue", len(tasks))


# ---------------------------------------------------------------------------
# Core sync loop
# ---------------------------------------------------------------------------

def sync_activetrack_to_room() -> list[dict[str, Any]]:
    """
    Read the current ActiveTrack state, identify changes, and produce any
    new tasks for the room coordinator.

    Returns the list of created tasks.
    """
    state = read_activetrack_state()
    sample = get_latest_sample(state)

    if not sample:
        log.debug("No samples in ActiveTrack state — nothing to sync")
        return []

    bridge = load_bridge_state()
    tasks: list[dict[str, Any]] = []

    # Always produce a position update for every cycle
    tasks.append(make_position_update_task(sample))

    # Tide change detection
    current_tide = sample.get("tide")
    last_tide = bridge.get("last_tide")
    if (
        current_tide is not None
        and last_tide is not None
        and abs(current_tide - last_tide) >= 0.5
    ):
        tasks.append(make_tide_change_task(last_tide, current_tide, sample))

    # Depth change detection
    current_depth = sample.get("depth")
    last_depth = bridge.get("last_depth")
    depth_task = make_depth_change_task(last_depth, current_depth, sample)
    if depth_task:
        tasks.append(depth_task)

    # SOG anomaly detection (SOG drop > 1 kn or spike > 3 kn)
    current_sog = sample.get("sog")
    last_sog = bridge.get("last_sog")
    if current_sog is not None and last_sog is not None:
        sog_delta = abs(current_sog - last_sog)
        if sog_delta > 3.0:
            tasks.append(make_anomaly_task(
                sample,
                "SOG_SPIKE",
                f"Speed change from {last_sog} to {current_sog} kn",
            ))
        elif current_sog < 0.3 and last_sog >= 1.0:
            tasks.append(make_anomaly_task(
                sample,
                "SOG_DROP",
                f"Speed dropped from {last_sog} to {current_sog} kn — possible stop",
            ))

    # Update bridge state
    bridge["last_sample_ts"] = sample.get("ts")
    bridge["last_tide"] = current_tide
    bridge["last_depth"] = current_depth
    bridge["last_sog"] = current_sog
    bridge["tasks_created"] += len(tasks)
    save_bridge_state(bridge)

    # Insert the tasks into the coordinator queue
    inject_tasks(tasks)

    return tasks


# ---------------------------------------------------------------------------
# NMEA poll — direct read (optional, supplements state file)
# ---------------------------------------------------------------------------

def poll_nmea_directly() -> list[dict[str, Any]]:
    """
    Read NMEA sentences from TCP :6006 and create observation tasks from any
    parsed data.

    This is a lightweight supplement to the state-file-based sync.
    """
    tasks: list[dict[str, Any]] = []
    nmea_line = read_nmea_line()

    if not nmea_line:
        return tasks

    parsed = parse_nmea_position(nmea_line)
    if not parsed:
        return tasks

    parsed["ts"] = _now_iso()
    tasks.append(make_position_update_task(parsed))

    if tasks:
        inject_tasks(tasks)

    return tasks


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_loop(*, once: bool = False, interval_s: int = DEFAULT_POLL_INTERVAL_S) -> None:
    log.info(
        "ActiveTrack bridge started (once=%s, interval=%ds)",
        once,
        interval_s,
    )
    log.info("State file: %s", ACTIVETRACK_STATE_PATH)
    log.info("NMEA TCP: %s:%d", NMEA_HOST, NMEA_PORT)

    cycle = 0
    while True:
        cycle += 1
        log.debug("Bridge cycle %d", cycle)

        # 1. Sync from ActiveTrack state file → tasks
        state_tasks = sync_activetrack_to_room()

        # 2. Optionally poll NMEA directly for live data
        nmea_tasks = poll_nmea_directly()

        total = len(state_tasks) + len(nmea_tasks)
        if total:
            log.info("Cycle %d: produced %d task(s)", cycle, total)
        else:
            log.debug("Cycle %d: no new tasks", cycle)

        if once:
            log.info("Once-mode: exiting after cycle %d", cycle)
            break

        time.sleep(interval_s)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Hermit Crab — ActiveTrack <-> Room Coordinator Bridge",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one sync cycle and exit.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_S,
        help=f"Poll interval in seconds (default: {DEFAULT_POLL_INTERVAL_S}).",
    )
    parser.add_argument(
        "--read-state",
        action="store_true",
        help="Print the current ActiveTrack state and exit.",
    )
    parser.add_argument(
        "--read-nmea",
        action="store_true",
        help="Read one NMEA sentence from TCP :6006 and print it.",
    )

    args = parser.parse_args()

    if args.read_state:
        state = read_activetrack_state()
        print(json.dumps(state, indent=2, default=str))
        return

    if args.read_nmea:
        line = read_nmea_line()
        if line:
            print(f"NMEA: {line}")
        else:
            print("No NMEA data (connection failed or timed out).")
        return

    run_loop(once=args.once, interval_s=args.interval)


if __name__ == "__main__":
    main()
