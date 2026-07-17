# 🦀 Hermit Crab

**Agent that migrates between hardware shells, preserving knowledge across migrations.**

Tracks conservation ratio — how much memory, context, and capability survives a shell change — in Rust.

## Why?

An agent wakes up in a new runtime. Different model, different tools, different constraints. What survives?

Hermit Crab measures the answer. It tracks:
- **Memory conservation ratio** — what fraction of long-term memory persists across migrations
- **Tool coverage delta** — which capabilities survive the shell change
- **Context loss** — how much conversational context degrades with each hop
- **Recovery cost** — time/tokens to rebuild lost context

## Philosophy

From the EILEEN philosophy:

> The disjointed cells of a body making a consciousness through connectivity.

An agent's identity isn't in the model — it's in the connections between memory, tools, and context. When the shell changes, the connections are tested. Hermit Crab measures what holds.

## Architecture

Written in Rust. Designed for edge environments (fishing boats, field stations, offline nodes) where:
- Hardware is constrained (wattage, memory, compute)
- Network is intermittent at best
- Conservation isn't a preference — it's a physical law

## Repository Structure

```
AGENTS.md                         — Agent workspace configuration
FISHINGLOG_DAW_DESIGN.md          — Design doc: Digital Assistant Workspace
FISHINGLOG_FOUNDING.md            — Origin story: why this exists
FISHINGLOG_PHILOSOPHY.md          — The EILEEN philosophy (five meditations)
MEMORY.md                         — Curated long-term memory
ONBOARDING.md                     — Onboarding for new agent generations
REVERSE_ACTUALIZATION_ANALYSIS.md — Analysis of goal-directed vs emergent behavior
SOUL.md                           — Agent persona/tone
TOOLS.md                          — Environment-specific tool notes
USER.md                           — About the operator
```

## Origin

Built for the SuperInstance ecosystem. Born on a fishing boat in Ketchikan, Alaska.

## License

MIT
