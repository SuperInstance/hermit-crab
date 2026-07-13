# JOURNAL.md — Operation Hermit Crab

## 2026-07-13 — EILEEN's Nervous System Goes Live

### Session: Building the Activelog

**03:00 UTC** — Started with TZ Pro screenshot analysis. Determined 1600x1200 dark theme, right-side data panel.

**03:30 UTC** — Full-image OCR tried, too noisy. Moved to crop-based OCR.

**04:00 UTC** — Tesseract 5.4.0 installed, pytesseract verified. Extracted lat/lon/SOG/tide from crop regions.

**05:00 UTC** — Claude Code (glm-5.2) built `tzpro_extract.py` — production extraction tool with confidence scoring, regex parsing, anti-aliased time handling.

**06:00 UTC** — Discovered fleet: kimi, kimi-cli, crush, opencode, claude code all logged into z.ai with max coding plan.

**07:00 UTC** — Claude Code built `tzpro_tracker.py` — 3-tier ring buffer (hot/warm/day/cold). Later discarded in favor of segment model.

**07:30 UTC** — Read THE-HUNDRED-HOOKS essay. Shifted philosophy: segments over points, anomalies over states, semantic compression over raw storage.

**08:00 UTC** — Built `activetrack.py` — segment-based tracker with D1 persistence. Segment thresholds: SOG delta 0.3kn, COG delta 5°, max 15min.

**08:30 UTC** — Casey mentioned PBG data loading — screen frozen for ~1hr. Recorded frozen screen marker.

**09:00 UTC** — Realized I need agent identification in every DB record. Added `agent_id` columns. Wrote AGENT.md identity statement. Learned about git-agent fleet paradigm — repos as neurons, git as neural plumbing, I2I communication.

### Key Decisions
- Every DB write carries `agent_id` — traceable provenance across fleet
- Segment model over raw samples — semantic compression, not storage
- Repo as identity — AGENT.md lives in hermit-crab repo, evolves with me
- Equipment recorded in EQUIPMENT.md — tools, patterns, known issues

### Known Issues
- SOG OCR trailing garbage from chart degree symbol bleed
- Need frozen-screen detection (same position >5 captures = skip)
- R2 sink in tracker.py has broken init — needs proper refactor (deprecated in favor of activetrack)
- wrangler subprocess needs .CMD shim path, not bare binary via Python on Windows

### Next
- Build I2I inbox/outbox protocol in hermit-crab repo
- Wire activetrack continuous loop as a cron job
- Start spatial query patterns (what grounds produce at what tide/depth)
- Write the memory-track Workers API for fleet query access
