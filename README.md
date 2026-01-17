# Arlo Open Base Station

A DIY replacement for Arlo's commercial base stations (VMB4000/VMB5000/VMB4540) using commodity hardware. Run your Arlo cameras without cloud subscriptions or vendor lock-in.

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

## Quick Start

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

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for complete setup instructions.

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

MIT
