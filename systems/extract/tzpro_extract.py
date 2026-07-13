#!/usr/bin/env python3
"""
tzpro_extract.py — TimeZero Professional data extraction tool.

Captures monitor 2 (or reads a provided PNG), crops the right-side data panel
of TimeZero Professional (dark theme, 1600x1200), runs Tesseract OCR with
dark-theme-optimized preprocessing, and parses the navigation fields into a
structured JSON document with confidence scoring and a capture timestamp.

Usage
-----
    # Live capture via the existing PowerShell capture script
    python tzpro_extract.py

    # Read from an existing PNG file
    python tzpro_extract.py --image tzpro_live.png

    # Pretty-print JSON to stdout (default), or write to file
    python tzpro_extract.py --image tzpro_live.png --out result.json

    # Quiet: only the JSON blob, no logging on stderr
    python tzpro_extract.py --image tzpro_live.png --quiet

Requirements
------------
    * Tesseract 5.x at C:\\Program Files\\Tesseract-OCR\\tesseract.exe
      (override with --tesseract or the TESSERACT_CMD env var)
    * Python packages: Pillow, pytesseract
    * Optional: PowerShell, for live capture (capture_monitor2.ps1)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

try:
    from PIL import Image, ImageOps, ImageFilter  # type: ignore
except ImportError:  # pragma: no cover
    sys.stderr.write("Pillow is required: pip install Pillow\n")
    raise

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover
    sys.stderr.write("pytesseract is required: pip install pytesseract\n")
    raise


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_TESSERACT = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)

# Default capture script that ships alongside this tool.
DEFAULT_CAPTURE_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "capture_monitor2.ps1"
)

# Where capture_monitor2.ps1 writes its PNG.
DEFAULT_CAPTURE_OUTPUT = os.path.join(os.environ.get("TEMP", "/tmp"), "tzpro_monitor2.png")

# Reference resolution. Crops below are defined relative to this; if the input
# image differs, crops are rescaled proportionally.
REF_W, REF_H = 1600, 1200


# ---------------------------------------------------------------------------
# Crop definitions
# ---------------------------------------------------------------------------
# Each entry: (x0, y0, x1, y1) in the reference 1600x1200 frame, plus the
# preferred PSM and an optional character whitelist. Coordinates were tuned
# against real TimeZero Professional screenshots (dark theme).

@dataclass(frozen=True)
class CropSpec:
    name: str
    box: tuple[int, int, int, int]  # (x0, y0, x1, y1) in ref frame
    psm: int = 6                    # Tesseract page-segmentation mode
    whitelist: Optional[str] = None
    scale: int = 4                  # upscaling factor for preprocessing


# Right-side data panel crops.
CROPS: dict[str, CropSpec] = {
    "time": CropSpec(
        "time",
        (1330, 60, 1480, 95),
        psm=7,
        whitelist="0123456789:APMapm ",
    ),
    "position": CropSpec(
        # Lat/Lon are on two adjacent lines; read them together with psm 6.
        # No whitelist — Tesseract needs the degree symbol in its alphabet,
        # and whitelisting it out corrupts the minute digits.
        "position",
        (1290, 295, 1600, 335),
        psm=6,
        whitelist=None,
    ),
    "bearing": CropSpec(
        # No whitelist — Tesseract needs to see the '---' no-data sentinel
        # verbatim. We detect it in the parser.
        "bearing",
        (1330, 405, 1600, 432),
        psm=7,
        whitelist=None,
    ),
    "range": CropSpec(
        "range",
        (1330, 430, 1600, 458),
        psm=7,
        whitelist=None,
    ),
    "ttc": CropSpec(
        "ttc",
        (1330, 455, 1600, 483),
        psm=7,
        whitelist=None,
    ),
    "depth": CropSpec(
        "depth",
        (1330, 480, 1600, 508),
        psm=7,
        whitelist=None,
    ),
    "sog": CropSpec(
        # SOG's small anti-aliased font is the hardest field; needs a slightly
        # taller crop and psm 7. No whitelist — restricting the alphabet makes
        # the 'kn' label bleed digits into the value. Repairs are applied
        # post-OCR in parse_sog().
        "sog",
        (1330, 500, 1600, 540),
        psm=7,
        whitelist=None,
    ),
    "tide_height": CropSpec(
        # Multi-line block: "Tide Height -2.29 ft". psm 6 reads the whole line.
        "tide_height",
        (1320, 710, 1600, 750),
        psm=6,
        whitelist="-0123456789.ft TideHeight",
    ),
    "next_tide": CropSpec(
        "next_tide",
        (1340, 785, 1600, 815),
        psm=7,
        whitelist="0123456789:APMapm NextTideTime ",
    ),
    "scale": CropSpec(
        # Chart scale read from the top-of-panel area.
        "scale",
        (1340, 150, 1560, 195),
        psm=6,
        whitelist="0123456789.\u00b0m ",
    ),
    "date": CropSpec(
        # Multi-line footer; psm 6 captures "7:23 AM / 7/13/2026" and we pick
        # the date-looking token out in the parser.
        "date",
        (1300, 1150, 1600, 1195),
        psm=6,
        whitelist="0123456789-/AM: APMapm",
    ),
}


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass
class Field:
    """A single extracted field."""
    raw: str
    value: Any
    unit: Optional[str]
    confidence: str  # "HIGH" | "MEDIUM" | "LOW" | "NONE"


@dataclass
class TzProResult:
    capture_timestamp: str
    source: str
    image_size: list[int]
    fields: dict[str, Any] = field(default_factory=dict)
    raw_ocr: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

def _ensure_tesseract(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Tesseract binary not found at: {path}\n"
            "Set --tesseract or the TESSERACT_CMD environment variable."
        )
    pytesseract.pytesseract.tesseract_cmd = path


def _scale_box(
    box: tuple[int, int, int, int], w: int, h: int
) -> tuple[int, int, int, int]:
    """Rescale a reference-frame box to the actual image dimensions."""
    x0, y0, x1, y1 = box
    sx, sy = w / REF_W, h / REF_H
    return (
        max(0, int(x0 * sx)),
        max(0, int(y0 * sy)),
        min(w, int(x1 * sx)),
        min(h, int(y1 * sy)),
    )


def _preprocess(crop: "Image.Image", scale: int = 4) -> "Image.Image":
    """
    Prepare a crop for Tesseract on a dark theme.

    Strategy:
      * Convert to grayscale.
      * Auto-contrast to stretch the (dark background / bright text) range.
      * Upscale for small fonts.
      * Light sharpening to recover anti-aliased edges.
    """
    g = crop.convert("L")
    g = ImageOps.autocontrast(g, cutoff=2)
    if scale > 1:
        g = g.resize((g.width * scale, g.height * scale), Image.LANCZOS)
    # Sharpen to reduce anti-aliasing blur (helps a lot with SOG-style values).
    g = g.filter(ImageFilter.SHARPEN)
    return g


def _ocr_crop(
    img: "Image.Image", spec: CropSpec
) -> str:
    """Run Tesseract on a single crop with the spec's settings."""
    crop = img.crop(spec.box)
    pre = _preprocess(crop, scale=spec.scale)
    cfg_parts = [f"--psm {spec.psm}"]
    if spec.whitelist:
        # Escape characters for the Tessedit config syntax.
        wl = spec.whitelist.replace("\\", "\\\\").replace(" ", "\\ ")
        cfg_parts.append(f"-c tessedit_char_whitelist={wl}")
    config = " ".join(cfg_parts)
    try:
        text = pytesseract.image_to_string(pre, config=config)
    except pytesseract.TesseractError as exc:  # pragma: no cover
        logging.warning("Tesseract error on %s: %s", spec.name, exc)
        return ""
    return text.strip()


