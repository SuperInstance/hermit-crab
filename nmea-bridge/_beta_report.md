# NMEA Bridge — Beta Test Report

**Tester:** Simulated fresh-discovery from GitHub  
**Date:** 2026-07-14  
**Environment:** Windows 11 10.0.26200, Python 3.14.3, pyserial 3.5  
**Hardware:** u-blox USB GPS on COM6 (USB VID:PID=1546:01A7)

---

## Executive Summary

The tool works great at its core mission. The auto-detect, NMEA scanning, TCP broadcasting, and multi-client support all functioned correctly on the first try — exactly as the README promises. However, several documentation inaccuracies, a dangerous argparse footgun, and misleading log messages need fixing before a v1 release.

**Overall impression:** The bridge does what it says, and does it well. But the README doesn't match reality in a few places, and a new user could easily be misled into breaking their setup.

---

## 1. What Worked Immediately (The Good)

### ✅ `pip install pyserial`
Clean, one command. Already installed, no issues.

### ✅ `python nmea_bridge.py --list`
Output:
```
COM6      USB Serial Device (COM6)                  USB VID:PID=1546:01A7 SER= LOCATION=1-1.3
```
Found the GPS perfectly. Device, description, and HWID all present.

### ✅ `python nmea_bridge.py --scan`
Output:
```
15:23:23 INFO nmea_bridge Scanning for NMEA ports at 4800 baud...
15:23:23 INFO nmea_bridge NMEA detected on COM6: $GPRMC,...
NMEA detected on: COM6
```
Detected NMEA within ~3 seconds. The detected sentence is logged into the first 50 chars — useful for debug.

### ✅ `python nmea_bridge.py` (no arguments)
Full auto-detect mode. Output:
```
15:23:27 INFO nmea_bridge Auto-scanning for NMEA ports...
15:23:27 INFO nmea_bridge NMEA detected on COM6: $GPRMC,...
15:23:27 INFO nmea_bridge Reading NMEA from: COM6
15:23:27 INFO nmea_bridge Broadcasting on TCP port 6006
15:23:27 INFO nmea_bridge Connect apps to: localhost:6006
15:23:27 INFO nmea_bridge Opened COM6 (4800 baud)
```
All went well. The bridge scanned, found the port, opened it, and started serving.

### ✅ `python tests/test_connection.py`
```
Connected to 127.0.0.1:6006
Received 81 NMEA sentences in 8.6s
PASS: Bridge is healthy
```
Health check works perfectly. Sensible timeout (8 seconds), clear pass/fail output.

### ✅ `python examples/hermit_crab_client.py`
Connected immediately and streamed live NMEA to stdout. Received $GPGGA, $GPGSA, $GPGSV, $GPGLL, $GPRMC, $GPVTG sentences in real time.

### ✅ Two simultaneous clients
Both test scripts ran in parallel — each received 81+ sentences and both reported PASS. Multi-client broadcasting works correctly.

### ✅ `--ports COM6` (manual port specification)
Overrides auto-scan, opens exactly the ports specified. Works correctly.

### ✅ `--tcp-port 6007`
Changed the TCP listening port from 6006 to 6007. Clients connecting to 6007 received the full stream.

### ✅ `--verbose` / `-v`
Enabled debug-level logging. Showed additional detail from serial operations.

### ✅ `--baud 38400 --scan`
Scanned at non-default baud rate. Detected NMEA successfully (the u-blox GPS appears to speak at multiple rates).

---

## 2. What Was Confusing or Broken

### 🔴 CRITICAL: `--port` (singular) in README is a dangerous footgun

The README says:

```bash
python nmea_bridge.py --port 6006         # TCP port
```

**This does NOT set the TCP port.** Because argparse allows abbreviation (default `allow_abbrev=True`), `--port` is silently treated as an abbreviation for `--ports`. So `--port 6006` actually means `--ports 6006` — it tries to open a serial device literally named `6006`.

**What happens:**
```
Reading NMEA from: 6006
Broadcasting on TCP port 6006
```
The bridge starts up, tries to open COM port "6006", fails with "The system cannot find the file specified", and retries every 5 seconds forever. The user thinks everything is fine because the log says "Broadcasting on TCP port 6006," but the serial reader is failing silently in a retry loop.

**Fix needed:** Either:
1. Rename the README example to use `--tcp-port 6006`, or
2. Add `allow_abbrev=False` to the argparse constructor, or
3. Add a `--port` alias in argparse that maps to `--tcp-port`

### 🟡 "Spare TCP port" messages are misleading

The bridge logs at startup:
```
Spare TCP port: 6007 (localhost:6007)
Spare TCP port: 6008 (localhost:6008)
Spare TCP port: 6009 (localhost:6009)
```

But **these ports are not actually listening**. Connecting to port 6007 gives `ConnectionRefusedError: [WinError 10061]`.

The README says: *"Bridge supports multiple TCP ports — use `--tcp-port` for dedicated ports per app"* — but this suggests you launch separate bridge instances, not that spare ports are magically available.

