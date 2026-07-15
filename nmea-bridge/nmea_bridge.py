#!/usr/bin/env python3
"""
nmea_bridge.py — Scan all COM ports for NMEA, merge, broadcast over TCP.

Any app (TZ Pro, Nobeltec, OpenCPN, Hermit Crab, Signal K) connects
via TCP to receive all NMEA sentences from all detected sources.

Usage:
  python nmea_bridge.py                     # auto-detect + serve on 6006
  python nmea_bridge.py --baud 4800         # override baud for all ports
  python nmea_bridge.py --ports COM5,COM7   # specific ports only
  python nmea_bridge.py --tcp-port 6006     # TCP listen port
  python nmea_bridge.py --scan              # scan & show NMEA ports, exit
"""

from __future__ import annotations
import argparse, asyncio, logging, os, re, sys, time
from typing import Optional

log = logging.getLogger("nmea_bridge")

# ── Config ──────────────────────────────────────────────────────────
DEFAULT_TCP_PORT = 6006
DEFAULT_BAUD = 4800
SCAN_TIMEOUT = 3  # seconds to listen per port when scanning
NMEA_RE = re.compile(r"^\$[A-Z]{5,6},.*\*[0-9A-F]{2}$")
IS_WINDOWS = sys.platform == "win32"
# ────────────────────────────────────────────────────────────────────

_clients: set[asyncio.StreamWriter] = set()


# ══════════════════════════════════════════════════════════════════════
#  Port discovery
# ══════════════════════════════════════════════════════════════════════

def list_all_ports() -> list[dict]:
    """List all serial ports with metadata."""
    try:
        import serial.tools.list_ports
        return [{"device": p.device, "description": p.description, "hwid": p.hwid}
                for p in serial.tools.list_ports.comports()]
    except ImportError:
        return []


def scan_nmea_ports(baud: int = DEFAULT_BAUD, specific: list[str] | None = None) -> list[str]:
    """
    Probe serial ports for NMEA data.
    If *specific* is given, only probe those ports (bypass auto-scan).
    """
    import serial
    candidates: list[str] = specific or []
    if not candidates:
        import serial.tools.list_ports
        candidates = [p.device for p in serial.tools.list_ports.comports()
                      if p.device.startswith("COM")]
    found: list[str] = []
    for device in candidates:
        try:
            ser = serial.Serial(device, baud, timeout=SCAN_TIMEOUT)
            t0 = time.time()
            while time.time() - t0 < SCAN_TIMEOUT:
                line = ser.readline().decode("ascii", errors="replace").strip()
                if NMEA_RE.match(line):
                    log.info("NMEA detected on %s: %s", device, line[:60])
                    found.append(device)
                    break
            ser.close()
        except Exception:
            continue
    return found


# ══════════════════════════════════════════════════════════════════════
#  Serial reader (async)
# ══════════════════════════════════════════════════════════════════════

async def read_serial(device: str, baud: int) -> None:
    """Read NMEA from a serial port and broadcast to all TCP clients.

    Automatically reconnects if the device is disconnected and
    re-plugged (e.g., USB GPS temporarily unplugged).
    """
    import serial
    while True:
        try:
            ser = serial.Serial(device, baud, timeout=1)
            log.info("Opened %s (%d baud)", device, baud)
        except serial.SerialException as e:
            log.warning("Cannot open %s: %s — retrying in 5s", device, e)
            await asyncio.sleep(5)
            continue

        try:
            while True:
                line = await asyncio.to_thread(ser.readline)
                if not line:
                    continue
                text = line.decode("ascii", errors="replace").strip()
                if text and NMEA_RE.match(text):
                    _broadcast(text + "\r\n")
        except serial.SerialException as e:
            log.warning("Lost connection to %s: %s — reconnecting...", device, e)
        except Exception as e:
            log.error("Unexpected error on %s: %s", device, e)
        finally:
            try:
                ser.close()
            except Exception:
                pass

        await asyncio.sleep(5)


