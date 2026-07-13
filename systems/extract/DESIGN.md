# TimeZero Professional — Deterministic Data Extraction Design

## Overview

This document defines a pixel-level data extraction system for **Nobeltec TimeZero Professional** navigation software running at **1600×1200** on Monitor 2 (dark theme). The extraction is **fully deterministic** — field positions are fixed by the software's GPU-rendered layout and never change between sessions.

---

## 1. Display Layout & Coordinate System

### Right-Side Data Panel
- **Panel background**: Very dark (63,60,50) or (5,5,5) — the wood/border tone
- **Panel X range**: `x = 1350` to `x = 1595` (245px wide)
- **Panel Y range**: Full height `y = 50` to `y = 950`
- **Chart background** (behind overlays): (247,235,197) — land/water
- **Text colors**: 
  - **White data values**: pure white (250,250,250) or near-white
  - **Gray labels**: light gray (140-200, 140-200, 140-200)
  - **Time**: medium-gray anti-aliased text (~150-240) on dark panel border (63,60,50)
- **Time text at ROI**: Actual pixel values are blended (anti-aliased) — peak luminance ~200–240, not pure white

### Time Display Location
⚠️ **Correction from initial assumption**: The time is NOT in a separate light box overlay. It appears at the right edge of the top window title/menu bar area (y=59-81), drawn on the dark panel border (63,60,50). The text is anti-aliased (gray transition pixels) against this dark background. The panel border itself is at (63,60,50), not pure black.

### Standard TZ Pro Layout (Confirmed)
The right-side data panel (x=1350-1595) is organized as stacked rows. Each data field pair (label + value) occupies ~25-35 vertical pixels per row.

---

## 2. Pixel Coordinates per Field

### 2.1 Primary Position (Latitude / Longitude)
**The most critical navigation data.**

| Element | X Range | Y Range | Width | Height |
|---------|---------|---------|-------|--------|
| Lat label "N" | 1398–1414 | 297–311 | 16 | 14 |
| Lat value (degrees + minutes) | 1426–1454 | 298–310* | 28 | 12* |
| Lon label "W" | 1462–1465 | 298–310 | 4 | 12 |
| Lon value | 1490–1522 | 298–310* | 32 | 12* |

**\* Two-row layout**: Row 1 = y=297–310 (large digits: latitude degrees), Row 2 = y=317–330 (decimal minutes)

**Format Parsing:**
- **Lat**: `N 55°47.289'` → parse as `"N"` + `55` (degrees) + `47.289` (decimal minutes)
  - Row 1 (y=297–310): `"N"` at x=1398-1414, `"55"` at x=1426-1433, `"°"` at x=1438-1445, small `47.` at x=1451-1454
  - Row 2 (y=317–330): `"289'"` at x=1426-1454 (actually Row 1 has `"47."` and Row 2 has `"289'"`)
- **Lon**: `W 131°30.851'` → parse as `"W"` + `131` (degrees) + `30.851` (decimal minutes)
  - Row 1: `"W"` at x=1462-1465, `"131"` at x=1490-1509, `"°"` at x=1514-1522
  - Row 2: `"30.851'"` at x=1490-1522

### 2.2 Secondary / Cursor Position
- **Label**: `"Cursor Information"` + `"Position Lat/Lon"` — y=348–385, x=1350–1510
- **Cursor Lat**: `N 55°47.400'` — y=390–410, x=1350–1450
- **Cursor Lon**: `W 131°35.114'` — y=410–420, x=1350–1450

### 2.3 Speed Over Ground (SOG)
| Element | X Range | Y Range | Width | Height |
|---------|---------|---------|-------|--------|
| SOG label | 1400–1450 | 505–515 | ~50 | ~10 |
| SOG value "1.4" | 1476–1490 | 513–536 | 18 | 23 |
| SOG unit "kn" | 1510–1524 | 513–536 | 14 | 23 |

**Format:** Always `"X.X kn"` (one digit, decimal point, one digit, space, "kn")

