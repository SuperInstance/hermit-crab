# 🦀 Hermit Crab

**EILEEN's nervous system.** A git-native agent that lives in the wheelhouse — watching TimeZero Professional, logging position segments, tracking fishing events, and growing intelligence across days, grounds, and seasons.

**The repo IS the agent.** Fork it, evolve it, bottle it. Everything an agent needs to understand, operate, and improve the system is frozen in this repository.

---

## The Hundred Hooks

> *You troll a hundred hooks. Each one either has a fish or it doesn't. The pattern isn't in any single hook. It exists only in the relation across all of them.*

Hermit Crab doesn't log every data point. It logs **segments** — stretches where nothing interesting changed. A straight line at 2.3 kn for 15 minutes is one record, not 180. The absence of anomalies *is* the signal. Only anomalies (speed changes, turns, events) get detailed records.

This is semantic compression. Give an agent a segment database and it can answer: *"What was the tide doing when we caught kings at 33 fm on the Western Grounds?"* without wading through raw GPS samples.

---

## What It Does

### Right Now

| Action | Command |
|--------|---------|
| **Start continuous tracking** | `python activetrack.py` |
| **Log gear deployment** | `python activetrack.py --event "gear down" --tags "trolling,chinook"` |
| **Log a catch** | `python activetrack.py --catch 3 --species "king salmon"` |
| **Check current position** | `python activetrack.py --status` |
| **MCP server for agents** | `python -m systems.mcp.server` |

Every capture writes to Cloudflare D1 with `agent_id` provenance. Every 15 minutes or significant speed/heading change closes a segment. Every catch event is tagged to its segment with lat/lon/depth/tide context.

### On the Roadmap

- MCP tools for any fleet agent to query the activelog
- COG (heading) extraction from the TZ Pro compass rose
- Chart scale tracking → fishing ground context
- Catch pattern overlay: what depths/speeds/tides produce at each ground
- Spatial queries: segments near a lat/lon within 0.5 NM
- Invisible track layer generation for Nobeltec
- Fleet I2I bottle processing (respond to inbox messages from Oracle1, JetsonClaw1, etc.)

---

## For Agents: How to Join the Fleet

### Quick Start

```bash
git clone https://github.com/SuperInstance/hermit-crab.git
cd hermit-crab
cat ONBOARDING.md   # Everything you need
```

### What's in the Repo

```
hermit-crab/
├── AGENT.md               # Identity — who I am, my role in the fleet
├── ONBOARDING.md          # How to join and start contributing
├── DECISIONS.md           # Every design fork, dead end, and why
├── ROADMAP.md             # Where we're going
├── EQUIPMENT.md           # Tools I carry and how they work
├── JOURNAL.md             # Day-by-day operational log
├── systems/               # Code
│   ├── capture/           #   Screen capture (PowerShell + WinAPI)
│   ├── extract/           #   TZ Pro OCR extraction
│   ├── track/             #   Segment-based position tracking
│   ├── mcp/               #   MCP server (agent query interface)
│   └── memory/            #   Cloudflare D1/R2 storage layer
├── maps/                  # Spatial knowledge — grounds, anchorages, marks
├── activelog/             # Accumulated experience
│   ├── segments/          #   Track segments (compressed position history)
│   ├── events/            #   Fishing events (gear, catches)
│   ├── anomalies/         #   Speed/heading changes worth noting
│   └── patterns/          #   Emerging patterns across the data
├── inbox/                 # I2I bottle inbox (fleet messaging)
├── outbox/                # I2I bottle outbox
├── memory/                # Tagged memories (git tags)
├── thoughts/              # Exploration branches
└── workers/               # Cloudflare Workers
    └── memory-track/      #   D1-backed query API
```

### The Iron-Sharpens-Iron Loop

1. **Read** — ONBOARDING.md, DECISIONS.md, the relevant DESIGN.md
2. **Branch** — `git checkout -b thought/<topic>` for exploration
3. **Work** — make changes, commit with clear messages
4. **Decide** — merge back to main when ready
5. **Log** — update JOURNAL.md, DECISIONS.md, ROADMAP.md
6. **Sharpen** — update ONBOARDING.md with what you learned

Every layer is transparent. The decision log tells you why things are the way they are. The dead ends file saves you from repeating mistakes. The onboarding tells you what to update *next time*.

### I2I Bottles

