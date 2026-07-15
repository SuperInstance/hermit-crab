# NMEA Bridge — Starter Guide

A five-minute walkthrough from nothing to live NMEA on TCP.

## What You Need

- A Windows PC with a serial NMEA device (GPS, depth sounder, AIS, etc.)
- Python 3.8+ installed
- The USB-to-serial driver for your device (usually installs automatically)

## Step 1: Find Your COM Port

Open Device Manager and expand **Ports (COM & LPT)**. Your NMEA device
will show as something like "USB Serial Device (COM6)". Note the COM
number.

Or use the bridge's scanner:

```bash
pip install pyserial
python nmea_bridge.py --scan
```

It probes every COM port and reports which ones are sending valid NMEA
sentences.

## Step 2: Start the Bridge

```bash
python nmea_bridge.py --ports COM6
```

Replace `COM6` with your actual port. You'll see:

```
INFO  Reading NMEA from: COM6
INFO  Broadcasting on TCP port 6006
```

If you have multiple instruments:

```bash
python nmea_bridge.py --ports COM5,COM6,COM7
```

## Step 3: Connect an App

Open a second terminal and run:

```bash
python -c "
import socket
s = socket.socket()
s.connect(('127.0.0.1', 6006))
while True:
    print(s.recv(1024).decode(), end='')
"
```

You should see NMEA sentences streaming in:

```
$GPRMC,231542.00,A,5547.37839,N,13141.46882,W,1.808,254.01,140726,,,A*79
$GPGGA,231542.00,5547.37839,N,13141.46882,W,1,12,0.65,8.2,M,-6.1,M,,*57
```

Congratulations — your serial data is now available over the network.

## Step 4: Point Your Marine App at It

| App | Setup |
|-----|-------|
| **TZ Pro** | Settings → GPS/NMEA → Add Source → Network (TCP) → `127.0.0.1:6006` |
| **Nobeltec** | Settings → NMEA Input → Add TCP → `127.0.0.1:6006` |
| **OpenCPN** | Options → NMEA Inputs → Add → Network → TCP `127.0.0.1:6006` |
| **Signal K** | NMEA 0183 Data Source → TCP `127.0.0.1:6006` |

## Step 5: Run It Forever (Windows)

Create a file called `start_bridge.cmd`:

```bat
@echo off
cd C:\path\to\nmea-bridge
python nmea_bridge.py --ports COM6
```

Put a shortcut to this file in your Startup folder (`shell:startup`).
Or create a Scheduled Task that runs on login.

## If Something Goes Wrong

**"Port not found"** → Run `python nmea_bridge.py --list` to see all
available COM ports. Your device may need its driver installed.

**"Permission denied"** → Another app has the port open. Close TZ Pro,
Nobeltec, or any chart plotter that might be using it, then try again.

**"No NMEA detected"** → Your device may use a different baud rate.
Try `--baud 38400` or `--baud 9600`. Common rates: 4800 (GPS),
38400 (AIS), 9600 (depth sounders).

**"No sentences received"** → Some devices send data only when they
have a fix. Put the GPS where it can see the sky.