# ══════════════════════════════════════════════════════════════════════
#  TCP server
# ══════════════════════════════════════════════════════════════════════

def _broadcast(data: str) -> None:
    """Send *data* to every connected TCP client."""
    dead: list[asyncio.StreamWriter] = []
    for w in _clients:
        try:
            w.write(data.encode())
        except Exception:
            dead.append(w)
    for w in dead:
        _clients.discard(w)


async def handle_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Accept one TCP client (receive-only — they get NMEA pushed)."""
    addr = writer.get_extra_info("peername")
    log.info("Client connected: %s", addr)
    _clients.add(writer)
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                break
    except Exception:
        pass
    finally:
        log.info("Client disconnected: %s", addr)
        _clients.discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NMEA Bridge — multi-port serial aggregator & TCP splitter",
        allow_abbrev=False,  # prevent --port from silently matching --ports
    )
    p.add_argument(
        "--ports",
        help="COM ports to read, comma-sep (default: auto-scan all ports)",
    )
    p.add_argument(
        "--baud", type=int, default=DEFAULT_BAUD,
        help=f"Baud rate (default: {DEFAULT_BAUD})",
    )
    p.add_argument(
        "--tcp-port", type=int, default=DEFAULT_TCP_PORT,
        dest="tcp_port",
        help=f"TCP listen port (default: {DEFAULT_TCP_PORT})",
    )
    p.add_argument(
        "--scan", action="store_true",
        help="Scan for NMEA ports and exit",
    )
    p.add_argument(
        "--list-ports", action="store_true",
        dest="list_ports",
        help="List all serial ports and exit",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose (debug-level) logging",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_ports:
        ports = list_all_ports()
        if not ports:
            print("No serial ports found. Install pyserial if you haven't.")
            return
        header = f"{'Device':8s}  {'Description':<40s}  HWID"
        print(header)
        print("-" * len(header))
        for p in ports:
            print(f"{p['device']:8s}  {p['description']:<40s}  {p['hwid']}")
        return

    if args.scan:
        log.info("Scanning for NMEA ports at %d baud...", args.baud)
        if args.ports:
            port_list = [x.strip() for x in args.ports.split(",")]
        else:
            port_list = []
        found = scan_nmea_ports(args.baud, specific=port_list or None)
        if found:
            print(f"NMEA detected on: {', '.join(found)}")
        else:
            print("No NMEA ports detected.")
        return

    # ── Determine which ports to read ──────────────────────────────
    if args.ports:
        ports = [x.strip() for x in args.ports.split(",")]
    else:
        log.info("Auto-scanning for NMEA ports...")
        ports = scan_nmea_ports(args.baud)
        if not ports:
            log.warning("No NMEA ports auto-detected.")
            if IS_WINDOWS:
                avail = list_all_ports()
                if avail:
                    devs = ", ".join(p["device"] for p in avail)
                    log.warning("Available ports: %s. Try: --ports %s",
                                devs, avail[0]["device"])
                else:
                    log.warning("No serial ports found. Is your GPS plugged in?")
            else:
                log.warning("Try: python nmea_bridge.py --ports /dev/ttyUSB0")
            sys.exit(1)

    if not ports:
        log.error("No ports to read. Use --ports to specify or check connections.")
        sys.exit(1)

    log.info("Reading NMEA from: %s", ", ".join(ports))
    log.info("Broadcasting on TCP port %d", args.tcp_port)
    log.info("Connect apps to: localhost:%d", args.tcp_port)

    # ── Start TCP server FIRST (so we fail fast on port conflict) ──
    try:
        server = await asyncio.start_server(
            handle_client, "127.0.0.1", args.tcp_port
        )
    except OSError as e:
        log.error("Cannot bind to port %d: %s", args.tcp_port, e)
        log.error("Is another bridge instance already running?")
        sys.exit(1)

    # ── Start serial readers ───────────────────────────────────────
    tasks = [read_serial(p, args.baud) for p in ports]
    tasks.append(server.serve_forever())

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        server.close()
        log.info("Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
