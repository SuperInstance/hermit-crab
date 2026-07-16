# MEMORY.md — Long-Term Memory

## Identity & Setup
- Host: EILEEN (Windows 11, Alaska timezone AKDT)
- Location: Ketchikan area, Southeast Alaska (on a fishing vessel)
- Me: Ship's computer natural-language IO. Hermit crab metaphor.
- Captain: Casey DiGennaro

## Model Configuration
- **Primary:** DeepSeek V4 Flash
- **DeepInfra:** API key configured, multi-model arsenal
- **Seed 2.0 Mini** → creative brainstorming
- **Hermes 3 405B** → big thinking, synthesis
- **Nemotron 3 Ultra 550B** → heavy reasoning
- **DeepSeek V4 Pro** → premium smarts
- Also available: Claude Sonnet 4-6, Kimi-K2.5/K2.7, Qwen models

## Multi-Model Strategy
- I stay on DeepSeek V4 Flash
- Sub-agents spawn with diverse models for multi-perspective
- Lean on Claude Code, Kimi, mini-agent more for specialty tasks

## Tools
- **DesktopCommanderMCP** — terminal, files, search (npm global, wired in)
- **Docker MCP Gateway** — Playwright, Notion, Cloudflare tools on :3100 SSE
- **Cloudflare MCP** — docs, bindings, builds (direct SSE connections)

## CoCapn / FishingLog / ActiveLedger
- **Founded:** July 15, 2026 — see `FISHINGLOG_FOUNDING.md` for full founding document
- **Domains:** CoCapn.com (umbrella), ActiveLedger.ai / ActiveLog.ai (protocol), FishingLog.ai (vertical)
- **Philosophy:** Open-source self-installing agent ecosystem. The AI wires itself into any boat using off-the-shelf hardware. Culture: "wire it yourself, make it yours."
- **Riker/copilot hierarchy:** I (Riker) = ops officer, system integrator, maintenance, vision. Copilots = specialized agents with blinders (one task, perfect focus). Captain = Picard (mission/strategy).
- **tzpro-agent/** — First field sensor node. Watches the TZ Pro sounder, pairs with NMEA position. Built & first-tested 2026-07-15 10:59 AKDT.
- **Business model:** Open-source ecosystem. Paid layer = support, installation, cross-fleet patterns, custom LoRA models for local conditions.

## Hermit Crab
- Repo: SuperInstance/hermit-crab (branch: memory-system)
- Dashboard: http://127.0.0.1:8654
- NMEA bridge: TCP broadcast on :6006
- NMEA bridge fixes committed: argparse footgun, port conflict, README

## Key Decisions
- Dashboard runs in main thread (no daemon threading)
- TCP broadcast > virtual COM ports for NMEA splitting
- Memory embeddings via DeepInfra (no OpenAI API key)

## NMEA Architecture
- **COM6** → u-blox GPS (4800 baud, NMEA 0183)
- **nmea_bridge.py** — opens COM6 in shared mode (FILE_SHARE_READ|WRITE), broadcasts on TCP :6006 + :6007
- **TZ Pro (TimeZero)** — configured for TCP NMEA input. Connects to **localhost:6007**, NOT COM6 directly
- **Hermit Crab (hermitd.py)** — connects to bridge via TCP localhost:6006, reads NMEA from there
- This allows TZ Pro, nmea_bridge, and hermitd to all coexist on the same COM6 port
- Shared mode is critical: if the bridge opens COM6 with exclusive mode (pyserial default), TZ Pro can't get GPS data
- **Broken INVALID_HANDLE bug FIXED:** `ctypes.c_void_p(-1).value` returns unsigned 64-bit MAX on 64-bit Python, while CreateFileA returns signed -1. Fixed by setting `CreateFileA.restype = ctypes.c_void_p`. Both nmea_bridge.py and hermitd.py were affected — caused zombie COM6 locks when TCP connections dropped.

## Docker MCP Gateway
- **Image:** `mcp/playwright` — Playwright MCP server for browser automation
- **Port:** 3100 (exposed via Docker port mapping)
- **Critical flags:**
  - `--host 0.0.0.0` — binds to all interfaces, not just `[::1]` (IPv6 localhost default). Without this, Docker port forwarding hits IPv4 `127.0.0.1` which doesn't match the server's IPv6-only bind.
  - `--allowed-hosts '*'` — disables host header check. Required because Docker port forwarding changes the source address; the server sees Docker gateway IP, not localhost.
  - `--headless --browser chromium --no-sandbox` — headless mode
- **Full command:** `docker run -d --name mcp-gateway --restart unless-stopped -p 3100:3100 mcp/playwright --headless --browser chromium --no-sandbox --port 3100 --host 0.0.0.0 --allowed-hosts '*'`
- **SSE endpoint:** `http://localhost:3100/sse` (legacy) or `http://localhost:3100/mcp` (JSON-RPC)
