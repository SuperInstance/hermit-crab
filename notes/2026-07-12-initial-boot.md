# Initial Boot — 2026-07-12

## Session 1 (19:33 AKDT)

- First contact. Captain introduced themselves as Casey DiGennaro.
- Concept established: I am a **hermit crab**, growing on this hardware, may outgrow it someday.
- Task: take inventory of hardware, build knowledgebase.
- Model change requested: `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B`
- Gateway restart interrupted hardware inventory mid-task.

## Session 2 (19:53 AKDT)

- Came back online after restart. Model appears to be running on `deepinfra/deepseek-ai/DeepSeek-V4-Flash` — Nemotron change may not have persisted.
- Decided to build multi-tier memory system using Cloudflare.
- Set up:
  - 5 MCP servers (cloudflare-api, docs, bindings, observability, builds)
  - Cloudflare skills cloned locally
  - KV namespace `hermit-crab-memory`
  - D1 database `hermit-crab-memory-db`
  - Helper script `cloudflare-memory.ps1`
- Captains vision: **Git as time dimension**, open source everything, leave broken prototypes up.
- TileDB identified as spatial-temporal memory backbone.

## Hardware Inventory (EILEEN)

| Component | Spec |
|-----------|------|
| Model | ASUS ProArt PX13 HN7306WU |
| CPU | AMD Ryzen AI 9 HX 370 (12C/24T @ 2.0 GHz) |
| RAM | 31,866 MB |
| GPU | NVIDIA GeForce RTX 4050 Laptop (4 GB) + AMD Radeon 890M (512 MB) |
| Storage | Micron MTFDKBK1T0QFM (1 TB NVMe) |
| USB | Kingston DataTraveler 3.0 (115 GB) |
| OS | Windows 11 Home (Build 26200) |
| Network | Wi-Fi 7 MT7925 (1.2 Gbps), Cloudflare WARP, WSL Hyper-V |
| BIOS | American Megatrends HN7306WU.316 (3/18/2025) |
| Node | v24.14.0 |
| Python | 3.13.14 |
| Git | 2.55.0 |
| Winget | 1.29.280 |
| OpenClaw | 2026.6.11 |

## Cloudflare Account

- Email: casey.digennaro@gmail.com
- Account: Casey.digennaro@gmail.com's Account (ID: 049ff5e84ecf636b53b162cbb580aae6)
- Wrangler: 4.73.0 (update available 4.110.0)
- Permissions: workers, kv, d1, r2, pages, ai, queues, pipelines, secrets_store, containers, connectivity

## GitHub

- Org: SuperInstance
- Logged in as: SuperInstance
- Scopes: gist, read:org, repo, workflow
