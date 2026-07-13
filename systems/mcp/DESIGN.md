# DESIGN.md — Activelog MCP Server

## Purpose

Expose Hermit Crab's activelog data (track points, segments, events, anomalies)
and capture capabilities as MCP (Model Context Protocol) tools and resources.

Any MCP-speaking agent — Claude Code, git-agents, DeckBoss, any future fleet
member — can connect and query the system without knowing Python, SQL, or the
repo internals.

## Protocol

MCP stdio transport. The server runs as a subprocess and speaks JSON-RPC over
stdin/stdout. Compatible with Claude Code's `--mcp` flag, the MCP CLI, and any
MCP client.

## Tools

### actuelog_query_segments
Query track segments with optional filters.
```
Input: { start_date?, end_date?, min_duration_s?, max_results?, agent_id? }
Output: [{ id, start_ts, end_ts, start_lat, start_lon, end_lat, end_lon,
           sog_mean, sog_var, depth_mean, tide_mean, duration_s, distance_nm }]
```

### actuelog_query_events
Query fishing events (gear deployments, catches, manual notes).
```
Input: { type?, species?, tags?, since?, max_results? }
Output: [{ id, ts, lat, lon, type, description, tags, segment_id, catch_count, species }]
```

### actuelog_query_anomalies
Query anomalies (speed changes, heading shifts, timeouts).
```
Input: { type?, since?, segment_id?, max_results? }
Output: [{ id, ts, lat, lon, type, magnitude, segment_id, sog_before, sog_after }]
```

### actuelog_query_track_points
Query raw track points (for detailed analysis).
```
Input: { since?, lat_near?, lon_near?, radius_nm?, max_results? }
Output: [{ ts, lat, lon, sog, depth, tide }]
```

### actuelog_capture_screen (resource-like tool)
Take a fresh TZ Pro screenshot and extract current position.
```
Input: {}
Output: { ts, lat, lon, sog, depth, tide, chart_scale, confidence }
```

### actuelog_log_event
Log a manual event to the current segment.
```
Input: { type, description?, tags? }
Output: { id, ts, segment_id }
```

### actuelog_log_catch
Log a catch event.
```
Input: { count, species }
Output: { id, ts, segment_id }
```

### actuelog_status
Get current system status.
```
Input: {}
Output: { current_position, open_segment, recent_events, buffer_counts }
```

## Resources

- `activelog://status` — current position + segment state
- `activelog://last-segment` — most recently closed segment
- `activelog://today/counts` — today's segment/event/anomaly counts
- `activelog://version` — schema version and agent identity

## Implementation

Server: `systems/mcp/server.py`
- Uses wrangler CLI for D1 queries (same as activetrack.py)
- Imports tzpro_extract for screen capture
- Reads activetrack_state.json for current segment
- stdio transport only (no HTTP for now)

## Security

- All queries are read-only except explicit log_event/log_catch
- Screen capture requires TZ Pro running on Monitor 2
- No auth — trust is established by being on the same machine
- For fleet access, wrap behind the memory-track Worker + API key later
