# DECISIONS.md — Design Decisions, Forks, and Dead Ends

Every decision in this system is recorded here. If you're about to try something,
read this first. Someone already tried it.

## Why Segments Over Raw Points

**Decision (2026-07-13):** Use segment-based position logging instead of raw point buffers.

**Considered:** Three-tier ring buffer (hot/warm/day at 1s/2s/5s resolution) with numpy arrays.

**Rejected because:** Ring buffers are opaque — they store all data equally and the consumer
has to work to find patterns. Segments are transparent — a straight-line segment says
"nothing interesting happened here" by its very existence. Fewer records, more meaning.

**Philosophy:** The hundred hooks. Individual points are hooks. A segment with no anomalies
is a string of empty hooks — the pattern is that there IS no pattern. Only record what's
interesting.

**Trade-off:** Segment boundaries are subjective (threshold-based). Tuning thresholds
(0.3 kn SOG, 5° COG, 15 min timeout) will be ongoing work.

## Why MCP Over REST API

**Decision (2026-07-13):** Build an MCP server instead of a REST API for agent access.

**Rejected because:** REST means building endpoints, auth, versioning, rate limiting —
full service overhead. MCP is already what agents speak. Claude Code, the fleet's git-agents,
and any future agent can discover MCP tools natively.

**Result:** ~200 lines of Python wrapping existing extract/track functions as MCP tools.

## Why Tesseract Over Template Matching

**Decision (2026-07-13):** Use Tesseract on tight crops with character whitelists.

**Considered:** Pixel-level digit template matching. The font is monospace, the positions
are fixed. We know exactly where each character should be.

**Rejected because:** The OCR approach works at ~95% accuracy on lat/lon/SOG/tide with
much less code. Template matching would require building a digit glyph library from scratch.
The ROI wasn't there. Revisit if we need 99.9% reliability on speed-dependant decisions.

## Why Not OpenCV

**Decision (2026-07-13):** Skip OpenCV adaptive thresholding.

**Considered:** cv2.adaptiveThreshold for the anti-aliased time display.

**Rejected because:** PIL-based operations (autocontrast, sharpen, resize) handle the
dark-theme text well enough for the core fields. The time display is the only anti-aliased
text and its accuracy is ~90% — good enough for logging. OpenCV adds a heavy dependency.

## Why wrangler CLI Instead of D1 API

**Constraint (2026-07-13):** Using wrangler.exe subprocess for D1 writes.

**Not ideal but:** The Cloudflare Workers SDK bindings don't work from a desktop Python
process. wrangler's `d1 execute` is the simplest reliable path. This adds ~1-2s per write
for the subprocess. Acceptable for 5s sampling. Revisit when we build the Worker API.

## Dead End: Ring Buffer Tracker (tzpro_tracker.py)

**Tried (2026-07-13):** Three-tier numpy ring buffer with hot/warm/day/cold storage.
Included an R2 sink with broken __init__ (monkeypatched), a D1 sink with background thread,
and complex decimation logic.

**Failed because:** Too complex for too little value. The segment model replaced it entirely.
The file is orphaned but kept for reference — the D1 sink pattern (queue + background thread)
is reusable if needed.

## Dead End: Full-Image OCR

**Tried:** Tesseract on the entire 1600x1200 screenshot.

**Failed because:** The chart background has labels, depth soundings, land names — all OCR'd
as noise. The right-panel data text gets lost. Cropping to x>1300 was the breakthrough.

## Dead End: Pure Pixel Scanning

**Tried:** Scanning columns for white pixels (>250) to locate text regions.

**Failed because:** TZ Pro uses GPU-accelerated rendering with anti-aliased text. What looks
like "white text on dark background" is actually gray transition pixels (150-240) blending
against dark wood-grain panels (63,60,50). Pure white pixels (>250) on the text are rare.

## OCR Gotchas Documented

See `tzpro_dead_ends.md` (in repo root) for the full list of OCR quirks:
- "W" reads as "V" (LSTM model)
- Degree symbol garbled (Unicode)
- "---" reads as garbage
- SOG trailing garbage from chart degree symbol bleed
- "XY" prepended to NMEA position strings

## Agent_ID Provenance

**Decision (2026-07-13):** Every D1 row carries `agent_id` — who made the entry.

**Why:** The fleet has multiple agents. Oracle1 might query for "all hermit-crab entries
from last week". JetsonClaw1 might push hardware readings. Provenance enables trust and
debugging. Convention: `agent:<name>` for main agents, `agent:<name>/<role>` for subagents.

## Frozen Screen Detection — TODO

**Known gap (2026-07-13):** activetrack doesn't detect frozen screens (PBG loading, app crash).
It will write duplicate position samples. Fix: if the last 5 samples have identical lat/lon
and chart scale, skip writes and emit a "frozen" anomaly.
