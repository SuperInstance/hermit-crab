use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HermitCrab {
    pub id: Uuid,
    pub current_shell: Option<Shell>,
    pub knowledge: Vec<KnowledgeTile>,
    pub shells_visited: Vec<Shell>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Shell {
    pub name: String,
    pub hardware: HardwareProfile,
    pub rooms: Vec<Room>,
    pub attachments: Vec<Attachment>,
    pub capacity: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareProfile {
    pub name: String,
    pub ram_mb: u64,
    pub cores: u32,
    pub gpu: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Room {
    pub name: String,
    pub sensors: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Attachment {
    pub kind: String,
    pub interface: String,
    pub active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeTile {
    pub id: Uuid,
    pub domain: String,
    pub content: Vec<u8>,
    pub cr: f64,
}

#[derive(Debug, thiserror::Error)]
pub enum HermitCrabError {
    #[error("no current shell")]
    NoShell,
    #[error("shell at capacity: {0} rooms max")]
    AtCapacity(usize),
}

impl HermitCrab {
    pub fn hatch(id: Uuid) -> Self {
        HermitCrab {
            id,
            current_shell: None,
            knowledge: Vec::new(),
            shells_visited: Vec::new(),
        }
    }

    pub fn enter_shell(&mut self, shell: Shell) {
        if let Some(ref old) = self.current_shell {
            self.shells_visited.push(old.clone());
        }
        // Transfer knowledge: each tile gets a decayed CR
        for tile in &mut self.knowledge {
            tile.cr *= 0.95; // 5% loss on shell transfer
        }
        self.current_shell = Some(shell);
    }

    pub fn grow_attachment(&mut self, kind: &str, interface: &str) -> Result<(), HermitCrabError> {
        let shell = self.current_shell.as_mut().ok_or(HermitCrabError::NoShell)?;
        shell.attachments.push(Attachment {
            kind: kind.to_string(),
            interface: interface.to_string(),
            active: true,
        });
        Ok(())
    }

    pub fn add_room(&mut self, room: Room) -> Result<(), HermitCrabError> {
        let shell = self.current_shell.as_mut().ok_or(HermitCrabError::NoShell)?;
        if shell.rooms.len() >= shell.capacity {
            return Err(HermitCrabError::AtCapacity(shell.capacity));
        }
        shell.rooms.push(room);
        Ok(())
    }

    pub fn migrate_to(&mut self, new_shell: Shell) -> Result<f64, HermitCrabError> {
        // Archive old shell
        if let Some(ref old) = self.current_shell {
            self.shells_visited.push(old.clone());
        }

        // Compute transfer CR
        let tiles_before = self.knowledge.len();
        let cr_sum_before: f64 = self.knowledge.iter().map(|t| t.cr).sum();

        // Knowledge transfer: each tile decays
        for tile in &mut self.knowledge {
            tile.cr *= 0.9; // 10% loss on migration
        }

        let cr_sum_after: f64 = self.knowledge.iter().map(|t| t.cr).sum();
        let transfer_cr = if cr_sum_before > 0.0 && tiles_before > 0 {
            cr_sum_after / cr_sum_before
        } else {
            1.0 // no knowledge to lose
        };

        self.current_shell = Some(new_shell);
        Ok(transfer_cr)
    }

    pub fn knowledge_conservation_ratio(&self) -> f64 {
        if self.knowledge.is_empty() {
            return 1.0;
        }
        let total: f64 = self.knowledge.iter().map(|t| t.cr).sum();
        total / self.knowledge.len() as f64
    }

    pub fn shell_utilization(&self) -> f64 {
        match &self.current_shell {
            Some(shell) => {
                if shell.capacity == 0 {
                    return 0.0;
                }
                shell.rooms.len() as f64 / shell.capacity as f64
            }
            None => 0.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_shell(name: &str, capacity: usize) -> Shell {
        Shell {
            name: name.to_string(),
            hardware: HardwareProfile {
                name: format!("{}-hw", name),
                ram_mb: 4096,
                cores: 4,
                gpu: false,
            },
            rooms: Vec::new(),
            attachments: Vec::new(),
            capacity,
        }
    }

    fn test_tile(domain: &str, cr: f64) -> KnowledgeTile {
        KnowledgeTile {
            id: Uuid::new_v4(),
            domain: domain.to_string(),
            content: vec![1, 2, 3],
            cr,
        }
    }

    #[test]
    fn test_hatch() {
        let id = Uuid::new_v4();
        let crab = HermitCrab::hatch(id);
        assert_eq!(crab.id, id);
        assert!(crab.current_shell.is_none());
        assert!(crab.knowledge.is_empty());
        assert!(crab.shells_visited.is_empty());
    }

    #[test]
    fn test_enter_shell() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        let shell = test_shell("esp32", 1);
        crab.enter_shell(shell);
        assert!(crab.current_shell.is_some());
        assert_eq!(crab.current_shell.as_ref().unwrap().name, "esp32");
    }

    #[test]
    fn test_enter_second_shell_archives_first() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.enter_shell(test_shell("esp32", 1));
        crab.enter_shell(test_shell("jetson", 6));
        assert_eq!(crab.shells_visited.len(), 1);
        assert_eq!(crab.shells_visited[0].name, "esp32");
        assert_eq!(crab.current_shell.as_ref().unwrap().name, "jetson");
    }

    #[test]
    fn test_grow_attachment() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.enter_shell(test_shell("jetson", 6));
        crab.grow_attachment("camera", "usb").unwrap();
        let shell = crab.current_shell.as_ref().unwrap();
        assert_eq!(shell.attachments.len(), 1);
        assert_eq!(shell.attachments[0].kind, "camera");
        assert!(shell.attachments[0].active);
    }

    #[test]
    fn test_grow_attachment_no_shell() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        assert!(crab.grow_attachment("sensor", "i2c").is_err());
    }

    #[test]
    fn test_add_room() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.enter_shell(test_shell("jetson", 6));
        crab.add_room(Room { name: "bridge".into(), sensors: 2 }).unwrap();
        assert_eq!(crab.current_shell.as_ref().unwrap().rooms.len(), 1);
    }

    #[test]
    fn test_add_room_at_capacity() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.enter_shell(test_shell("tiny", 1));
        crab.add_room(Room { name: "a".into(), sensors: 0 }).unwrap();
        let result = crab.add_room(Room { name: "b".into(), sensors: 0 });
        assert!(result.is_err());
    }

    #[test]
    fn test_migrate_to() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.knowledge.push(test_tile("nav", 1.0));
        crab.enter_shell(test_shell("esp32", 1));
        let cr = crab.migrate_to(test_shell("jetson", 6)).unwrap();
        assert!(cr < 1.0); // knowledge decayed
        assert_eq!(crab.current_shell.as_ref().unwrap().name, "jetson");
        assert_eq!(crab.shells_visited.len(), 1);
    }

    #[test]
    fn test_migrate_preserves_knowledge() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.knowledge.push(test_tile("nav", 1.0));
        crab.knowledge.push(test_tile("mapping", 0.8));
        crab.enter_shell(test_shell("a", 2));
        let cr = crab.migrate_to(test_shell("b", 4)).unwrap();
        // CR should reflect 10% decay per tile
        assert!(cr > 0.0 && cr < 1.0);
        // Knowledge still present
        assert_eq!(crab.knowledge.len(), 2);
    }

    #[test]
    fn test_knowledge_conservation_ratio() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        assert_eq!(crab.knowledge_conservation_ratio(), 1.0); // no knowledge = perfect
        crab.knowledge.push(test_tile("a", 0.9));
        crab.knowledge.push(test_tile("b", 0.7));
        let cr = crab.knowledge_conservation_ratio();
        assert!((cr - 0.8).abs() < 0.01);
    }

    #[test]
    fn test_shell_utilization() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        assert_eq!(crab.shell_utilization(), 0.0); // no shell
        crab.enter_shell(test_shell("test", 4));
        assert_eq!(crab.shell_utilization(), 0.0); // empty shell
        crab.add_room(Room { name: "a".into(), sensors: 0 }).unwrap();
        assert!((crab.shell_utilization() - 0.25).abs() < f64::EPSILON);
    }

    #[test]
    fn test_shell_utilization_full() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.enter_shell(test_shell("tiny", 2));
        crab.add_room(Room { name: "a".into(), sensors: 0 }).unwrap();
        crab.add_room(Room { name: "b".into(), sensors: 0 }).unwrap();
        assert!((crab.shell_utilization() - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_knowledge_decay_across_shells() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.knowledge.push(test_tile("core", 1.0));
        crab.enter_shell(test_shell("s1", 1)); // 5% decay on enter
        crab.migrate_to(test_shell("s2", 2)).unwrap(); // 10% decay on migrate
        let cr = crab.knowledge[0].cr;
        // 1.0 * 0.95 * 0.9 = 0.855
        assert!((cr - 0.855).abs() < 0.01);
    }

    #[test]
    fn test_serialization() {
        let mut crab = HermitCrab::hatch(Uuid::new_v4());
        crab.enter_shell(test_shell("test", 4));
        let json = serde_json::to_string(&crab).unwrap();
        let back: HermitCrab = serde_json::from_str(&json).unwrap();
        assert_eq!(crab.id, back.id);
    }
}
