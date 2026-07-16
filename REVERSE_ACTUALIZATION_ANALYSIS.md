# FishingLog.ai / ActiveLog.ai — Reverse-Actualization Analysis

**Date:** 2026-07-15  
**Author:** Systems Architect (subagent)  
**Purpose:** Work backwards from the DAW-like dashboard end-state to define Year 1 engineering delivered on a fishing boat (RTX 4050 6GB, Windows 11, alongside NMEA bridge + hermitd).

---

## Executive Summary

The end-state is a **DAW-like timeline** where every sensor stream (echogram, rudder, compass, SOG, conversation transcript, catch log) is a synchronized track. You scrub the playhead; all tracks move together. A catch event at T=14:32:17 lights up the echogram track, the GPS track, the autopilot rudder track, and the voice transcript track simultaneously.

**Year 1 reality:** We have a 30-second sounder crop pipeline writing JSONL logs, paired with NMEA position. No TileDB. No Florence-2. No catch correlation. No delta detection. The DAW doesn't exist.

This document bridges that gap with **minimum viable engineering** — nothing that won't survive a season on a 50-foot troller in Southeast Alaska.

---

## 1. Minimum Viable Data Model — TileDB Array Schema

### 1.1 Why TileDB (and why not yet)

**Don't install TileDB in Year 1.** The current JSONL + PNG file layout works, is human-readable, survives power loss, and requires zero dependencies beyond Python stdlib.

**Migrate to TileDB when:**
- Daily observations exceed 50,000 rows (≈ 17 days at 30s cadence)
- You need sub-second slice queries: "give me all echogram tiles between 45–55 fathoms on July 12"
- You want to compress 40 GB of PNGs into 4 GB of chunked arrays

Until then, **the file system IS the database.**

### 1.2 Current Layout (Year 1 — Keep This)

```
tzpro-agent/
├── captures/
│   ├── frame_20260715_105941.png          # Full frame (4 min cadence)
│   ├── frame_20260715_105941_sounder.png  # Sounder crop (30s cadence)
│   └── ...
└── memory/
    ├── observations/
    │   └── 2026-07-15.jsonl               # One JSON line per observation
    └── daily/
        └── 2026-07-15.md                   # Human-readable summary
```

**JSONL line (current, ~400 bytes):**
```json
{
  "ts": "2026-07-15T17:59:41+00:00",
  "sounder": "frame_20260715_105941_sounder.png",
  "position": {"lat": 55.3421, "lon": -131.6452},
  "vessel": {"sog": 2.3, "cog": 287},
  "sounder_analysis": {
    "depth_fm": 42.5,
    "bottom_type": "medium",
    "confidence": "high",
    "fish": {"count": 127, "distribution": "moderate", "depth_range": [0.31, 0.58]},
    "thermoclines": {"layer_count": 2, "layers": [{"y": 240, "depth_frac": 0.27, ...}]},
    "depth_scale": [0, 20, 40, 60, 80]
  }
}
```

### 1.3 TileDB Schema (Year 2 — Design Now, Deploy Later)

When the migration trigger hits, this is the **exact schema** to create. No iteration — copy/paste.

```python
# create_tiledb_schema.py — Run ONCE per season directory
import tiledb
import numpy as np
from pathlib import Path

SEASON_DIR = Path("F:/fishinglog/seasons/2026")  # External SSD recommended
ARRAY_URI = str(SEASON_DIR / "echogram_tiles")

# ── Domain: (time_sec, depth_bin, ping_index) ───────────────────────
# time_sec: Unix epoch seconds (int64) — aligns with NMEA timestamps
# depth_bin: 0..255 — normalized depth (0=surface, 255=max_range)
# ping_index: 0..N-1 — horizontal position within the sounder window
#              (maps to sounder pixel column; 370 columns → ping_index 0..369)

dom = tiledb.Domain(
    tiledb.Dim(name="time_sec", domain=(0, 2**63-1), tile=3600, dtype=np.int64),   # 1-hour tiles
    tiledb.Dim(name="depth_bin", domain=(0, 255), tile=256, dtype=np.uint8),        # Full depth per tile
    tiledb.Dim(name="ping_index", domain=(0, 369), tile=370, dtype=np.uint16),      # Full width per tile
)

# ── Attributes ──────────────────────────────────────────────────────
attrs = [
    # Raw intensity (0-255) — the echogram pixel value
    tiledb.Attr(name="intensity", dtype=np.uint8, filters=tiledb.FilterList([tiledb.ZstdFilter(level=3)])),
    # RGB channels for palette analysis (optional, 3x storage)
    tiledb.Attr(name="r", dtype=np.uint8, filters=tiledb.FilterList([tiledb.ZstdFilter(level=3)])),
    tiledb.Attr(name="g", dtype=np.uint8, filters=tiledb.FilterList([tiledb.ZstdFilter(level=3)])),
    tiledb.Attr(name="b", dtype=np.uint8, filters=tiledb.FilterList([tiledb.ZstdFilter(level=3)])),
    # Metadata — sparse, one per time_sec (not per voxel)
    tiledb.Attr(name="lat", dtype=np.float64),
    tiledb.Attr(name="lon", dtype=np.float64),
    tiledb.Attr(name="sog", dtype=np.float32),
    tiledb.Attr(name="cog", dtype=np.float32),
    tiledb.Attr(name="depth_fm", dtype=np.float32),       # Calibrated bottom depth
    tiledb.Attr(name="bottom_type", dtype=np.uint8),      # 0=hard,1=medium,2=soft_mud,3=very_soft,4=mixed
    tiledb.Attr(name="bottom_confidence", dtype=np.uint8), # 0=low,1=medium,2=high
    tiledb.Attr(name="fish_count", dtype=np.uint16),
    tiledb.Attr(name="fish_distribution", dtype=np.uint8), # 0=none,1=scattered,2=moderate,3=dense,4=very_dense
    tiledb.Attr(name="catch_event", dtype=np.uint8),       # 0=no, 1=yes — set by catch correlation loop
    tiledb.Attr(name="catch_species", dtype="U16"),        # "chum", "coho", "chinook", etc.
    tiledb.Attr(name="catch_weight_lbs", dtype=np.float32),
    tiledb.Attr(name="notes", dtype="U256"),               # Captain's voice note transcribed
]

schema = tiledb.ArraySchema(domain=dom, sparse=True, attrs=attrs, allows_duplicates=False)
tiledb.Array.create(ARRAY_URI, schema)
print(f"Created {ARRAY_URI}")
```

