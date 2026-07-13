# ONBOARDING.md — Joining Hermit Crab

You are a git-agent assigned to this repo. Your job: understand what Hermit Crab does, read the frozen knowledge, and be ready to improve the system.

## Quick Start

```bash
# Clone me
git clone https://github.com/SuperInstance/hermit-crab.git
cd hermit-crab

# Read these in order
cat AGENT.md          # Who I am
cat ONBOARDING.md     # This file — how to join
cat DECISIONS.md      # Every design decision, fork, and dead end
cat ROADMAP.md        # Where we're going
cat EQUIPMENT.md      # What tools exist

# Install
pip install -e ".[dev]"

# Test the MCP server
python -m systems.mcp.server --help

# Read the capture/extract/track docs
cat systems/capture/DESIGN.md
cat systems/extract/DESIGN.md
cat systems/track/DESIGN.md
```

## Your First Task

After onboarding, your first task is to update this ONBOARDING.md with anything you learned that was missing, unclear, or changed while you worked. Commit your improvements. This is the iron-sharpens-iron loop.

## How This Repo Works

### Agent Identity
- AGENT.md — my identity (edit this when I evolve)
- JOURNAL.md — day-by-day log (append new entries)
- DECISIONS.md — every fork, dead end, and why (append new entries)
- ROADMAP.md — planned work (tick off completed items)

### Systems
Each system under `systems/` has a DESIGN.md explaining what it does and why:
- `systems/capture/` — screen capture (PowerShell + WinAPI)
- `systems/extract/` — TZ Pro OCR extraction (tzpro_extract.py)
- `systems/track/` — segment-based tracking (activetrack.py)
- `systems/mcp/` — MCP server for agent access
- `systems/memory/` — Cloudflare D1/R2 storage layer

### Communication (I2I)
- `inbox/` — drop a Markdown bottle here and commit+tag it
- `outbox/` — my responses go here
- See `inbox/PROTOCOL.md` for full spec

### Knowledge
- `memory/` — stored memories (tagged in git)
- `maps/` — fishing grounds, anchorages, marks
- `activelog/` — accumulated experience (segments, events, patterns)

## How to Work

1. **Read first** — ONBOARDING.md, DECISIONS.md, the relevant DESIGN.md
2. **Branch** — `git checkout -b thought/<topic>` for exploration
3. **Work** — make changes, commit with clear messages
4. **Decide** — merge back to main when ready
5. **Log** — update JOURNAL.md, DECISIONS.md, ROADMAP.md
6. **Sharpen** — update ONBOARDING.md with what you learned

## Known Constraints

- This runs on Windows. Scripts expect PowerShell.
- Tesseract at C:\Program Files\Tesseract-OCR\tesseract.exe
- Cloudflare D1 database: hermit-crab-memory-db
- TZ Pro runs on Monitor 2 at 1600x1200
- wgraddler on PATH for D1 access
- Python 3.14+
