# Installation Guide

## What This Replaces

This project is a complete replacement for:

| Commercial Product | What It Does | Status After Migration |
|-------------------|--------------|------------------------|
| **Arlo Base Station VMB4000** | WiFi hub for Arlo Pro cameras | Not needed |
| **Arlo Base Station VMB5000** | WiFi hub for Arlo Pro 2/3 cameras | Not needed |
| **Arlo SmartHub VMB4540** | Newer base station model | Not needed |
| **Arlo Cloud Subscription** | Cloud storage, notifications | Replaced by local storage + ntfy |
| **Arlo App** | Mobile viewing, alerts | Replaced by web viewer |

### What You Gain
- No monthly subscription fees
- Local storage (no cloud dependency)
- Extended WiFi range (with proper hardware)
- Self-hosted push notifications
- Full control over your camera system

### What You Lose
- Arlo app integration
- Geofencing / smart home integrations
- Cloud backup redundancy
- Official support

## Hardware Requirements

### Compute
- Linux machine (Ubuntu 20.04+ recommended)
- Raspberry Pi 4, old laptop, or mini PC all work fine

### WiFi Access Point (CRITICAL)

**The WiFi hardware choice is critical.** Arlo cameras sleep deeply to conserve battery and expect the WiFi connection to remain stable during sleep. Consumer USB WiFi adapters often drop sleeping clients, forcing cameras to reconnect every ~30 minutes and drain battery.

| Hardware Type | Sleep Support | Result |
|--------------|---------------|--------|
| Enterprise AP (TP-Link Omada) | Excellent | Cameras sleep 2-5 hours |
| Consumer USB (RTL8812AU) | Poor | Cameras reconnect every 30 min |
| Intel integrated WiFi | Varies | Usually poor |

**Recommended:** TP-Link Omada EAP225 or similar enterprise AP
- Proper 802.11n power save support
- Cameras sleep for hours, wake instantly on motion
- No configuration needed beyond basic SSID/password

**Not Recommended:** USB WiFi adapters with RTL8812AU/RTL8814AU chipsets
- Great range (30 dBm) but driver issues in AP mode
- Power management conflicts with sleeping clients
- Results in constant reconnections and battery drain

See [WIFI-HARDWARE.md](WIFI-HARDWARE.md) for the full technical investigation.

### Cameras
- Arlo cameras (VMC4030 tested)
- Custom firmware capability required

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/arlo-open-base-station.git
cd arlo-open-base-station

# 2. Copy and edit the configuration
cp config/install.conf.example config/install.conf
nano config/install.conf  # Fill in your values

# 3. Run the installer
sudo scripts/install.sh

# 4. Configure network interface (see below)

# 5. Reboot
sudo reboot
```

## Configuration Reference

Edit `config/install.conf` before running the installer:

| Variable | Description | Example |
|----------|-------------|---------|
| `USERNAME` | Your Linux username | `randy` |
| `WIFI_INTERFACE` | WiFi adapter for AP | `wlan0`, `wlx00c0cab955c4` |
| `ETH_INTERFACE` | Ethernet for SSH/internet | `eth0`, `enp0s25` |
| `WIFI_SSID` | Network name for cameras | `NETGEAR99` |
| `WIFI_PASSWORD` | WPA2 password | `yourpassword` |
| `RECORDINGS_PATH` | Where to store videos | `/home/user/arlo-recordings` |
| `CAMERA_SERIAL_1` | Camera serial number | `5EM1877DA41B6` |
| `CAMERA_NAME_1` | Friendly name | `Front Door` |

### Optional: Push Notifications

For mobile alerts via [ntfy](https://ntfy.sh):

| Variable | Description |
|----------|-------------|
| `NTFY_ENABLED` | `true` or `false` |
| `NTFY_URL` | `https://ntfy.sh` or self-hosted |
| `NTFY_TOPIC` | Your notification topic |

### Optional: Remote Access

For exposing the viewer via [bore](https://github.com/ekzhang/bore) tunnel:

| Variable | Description |
|----------|-------------|
| `BORE_REMOTE_SERVER` | Your server running bore |
| `BORE_VIEWER_PORT` | Remote port for viewer |
| `BORE_NTFY_PORT` | Remote port for ntfy |

## Post-Installation: Network Setup

After the installer completes, configure your WiFi interface IP address.

### Ubuntu 18.04+ (netplan)

Create `/etc/netplan/03-arlo-ap.yaml`:

```yaml
network:
  version: 2
  wifis:
    YOUR_WIFI_INTERFACE:
      dhcp4: false
      addresses:
        - 172.14.0.1/24
```

Apply with: `sudo netplan apply`

### Other Systems

```bash
sudo ip link set YOUR_WIFI_INTERFACE up
sudo ip addr add 172.14.0.1/24 dev YOUR_WIFI_INTERFACE
```

## Verification

After reboot, verify the installation:

```bash
# Check services are running
systemctl status arlo arlo-viewer

# Check WiFi AP is broadcasting
iw dev YOUR_WIFI_INTERFACE info

# Check DHCP is ready
systemctl status dnsmasq

# View the web interface
curl http://localhost:3003
```

## Camera Setup

1. Power on your Arlo camera
2. Camera should connect to your WiFi network (SSID from config)
3. Check DHCP lease: `cat /var/lib/misc/dnsmasq.leases`
4. Check registration: `curl http://localhost:5000/api/cameras/status`

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or check logs:

```bash
# Main service log
tail -f /tmp/arlo-service.log

# Viewer service log
journalctl -u arlo-viewer -f

# DHCP/DNS log
journalctl -u dnsmasq -f
```
