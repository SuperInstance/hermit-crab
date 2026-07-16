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
#  Shared-mode serial reader (Windows) — coexists with TZ Pro/Nobeltec
# ══════════════════════════════════════════════════════════════════════

try:
    import ctypes, struct
    from ctypes import wintypes
    import serial
    _kernel32 = ctypes.windll.kernel32
    _GENERIC_READ = 0x80000000
    _FILE_SHARE_READ = 1
    _FILE_SHARE_WRITE = 2
    _OPEN_EXISTING = 3
    _INVALID_HANDLE = ctypes.c_void_p(-1)
    _kernel32.CreateFileA.argtypes = [wintypes.LPCSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    _kernel32.CreateFileA.restype = ctypes.c_void_p
    _kernel32 = ctypes.windll.kernel32

    class _DCB(ctypes.Structure):
        _fields_ = [
            ("DCBlength", wintypes.DWORD),
            ("BaudRate", wintypes.DWORD),
            ("fBinary", wintypes.DWORD, 1),
            ("fParity", wintypes.DWORD, 1),
            ("fOutxCtsFlow", wintypes.DWORD, 1),
            ("fOutxDsrFlow", wintypes.DWORD, 1),
            ("fDtrControl", wintypes.DWORD, 2),
            ("fDsrSensitivity", wintypes.DWORD, 1),
            ("fTXContinueOnXoff", wintypes.DWORD, 1),
            ("fOutX", wintypes.DWORD, 1),
            ("fInX", wintypes.DWORD, 1),
            ("fErrorChar", wintypes.DWORD, 1),
            ("fNull", wintypes.DWORD, 1),
            ("fRtsControl", wintypes.DWORD, 2),
            ("fAbortOnError", wintypes.DWORD, 1),
            ("fDummy2", wintypes.DWORD, 17),
            ("wReserved", wintypes.WORD),
            ("XonLim", wintypes.WORD),
            ("XoffLim", wintypes.WORD),
            ("ByteSize", wintypes.BYTE),
            ("Parity", wintypes.BYTE),
            ("StopBits", wintypes.BYTE),
            ("XonChar", ctypes.c_char),
            ("XoffChar", ctypes.c_char),
            ("ErrorChar", ctypes.c_char),
            ("EofChar", ctypes.c_char),
            ("EvtChar", ctypes.c_char),
            ("wReserved1", wintypes.WORD),
        ]

    class _COMMTIMEOUTS(ctypes.Structure):
        _fields_ = [
            ("ReadIntervalTimeout", wintypes.DWORD),
            ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
            ("ReadTotalTimeoutConstant", wintypes.DWORD),
            ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
            ("WriteTotalTimeoutConstant", wintypes.DWORD),
        ]

    _SHARED_MODE_OK = True
except Exception as e:
    log.warning("Shared-mode serial not available: %s", e)
    _SHARED_MODE_OK = False


class _SharedSerial:
    """Minimal shared-mode COM port reader compatible with the pyserial interface.

    Opens the port with FILE_SHARE_READ|FILE_SHARE_WRITE so TZ Pro / Nobeltec
    can simultaneously receive GPS data from the same COM port.
    """
    def __init__(self, device: str, baud: int = 4800, timeout: float = 1):
        self.device = device
        self._handle = None
        if not _SHARED_MODE_OK:
            raise RuntimeError("ctypes/kernel32 not available (not Windows?)")

        # Win32: CreateFile with share flags
        name = f"\\\\.\\{device}" if not device.startswith("\\\\.\\") else device
        h = _kernel32.CreateFileA(
            name.encode("ascii"),
            _GENERIC_READ,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            0,
            None,
        )
        if h is None or h == _INVALID_HANDLE or not h:
            err = ctypes.get_last_error()
            raise serial.SerialException(
                f"Cannot open {device} in shared mode (win32 error {err})"
            )
        self._handle = h

        # Read current DCB (TZ Pro already set it up)
        # If this fails, the port may already be in a good state — continue anyway
        try:
            dcb = _DCB()
            dcb.DCBlength = ctypes.sizeof(_DCB)
            _kernel32.GetCommState(self._handle, ctypes.byref(dcb))
        except Exception as e:
            log.warning("GetCommState: %s — continuing with default DCB", e)

        # Timeouts: 1000ms read interval timeout
        try:
            to = _COMMTIMEOUTS()
            to.ReadIntervalTimeout = 1000
            to.ReadTotalTimeoutMultiplier = 0
            to.ReadTotalTimeoutConstant = 1000
            _kernel32.SetCommTimeouts(self._handle, ctypes.byref(to))
        except Exception as e:
            log.warning("SetCommTimeouts: %s — continuing anyway", e)

        self._buf = ctypes.create_string_buffer(4096)
        self._rd = ctypes.c_uint32(0)
        self._acc = b""
        self.baud = baud
        log.info("Opened %s (%d baud, SHARED mode)", device, baud)

    def readline(self) -> bytes:
        """Read one line (blocking, with 1s timeout via CommTimeouts)."""
        while True:
            idx = self._acc.find(b"\n")
            if idx >= 0:
                line = self._acc[: idx + 1]
                self._acc = self._acc[idx + 1 :]
                return line
            r = _kernel32.ReadFile(
                self._handle, self._buf, 4096, ctypes.byref(self._rd), None
            )
            if r and self._rd.value:
                self._acc += self._buf.raw[: self._rd.value]
            else:
                # No data available within timeout — return whatever we have or empty
                if self._acc:
                    line = self._acc
                    self._acc = b""
                    if not line.endswith(b"\n"):
                        line += b"\n"
                    return line
                # Simulate b""
                return b""

    def close(self) -> None:
        if self._handle is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


async def read_serial(device: str, baud: int) -> None:
    """Read NMEA from a serial port and broadcast to all TCP clients.

    On Windows, opens in **shared mode** so TZ Pro / Nobeltec can also
    read the same COM port simultaneously.

    Automatically reconnects on disconnect / replug.
    """
    while True:
        ser = None
        try:
            # Try shared mode first (Windows) — lets TZ Pro coexist
            if IS_WINDOWS and _SHARED_MODE_OK:
                try:
                    ser = _SharedSerial(device, baud)
                except (serial.SerialException, RuntimeError):
                    log.warning("Shared-mode open failed, falling back to exclusive...")
                    ser = serial.Serial(device, baud, timeout=1)
            else:
                ser = serial.Serial(device, baud, timeout=1)

            log.info("Reading from %s (%d baud)", device, baud)
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
                if ser:
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
        help=f"Base TCP listen port (default: {DEFAULT_TCP_PORT})",
    )
    p.add_argument(
        "--num-ports", type=int, default=2,
        dest="num_ports",
        help="Number of TCP ports to serve (default: 2 — 6006, 6007)",
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

    ports_str = [str(args.tcp_port + i) for i in range(args.num_ports)]
    log.info("Reading NMEA from: %s", ", ".join(ports))
    log.info("Broadcasting on TCP ports: %s", ", ".join(ports_str))
    log.info("Connect apps to: localhost:%s", ", ".join(ports_str))

    # ── Start TCP servers FIRST (so we fail fast on port conflict) ──
    servers = []
    for i in range(args.num_ports):
        port = args.tcp_port + i
        try:
            server = await asyncio.start_server(
                handle_client, "127.0.0.1", port
            )
            servers.append(server)
        except OSError as e:
            log.error("Cannot bind to port %d: %s", port, e)
            log.error("Is another bridge instance already running?")

    if not servers:
        log.error("No TCP ports could be bound. Exiting.")
        sys.exit(1)

    # ── Start serial readers ───────────────────────────────────────
    tasks = [read_serial(p, args.baud) for p in ports]
    for s in servers:
        tasks.append(s.serve_forever())

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        for s in servers:
            s.close()
        log.info("Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
