# EQUIPMENT.md — Hermit Crab Tooling

## Installed Tools

### Screen Capture
- `capture_monitor2.ps1` — Captures TZ Pro on Monitor 2 (1600x1200) via Add-Type WinAPI
- `Tesseract 5.4.0` at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- `pytesseract` Python binding

### Data Extraction
- `tzpro_extract.py` — Monitor 2 → OCR → structured JSON with confidence scoring
- `activetrack.py` — Segment-based position logger, writes to D1

### Storage
- **D1**: `hermit-crab-memory-db` (tables: track_points, segments, anomalies, events, memory_entries, session_logs)
- **R2**: `hermit-crab-memory-cold` (long-term JSONL archives)
- **KV**: `hermit-crab-memory` (low-latency key-value)

### CLI Coding Agents
- **Claude Code** (2.0.65) — glm-5.2 via z.ai, bypass permissions, always-thinking
- **OpenCode** — glm-4.6 via z.ai coding plan
- **Crush** (0.84.1) — z.ai provider
- **Kimi Code** (0.23.5) — kimi-for-coding, 262K context, image/video input
- **Kimi CLI** (1.48.0)

### Cloudflare
- **wrangler 4.73.0** — Worker/D1/R2 management
- **Account**: casey.digennaro@gmail.com (049ff5e84ecf636b53b162cbb580aae6)

## Equipment Patterns

### Extractor Pipeline
```
capture_monitor2.ps1 → tzpro_live.png → tzpro_extract.py → JSON → parse lat/lon/SOG/depth/tide
```

### Tracker Pipeline
```
tzpro_extract.py (per 5s) → activetrack.py → sample → window → segment → D1
activatrack.py --event → writes to events table
activatrack.py --catch → writes to events table with species/count
```

### Query
```
wrangler d1 execute hermit-crab-memory-db --command "SQL" --remote
```

## Known Issues

- SOG OCR sometimes has trailing garbage (`1.5°°`) from chart degree symbol bleed
- Time display is anti-aliased on dark panel; OCR works but lower confidence
- Frozen screen (PBG loading) detected by repeated identical positions
- wrangler must be on PATH; Python subprocess needs full path to .CMD shim
