#!/usr/bin/env python3
"""
model_scheduler.py -- Time-based model rotation for Hermit Crab's multi-model
room.

Rotates which model handles which task type throughout the day based on
watch schedules:

  Watch        |  Hours        |  Orchestrator    |  Specialist
  -------------|---------------|------------------|----------------------
  Morning      |  00:00-08:00  |  DeepSeek Flash  |  (always-on prose)
  Day          |  08:00-16:00  |  Seed2           |  Kimi
  Evening      |  16:00-24:00  |  Nemotron        |  Claude Sonnet

The scheduler updates the *tasks.json* routing table so the room coordinator
picks the correct model for each task type at the current time.

Usage
-----
    # Update the routing table once (good for cron)
    python model_scheduler.py --apply

    # Print the current watch info
    python model_scheduler.py --status

    # Run as a continuous daemon, updating every 15 minutes
    python model_scheduler.py --daemon

    # Run as a daemon with custom interval
    python model_scheduler.py --daemon --interval 600
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HERMIT_CRAB_ROOT = Path(__file__).resolve().parent.parent
OUTBOX_DIR = HERMIT_CRAB_ROOT / "outbox"
TASKS_PATH = OUTBOX_DIR / "tasks.json"
SCHEDULER_STATE_PATH = OUTBOX_DIR / "scheduler_state.json"
DAEMON_INTERVAL_S = 900  # 15 minutes

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] model_scheduler: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(OUTBOX_DIR / "scheduler.log")),
    ],
)
log = logging.getLogger("model_scheduler")


# ---------------------------------------------------------------------------
# Watch definitions
# ---------------------------------------------------------------------------

@dataclass
class Watch:
    """A single watch shift with assigned models."""

    name: str
    start_hour: int   # inclusive
    end_hour: int     # exclusive
    orchestrator: str
    specialist: str | None
    description: str = ""

    def contains(self, hour: int) -> bool:
        """Return True if *hour* falls within this watch."""
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        # Spans midnight (e.g. 22:00-02:00) -- not used here but handled
        return hour >= self.start_hour or hour < self.end_hour


WATCHES = [
    Watch(
        name="morning",
        start_hour=0,
        end_hour=8,
        orchestrator="deepseek-flash",
        specialist=None,
        description="Always-on orchestration; prose + light synthesis",
    ),
    Watch(
        name="day",
        start_hour=8,
        end_hour=16,
        orchestrator="seed2",
        specialist="kimi",
        description="Creative brainstorming (Seed2) + Code (Kimi)",
    ),
    Watch(
        name="evening",
        start_hour=16,
        end_hour=24,
        orchestrator="nemotron",
        specialist="claude-sonnet",
        description="Structural (Nemotron) + Deep synthesis (Claude)",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
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
# Watch resolution
# ---------------------------------------------------------------------------

def current_watch(dt: _dt.datetime | None = None) -> Watch:
    """Return the active Watch for the given time (or now)."""
    if dt is None:
        dt = _dt.datetime.now(_dt.timezone.utc)
    hour = dt.hour
    for watch in WATCHES:
        if watch.contains(hour):
            return watch
    # Fallback to morning watch (should never happen if WATCHES cover 0-24)
    return WATCHES[0]


def routing_for_watch(watch: Watch) -> dict[str, str]:
    """
    Build the model->task_type routing table for the given *watch*.

    The base routing is overridden by the watch's orchestrator and specialist.
    """
    # Default routing (balanced across all models)
    routing = {
        "creative": "seed2",
        "code": "kimi",
        "structural": "nemotron",
        "synthesis": "claude-sonnet",
        "prose": "deepseek-pro",
        "orchestration": "deepseek-flash",
    }

    # Override orchestrator for this watch
    if watch.orchestrator == "deepseek-flash":
        # Morning: Flash handles everything except code/structural
        routing["creative"] = "deepseek-flash"
        routing["prose"] = "deepseek-flash"
        routing["synthesis"] = "deepseek-flash"
        routing["orchestration"] = "deepseek-flash"
    elif watch.orchestrator == "seed2":
        # Day: Seed2 handles creative; Kimi handles code
        routing["creative"] = "seed2"
        routing["code"] = "kimi"
        routing["orchestration"] = "seed2"
    elif watch.orchestrator == "nemotron":
        # Evening: Nemotron handles structural; Claude handles synthesis
        routing["structural"] = "nemotron"
        routing["synthesis"] = "claude-sonnet"
        routing["orchestration"] = "nemotron"

    # Specialist override: if a specialist is assigned, it takes code
    if watch.specialist:
        if watch.specialist == "kimi":
            routing["code"] = "kimi"
        elif watch.specialist == "claude-sonnet":
            routing["synthesis"] = "claude-sonnet"

    return routing


# ---------------------------------------------------------------------------
# Apply routing to tasks.json
# ---------------------------------------------------------------------------

def apply_routing(watch: Watch | None = None) -> Watch:
    """
    Update the models routing table inside *tasks.json* to reflect the current
    watch schedule.

    Returns the active Watch.
    """
    if watch is None:
        watch = current_watch()

    routing = routing_for_watch(watch)

    data = _read_json(TASKS_PATH, default={"version": 1, "tasks": []})
    data["models"] = routing
    data["active_watch"] = {
        "name": watch.name,
        "orchestrator": watch.orchestrator,
        "specialist": watch.specialist,
        "description": watch.description,
        "applied_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    _write_json(TASKS_PATH, data)

    log.info(
        "Applied watch=%s orchestrator=%s specialist=%s",
        watch.name,
        watch.orchestrator,
        watch.specialist or "(none)",
    )

    # Advance scheduler state
    state = _read_json(SCHEDULER_STATE_PATH)
    state["last_watch"] = watch.name
    state["last_applied"] = data["active_watch"]["applied_at"]
    state["watch_count"] = state.get("watch_count", 0) + 1
    _write_json(SCHEDULER_STATE_PATH, state)

    return watch


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------

def format_status() -> str:
    """Return a human-readable status string of the current schedule."""
    now = _dt.datetime.now(_dt.timezone.utc)
    watch = current_watch(now)
    routing = routing_for_watch(watch)

    lines = [
        f"Current time (UTC): {now.strftime('%H:%M:%S')}",
        f"Active watch:       {watch.name.upper()}",
        f"  {watch.start_hour:02d}:00 - {watch.end_hour:02d}:00  "
        f"orchestrator={watch.orchestrator}  "
        f"specialist={watch.specialist or '(none)'}",
        f"  Description: {watch.description}",
        "",
        "Routing table:",
    ]
    for task_type, model in sorted(routing.items()):
        lines.append(f"  {task_type:16s} -> {model}")
    lines.append("")

    # Count tasks in queue
    data = _read_json(TASKS_PATH)
    task_count = len(data.get("tasks", []))
    lines.append(f"Pending tasks in queue: {task_count}")

    state = _read_json(SCHEDULER_STATE_PATH)
    lines.append(f"Total watch rotations: {state.get('watch_count', 0)}")
    if state.get("last_applied"):
        lines.append(f"Last rotation applied: {state['last_applied']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------

def run_daemon(*, interval_s: int = DAEMON_INTERVAL_S, once: bool = False) -> None:
    """
    Run the scheduler as a daemon, periodically checking the time and
    applying the correct watch routing.
    """
    log.info(
        "Model scheduler daemon started (interval=%ds, once=%s)",
        interval_s,
        once,
    )

    LAST_WATCH_KEY: str | None = None
    cycle = 0

    while True:
        cycle += 1
        now = _dt.datetime.now(_dt.timezone.utc)
        watch = current_watch(now)

        if watch.name != LAST_WATCH_KEY:
            log.info(
                "Watch transition: %s -> %s (%s orchestrator=%s)",
                LAST_WATCH_KEY or "(init)",
                watch.name,
                watch.description,
                watch.orchestrator,
            )
            apply_routing(watch)
            LAST_WATCH_KEY = watch.name
        else:
            log.debug("Cycle %d: watch=%s unchanged", cycle, watch.name)

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
        description="Hermit Crab -- Time-based model rotation scheduler",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current watch / routing status and exit.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the current watch routing and exit.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as a continuous daemon, updating every --interval seconds.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DAEMON_INTERVAL_S,
        help=f"Daemon poll interval in seconds (default: {DAEMON_INTERVAL_S}).",
    )
    parser.add_argument(
        "--force-watch",
        type=str,
        choices=[w.name for w in WATCHES],
        help="Force a specific watch (useful for testing).",
    )

    args = parser.parse_args()

    if args.force_watch:
        forced = next(w for w in WATCHES if w.name == args.force_watch)
        apply_routing(forced)
        print(f"Forced watch={forced.name} applied.")
        return

    if args.status:
        print(format_status())
        return

    if args.apply:
        watch = apply_routing()
        print(f"Applied watch={watch.name} orchestrator={watch.orchestrator}")
        return

    if args.daemon:
        run_daemon(interval_s=args.interval)
        return

    # Default: print status
    print(format_status())


if __name__ == "__main__":
    main()
