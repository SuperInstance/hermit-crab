#!/usr/bin/env python3
"""
Quick test: connect to bridge, verify NMEA sentences arrive.
"""
import socket, sys, time, re

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6006
TIMEOUT = 8

s = socket.socket()
s.settimeout(TIMEOUT)
t0 = time.time()
nmea_count = 0

try:
    s.connect((HOST, PORT))
    print(f"Connected to {HOST}:{PORT}")
    buf = b""
    while time.time() - t0 < TIMEOUT:
        try:
            data = s.recv(4096)
            if not data:
                break
            buf += data
            # Count complete NMEA sentences
            for line in buf.split(b"\n"):
                line = line.decode("ascii", errors="replace").strip()
                if re.match(r"^\$[A-Z]{5,6},", line):
                    nmea_count += 1
            buf = b"" if buf.endswith(b"\n") else buf
        except socket.timeout:
            break
finally:
    s.close()

print(f"Received {nmea_count} NMEA sentences in {time.time()-t0:.1f}s")
if nmea_count > 5:
    print("PASS: Bridge is healthy")
    sys.exit(0)
else:
    print("FAIL: Few or no NMEA sentences received")
    sys.exit(1)
