# Arlo-Base Cleanup Plan

**Goal**: Clean up arlo-base and create a proper `arlo-open-base-station` project directory for the GitHub repo.

## Current State (Messy)

Files are scattered across multiple locations:

```
~/                              # Home directory (messy)
├── api.py                      # Duplicate/modified copy
├── camera.py                   # Duplicate/modified copy
├── config.yaml                 # Active config
├── arlo.db                     # Active database
├── arlo-cam-api/               # Original forked repo (outdated)
│   ├── arlo/                   # Original source
│   ├── api/
│   └── server.py
├── arlo-viewer/                # Node.js viewer (active)
├── arlo-recordings/            # Recording storage
├── hosting/                    # Mixed droplet + arlo docs
│   ├── CLAUDE.md               # WRONG - this is droplet docs!
│   ├── ARLO-SYSTEM-V1.0.md     # Correct - arlo docs
│   ├── api.py, camera.py...    # More duplicates
│   └── [arlo docs & scripts]
└── [various arlo scripts]
```

## Target State (Clean)

```
~/arlo-open-base-station/       # NEW - GitHub repo root
├── README.md                   # Project overview
├── LICENSE                     # MIT license
├── CHANGELOG.md                # Version history
├── docs/
│   ├── INSTALLATION.md         # Setup guide
│   ├── CONFIGURATION.md        # Config reference
│   ├── TROUBLESHOOTING.md      # Common issues
│   ├── WIFI-HARDWARE.md        # AP hardware notes
│   └── ARCHITECTURE.md         # System design
├── src/
│   ├── arlo-cam-api/           # Python backend
│   │   ├── api.py
│   │   ├── camera.py
│   │   ├── messages.py
│   │   ├── server.py
│   │   ├── stream_manager.py
│   │   └── requirements.txt
│   └── arlo-viewer/            # Node.js frontend
│       ├── server.js
│       ├── package.json
│       └── public/
├── config/
│   ├── config.yaml.example     # Sanitized config template
│   ├── hostapd.conf.example    # WiFi AP template
│   ├── dnsmasq.conf.example    # DHCP template
│   └── netplan.example.yaml    # Network template
├── systemd/
│   ├── arlo.service
│   ├── arlo-viewer.service
│   ├── security-bore-tunnel.service
│   └── ntfy-bore-tunnel.service
└── scripts/
    ├── install.sh              # Automated setup
    ├── start-security-bore-tunnel.sh
    ├── start-ntfy-bore-tunnel.sh
    └── snapshot-arlo.sh

~/                              # Home directory (clean)
├── arlo-open-base-station/     # The project repo
├── arlo-recordings/            # Recording storage (not in repo)
├── arlo.db                     # Active database (not in repo)
├── config.yaml                 # Symlink → repo/config/config.yaml
└── hosting/                    # REMOVED or minimal pointer file

```

## Cleanup Steps

### Step 1: Create New Project Directory
```bash
mkdir -p ~/arlo-open-base-station/{docs,src/arlo-cam-api,src/arlo-viewer,config,systemd,scripts}
```

### Step 2: Source of Truth (CONFIRMED)

The **active running code** is in `/opt/arlo-cam-api/` (owned by `arlo` user):

```
/opt/arlo-cam-api/
├── server.py              # Main server (16KB)
├── config.yaml            # Active config
├── arlo.db                # Database
├── requirements.txt
├── arlo/
│   ├── camera.py          # Camera handling (9KB)
│   ├── messages.py        # Message definitions (23KB)
│   └── socket.py          # Socket handling
├── api/
│   └── api.py             # REST API (13KB)
├── helpers/
│   └── [helper modules]
└── venv/                  # Python virtualenv
```

The files in `~/`, `~/hosting/`, and `~/arlo-cam-api/` are **outdated copies/backups**.

### Step 3: Copy Active Code to New Repo

```bash
# Python backend - preserve directory structure
mkdir -p ~/arlo-open-base-station/src/arlo-cam-api/{arlo,api,helpers}

cp /opt/arlo-cam-api/server.py ~/arlo-open-base-station/src/arlo-cam-api/
cp /opt/arlo-cam-api/requirements.txt ~/arlo-open-base-station/src/arlo-cam-api/
cp /opt/arlo-cam-api/stream.py ~/arlo-open-base-station/src/arlo-cam-api/

cp /opt/arlo-cam-api/arlo/*.py ~/arlo-open-base-station/src/arlo-cam-api/arlo/
cp /opt/arlo-cam-api/api/*.py ~/arlo-open-base-station/src/arlo-cam-api/api/
cp -r /opt/arlo-cam-api/helpers/*.py ~/arlo-open-base-station/src/arlo-cam-api/helpers/ 2>/dev/null

# Node.js frontend
cp -r ~/arlo-viewer/* ~/arlo-open-base-station/src/arlo-viewer/
# Remove node_modules (will be reinstalled)
rm -rf ~/arlo-open-base-station/src/arlo-viewer/node_modules
```

### Step 4: Move Documentation