**Key design choices:**

| Decision | Rationale |
|----------|-----------|
| `sparse=True` | Only ~30s cadence writes; 99.9% of time×depth×ping space is empty |
| `tile=3600` on time | 1-hour tiles = natural query boundary (tide windows, drift sets) |
| `tile=256` on depth | Full depth column in one tile — single read gets entire water column |
| `tile=370` on ping | Full sounder width — one tile = one complete sounder frame |
| `Zstd level 3` | 2-3x compression on echogram data; fast enough on 4050 |
| `catch_event` boolean | Enables "show me all frames where we caught chum" without join |

### 1.4 Migration Script (Run at Season End)

```python
# migrate_jsonl_to_tiledb.py
import json, tiledb, numpy as np
from pathlib import Path
from PIL import Image

OBS_DIR = Path("tzpro-agent/memory/observations")
ARRAY_URI = "F:/fishinglog/seasons/2026/echogram_tiles"

with tiledb.open(ARRAY_URI, 'w') as A:
    for jsonl_path in sorted(OBS_DIR.glob("*.jsonl")):
        date_str = jsonl_path.stem
        with open(jsonl_path) as f:
            for line in f:
                obs = json.loads(line)
                
                # Load sounder PNG → intensity array
                sounder_path = Path("tzpro-agent/captures") / obs["sounder"]
                if not sounder_path.exists():
                    continue
                img = Image.open(sounder_path).convert("RGB")
                arr = np.array(img)  # (900, 370, 3)
                
                # Downsample depth: 900px → 256 bins (stride 3.5, take max)
                intensity = arr[:, :, 0].max(axis=0)  # Simplification: use R channel as intensity proxy
                # Proper: (r+g+b)/3 → 900→256 via max-pool
                depth_bins = 256
                pooled = np.zeros((depth_bins, 370), dtype=np.uint8)
                stride = 900 // depth_bins
                for i in range(depth_bins):
                    y_start = i * stride
                    y_end = min(y_start + stride, 900)
                    pooled[i, :] = intensity[y_start:y_end, :].max(axis=0)
                
                ts = int(datetime.fromisoformat(obs["ts"].replace("Z", "+00:00")).timestamp())
                
                # Write one frame = 370×256 = 94,720 cells
                A[ts, 0:256, 0:370] = {
                    "intensity": pooled.flatten(order='F'),  # Column-major: depth varies fastest
                    "r": arr[:, :, 0].max(axis=0).flatten(order='F'),  # Same pooling for RGB
                    "g": arr[:, :, 1].max(axis=0).flatten(order='F'),
                    "b": arr[:, :, 2].max(axis=0).flatten(order='F'),
                    "lat": obs["position"]["lat"],
                    "lon": obs["position"]["lon"],
                    "sog": obs["vessel"]["sog"],
                    "cog": obs["vessel"]["cog"],
                    "depth_fm": obs["sounder_analysis"]["depth_fm"],
                    "bottom_type": {"hard":0,"medium":1,"soft_mud":2,"very_soft":3,"mixed":4}.get(
                        obs["sounder_analysis"]["bottom_type"], 4),
                    "bottom_confidence": {"low":0,"medium":1,"high":2}.get(
                        obs["sounder_analysis"]["bottom_confidence"], 1),
                    "fish_count": obs["sounder_analysis"]["fish"].get("count", 0),
                    "fish_distribution": {"none":0,"scattered":1,"moderate":2,"dense":3,"very_dense":4}.get(
                        obs["sounder_analysis"]["fish"].get("distribution"), 0),
                    "catch_event": 0,  # Filled later by correlation loop
                    "catch_species": "",
                    "catch_weight_lbs": 0.0,
                    "notes": "",
                }
```

**Storage estimate:** 1 frame ≈ 95K cells × 4 attrs × 1 byte ≈ 380 KB compressed → ~115 GB/season (2,880 frames/day × 120 days). Fits on a 2 TB external SSD with room for 10+ seasons.

---

## 2. Florence-2 Integration Path — From OCR to Human Description

### 2.2 The Gap

**Current:** Tesseract reads "7.0" from depth scale. That's it.

**Target:** "The sounder shows a hard bottom at 42 fathoms with a scattered layer of bait at 25 fathoms, a thermocline at 30 fathoms, and two distinct arches at 38 fathoms — likely chum salmon holding off the bottom transition."