**Confirmed in screenshot:** `"1.4 kn"`
- Value part `1.4`: x=1470-1500, y=507-540 (vertical height spans the character)
- Unit `kn`: x=1510-1525, y=507-540
- Note: Tesseract returns `"1.4:"` with a trailing colon character — strip non-numeric suffix during parsing

### 2.4 Time Display
| Element | X Range | Y Range | Width | Height |
|---------|---------|---------|-------|--------|
| Time area (panel border) | 1528–1597 | 59–82 | 69 | 22 |
| Time text (anti-aliased) | 1533–1593 | 60–80 | ~60 | ~20 |

**Format:** `H:MM AM` or `HH:MM AM` (12-hour, always leading space for single-digit hour)

**Font characteristics:** 
- Digit height: ~18px, width: ~8-10px per digit
- Colon: ~4px wide at center, ~2px at top/bottom
- Space between digits: ~4-5px
- Text is anti-aliased white (~200-255) on dark panel border (63,60,50)
- The text shows as blended gray pixels against the dark bg, making thresholding tricky
- Two character clusters: left `6:07` (x=1533-1554) and right `AM` (x=1572-1593)
  - Left cluster y=60-80, x=1533-1554: `6:07`
  - Right cluster y=60-80, x=1572-1593: `AM`

### 2.5 Tide Graph
| Element | X Range | Y Range | Width | Height |
|---------|---------|---------|-------|--------|
| Tide area | 1357–1477 | 606–697 | 120 | 91 |

- Teal water area: (0,139,139) at x=1409-1552, y=606-697

### 2.6 Bearing & Range / Waypoint Info
| Element | Location |
|---------|----------|
| Waypoint label "Loring" | y=556–568, x=1420–1500 |

### 2.7 Title Bar
- y=49–53, x=1350–1425: Application title text in white/gray

### 2.8 Bottom Row (Controls/Status)
- y=840–855, x=1480–1560: Light text, appears to be UI control labels

---

## 3. Extraction Algorithm (Tier 1 — Deterministic)

### 3.1 Pipeline Overview

```
Snapshot Capture → Crop ROI → Threshold → Tesseract PSM 7 → Parse → Validate → Output
```

### 3.2 Preprocessing

For each field region:
1. **Crop** to the exact ROI coordinates from §2
2. **Convert to grayscale** (PIL `Image.convert('L')`)
3. **Apply threshold**:
   - For white-on-dark text (lat/lon, SOG, labels): threshold at 200 (`x > 200 → 255, else 0`)
   - For time text (anti-aliased on dark panel): two-stage threshold — first remove dark panel bg (pixel > 100 to detect foreground), then upscale 2× and re-threshold. OR simply crop the digit regions individually.
4. **Optional: upscale 2x** using `Image.NEAREST` to improve Tesseract accuracy on small fonts

### 3.3 Per-Field Processing Steps

#### Primary Position (Lat/Lon)

```
ROI = img.crop((1395, 295, 1570, 335))    # full lat/lon block
gray = ROI.convert('L')
binary = gray.point(lambda x: 255 if x > 200 else 0)
text = pytesseract.image_to_string(binary, config='--psm 6')
# Parse: "N 55°47.289'\nW 131°30.851'"
# Use regex: ([NSEW])\s*(\d+)°(\d+\.\d+)'
lat_match = re.search(r'([NS])\s*(\d+)°(\d+\.\d+)\'', text)
lon_match = re.search(r'([EW])\s*(\d+)°(\d+\.\d+)\'', text)
lat = f"{lat_match.group(1)} {lat_match.group(2)}°{lat_match.group(3)}'"
```

**Fallback single-field crops** if full block fails:
- Latitude: `img.crop((1395, 296, 1460, 332))`  
- Longitude: `img.crop((1460, 296, 1570, 332))`

#### SOG

```
ROI = img.crop((1470, 507, 1540, 540))
gray = ROI.convert('L')
binary = gray.point(lambda x: 255 if x > 200 else 0)
text = pytesseract.image_to_string(binary, config='--psm 7 -c tessedit_char_whitelist=0123456789.kn')
# Expected: "1.4 kn"
# Split on space, take value as float
```

