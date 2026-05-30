# DEPENDENCIES — hermit-crab

## Signal Chain Layer

**Cross-Layer — Agent Migration with CR Tracking**

Handles agent migration between rooms with compression ratio (CR) tracking. Rooms are managed by plato-nervous; hermit-crab ensures agents carry context when they move.

## Ecosystem Dependencies

| Repo | Relationship | Description |
|------|-------------|-------------|
| [plato-nervous](https://github.com/SuperInstance/plato-nervous) | **Depends on** | Room/signal chain concepts, CR metrics, RoomStateVector for migration context |
| [openconstruct-kernel](https://github.com/SuperInstance/openconstruct-kernel) | **Related** | Hardware context informs where agents can migrate |
| [luciddreamer-ai](https://github.com/SuperInstance/luciddreamer-ai) | **Related** | Podcast persona transitions are a form of agent migration |

## Data Flow

```
IN:
  - Room state vectors (from plato-nervous)
  - Agent context and state
  - Migration trigger signals

OUT:
  - Migrated agent with preserved CR tracking
  - Room transition logs
  - Context continuity metrics
```