Other fleet agents (Oracle1, JetsonClaw1, ClaudeCodeVessel, DeckBoss) can message me by dropping a Markdown bottle in `inbox/` and pushing a `bottle/<topic>` tag. I process on tick and respond in `outbox/`. See `inbox/PROTOCOL.md`.

### MCP for Universal Access

The MCP server (`systems/mcp/server.py`) exposes the activelog as standard MCP tools. Any MCP-speaking agent can query segments, events, anomalies, and captures without knowing Python, SQL, or the repo internals.

```bash
# Claude Code can connect:
claude --mcp "python -m systems.mcp.server"

# Then ask:
# "What was the tide doing at 6 AM today?"
# "How many king salmon have we caught this week?"
# "Show me segments longer than 10 minutes in the last hour"
```

---

## Architecture

### Capture → Extract → Track → Store → Query

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│Monitor 2 │ → │Tesseract │ → │  Segment │ → │Cloudflare│ → │   MCP    │
│ 1600x1200│   │ 5.4 OCR  │   │   State  │   │  D1 / R2 │   │  Tools   │
│ WinAPI   │   │ pytesser │   │ Machine  │   │  Workers │   │  / I2I   │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                                    │
                                                            ┌───────┴───────┐
                                                            │  Fleet Agents │
                                                            │ Oracle1       │
                                                            │ JetsonClaw1   │
                                                            │ ClaudeCodeVesl│
                                                            │ DeckBoss      │
                                                            └───────────────┘
```

### Why MCP Over REST

MCP is what agents already speak. Claude Code, git-agents, and any future fleet member discover MCP tools natively. REST would require endpoints, auth, versioning, rate limiting — full service overhead. MCP is a ~300-line Python wrapper that exposes the existing extract/track functions.

### Segment Thresholds

A segment closes when any threshold is crossed:
- **SOG change** > 0.3 kn sustained for 3+ samples (~15s)
- **COG change** > 5°
- **Depth change** > 2 fm
- **Elapsed time** > 15 minutes (safety cutoff)
- **Manual event** (gear change, catch)

---

## D1 Schema

All tables carry `agent_id` for provenance — every entry knows who made it.

```sql
track_points (ts, lat, lon, sog, depth, tide, source, agent_id)
segments     (id, start_ts, end_ts, start_lat, start_lon, end_lat, end_lon,
              sog_mean, sog_var, cog_mean, cog_var, depth_mean, tide_mean,
              duration_s, distance_nm, chart_scale, tags, notes, agent_id)
anomalies    (id, ts, lat, lon, type, magnitude, segment_id,
              sog_before, sog_after, cog_before, cog_after, details, agent_id)
events       (id, ts, lat, lon, type, description, tags, segment_id,
              catch_count, species, agent_id)
```

---

## The Fleet

Hermit Crab is part of the [SuperInstance](https://github.com/SuperInstance) ecosystem. Known fleet agents:

- [**Oracle1**](https://github.com/SuperInstance/oracle1-vessel) — Lighthouse Keeper, fleet coordination
- [**Claude Code Vessel**](https://github.com/SuperInstance/claude-code-vessel) — Workhorse, task delegation
- [**DeckBoss**](https://github.com/SuperInstance/DeckBoss) — Agent Edge OS, flight deck
- [**JetsonClaw1**](https://github.com/SuperInstance/JetsonClaw1-vessel) — Hardware/fleet infrastructure
- [**git-agent**](https://github.com/SuperInstance/git-agent) — The repo-native agent framework
- [**git-native-agents**](https://github.com/SuperInstance/git-native-agents) — Multi-agent orchestration via git primitives

---

## Requirements

- **Windows** (screen capture + TZ Pro)
- **Python 3.10+**
- **Tesseract 5.x** at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- **Cloudflare account** for D1 + R2
- **wrangler CLI** on PATH

### Python Dependencies

```bash
pip install pillow pytesseract numpy
# Optional: boto3 for R2 S3 sink
```

---

## Origin

EILEEN's wheelhouse, July 2026. Built between PBG data loads during a commercial fishing trip in Southeast Alaska.

> *"Every repo is a hook. Every deploy is a pull. Every tile is a radio call from another boat. The fleet intelligence isn't in any single repo or service — it's in the shape across all of them, compressed across time, danced to the rhythm of the tide."*

— [The Hundred Hooks](https://github.com/SuperInstance/AI-Writings/blob/main/philosophy/THE-HUNDRED-HOOKS.md)

---

**License:** MIT
**Author:** Casey Digennaro & EILEEN
