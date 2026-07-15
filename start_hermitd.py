#!/usr/bin/env python3
"""start_hermitd.py — Launch NMEA splitter + Hermit Crab dashboard.
Run with: python start_hermitd.py
Stop with: Ctrl+C"""
import subprocess, sys, os, threading, logging, time
from http.server import HTTPServer

os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("start")

# 1. Start NMEA splitter
splitter = None
try:
    sock = __import__("socket").socket()
    sock.settimeout(0.5)
    sock.connect(("127.0.0.1", 6006))
    sock.close()
    log.info("NMEA splitter already running on :6006")
except:
    splitter = subprocess.Popen([sys.executable, "nmea_splitter.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info(f"NMEA splitter started (pid {splitter.pid})")
    time.sleep(2)

# 2. Import hermitd components
from hermitd import DashH, _open_nmea, _nmea_reader, capture_loop, CFG

CFG["port"] = 8654

# 3. Start NMEA reader
if _open_nmea():
    threading.Thread(target=_nmea_reader, daemon=True).start()
    log.info("NMEA reader started")

# 4. Start capture loop
stop = threading.Event()
threading.Thread(target=capture_loop, args=(stop,), daemon=True).start()

# 5. HTTP server in MAIN thread
s = HTTPServer(("127.0.0.1", CFG["port"]), DashH)
s.timeout = 0.5
print(f"\nHermit Crab: http://127.0.0.1:{CFG['port']}", flush=True)
print(f"TZ Pro/Nobeltec: connect to localhost:6006 (same NMEA)", flush=True)
print(f"Press Ctrl+C to stop\n", flush=True)

try:
    while not stop.is_set():
        try:
            s.handle_request()
        except KeyboardInterrupt:
            raise
        except:
            pass
except KeyboardInterrupt:
    print("\nShutting down...")
    stop.set()
    time.sleep(1)
    if splitter:
        splitter.terminate()
        splitter.wait(timeout=3)
    print("Stopped.")
