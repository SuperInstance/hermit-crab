"""
Hermit Crab MCP Server — exposes the activelog as MCP tools and resources.

Any MCP-speaking agent (Claude Code, git-agents, DeckBoss, fleet) can query
track segments, events, anomalies, and captures without knowing the repo
internals or D1 SQL.

Usage:
    python -m systems.mcp.server          # stdio mode — for MCP clients
    python -m systems.mcp.server --help   # show flags

Connect from Claude Code:
    claude --mcp "python -m systems.mcp.server"

Protocol: MCP stdio transport (JSON-RPC over stdin/stdout).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any

# ── workspace ──────────────────────────────────────────────────────────
_WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _WORKSPACE not in sys.path:
    sys.path.insert(0, _WORKSPACE)

_WRANGLER = shutil.which("wrangler") or r"C:\Users\casey\AppData\Roaming\npm\wrangler.CMD"
import shutil

_DB = "hermit-crab-memory-db"
_STATE_FILE = os.path.join(_WORKSPACE, "activetrack_state.json")

log = logging.getLogger("hermit-crab.mcp")


# ── D1 helpers ─────────────────────────────────────────────────────────
def d1_query(sql: str) -> list[dict]:
    """Execute a read-only SQL query against D1 and return results."""
    cmd = [_WRANGLER, "d1", "execute", _DB, "--command", sql, "--remote", "--json"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, cwd=_WORKSPACE,
        )
        if proc.returncode != 0:
            log.warning("wrangler err: %s", proc.stderr[:200])
            return []
        data = json.loads(proc.stdout)
        if isinstance(data, list) and data:
            return data[0].get("results", [])
        return []
    except Exception as exc:
        log.warning("D1 query failed: %s", exc)
        return []


def d1_write(sql: str) -> bool:
    """Execute a write SQL against D1. Returns True on success."""
    cmd = [_WRANGLER, "d1", "execute", _DB, "--command", sql, "--remote"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, cwd=_WORKSPACE,
        )
        if proc.returncode != 0:
            log.warning("wrangler write err: %s", proc.stderr[:200])
            return False
        return '"success": true' in proc.stdout
    except Exception as exc:
        log.warning("D1 write failed: %s", exc)
        return False


def _sql_val(v: Any) -> str:
    """Escape a Python value for SQL insertion."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        if not (v == v):  # NaN check
            return "NULL"
        return str(v)
    # string — double single-quotes
    escaped = str(v).replace("'", "''")
    return f"'{escaped}'"


# ── activetrack_state ──────────────────────────────────────────────────
def _read_state() -> dict:
    if os.path.isfile(_STATE_FILE):
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ── MCP Protocol ───────────────────────────────────────────────────────
def _send(msg: dict) -> None:
    line = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(f"Content-Length: {len(line.encode('utf-8'))}\r\n\r\n{line}")
    sys.stdout.flush()


def _receive() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    # Parse Content-Length header
    if line.startswith("Content-Length:"):
        length = int(line.split(":")[1].strip())
        # Read blank line
        sys.stdin.readline()
        body = sys.stdin.read(length)
        return json.loads(body)
    return None


# ── Tool implementations ──────────────────────────────────────────────
def tool_query_segments(args: dict) -> list[dict]:
    where = []
    if since := args.get("since"):
        where.append(f"end_ts >= {_sql_val(since)}")
    if min_dur := args.get("min_duration_s"):
        where.append(f"duration_s >= {min_dur}")
    if agent_id := args.get("agent_id"):
        where.append(f"agent_id = {_sql_val(agent_id)}")
    limit = min(args.get("max_results", 20), 100)
    sql = "SELECT * FROM segments"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY end_ts DESC LIMIT {limit}"
    return d1_query(sql)


def tool_query_events(args: dict) -> list[dict]:
    where = []
    if ev_type := args.get("type"):
        where.append(f"type = {_sql_val(ev_type)}")
    if species := args.get("species"):
        where.append(f"species = {_sql_val(species)}")
    if tags := args.get("tags"):
        like = f"%{tags}%"
        where.append(f"tags LIKE {_sql_val(like)}")
    if since := args.get("since"):
        where.append(f"ts >= {_sql_val(since)}")
    limit = min(args.get("max_results", 20), 100)
    sql = "SELECT * FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY ts DESC LIMIT {limit}"
    return d1_query(sql)