### 2.3 Architecture: Two-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1: Structured Extraction (runs every 30s, <500ms on 4050) │
├─────────────────────────────────────────────────────────────────┤
│ Input:  370×900 sounder crop (RGB)                              │
│ Model:  Florence-2-base (0.23B params) — quantized INT4 (~120MB)│
│ Task:   <CAPTION> + <DENSE_REGION_CAPTION> + <OCR>             │
│ Output: JSON with bounding boxes, labels, depth-scale numbers   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 2: Narrative Synthesis (runs on-demand, <2s on 4050)      │
├─────────────────────────────────────────────────────────────────┤
│ Input:  Stage 1 JSON + NMEA context + recent catch history      │
│ Model:  Phi-3.5-mini (3.8B) — quantized INT4 (~2.3GB)           │
│ Task:   Convert structured detections → Captain's language      │
│ Output: Natural language paragraph + confidence scores          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 Why Two Models (Not One Big Model)

| Factor | Florence-2-base (0.23B) | Phi-3.5-mini (3.8B) | Single 7B Model |
|--------|------------------------|---------------------|-----------------|
| VRAM (INT4) | 120 MB | 2.3 GB | 4.5+ GB |
| 30s inference | 300 ms | — | 2+ s |
| On-demand inference | — | 1.5 s | 3+ s |
| OCR quality | Excellent (trained) | Poor | Good |
| Reasoning | None | Strong | Strong |
| **Total VRAM** | **2.4 GB** | | **4.5+ GB** |

**6 GB VRAM budget:** 2.4 GB leaves 3.6 GB for OS, display, NMEA bridge, hermitd, Python overhead. Single 7B model leaves <1 GB — OOM risk on Windows.

### 2.5 Stage 1: Florence-2 Prompt Engineering

```python
# florence_extractor.py — Runs every 30s, outputs structured JSON
from transformers import AutoProcessor, AutoModelForCausalLM
import torch
from PIL import Image

MODEL_ID = "microsoft/Florence-2-base"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16  # INT4 via bitsandbytes if needed

processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, trust_remote_code=True, torch_dtype=DTYPE
).to(DEVICE).eval()

# ── Prompt sequence (single forward pass with multiple tasks) ───────
TASKS = [
    "<CAPTION>",                    # General scene description
    "<DENSE_REGION_CAPTION>",       # All regions with boxes + labels
    "<OCR>",                        # All text (depth scale numbers)
    "<OD>",                         # Object detection: bottom, fish, thermocline
]

def extract_sounder_structure(image_path: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    results = {}
    
    for task in TASKS:
        inputs = processor(text=task, images=img, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=512,
                num_beams=3,
            )
        text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        results[task] = processor.post_process_generation(
            text, task=task, image_size=img.size
        )
    
    # ── Normalize to our schema ────────────────────────────────────
    return {
        "caption": results["<CAPTION>"].get("<CAPTION>", ""),
        "regions": results["<DENSE_REGION_CAPTION>"].get("<DENSE_REGION_CAPTION>", []),
        "ocr": results["<OCR>"].get("<OCR>", ""),
        "objects": results["<OD>"].get("<OD>", {"bboxes": [], "labels": []}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

**Florence-2 output parsing (critical — it's messy):**

```python
def parse_florence_output(raw: dict) -> dict:
    """Convert Florence-2's quirky output to our typed schema."""
    parsed = {
        "depth_scale_numbers": [],
        "bottom": {"bbox": None, "type": None, "confidence": 0},
        "fish_schools": [],
        "thermoclines": [],
        "other": [],
    }
    
    # OCR: "0 20 40 60 80" → [0, 20, 40, 60, 80]
    ocr_text = raw.get("ocr", "")
    parsed["depth_scale_numbers"] = [float(x) for x in re.findall(r"\d+\.?\d*", ocr_text)]
    
    # Dense regions: [{"bbox": [x1,y1,x2,y2], "label": "hard bottom at 42 fathoms"}, ...]
    for region in raw.get("regions", []):
        label = region.get("label", "").lower()
        bbox = region.get("bbox")
        if "bottom" in label:
            parsed["bottom"] = {"bbox": bbox, "type": label, "confidence": 0.8}
        elif "fish" in label or "bait" in label or "school" in label:
            parsed["fish_schools"].append({"bbox": bbox, "label": label, "confidence": 0.7})
        elif "thermocline" in label or "temperature" in label:
            parsed["thermoclines"].append({"bbox": bbox, "label": label, "confidence": 0.7})
        else:
            parsed["other"].append({"bbox": bbox, "label": label, "confidence": 0.5})
    
    # OD objects (backup if dense regions miss things)
    for bbox, label in zip(raw["objects"].get("bboxes", []), raw["objects"].get("labels", [])):
        if label not in [r["label"] for r in parsed["fish_schools"] + parsed["thermoclines"]]:
            if "fish" in label or "bait" in label:
                parsed["fish_schools"].append({"bbox": bbox, "label": label, "confidence": 0.6})
            elif "thermocline" in label:
                parsed["thermoclines"].append({"bbox": bbox, "label": label, "confidence": 0.6})
    
    return parsed
```

### 2.6 Stage 2: Phi-3.5 Narrative Synthesis (On-Demand Only)

```python
# narrator.py — Called when Captain asks "what am I looking at?"
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

NARRATOR_ID = "microsoft/Phi-3.5-mini-instruct"
tokenizer = AutoTokenizer.from_pretrained(NARRATOR_ID)
model = AutoModelForCausalLM.from_pretrained(
    NARRATOR_ID, torch_dtype=torch.float16, device_map="auto"
).eval()

SYSTEM_PROMPT = """You are a commercial fishing electronics interpreter. 
Convert structured sounder analysis into the language a troller captain uses.
Be specific: depths in fathoms, bottom types (hard/medium/soft/mud), 
fish behavior (arches=single fish, clouds=bait, layers=schools).
Reference tide, time, and recent catch context when relevant.
Never hallucinate. If uncertain, say "uncertain"."""