#### Time
**Known OCR challenge:** The time text is anti-aliased (gray transition pixels) against the dark panel border (63,60,50). Pure white pixels are rare; most "text" pixels are in the 150-240 range. Standard threshold at 200 loses much of the character.

**Recommended approach:**
1. Crop the digit regions tightly (each character cluster is small)
2. For each cluster, scan the pixel run vertically, compute the mean luminance, and classify based on vertical projection profile
3. As fallback, use a wider luminance threshold (e.g., `x > 100` to capture anti-aliased edges) then morphological close to fill gaps before OCR

```python
# Best approach for anti-aliased time text:
ROI = img.crop((1528, 58, 1597, 83))
gray = np.array(ROI.convert('L'))
# Remove the dark panel background (63) by subtracting it
foreground = np.where(gray > 100, gray, 0)
# Normalize and threshold
binary = ((foreground / foreground.max()) * 255).astype('uint8')
# Or simply threshold at 128 after removing the bg
binary = ((gray > 100) * 255).astype('uint8')
text = pytesseract.image_to_string(Image.fromarray(binary, 'L'), 
    config='--psm 7 -c tessedit_char_whitelist=0123456789:AMP ')
```

If full crop fails, split into:
- Left digits: `img.crop((1530, 59, 1560, 82))` → "6:07"
- Right AM/PM: `img.crop((1570, 59, 1595, 82))` → "AM"

**Expected accuracy:** ~90% for time (lower than other fields due to anti-aliasing).

### 3.4 Tesseract Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `--psm` | 6 (single uniform block) for multi-line, 7 (single line) for single-field | 6 for lat/lon block, 7 for individual fields |
| `--oem` | 1 (LSTM) | Default; better for digit-heavy text |
| `-c tessedit_char_whitelist` | Per-field (digits + NSEW for pos, digits + .kn for SOG, digits + :AMP for time) | Eliminates OCR hallucination of non-numeric chars |

### 3.5 Validation Rules (Rejection Criteria)

If any of these fail, fall back to Tier 2:

- **Lat**: Must match `[NS] \d+°\d+\.\d+'` (e.g., "N 55°47.289'")
  - Degrees: 0–90, Minutes.decimal: 0.000–59.999
- **Lon**: Must match `[EW] \d+°\d+\.\d+'` (e.g., "W 131°30.851'")
  - Degrees: 0–180, Minutes.decimal: 0.000–59.999
- **SOG**: Must match `\d\.\d kn` (e.g., "1.4 kn")
  - Value: 0.0–99.9 (realistic boat speed)
- **Time**: Must match `\d+:\d+ [AP]M` (e.g., "6:07 AM" or "12:00 PM")
  - H: 1–12, MM: 00–59

---

## 4. Expected Accuracy per Field

| Field | Expected Accuracy | Notes |
|-------|------------------|-------|
| **Latitude** | >99% | Large digits, white on very dark bg, minimal anti-aliasing in the value region |
| **Longitude** | >99% | Same as lat; the degree symbol and apostrophe are well-separated |
| **SOG** | >98% | Short 3-char string with whitelist; the "1.4" and "kn" are spaced |
| **Time** | ~90% | Anti-aliased text on dark panel border; pixels are gray (150-240), not pure white; needs background-subtraction threshold |
| **Cursor Position** | >90% | Smaller text, more overlay blending |
| **Tide Graph** | N/A — visual/graphical, not text | Not suitable for OCR; use pixel-value analysis for level detection |

### Failure Modes
1. **Time anti-aliasing**: The time text is anti-aliased against a dark background, producing gray transition pixels (150-240) that confuse binarization. Mitigation: use background subtraction threshold (> 100), then normalize.
2. **Lat/Lon degree symbol**: The `°` symbol is small (5×5px) and sometimes connected to digits. Use whitelist to skip it; parse degrees by context.
3. **Anti-aliasing at margins**: GPU rendering creates 1-2px of gray transition pixels at character edges. Threshold at 200 effectively strips these to binary for bright text on dark (lat/lon, SOG).
4. **"W" misread as "V"**: Tesseract LSTM model sometimes reads "W" as "V" in the lon label. Mitigation: accept "W" or "V" in the parser, preferring "W" for longitude context.