def tool_query_anomalies(args: dict) -> list[dict]:
    where = []
    if an_type := args.get("type"):
        where.append(f"type = {_sql_val(an_type)}")
    if seg_id := args.get("segment_id"):
        where.append(f"segment_id = {_sql_val(seg_id)}")
    if since := args.get("since"):
        where.append(f"ts >= {_sql_val(since)}")
    limit = min(args.get("max_results", 20), 100)
    sql = "SELECT * FROM anomalies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY ts DESC LIMIT {limit}"
    return d1_query(sql)


def tool_query_track_points(args: dict) -> list[dict]:
    where = []
    if since := args.get("since"):
        where.append(f"ts >= {_sql_val(since)}")
    if lat := args.get("lat_near"):
        lon = args.get("lon_near")
        radius = args.get("radius_nm", 0.5)
        # Approximate degree → nm: 1° lat ≈ 60 nm, 1° lon ≈ 60*cos(lat) nm
        lat_deg = radius / 60.0
        lon_deg = radius / (60.0 * 0.57)  # cos(55°) ≈ 0.57
        where.append(f"lat BETWEEN {lat - lat_deg} AND {lat + lat_deg}")
        if lon is not None:
            where.append(f"lon BETWEEN {lon - lon_deg} AND {lon + lon_deg}")
    limit = min(args.get("max_results", 50), 500)
    sql = "SELECT ts, lat, lon, sog, depth, tide FROM track_points"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY ts DESC LIMIT {limit}"
    return d1_query(sql)


def tool_capture_screen(args: dict) -> dict:
    """Take a fresh TZ Pro screenshot and extract current position."""
    try:
        from tzpro_extract import capture_via_powershell, extract
        log.info("Capturing screen for MCP request")
        path = capture_via_powershell(
            os.path.join(_WORKSPACE, "capture_monitor2.ps1"), log
        )
        result = extract(path, log=log)
        return result.to_dict()
    except Exception as exc:
        return {"error": str(exc)}


def tool_log_event(args: dict) -> dict:
    ev_type = args.get("type", "manual")
    desc = args.get("description", "")
    tags = args.get("tags", "")
    state = _read_state()
    seg = state.get("segment", {})
    seg_id = seg.get("id", "none")
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    ev_id = f"evt_mcp_{int(time.time())}"
    sql = (
        f"INSERT OR REPLACE INTO events "
        f"(id, ts, lat, lon, type, description, tags, segment_id, catch_count, species, agent_id) "
        f"VALUES ({_sql_val(ev_id)}, {_sql_val(ts)}, "
        f"{seg.get('lat', 'NULL')}, {seg.get('lon', 'NULL')}, "
        f"{_sql_val(ev_type)}, {_sql_val(desc)}, {_sql_val(tags)}, "
        f"{_sql_val(seg_id)}, NULL, '', 'agent:hermit-crab/mcp')"
    )
    ok = d1_write(sql)
    return {"id": ev_id, "ts": ts, "segment_id": seg_id, "success": ok}


def tool_log_catch(args: dict) -> dict:
    count = args.get("count", 1)
    species = args.get("species", "unknown")
    state = _read_state()
    seg = state.get("segment", {})
    seg_id = seg.get("id", "none")
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    ev_id = f"evt_mcp_{int(time.time())}"
    desc = f"Caught {count} {species}"
    sql = (
        f"INSERT OR REPLACE INTO events "
        f"(id, ts, lat, lon, type, description, tags, segment_id, catch_count, species, agent_id) "
        f"VALUES ({_sql_val(ev_id)}, {_sql_val(ts)}, "
        f"{seg.get('lat', 'NULL')}, {seg.get('lon', 'NULL')}, "
        f"'catch', {_sql_val(desc)}, {_sql_val(species)}, "
        f"{_sql_val(seg_id)}, {count}, {_sql_val(species)}, 'agent:hermit-crab/mcp')"
    )
    ok = d1_write(sql)
    return {"id": ev_id, "ts": ts, "segment_id": seg_id, "catch_count": count, "species": species, "success": ok}


