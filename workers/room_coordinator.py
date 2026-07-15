#!/usr/bin/env python3
"""
room_coordinator.py — Multi-model coordination room for Hermit Crab.

Routes tasks to appropriate model sub-agents based on task type:

  - "creative"     → Seed2 (T=0.7)
  - "code"         → Kimi / Claude Code
  - "structural"   → Nemotron
  - "synthesis"    → Claude Sonnet
  - "prose"        → DeepSeek Pro
  - "orchestration" → DeepSeek Flash

Runs as a continuous loop, checking the outbox every 30 seconds.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTBOX_DIR = Path(__file__).resolve().parent.parent / "outbox"
TASKS_PATH = OUTBOX_DIR / "tasks.json"
RESULTS_PATH = OUTBOX_DIR / "results.json"
ERROR_LOG_PATH = OUTBOX_DIR / "coordinator_errors.log"
POLL_INTERVAL_S = 30

MODEL_ROUTING: dict[str, str] = {
    "creative": "seed2",
    "code": "kimi",
    "structural": "nemotron",
    "synthesis": "claude-sonnet",
    "prose": "deepseek-pro",
    "orchestration": "deepseek-flash",
}

# Allowed sources so we can trace where a task came from
ALLOWED_SOURCES = {"user", "autotrack", "scheduler", "system", "webhook"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(ERROR_LOG_PATH)),
    ],
)
log = logging.getLogger("room_coordinator")


# ---------------------------------------------------------------------------
# I/O Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    """Read and return a JSON file, or return an default structure on error."""
    try:
        if not path.exists():
            return {"version": 1, "tasks": [], "current_task_index": 0}
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read %s: %s — using empty state", path, exc)
        return {"version": 1, "tasks": [], "current_task_index": 0}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON data to *path*."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------

def classify_task(task: dict[str, Any]) -> str | None:
    """
    Determine which model should handle the task based on its *task_type* field.

    Returns the model name string (e.g. "seed2") or *None* if the task type is
    unrecognised.
    """
    task_type = task.get("task_type", "").lower().strip()
    model = MODEL_ROUTING.get(task_type)
    if model is None:
        log.warning("Unknown task_type=%r for task %s", task_type, task.get("id", "?"))
    return model


# ---------------------------------------------------------------------------
# Sub-agent delegation
# ---------------------------------------------------------------------------

def spawn_subagent(
    model: str,
    prompt: str,
    task_id: str,
    *,
    context: dict[str, Any] | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """
    Delegate a prompt to the named model by spawning a sub-agent process.

    The actual invocation is a placeholder that writes to the results file.
    In production this would call out to an MCP server, API, or OpenClaw
    sub-agent tool.

    Returns a result dict with keys: success, output/error, model, task_id, ts.
    """
    log.info("Spawning sub-agent model=%s task=%s", model, task_id)

    ts = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # --- Real sub-agent dispatch (extensible) ---
    # The current implementation records the delegation; a production version
    # would call `openclaw spawn` or an external API.
    try:
        env = os.environ.copy()
        env["SUBAGENT_MODEL"] = model
        env["SUBAGENT_TASK_ID"] = task_id
        if context:
            env["SUBAGENT_CONTEXT"] = json.dumps(context, default=str)

        # Use the prompt as an argument — trivially visible in proc table.
        # In production, pipe via stdin or a temp file.
        result = subprocess.run(
            [
                sys.executable or "python3",
                "-c",
                _subagent_stub_script(model, prompt, task_id),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return {
                "success": False,
                "error": stderr or f"Exit code {result.returncode}",
                "model": model,
                "task_id": task_id,
                "ts": ts,
            }

        try:
            output = json.loads(stdout) if stdout else {"text": ""}
        except json.JSONDecodeError:
            output = {"text": stdout}

        return {
            "success": True,
            "output": output,
            "model": model,
            "task_id": task_id,
            "ts": ts,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Timeout after {timeout_s}s",
            "model": model,
            "task_id": task_id,
            "ts": ts,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "model": model,
            "task_id": task_id,
            "ts": ts,
        }


def _subagent_stub_script(model: str, prompt: str, task_id: str) -> str:
    """Return a tiny Python script that simulates model output.

    Replace this with actual API/MCP calls for production use.
    """
    return f"""
