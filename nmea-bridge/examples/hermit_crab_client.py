#!/usr/bin/env python3
"""
Hermit Crab — TCP NMEA client with auto-reconnection.
Connects to the bridge and prints NMEA sentences to stdout.
"""
import socket, sys, time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6006
RECONNECT_DELAY = 3


def connect() -> socket.socket:
    s = socket.socket()
    s.settimeout(10)
    s.connect((HOST, PORT))
    s.settimeout(None)
    return s


print(f"NMEA Bridge client — connecting to {HOST}:{PORT}", flush=True)
while True:
    try:
        sock = connect()
        print(f"Connected.", flush=True)
        while True:
            data = sock.recv(4096)
            if not data:
                break
            sys.stdout.write(data.decode("ascii", errors="replace"))
            sys.stdout.flush()
    except (ConnectionRefusedError, ConnectionResetError, BrokenPipeError,
            socket.timeout, OSError) as e:
        print(f"\nDisconnected ({e}). Reconnecting in {RECONNECT_DELAY}s...",
              flush=True)
    except KeyboardInterrupt:
        break
    finally:
        try:
            sock.close()
        except Exception:
            pass
    time.sleep(RECONNECT_DELAY)
