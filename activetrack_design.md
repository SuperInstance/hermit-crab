# ActiveLog — Segment-Based Position Logger for Hermit Crab

## Philosophy

Tracking every position sample is like recording every individual hook. The pattern isn't in any single point. It's in the shape across them.

**Segments** are transparent abstractions. Each segment is a stretch where nothing interesting changed: same speed, same heading, same depth band. The consumer sees through the segment to the implied data — steady course means steady conditions means the boat was doing one thing.

**Anomalies** are the interesting bits: turns, speed changes, gear events, fish caught. Each anomaly carries weight. A logged catch at a specific lat/lon with known tide/current/depth is worth a thousand raw position samples.

## Data Model

### Segment (the default record)
```
{
  "id": "seg_20260713_142300",
  "start_ts": "2026-07-13T14:23:00",
  "end_ts":   "2026-07-13T14:38:00",
  "start_lat": 55.787167, "start_lon": -131.504183,
  "end_lat":   55.789200, "end_lon":   -131.501100,
  "vector":   [delta_lat, delta_lon],
  "sog_mean": 2.3, "sog_var": 0.12,
  "cog_mean": 285.0, "cog_var": 2.1,
  "depth_mean": 33, "depth_var": 1.5,
  "tide_mean": -1.73,
  "chart_scale": 25100,
  "duration_s": 900,
  "distance_nm": 0.52,
  "tags": []
}
```

### Anomaly (the interesting record)
```
{
  "id": "anom_20260713_143045",
  "ts": "2026-07-13T14:30:45",
  "lat": 55.788100, "lon": -131.502500,
  "type": "speed_change",
  "magnitude": 1.2,  // new - old SOG
  "segment_id": "seg_20260713_142300",
  "context": {
    "sog_before": 2.3, "sog_after": 3.5,
    "cog_before": 285, "cog_after": 287
  }
}
```

### Event (human-tagged record)
```
{
  "id": "evt_20260713_143100",
  "ts": "2026-07-13T14:31:00",
  "lat": 55.788300, "lon": -131.502300,
  "type": "gear_deployed",
  "description": "Put gear in at 33 fm, heading 285",
  "tags": ["trolling", "chinook", "33fm"],
  "segment_id": "seg_20260713_142300"
}
```

## Segment Thresholds (when to cut)

A segment ends and a new one starts when any:
- SOG change > 0.3 kn sustained for 3+ samples
- COG change > 5° sustained
- Depth change > 2 fm
- Elapsed time > 15 min (force cut to avoid unlimited segments)
- Manual event (gear up/down, fish on)

## Queries the Activelog Enables

- "What was our SOG on the last 5 segments in 30-40 fm depth?"
- "Show me all speed anomalies with magnitude >1.5 kn in the last week"
- "Where did we deploy gear last week Wednesday?"
- "What's the average tide height when we caught kings in July?"

## Screenshot Policy

Only save screenshots when:
1. First capture (initial state)
2. Chart scale changes
3. Dialog/alert appears (low confidence across all fields)
4. Manual request from Casey ("capture what you see")
5. Max 1 per hour unless conditions change

## Implementation Plan

1. Build `activetrack.py` — segment/state machine on top of raw captures
2. D1 table `segments` and `anomalies` and `events`
3. Relationship: capture → sample → segment (captures feed samples, samples hit thresholds, thresholds close segments)
4. Keep raw capture pipeline for cold storage, but active queries hit the segment/anomaly/event tables