import json, os
# Stub: echo back the prompt wrapped in a mock response.
# Production would call the model's API.
print(json.dumps({{
    "model": {model!r},
    "task_id": {task_id!r},
    "response": "Sub-agent {model} processed: " + {prompt[:120]!r},
    "tokens_estimated": len({prompt!r}.split()),
}}))
"""


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def collect_and_write_results(results: list[dict[str, Any]]) -> None:
    """Append *results* to the results.json file."""
    data = _read_json(RESULTS_PATH)
    if "results" not in data:
        data["results"] = []
    data["results"].extend(results)
    _write_json(RESULTS_PATH, data)
    log.info("Wrote %d result(s) to %s", len(results), RESULTS_PATH)


# ---------------------------------------------------------------------------
# Loading tasks
# ---------------------------------------------------------------------------

def load_tasks() -> list[dict[str, Any]]:
    """Return the current pending task list from tasks.json."""
    data = _read_json(TASKS_PATH)
    return data.get("tasks", [])


def mark_task_completed(task_id: str) -> None:
    """
    Remove the task with *task_id* from the pending list and advance the
    internal index.
    """
    data = _read_json(TASKS_PATH)
    tasks = data.get("tasks", [])
    data["tasks"] = [t for t in tasks if t.get("id") != task_id]
    _write_json(TASKS_PATH, data)


def store_error(error_entry: dict[str, Any]) -> None:
    """Append an error record to the results error list."""
    data = _read_json(RESULTS_PATH)
    if "errors" not in data:
        data["errors"] = []
    data["errors"].append(error_entry)
    _write_json(RESULTS_PATH, data)


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------

def orchestrate_task(task: dict[str, Any]) -> dict[str, Any] | None:
    """
    Orchestrate a single task through the model pipeline.

    1. Classify the task → pick a model
    2. Spawn the sub-agent
    3. Collect and persist the result

    Returns the result dict, or *None* if classification failed.
    """
    task_id = task.get("id", "unknown")
    log.info("Orchestrating task %s", task_id)

    model = classify_task(task)
    if model is None:
        error_entry = {
            "task_id": task_id,
            "error": f"Unrecognised task_type={task.get('task_type')}",
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        store_error(error_entry)
        return None

    prompt = task.get("prompt", "")
    context = task.get("context", {})

    result = spawn_subagent(model, prompt, task_id, context=context)

    if result["success"]:
        collect_and_write_results([result])
        mark_task_completed(task_id)
    else:
        store_error({
            "task_id": task_id,
            "error": result.get("error"),
            "model": model,
            "ts": result.get("ts"),
        })
        log.error("Task %s failed on %s: %s", task_id, model, result.get("error"))

    return result


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_loop(*, once: bool = False, interval: int = 30) -> None:
    """
    Main coordination loop.

    Parameters
    ----------
    once : bool
        If True, process any pending tasks and exit. Otherwise loop forever.
    interval : int
        Poll interval in seconds between cycles.
    """
    poll_interval = interval
    log.info("Room coordinator started (once=%s, interval=%ds)", once, poll_interval)
    log.info("Watching %s", TASKS_PATH)

    cycle = 0

    while True:
        cycle += 1
        tasks = load_tasks()

        if not tasks:
            log.debug("Cycle %d: no pending tasks — sleeping %ds", cycle, poll_interval)
        else:
            log.info("Cycle %d: %d pending task(s)", cycle, len(tasks))
            for task in tasks:
                orchestrate_task(task)

        if once:
            log.info("Once-mode: exiting after cycle %d", cycle)
            break

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Hermit Crab — Multi-model room coordinator",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process pending tasks once and exit instead of looping.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=POLL_INTERVAL_S,
        help=f"Poll interval in seconds (default: {POLL_INTERVAL_S}).",
    )
    parser.add_argument(
        "--add-task",
        nargs=3,
        metavar=("ID", "TYPE", "PROMPT"),
        help="Add a task to the queue and exit (useful for automated dispatch).",
    )

    args = parser.parse_args()

    if args.add_task:
        tid, ttype, tprompt = args.add_task
        if ttype not in MODEL_ROUTING:
            print(f"Error: unknown task type '{ttype}'. Valid: {list(MODEL_ROUTING.keys())}")
            sys.exit(1)
        data = _read_json(TASKS_PATH)
        if "tasks" not in data:
            data["tasks"] = []
        data["tasks"].append({
            "id": tid,
            "task_type": ttype,
            "prompt": tprompt,
            "source": "cli",
            "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        })
        _write_json(TASKS_PATH, data)
        print(f"Added task {tid} (type={ttype}) to queue.")
        return

    run_loop(once=args.once, interval=args.interval)


if __name__ == "__main__":
    main()
