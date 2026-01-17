# Dependencies

All dependencies are installed automatically by `scripts/install.sh`. This document lists them for reference.

## External Services (Optional)

These are separate projects that can be self-hosted or used as public services:

| Service | Purpose | Options |
|---------|---------|---------|
| **[ntfy](https://github.com/binwiederhier/ntfy)** | Push notifications to mobile | Use public `ntfy.sh` or self-host |
| **[bore](https://github.com/ekzhang/bore)** | TCP tunneling for remote access | Self-host server + local client |

### ntfy Setup

For push notifications, you have two options:

**Option A: Public ntfy.sh (easiest)**
- No setup required
- Set `NtfyUrl: "https://ntfy.sh"` in config
- Pick a unique topic name

**Option B: Self-hosted ntfy**
```bash
# Install ntfy server
curl -sSL https://install.ntfy.sh | sh

# Or via Docker
docker run -p 8085:80 binwiederhier/ntfy serve
```

### bore Setup (for remote access)

If you want to access the viewer from outside your network:

```bash
# Install bore client (on arlo-base)
cargo install bore-cli

# On your public server, run bore server
bore server --min-port 8080 --max-port 8090

# bore tunnels are configured in install.conf
```

## System Packages (apt)

| Package | Purpose |
|---------|---------|
| `hostapd` | WiFi access point daemon |
| `dnsmasq` | DHCP and DNS server for camera network |
| `netfilter-persistent` | Persistent iptables firewall rules |
| `iptables-persistent` | Saves/restores firewall on boot |
| `python3-venv` | Python virtual environment support |
| `python3-full` | Complete Python 3 installation |
| `ffmpeg` | Video processing (thumbnails, format conversion) |
| `nodejs` | Runtime for arlo-viewer web server |
| `npm` | Node.js package manager |
| `gstreamer1.0-tools` | GStreamer CLI tools (gst-launch-1.0) |
| `gstreamer1.0-plugins-base` | Core GStreamer plugins |
| `gstreamer1.0-plugins-good` | Quality GStreamer plugins (RTSP, HLS) |
| `gstreamer1.0-plugins-bad` | Additional GStreamer plugins |
| `python3-gst-1.0` | Python bindings for GStreamer |

### Optional

| Package | Purpose |
|---------|---------|
| `bore` | TCP tunnel for remote access (install via cargo) |

## Python Packages (pip)

Located in `src/arlo-cam-api/requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| `Flask` | 1.1.2 | Web framework for REST API |
| `PyYAML` | 5.3.1 | YAML config file parsing |
| `pyaml` | 20.4.0 | YAML utilities |
| `requests` | 2.25.0 | HTTP client for webhooks/ntfy |
| `webhooks` | 0.4.2 | Webhook dispatch |
| `python-vlc` | 3.0.11115 | VLC bindings (legacy, may not be used) |
| `Jinja2` | 2.11.2 | Flask templating |
| `Werkzeug` | 1.0.1 | Flask WSGI utilities |
| `click` | 7.1.2 | CLI framework (Flask dependency) |
| `itsdangerous` | 1.1.0 | Flask session signing |
| `MarkupSafe` | 1.1.1 | Jinja2 dependency |
| `certifi` | 2020.11.8 | SSL certificates |
| `chardet` | 3.0.4 | Character encoding detection |
| `idna` | 2.10 | Internationalized domain names |
| `urllib3` | 1.26.2 | HTTP library |
| `wrapt` | 1.12.1 | Decorator utilities |
| `standardjson` | 0.3.1 | JSON utilities |
| `cached-property` | 1.5.2 | Cached property decorator |

## Node.js Packages (npm)

Located in `src/arlo-viewer/package.json`:

| Package | Version | Purpose |
|---------|---------|---------|
| `express` | ^4.18.2 | Web server framework |
| `js-yaml` | ^4.1.1 | YAML parsing for config |

## Why GStreamer Instead of FFmpeg?

Both are installed, but GStreamer is used for live streaming because:

- **FFmpeg** sends RTCP keep-alive packets every 10 seconds (hardcoded)
- **Arlo cameras** require RTCP every 5 seconds or they stop streaming
- **GStreamer** correctly sends RTCP at 5-second intervals

FFmpeg is still used for thumbnail generation from recorded videos.

## Version Notes

The Python dependencies use older versions for compatibility with the original arlo-cam-api fork. Consider updating for security patches, but test thoroughly as Flask 1.x → 2.x has breaking changes.

## Credits / Based On

| Project | Author | Purpose |
|---------|--------|---------|
| [arlo-cam-api](https://github.com/Meatballs1/arlo-cam-api) | Meatballs1 | Original Arlo camera protocol implementation |
| [ntfy](https://github.com/binwiederhier/ntfy) | binwiederhier | Push notification server |
| [bore](https://github.com/ekzhang/bore) | ekzhang | TCP tunnel for remote access |

The `arlo-cam-api` project reverse-engineered the Arlo camera protocol and provided the foundation for this base station replacement. This project extends it with:
- GStreamer-based live streaming (fixes RTCP timing issues)
- Web-based recording viewer
- ntfy push notifications with thumbnails
- Improved WiFi hardware compatibility documentation
