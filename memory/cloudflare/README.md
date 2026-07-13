# Cloudflare Memory Layer

## KV Namespace: `hermit-crab-memory`

Fast key-value lookups for identity, config, and quick context.

**Namespace ID**: `d7660e0691cc4a06bf189a14695cbe1d`

### Current Keys

| Key | Value |
|-----|-------|
| `identity.name` | Unnamed Hermit Crab |
| `captain.name` | Casey DiGennaro |
| `captain.title` | Captain |
| `ship.boot` | First boot record |

## D1 Database: `hermit-crab-memory-db`

Structured queryable memory with SQL.

**Database ID**: `f49c9a90-b4a0-4a55-bd58-0bfa24dbafb6`

### Schema

```sql
CREATE TABLE memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    category TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

## MCP Servers

Configured in OpenClaw:

| Server | URL | Purpose |
|--------|-----|---------|
| `cloudflare-api` | `https://mcp.cloudflare.com/mcp` | Full API access (2,500+ endpoints) |
| `cloudflare-docs` | `https://docs.mcp.cloudflare.com/mcp` | Docs search |
| `cloudflare-bindings` | `https://bindings.mcp.cloudflare.com/mcp` | Workers storage/AI primitives |
| `cloudflare-observability` | `https://observability.mcp.cloudflare.com/mcp` | Logs and debugging |
| `cloudflare-builds` | `https://builds.mcp.cloudflare.com/mcp` | Build management |
