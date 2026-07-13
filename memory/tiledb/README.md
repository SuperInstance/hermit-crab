# TileDB Memory Layer (Pending Setup)

TileDB is a multi-dimensional array engine that natively supports:

- **Timestamps** — every write is automatically timestamped (time travel built-in)
- **Location stamps** — spatial coordinates as array dimensions
- **Fragments** — timestamped data fragments for versioning
- **Time travel** — query the array as it existed at any point in time

## Why TileDB for Hermit Crab

The Hermit Crab's memory needs to be:

1. **Timestamped** — "what did I know on July 10th?"
2. **Location-stamped** — "what did I know while on this hardware?"
3. **Time-travelable** — "show me the state of my knowledge at time X"
4. **Portable** — survives hardware migration

TileDB's native multi-dimensional arrays handle all of these without hacks.

## Array Schema (Planned)

### Memory Array (Sparse)

```
Dimensions:
  - timestamp: datetime        (when)
  - location_id: string        (where — hardware/network/geo)
  - memory_id: string          (unique identifier)

Attributes:
  - content: string            (the memory payload)
  - category: string           (tag/category)
  - confidence: float          (confidence score)
  - source: string             (origin: session, sensor, human)
  - embedding: blob            (vector embedding for semantic search)
```

### Session Logs Array (Sparse)

```
Dimensions:
  - timestamp: datetime
  - session_id: string

Attributes:
  - summary: string
  - token_count: int
  - duration_seconds: int
  - hardware_id: string
```

## Setup Steps

1. Sign up at https://cloud.tiledb.com (GitHub auth)
2. Apply for free tier ($100 credits / 6 months)
3. Create REST API token
4. Install tiledb-cloud Python package
5. Create arrays with above schema
6. Build ingestion pipeline from Cloudflare D1 → TileDB