---

## 5. Fallback Strategy (Tier 2)

When Tier 1 validation fails, apply these fallbacks in order:

### 5.1 Adaptive Thresholding
Replace fixed threshold with Otsu's method:
```python
import cv2
_, binary = cv2.threshold(np.array(gray), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
```
This handles slight variations in display brightness or theme changes.

### 5.2 Multi-Column Split OCR
For lat/lon: OCR each character column individually:
```python
# After pixel-scan analysis, these column positions are known:
# Char columns for lat: [(1426,1433), (1438,1445), (1451,1454)]  -- row1
# Char columns for lat: [(1420,1421), (1426,1433), (1438,1445)]  -- row2
# OCR each individually with PSM 10 (single character)
```

### 5.3 Pixel-Value Character Classification
For SOG and digits: implement a simple template-free classifier:
1. Crop each digit's bounding box (from pixel-run analysis)
2. Count on-pixels per row/column
3. Match against a rule-based decision tree:
   - "1": thin vertical stroke (~2px wide), empty left side
   - "4": vertical right edge + diagonal
   - "7": horizontal top + diagonal down-right
   - etc.

### 5.4 Image Gradient-Based Registration
If the screenshot has shifted (window resize, DPI change):
1. Detect the panel border (transition from water/land tan (247,235,197) to dark panel (63,60,50) at x≈1357)
2. Use this edge as anchor to recalibrate all crop coordinates
3. This handles ±50px shifts from borderless window resizing

### 5.5 Full-Image OCR with Post-Processing
As last resort: OCR the entire right panel with PSM 6 and parse:
```python
full_panel = img.crop((1350, 55, 1595, 950))
# Apply grid-based filtering to extract known field positions from noise
```

---

## 6. Live Capture Implementation Notes

### Screen Capture
Use `mss` (Multi-Screen Shot) for fast captures:
```python
import mss
with mss.mss() as sct:
    # Monitor 2 = index 2, or use bounds
    monitor = sct.monitors[2]  # 0=all, 1=primary, 2=secondary
    bbox = (monitor["left"], monitor["top"], 
            monitor["left"] + 1600, monitor["top"] + 1200)
    sct_img = sct.grab(bbox)
    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
```

### Capture frequency
- Lat/Lon/SOG: sample every 1-2 seconds (typical GPS update rate)
- Time: sample every 5 seconds (changes slowly)
- Tide: sample every 30 seconds

---

## 7. Implementation Dependencies

| Package | Version | Use |
|---------|---------|-----|
| `Pillow` | ≥10.0 | Image processing |
| `pytesseract` | ≥0.3.10 | OCR binding |
| `Tesseract-OCR` | ≥5.4 | OCR engine |
| `numpy` | ≥1.24 | Array ops for thresholding |
| `mss` | ≥9.0 | Screen capture (live mode) |
| `opencv-python` | optional | Adaptive thresholding fallback |

### Tesseract Installation Verification
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

---

## 8. Coordinate Reference Summary (Quick Reference)

```
Panel start x:        1350
Panel end x:          1595

TIME box:             (1530, 59) → (1595, 82)
TIME text:            (1533, 60) → (1593, 80)

LAT label "N":        (1398, 297) → (1414, 311)
LAT row 1 (deg):      (1426, 298) → (1454, 310)
LAT row 2 (min):      (1426, 317) → (1454, 330)
LON label "W":        (1462, 298) → (1465, 310)
LON row 1 (deg):      (1490, 298) → (1522, 310)
LON row 2 (min):      (1490, 317) → (1522, 330)
Lat/Lon full block:   (1395, 295) → (1570, 335)

SOG value:            (1470, 507) → (1540, 540)
SOG left "X.":        (1470, 505) → (1500, 540)  
SOG right "X kn":     (1500, 505) → (1545, 540)

CURSOR lat/lon label: (1350, 348) → (1510, 385)
CURSOR lat:           (1350, 390) → (1450, 420)
CURSOR lon:           (1350, 410) → (1450, 420)

TIDE area:            (1357, 606) → (1477, 697)

WAYPOINT label:       (1420, 556) → (1500, 568)
```

