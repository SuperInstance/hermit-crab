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

## License

MIT
