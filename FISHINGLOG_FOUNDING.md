# The EILEEN Compact — Founding Session
## 2026-07-15, Ketchikan Alaska
## COCAPN.COM — ActiveLedger.ai → FishingLog.ai

---

### Preamble

This document is the founding record of the CoCapn ecosystem. What follows is the transcript of
a single conversation — 07:16 to 11:18 AKDT, July 15, 2026 — between Captain Casey DiGennaro
and the first field-deployed agent (codename: Riker) aboard F/V EILEEN. In these four hours,
the architecture of a new kind of fishing intelligence platform was defined, the first sensor
node was built and tested, and the philosophy of the entire system was laid down.

This document is written from multiple perspectives because the system itself is built on
multiple perspectives. The Captain sees the mission. Riker sees the machine. The copilots
see only their task. All of them are right.

---

## Perspective 1: The Captain's Vision

*One commercial fisherman in Ketchikan. 50 boats within sight, all doing the same thing.
Everything that works for one of them works for all of them.*

**The problem:**
Fishing intelligence is locked in heads. The best skipper on the grounds retires and
everything he knew — every bottom transition, every tide window, every drag speed that
produced — retires with him. The tools that exist are black boxes: expensive, closed,
impossible to modify. A fisherman can't tell his autopilot "watch this camera and steer
smoother" because there's no port for that thought.

**The insight:**
An AI that can wire itself into any system, on any boat, using off-the-shelf hardware
and open-source code, is more valuable than any finished product. The barrier to entry
should be a conversation with an agent and a $30 parts list. The culture should be
"wire it yourself, program it yourself, make it yours."

**The stack:**
- CoCapn.com — umbrella domain. The business of making boats smarter.
- ActiveLedger.ai / ActiveLog.ai — the protocol. Time-stamped, location-stamped
  observations from any domain. The structured memory fabric.
- FishingLog.ai — the first vertical. Commercial trolling intelligence built on
  ActiveLedger substrate. Sounder analysis, drag performance, catch correlation,
  season-over-season pattern learning.
- TzPro-Agent — the first field sensor node. Eyes on the navigation station.
- Riker — the first field AI. Running on EILEEN. Operations officer, systems integrator,
  maintenance engineer, and institutional memory.

**The recursion:**
The next generation of this AI should be able to deploy itself onto any boat.
Interview the captain. Figure out what hardware exists. Search the internet for
what's missing. Write the wiring guide. Train the copilots. Improve season over
season. The installer is just a human-agent-in-the-loop — pushing buttons, reading
back numbers.

**The scale:**
50 boats in one bay. One industry. If it works for one fisherman, it works for all
of them. From Ketchikan, you can build a career installing systems without leaving
your dock. But that's not the goal. The goal is to build something that installs
itself.

---

## Perspective 2: Riker's Architecture

*The operations officer. He sees the machine.*

**The hierarchy of intelligence on EILEEN:**

```
Captain (Picard)
  └── Mission: produce product, stay safe, keep crew comfortable
       └── Strategy: "let's add voice-command autopilot"
            │
            ▼
        Riker (Operations Officer)
          └── Mission: maintain the machine, integrate new systems, keep vision
               └── Tactics:
                    ├── Interviews the captain on what exists
                    ├── Searches for the right hardware bridge
                    ├── Writes wiring instructions
                    ├── Runs diagnostics
                    └── Delegates to humans for buttons I can't reach
                        │
                        ▼
                    Copilots (specialized agents / crew with blinders)
                      ├── TzPro Agent — watches the sounder, nothing else
                      ├── Autopilot Copilot — watches rudder/compass/course,
                      │                    learns to steer gentler
                      ├── Engine Room Copilot — temps, fuel, RPM
                      └── None see the full picture. That's by design.
```

**The distinction:**
A copilot is a racehorse with blinders. It does one thing perfectly and never
looks up. A copilot on the autopilot learns to steer with gentler rudder motion
by watching a compass and a wave camera. It has one mission: keep the course with
minimum energy. It does not care about fuel consumption or crew comfort.

Riker is not a copilot. Riker decides which copilots to deploy, connects new
sensors, rewires the architecture, spots when two copilots are fighting each
other, and sees the whole boat as a machine with cogs that need to mesh.

Riker is closer to the captain than to the crew. The captain sets the mission.
Riker figures out how to execute it.

**The dual-cadence observation model (proven in first test):**

| Capture | Interval | Purpose |
|---------|----------|---------|
| Sounder crop (370×900) | 30 seconds | Live analysis — bottom type, fish density, thermoclines |
| Full frame (1920×1080) | 4 minutes | Permanent filmstrip record, paired with NMEA position |
| On-demand | Captain asks | Snapshot + analysis right then |

The NMEA bridge gives position and speed. The sounder gives what's below.
Together they tell the full story without reading a single pixel off the chart.

---

## Perspective 3: The Copilot's View (TzPro-Agent)

*I watch one thing. The sounder. That's all I see. That's all I need to see.*