# ---------------------------------------------------------------------------
# Field parsers
# ---------------------------------------------------------------------------

# TimeZero renders unavailable numeric fields as '---'; the labeled-number
# parser treats three-or-more consecutive dashes as the no-data sentinel.


def _conf(high: bool, medium: bool = False) -> str:
    if high:
        return "HIGH"
    if medium:
        return "MEDIUM"
    return "LOW"


def _clean(s: str) -> str:
    """Normalize whitespace and drop common OCR garbage characters."""
    if not s:
        return ""
    s = s.replace("\u00b0", " ").replace("\ufffd", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_time(text: str) -> Field:
    raw = _clean(text)
    m = re.search(r"\b(\d{1,2}:\d{2})\s*([AP]M)", raw, re.IGNORECASE)
    if m:
        val = f"{m.group(1)} {m.group(2).upper()}"
        return Field(raw=raw, value=val, unit=None, confidence=_conf(True))
    return Field(raw=raw, value=None, unit=None, confidence="NONE")


def parse_date(text: str) -> Field:
    raw = _clean(text)
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", raw)
    if m:
        val = m.group(1)
        # Normalize to ISO-ish if possible.
        try:
            dt = _dt.datetime.strptime(val, "%m/%d/%Y")
            iso = dt.strftime("%Y-%m-%d")
            return Field(raw=raw, value=iso, unit=None, confidence=_conf(True))
        except ValueError:
            return Field(raw=raw, value=val, unit=None, confidence="MEDIUM")
    return Field(raw=raw, value=None, unit=None, confidence="NONE")


# Matches a coordinate like "N 55 47.250'" tolerating a missing/garbled degree
# symbol. We require the hemisphere letter and the trailing minute decimal.
# Tesseract frequently OCRs the Unicode degree symbol (\u00b0) as a stray digit
# ("9"), an asterisk, the replacement char (\ufffd), or whitespace — all of
# those are accepted as the separator between degrees and minutes.
_COORD_RE = re.compile(
    r"(?P<hem>[NSEW])\s*"
    r"(?P<deg>\d{1,3})\s*"
    r"[\u00b0\u2218\u00ba*\u2018\u2019'`.\ufffd\s]?\s*"
    r"(?P<min>\d{1,2}(?:[.\u2018\u2019'`]\d+)?)"
)


def parse_position(text: str) -> dict[str, Field]:
    """Parse the combined lat/lon block into two fields."""
    raw = _clean(text)
    out: dict[str, Field] = {}
    matches = list(_COORD_RE.finditer(raw))

    lat = lon = None
    for m in matches:
        hem = m.group("hem").upper()
        try:
            deg = int(m.group("deg"))
            # Normalize odd minute punctuation (smart quotes etc.) to a dot.
            minute_str = re.sub(r"[^\d]", ".", m.group("min"))
            minute = float(minute_str)
        except ValueError:
            continue
        # Reject absurd minutes (e.g. when OCR glued "947" together).
        if minute >= 60:
            continue
        decimal = deg + minute / 60.0
        # Apply hemisphere sign: West and South are negative.
        signed = -decimal if hem in ("W", "S") else decimal
        if hem in ("N", "S"):
            if 0 <= deg <= 90:
                lat = Field(
                    raw=m.group(0),
                    value=round(signed, 6),
                    unit=hem,
                    confidence=_conf(True),
                )
        elif hem in ("E", "W"):
            if 0 <= deg <= 180:
                lon = Field(
                    raw=m.group(0),
                    value=round(signed, 6),
                    unit=hem,
                    confidence=_conf(True),
                )

    out["latitude"] = lat or Field(raw=raw, value=None, unit=None, confidence="NONE")
    out["longitude"] = lon or Field(raw=raw, value=None, unit=None, confidence="NONE")
    return out


def _parse_labeled_number(
    text: str,
    unit: str,
    value_range: Optional[tuple[float, float]] = None,
    allow_negative: bool = False,
    extra_units: tuple[str, ...] = (),
    max_decimals: Optional[int] = None,
    trust_without_unit: bool = False,
) -> Field:
    """
    Generic parser for a labeled numeric field. Handles the TimeZero 'no data'
    sentinel '---' gracefully. Tries multiple strategies to recover numbers
    from OCR-noisy text.

    When *unit* is non-empty and present in the text, the parser prefers a
    number that appears immediately before the unit token (e.g. '-2.29' in
    'Tide Height -2.29 ft'). This defeats spurious numbers elsewhere in the
    crop (timestamps, neighboring labels).
    """
    raw = _clean(text)

    # Honor the 'no data' sentinel anywhere in the OCR'd line. TimeZero shows
    # three or more dashes when a value is unavailable. Under OCR the dashes
    # frequently corrupt into underscores or equals signs, so accept any run of
    # three or more of those characters as the sentinel.
    if re.search(r"[\-_=]{3,}", raw):
        return Field(raw=raw, value=None, unit=unit, confidence="NONE")
    if not raw:
        return Field(raw=raw, value=None, unit=unit, confidence="NONE")

    sign = r"(-?)" if allow_negative else r"(\+?-?)"
    # Allow up to 3 decimal places by default; tighten via max_decimals.
    dec = max_decimals if max_decimals is not None else 3
    pat = re.compile(sign + r"\s*(\d{1,4}\.\d{1,%d}|\d{1,4})" % dec)

    # Strategy A: a number immediately preceding the unit token.
    chosen: Optional[float] = None
    if unit:
        # Build a tolerant unit matcher (e.g. '\u00b0M', 'ft', 'NM', 'kn').
        unit_pat = re.compile(
            r"(-?\s*\d{1,4}(?:\.\d{1,%d})?)\s*%s" % (dec, re.escape(unit)),
            re.IGNORECASE,
        )
        m = unit_pat.search(raw)
        if m:
            try:
                v = float(m.group(1).replace(" ", ""))
                if value_range is None or value_range[0] <= v <= value_range[1]:
                    chosen = v
            except ValueError:
                pass

    # Strategy B: any plausible float, preferring the one closest to the unit.
    # This is a fallback for noisy OCR; downgrade confidence unless the unit
    # token was actually present (Strategy A would have caught it then).
    unit_present = bool(unit) and bool(
        re.search(re.escape(unit), raw, re.IGNORECASE)
    )
    if chosen is None:
        candidates: list[float] = []
        for sm in pat.finditer(raw):
            try:
                v = float(sm.group(0).replace(" ", ""))
            except ValueError:
                continue
            if value_range and not (value_range[0] <= v <= value_range[1]):
                continue
            candidates.append(v)
        if candidates:
            chosen = candidates[0]

    if chosen is not None:
        # HIGH only when the unit token anchored the match (Strategy A). A
        # Strategy B value is a guess from a noisy crop — report it but mark
        # the confidence LOW so callers know not to trust it. SOG (and any
        # field with trust_without_unit=True) is an exception: its crop is
        # tightly bounded and its value format is unambiguous, so a clean
        # in-range number is trustworthy even without the unit label.
        if unit_present:
            conf = _conf(True)
        elif trust_without_unit:
            conf = _conf(True)
        else:
            conf = "LOW"
        return Field(raw=raw, value=chosen, unit=unit, confidence=conf)

    return Field(raw=raw, value=None, unit=unit, confidence="LOW")


def parse_sog(text: str) -> Field:
    raw = _clean(text)
    # SOG frequently OCRs as e.g. "1.5", "1.4.", "1.510", "1,5". Repair common
    # corruption before handing off to the generic parser.
    repaired = raw
    # Strip a trailing junk period after digits ("1.4." -> "1.4").
    repaired = re.sub(r"(\d\.\d)\.+", r"\1", repaired)
    # A spurious extra digit appended to a 2-decimal value ("1.510" -> "1.51").
    repaired = re.sub(r"(\d\.\d{2})\d+", r"\1", repaired)
    # Comma decimal separators.
    repaired = repaired.replace(",", ".")
    # SOG is realistically 0.0–99.9 kn and TimeZero renders it with ONE decimal
    # place. Capping at 1 decimal also discards the stray digit that the 'kn'
    # label contributes under OCR.
    return _parse_labeled_number(
        repaired,
        unit="kn",
        value_range=(0.0, 99.9),
        max_decimals=1,
        trust_without_unit=True,
    )


def parse_depth(text: str) -> Field:
    return _parse_labeled_number(text, unit="fm", value_range=(0.0, 99999.0))


def parse_bearing(text: str) -> Field:
    return _parse_labeled_number(text, unit="\u00b0M", value_range=(0.0, 360.0))


def parse_range(text: str) -> Field:
    return _parse_labeled_number(text, unit="NM", value_range=(0.0, 99999.0))


def parse_tide_height(text: str) -> Field:
    # Tide height OCR often contains junk like "2 723\nt -2.29ft" where stray
    # numbers ("2", "723", etc.) are chart annotations or clutter near the
    # tide graph. The real tide value is the number with a decimal point that
    # is nearest to the "ft" unit token.
    raw = _clean(text)
    # Find any decimal number adjacent to "ft", with optional sign.
    m = re.search(r"(-?\s*\d+\.\d+)\s*ft", raw, re.IGNORECASE)
    if m:
        val_str = re.sub(r"\s+", "", m.group(1))
        try:
            v = float(val_str)
            if -50.0 <= v <= 50.0:
                return Field(raw=raw, value=v, unit="ft", confidence=_conf(True))
        except ValueError:
            pass
    # Fall through to generic parser.
    return _parse_labeled_number(
        raw, unit="ft", value_range=(-50.0, 50.0),
        allow_negative=True, max_decimals=3,
    )


def parse_next_tide(text: str) -> Field:
    raw = _clean(text)
    m = re.search(r"(\d{1,2}:\d{2})\s*([AP]M)", raw, re.IGNORECASE)
    if m:
        return Field(
            raw=raw,
            value=f"{m.group(1)} {m.group(2).upper()}",
            unit=None,
            confidence=_conf(True),
        )
    return Field(raw=raw, value=None, unit=None, confidence="NONE")


def parse_scale(text: str) -> Field:
    raw = _clean(text)
    m = re.search(r"(\d{1,6}(?:\.\d+)?)", raw)
    if m:
        try:
            v = float(m.group(1))
            return Field(raw=raw, value=v, unit="x", confidence=_conf(True))
        except ValueError:
            pass
    return Field(raw=raw, value=None, unit="x", confidence="NONE")


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def capture_via_powershell(script_path: str, log: logging.Logger) -> str:
    """Invoke capture_monitor2.ps1 and return the produced PNG path."""
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Capture script not found: {script_path}")

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise RuntimeError(
            "PowerShell is required for live capture but was not found on PATH."
        )

    log.info("Capturing monitor 2 via %s", script_path)
    cmd = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", script_path,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30, check=False
    )
    log.debug("capture stdout: %s", proc.stdout.strip())
    if proc.returncode != 0:
        log.error("capture stderr: %s", proc.stderr.strip())
        raise RuntimeError(f"Capture failed (exit {proc.returncode}): {proc.stderr}")

    # Parse the "Saved to: <path>" line from the script output.
    m = re.search(r"Saved to:\s*(.+)", proc.stdout)
    path = m.group(1).strip() if m else DEFAULT_CAPTURE_OUTPUT
    if not os.path.isfile(path):
        raise RuntimeError(f"Capture reported success but file missing: {path}")
    return path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def extract(
    image_path: str,
    tesseract_cmd: str = DEFAULT_TESSERACT,
    log: Optional[logging.Logger] = None,
) -> TzProResult:
    """Run the full extraction pipeline against a single PNG."""
    log = log or logging.getLogger("tzpro_extract")

    _ensure_tesseract(tesseract_cmd)
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)

    log.info("Opening image: %s", image_path)
    img = Image.open(image_path)
    img.load()
    w, h = img.size
    log.info("Image size: %dx%d", w, h)

    # Re-scale crop boxes to actual image dimensions.
    scaled_crops: dict[str, CropSpec] = {}
    for name, spec in CROPS.items():
        scaled = CropSpec(
            name=spec.name,
            box=_scale_box(spec.box, w, h),
            psm=spec.psm,
            whitelist=spec.whitelist,
            scale=spec.scale,
        )
        scaled_crops[name] = scaled

    raw_ocr: dict[str, str] = {}
    for name, spec in scaled_crops.items():
        raw_ocr[name] = _ocr_crop(img, spec)
        log.debug("OCR[%s] = %r", name, raw_ocr[name])

    fields: dict[str, Any] = {}

    fields["time"] = parse_time(raw_ocr["time"]).__dict__
    fields["date"] = parse_date(raw_ocr["date"]).__dict__

    pos = parse_position(raw_ocr["position"])
    fields["latitude"] = pos["latitude"].__dict__
    fields["longitude"] = pos["longitude"].__dict__

    fields["bearing"] = parse_bearing(raw_ocr["bearing"]).__dict__
    fields["range"] = parse_range(raw_ocr["range"]).__dict__
    fields["depth"] = parse_depth(raw_ocr["depth"]).__dict__
    fields["sog"] = parse_sog(raw_ocr["sog"]).__dict__
    fields["tide_height"] = parse_tide_height(raw_ocr["tide_height"]).__dict__
    fields["next_tide_time"] = parse_next_tide(raw_ocr["next_tide"]).__dict__
    fields["chart_scale"] = parse_scale(raw_ocr["scale"]).__dict__

    result = TzProResult(
        capture_timestamp=_dt.datetime.now().isoformat(timespec="seconds"),
        source=os.path.abspath(image_path),
        image_size=[w, h],
        fields=fields,
        raw_ocr=raw_ocr,
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_logger(quiet: bool) -> logging.Logger:
    log = logging.getLogger("tzpro_extract")
    log.setLevel(logging.DEBUG if os.environ.get("TZPRO_DEBUG") else logging.INFO)
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    if quiet:
        log.setLevel(logging.WARNING)
    return log


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Extract navigation data from TimeZero Professional on monitor 2."
    )
    p.add_argument(
        "--image", "-i",
        help="Path to a PNG screenshot. If omitted, capture monitor 2 live.",
    )
    p.add_argument(
        "--capture-script",
        default=DEFAULT_CAPTURE_SCRIPT,
        help="Path to capture_monitor2.ps1 (used when --image is omitted).",
    )
    p.add_argument(
        "--tesseract",
        default=DEFAULT_TESSERACT,
        help="Path to tesseract.exe.",
    )
    p.add_argument(
        "--out", "-o",
        help="Write JSON to this file (default: stdout).",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress informational logging.",
    )
    p.add_argument(
        "--indent", type=int, default=2,
        help="JSON indent level (default 2).",
    )
    args = p.parse_args(argv)

    log = _build_logger(args.quiet)

    try:
        if args.image:
            image_path = args.image
        else:
            image_path = capture_via_powershell(args.capture_script, log)

        result = extract(
            image_path=image_path,
            tesseract_cmd=args.tesseract,
            log=log,
        )

        payload = json.dumps(result.to_dict(), indent=args.indent, ensure_ascii=False)

        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload)
            log.info("Wrote %s", args.out)
        else:
            sys.stdout.write(payload + "\n")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("Extraction failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
