#!/usr/bin/env python3
"""
NMEA Serial Splitter -- reads COM6 at 4800 baud and broadcasts
NMEA sentences to any TCP client that connects.

Usage:
  python nmea_splitter.py              # run with defaults
  python nmea_splitter.py --port 6007  # change TCP port
  python nmea_splitter.py --baud 9600  # change baud rate
"""

import asyncio
import serial
import serial.tools.list_ports
import sys

# -- Config -----------------------------------------------------------------
COM_PORT = "COM6"
COM_BAUD = 4800
TCP_PORT = 6006  # base port; clients connect to 6006, 6007, ...
NUM_CLIENTS = 4  # max simultaneous TCP clients
# --------------------------------------------------------------------------

clients: set[asyncio.StreamWriter] = set()


async def serial_reader(ser: serial.Serial):
    """Read NMEA from serial port and broadcast to all TCP clients."""
    print(f"[OK] Listening on COM6 ({COM_BAUD} baud)")
    print(f"[OK] TCP servers on ports {TCP_PORT}-{TCP_PORT + NUM_CLIENTS - 1}")
    print(f"[*] Connect clients with: nc localhost {TCP_PORT}")
    print("-" * 50)

    while True:
        try:
            line = await asyncio.to_thread(ser.readline)
            if not line:
                continue
            decoded = line.decode("ascii", errors="replace").strip()
            if decoded:
                broadcast(decoded + "\r\n")
        except serial.SerialException as e:
            print(f"[!] Serial error: {e}")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[!] Read error: {e}")
            await asyncio.sleep(1)


def broadcast(data: str):
    """Send data to all connected TCP clients."""
    dead = set()
    for w in clients:
        try:
            w.write(data.encode())
        except Exception:
            dead.add(w)
    clients.difference_update(dead)


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle a single TCP client connection."""
    addr = writer.get_extra_info("peername")
    print(f"[+] Client connected: {addr}")
    clients.add(writer)
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                break
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    finally:
        print(f"[-] Client disconnected: {addr}")
        clients.discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    # Open serial port
    try:
        ser = serial.Serial(COM_PORT, COM_BAUD, timeout=1)
    except serial.SerialException as e:
        print(f"[!] Cannot open {COM_PORT}: {e}")
        print("[!] Make sure TZ Pro is not using the port.")
        print("[!] Available ports:")
        for p in serial.tools.list_ports.comports():
            print(f"     {p.device}: {p.description}")
        sys.exit(1)

    # Start TCP servers
    servers = []
    for i in range(NUM_CLIENTS):
        port = TCP_PORT + i
        try:
            server = await asyncio.start_server(handle_client, "127.0.0.1", port)
            servers.append(server)
        except OSError as e:
            print(f"[!] Could not start TCP server on port {port}: {e}")

    if not servers:
        print("[!] No TCP servers could be started. Exiting.")
        ser.close()
        sys.exit(1)

    # Run serial reader + TCP servers concurrently
    tasks = [serial_reader(ser)] + [s.serve_forever() for s in servers]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
    finally:
        ser.close()
        for s in servers:
            s.close()
        print("[OK] Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