def tool_status(args: dict) -> dict:
    state = _read_state()
    seg = state.get("segment", {})
    latest = d1_query("SELECT ts, lat, lon, sog, tide FROM track_points ORDER BY ts DESC LIMIT 1")
    today_counts = d1_query(
        "SELECT 'segments' as t, count(*) as c FROM segments WHERE start_ts >= date('now') "
        "UNION ALL SELECT 'events', count(*) FROM events WHERE ts >= date('now') "
        "UNION ALL SELECT 'anomalies', count(*) FROM anomalies WHERE ts >= date('now')"
    )
    return {
        "current_position": latest[0] if latest else None,
        "open_segment": {
            "id": seg.get("id"),
            "start_ts": seg.get("start_ts"),
            "duration_s": seg.get("duration_s", 0),
            "samples": seg.get("samples", 0),
        },
        "today_counts": {r["t"]: r["c"] for r in today_counts} if today_counts else {},
        "agent": "agent:hermit-crab",
        "server": "systems/mcp/server.py",
    }


# ── Tool registry ──────────────────────────────────────────────────────
TOOLS = {
    "activelog_query_segments": {
        "description": "Query track segments (compressed position history). Filters: start_date, end_date, min_duration_s, max_results, agent_id.",
        "handler": tool_query_segments,
    },
    "activelog_query_events": {
        "description": "Query fishing events (gear, catches, notes). Filters: type, species, tags, since, max_results.",
        "handler": tool_query_events,
    },
    "activelog_query_anomalies": {
        "description": "Query anomalies (speed changes, heading shifts, timeouts). Filters: type, since, segment_id, max_results.",
        "handler": tool_query_anomalies,
    },
    "activelog_query_track_points": {
        "description": "Query raw track points. Filters: since, lat_near, lon_near, radius_nm, max_results.",
        "handler": tool_query_track_points,
    },
    "activelog_capture_screen": {
        "description": "Take a fresh TZ Pro screenshot and extract current position/lat/lon/SOG/depth/tide.",
        "handler": tool_capture_screen,
    },
    "activelog_log_event": {
        "description": "Log a manual event (gear deployment, note, etc.). Params: type, description, tags.",
        "handler": tool_log_event,
    },
    "activelog_log_catch": {
        "description": "Log a fishing catch. Params: count, species.",
        "handler": tool_log_catch,
    },
    "activelog_status": {
        "description": "Get current system status: position, open segment, today's counts.",
        "handler": tool_status,
    },
}


# ── MCP loop ───────────────────────────────────────────────────────────
def _handle_initialize(req: dict) -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {k: {"description": v["description"]} for k, v in TOOLS.items()},
            "resources": {
                "activelog://status": {"description": "Current position and segment state"},
                "activelog://last-segment": {"description": "Most recently closed segment"},
                "activelog://today/counts": {"description": "Today's activity counts"},
            },
        },
        "serverInfo": {"name": "hermit-crab-activelog", "version": "1.0.0"},
    }


def _handle_list_tools(req: dict) -> dict:
    return {
        "tools": [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": {"type": "object", "properties": {}},
            }
            for name, info in TOOLS.items()
        ]
    }


def _handle_call_tool(req: dict) -> dict:
    name = req.get("params", {}).get("name", "")
    args = req.get("params", {}).get("arguments", {})
    if name in TOOLS:
        try:
            result = TOOLS[name]["handler"](args)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}
        except Exception as exc:
            return {"isError": True, "content": [{"type": "text", "text": f"Error: {exc}"}]}
    return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}


HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_list_tools,
    "tools/call": _handle_call_tool,
    # Resource handlers
    "resources/list": lambda r: {
        "resources": [
            {"uri": "activelog://status", "name": "Current Status"},
            {"uri": "activelog://last-segment", "name": "Last Segment"},
            {"uri": "activelog://today/counts", "name": "Today Counts"},
        ]
    },
    "resources/read": lambda r: {
        "contents": [
            {
                "uri": r.get("params", {}).get("uri", ""),
                "text": json.dumps(tool_status({}), indent=2, default=str),
            }
        ]
    },
}


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("Hermit Crab MCP server starting (stdio)")

    while True:
        try:
            msg = _receive()
            if msg is None:
                break
            method = msg.get("method", "")
            req_id = msg.get("id")
            handler = HANDLERS.get(method)
            if handler:
                result = handler(msg)
                _send({"jsonrpc": "2.0", "id": req_id, "result": result})
            else:
                _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
        except EOFError:
            break
        except Exception as exc:
            log.error("MCP error: %s", exc)


if __name__ == "__main__":
    main()
