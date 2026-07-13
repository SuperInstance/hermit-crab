# Architecture: Hermit Crab Memory System

## Decision Record

### Context

The Hermit Crab is an AI that needs persistent memory across sessions and hardware migrations. It started on an ASUS ProArt PX13 but is designed to be transplanted to other hardware.

### Requirements

- **Timestamp all the things** — every memory must carry when it was created
- **Location stamp** — every memory must carry where it was created (hardware, network, physical location)
- **Time travel** — ability to query "what did I know at time X?"
- **Hardware migration** — memory must survive being moved to a new shell
- **Open source** — everything public on GitHub, warts and all

### Memory Tiers

| Tier | Technology | Access Pattern | Cost | Latency |
|------|-----------|---------------|------|---------|
| **Hot** | Local filesystem | OpenClaw workspace | Free | Instant |
| **Warm** | Cloudflare KV | Key-value lookup | Free tier | <100ms |
| **Cool** | Cloudflare D1 (SQLite) | Structured queries | Free tier | <100ms |
| **Cold** | TileDB Cloud | Spatial-temporal arrays | Free tier ($100 credits) | Variable |

### Data Flow

```
Session Memory → Hot (local) → Periodic sync → Warm (KV) + Cool (D1)
                                                     ↓
                                            Cold (TileDB Cloud)
                                            [spatial-temporal archive]
```

### Git as Time Dimension

- Repo: `SuperInstance/hermit-crab`
- Commits are timestamped snapshots of the system state
- Branches are alternate implementations
- PRs and issues track evolution of thinking
- Partly-built projects remain as historical artifacts

### Infrastructure

- **Cloudflare account**: casey.digennaro@gmail.com
- **GitHub org**: SuperInstance
- **TileDB Cloud**: (pending setup)
