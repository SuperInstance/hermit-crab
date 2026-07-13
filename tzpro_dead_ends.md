# TZ Pro Extraction — What Doesn't Work / Dead Ends

A log of things tried and rejected, to avoid repeating dead ends.

## Approaches Tried

### 1. Full-image OCR (x=0 to 1600, y=0 to 1200) — FAILED
**Problem:** Tesseract processes the entire chart, picking up chart labels, land names, depth soundings, etc. Way too noisy. The right panel text gets lost in the noise.

### 2. Enhanced full-image OCR (autocontrast, sharpen) — FAILED
**Problem:** The chart has a tan/beige background (247,235,197) with dark text on it. Applying autocontrast blows out the subtle dark-theme panel text. The enhanced version had *worse* OCR than raw.

### 3. Pure pixel matching (scanning rows for white pixels) — PARTIAL
**Problem:** TZ Pro uses anti-aliased GPU rendering. Text pixels are gray transitions (150-240), not pure white. Scanning for white (>250) misses most of the character. You get disconnected fragments.

### 4. Simple binary threshold at 200 — PARTIAL
**Problem:** Works for bright white text on very dark backgrounds (lat/lon, SOG) but fails for anti-aliased text (time display) where pixels are in the 150-240 range. The time display needs background-subtraction thresholding (>100 then normalize).

### 5. Otsu thresholding — PARTIAL
**Problem:** Otsu finds a global threshold which doesn't work well when the crop has both bright text and dark panel background. The text pixels are a small fraction of the crop, so Otsu picks a threshold closer to the background mean.

### 6. Reading time as a single crop — DIFFICULT
**Problem:** The time text "7:23 AM" is anti-aliased against a dark panel edge (63,60,50). The colon `:` is tiny (~4px) and gets lost in thresholding. Splitting into left-digits and AM/PM halves works better.

### 7. Tesseract PSM modes for SOG — CONFUSING
**Problem:** SOG values like "1.4 kn" get OCR'd as "1.4" or "1.4." or "1.510" or "1.5°°" — Tesseract hallucinates trailing garbage characters. The `tessedit_char_whitelist=0123456789.kn ` helps but doesn't eliminate all garbage. The `1.5°°` result is interesting — the degree symbols (background chart labels at ~x=1440) bleed into the SOG crop.

### 8. Claude Code via stdin piping (`Get-Content | claude -p @-`) — FAILED
**Problem:** PowerShell doesn't support the `@-` stdin syntax that bash does. Using a temp file approach (`claude -p "Read file X and do what it says"`) works but adds complexity.

### 9. R2Sink `_access_key` / `_secret_key` properties — BROKEN ARCHITECTURE
**Problem:** The code used `@property` for `_access_key` and `_secret_key` but the `_ak` and `_sk` instance variables were never set in `__init__`. The workaround was patching `__init__` with a monkeypatch function. Needs a proper refactor.

## Known OCR Gotchas

| Symbol/Observation | What Tesseract Reads | Why |
|---|---|---|
| "W" (west) | Frequently "V" | LSTM model confuses the two |
| Degree symbol ° | Garbled/byte-mangled | Unicode handling issues |
| "---" (no data) | Various garbage | System processes as text |
| "1.4 kn" | "1.4" / "1.4." / "1.5°°" | Chart degree symbol bleeds into SOG crop area |
| NMEA position | "XY N 55°47.250' pos" | Tesseract prepends "XY" from chart decoration |

## Abandoned Features

- **OpenCV adaptive thresholding** — Not needed; the base Tesseract crops work well enough for the core data (lat/lon/SOG/tide). Only consider for the anti-aliased time field.
- **Template matching each digit** — Overkill given that Tesseract on tight crops with whitelists works at ~95% accuracy. The ROI for template matching wouldn't justify the effort.
- **Video-based interpolation between screenshots** — Not useful when the data is extracted from the display at 1Hz.
