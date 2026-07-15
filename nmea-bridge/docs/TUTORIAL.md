# NMEA Bridge — Tutorial

Build a complete NMEA distribution system from scratch. This tutorial
takes you from zero to a multi-instrument, multi-client setup that
survives reboots and device disconnects.

## Prerequisites

- Windows 10 or 11
- Python 3.8+ (get it at python.org)
- At least one NMEA serial device (GPS, depth sounder, AIS, etc.)

## Part 1: Hello, NMEA

### 1.1 Install the bridge

```bash
pip install pyserial
```

### 1.2 Discover your instruments

```bash
python nmea_bridge.py --list
```

Example output:

```
COM1     Communications Port (COM1)
COM6     USB Serial Device (COM6)
```

Your GPS or depth sounder will show as "USB Serial Device" on some COM
port. If nothing shows up, install the USB-to-serial driver for your
device.

### 1.3 Test the connection

```bash
python nmea_bridge.py --ports COM6
```

Hit `Ctrl+C` to stop. If you see `NMEA detected`, you're good. If you
see "No NMEA detected", try different baud rates:

```bash
python nmea_bridge.py --ports COM6 --baud 4800
python nmea_bridge.py --ports COM6 --baud 9600
python nmea_bridge.py --ports COM6 --baud 38400
```

### 1.4 Start the bridge

```bash
python nmea_bridge.py --ports COM6 --verbose
```

### 1.5 Connect and watch

In another terminal:

```bash
python -c "
import socket, time
s = socket.socket()
s.connect(('127.0.0.1', 6006))
s.settimeout(5)
try:
    while True:
        data = s.recv(4096)
        if data: print(data.decode().strip())
except KeyboardInterrupt:
    pass
"
```

You should see NMEA sentences flowing.

## Part 2: Multiple Instruments

### 2.1 Connect everything

Plug in all your serial devices. Note each COM port number.

### 2.2 Run with all ports

```bash
python nmea_bridge.py --ports COM5,COM6,COM7
```

The bridge opens every port and merges all sentences into one stream.
Every TCP client sees every sentence from every instrument.

### 2.3 Verify

Connect a TCP client and look for sentences from different sources:

```
$GPRMC,...      ← GPS on COM6
$SDDBT,...      ← Depth sounder on COM5
$WIMWV,...      ← Wind sensor on COM8
```

## Part 3: Multiple Clients

### 3.1 Connect several apps

Start the bridge on the default port:

```bash
python nmea_bridge.py --ports COM6
```

Then in separate terminals (or different machines on your LAN):

```bash
# App 1 — TZ Pro pointing at localhost:6006
# App 2 — Nobeltec pointing at localhost:6006
# App 3 — Your custom script
python -c "
import socket
s = socket.socket()
s.connect(('127.0.0.1', 6006))
with open('nmea_log.txt', 'w') as f:
    while True:
        data = s.recv(4096)
        if data: f.write(data.decode())
"
```

### 3.2 Or use dedicated ports per app

```bash
# Instance 1 for TZ Pro on port 6006
python nmea_bridge.py --ports COM6 --tcp-port 6006

# Instance 2 for Nobeltec on port 7000
python nmea_bridge.py --ports COM6 --tcp-port 7000
```

## Part 4: Production Deployment

### 4.1 Run as a background service

```powershell
Start-Process -NoNewWindow python -ArgumentList "nmea_bridge.py --ports COM6" `
    -WorkingDirectory "C:\nmea-bridge" `
    -RedirectStandardOutput "$env:TEMP\nmea_bridge.log" `
    -RedirectStandardError "$env:TEMP\nmea_bridge_err.log"
```

### 4.2 Create a Scheduled Task

```powershell
$action = New-ScheduledTaskAction -Execute "python" `
    -Argument "C:\nmea-bridge\nmea_bridge.py --ports COM6"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "NMEA Bridge" `
    -Action $action -Trigger $trigger -Principal $principal
```

### 4.3 Auto-restart on crash

Wrap in a PowerShell loop:

```powershell
while ($true) {
    python nmea_bridge.py --ports COM6
    Start-Sleep 2  # wait before restart
}
```

## Part 5: Network Distribution

Want instruments on one machine and apps on another?

### 5.1 Bind to all interfaces

```bash
# Edit nmea_bridge.py: change "127.0.0.1" to "0.0.0.0"
# Then restart
```

### 5.2 Connect from another machine

On the client machine, point your app at the bridge machine's IP:

```
TZ Pro → TCP 192.168.1.100:6006
```

### 5.3 Security note

Binding to `0.0.0.0` exposes NMEA to your entire network. On a boat
that's fine. On a marina WiFi, consider a firewall rule.

## Part 6: Custom Integration

### 6.1 Embed in your Python app

```python
import socket, threading

nmea_buffer = []

def nmea_listener():
    s = socket.socket()
    s.connect(('127.0.0.1', 6006))
    while True:
        data = s.recv(4096)
        if data:
            nmea_buffer.extend(data.decode().splitlines())

threading.Thread(target=nmea_listener, daemon=True).start()
```

### 6.2 Log all NMEA to a file

```bash
python -c "
import socket
s = socket.socket()
s.connect(('127.0.0.1', 6006))
with open(f'nmea_{__import__(\"datetime\").datetime.now():%Y%m%d}.log', 'ab') as f:
    while True:
        data = s.recv(4096)
        if data: f.write(data)
" &
```

### 6.3 React to specific sentences

```python
import socket, re

s = socket.socket()
s.connect(('127.0.0.1', 6006))
buf = b''
while True:
    buf += s.recv(4096)
    while b'\n' in buf:
        line, buf = buf.split(b'\n', 1)
        text = line.decode(errors='replace')
        if 'GPGGA' in text:
            print(f'GGA: {text.strip()}')  # position
        elif 'AIVDM' in text:
            print(f'AIS: {text.strip()}')  # AIS target
```

## Reference

| Command | What it does |
|---------|-------------|
| `--ports COM5,COM6` | Specify which COM ports to read |
| `--baud 4800` | Set baud rate (default 4800) |
| `--tcp-port 6006` | Set TCP listen port (default 6006) |
| `--scan` | Probe all ports for NMEA, then exit |
| `--list` | List all serial ports, then exit |
| `--verbose` | Show debug-level logs |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Port not found" | Wrong COM number | Run `--list` to see available ports |
| "Permission denied" | Port in use | Close the app that has it open |
| "No NMEA detected" | Wrong baud rate | Try 4800, 9600, 38400 |
| "No sentences" | GPS needs sky | Move antenna outside |
| Bridge crashes | USB disconnect | It auto-reconnects — wait 5s |