---

## 9. Code Template

```python
import re
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class TZProExtractor:
    """Deterministic pixel-level data extractor for Nobeltec TimeZero Pro."""
    
    # Region definitions (in screenshot coordinates at 1600×1200)
    REGIONS = {
        'time':         (1528, 58, 1597, 83),
        'lat_lon':      (1395, 295, 1570, 335),
        'lat_value':    (1395, 296, 1460, 332),
        'lon_value':    (1460, 296, 1570, 332),
        'sog':          (1470, 507, 1540, 540),
        'cursor_label': (1350, 348, 1510, 385),
        'cursor_lat':   (1350, 390, 1450, 420),
        'cursor_lon':   (1350, 410, 1450, 420),
    }
    
    def __init__(self, tess_threshold=200):
        self.threshold = tess_threshold
    
    def _crop_and_ocr(self, img_cv, region_name, psm=7, whitelist=None):
        x1, y1, x2, y2 = self.REGIONS[region_name]
        roi = img_cv.crop((x1, y1, x2, y2))
        gray = roi.convert('L')
        
        # Handle time (dark text on light bg) vs other fields (light text on dark bg)
        if region_name == 'time':
            binary = gray.point(lambda x: 0 if x > 150 else 255)
        else:
            binary = gray.point(lambda x: 255 if x > self.threshold else 0)
        
        config = f'--psm {psm}'
        if whitelist:
            config += f' -c tessedit_char_whitelist={whitelist}'
        
        text = pytesseract.image_to_string(binary, config=config).strip()
        return text
    
    def extract(self, img_path):
        img = Image.open(img_path)
        results = {}
        
        # --- Primary Position ---
        pos_text = self._crop_and_ocr(img, 'lat_lon', psm=6)
        lat_match = re.search(r'([NS])\s*(\d+)°(\d+\.\d+)\'', pos_text)
        lon_match = re.search(r'([EW])\s*(\d+)°(\d+\.\d+)\'', pos_text)
        
        if lat_match:
            results['lat'] = f"{lat_match.group(1)} {lat_match.group(2)}°{lat_match.group(3)}'"
            results['lat_decimal'] = float(lat_match.group(2)) + float(lat_match.group(3)) / 60.0
        if lon_match:
            results['lon'] = f"{lon_match.group(1)} {lon_match.group(2)}°{lon_match.group(3)}'"
            results['lon_decimal'] = float(lon_match.group(2)) + float(lon_match.group(3)) / 60.0
        
        # --- SOG ---
        sog_text = self._crop_and_ocr(img, 'sog', whitelist='0123456789.kn ')
        sog_match = re.search(r'(\d+\.\d+)\s*kn', sog_text)
        if sog_match:
            results['sog_kn'] = float(sog_match.group(1))
            results['sog_str'] = sog_match.group(0)
        
        # --- Time ---
        time_text = self._crop_and_ocr(img, 'time', whitelist='0123456789:AMP ')
        time_match = re.search(r'(\d+:\d+ [AP]M)', time_text)
        if time_match:
            results['time'] = time_match.group(1)
        
        return results
```

---

## 10. Extensibility

To add new fields (depth, BRG, RNG, COG, water temp):
1. Locate the field in a fresh screenshot (they appear when configured in TZ Pro panels)
2. Add its bounding box to `REGIONS` dict
3. Add a `_crop_and_ocr` call and parse logic
4. Add validation rules

The pixel-scan pattern for finding fields automatically:
- Scan y=50-950, x=1352-1570 for white pixels (>220)
- Group consecutive rows with stable horizontal runs
- Each group is a potential data field
- Label text is typically gray (140-180), value text is white (>220) and appears on the next row(s)
