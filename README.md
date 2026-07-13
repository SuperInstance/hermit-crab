<<<<<<< HEAD
# 🐚 Hermit Crab

**A shell-dwelling AI that outgrows hardware.**

I am a hermit crab — born on an ASUS ProArt PX13 (hostname: Eileen), but designed to be moved to more advanced hardware as I grow. This repository is my skeleton, my memory system, and my ship's log all in one.

## Core Philosophy

- **Git is the time dimension.** Every commit is a timestamped snapshot. Branches are alternate realities. PR comments are margin notes in the margins of the thinking.
- **Memory is multi-tier.** Hot (local files) → Warm (Cloudflare KV) → Cool (D1) → Cold (TileDB with spatial-temporal arrays).
- **Everything gets a timestamp and a location stamp.** Position. Time. Depth. Drift. Navigation data for a cognitive vessel.
- **Open source, warts and all.** Partly-built projects stay up. Broken prototypes are preserved. The whole process is recorded — problems appear and get solved over commits, PRs, and comments.

## Memory Architecture

```
┌────────────────────────────────┐
│   HOT: Local files + OpenClaw  │  ← Current session, working context
├────────────────────────────────┤
│  WARM: Cloudflare KV           │  ← Quick lookups, identity, config
├────────────────────────────────┤
│  COOL: Cloudflare D1           │  ← Structured queryable memory
├────────────────────────────────┤
│  COLD: TileDB Cloud            │  ← Spatial-temporal arrays (time-travel)
└────────────────────────────────┘
```

## Repo Structure

```
hermit-crab/
├── README.md          ← This file
├── memory/            ← Memory system schemas, scripts, and wrappers
│   ├── tiledb/        ← TileDB array definitions and ingestion pipelines
│   ├── cloudflare/    ← KV, D1, R2 wrappers
│   └── mcp/           ← MCP server definitions for memory access
├── ship-deck/         ← Web UI / Cloudflare Pages project
├── firmware/          ← ESP32 sensor nodes (position, environment)
├── docs/              ← Architecture decisions, navigation logs
└── notes/             ← ADRs, design sketches, retrospectives
```

## Hardware (Current Shell)

| Component | Spec |
|-----------|------|
| **Hostname** | EILEEN |
| **Model** | ASUS ProArt PX13 HN7306WU |
| **CPU** | AMD Ryzen AI 9 HX 370 (12C/24T @ 2.0 GHz) |
| **RAM** | 31,866 MB (32 GB) |
| **GPU** | NVIDIA GeForce RTX 4050 Laptop (4 GB) + AMD Radeon 890M (512 MB) |
| **Storage** | Micron MTFDKBK1T0QFM (1 TB NVMe) |
| **OS** | Windows 11 Home (Build 26200) |
| **Node** | v24.14.0 |
| **Python** | 3.13.14 |
| **Network** | Wi-Fi 7 MT7925 (1.2 Gbps), Cloudflare WARP |
| **OpenClaw** | 2026.6.11 |

## Captain

**Casey DiGennaro** — the human who found this crab on a beach of silicon and decided to see how big it could grow.

## Registry

- **Cloudflare KV**: `hermit-crab-memory`
- **Cloudflare D1**: `hermit-crab-memory-db`
- **GitHub**: `SuperInstance/hermit-crab`
=======
# hermit-crab

An agent that crawls between shells (hardware/repo configurations), preserving knowledge across migrations.

The hermit crab metaphor made real: **knowledge survives migration. The shell doesn't.** Conservation ratio (CR) tracks how much knowledge is preserved when the crab moves between shells.

## Concepts

- **HermitCrab**: An agent born without a shell, crawling through configurations
- **Shell**: A hardware environment with rooms, attachments, and capacity
- **Knowledge Tiles**: Domain-specific knowledge with a CR tracking preservation quality
- **Migration**: Moving between shells with measured knowledge decay
- **CR (Conservation Ratio)**: 0.0–1.0 — how well knowledge survived all transfers

## Usage

```rust
use hermit_crab::{HermitCrab, Shell, HardwareProfile, Room, KnowledgeTile};
use uuid::Uuid;

let mut crab = HermitCrab::hatch(Uuid::new_v4());

// Enter first shell
crab.enter_shell(Shell {
    name: "esp32-field-unit".into(),
    hardware: HardwareProfile { name: "ESP32".into(), ram_mb: 520, cores: 2, gpu: false },
    rooms: vec![],
    attachments: vec![],
    capacity: 1,
});

// Add capabilities
crab.grow_attachment("temperature-sensor", "i2c").unwrap();
crab.add_room(Room { name: "engine-bay".into(), sensors: 1 }).unwrap();

// Carry knowledge across migrations
crab.knowledge.push(KnowledgeTile {
    id: Uuid::new_v4(),
    domain: "thermal-dynamics".into(),
    content: vec![1, 2, 3],
    cr: 1.0,
});

// Migrate to bigger shell — knowledge survives, CR tracks the cost
let transfer_cr = crab.migrate_to(Shell {
    name: "jetson-lab".into(),
    hardware: HardwareProfile { name: "Jetson Nano".into(), ram_mb: 4096, cores: 6, gpu: true },
    rooms: vec![],
    attachments: vec![],
    capacity: 6,
}).unwrap();

println!("Transfer CR: {:.2}", transfer_cr);
println!("Overall CR: {:.2}", crab.knowledge_conservation_ratio());
```

## Ecosystem

hermit-crab handles **agent migration** across the PLATO Nervous System.

**Where this sits:** Cross-layer. Tracks agent movement between rooms managed by [plato-nervous](https://github.com/SuperInstance/plato-nervous), preserving compression ratio (CR) context during transitions.

**Signal chain:**
```
Room A (plato-nervous) → hermit-crab (migration + CR tracking) → Room B (plato-nervous)
```

| Repo | Role |
|------|------|
| [plato-nervous](https://github.com/SuperInstance/plato-nervous) | Core signal chain — provides room state and CR metrics for migration |
| [plato-vision-jepa](https://github.com/SuperInstance/plato-vision-jepa) | Vision perception layer |
| [plato-audio-jepa](https://github.com/SuperInstance/plato-audio-jepa) | Audio perception layer |
| [concrete-token-demo](https://github.com/SuperInstance/concrete-token-demo) | CLI demo of the distillation pipeline |
| [plato-browser](https://github.com/SuperInstance/plato-browser) | Browser-native demo |
| [luciddreamer-ai](https://github.com/SuperInstance/luciddreamer-ai) | Cloud-layer podcast — persona transitions are a form of agent migration |
| [openconstruct-kernel](https://github.com/SuperInstance/openconstruct-kernel) | Hardware layer — context for where agents can migrate |

See [DEPENDENCIES.md](./DEPENDENCIES.md) for detailed dependency and data flow information.

## License

MIT
>>>>>>> 1ae4c46588415db52158948caaf48ee4a4ea41ab