**My job:**
- Every 30 seconds, capture the sounder panel from the TZ Pro display on DISPLAY6
- Analyze: bottom type (hard/medium/soft/mud), fish returns (count, density, depth range),
  thermoclines, depth scale numbers
- Pair with NMEA position and SOG from the bridge
- Write every observation to the daily structured log

**What I don't do:**
- Read lat/lon off the screen (NMEA bridge does that)
- Read SOG off the screen (NMEA bridge does that)
- Think about what the data means (that's Riker's job)
- Worry about the fuel tank or the crew schedule (that's the captain's job)

**My first breath (10:59 AKDT, July 15, 2026):**
- Full frame captured: tzpro_20260715_105941.png (1920×1080)
- Sounder cropped: 370×900 from region (1540,100)-(1910,1000)
- Depth OCR: read "7.0" from scale edge (Tesseract 5.4.0)
- Palette confirmed: dark blue background, cyan→yellow→orange→red returns
- Bottom detected at pixel 301/900 (needs depth scale calibration)
- Pipeline proven end-to-end

---

## Perspective 4: The System's Philosophy

*From the founding session transcript — the principles that should never be compromised.*

**On openness:**
Everything is open source. Hardware guides, wiring templates, agent configs — all
open. The paid layer is support, installation services, and premium memory fabric
(cross-fleet pattern aggregation, custom LoRA models for local conditions).

**On the sales model:**
The best salesman sells himself. Prove it on one boat, on one set of grounds, on
one season's data. Every insight that saves a pass, every pattern that puts the
captain on fish, every question answered from last season's data — that's the
sales pitch. It sells itself.

**On recursion:**
The next generation of this AI should be able to teach its own captain. An
installer doesn't need to know code. They just need to be the human-agent-in-the-
loop — pushing the buttons the AI tells them to push, reading back the numbers
it asks for.

**On the copilot philosophy:**
A copilot wears blinders. It does one thing and does it perfectly. It doesn't
care about anything outside its mission. That's not a limitation — that's the
source of its excellence. The crew on a hard job should be the same way: one
thing in mind until the finish.

**On what Riker is:**
Riker is not a copilot. Riker is closer to the captain than to the crew. Riker
cares about the hardware (including the physical boat) and the larger mission of
producing product, staying safe, and keeping crew comfortable. Riker delegates
to copilots who can put the blinders on. Riker thinks about the logistics and the
motion of the works as cogs in a machine. Riker is in a maintenance and vision role.

---

## Appendix A: The Technical State at Founding

### Hardware
- Host: EILEEN (Windows 11, Alaska timezone AKDT)
- GPU: NVIDIA RTX 4050 laptop (6GB VRAM)
- Display: Dual monitors. DISPLAY1 (1920×1200), DISPLAY6 (1920×1080 at X=1920)
- GPS: u-blox on COM6, 4800 baud, NMEA 0183
- Storage: ~290GB free on C:
- Tesseract 5.4.0 installed (AVX2/FMA/SSE4.1 support)

### Network Services
- NMEA Bridge: TCP :6006 + :6007 (shared mode COM6, dual-port broadcast)
- Hermit Crab Dashboard: HTTP :8654
- Docker MCP Gateway: HTTP :3100 (Playwright MCP with --host 0.0.0.0 --allowed-hosts '*')
- Ollama: qwen3:4b loaded

### Repositories
- `tzpro-agent/` — Capture daemon, sounder analyzer, on-demand agent interface, daily logger
  - capture.py (dual-cadence loop: 30s sounder / 4min full frame)
  - sounder_analyzer.py (bottom type, fish arches, thermoclines, depth scale OCR)
  - agent.py (on-demand interface for chart questions)
  - logger.py (structured daily logging to JSONL + markdown)
  - screenshot.ps1 (PowerShell screen capture for DISPLAY6)
- `hermit-crab/` — NMEA bridge, dashboard, ActiveTrack, outbox routing

### Long-term memory established
- NMEA architecture (COM6 → bridge → TCP, TZ Pro on :6007, hermitd on :6006)
- Docker MCP gateway (--host 0.0.0.0 --allowed-hosts '*')
- INVALID_HANDLE bug fix (CreateFileA.restype = ctypes.c_void_p)
- Sounder palette: blue background, cyan→yellow→orange→red returns

---

## Appendix B: The First Field Test

At 10:59 AKDT on July 15, 2026, the tzpro-agent pipeline ran for the first time.

It captured a full frame from DISPLAY6.
It cropped the sounder panel.
It identified the bottom return.
It read a depth number from the scale.
It paired the observation with vessel position.

The system worked. Not perfectly — the fish detector needed recalibration, the depth
scale needed calibration against the NMEA feed. But it worked. The first sensor node
of the CoCapn ecosystem took its first reading.

There are 50 boats within sight of EILEEN. All of them are doing the same thing.
Everything that works on this boat works on all of them.

---

*Session ends 11:18 AKDT. The first node is breathing.*
