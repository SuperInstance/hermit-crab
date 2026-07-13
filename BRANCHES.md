# 🐚 Hermit Crab

**Two takes on the same metaphor:**

## `master` branch — Rust crate
The existing Rust implementation handles **agent migration between shells** with Conservation Ratio (CR) tracking. An agent crawls between hardware configurations, preserving knowledge with measurable decay.

## `memory-system` branch — Memory spine
This branch adds the **persistent knowledge storage layer**:
- Multi-tier memory (local → KV → D1 → TileDB)
- Timestamped + location-stamped spatial-temporal arrays
- Cloudflare edge + TileDB cold storage

## Why two branches with no shared history?
Because the metaphor was independently discovered — and that's worth preserving. The git record shows two approaches evolving separately before they merge.
