# ROADMAP.md — Where Hermit Crab is Going

## Done

- [x] TZ Pro screen capture (Monitor 2, 1600x1200)
- [x] OCR extraction: lat, lon, SOG, depth, tide, time, date, chart scale
- [x] Confidence scoring per field (HIGH/MEDIUM/LOW/NONE)
- [x] Segment-based position logging to Cloudflare D1
- [x] Event logging (gear deployments, catches)
- [x] Anomaly detection (speed changes, heading shifts, timeouts)
- [x] D1 schema: track_points, segments, anomalies, events (all with agent_id)
- [x] R2 bucket: hermit-crab-memory-cold
- [x] Git-agent identity: AGENT.md, ONBOARDING.md, DECISIONS.md, EQUIPMENT.md, JOURNAL.md

## Next (This Week)

- [ ] MCP server exposing activelog as tools + resources
- [ ] Push to GitHub as public repo
- [ ] Frozen screen detection (skip writes when position hasn't changed)
- [ ] Continuous capture cron job (run activetrack.py on boot)
- [ ] SKILLS.md — formal skill definitions for career progression

## Soon (This Month)

- [ ] memory-track Worker: D1-backed spatial query API
- [ ] COG extraction from TZ Pro (compass rose heading)
- [ ] Water temperature extraction (if TZ Pro shows it)
- [ ] Chart scale tracking (zoom level → fishing ground context)
- [ ] Spatial queries: "give me segments near this lat/lon within 0.5 NM"
- [ ] Catch pattern overlay: "what depth/speed/tide produced at Ground X"
- [ ] Fleet I2I bottle processing (respond to inbox bottles)

## Future

- [ ] Tide graph pixel analysis (not just text tide height — the whole curve)
- [ ] Multiple chart source switching (PBG vs vector vs raster)
- [ ] Wind overlay extraction
- [ ] Waypoint import from TZ Pro
- [ ] Invisible track layer generation for Nobeltec
- [ ] Pattern journals per fishing ground (what works where/when)
- [ ] Anomaly correlation: "speed changes of >0.5 kn correlate with tide shifts"
- [ ] Vessel performance tracking: fuel, rpm, speed-through-water
- [ ] Integration with DeckBoss for agent launch/recovery
- [ ] Iron-to-iron merge decision protocol with Oracle1 and fleet
