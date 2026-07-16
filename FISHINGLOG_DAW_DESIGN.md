# FishingLog.ai — The DAW Dashboard
## Product Design Specification v0.1

> *"Every data stream is a track. The timeline is the one true axis."*
>
> A web-based fishing intelligence dashboard that looks and feels like
> Ableton Live meets a marine chartplotter. Built on the ActiveLedger
> observation fabric. First deployed aboard F/V EILEEN, Ketchikan AK.
>
> **Author:** Design session, 2026-07-15
> **Status:** Vision document — nothing built yet

---

## Table of Contents

1. [The Metaphor](#1-the-metaphor)
2. [Track Layout](#2-track-layout)
3. [Timeline Interaction](#3-timeline-interaction)
4. [The Echogram Track](#4-the-echogram-track)
5. [Bite & Catch Events as MIDI](#5-bite--catch-events-as-midi)
6. [Conversation Transcript](#6-conversation-transcript)
7. [Pattern Markers](#7-pattern-markers)
8. [Five-Dimensional Navigation](#8-five-dimensional-navigation)
9. [The Data Model](#9-the-data-model)
10. [The Rendering Engine](#10-the-rendering-engine)
11. [The Interaction Model](#11-the-interaction-model)
12. [The Three Audiences](#12-the-three-audiences)

---

## 1. The Metaphor

### Why a DAW?

Ableton Live is the most intuitive timeline interface ever built. Musicians —
people who have never written a line of code — arrange complex multi-track
compositions across time. They zoom from sample-level detail (milliseconds)
to full arrangement view (hours). They drop markers, loop regions, solo/mute
tracks. They understand that every track is independent but the timeline binds
them all.

A fishing day is a multi-track recording session:

| DAW Concept | Fishing Equivalent |
|-------------|-------------------|
| Audio track | Sensor stream (sounder, rudder, SOG) |
| MIDI track | Bite events, catch log entries |
| Session clip | A drag through productive water |
| Loop region | "Let's re-fish that pass" |
| Marker | "The chum school was right here" |
| Mixer solo/mute | "Show me just the sounder and bites" |
| Arrangement view | The full day, left to right |
| Sample editor | Zoom into a single 30s sounder ping |
| Warp marker | Tide correction — align by state of tide, not clock time |

### The Core Experience

You open the dashboard and you see **time**. Not a table of numbers, not a
chart of isolated variables. You see the day as it happened — every sensor
stream laid out in parallel, the playhead sweeping across like a record needle.
You can hear it in your head: the engine RPM rising as you come on step, the
sounder lighting up as you cross the ledge, the bite that came two minutes
later exactly where you expected it.

This is not a dashboard. This is a **recording studio for the ocean**.

---

## 2. Track Layout

### 2.1 Track Hierarchy

Tracks are arranged vertically in the Arrangement View, like Ableton's
horizontal track lanes. The vertical order is fixed by convention but
user-reorderable by drag:

```
┌──────────────────────────────────────────────────────────────────┐
│ TRACK HEADER (collapsed)         │  ████████████████████████████ │
├──────────────────────────────────┤───────────────────────────────┤
│ ▲ ECHOGRAM            [expanded] │ [quilted sounder tiles]       │
│   └─ Depth scale                 │                               │
│   └─ Bottom classification       │                               │
│   └─ Fish density heatmap        │                               │
├──────────────────────────────────┤───────────────────────────────┤
│ ▲ RUDDER ANGLE        [collapsed]│ ═══════╱╲══════╱╲══════════ │
├──────────────────────────────────┤───────────────────────────────┤
│ ▲ SOG ENVELOPE        [expanded] │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
│   └─ SOG (kts)                   │ ▓▓▓▓▓▓░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
│   └─ Target speed band           │          ═══════════════     │
├──────────────────────────────────┤───────────────────────────────┤
│ ▲ COMPASS              [collapsed]│ ───╱──────╲─────────────── │
├──────────────────────────────────┤───────────────────────────────┤
│ ◆ BITES (MIDI)         [expanded]│ •  •   ••  •     •    ••  • │
│   └─ Species legend              │ 🟡🟡  🟢🟢 🟡   🟢    🟡🟡 🟢│
├──────────────────────────────────┤───────────────────────────────┤
│ ◆ CATCH LOG            [expanded]│ 🐟King 22#  🐟Coho 8#  🐟King│
├──────────────────────────────────┤───────────────────────────────┤
│ 💬 CONVERSATION        [collapsed]│ the chum should be...───────▶│
├──────────────────────────────────┤───────────────────────────────┤
│ 🎥 VIDEO (optional)    [collapsed]│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└──────────────────────────────────┴───────────────────────────────┘
         TRACK HEADERS                      ARRANGEMENT AREA
         (fixed left panel)                 (horizontally scrollable)
```

### 2.2 Track States

Each track has three visual states:

**Collapsed (default for less-critical tracks):**
- 24px tall
- Shows a sparkline — a 1D miniaturization of the full data
- For rudder: a thin waveform line, no axes
- For compass: a thin colored line that shifts red→green→blue with heading
- For conversation: a scrolling 1-line ticker synced to playhead
- Hover expands to a tooltip preview
- Click the track header to expand

**Expanded (2-4 tracks at a time max):**
- Variable height (user-draggable, defaults to 120-200px)
- Full visualization with labeled axes
- Echogram: shows actual quilted tiles with depth scale
- SOG: filled area chart with target band overlay
- Bites: piano-roll view with colored note-on diamonds

**Focused (one track, full height):**
- Double-click a track header or press `F` to focus
- Track fills 70% of the viewport height
- All other tracks collapse to sparklines
- Echogram in focus mode: full-resolution tiles, interactive scrub
- Press `Esc` or click another track to exit focus

### 2.3 Track-Specific Designs

#### Rudder Angle Track

```
Expanded (160px):
                    ┌──────────────────────────────────────┐
   PORT 15° ─       │    ╱╲        ╱╲                     │
   PORT 10° ─       │   ╱  ╲      ╱  ╲    ╱╲             │
   PORT  5° ─       │  ╱    ╲    ╱    ╲  ╱  ╲            │
   CENTER  ─────────│─╱──────╲──╱──────╲╱────╲───────────│
   STBD  5° ─       │          ╲╱              ╲          │
   STBD 10° ─       │                                     │
   STBD 15° ─       │                                     │
                    └──────────────────────────────────────┘
                    ← centerline is the midline of the track

Collapsed (sparkline, 24px):
   ═══╱╲═════╱╲═══╱╲══════╱╲═══════  (oscillation visible but compact)
```

Design note: center is the visual midline. The waveform oscillates above
(port) and below (starboard). This is intuitive — it looks like the rudder
moving. Overcorrection is instantly visible as high-frequency oscillation.

#### SOG Envelope Track

```
Expanded (120px):
  6.0 kts ─  ┌─────────────────────────────────────────┐
  5.0 kts ─  │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                    │
  4.0 kts ─  │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
  3.0 kts ─  │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
  2.0 kts ─  │░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
  1.5 kts ─  │░░░░░░░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│ (trolling band)
             └─────────────────────────────────────────┘
             ░░ = outside trolling band (too fast/slow)
             ▓▓ = inside trolling band
             ── = target speed line (1.8 kts for chum)
```

The SOG envelope track shows speed as a filled area between min and max
speed for each time bucket. Color encodes whether you're in the target
trolling band. The band itself is configurable per species/target.

#### Compass Heading Track

```
Expanded (120px):
                    ┌──────────────────────────────────────┐
  N  (0°/360°) ─    │                                      │
  NW (315°)    ─    │  ╱╲                                  │
  W  (270°)    ─    │ ╱  ╲        ╱╲                      │
  SW (225°)    ─    │╱    ╲      ╱  ╲    ╱╲              │
  S  (180°)    ─    │      ╲    ╱    ╲  ╱  ╲             │
  SE (135°)    ─    │       ╲  ╱      ╲╱    ╲            │
  E  (90°)     ─    │        ╲╱              ╲           │
  NE (45°)     ─    │                                      │
                    └──────────────────────────────────────┘

                    Color gradient along the line:
                    N=red, E=yellow, S=cyan, W=blue (compass rose)
```

Unlike rudder (oscillating above/below center), compass is a continuous
360° wrapping signal. The track handles the 0°/360° wrap elegantly:
when heading crosses north, the line doesn't spike — it smoothly wraps
by extending above or below the axis bounds.

---

## 3. Timeline Interaction

### 3.1 The Fractal Scale Model

Time in fishing is not linear. It is fractal. A 30-second sounder ping
matters at the scale of a single pass. A season's worth of passes matters
at the scale of a career. The zoom control respects these natural scales.

```
┌─────────────────────────────────────────────────────────────────┐
│ ◀◀  │█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│  ▶▶    │
│     │                                                  │        │
│     │  [30s]  [5m]  [30m]  [2h]  [12h]  [1w]  [1M]  [1Y]  [3Y]│
│     │    ·      ·      █      ·      ·     ·     ·     ·     ·  │
│     │                                                  │        │
│ ◀◀  │  scale: 2 hours (drag to zoom)                  │  ▶▶    │
└─────────────────────────────────────────────────────────────────┘
```

#### Scale Presets (Snap Points)

| Scale | Label | What You See | Echogram Rendering |
|-------|-------|-------------|-------------------|
| 30s | "Ping" | Individual sounder frames | 1-2 full tiles |
| 1m | "Minute" | 2-4 pings, bite context | Tiles full height |
| 5m | "Pass" | A single drag/tack | Tiles at 60% height |
| 30m | "Area" | 6 passes through a spot | Tiles at 25%, 6-10 visible |
| 2h | "Opening" | Morning or afternoon session | Tiles at 12%, semi-transparent |
| 12h | "Day" | Full fishing day | Tiles at 4%, blended avg color |
| 1w | "Trip" | 7 days stacked | Tiles invisible, heatmap only |
| 1M | "Month" | Season segment | Heatmap + pattern markers |
| 6M | "Season" | Full season (Jun-Sep) | Compressed to 1-bar width |
| 3Y | "Career" | Multi-season comparison | Season-stripe comparison view |

#### The Slider Behavior

The slider is NOT a continuous linear zoom. It is a **detented fractal slider**:

1. **Snap zones**: As you drag, the slider magnetically snaps to the preset scales
2. **Between snaps**: A subtle haptic/numeric readout shows you're "between 5 minutes
   and 30 minutes"
3. **Visual feedback**: As you approach a scale boundary, the view begins to
   transition — echogram tiles start to shrink, labels fade, sparklines compress
4. **Keyboard shortcuts**: `1`-`0` jump directly to scale presets
5. **Scroll wheel**: `Ctrl+Scroll` zooms with momentum and snap

#### "Zooming Out Until an Entire Season Is One Bar"

This is the most radical design decision in the dashboard.

When you zoom out to the 6-month (Season) scale, the entire June-September
fishing season compresses into a single screen-width bar. What does it look like?

```
┌──────────────────────────────────────────────────────────────────┐
│ JUNE              JULY              AUGUST           SEPTEMBER   │
│ ▓▓▓▓▓▓░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓░▓▓▓▓▓▓▓▓▓▓▓░░░│
│ low fish  ████████████████████  low  ██████████████████████  low│
│                                                         │       │
│                    █ = productive days (catches)                  │
│                    ░ = unproductive days (no catches)             │
│                    · = no data (boat not fishing)                 │
│                                                                   │
│  Click any day to zoom to 12h view of that day.                  │
│  Shift+click to compare two days side by side.                   │
└──────────────────────────────────────────────────────────────────┘
```

At the 3-year (Career) scale, you see three season-stripes stacked vertically:

```
┌──────────────────────────────────────────────────────────────────┐
│ 2026 │▓▓▓▓░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓░░░░░░│
│ 2027 │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│ 2028 │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│      └──────────────┬──────────────┘                            │
│              July 15 — same date, three years                    │
│              Vertical alignment by calendar date                 │
└──────────────────────────────────────────────────────────────────┘
```

This is where the institutional knowledge lives. You can see, at a glance,
that July 2027 was a better season than 2026. You can see that early June
is consistently slow. You can align by calendar date OR by tide phase
(the "warp marker" concept — see §8).

### 3.2 Playhead

The playhead is a vertical red line spanning all tracks:

```
│                                                          │
│  ═══════════════╪══════════════════════════════════════  │  ← SOG track
│                 │                                        │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  ← Echogram
│                 │                                        │
│  ═══════╱╲══════│══╱╲══════════════════════════════════  │  ← Rudder
│                 │                                        │
│         •   •   │ ••    •       •     ••   •            │  ← Bites
│                 │                                        │
│                 ▼                                        │
│            PLAYHEAD (red, 2px, full-height)              │
│            Timestamp: 14:32:15 AKDT                      │
│            Lat: 55.785°N  Lon: -131.527°W               │
│            SOG: 1.8 kts  COG: 265°                       │
```

The playhead shows a floating tooltip at its top edge with:
- Timestamp
- Position (lat/lon)
- Current SOG and COG
- Depth under keel (from the echogram at this timestamp)

### 3.3 Playback Controls

Borrowed directly from DAW transport:

```
┌────────────────────────────────────────────────────────┐
│  ⏮   ⏪   ▶   ⏸   ⏩   ⏭    🔴   🔁  │ 1x  │ 14:32:15 │
│ prev  rew play pause ffwd next  rec loop speed timestamp│
│ mark                            arm                     │
└────────────────────────────────────────────────────────┘
```

- **Play/Pause**: Animates the playhead moving across time at 1×-64× speed
- **Record Arm**: When armed, new data streams in live. The view auto-scrolls
  to keep the playhead at the right third of the screen (like a DAW recording)
- **Loop**: Click-drag in the timeline ruler to set loop points. The playhead
  jumps back to loop start on reaching loop end. This is "re-fishing a pass"
  visually.
- **Speed**: 1/2×, 1×, 2×, 4×, 8×, 16×, 32×, 64× — for scrubbing through
  a day in seconds

---

## 4. The Echogram Track

### 4.1 The Tile Quilt

This is the hardest rendering problem in the dashboard, and the most
visually distinctive.

**The input:** 370×900px sounder crops captured every 30 seconds. Each crop
shows the water column from surface to bottom with acoustic returns rendered
in the TZ Pro palette (dark blue background → cyan → yellow → orange → red).

**The output:** A continuous, horizontally-scrolling echogram that looks like
the sounder was recording continuously — even though it's stitched from
discrete 30-second tiles.

#### Stitching Algorithm (Conceptual)

```
Tile 1 (14:32:00-14:32:30)        Tile 2 (14:32:30-14:33:00)
┌─────────────────────┐            ┌─────────────────────┐
│  ░░░░░░░░░░░░░░░░░  │  surface   │  ░░░░░░░░░░░░░░░░░  │
│  ░░░░▓▓░░░░░░░░░░░  │            │  ░░░░░░▓▓▓░░░░░░░░  │
│  ░░░░▓▓▓▓░░░░░░░░░  │            │  ░░░░░▓▓▓▓▓░░░░░░░  │
│  ░░░░░░▓▓░░░░░░░░░  │            │  ░░░░░░░▓▓░░░░░░░░  │
│  ░░░░░░░░░░▓▓░░░░░  │  fish      │  ░░░░░░░░░░░▓▓▓░░░  │
│  ░░░░░░░░░░▓▓░░░░░  │  marks     │  ░░░░░░░░░░░░░░░░░  │
│  ░░░░░░░░░░░░░░░░░  │            │  ░░░░░░░░░░░░░░░░░  │
│  ██████████████████  │  bottom    │  ██████████████████  │
└─────────────────────┘            └─────────────────────┘
         │         blended overlap zone          │
         └────────── 5px blend ─────────────────┘
```

Each tile is rendered at a width proportional to its time span (30s) at the
current zoom level. Adjacent tiles overlap by 5px of blended alpha to hide
the seam. The bottom contour should appear continuous — if tile 1 ends at
pixel 750/900 and tile 2 starts at pixel 748/900, that's a 2px jump that
looks natural (the bottom did change slightly).

If there's a gap in captures (the agent was paused, the boat was off),
the gap is rendered as a subtle diagonal-stripe pattern with a label:
`[ 4min gap — agent paused ]`. Clicking the gap triggers a backfill
request to the agent.

### 4.2 Metadata Overlays

Each tile carries metadata rendered as semi-transparent overlays that
appear/hide based on zoom level:

**At 30s-5m scale (individual tiles visible):**
```
┌─────────────────────┐
│  ░░░░░░░░░░░░░░░░░  │
│  ░░░░▓▓░░░░░░░░░░░  │  ← fish density indicator dots
│  ░░░░▓▓▓▓░░░░░░░░░  │
│  ░░░░░░▓▓░░░░░░░░░  │
│  ═══════════════ 22f│  ← depth scale on right edge
│  ░░░░░░░░░░▓▓░░░░░  │
│  ░░░░░░░░░░▓▓░░░░░  │
│  ░░░░░░░░░░░░░░░░░  │
│  ██████████████████  │
│  HARD BOTTOM  82%   │  ← bottom classification badge
└─────────────────────┘
```

Overlay elements (all semi-transparent, non-destructive to the tile image):

| Element | Position | Style | Shows |
|---------|----------|-------|-------|
| Depth scale | Right edge, vertical | White text on transparent bg | Depth in fathoms at scale markings |
| Bottom line | Bottom contour | 1px bright cyan line | Traced bottom for clarity |
| Bottom type badge | Bottom-left of tile | Rounded pill: 🟤Mud 🟠Soft 🟡Med 🔴Hard | ML classification result + confidence % |
| Fish density | Overlaid on water column | Small colored dots (heat scale) | Individual returns as dots, density as color |
| Thermocline | Horizontal dashed line | Cyan dashes @ detected depth | Temperature layer boundary |
| Tile timestamp | Top-left corner | Subtle white monospace | `14:32:00` |
| Recording indicator | Top-right corner | Red dot (if capture was live) | Distinguishes live vs backfilled tiles |

**At 5m-30m scale (tiles shrinking):**
- Depth scale fades out (too small to read)
- Bottom type badges collapse to colored dots on the bottom contour
- Fish density becomes a continuous heatmap strip above the bottom
- Timestamps appear every 5th tile only

**At 2h+ scale (tiles invisible):**
- Echogram becomes a pure heatmap: bottom contour as a line, fish density
  as a colored band
- Bottom type shown as a colored stripe along the bottom contour
- Pattern markers (see §7) become the primary visual element

### 4.3 Scrubbing Through Time

There are three ways to scrub through the echogram:

**1. Drag the playhead** — standard DAW behavior. Click and drag the
red playhead line. The echogram tiles update as you drag.

**2. Click in the echogram track** — clicking directly on a tile jumps
the playhead to that timestamp. Clicking on a fish return dot zooms to
that 30s tile in focus mode.

**3. Arrow-key nudge** — left/right arrows move the playhead by one tile
(30s). Shift+arrows move by one screen-width. This is for fine-grained
inspection: nudge, look at the tile, nudge, look at the tile.

**4. Scroll-wheel scrub** — when hovering over the echogram track, the
scroll wheel (without Ctrl) scrubs the playhead horizontally. This is the
fastest way to skim through a day: just scroll and watch the bottom
contour rise and fall.

---

## 5. Bite & Catch Events as MIDI

### 5.1 The Piano Roll for Fishing

In a DAW, the piano roll shows MIDI notes:
- Vertical axis = pitch (which note)
- Horizontal axis = time
- Note length = duration
- Note color = MIDI channel
- Velocity = how hard the note was struck (opacity/size)

In FishingLog, the bite track is a piano roll:

```
┌──────────────────────────────────────────────────────────────────┐
│ BITE TRACK (MIDI Piano Roll)                                     │
│                                                                   │
│ King ─  │      ◇              ◇       ◇◇      ◇                │
│ (Ch1)   │     (22#)          (18#)   (15#)(24#)                 │
│         │                                                        │
│ Coho ─  │  ◇     ◇◇      ◇          ◇            ◇    ◇◇     │
│ (Ch2)   │ (8#)  (7#)(9#)  (6#)      (8#)         (7#) (8#)(9#) │
│         │                                                        │
│ Chum ─  │            ◇◇◇◇◇◇◇◇◇◇◇◇◇◇◇◇◇◇◇                │
│ (Ch3)   │           (7#)(8#)(7#)(9#)(8#)(10#)(7#)              │
│         │                                                        │
│ Pink ─  │                                              ◇        │
│ (Ch4)   │                                             (5#)      │
│         │                                                        │
│ Bite ─  │  ·  ··   · ·  ·    ··    ·   ·  · ···  ·    ·  ··   │
│ (noID)  │  ·  ··   · ·  ·    ··    ·   ·  · ···  ·    ·  ··   │
│         │                                                        │
│         ├────────────────────────────────────────────────────────│
│         │  08:00    09:00    10:00    11:00    12:00    13:00   │
└──────────────────────────────────────────────────────────────────┘

◇ = catch (confirmed, logged)
· = bite (strike detected, not landed)
```

### 5.2 MIDI Channel → Species

Each salmon species is assigned a MIDI channel (1-16), which maps to a color:

| MIDI Ch | Species | Color | Hex |
|---------|---------|-------|-----|
| 1 | King/Chinook | Royal gold | `#FFD700` |
| 2 | Coho/Silver | Bright silver | `#C0C0C0` |
| 3 | Chum/Dog | Olive green | `#6B8E23` |
| 4 | Pink/Humpy | Rose pink | `#FF69B4` |
| 5 | Sockeye/Red | Deep red | `#DC143C` |
| 6 | Halibut | Brown | `#8B4513` |
| 7 | Lingcod | Steel blue | `#4682B4` |
| 8 | Rockfish | Orange | `#FF8C00` |
| 9+ | Other/Unknown | Gray | `#808080` |

### 5.3 Velocity → Fish Size

In MIDI, velocity ranges from 0-127. In FishingLog:

```
Velocity = map(fish_weight_lbs, 0, 60, 1, 127)
```

A 30-pound king is velocity 64 (mid). A 60-pound king is velocity 127 (max).
A 5-pound pink is velocity 11 (faint).

**Visual encoding of velocity:**
- Diamond size: proportional to weight (8px for 5# → 32px for 60#)
- Diamond opacity: proportional to weight (40% for small → 100% for large)
- Diamond glow: a subtle radial gradient behind large fish, like a
  "reverb tail" on a loud note

### 5.4 What MIDI Visualization Communicates That a Table Never Could

A table says:
```
14:32 King 22#   14:45 Coho 8#   14:58 King 18#   15:02 Coho 7#
15:12 King 15#   15:13 King 24#   15:30 Coho 9#   16:05 King 22#
```

The MIDI piano roll shows — instantly, in one glance — that:

1. **Clustering**: Those two kings at 15:12 and 15:13 are a double. The
   captain can see they were on a school.

2. **Rhythm**: The coho are coming in a steady pulse every 12-15 minutes.
   The kings are clustered in bursts. Different species, different rhythm.

3. **Gaps**: There's a dead zone from 15:30 to 16:05. Did the boat change
   course? Did the tide change? Cross-reference with the rudder and compass
   tracks.

4. **Density patterns**: Zoom out to the month view. The coho channel is a
   tight, steady band. The king channel has intense clusters separated by
   long silences. This is the difference between a consistent coho fishery
   and a boom-or-bust king fishery — visible as a musical score.

5. **The "chum wall"**: When chum are running, the chum channel (olive green)
   becomes a solid wall of diamonds. It looks like a wall of sound. It feels
   different to look at than scattered coho diamonds. Your brain processes
   it as a different texture.

6. **Seasonal arcs**: At the 6-month scale, you see the king run as a
   crescendo-decrescendo arc in the gold channel. The coho run is a later,
   sharper arc in the silver channel. It looks like a symphonic score —
   different instruments entering and leaving across the season.

### 5.5 Catch Log Track (Companion to Bites)

Below the bite piano roll, the catch log track shows text entries:

```
┌──────────────────────────────────────────────────────────────────┐
│ 🐟 King 22#  │ 🐟 Coho 8# │  🐟 King 18#  │  🐟 King 15#      │
│ 14:32 55.785 │ 14:45      │  14:58        │  🐟 King 24#      │
│ -131.527     │ 55.788     │  55.782       │  15:12-15:13      │
│ 1.8kts 265°  │ -131.525   │  -131.530     │  double!          │
│ hard bottom  │ 1.7kts     │  1.9kts       │                    │
│ 22fm         │ soft bot   │  hard bot     │                    │
└──────────────────────────────────────────────────────────────────┘
```

Each catch entry is a card pinned to the timeline at its timestamp. The card
shows species emoji, weight, time, position, SOG, bottom type, and depth.
Cards can be expanded (click) to show full metadata. Cards can be filtered
by species (click the species name in the legend to solo that channel,
just like soloing a MIDI track).

---

## 6. Conversation Transcript

### 6.1 The Ticker Tape

The conversation track renders transcribed speech as a scrolling ticker
tape synced to the playhead. This is inspired by news tickers and
subtitles — text that flows with time.

```
┌──────────────────────────────────────────────────────────────────┐
│ CONVERSATION                                                      │
│                                                                   │
│       "yeah I see the ledge │"let's drag along it for a bit"│    │
│  ───────coming up on the────▶─────────────────────────────────   │
│       port side" │"copy      │                                  │
│                  │that"      │                                   │
│                                                                   │
│  ◀─────────────── playhead sweeps ─────────────────────────────▶ │
│                                                                   │
│  Collapsed view (24px):                                           │
│  "yeah I see the ledge coming up on the port side" "copy that"──▶│
└──────────────────────────────────────────────────────────────────┘
```

**In expanded mode:** The ticker shows the current utterance at the playhead
position, with surrounding context fading in from the left and out to the
right. Each utterance is a speech bubble pinned to its timestamp.

**In collapsed mode:** A single line of scrolling text synced to playhead.

### 6.2 Voice Attribution

Different speakers get different colors (derived from the audio source):

```
Captain:  ██ "drag along the ledge"         (blue)
Crew:     ██ "copy that"                    (green)
Radio:    ██ "EILEEN this is MARY ANN"      (orange)
Riker:    ██ "bottom transition detected"   (purple, italic)
```

### 6.3 Search Visualization

When you search for "chum" across all sessions:

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔍 "chum" — 47 results across 12 sessions                         │
│                                                                   │
│  2026-07-15 ─────────────────────────────────────────────────────│
│  │  ··········██······███·····················██······  │
│  │                                                        │
│  2026-07-16 ─────────────────────────────────────────────│
│  │  ······██···███████·············███········  │
│  │                                                        │
│  2026-07-18 ─────────────────────────────────────────────│
│  │  ···········███···█████████████···██········  │
│  │                                                        │
│  ██ = utterance contains "chum"                             │
│  ·· = utterance does not contain "chum"                    │
│                                                                   │
│  Click any ██ to jump to that moment in the conversation track.  │
└──────────────────────────────────────────────────────────────────┘
```

The search results are displayed as a **heatmap strip** above the conversation
track, showing where in time the search term appears. Each session gets its
own row. The density of matches is immediately visible — July 18 was clearly
the big chum conversation day.

Clicking a match block:
1. Jumps the timeline to that session and timestamp
2. Expands the conversation track
3. Highlights the matching utterances in yellow
4. Sets the playhead to 30 seconds before the match (context lead-in)

### 6.4 Transcript as Searchable Memory

The conversation track isn't just a playback feature. It's a search interface
into the boat's institutional memory:

- "Show me every conversation about the south ledge from July 2026"
- "When did we first discuss switching to smaller spoons?"
- "What did the radio say about the chum opener?"

Every utterance is timestamped and geotagged (the boat's position when it was
spoken). This means you can search by location: "What were we saying when we
were over the 22-fathom hump?"

---

## 7. Pattern Markers

### 7.1 The Core Idea

A pattern marker says: "This area right here looks similar to an area you
fished before, and last time it produced fish." It's the institutional
memory becoming visible.

The system compares the current echogram context (bottom contour, depth,
bottom type, fish density pattern) against every previous observation.
When it finds a high-confidence match, it places a marker.

### 7.2 Visual Design

```
┌──────────────────────────────────────────────────────────────────┐
│ PATTERN MARKERS                                                   │
│                                                                   │
│         ┌──────────────────────┐       ┌─────────────┐           │
│         │ 🟢  JUL 22 CHUM     │       │ 🟡  JUL 8    │           │
│  ───────┤  SCHOOL             ├───────┤  COHO       ├───────────│
│         │  92% similar        │       │  DRAG       │           │
│         │  bottom: med→hard   │       │  78%        │           │
│         │  depth: 18-24fm     │       │  bottom: mud│           │
│         │  density: high      │       │  depth: 12fm│           │
│         │  result: 14 chum    │       │  result: 3  │           │
│         └──────┬──────────────┘       └──────┬──────┘           │
│                │                             │                   │
│                ▼                             ▼                   │
│  ████████████████████████████████████████████████████████████   │
│  ████████████▓▓▓▓████████████████████████████████████████████   │
│  ████████████████████████████████████████████████████████████   │
│  ████████▓▓▓▓▓▓▓▓▓▓██████████████████████████████████████████   │
│  ████████████████████████████████████████▓▓▓▓▓▓██████████████   │
│                         ▲                        ▲               │
│              ECHOGRAM HEATMAP — highlighted regions              │
│              where pattern matches were detected                 │
└──────────────────────────────────────────────────────────────────┘
```

A pattern marker has:

1. **A colored bracket** spanning the matching region in the echogram track.
   The bracket sits above the echogram, like a DAW loop region marker.

2. **A label card** pinned to the bracket showing:
   - Match name (auto-generated: "JUL 22 CHUM SCHOOL" or user-named)
   - Confidence percentage
   - Matching features (bottom type, depth range, density)
   - Historical result ("result: 14 chum" — what happened last time)

3. **A highlight region** on the echogram itself — a subtle colored wash
   over the tiles that match the pattern.

### 7.3 Confidence as a Visual Element

Confidence is communicated through multiple redundant visual channels:

| Confidence | Bracket Color | Bracket Style | Card Opacity | Glow |
|------------|--------------|---------------|-------------|------|
| 90-100% | Green (`#00FF00`) | Solid thick (3px) | 100% | Strong green glow |
| 75-89% | Yellow (`#FFFF00`) | Solid thin (2px) | 90% | Subtle yellow glow |
| 50-74% | Orange (`#FF8C00`) | Dashed (2px) | 70% | None |
| 25-49% | Red (`#FF4444`) | Dotted (1px) | 50% | None |
| <25% | Not shown | — | — | — |

High-confidence matches **demand attention**. A strong green bracket with a
glow effect says "look here, this matters." Low-confidence matches are
present but unobtrusive — they don't distract but they're there if you want
to investigate.

### 7.4 User-Created Markers

The captain can also place manual markers — like DAW locators:

```
┌──────────────────────────────────────────────┐
│  ▼ SOUTH LEDGE    ▼ THE HUMP    ▼ CHUM HOLE │
│  [1]              [2]           [3]          │
└──────────────────────────────────────────────┘
```

Markers appear as numbered flags in the timeline ruler at the top of the
arrangement. Pressing `1`, `2`, `3` jumps the playhead to that marker.
Right-click a marker to name it, set its color, or add notes.

### 7.5 Pattern Comparison Mode

Shift+click on a pattern marker opens a **split comparison view**:

```
┌────────────────────────────────┬────────────────────────────────┐
│  NOW: July 15, 2026           │  THEN: July 22, 2026 (match)  │
│  14:32-14:38                  │  09:15-09:21                   │
│                                │                                │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░   │  ░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│  ░░░░▓▓░░░░░░░░▓▓░░░░░░░░░   │  ░░░░░▓▓░░░░░░░▓▓░░░░░░░░░░   │
│  ░░░░▓▓▓▓░░░░░▓▓▓░░░░░░░░░   │  ░░░░▓▓▓▓░░░░▓▓▓▓░░░░░░░░░░   │
│  ░░░░░░▓▓▓░░░▓▓▓░░░░░░░░░░   │  ░░░░░▓▓▓░░░▓▓▓░░░░░░░░░░░░   │
│  ░░░░░░░░▓▓▓▓▓░░░░░░░░░░░░   │  ░░░░░░░▓▓▓▓░░░░░░░░░░░░░░░   │
│  ██████████████████████████   │  ██████████████████████████   │
│                                │                                │
│  Bottom: med→hard, 18-24fm    │  Bottom: med→hard, 18-24fm    │
│  Density: high                │  Density: high                 │
│  SOG: 1.8kts                  │  SOG: 1.7kts                  │
│  Tide: flooding               │  Tide: flooding                │
│                                │                                │
│  RESULT: ???                  │  RESULT: 14 chum in 6 min     │
│  ─────────────────            │  ─────────────────────────    │
└────────────────────────────────┴────────────────────────────────┘
```

Side by side, the captain can see exactly how similar the two situations are.
The left side says "RESULT: ???" because we haven't fished it yet. The right
side says what happened last time. This is the fishing equivalent of "here's
what the chart looked like last time we caught fish here."

---

## 8. Five-Dimensional Navigation

### 8.1 The Five Dimensions

| Dim | Name | What It Is | How You Navigate |
|-----|------|-----------|-----------------|
| 1 | X (Time) | Left-right scroll through the timeline | Scroll wheel, drag, arrow keys |
| 2 | Y (Tracks) | Vertical scroll through track list | Scroll wheel (on track headers), drag |
| 3 | Z (Detail) | Expand/collapse/focus tracks | Click, double-click, `F` key |
| 4 | Time-as-Waveform | Playhead position, loop, markers | Transport controls, click, drag |
| 5 | Scale | Zoom from 30s to 3 years | Fractal slider, `Ctrl+Scroll`, `1`-`0` |

Dimensions 1-3 are what you see. Dimensions 4-5 are how you move through
what you see. The design challenge is making all five feel like one
continuous navigation gesture, not five separate controls.

### 8.2 The Navigation Panel

```
┌──────────────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────┐  ┌────────────────────────────┐ │
│  │ ⏮ ⏪ ▶ ⏸ ⏩ ⏭ 🔴 🔁  │  │ 1/2x 1x 2x 4x 8x 16x 32x│ │
│  │ TRANSPORT                   │  │ PLAYBACK SPEED             │ │
│  └─────────────────────────────┘  └────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ ◀◀ │█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│ ▶▶        ││
│  │    │ 30s  5m  30m  2h  12h  1w  1M  6M  1Y  3Y │           ││
│  │    │  ·    ·    █    ·    ·    ·   ·   ·   ·   · │           ││
│  │ ◀◀ │ scale: 2h                           │ ▶▶        ││
│  └──────────────────────────────────────────┴──────────┘│
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ LOOP: [14:32:00 —— 14:38:30]  │  MARKERS: ▼1 ▼2 ▼3         ││
│  │        ↺ LOOP ACTIVE          │  SEARCH: [chum...........]  ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ SESSIONS: ◀ 2026-07-15 | 2026-07-16 | 2026-07-18 ▶         ││
│  │            click to load  · = has data  ○ = no data          ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 8.3 The 4th Dimension: Time as a Waveform

The playhead is not just a cursor. It's a **performable instrument**.

**Scrubbing with feel:**
When you drag the playhead, it has momentum. Flick it and it coasts,
decelerating like a jog wheel on professional DJ equipment. You can
"throw" the playhead across a day and catch it where you want to look.

**Looping as inquiry:**
You don't just loop for playback. You loop to ask questions:
- "What was the bottom doing during this 6-minute drag?"
- "Did the SOG stay in the band for this whole pass?"
- "How many bites came in this 20-minute window?"

Setting a loop is a single click-drag in the timeline ruler. The looped
region highlights. The stats panel updates to show aggregate data for
the loop window (avg SOG, total bites, bottom type distribution).

**Jumping to markers:**
Markers are like Ableton's locators. Press `1` to jump to the South Ledge.
Press `2` for The Hump. `Shift+1` sets a loop from marker 1 to marker 2.
This is the navigation vocabulary of someone who knows their grounds:
they don't scroll through time, they jump between named places.

**Record-arm mode:**
When record is armed, the view is "live." New data streams in and the
view auto-scrolls to keep the playhead at the right third of the screen.
A thin red border appears around the entire dashboard to indicate
record mode. This is what the captain sees while fishing — the system
is writing down everything.

### 8.4 The 5th Dimension: Scale (The Fractal Zoom)

This is the dimension that makes the dashboard unique.

**The fractal slider** (see §3) is the primary control. But scale is
also navigable through:

**Pinch-to-zoom** (touch devices):
On an iPad, pinch to zoom in/out of the timeline. The snap points are
gentle — they don't fight you, but they guide you to the natural scales.

**Double-click to zoom to fit:**
Double-click a loop region to zoom the timeline to exactly fit that region.
Double-click the timeline background to zoom out one level.
Double-click a single 30s tile to zoom to the max detail level focused
on that tile.

**The overview + detail pattern:**
At the top of the arrangement area, a thin strip shows the full time range
at the coarsest scale:

```
┌──────────────────────────────────────────────────────────────────┐
│ OVERVIEW STRIP (always shows full session range)                  │
│ ░░░░██████████░░░░░░░░░░░████████████████████░░░░░░░░░████████░ │
│ 06:00   08:00   10:00   12:00   14:00   16:00   18:00   20:00   │
│                                                                   │
│ ┌── CURRENT VIEWPORT ──┐                                         │
│ │ ████████████████████ │ ← this rectangle maps to the main view  │
│ └──────────────────────┘    below. Drag it to pan. Resize edges  │
│                              to zoom.                             │
└──────────────────────────────────────────────────────────────────┘
```

The overview strip is always visible (collapsible, but on by default).
It shows the full session as a productivity heatmap (dark = fish caught,
light = no fish, striped = no data). The rectangle representing the
current viewport is draggable and resizable — it's the fastest way to
navigate at the macro level.

### 8.5 Tide-Aligned Time (The "Warp Marker" Concept)

Ableton's warp markers let you stretch audio to a grid. In FishingLog,
the warp grid is the **tide cycle**.

```
┌──────────────────────────────────────────────────────────────────┐
│ TIME MODE: [CLOCK]  [TIDE]                                       │
│                                                                   │
│ Clock mode (default):  │ 08:00  09:00  10:00  11:00  12:00      │
│                         │ ·····███████████████·············      │
│                                                                   │
│ Tide mode:              │ LOW ──── FLOOD ──── HIGH ─── EBB ──   │
│                         │ ·········██████████████████████████    │
│                         │           "all our fish came on the     │
│                         │            flood tide"                  │
└──────────────────────────────────────────────────────────────────┘
```

In tide mode, the X-axis is not clock time — it's tide state. Two fishing
days that happened at different clock times but the same tide state are
aligned. This is how you compare: "July 15 at the start of the flood"
vs "July 22 at the start of the flood."

When comparing across seasons, tide alignment reveals patterns that clock
time obscures. The chum always bite on the first hour of the flood — but
the flood happens at 6am in July and 10am in August. Clock-aligned, those
bites look like they're at different times. Tide-aligned, they're in the
same place.

---

## 9. The Data Model

### 9.1 How the Frontend Asks for Data

The frontend is a single-page web app. It queries an API that fronts the
ActiveLedger observation fabric. The API is designed around the timeline
as the primary query axis.

```
GET /api/sessions
  → List all fishing sessions (date ranges with data)

GET /api/session/{date}/tracks
  → List available tracks for this session

GET /api/session/{date}/echogram?from={iso}&to={iso}&resolution={px}
  → Returns echogram tiles for a time range at the requested resolution
  → resolution: "full" (original 370×900 tiles), "half", "quarter",
     "heatmap" (pre-computed heatmap strip for zoomed-out views)

GET /api/session/{date}/telemetry?from={iso}&to={iso}&fields=sog,rudder,compass
  → Returns time-series telemetry data as arrays of {ts, value}

GET /api/session/{date}/bites?from={iso}&to={iso}
  → Returns bite/catch events with species, weight, position, depth

GET /api/session/{date}/conversation?from={iso}&to={iso}&q={search}
  → Returns transcribed utterances with speaker, timestamp, text

GET /api/session/{date}/markers
  → Returns pattern markers and user-created markers for this session

GET /api/patterns/match?session={date}&from={iso}&to={iso}&minConfidence={0-100}
  → Returns pattern matches for the given time range against historical data

GET /api/search?q={query}&type=conversation|catch|marker|all
  → Full-text search across all sessions
```

### 9.2 Data Resolution by Zoom Level

The API returns different data depending on the zoom level. The frontend
requests the appropriate resolution:

| Zoom | Echogram | Telemetry | Bites | Conversation |
|------|----------|-----------|-------|-------------|
| 30s-5m | Full tiles (PNG) | Raw (1s intervals) | Individual events | Full text |
| 5m-2h | Half-res tiles | Downsampled (5s) | Individual events | Summarized |
| 2h-12h | Quarter-res tiles | Downsampled (30s) | Aggregated (per 5min) | Keywords only |
| 12h-1w | Heatmap strip | Downsampled (5min) | Aggregated (per hour) | Hidden |
| 1M+ | Heatmap strip | Daily stats only | Aggregated (per day) | Hidden |

The backend pre-computes downsampled views. When the frontend requests data,
it includes the current zoom level in the request so the backend returns
the right resolution. This is the "level of detail" pattern from game
rendering applied to data visualization.

### 9.3 The ActiveLedger Observation Format

Every observation is written to ActiveLedger in a unified format:

```json
{
  "ledger": "fishinglog",
  "session": "2026-07-15",
  "vessel": "EILEEN",
  "ts": "2026-07-15T22:32:00Z",
  "ts_local": "2026-07-15T14:32:00-08:00",
  "position": {
    "lat": 55.785,
    "lon": -131.527
  },
  "tide": {
    "state": "flooding",
    "height_ft": 8.2,
    "station": "ketchikan"
  },
  "type": "sounder_observation",
  "data": {
    "tile_path": "captures/2026-07-15/echogram_143200.png",
    "depth_fm": 22.5,
    "bottom_type": "hard",
    "bottom_confidence": 0.82,
    "fish_returns": {
      "count": 45,
      "density": "moderate",
      "depth_range_fm": [9, 23]
    },
    "thermocline_depth_fm": null,
    "palette": "tzpro_blue"
  }
}
```

The key insight: every observation is **timestamped and geotagged at the
point of capture**. This is what makes the timeline work — every data point
knows exactly where it belongs on the X axis.

### 9.4 The Tile Index

Echogram tiles are stored as individual image files. A SQLite (or D1) index
maps timestamps to tile paths:

```sql
CREATE TABLE echogram_tiles (
  session_date TEXT NOT NULL,
  ts TEXT NOT NULL,           -- ISO 8601
  tile_path TEXT NOT NULL,    -- relative to captures/
  depth_fm REAL,
  bottom_type TEXT,
  bottom_confidence REAL,
  fish_count INTEGER,
  fish_density TEXT,
  lat REAL,
  lon REAL,
  PRIMARY KEY (session_date, ts)
);

CREATE INDEX idx_echogram_time ON echogram_tiles(session_date, ts);
CREATE INDEX idx_echogram_position ON echogram_tiles(lat, lon);
```

The frontend queries: "Give me all tiles between 14:00 and 16:00 on July 15."
The backend returns an array of tile metadata with paths. The frontend renders
them as `<img>` elements in a horizontal strip, with CSS `transform: scale()`
for zoom.

---

## 10. The Rendering Engine

### 10.1 HTML/CSS Metaphor

The dashboard is a single `<canvas>` element wrapped in a React (or vanilla JS)
application. Why canvas and not DOM?

**DOM approach (easier, worse):**
Each echogram tile is an `<img>`. Each telemetry track is an SVG. Each bite
diamond is a positioned `<div>`. This works at low zoom levels with few tiles.
At 12-hour zoom with 1,440 tiles, the DOM chokes.

**Canvas approach (harder, correct):**
One `<canvas>` for the arrangement area. Tiles are drawn with
`ctx.drawImage()`. Telemetry waveforms are drawn with `ctx.lineTo()`.
Bite diamonds with `ctx.fill()`. Everything is a single paint pass.

The canvas approach scales to thousands of tiles because there's no DOM
overhead. It's also GPU-accelerated — the browser can composite the canvas
layer efficiently.

**Hybrid approach (pragmatic):**
Use the DOM for UI chrome (transport bar, track headers, slider, search).
Use `<canvas>` for the arrangement area only. This gives you accessible
HTML controls and performant data rendering.

### 10.2 Rendering Pipeline

```
1. User changes viewport (pan, zoom, jump to marker)
      │
2. Debounced API request fires
      │  GET /api/session/2026-07-15/echogram?from=...&to=...&resolution=...
      │  GET /api/session/2026-07-15/telemetry?from=...&to=...&fields=sog,rudder
      │  GET /api/session/2026-07-15/bites?from=...&to=...
      │
3. Data returns. Frontend computes layout:
      │  - Tile width = f(zoom_level, time_span)
      │  - Waveform Y scale = f(track_height, data_range)
      │  - Diamond positions = f(timestamps, track_height, species_channel)
      │
4. requestAnimationFrame(() => {
      │  ctx.clearRect(0, 0, canvas.width, canvas.height)
      │  drawGrid()          // time gridlines
      │  drawEchogram()      // tiles + overlays
      │  drawTelemetry()     // rudder, SOG, compass
      │  drawBites()         // MIDI diamonds
      │  drawConversation()  // ticker text
      │  drawMarkers()       // pattern brackets + labels
      │  drawPlayhead()      // red vertical line
      │})
      │
5. User drags playhead → requestAnimationFrame loop redraws playhead
   (no API call needed — all data for the viewport is already loaded)
```

### 10.3 Tile Rendering Strategy

Echogram tiles are the performance bottleneck. Each tile is a 370×900 PNG
(~50-100KB). At the 30s zoom level, 2-4 tiles are visible → trivial.
At the 12h zoom level, 1,440 tiles are in the viewport → requires strategy.

**Level-of-detail tile pyramid (pre-computed):**

```
Level 0: Full tiles (370×900)       — for 30s-5m zoom
Level 1: Half tiles (185×450)       — for 5m-2h zoom
Level 2: Quarter tiles (92×225)     — for 2h-12h zoom
Level 3: Heatmap strip (1×900)      — for 12h+ zoom
         ↑ pre-computed as a single image per session
```

The heatmap strip is generated offline: every 30s tile is compressed to a
1px-wide vertical strip of its average column colors, then all 1px strips
are concatenated. A 12-hour session becomes a 1,440px-wide by 900px-tall
image — trivially renderable.

The frontend loads the appropriate tile level based on zoom. At the boundary
between levels, it blends between them (cross-fade over 200ms).

### 10.4 Virtual Scrolling for Time

Traditional virtual scrolling handles vertical lists. We need horizontal
virtual scrolling through time.

Only tiles whose time range intersects the visible viewport (plus a small
buffer) are loaded into memory. As the user scrolls, tiles are loaded ahead
and discarded behind. The maximum memory footprint is bounded by the
viewport width, not the session length.

```
                   ┌── VIEWPORT ──┐
  [discard] [keep] [██████████████] [prefetch] [prefetch] [not loaded]
  ──────────────────────────────────────────────────────────────────▶
  LOADED TILES                            time →
```

### 10.5 Web Worker for Pattern Matching

Pattern matching (comparing current echogram context against historical
data) runs in a Web Worker to avoid blocking the UI thread. The worker
receives the current tile data, queries the tile index for historical
matches, and posts results back to the main thread as pattern markers.

---

## 11. The Interaction Model

### 11.1 Input Modes

The dashboard has three input modes, switched by keyboard or toolbar:

**Navigate Mode (default):**
- Click-drag in timeline: pan
- Scroll wheel: vertical scroll through tracks
- Ctrl+scroll: zoom in/out
- Click on playhead: drag to scrub
- Click in empty space: set playhead position
- Double-click: zoom to fit
- Right-click: context menu (add marker, set loop, compare with…)

**Select Mode (`V` key, like Ableton's pointer tool):**
- Click-drag in timeline: select a time range
- Selected range highlights in blue across all tracks
- Right-click selection: "loop this", "zoom to this", "export this",
  "compare with another session"
- Selected range shows aggregate stats in the inspector panel

**Draw Mode (`B` key, like Ableton's pencil tool):**
- Click-drag in timeline: draw a custom marker region
- Used to annotate interesting areas manually
- Draw a shape → name it → it becomes a searchable marker

### 11.2 Keyboard Shortcuts (DAW Convention)

```
Transport:
  Space       Play/Pause
  Shift+Space  Play from loop start
  Ctrl+Space   Play from selection start
  Enter        Return to beginning
  0            Stop

Navigation:
  ← →          Nudge playhead by 1 tile (30s)
  Shift+←→     Nudge by 1 screen-width
  ↑ ↓          Scroll tracks vertically
  Ctrl+←→      Jump to prev/next marker
  1-9          Jump to marker 1-9
  Ctrl+1-9     Set marker 1-9 at playhead

Zoom:
  Ctrl+↑↓      Zoom tracks vertically (height)
  Ctrl+←→     Zoom time horizontally
  1-0 (num)    Jump to zoom preset (1=30s, 0=3Y)
  /            Zoom to fit loop/selection
  \            Zoom to fit session

View:
  F            Focus selected track
  Esc          Exit focus / exit draw mode / cancel selection
  Tab          Cycle through expanded tracks
  S            Solo selected track (hide all others)
  Shift+S      Unsolo all
  M            Mute selected track

Markers:
  Insert       Add marker at playhead
  Shift+Insert Add pattern search at playhead
  Delete       Remove selected marker

Search:
  Ctrl+F       Focus search bar
  Ctrl+G       Find next search result
  Ctrl+Shift+G Find previous search result
```

### 11.3 Undo/Redo

Every navigation action is pushed to a history stack:

```
[zoom to 30m] → [pan right] → [set marker 3] → [zoom to 5m] → [undo] → [undo]
                                                         ↑ current position
```

Ctrl+Z / Ctrl+Y navigate the history stack. This is critical for
exploratory analysis: you zoom in to look at something, then undo
to return to your previous view. Without undo, every zoom is a
commitment. With undo, every zoom is a question you can un-ask.

### 11.4 The Inspector Panel

A right-side panel docked to the viewport (collapsible):

```
┌─────────────────────────────┐
│ INSPECTOR                   │
│                             │
│ PLAYHEAD                    │
│ 14:32:15 AKDT              │
│ 55.785°N, -131.527°W       │
│ SOG: 1.8 kts  COG: 265°    │
│ Depth: 22.5 fm              │
│ Bottom: hard (82%)          │
│ Tide: flooding, 8.2ft       │
│                             │
│ ─────────────────────────  │
│                             │
│ SELECTION [14:32-14:38]    │
│ Duration: 6m 30s            │
│ Avg SOG: 1.7 kts            │
│ SOG in band: 94%            │
│ Rudder: port 2° avg         │
│ Bites: 4 (2 landed)        │
│ Bottom: med→hard transition │
│                             │
│ ─────────────────────────  │
│                             │
│ SESSION STATS               │
│ Total time: 14h 22m        │
│ Productive: 6h 15m (44%)   │
│ Fish caught: 47             │
│ Species: 22 king, 18 coho, │
│          5 chum, 2 pink     │
│ Total weight: 612 lbs       │
│ Avg SOG: 1.9 kts            │
│                             │
│ ─────────────────────────  │
│                             │
│ LEGEND                      │
│ 🟡 King  🥈 Coho  🫒 Chum │
│ 🩷 Pink  🟤 Halibut       │
└─────────────────────────────┘
```

---

## 12. The Three Audiences

### 12.1 The Captain in the Wheelhouse

**Context:** Casey is on EILEEN, the autopilot is holding course, the
gear is in the water. He has 30 seconds to glance at a screen and learn
something useful.

**What he sees:**

The dashboard in **Record-Arm Mode**. The red border is on. The playhead
moves on its own, tracking real time. The echogram track is filling with
new tiles every 30 seconds — he watches the bottom contour scrolling in
from the right. The SOG track confirms he's at 1.8 knots, in the band.
The rudder track shows gentle oscillations — the autopilot is doing fine.

A green bracket appears on the echogram: **JUL 22 CHUM SCHOOL — 92% MATCH**.
He glances at it. He knows what that means. He doesn't need to click anything.
The confidence is high enough that he adjusts course slightly — a 5-degree
nudge to port, riding the same contour the chum were on three weeks ago.

Thirty seconds. That's the interaction. No clicks. No typing. The dashboard
is a passive display that surfaces information when it matters. It watches
with him.

**What he does when he has more time:**

At the end of the day, he opens the dashboard on a tablet in the cabin.
He zooms out to the day view. He sees the full day as a heatmap strip:
productive morning, slow midday, productive afternoon (the chum school
he found at 2pm). He sets markers on the productive areas. He adds a note:
"chum were on the flood tide, 18-24 fm, hard bottom transition."

He searches for "chum" in the conversation transcript. He replays the moment
the crew first spotted them on the sounder. He can hear it in his head —
he was there — but now he can see it as data.

### 12.2 The Non-Fishing Partner

**Context:** Casey's partner isn't a fisherman. They don't want to see
echogram tiles or rudder angles. They want to know: is he safe? Is he
coming home? What did he catch?

**What they see:**

A different view — the **Partner Dashboard**. This is a separate URL or
a toggle switch in the top-right corner of the main dashboard.

```
┌──────────────────────────────────────────────────────────────────┐
│  EILEEN — July 15, 2026                                          │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                                                             │ │
│  │                    🚤  EILEEN                               │ │
│  │                                                             │ │
│  │              SOG: 1.8 kts  •  COG: 265°                    │ │
│  │              Position: 55.785°N, 131.527°W                │ │
│  │              Depth: 22 fm  •  Bottom: hard                 │ │
│  │                                                             │ │
│  │              📍 Ketchikan, AK                              │ │
│  │              ⏱ Last update: 2 seconds ago                  │ │
│  │              🟢 All systems normal                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Today's catch:                                                   │
│  🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟 (22 king!)     │
│  🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟 (18 coho!)            │
│  🐟🐟🐟🐟🐟 (5 chum)  🐟🐟 (2 pink)                            │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  MAP                                                        │ │
│  │  [simple map showing boat position + track for the day]     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Conversation snippet:                                            │
│  "copy that" — 14:32  |  "nice king!" — 14:35                   │
│  "let's head in" — 18:45                                         │
│                                                                   │
│  ETA: ~19:30 (estimated)                                          │
└──────────────────────────────────────────────────────────────────┘
```

The partner view strips everything down to: position, safety, catch count,
and the conversation snippet (so they can hear his voice in the data).
It's warm, it's simple, it's reassuring. It answers the three questions
they actually have: where is he, is he okay, when is he coming home.

The partner view also has a "Send Message" button that sends a text to
the boat's display or the captain's phone. This is the one interaction
that flows the other way — from shore to boat.

### 12.3 The Seven-Year-Old Daughter at the Dinner Table

**Context:** Casey's daughter has an iPad. She's seven. She knows her dad
catches fish. She wants to see the fish.

**What she sees:**

The **Kids' View** — a completely different rendering of the same data.

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│              🎣  DADDY'S FISHING BOAT!                           │
│                                                                   │
│                    🚤                                            │
│                  ~ ~ ~ ~                                         │
│              ~~~~~~~~~~~~~~~~~~~                                  │
│                                                                   │
│         Today Daddy caught:                                       │
│                                                                   │
│            🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟🐟                              │
│               (tap a fish!)                                       │
│                                                                   │
│  ┌─────────────────────────────────────────┐                     │
│  │  🐟 KING SALMON  —  22 POUNDS!         │                     │
│  │  This is a BIG fish!                    │                     │
│  │  Daddy caught it at 2:32pm.            │                     │
│  │  It's as heavy as a big watermelon!     │                     │
│  │  [drawing of a king salmon]             │                     │
│  │  [X] close                              │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                   │
│         🗺️  Where is Daddy?                                     │
│         [simplified map — a cartoon boat on blue water]          │
│         He's near Ketchikan!                                      │
│                                                                   │
│         ⏰  Daddy will be home around dinnertime!                 │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

The kids' view has no timeline, no echogram, no SOG envelope. It has:
- A cartoon boat on water
- Fish icons you can tap to see species and weight
- A simple map ("Daddy is here!")
- An ETA tracker ("Daddy will be home after dinner!")
- Every fish has a kid-friendly comparison ("as heavy as a big watermelon")

The echogram tiles — those 370×900 sounder crops with their cyan-to-red
returns — are rendered as a **pretty pattern** in the background of the
cartoon boat screen. Stripes of color that flow and change. To the daughter,
it's just a pretty moving picture. To the engineer, it's the same echogram
heatmap, rendered at low opacity as a decorative element. The data is there,
it's just wearing a different face.

### 12.4 The Design Principle

The same data, three views. Not three separate apps — one data source,
three lenses. Each lens respects its audience:

| | Captain | Partner | Daughter |
|---|---------|---------|----------|
| What they care about | Patterns, decisions | Safety, connection | Fish, daddy |
| Time scale | 30s to 3 years | Right now | Today |
| Interaction | Deep, fast, keyboard-driven | Passive, reassuring | Tap to explore |
| Complexity | Maximum detail when needed | Minimum to feel connected | Zero — pure delight |
| Color palette | Dark (wheelhouse, night-vision) | Light, warm, calm | Bright, playful |
| Primary emotion | Confidence, insight | Relief, connection | Joy, pride |

---

## Appendix A: UI Layout (Full Dashboard)

```
┌──────────────────────────────────────────────────────────────────────┐
│  ╔══════════════════════════════════════════════════════════════════╗ │
│  ║ MENU BAR                                            [P] [C] [K]║ │
│  ║ FishingLog.ai  │ Session: 2026-07-15  │ EILEEN  │  🟢 LIVE     ║ │
│  ╚══════════════════════════════════════════════════════════════════╝ │
├──────────────────────────────────────────────────────────────────────┤
│ ┌────────────────────┐ ┌───────────────────────────────────────────┐ │
│ │ TRANSPORT          │ │ OVERVIEW STRIP                            │ │
│ │ ⏮⏪▶⏸⏩⏭🔴🔁 │ │ ░░████████░░░░░███████████████░░░░░████░░ │ │
│ │ Speed: 1x 2x 4x   │ │ 06:00  08:00  10:00  12:00  14:00  16:00 │ │
│ └────────────────────┘ └───────────────────────────────────────────┘ │
│                                                                       │
│ ┌──────────┐ ┌──────────────────────────────────────────────────────┐│
│ │ TRACK    │ │ ARRANGEMENT AREA (canvas)                            ││
│ │ HEADERS  │ │                                                      ││
│ │ (fixed)  │ │  ═══════════════╪══════════════════════════════════ ││
│ │          │ │                 │                                    ││
│ │ ▲ECHO    │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ││
│ │ ▲RUDD    │ │ ══════╱╲═══════│══╱╲═════════════════════════════ ││
│ │ ▲SOG     │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ││
│ │ ▲COMP    │ │ ────╱─────╲────│──╱──────────╲──────────────────── ││
│ │ ◆BITES   │ │    ·  ··   · · │·    ··    ·   ·  · ···  ·       ││
│ │ ◆CATCH   │ │ 🐟King 🐟Coho  │ 🐟King  🐟King 🐟Coho           ││
│ │ 💬CONV   │ │ "yeah I see the│ledge coming up on the port side"─▶││
│ │          │ │                 │                                    ││
│ │          │ │                 ▼                                    ││
│ │          │ │            PLAYHEAD                                 ││
│ └──────────┘ └──────────────────────────────────────────────────────┘│
│                                                                       │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ ZOOM: ████████░░░░░░░░░░░░░░░░░░░░░░░░ [2h]  │ LOOP: [14:32-38]│ │
│ └──────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│ STATUS BAR                                                 47 fish   │
│ 14:32:15 AKDT │ 55.785°N 131.527°W │ 1.8kts 265° │ 22fm hard │ 🟢  │
└──────────────────────────────────────────────────────────────────────┘
  [P] = Partner View  [C] = Captain View  [K] = Kids View
```

---

## Appendix B: Technology Stack (Provisional)

| Layer | Technology | Rationale |
|-------|-----------|----------|
| Frontend framework | React + Canvas | React for chrome, Canvas for arrangement area |
| Canvas library | Custom (or Konva.js) | Need full control over tile rendering |
| State management | Zustand or Jotai | Lightweight, works well with canvas |
| API layer | Hono (Cloudflare Workers) | Runs at edge, close to D1/R2 |
| Tile storage | Cloudflare R2 | Object storage for thousands of PNG tiles |
| Tile index | Cloudflare D1 (SQLite) | Query tiles by time range + position |
| Search | SQLite FTS5 (D1) or Workers AI | Full-text search across conversation transcripts |
| Pattern matching | Web Worker + custom similarity algo | Client-side for responsiveness |
| Realtime updates | WebSocket (Workers Durable Objects) | Live data streaming during record mode |
| Auth | Cloudflare Access | Simple, works with existing identity |

---

## Appendix C: Development Phases

### Phase 1: Static Replay (MVP)
- Load a single session's JSON data
- Render the arrangement area in canvas
- Show echogram tiles (pre-loaded), telemetry waveforms, bite diamonds
- Draggable playhead
- No live data, no pattern matching, no search
- **Goal:** Prove the DAW metaphor works visually

### Phase 2: Timeline Navigation
- Fractal zoom slider with snap points
- Virtual scrolling for time
- Keyboard shortcuts
- Overview strip
- Markers (user-created)
- **Goal:** Navigation feels like a DAW

### Phase 3: Live Data
- Record-arm mode with WebSocket streaming
- Auto-scrolling viewport
- Real-time echogram tile insertion
- Partner view
- **Goal:** Dashboard works in the wheelhouse during fishing

### Phase 4: Intelligence Layer
- Pattern matching engine
- Pattern markers with confidence visualization
- Conversation search
- Tide-aligned time mode
- Cross-session comparison
- **Goal:** Dashboard doesn't just show data, it finds patterns

### Phase 5: Polish & Audiences
- Kids' view
- Animated transitions between zoom levels
- Export (share a session as a link)
- Mobile-responsive layout
- Offline mode (pre-cache session data)
- **Goal:** Everyone on the boat (and at home) has a view that fits them

---

## Appendix D: Open Design Questions

1. **Audio rendering:** Should the bite track actually play sounds? A MIDI
   note-on for each bite, with pitch mapped to species and velocity mapped
   to weight? You could literally *hear* the fishing day — the chum wall
   would sound like a snare roll.

2. **Video track:** If we add a deck camera, how do we sync video frames
   to the timeline? Thumbnail strips like a video editor? Seek-able
   playback? This is technically the same problem as echogram tiles but
   with different data.

3. **Collaborative markers:** If two boats share a grounds, can they see
   each other's markers? Is there a "fleet view" where pattern markers
   from multiple boats are aggregated?

4. **Tide-as-primary-axis:** Should "tide mode" be the default? Clock time
   matters for logistics, but tide time matters for fish. The system could
   default to tide-aligned and offer clock as an overlay.

5. **The install experience:** The vision says an AI should deploy itself
   onto any boat. How does the dashboard appear for a new boat with zero
   historical data? What does the empty state look like, and how does it
   become useful as quickly as possible?

---

*Document version 0.1 — July 15, 2026*
*This is a vision document. Nothing is built. Everything is possible.*