```bash
# Move arlo docs from ~/hosting/ to new repo
mv ~/hosting/ARLO-SYSTEM-V1.0.md ~/arlo-open-base-station/docs/
mv ~/hosting/WIFI-HARDWARE-DISCOVERY.md ~/arlo-open-base-station/docs/WIFI-HARDWARE.md
mv ~/hosting/INSTALL-BORE-SERVICES.md ~/arlo-open-base-station/docs/
mv ~/hosting/USB-WIFI-*.md ~/arlo-open-base-station/docs/
mv ~/hosting/omada-vs-usb-wifi-analysis.md ~/arlo-open-base-station/docs/
mv ~/hosting/ON-DEMAND-STREAMING-PLAN.md ~/arlo-open-base-station/docs/
```

### Step 5: Create Config Templates

```bash
# Copy and sanitize configs
cp ~/config.yaml ~/arlo-open-base-station/config/config.yaml.example
# Edit to remove sensitive data (IPs, passwords)

cp /etc/hostapd/hostapd.conf ~/arlo-open-base-station/config/hostapd.conf.example
# Edit to use placeholder SSID/password

cp /etc/dnsmasq.conf ~/arlo-open-base-station/config/dnsmasq.conf.example
```

### Step 6: Copy Service Files and Scripts

```bash
# Systemd services
cp /etc/systemd/system/arlo.service ~/arlo-open-base-station/systemd/
cp /etc/systemd/system/arlo-viewer.service ~/arlo-open-base-station/systemd/
cp ~/hosting/*-bore-tunnel.service ~/arlo-open-base-station/systemd/ 2>/dev/null

# Scripts
cp ~/hosting/start-*-bore-tunnel.sh ~/arlo-open-base-station/scripts/
cp ~/snapshot-arlo.sh ~/arlo-open-base-station/scripts/
```

### Step 7: Replace ~/hosting/CLAUDE.md

Replace the droplet CLAUDE.md with an arlo-specific one:

```bash
# Backup old (wrong) CLAUDE.md
mv ~/hosting/CLAUDE.md ~/hosting/CLAUDE.md.droplet-backup

# Create new arlo-specific CLAUDE.md
cat > ~/hosting/CLAUDE.md << 'EOF'
# CLAUDE.md - Arlo Open Base Station

This machine (arlo-base) runs the Arlo Open Base Station project.

## Project Location
- **Main repo**: `~/arlo-open-base-station/`
- **Documentation**: `~/arlo-open-base-station/docs/`
- **Active config**: `~/config.yaml`
- **Recordings**: `~/arlo-recordings/`
- **Database**: `~/arlo.db`

## Quick Reference

**Services:**
- `arlo.service` - Main camera control service (port 4000)
- `arlo-viewer.service` - Web viewer (port 3003)
- `security-bore-tunnel.service` - Tunnel to droplet:8084
- `ntfy-bore-tunnel.service` - Tunnel to droplet:8085

**URLs:**
- https://security.thefarmers.org - Recording viewer
- https://ntfy.thefarmers.org - Push notifications

**For droplet/hosting documentation**: See Ryugi `~/hosting/CLAUDE.md`
EOF
```

### Step 8: Clean Up Old Files

```bash
# Remove duplicates from home directory
rm ~/api.py ~/camera.py ~/messages.py ~/server.py 2>/dev/null

# Archive old hosting directory contents
mkdir -p ~/backups/hosting-cleanup-$(date +%Y%m%d)
mv ~/hosting/*.py ~/backups/hosting-cleanup-$(date +%Y%m%d)/
mv ~/hosting/archive-obsolete-investigations-* ~/backups/hosting-cleanup-$(date +%Y%m%d)/
mv ~/hosting/streaming-* ~/backups/hosting-cleanup-$(date +%Y%m%d)/
mv ~/hosting/*.backup-* ~/backups/hosting-cleanup-$(date +%Y%m%d)/

# Remove or archive the old arlo-cam-api fork
mv ~/arlo-cam-api ~/backups/arlo-cam-api-original-fork
```

### Step 9: Create README and Initialize Git

```bash
cd ~/arlo-open-base-station
git init

# Create README.md
cat > README.md << 'EOF'
# Arlo Open Base Station

Open-source DIY base station for Arlo cameras with extended range and self-hosted features.

## Features
- Custom WiFi access point with 2x commercial base station range
- Motion-triggered recording with thumbnail generation
- Push notifications via ntfy
- Web-based recording viewer
- No cloud dependency

## Requirements
- Linux machine (tested on Ubuntu)
- USB WiFi adapter (recommended: Alfa AWUS036ACH or TP-Link Omada EAP)
- Arlo cameras (VMC4030 tested)

## Quick Start
See [docs/INSTALLATION.md](docs/INSTALLATION.md)

## License
MIT
EOF
```

## Files to Keep in ~/hosting/ (Minimal)

After cleanup, ~/hosting/ should only contain:
- `CLAUDE.md` (new arlo-specific version)
- Possibly a pointer to Ryugi for droplet docs

## Verification

After cleanup:
1. `systemctl status arlo arlo-viewer` - Services still running
2. `https://security.thefarmers.org` - Viewer accessible
3. `ls ~/arlo-open-base-station/` - Clean repo structure
4. `ls ~/hosting/` - Minimal files

---

**Execute this plan on arlo-base using Claude locally there.**