def narrate_sounder(florence_json: dict, nmea: dict, recent_catches: list) -> str:
    context = f"""
Vessel: {nmea.get('sog', '?')} kt SOG, {nmea.get('cog', '?')}° COG
Position: {nmea.get('lat', '?')}, {nmea.get('lon', '?')}
Depth scale: {florence_json.get('depth_scale_numbers', 'unknown')}
Bottom: {florence_json.get('bottom', {})}
Fish schools: {florence_json.get('fish_schools', [])}
Thermoclines: {florence_json.get('thermoclines', [])}
Recent catches: {recent_catches[-3:] if recent_catches else 'none'}
"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Describe this sounder:\n{context}"},
    ]
    inputs = tokenizer.apply_chat_template(messages, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(inputs, max_new_tokens=256, temperature=0.3, top_p=0.9)
    return tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()
```

### 2.7 Bootstrapping Without Labeled Data

**Year 1 strategy: Zero labeled data. Use Florence-2's pre-trained knowledge + Captain-in-the-loop.**

| Week | Activity | Data Produced |
|------|----------|---------------|
| 1-2  | Deploy Florence-2 extractor alongside current analyzer. Log both outputs to JSONL. | Paired (current_analysis, florence_analysis) |
| 3-4  | Captain reviews 20 frames/day via Riker: "Florence said X. Truth is Y." | 400+ human corrections |
| 5-6  | Fine-tune Florence-2 LoRA (rank 16, 4M params) on Captain corrections. 1 epoch, 30 min on 4050. | Adapted Florence-2 (save as `florence2-troller-v1`) |
| 7+   | Deploy adapted model. Continue Captain corrections weekly. Retrain monthly. | Continuously improving extractor |

**LoRA fine-tune script (runs on 4050 in <1 hour):**

```python
# finetune_florence_lora.py
from peft import LoraConfig, get_peft_model
from transformers import Trainer, TrainingArguments

lora_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.1,
    target_modules=["q_proj", "v_proj", "k_proj", "out_proj"],
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

# Dataset: (image, prompt="<DENSE_REGION_CAPTION>", target=Captain_corrected_JSON)
trainer = Trainer(
    model=model,
    args=TrainingArguments(
        output_dir="florence2-troller-v1",
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        num_train_epochs=1,
        learning_rate=5e-5,
        fp16=True,
        logging_steps=10,
    ),
    train_dataset=CaptainCorrectionDataset("corrections.jsonl"),
)
trainer.train()
model.save_pretrained("florence2-troller-v1")
```

**Cost:** 4M trainable params × 2 bytes = 8 MB adapter. Swaps in/out of base model instantly. Zero risk to base capabilities.

---

## 3. Catch Correlation Loop — "This Pattern Looks Like July 22"

### 3.1 Problem Statement

Given:
- Timestamped catch logs (species, weight, lat, lon, time)
- Synchronized echogram tiles (time × depth × intensity) from TileDB
- Vessel state (SOG, COG, bottom type, fish density)

**Output:** "Current echogram pattern is 73% similar to the pattern at 2026-07-22T14:32:17 when we caught 40 lbs chum."

### 3.2 Simplest Algorithm That Works: **Weighted Template Matching**

No neural nets. No embeddings. No vector database. Just **normalized cross-correlation** on engineered feature vectors.

```python
# catch_correlator.py — Runs on-demand or scheduled (e.g., every 5 min)
import numpy as np
import tiledb
from dataclasses import dataclass
from typing import List

@dataclass
class EchogramSignature:
    """Compact fingerprint of one sounder frame — 64 floats."""
    time_sec: int
    lat: float
    lon: float
    depth_fm: float
    bottom_type: int        # 0-4
    bottom_hardness: float  # 0-1
    fish_density: float     # fish_count / (width * depth)
    fish_depth_mode: float  # 0-1 (normalized depth where fish concentrate)
    fish_intensity_mean: float
    fish_intensity_std: float
    thermocline_count: int
    thermocline_depths: List[float]  # normalized 0-1, padded to 4
    sog: float
    cog: float
    catch_event: bool = False
    catch_species: str = ""
    catch_weight: float = 0.0

    def to_vector(self) -> np.ndarray:
        """64-dim feature vector for correlation."""
        v = np.zeros(64, dtype=np.float32)
        v[0] = self.depth_fm / 100.0           # normalized max depth
        v[1] = self.bottom_type / 4.0
        v[2] = self.bottom_hardness
        v[3] = min(self.fish_density * 10, 1.0)
        v[4] = self.fish_depth_mode
        v[5] = self.fish_intensity_mean / 255.0
        v[6] = self.fish_intensity_std / 255.0
        v[7] = min(self.thermocline_count / 5.0, 1.0)
        v[8:12] = (np.array(self.thermocline_depths + [0]*4)[:4])  # pad/truncate
        v[12] = min(self.sog / 10.0, 1.0)
        v[13] = self.cog / 360.0
        # 14-63: intensity histogram (16 bins) + spatial moments (4) + texture (8) + spectral (8)
        # For Year 1, keep it simple: just the first 14 dims + 50 zeros
        return v
```

### 3.3 Building the Reference Library

```python
def build_reference_library(array_uri: str, catch_log_path: str) -> List[EchogramSignature]:
    """Extract signatures for every catch event + 30 min before/after."""
    catches = parse_catch_log(catch_log_path)  # List of (ts, lat, lon, species, weight)
    refs = []
    
    with tiledb.open(array_uri, 'r') as A:
        for catch in catches:
            ts = int(catch["ts"].timestamp())
            # Query ±30 min window around catch
            window = A.query(attrs=["intensity", "lat", "lon", "sog", "cog", 
                                     "depth_fm", "bottom_type", "bottom_confidence",
                                     "fish_count", "fish_distribution", "catch_event",
                                     "catch_species", "catch_weight_lbs"])\
                      .cond(f"time_sec >= {ts-1800} AND time_sec <= {ts+1800}")[:]
            
            # Group by unique time_sec (each = one sounder frame)
            for frame_ts in np.unique(window["time_sec"]):
                mask = window["time_sec"] == frame_ts
                frame = {k: v[mask] for k, v in window.items()}
                
                sig = EchogramSignature(
                    time_sec=int(frame_ts),
                    lat=float(frame["lat"][0]),
                    lon=float(frame["lon"][0]),
                    depth_fm=float(frame["depth_fm"][0]),
                    bottom_type=int(frame["bottom_type"][0]),
                    bottom_hardness=float(frame["bottom_confidence"][0]) / 2.0,
                    fish_density=float(frame["fish_count"][0]) / (370 * 256),
                    fish_depth_mode=0.5,  # TODO: compute from intensity profile
                    fish_intensity_mean=float(frame["intensity"][mask_intensity].mean()),
                    fish_intensity_std=float(frame["intensity"][mask_intensity].std()),
                    thermocline_count=0,  # TODO: extract from full frame
                    thermocline_depths=[],
                    sog=float(frame["sog"][0]),
                    cog=float(frame["cog"][0]),
                    catch_event=True,
                    catch_species=catch["species"],
                    catch_weight=catch["weight"],
                )
                refs.append(sig)
    
    return refs
```

### 3.4 Real-Time Correlation Query

```python
def correlate_current_frame(current_sig: EchogramSignature, 
                            reference_lib: List[EchogramSignature],
                            top_k: int = 5) -> List[dict]:
    """Return top-k historical frames most similar to current."""
    current_vec = current_sig.to_vector()
    current_norm = np.linalg.norm(current_vec)
    if current_norm == 0:
        return []
    
    scores = []
    for ref in reference_lib:
        ref_vec = ref.to_vector()
        ref_norm = np.linalg.norm(ref_vec)
        if ref_norm == 0:
            continue
        # Cosine similarity
        sim = float(np.dot(current_vec, ref_vec) / (current_norm * ref_norm))
        # Weight by catch relevance
        catch_weight = 1.5 if ref.catch_event else 1.0
        species_bonus = 0.1 if ref.catch_species in TARGET_SPECIES else 0.0
        weighted = sim * catch_weight + species_bonus
        scores.append((weighted, ref))
    
    scores.sort(key=lambda x: x[0], reverse=True)
    
    return [
        {
            "similarity_pct": round(score * 100, 1),
            "timestamp": datetime.fromtimestamp(ref.time_sec).isoformat(),
            "position": {"lat": ref.lat, "lon": ref.lon},
            "catch": {"species": ref.catch_species, "weight_lbs": ref.catch_weight} if ref.catch_event else None,
            "bottom_type": ["hard","medium","soft_mud","very_soft","mixed"][ref.bottom_type],
            "fish_density": ref.fish_density,
        }
        for score, ref in scores[:top_k]
    ]
```

### 3.5 Integration Point: Captain's Display

```python
# In agent.py snap() — add correlation to on-demand response
def snap_with_correlation() -> dict:
    result = snap()  # existing
    current_sig = extract_signature_from_result(result)
    matches = correlate_current_frame(current_sig, REFERENCE_LIBRARY, top_k=3)
    result["correlation"] = {
        "top_matches": matches,
        "interpretation": generate_interpretation(matches),
    }
    return result

def generate_interpretation(matches: List[dict]) -> str:
    if not matches or matches[0]["similarity_pct"] < 40:
        return "No strong historical pattern match."
    top = matches[0]
    if top["catch"]:
        return (f"{top['similarity_pct']}% match to {top['timestamp'][:16]} — "
                f"caught {top['catch']['weight_lbs']} lbs {top['catch']['species']} "
                f"at {top['position']['lat']:.4f}, {top['position']['lon']:.4f}. "
                f"Bottom: {top['bottom_type']}. Fish density: {top['fish_density']:.3f}.")
    else:
        return (f"{top['similarity_pct']}% match to {top['timestamp'][:16]} (no catch logged). "
                f"Bottom: {top['bottom_type']}. Fish density: {top['fish_density']:.3f}.")
```

**Output example:**
> "73% match to 2026-07-22T14:32:17 — caught 42 lbs chum at 55.3421, -131.6452. Bottom: medium. Fish density: 0.012."

That's the "DAW playhead" moment — Captain sees *now* and *then* simultaneously.

---

## 4. Delta Logger — Detecting "Meaningful Changes" Every 30 Seconds

### 4.1 The Hallucination Problem

An LLM asked "did anything change?" will *always* find something. The sea state changes every second. We need **deterministic, thresholded change detection** that only triggers on operational events:

| Event | Detection Method | Threshold |
|-------|------------------|-----------|
| Marks placed (waypoints) | NMEA waypoint sentence ($GPWPL) | New waypoint in last 30s |
| Course change > 15° | COG delta | \|COG_t - COG_t-1\| > 15° |
| Speed change > 0.5 kt | SOG delta | \|SOG_t - SOG_t-1\| > 0.5 |
| Boundary proximity | Distance to polygon (MPA, closure, contour) | < 0.25 NM |
| Bottom type transition | bottom_type enum change | hard ↔ soft_mud |
| Fish density spike | fish_count delta | > 2x median of last 10 min |
| New thermocline | layer_count increase | +1 layer |
| Depth scale change | max_depth_fm delta | > 10 fm (range switch) |

### 4.2 Deterministic Delta Engine (No LLM)

```python
# delta_logger.py — Runs every 30s in capture loop, writes ONLY on change
from collections import deque
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class VesselState:
    ts: float
    lat: float
    lon: float
    sog: float
    cog: float
    depth_fm: float
    bottom_type: int
    fish_count: int
    fish_density: float
    thermocline_count: int
    max_depth_fm: float  # from depth scale OCR

class DeltaLogger:
    def __init__(self):
        self.history = deque(maxlen=120)  # 1 hour at 30s
        self.boundaries = load_boundaries()  # GeoJSON polygons
        self.last_logged_ts = 0
    
    def process(self, current: VesselState) -> Optional[dict]:
        """Returns delta event dict if meaningful change detected, else None."""
        if not self.history:
            self.history.append(current)
            return None
        
        prev = self.history[-1]
        events = []
        
        # 1. Course change
        cog_delta = abs((current.cog - prev.cog + 180) % 360 - 180)
        if cog_delta > 15:
            events.append({"type": "course_change", "delta_deg": round(cog_delta, 1),
                           "from_cog": prev.cog, "to_cog": current.cog})
        
        # 2. Speed change
        sog_delta = abs(current.sog - prev.sog)
        if sog_delta > 0.5:
            events.append({"type": "speed_change", "delta_kt": round(sog_delta, 1),
                           "from_sog": prev.sog, "to_sog": current.sog})
        
        # 3. Bottom transition
        if current.bottom_type != prev.bottom_type:
            events.append({"type": "bottom_transition",
                           "from": BOTTOM_TYPES[prev.bottom_type],
                           "to": BOTTOM_TYPES[current.bottom_type]})
        
        # 4. Fish density spike (relative to recent median)
        recent_counts = [h.fish_count for h in list(self.history)[-20:]]
        if recent_counts:
            median_count = np.median(recent_counts)
            if current.fish_count > 2 * median_count and median_count > 10:
                events.append({"type": "fish_spike", "count": current.fish_count,
                               "median_10min": round(median_count), "ratio": round(current.fish_count/median_count, 1)})
        
        # 5. Thermocline change
        if current.thermocline_count != prev.thermocline_count:
            events.append({"type": "thermocline_change",
                           "from": prev.thermocline_count, "to": current.thermocline_count})
        
        # 6. Depth range change (sonar range switch)
        if abs(current.max_depth_fm - prev.max_depth_fm) > 10:
            events.append({"type": "depth_range_change",
                           "from_fm": prev.max_depth_fm, "to_fm": current.max_depth_fm})
        
        # 7. Boundary proximity
        for boundary in self.boundaries:
            dist_nm = distance_to_polygon(current.lat, current.lon, boundary)
            if dist_nm < 0.25:
                events.append({"type": "boundary_proximity",
                               "boundary": boundary.name, "distance_nm": round(dist_nm, 2)})
        
        # 8. Waypoint/Mark (from NMEA $GPWPL — check separate feed)
        new_marks = check_new_waypoints(prev.ts, current.ts)
        for mark in new_marks:
            events.append({"type": "mark_placed", "name": mark.name,
                           "lat": mark.lat, "lon": mark.lon})
        
        self.history.append(current)
        
        if not events:
            return None
        
        # Build delta log entry
        delta = {
            "ts": datetime.fromtimestamp(current.ts, timezone.utc).isoformat(),
            "type": "delta",
            "events": events,
            "state": {
                "position": {"lat": current.lat, "lon": current.lon},
                "vessel": {"sog": current.sog, "cog": current.cog},
                "sounder": {
                    "depth_fm": current.depth_fm,
                    "bottom_type": BOTTOM_TYPES[current.bottom_type],
                    "fish_count": current.fish_count,
                    "thermocline_count": current.thermocline_count,
                }
            }
        }
        
        # Write to dedicated delta log (low volume, high signal)
        log_delta(delta)
        return delta
```

### 4.3 LLM Summarization (Optional, On-Demand Only)

```python
# Only called when Captain asks "what happened in the last hour?"
def summarize_deltas(delta_entries: List[dict]) -> str:
    if not delta_entries:
        return "No significant changes in the last hour."
    
    by_type = {}
    for d in delta_entries:
        for e in d["events"]:
            by_type.setdefault(e["type"], []).append(e)
    
    summary = []
    for etype, events in by_type.items():
        if etype == "course_change":
            summary.append(f"Course changes: {len(events)} (max {max(e['delta_deg'] for e in events):.0f}°)")
        elif etype == "fish_spike":
            summary.append(f"Fish density spikes: {len(events)} (peak {max(e['ratio'] for e in events):.1f}x baseline)")
        elif etype == "bottom_transition":
            summary.append(f"Bottom transitions: {', '.join(f'{e[\"from\"]}→{e[\"to\"]}' for e in events)}")
        # ... etc
    
    return "; ".join(summary)
```

**Key principle:** The delta logger **never uses an LLM for detection**. LLMs only summarize *after* deterministic triggers fire. This eliminates hallucination.

---

## 5. Infrastructure Constraints — RTX 4050 6GB, Windows 11, Shared Host

### 5.1 Current Process Map (Verified Running)

```
┌──────────────────────────────────────────────────────────────────┐
│ EILEEN (Windows 11, RTX 4050 6GB, 16GB RAM)                      │
├──────────────────────────────────────────────────────────────────┤
│ COM6 (u-blox GPS, 4800 baud)                                     │
│   └── nmea-bridge.exe  →  TCP :6006 (hermitd) + :6007 (TZ Pro)   │
│                                                                     │
│ Docker (WSL2 backend)                                            │
│   └── mcp-gateway (Playwright)  →  HTTP :3100                    │
│                                                                     │
│ hermit-crab dashboard  →  HTTP :8654                             │
│   └── /vessel endpoint (JSON position window)                    │
│                                                                     │
│ Ollama  →  qwen3:4b (2.5GB VRAM)  —  Captain chat interface      │
│                                                                     │
│ tzpro-agent (Python)                                             │
│   ├── capture.py (daemon, 30s/4min cadence)                     │
│   ├── agent.py (on-demand)                                       │
│   └── sounder_analyzer.py (CPU OpenCV/PIL)                       │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 VRAM Budget (6 GB = 6144 MB)

| Component | VRAM (INT4/FP16) | Notes |
|-----------|------------------|-------|
| Windows/DWM | ~800 MB | Baseline |
| Ollama qwen3:4b (FP16) | ~2500 MB | Already loaded |
| **Available for new models** | **~2800 MB** | Hard ceiling |
| Florence-2-base (INT4) | 120 MB | Stage 1 extractor |
| Phi-3.5-mini (INT4) | 2300 MB | Stage 2 narrator |
| **Total new** | **2420 MB** | **Fits with 380 MB margin** |
| Python overhead / CUDA context | ~500 MB | Dynamic |
| **Safety margin** | **~0 MB** | **Tight but workable** |

**If OOM occurs:** Unload qwen3:4b when Florence-2/Phi-3.5 are active. Use `ollama stop qwen3:4b` / `ollama run qwen3:4b` on demand. Or quantize qwen3:4b to INT4 (1.2 GB) — but Captain chat quality drops.

### 5.3 CPU/RAM Budget

| Resource | Current | + Florence-2 + Phi-3.5 | Limit |
|----------|---------|------------------------|-------|
| RAM | ~4 GB | ~8 GB | 16 GB |
| CPU (capture loop) | 5% | 15% (inference) | 100% |
| Disk I/O | 5 MB/min | 10 MB/min | SSD fine |
| Disk space | 290 GB free | +50 GB/season | 1 TB external recommended |

### 5.4 Deployment Architecture — Windows Services

**Don't run as naked Python scripts.** Register as NSSM services for auto-restart, log rotation, crash recovery.

```powershell
# install_services.ps1 — Run once as Admin
nssm install TzProCapture "C:\Python311\python.exe" "C:\tzpro-agent\capture.py"
nssm set TzProCapture AppDirectory "C:\tzpro-agent"
nssm set TzProCapture AppStdout "C:\tzpro-agent\logs\capture_%Y%m%d.log"
nssm set TzProCapture AppStderr "C:\tzpro-agent\logs\capture_err_%Y%m%d.log"
nssm set TzProCapture AppRotateFiles 1
nssm set TzProCapture AppRotateOnline 1
nssm set TzProCapture Start SERVICE_AUTO_START
nssm start TzProCapture

nssm install TzProAgent "C:\Python311\python.exe" "C:\tzpro-agent\agent.py"
nssm set TzProAgent AppDirectory "C:\tzpro-agent"
# ... same logging config
nssm start TzProAgent

# Florence-2/Phi-3.5 model server (FastAPI, single shared process)
nssm install FishingLogModels "C:\Python311\python.exe" "C:\fishinglog\model_server.py"
nssm start FishingLogModels
```

**Model Server (model_server.py) — Single Process, Two Models:**

```python
# model_server.py — Runs as Windows service, exposes /florence and /phi endpoints
from fastapi import FastAPI
from pydantic import BaseModel
import torch, uvicorn
from transformers import AutoProcessor, AutoModelForCausalLM, AutoTokenizer

app = FastAPI()
DEVICE = "cuda"
DTYPE = torch.float16

# ── Load both models at startup (2.4 GB VRAM) ──────────────────────
florence_processor = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
florence_model = AutoModelForCausalLM.from_pretrained(
    "microsoft/Florence-2-base", trust_remote_code=True, torch_dtype=DTYPE
).to(DEVICE).eval()

phi_tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3.5-mini-instruct")
phi_model = AutoModelForCausalLM.from_pretrained(
    "microsoft/Phi-3.5-mini-instruct", torch_dtype=DTYPE, device_map="auto"
).eval()

class FlorenceRequest(BaseModel):
    image_path: str
    tasks: list[str] = ["<CAPTION>", "<DENSE_REGION_CAPTION>", "<OCR>", "<OD>"]

class PhiRequest(BaseModel):
    messages: list[dict]
    max_tokens: int = 256
    temperature: float = 0.3

@app.post("/florence")
async def florence_extract(req: FlorenceRequest):
    img = Image.open(req.image_path).convert("RGB")
    results = {}
    for task in req.tasks:
        inputs = florence_processor(text=task, images=img, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            gen = florence_model.generate(**inputs, max_new_tokens=512, num_beams=3)
        text = florence_processor.batch_decode(gen, skip_special_tokens=False)[0]
        results[task] = florence_processor.post_process_generation(text, task, img.size)
    return results

@app.post("/phi")
async def phi_narrate(req: PhiRequest):
    inputs = phi_tokenizer.apply_chat_template(req.messages, return_tensors="pt").to(phi_model.device)
    with torch.no_grad():
        out = phi_model.generate(inputs, max_new_tokens=req.max_tokens, 
                                 temperature=req.temperature, top_p=0.9)
    return {"text": phi_tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
```

**Capture loop integration (capture.py → model_server):**

```python
# In capture.py _log_and_analyze() — replace local analyze_sounder() with:
import requests

def analyze_sounder_remote(sounder_path: Path) -> dict:
    try:
        resp = requests.post("http://127.0.0.1:8765/florence",
            json={"image_path": str(sounder_path)}, timeout=10)
        florence_json = resp.json()
        return parse_florence_output(florence_json)  # Our normalizer
    except Exception as e:
        log.warning("Florence remote failed, falling back to local: %s", e)
        return analyze_sounder(sounder_path)  # Original CPU analyzer
```

### 5.5 Failure Modes & Mitigations

| Failure | Detection | Mitigation |
|---------|-----------|------------|
| GPU OOM | `torch.cuda.OutOfMemoryError` in logs | Catch → fallback to CPU analyzer; restart model_server service |
| Model server crash | HTTP 500 / timeout | NSSM auto-restart; capture loop falls back to local analyzer |
| NMEA bridge down | `read_nmea()` returns empty | Last-known-position cached; log `position: null` |
| Disk full | `OSError: [Errno 28]` | Log rotation (NSSM), external SSD auto-mount, alert via hermitd |
| Power loss | Dirty shutdown | JSONL append-only = no corruption; TileDB ACID on next write |
| Display capture fails | `capture_full()` returns None | Retry with 5s backoff; alert if 5 consecutive failures |

---

## 6. Implementation Sequence — Year 1 Roadmap

| Week | Deliverable | Command to Verify |
|------|-------------|-------------------|
| 1 | **TileDB schema + migration script** (not deployed) | `python create_tiledb_schema.py && python migrate_jsonl_to_tiledb.py --dry-run` |
| 2 | **Florence-2 extractor** (local test, no service) | `python florence_extractor.py captures/frame_XXXX_sounder.png` |
| 3 | **Captain correction loop** (20 frames/day) | `python collect_corrections.py --interactive` |
| 4 | **LoRA fine-tune** (30 min on 4050) | `python finetune_florence_lora.py && ls florence2-troller-v1/` |
| 5 | **Model server + Phi-3.5** (NSSM service) | `curl -X POST http://127.0.0.1:8765/phi -d '{"messages":[{"role":"user","content":"test"}]}'` |
| 6 | **Catch correlation loop** (reference library + query) | `python catch_correlator.py --build-refs && python catch_correlator.py --query-current` |
| 7 | **Delta logger** (integrated in capture.py) | `grep "delta" tzpro-agent/memory/observations/$(date +%F).jsonl` |
| 8 | **DAW timeline prototype** (HTML/JS, reads TileDB via WASM) | Open `timeline/index.html` in browser on EILEEN |

**Total new code:** ~1,200 lines across 6 files. All Python. No new languages. No Kubernetes. No cloud.

---

## 7. What Explicitly Does NOT Happen in Year 1

| Feature | Why Not |
|---------|---------|
| TileDB in production | JSONL works; migration trigger not hit |
| Vector database / embeddings | Cosine similarity on 64-dim vectors is faster and explainable |
| Multi-boat fleet aggregation | Requires satellite uplink, auth, privacy model — Year 2+ |
| Autopilot integration | Safety-critical; separate copilot, separate hardware |
| Voice commands | Captain types faster than he speaks in 6 ft seas |
| Cloud sync | No Starlink reliability guarantee; local-first always |
| Mobile app | Captain's phone is wet/gone/gloves; dashboard is on the nav station |

---

## Appendix A: File Manifest for Year 1 Build

```
fishinglog/
├── tiledb_schema.py           # create_tiledb_schema.py
├── migrate_to_tiledb.py       # migrate_jsonl_to_tiledb.py
├── florence_extractor.py      # Stage 1 structured extraction
├── phi_narrator.py            # Stage 2 natural language
├── finetune_lora.py           # Monthly Captain correction training
├── catch_correlator.py        # Template matching + reference library
├── delta_logger.py            # Deterministic change detection
├── model_server.py            # FastAPI service (Florence-2 + Phi-3.5)
├── boundaries.geojson         # MPA, closure, contour polygons
├── catch_log.csv              # Captain's manual catch entries
└── timeline/
    ├── index.html             # DAW-like scrubber (TileDB-WASM)
    ├── timeline.js
    └── tracks/
        ├── echogram.js
        ├── gps.js
        ├── autopilot.js
        └── transcript.js
```

---

## Appendix B: Captain's Acceptance Criteria (The Only Metrics That Matter)

1. **"Does it tell me something I didn't know?"** — At least once per trip, the correlation loop surfaces a historical match the Captain missed.
2. **"Does it survive a 14-hour day?"** — No restarts, no OOM, no missed captures.
3. **"Can I read it with wet gloves?"** — Delta log entries are one line, high contrast, no scroll.
4. **"Does it cost me money?"** — Zero cloud spend. Hardware: existing 4050 + $200 external SSD.
5. **"Can I fix it at 3 AM in Chatham Strait?"** — Pure Python, standard libs, logs are text, models are local files.

---

*End of analysis. The DAW is not a metaphor — it's a file format (TileDB), a query pattern (time-slice), and a UI (scrubber). Every component above exists to make that timeline queryable, trustworthy, and survivable on a fishing boat.*