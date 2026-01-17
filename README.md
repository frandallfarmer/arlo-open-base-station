# Arlo Open Base Station

A DIY replacement for Arlo's commercial base stations (VMB4000/VMB5000/VMB4540) using commodity hardware. Run your Arlo cameras without cloud subscriptions or vendor lock-in.

## Project Status: Advanced / Experimental

This is a working system, not a polished product. Installation requires configuring networking, systemd services, external tunneling, and camera re-pairing. There is an install script, but expect to troubleshoot and adapt to your specific hardware and network.

**Using an AI coding assistant (like [Claude Code](https://docs.anthropic.com/en/docs/claude-code)) is strongly recommended** to work through the installation and configuration process. The number of moving parts (Linux networking, GStreamer, DNS, firewall rules, camera protocol) makes interactive AI assistance very helpful.

### Tested Hardware

| Component | Tested Model |
|-----------|-------------|
| Camera | Arlo Pro (VMC4030) |
| WiFi AP | TP-Link Omada EAP225 |
| Compute | Surface Book 3 running Ubuntu 24.04 |

Other Arlo cameras that use the same registration protocol may work but have not been tested.

### Known Limitations

- Cameras must be re-paired from Arlo cloud (factory reset required)
- No geofencing, scheduling, or other cloud-based features
- Single WiFi subnet - all cameras on one AP
- GStreamer required for live streaming (FFmpeg RTCP timing is incompatible)
- Upstream protocol library ([arlo-cam-api](https://github.com/Meatballs1/arlo-cam-api)) has no license specified - see [LICENSE](LICENSE) for details

## What This Replaces

| Commercial Product | Replacement |
|-------------------|-------------|
| Arlo Base Station VMB4000/5000 | Linux computer + WiFi AP |
| Arlo Cloud Subscription | Local storage |
| Arlo App | Web-based viewer |
| Arlo Push Notifications | Self-hosted ntfy |

## Features

- **No subscription fees** - All recordings stored locally
- **No cloud dependency** - Works entirely offline
- **Extended range** - Use enterprise WiFi hardware for better coverage
- **Push notifications** - Motion alerts via ntfy (self-hosted or ntfy.sh)
- **Web viewer** - Browse and stream recordings from any browser
- **Live streaming** - On-demand camera streaming via HLS
- **Thumbnail previews** - Motion alerts include snapshot images

## Hardware Requirements

- **Compute**: Any Linux machine (Raspberry Pi 4, old laptop, mini PC)
- **WiFi AP**: Enterprise access point recommended (TP-Link Omada EAP225)
- **Cameras**: Arlo Pro cameras (VMC4030 tested)

> **Important**: WiFi hardware choice is critical. Consumer USB adapters often drop sleeping camera connections, causing battery drain. See [docs/WIFI-HARDWARE.md](docs/WIFI-HARDWARE.md) for details.

## Getting Started

```bash
# Clone the repository
git clone https://github.com/frandallfarmer/arlo-open-base-station.git
cd arlo-open-base-station

# Copy and edit configuration
cp config/install.conf.example config/install.conf
nano config/install.conf

# Run installer
sudo scripts/install.sh

# Reboot
sudo reboot
```

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for complete setup instructions, including external infrastructure requirements (VPS, domain, bore tunnels for remote access).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    arlo-base (Linux)                     │
├─────────────────────────────────────────────────────────┤
│  arlo-cam-api (Python)          arlo-viewer (Node.js)   │
│  ├─ Camera registration         ├─ Web interface        │
│  ├─ Motion detection            ├─ Recording playback   │
│  ├─ Video recording             ├─ Live streaming       │
│  └─ Push notifications          └─ Status dashboard     │
├─────────────────────────────────────────────────────────┤
│  WiFi AP (hostapd/Omada)     │  Recordings (local disk) │
└─────────────────────────────────────────────────────────┘
         │
    ┌────┴────┐
    │  Arlo   │
    │ Cameras │
    └─────────┘
```

## Documentation

- [Installation Guide](docs/INSTALLATION.md) - Complete setup instructions
- [Dependencies](docs/DEPENDENCIES.md) - Required packages and external services
- [WiFi Hardware](docs/WIFI-HARDWARE.md) - Critical hardware compatibility info
- [System Architecture](docs/ARLO-SYSTEM-V1.0.md) - Technical deep-dive

## Configuration

All configuration is done through `config/install.conf`:

```bash
# Required
USERNAME="your_username"
WIFI_INTERFACE="wlan0"
WIFI_SSID="NETGEAR99"
WIFI_PASSWORD="your_password"

# Camera names
CAMERA_SERIAL_1="ABC123"
CAMERA_NAME_1="Front Door"

# Push notifications (optional)
NTFY_ENABLED="true"
NTFY_URL="https://ntfy.sh"
NTFY_TOPIC="my-arlo-alerts"
```

## Credits

This project builds on the work of others:

- [Meatballs1/arlo-cam-api](https://github.com/Meatballs1/arlo-cam-api) - Original Arlo protocol reverse-engineering
- [ntfy](https://github.com/binwiederhier/ntfy) - Push notification server
- [bore](https://github.com/ekzhang/bore) - TCP tunneling for remote access

## License

MIT - See [LICENSE](LICENSE) for details, including third-party notices.
