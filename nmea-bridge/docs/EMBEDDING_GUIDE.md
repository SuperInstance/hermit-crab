# NMEA Bridge — Embedding Guide for Developers

Integrate NMEA Bridge into your own application. Whether you're
building a marine dashboard, a data logger, a tracking system, or
an AI agent that needs live instrument data, this guide shows you
how.

## Table of Contents

1. [The Simplest Possible Integration](#1-the-simplest-possible-integration)
2. [Python Integration Patterns](#2-python-integration-patterns)
3. [Other Languages](#3-other-languages)
4. [Parsing NMEA Sentences](#4-parsing-nmea-sentences)
5. [Error Handling & Reliability](#5-error-handling--reliability)
6. [Architecture Patterns](#6-architecture-patterns)
7. [CLI Integration in Batch Files](#7-cli-integration-in-batch-files)
8. [Docker & Containerization](#8-docker--containerization)

---

## 1. The Simplest Possible Integration

**Goal:** Get NMEA data into your app with zero dependencies.

Any language that can open a TCP socket can read the bridge output.
No SDK, no library, no authentication, no protocol negotiation.

```python
# 6 lines. That's it.
import socket
s = socket.socket()
s.connect(('127.0.0.1', 6006))
while True:
    data = s.recv(4096)
    print(data.decode(errors='replace'))
```

---

## 2. Python Integration Patterns

### 2.1 Background thread with buffer

```python
import socket, threading, time

class NMEAReader:
    def __init__(self, host='127.0.0.1', port=6006):
        self.host = host
        self.port = port
        self._buffer = []
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        return self

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            try:
                s = socket.socket()
                s.settimeout(5)
                s.connect((self.host, self.port))
                buf = b''
                while self._running:
                    data = s.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        with self._lock:
                            self._buffer.append(line.decode(errors='replace'))
            except socket.timeout:
                continue
            except Exception as e:
                print(f'NMEA reader error: {e}')
                time.sleep(3)
            finally:
                try:
                    s.close()
                except Exception:
                    pass

    def get_sentences(self, max_count=10):
        with self._lock:
            out = self._buffer[:max_count]
            self._buffer = self._buffer[max_count:]
            return out

# Usage
reader = NMEAReader().start()
time.sleep(5)
for sentence in reader.get_sentences():
    print(sentence)
```

### 2.2 Async with asyncio

```python
import asyncio

async def read_nmea(host='127.0.0.1', port=6006):
    reader, _ = await asyncio.open_connection(host, port)
    while True:
        line = await reader.readline()
        if not line:
            break
        yield line.decode(errors='replace').strip()

async def main():
    async for sentence in read_nmea():
        if sentence.startswith('$GPGGA'):
            print(f'Position fix: {sentence}')

asyncio.run(main())
```

### 2.3 Parse into structured data

```python
import socket, re

s = socket.socket()
s.connect(('127.0.0.1', 6006))
buf = b''
while True:
    buf += s.recv(4096)
    while b'\n' in buf:
        line, buf = buf.split(b'\n', 1)
        text = line.decode(errors='replace').strip()
        if not text or not text.startswith('$'):
            continue
        parts = text.split(',')
        sentence_type = text[1:6]

        if sentence_type == 'GPGGA' and len(parts) >= 15:
            # Time, lat, lon, quality, sats, altitude
            print(f'Time: {parts[1]}, Sats: {parts[7]}, Alt: {parts[9]}m')

        elif sentence_type == 'GPRMC' and len(parts) >= 12:
            # Speed over ground, course over ground
            print(f'SOG: {parts[7]} kn, COG: {parts[8]} deg')

        elif sentence_type == 'SDDBT':
            # Depth
            print(f'Depth: {parts[3]} m')

        elif sentence_type[:2] == 'AI' or sentence_type[:2] == 'VD':
            # AIS
            print(f'AIS: {text[:80]}')
```

---

## 3. Other Languages

### JavaScript / Node.js

```javascript
const net = require('net');

const client = net.createConnection({ host: '127.0.0.1', port: 6006 }, () => {
    console.log('Connected to NMEA Bridge');
});

client.on('data', (data) => {
    const lines = data.toString().split('\n');
    lines.forEach(line => {
        if (line.startsWith('$')) {
            console.log('NMEA:', line);
        }
    });
});

client.on('error', (err) => {
    console.error('Connection error:', err.message);
});
```

### C# / .NET

```csharp
using System.Net.Sockets;

using var client = new TcpClient("127.0.0.1", 6006);
using var stream = client.GetStream();
using var reader = new StreamReader(stream);

while (true)
{
    var line = await reader.ReadLineAsync();
    if (line != null && line.StartsWith("$"))
    {
        Console.WriteLine($"NMEA: {line}");
    }
}
```

### Go

```go
package main

import (
    "bufio"
    "fmt"
    "net"
)

func main() {
    conn, err := net.Dial("tcp", "127.0.0.1:6006")
    if err != nil {
        panic(err)
    }
    defer conn.Close()

    scanner := bufio.NewScanner(conn)
    for scanner.Scan() {
        line := scanner.Text()
        if len(line) > 0 && line[0] == '$' {
            fmt.Println("NMEA:", line)
        }
    }
}
```

### Rust

```rust
use std::io::{BufRead, BufReader};
use std::net::TcpStream;

fn main() {
    let stream = TcpStream::connect("127.0.0.1:6006").unwrap();
    let reader = BufReader::new(stream);

    for line in reader.lines() {
        if let Ok(line) = line {
            if line.starts_with('$') {
                println!("NMEA: {}", line);
            }
        }
    }
}
```

### Bash (netcat)

```bash
nc 127.0.0.1 6006 | while read line; do
    if [[ "$line" == \$* ]]; then
        echo "NMEA: $line"
    fi
done
```

---

## 4. Parsing NMEA Sentences

### Common sentence types

| Sentence | Source | Key data |
|----------|--------|----------|
| `$GPGGA` | GPS | Time, lat, lon, quality, altitude |
| `$GPRMC` | GPS | Speed, course, date |
| `$GPVTG` | GPS | Course & speed over ground |
| `$GPGSV` | GPS | Satellite positions & signal |
| `$GPGSA` | GPS | DOP & active satellites |
| `$GPGLL` | GPS | Lat/lon only |
| `$SDDBT` | Depth | Depth below transducer |
| `$SDDBS` | Depth | Depth below surface |
| `$WIMWV` | Wind | Wind speed & angle |
| `$WIVWR` | Wind | Relative wind |
| `$VWT` | Wind | True wind |
| `$AIVDM` | AIS | Vessel data & position |
| `$AIVDO` | AIS | Own vessel AIS data |
| `$HERMR` | Sentry | ...well, maybe not yet |

### Minimal parser

```python
def parse_nmea(line: str) -> dict | None:
    """Parse a single NMEA sentence into a dict of known fields."""
    if not line or not line.startswith('$'):
        return None
    parts = line.split(',')
    sen = line[1:6]
    result = {'raw': line, 'type': sen, 'fields': parts}

    try:
        if sen == 'GPGGA' and len(parts) >= 15:
            result['time'] = parts[1]
            result['lat'] = _parse_lat(parts[2], parts[3])
            result['lon'] = _parse_lon(parts[4], parts[5])
            result['quality'] = int(parts[6]) if parts[6] else None
            result['satellites'] = int(parts[7]) if parts[7] else None
            result['altitude'] = float(parts[9]) if parts[9] else None

        elif sen == 'GPRMC' and len(parts) >= 12:
            result['lat'] = _parse_lat(parts[3], parts[4])
            result['lon'] = _parse_lon(parts[5], parts[6])
            result['sog'] = float(parts[7]) if parts[7] else None  # knots
            result['cog'] = float(parts[8]) if parts[8] else None  # degrees
            result['date'] = parts[9] if parts[9] else None

        elif sen == 'SDDBT' and len(parts) >= 4:
            result['depth_m'] = float(parts[3]) if parts[3] else None

    except (ValueError, IndexError):
        pass

    return result


def _parse_lat(val: str, hem: str) -> float | None:
    """Parse NMEA lat/lon format (DDMM.MMMM) to decimal degrees."""
    if not val or not hem:
        return None
    d = int(val[:2])
    m = float(val[2:])
    dec = d + m / 60
    if hem in ('S', 'W'):
        dec = -dec
    return dec


def _parse_lon(val: str, hem: str) -> float | None:
    if not val or not hem:
        return None
    d = int(val[:3])
    m = float(val[3:])
    dec = d + m / 60
    if hem in ('S', 'W'):
        dec = -dec
    return dec
```

---

## 5. Error Handling & Reliability

### Reconnection (always reconnect)

```python
import socket, time

def connect_bridge(host='127.0.0.1', port=6006, retry=5):
    for attempt in range(retry):
        try:
            s = socket.socket()
            s.settimeout(10)
            s.connect((host, port))
            return s
        except Exception as e:
            print(f'Connection attempt {attempt+1} failed: {e}')
            time.sleep(3)
    raise ConnectionError('Could not connect to NMEA Bridge')
```

### Detect stale data

```python
import socket, time

s = socket.socket()
s.connect(('127.0.0.1', 6006))
s.settimeout(15)  # if no NMEA for 15s, something is wrong

last_data = time.time()
while True:
    try:
        data = s.recv(4096)
        if data:
            last_data = time.time()
            process(data)
        elif time.time() - last_data > 30:
            print('WARNING: No NMEA data for 30 seconds')
            last_data = time.time()
    except socket.timeout:
        if time.time() - last_data > 60:
            print('ALERT: Bridge appears dead, reconnecting...')
            s.close()
            s = connect_bridge()
            last_data = time.time()
```

---

## 6. Architecture Patterns

### Single consumer (simplest)

```
[COM6] → [Bridge] → TCP → [Your App]
```

### Multiple consumers on same machine

```
[COM6] ─→ [Bridge] ─→ TCP 6006 ─→ [TZ Pro]
                                ─→ [Nobeltec]
                                ─→ [Your App]
```

### Multi-machine (network distribution)

```
[Boat PC]
  [COM6] → [Bridge :6006] ─→ TCP (0.0.0.0)
                              │
[Tablet]                      │
  [TZ Pro] ─── TCP :6006 ←───┘

[Laptop]
  [Logger] ─── TCP :6006 ←───┘
```

### Multiple instruments, one stream

```
[COM6 GPS] ──┐
[COM5 Depth] ─┤
[COM7 AIS]  ──┤
[COM8 Wind] ──┘
              │
         [Bridge] ─→ TCP :6006 ─→ All apps
```

### Redundant bridges (failover)

```
[COM6] → [Bridge A :6006] ─→ Primary route
                              │
[COM6] ← [Bridge B :6007] ───┘ (standby)
```

Your app connects to both, deduplicates by sentence timestamp.

---

## 7. CLI Integration in Batch Files

### Windows batch (.cmd)

```bat
@echo off
:: Start bridge, wait, launch your app
start /B python nmea_bridge.py --ports COM6
timeout /T 3 /NOBREAK >nul
start "" "C:\Program Files\TZPro\TZPro.exe"
```

### PowerShell

```powershell
# Start bridge, pipe NMEA to your script
python nmea_bridge.py --ports COM6 --tcp-port 6006

# In another window, consume in real time
$tcp = New-Object System.Net.Sockets.TcpClient
$tcp.Connect('127.0.0.1', 6006)
$stream = $tcp.GetStream()
$reader = New-Object System.IO.StreamReader($stream)
while (($line = $reader.ReadLine()) -ne $null) {
    if ($line -match '^\$') {
        Write-Host $line
    }
}
```

---

## 8. Docker & Containerization

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY nmea_bridge.py requirements.txt ./
RUN pip install -r requirements.txt
EXPOSE 6006
CMD ["python", "nmea_bridge.py", "--ports", "COM6"]
```

Note: Docker on Windows has limited COM port passthrough.
Use `--privileged` or mount `\\.\COM6` explicitly.

### docker-compose.yml

```yaml
version: '3'
services:
  nmea-bridge:
    build: .
    ports:
      - "6006:6006"
    devices:
      - "/dev/ttyS0:/dev/ttyS0"
    restart: unless-stopped

  data-logger:
    image: python:3.12-slim
    command: python -c "
import socket
s = socket.socket()
s.connect(('nmea-bridge', 6006))
with open('/data/nmea.log', 'w') as f:
    while True:
        f.write(s.recv(4096).decode())
"
    depends_on:
      - nmea-bridge
    volumes:
      - ./logs:/data
```

---

## Summary

| Pattern | Lines of code | Dependency |
|---------|:---:|:---:|
| Raw TCP read | 6 | none |
| Background thread | ~50 | none |
| Async generator | ~10 | none |
| NMEA parser | ~40 | none |
| Full integration (C#/Go/Rust) | ~15 | language stdlib |

The bridge is intentionally dumb — it just forwards bytes. That makes
integration trivial in any language that speaks TCP.
