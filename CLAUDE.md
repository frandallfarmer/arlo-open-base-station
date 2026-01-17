# CLAUDE.md - Arlo Open Base Station

This is the development documentation for the Arlo Open Base Station project - a DIY replacement for Arlo's commercial base stations.

## Project Overview

This project provides a complete replacement for Arlo's commercial base station (VMB4000/VMB5000) using commodity hardware. It enables:

- Direct camera communication without Arlo cloud services
- Local motion-triggered recordings
- Self-hosted push notifications via ntfy
- Web-based video viewer
- Extended WiFi range compared to commercial base stations

## Repository vs. Live Deployment

**IMPORTANT**: This repository is for VERSION CONTROL only. It contains sanitized code and configuration templates. The actual running services read from a separate LIVE DEPLOYMENT.

### What's in the Repository (Version Control)
```
~/arlo-open-base-station/           # This repo
├── src/arlo-cam-api/               # Source code (sanitized)
├── src/arlo-viewer/                # Source code (sanitized)
├── config/*.example                # Config TEMPLATES (no secrets)
└── docs/                           # Documentation
```

### What's in the Live Deployment (Runtime)
```
/opt/arlo-cam-api/                  # RUNNING Python backend (arlo.service)
├── config.yaml                     # LIVE config with real secrets
├── arlo.db                         # LIVE database
└── venv/                           # Python virtualenv

~/arlo-viewer/                      # RUNNING Node.js frontend (arlo-viewer.service)

~/arlo-recordings/                  # LIVE video storage (NOT in repo)
```

### What is NOT in the Repository
- `config.yaml` with real camera serials, ntfy topics, passwords
- `arlo.db` database
- `arlo-recordings/` video files
- `node_modules/`
- Python `venv/`

### Development Workflow
1. Make changes in the LIVE DEPLOYMENT (`/opt/arlo-cam-api/` or `~/arlo-viewer/`)
2. Test by restarting services
3. Once working, copy changes to the repo (`~/arlo-open-base-station/`)
4. Commit and push to GitHub

### Fresh Install (New Machine)
1. Clone the repo
2. Run `scripts/install.sh` - creates live deployment from repo templates
3. Edit live config with real values
4. Services run from live deployment, not repo

## Directory Structure

```
arlo-open-base-station/
├── src/
│   ├── arlo-cam-api/          # Python backend (Flask + ArloSocket)
│   │   ├── server.py          # Main server entry point
│   │   ├── arlo/              # Camera protocol handlers
│   │   ├── api/               # Flask REST API endpoints
│   │   └── helpers/           # GStreamer streaming helpers
│   └── arlo-viewer/           # Node.js web frontend
│       ├── server.js          # Express server
│       └── public/            # Web interface (HTML/JS/CSS)
├── config/
│   ├── install.conf.example   # Installation configuration template
│   ├── config.yaml.example    # Main configuration template
│   └── dnsmasq.conf.example   # DHCP server configuration
├── systemd/
│   ├── arlo.service           # Main arlo-cam-api service
│   └── arlo-viewer.service    # Web viewer service
├── scripts/
│   ├── install.sh             # Main installation script
│   └── start-bore-tunnel.sh.example  # Remote access tunnel
└── docs/                      # Additional documentation
```

## Installation

1. Copy the config template:
   ```bash
   cp config/install.conf.example config/install.conf
   ```

2. Edit `config/install.conf` with your values (username, WiFi interface, passwords, etc.)

3. Run the installer as root:
   ```bash
   sudo scripts/install.sh
   ```

4. Configure your WiFi interface IP (instructions shown after install)

5. Reboot

## Key Components

### arlo-cam-api (Python)
The core backend that handles:
- Camera registration and authentication (TCP port 4000)
- Motion detection alerts
- RTSP video recording (port 554)
- Push notifications via ntfy
- REST API for status and control (port 5000)

**Important Files:**
- `server.py` - Main entry point, starts Flask and ArloSocket
- `arlo/registration.py` - Camera registration protocol
- `arlo/stream_manager.py` - Video recording management
- `api/routes.py` - REST API endpoints

### arlo-viewer (Node.js)
Web interface for:
- Viewing recorded videos
- Camera status dashboard
- Live streaming (HLS via GStreamer)
- Recording management (view, delete)

**Important Files:**
- `server.js` - Express server with auth, API proxy, cleanup
- `public/index.html` - Recording gallery with LIVE button
- `public/status.html` - Camera status dashboard
- `public/stream.html` - Live stream viewer

## Network Architecture

```
Internet/LAN (ethernet)
       │
   arlo-base (172.14.0.1)
       │
   WiFi AP (NETGEAR99)
       │
   ┌───┴───┐
Camera1  Camera2
(.102)   (.103)
```

**Ports:**
- 4000/TCP - Camera control protocol (ArloSocket)
- 5000/TCP - REST API (Flask)
- 3003/TCP - Web viewer (Node.js)
- 554/TCP - RTSP streaming
- 67/UDP - DHCP (dnsmasq)
- 53/UDP - DNS (dnsmasq)

## Configuration

Main configuration is in `config/config.yaml`:

```yaml
# Recording settings
RecordOnMotionAlert: true
RecordingBasePath: "/home/user/arlo-recordings/"
MotionRecordingTimeout: 120

# Push notifications (ntfy)
NtfyEnabled: true
NtfyUrl: "https://ntfy.sh"
NtfyTopic: "your-arlo-alerts"

# Camera aliases
CameraAliases:
  SERIAL1: "Front Door"
  SERIAL2: "Back Yard"
```

### Logs
```bash
# Main arlo service
tail -f /tmp/arlo-service.log

# Viewer service
journalctl -u arlo-viewer -f

# DHCP leases
cat /var/lib/misc/dnsmasq.leases
```

## Common Tasks

### Check Camera Status
```bash
# View connected cameras
curl http://localhost:5000/api/cameras/status

# Check DHCP leases
cat /var/lib/misc/dnsmasq.leases

# Check WiFi clients
iw dev YOUR_INTERFACE station dump
```

### Manual Recording
```bash
# Start recording from camera
curl -X POST http://localhost:5000/api/cameras/SERIAL/record

# Stop recording
curl -X POST http://localhost:5000/api/cameras/SERIAL/stop
```

### Troubleshooting
```bash
# Check if services are running
systemctl status arlo.service
systemctl status arlo-viewer.service

# Check ports
ss -tlnp | grep -E '4000|5000|3003'

# Check firewall
sudo iptables -L INPUT -n -v
```

## GStreamer Streaming

The project uses GStreamer for live streaming because:
- FFmpeg sends RTCP at 10-second intervals (hardcoded)
- Arlo cameras require RTCP every 5 seconds
- GStreamer correctly sends RTCP at 5-second intervals

Key streaming files:
- `src/arlo-cam-api/helpers/stream_manager.py`
- `src/arlo-cam-api/helpers/gst_hls_stream.py`

## Hardware Requirements

- Linux computer (Raspberry Pi, old laptop, etc.)
- USB WiFi adapter with AP mode support
- Recommended: Alfa AWUS036ACH (30 dBm, 2x Arlo range)

## Security Notes

- All recordings stored locally (no cloud)
- Web viewer uses cookie-based authentication
- Push notifications via self-hosted ntfy (optional)
- No internet required for core functionality