**Fix needed:** Either:
1. Remove the spare port log messages entirely (they're noise), or
2. Actually open those ports (with a shared broadcast), or
3. Change the wording: "To run additional ports, launch another bridge instance with `--tcp-port 6007`"

### 🟡 `--scan` ignores `--ports`

Passing `--ports COM6 --scan` still scans ALL COM ports. If a user wants to scan only specific ports they've identified, there's no way to do that.

The README documents `--scan` as "Scan for NMEA ports and exit" but doesn't mention that `--ports` is ignored during scan.

**Fix:** Either have `--ports` filter the scan, or document that `--ports` doesn't apply during `--scan`.

### 🟡 Graceful shutdown on port conflict is broken

When the TCP port is already in use (e.g., another bridge instance on 6006):
```
OSError: [Errno 10048] only one usage of each socket address
RuntimeWarning: coroutine 'read_serial' was never awaited
```

The serial reader coroutines are spawned before the TCP server starts, so on bind failure they're leaked as abandoned coroutines. The script crashes with a traceback instead of a clean error message.

**Fix:** Start the TCP server before spawning serial readers, or catch the bind error and cancel pending tasks properly.

### 🟡 No explicit non-Windows documentation

The README focuses heavily on Windows (COM ports, PowerShell services, Windows Scheduled Task). A first-time Linux/macOS user would need to guess that:
- `COM6` → `/dev/ttyUSB0`
- PowerShell → `systemd` or `screen`
- There's no mention of the `--baud` needed for Linux RS232 (typically 4800)

**Fix:** Add a brief note like: *"On Linux, replace COM6 with /dev/ttyUSB0; on macOS, /dev/tty.usbserial-*."*

### 🟡 No troubleshooting section

If `python nmea_bridge.py` produces no output or no ports are found, the new user has no guidance. Common issues:
- Permissions on serial port (Linux needs dialout group)
- Wrong baud rate
- Firewall blocking TCP port
- Device not actually sending NMEA

**Fix:** Add a short "Nothing Works?" section.

### 🟡 Example client doesn't handle disconnection

`hermit_crab_client.py` exits immediately if the bridge disconnects or isn't running. For a background monitoring app, auto-reconnect would be the expected behavior.

**Fix:** Wrap the connection in a `while True:` retry loop with a few seconds delay.

### 🟡 Runtime behavior of `--list` with `--ports`

This worked fine, but the README doesn't show the format output clearly. The `--list` output is:
```
COM6      USB Serial Device (COM6)                  USB VID:PID=1546:01A7 SER= LOCATION=1-1.3
```
This is just the raw print from `list_all_ports()`. The formatting for the second column (description) uses `:<40s` padding, which works for most devices but could misalign for very long descriptions.

---

## 3. Minor Observations

### ✅ NMEA_RE regex
The regex `^\$[A-Z]{5,6},.*\*[0-9A-F]{2}$` correctly matched all GPS sentences (GPGGA, GPRMC, GPGSA, GPGSV, GPGLL, GPVTG). No false negatives observed with the u-blox GPS.

### ✅ Log format
`15:23:27 INFO nmea_bridge ...` — clean, readable. The `%H:%M:%S` format is perfect for real-time monitoring.

### ✅ No admin required
The tool ran without any elevated permissions. No driver installation, no registry changes. This is a major selling point that works as advertised.

### ✅ Zero footprint
Closed the terminal, checked Task Manager — no leftover processes. True to the claim.

---

## 4. Edge Cases Worth Fixing

### Mixed baud rates
The README shows a confusing example:
```bash
python nmea_bridge.py --ports COM6,COM7 --baud 4800
python nmea_bridge.py --ports COM6,COM7 --baud 38400
```
These two commands would both try the same port set at different baud rates — the second would just override the first if running sequentially. If the user needs GPS at 4800 and AIS at 38400, they need two bridge instances on different TCP ports. This isn't clearly explained.

### Hardcoded COM6 fallback
```python
ports = ["COM6"]
```
If no NMEA ports are found, the bridge silently defaults to COM6 and retries forever. On a system without a COM6, this generates continuous "could not open port" warnings. A better default would be to exit with a message listing available ports.

---

## 5. Recommendations (Priority Order)

| Priority | Issue | Fix |
|----------|-------|-----|
| 🔴 **High** | `--port` docs mismatch | Remove `--port` from README, replace with `--tcp-port` |
| 🔴 **High** | argparse abbreviation | Add `allow_abbrev=False` to prevent `--port` → `--ports` |
| 🟡 **Medium** | Spare port messages | Remove or make them actually work |
| 🟡 **Medium** | Crash on port conflict | Start TCP server first, or handle `OSError` cleanly |
| 🟡 **Medium** | No troubleshooting | Add "Troubleshooting" section to README |
| 🟢 **Low** | Non-Windows docs | Add Linux/macOS equivalents |
| 🟢 **Low** | Example client reconnect | Add retry loop to hermit_crab_client.py |
| 🟢 **Low** | COM6 fallback | Warn and exit with port list instead |
| 🟢 **Low** | Mixed baud explanation | Clarify multi-instance approach |

---

## 6. Verdict

**The tool works.** The core functionality is solid — auto-scan, multi-port, TCP broadcast, multi-client — all of it worked on the first try without any debugging or guessing. A developer who just runs `pip install pyserial && python nmea_bridge.py` will have a great experience.

**But the README lies in two important places:**
1. `--port` doesn't set the TCP port (it triggers the argparse abbreviation footgun)
2. Spare ports aren't actually listening

Neither breaks the tool for the "quick start" path, but both would confuse anyone who reads the docs and tries the advanced features.

With the README cleaned up and the argparse footgun fixed, this is ready for a v1 release. The spare port messages and crash-on-conflict are nice-to-haves.
