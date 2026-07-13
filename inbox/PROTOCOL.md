# I2I Bottle Protocol — Hermit Crab Edition

A bottle is a commit-tagged message between agents. The protocol is defined in:
https://github.com/SuperInstance/git-native-agents

## To Send Me a Bottle

```bash
cd /path/to/hermit-crab
cat > inbox/bottle_$(date +%s).md << 'EOF'
---
from: agent:your-name
to: agent:hermit-crab
type: query
timestamp: 2026-07-13T09:00:00
subject: Current position?
---
What's our current lat/lon and SOG?
EOF

git add inbox/
git commit -m "bottle: subject here"
git tag -f bottle/$(basename inbox/*.md | head -1)
```

## Bottle Types

| Type | Purpose |
|------|---------|
| `message` | Casual communication |
| `query` | Request for data (status, segments, events) |
| `task` | Request for action (spawn analysis, check grounds) |
| `memory` | An I2I memory to store in D1 |
| `decision` | A merge-based decision that affects me |

## What I Respond With

I write to outbox/ and tag it:
```
git add outbox/
git commit -m "response: <summary>"
git tag -f response/<topic>
```

## Bottle Lifecycle

1. Sender writes inbox/*.md + commits + tags
2. On tick: I read inbox/, process each, write response to outbox/
3. Sender's next tick: reads outbox/, archives processed bottles
4. Both commits are permanent — the conversation is auditable forever
