# NMEA Bridge

**One TCP connection to rule all your marine instruments.**

Scan every serial port, find anything speaking NMEA 0183 — GPS, depth
sounder, AIS, wind, autopilot — merge it all into one clean TCP stream.
Any app on your network connects once and sees everything.

Born from a real problem on a fishing boat in Southeast Alaska: a USB GPS
on COM6 that two apps needed simultaneously. TZ Pro had it. Hermit Crab
couldn't get it. Kernel drivers failed (Secure Boot). Virtual COM ports
failed (driver signing). The solution turned out to be the simplest one:
just read the port and serve it over TCP.

That grew into this — a general-purpose NMEA aggregator for any vessel
with any instrument mix.

## The Problem

Marine electronics are a mess of one-to-one wiring:

- GPS receiver on COM6 → only one app at a time
- Depth sounder on COM5 → only one app at a time
- AIS receiver on COM7 → only one app at a time
- Quantum radar on USB → only one app at a time

If you want TZ Pro, Nobeltec, and a custom tracking script all reading
the same GPS, you need a splitter. Hardware splitters exist but cost
money and need power. Software splitters need kernel drivers that modern
Windows refuses to load (Secure Boot, driver signing).

This tool is the third option: **no hardware, no drivers, no cost.**

## What It Does

```
┌─────────┐     ┌──────────────┐     ┌──────────┐
│ COM6    │────▶│              │────▶│ TZ Pro   │
│ (GPS)   │     │              │     │ (:6006)  │
├─────────┤     │  nmea_bridge │     ├──────────┤
│ COM5    │────▶│  .py         │────▶│ Nobeltec │
│ (Depth)  │     │              │     │ (:6006)  │
├─────────┤     │  (merge +    │     ├──────────┤
│ COM7    │────▶│  broadcast)  │────▶│ OpenCPN  │
│ (AIS)   │     │              │     │ (:6006)  │
├─────────┤     │              │     ├──────────┤
│ COM8    │────▶│              │────▶│ Hermit   │
│ (Wind)  │     │              │     │ Crab     │
└─────────┘     └──────────────┘     └──────────┘
```

- **Auto-discovers** any COM port speaking NMEA 0183
- **Opens every port** — no limit on number of sources
- **Merges every sentence** into one combined TCP stream
- **Serves unlimited clients** — every connected app gets everything
- **Handles disconnects** — unplug a USB GPS, plug it back in, bridge
  reconnects automatically

## What It Doesn't Do

- No kernel drivers — pure Python, pure userspace
- No Windows registry changes — run it, kill it, zero footprint
- No virtual COM ports — no setup, no conflict, no Secure Boot problems
- No configuration files — either it finds your ports or you tell it
- No licensing — free, MIT, do what you want

## Quick Start

```bash
pip install pyserial
python nmea_bridge.py
```

That's it. Watch it find your instruments:

```
15:04:23 INFO  Scanning for NMEA ports at 4800 baud...
15:04:26 INFO  NMEA detected on COM6: $GPRMC,...
15:04:26 INFO  Reading NMEA from: COM6
15:04:26 INFO  Broadcasting on TCP port 6006
```

Now point any app at `localhost:6006`.

## Connecting Apps

| Application | How |
|-------------|-----|
| **TZ Pro** | Settings → GPS/NMEA → Add Source → Network (TCP) → `127.0.0.1:6006` |
| **Nobeltec** | Settings → NMEA Input → Add TCP → `127.0.0.1:6006` |
| **OpenCPN** | Options → NMEA Inputs → Add → Network → TCP `127.0.0.1:6006` |
| **Signal K** | NMEA 0183 Data Source → TCP `127.0.0.1:6006` |
| **Hermit Crab** | TCP `localhost:6006` (see `examples/hermit_crab_client.py`) |
| **Any script** | `nc localhost 6006` or raw TCP socket to `127.0.0.1:6006` |
| **Any device** | Bridge supports multiple TCP ports — use `--tcp-port` for dedicated ports per app |

Every client, regardless of protocol or application, gets **the exact same
merged stream** — every sentence from every instrument, in real time.

Because the bridge just speaks raw TCP (no RFC2217, no special framing),
literally anything that can open a socket can consume NMEA.

## Multi-Port Aggregation

Plug in multiple instruments. The bridge finds them all, reads them all,
merges everything into one stream:

```bash
python nmea_bridge.py
```

Auto-scan finds everything at the default baud. For mixed baud rates:

```bash
# Manual: GPS at 4800, AIS at 38400
python nmea_bridge.py --ports COM6,COM7 --baud 4800
python nmea_bridge.py --ports COM6,COM7 --baud 38400
```

Better yet: run multiple bridge instances on different TCP ports, one per
baud rate. Or write a short batch file that starts them all.

## Not Just NMEA

The same pattern works for **any serial data stream**, not just NMEA.
Need to split a serial debug console, a telemetry feed, or a GPS that
emits proprietary binary? The bridge doesn't care about sentence format —
it reads raw bytes and forwards them. Modify `NMEA_RE` or remove it
entirely:

```python
# Accept any non-empty line
NMEA_RE = re.compile(r".+")
```

The generalization is: **one producer, many consumers.** If you have a
serial device that one app monopolizes, put this bridge between them.

## Command Line Reference

```
usage: nmea_bridge.py [-h] [--ports PORTS] [--baud BAUD]
                      [--tcp-port TCP_PORT] [--scan] [--list]
                      [--verbose]

NMEA Bridge — multi-port aggregator & TCP splitter

options:
  --ports PORTS     COM ports to read, comma-sep (default: auto-scan)
  --baud BAUD       Baud rate (default: 4800)
  --tcp-port PORT   TCP listen port (default: 6006)
  --scan            Scan for NMEA ports and exit
  --list            List all serial ports and exit
  --verbose, -v     Verbose logging
```

## Running as a Service (Windows)

```powershell
# Background (survives terminal close)
Start-Process -NoNewWindow python -ArgumentList "nmea_bridge.py" `
    -WorkingDirectory "C:\path\to\nmea-bridge" `
    -RedirectStandardOutput "$env:TEMP\nmea_bridge.log" `
    -RedirectStandardError "$env:TEMP\nmea_bridge_err.log"
```

Or create a Windows Scheduled Task that runs on login. No admin
required (no drivers, no registry).

## Example NMEA Output

Every TCP client gets the full merged stream. You'll see sentences from
every connected instrument interleaved in real time:

```
$GPRMC,231542.00,A,5547.37839,N,13141.46882,W,1.808,254.01,140726,,,A*79
$SDDBT,024.4,f,007.4,M,004.0,F*22    ← depth sounder
$GPGGA,231542.00,5547.37839,N,13141.46882,W,1,12,0.65,8.2,M,-6.1,M,,*57
$WIMWV,045.0,R,12.5,N,A*2D            ← wind sensor
$GPGSV,4,1,15,01,36,298,32,02,62,280,36,03,05,264,30,08,29,232,40*76
$AIVDM,1,1,,A,13aEOK?P00PD,2*6D       ← AIS target
$GPGLL,5547.37839,N,13141.46882,W,231542.00,A,A*73
```

## Project Files

```
nmea-bridge/
├── nmea_bridge.py              # The bridge — one file, run it and go
├── requirements.txt            # pyserial (the only dependency)
├── README.md                   # This file
├── LICENSE                     # MIT — free for any use
├── examples/
│   └── hermit_crab_client.py   # Minimal TCP reader (copy-paste into your app)
└── tests/
    └── test_connection.py      # Health check: does the bridge work?
```

## The Backstory

This tool exists because of a specific moment on a boat in Ketchikan:

A USB GPS on COM6 was locked by TZ Pro. A companion agent (Hermit Crab)
needed the same GPS data. Virtual serial port drivers (com0com) were
installed, but Windows 11 with Secure Boot refused to load the unsigned
kernel driver. A signed version (3.0.0) was downloaded — same problem.
So was the next workaround, and the next.

The fix that finally worked was the simplest one: read the serial port
in Python, serve it over TCP, connect everything to that.

That pattern — **one serial producer, many TCP consumers** — applies to
every instrument on every boat. GPS, depth, AIS, wind, radar, autopilot:
they're all just serial ports. The bridge reads them all, merges them
all, and any app on the network consumes the combined stream.

No special hardware. No kernel drivers. No Windows settings. No
licensing. One file, one dependency, one command.

## License

MIT — do whatever you want with it. Use it on your boat, fork it,
embed it, sell it. Attribution appreciated but not required.
