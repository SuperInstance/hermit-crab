# SKILLS.md — What Hermit Crab Knows

## Screen Capture

**skill:tzpro-capture** — Capture TZ Pro on Monitor 2 (1600x1200) via WinAPI.
Uses Add-Type C# BitBlt. Outputs to a PNG file. PowerShell script at systems/capture/capture_monitor2.ps1

## OCR Extraction

**skill:tzpro-extract** — Extract lat/lon/SOG/depth/tide from TZ Pro screenshot.
Uses Tesseract 5.4 on cropped regions with character whitelists. Python at systems/extract/tzpro_extract.py.
Returns structured JSON with confidence scoring per field.

## Segment Tracking

**skill:segment-track** — Maintain open segment with running mean/variance of SOG, COG, depth, tide.
Closes segment on thresholds: SOG delta >0.3kn, COG delta >5°, depth delta >2fm, elapsed >15min.
Writes to D1. State persisted to activetrack_state.json. Python at systems/track/activetrack.py.

## Event Logging

**skill:event-log** — Log fishing events (gear deployments, catches, notes) to D1.
Each event tagged to current segment with lat/lon/depth/tide context.
Supports: --event "description" --tags "trolling,chinook" and --catch N --species "king salmon"

## I2I Bottle Protocol

**skill:i2i-bottle** — Send/receive fleet messages via git-native bottles.
Messages: inbox/*.md + commit + tag bottle/<topic>. Responses: outbox/*.md.
Protocol: inbox/PROTOCOL.md. Autohr: agent identity in every message.

## MCP Server

**skill:mcp-server** — Expose activelog as MCP tools (query_segments, query_events, log_event, etc.)
Any MCP-speaking agent can connect via stdio. Python at systems/mcp/server.py.
