# Arlo Camera System v1.0 - Complete Documentation

**Date:** January 9, 2026
**Status:** Production Ready - v1.0 Milestone Achieved

## Overview

DIY Arlo base station replacement running on 'arlo-base' - your local machine. Cameras connect via TP-Link Omada EAP225 WiFi access point. System provides motion detection, recording, battery monitoring, and web-based status dashboard.

---

## Major Components

### 1. Backend Server (arlo-cam-api)
**Location:** `/opt/arlo-cam-api/`
**Service:** `arlo.service`
**Technology:** Python 3, Flask, SQLite

**Key Features:**
- Camera registration and communication (port 4000)
- Motion-triggered recording with RTSP capture
- Battery warning notifications
- Webhook integration for alerts
- RESTful API for camera control and status

### 2. Web Dashboard (arlo-viewer)
**Location:** `~/arlo-viewer/`
**Served at:** `https://security.example.com/` (via bore tunnel)
**Technology:** Node.js, Express, HTML/JavaScript

**Key Features:**
- Real-time camera status display
- Arm/disarm motion detection controls
- Battery levels with visual indicators
- Signal strength display
- MAC address and IP tracking
- Sleep time indicator (time since last check-in)
- Video playback interface

### 3. Connectivity Checker
**Location:** `/opt/arlo-cam-api/helpers/connectivity_checker.py`
**Method:** ARP table monitoring (every 5 minutes)

**Purpose:** Determines camera online/offline status based on network presence rather than registration timeout

---

## Database Schema

**Location:** `/opt/arlo-cam-api/arlo.db`

### Camera Table Columns:
```sql
ip              TEXT    -- Current IP address (or UNKNOWN if offline)
serialnumber    TEXT    -- Unique camera serial number (PRIMARY KEY)
hostname        TEXT    -- Camera hostname (e.g., VMC4030-XXXXX)
status          TEXT    -- JSON blob of latest status message
register_set    TEXT    -- JSON blob of registration data
friendlyname    TEXT    -- User-friendly name (e.g., "Back Yard")
last_seen       REAL    -- Julian day timestamp of last contact
mac_address     TEXT    -- WiFi MAC address (for ARP checking)
connected       INTEGER -- 1=online (in ARP table), 0=offline
armed           INTEGER -- 1=armed, 0=disarmed (motion detection state)
```

**Example Cameras:**
- Back Yard: `YOUR_SERIAL_1` / MAC: `aa:bb:cc:dd:ee:01`
- Front Door: `YOUR_SERIAL_2` / MAC: `aa:bb:cc:dd:ee:02`

---

## Armed/Disarmed State Tracking

### Backend Implementation:
1. **Database:** `armed` column (INTEGER, default 1)
2. **Camera Registration:** Sets `armed=1` when camera connects (matches REGISTER_SET_INITIAL)
3. **API Endpoints:**
   - `/camera/<serial>/arm` - Arms camera, sets `armed=1`
   - `/camera/<serial>/disarm` - Disarms camera, sets `armed=0`
4. **Status API:** `/cameras/status` returns `"armed": true/false`

### Frontend Implementation:
1. **Button Colors:**
   - Armed state: "Armed" button = Green, "Disarm" button = Dark
   - Disarmed state: "Disarmed" button = Green, "Arm" button = Dark
2. **State Persistence:** JavaScript tracks state in `cameraStates` object, initialized from API
3. **Visual Feedback:** Button text changes to "-ed" form for active state

**Camera Settings (REGISTER_SET_INITIAL):**
```json
{
  "PIRTargetState": "Armed",          // Motion detection via PIR sensor
  "VideoMotionEstimationEnable": true, // Motion detection via video analysis
  "AudioTargetState": "Disarmed",     // Audio alert detection disabled by default
  "PIRStartSensitivity": 80,
  "VideoMotionSensitivity": 80
}
```

---

## Connectivity Detection

### ARP-Based Online/Offline Status

**Previous Method (DEPRECATED):** Registration timeout - cameras marked offline if no registration in 45 minutes

**Current Method (v1.0):** ARP table checking every 5 minutes

**Implementation:**
```python
# /opt/arlo-cam-api/helpers/connectivity_checker.py
def check_arp(mac_address):
    result = subprocess.run(['arp', '-n'], capture_output=True, text=True, timeout=1)
    return mac_address.lower() in result.stdout.lower()

# Updates camera.connected field: 1=online, 0=offline
```

**Why This Works:**
- Cameras maintain WiFi association even when sleeping (2-5 hour sleep cycles)
- ARP table entries persist as long as device is connected to WiFi
- More accurate than registration-based timeout since cameras sleep between registrations

**Sleep Cycles (with Omada EAP225):**
- Back Yard: 2-5 hours between registrations
- Front Door: 2-5 hours between registrations
- Previous USB WiFi: Only 30 minutes (hardware incompatibility with battery cameras)

---

## WiFi Infrastructure

### Current Setup (January 2026):
**Access Point:** TP-Link Omada EAP225
**SSID:** NETGEAR99
**Country Code:** US/EU (varies by region)
**DHCP:** Provided by dnsmasq on arlo-base via ethernet-to-AP interface

**Key Discovery:** USB WiFi adapter (Alfa AWUS036ACH with RTL8812AU driver) caused 30-minute reconnection issue due to incompatibility with battery-powered cameras. Omada resolved this completely.

**Removed Hardware:**
- Alfa AWUS036ACH USB WiFi adapter (stored)
- hostapd configuration (obsolete)
- USB WiFi firewall rules (removed from iptables/nftables)

---

## Recording System

### Motion-Triggered Recording:
1. **Detection:** Camera sends `pirMotionAlert` to server
2. **ACK Response:** Server immediately ACKs to prevent camera timeout
3. **Port Monitoring:** Background thread monitors port 554 for RTSP stream (max 3s wait)
4. **Recording:** ffmpeg captures 10-second video + thumbnail via RTSP
5. **Webhook Notification:** Alert sent to ntfy.sh with video metadata

**Recording Path:** `/mnt/arlo-recordings/`
**Format:** `arlo-{serial}-{timestamp}.mkv`
**Thumbnail:** `arlo-{serial}-{timestamp}.jpg` (frame at 1 second)

**Stream Timeout Settings:**
- `MaxStreamTimeLimit`: 1800 seconds (30 minutes) - rolled back from 24 hours
- `MaxMotionStreamTimeLimit`: 120 seconds
- `DefaultMotionStreamTimeLimit`: 10 seconds

---

## Battery Warning System

**Configuration:** `/opt/arlo-cam-api/config.yaml`
```yaml
BatteryWarningEnabled: true
BatteryWarningLow: 25        # First warning at 25%
BatteryWarningCritical: 10   # Critical warning at 10%
```

**Behavior:**
- Warnings sent via webhook when thresholds crossed
- State tracking prevents duplicate warnings
- Resets when battery recovers above low threshold

---

## API Endpoints

### Camera Status:
- `GET /cameras/status` - All cameras with comprehensive status
- `GET /camera/<serial>` - Individual camera status
- `GET /camera/<serial>/registration` - Registration data

### Camera Control:
- `POST /camera/<serial>/arm` - Enable motion detection
- `POST /camera/<serial>/disarm` - Disable motion detection
- `POST /camera/<serial>/statusrequest` - Request fresh status
- `POST /camera/<serial>/quality` - Set video quality (low/medium/high/subscription)
- `POST /camera/<serial>/pirled` - Configure PIR LED
- `POST /camera/<serial>/userstreamactive` - Control user stream

### Status Response Format:
```json
{
  "serial_number": "YOUR_SERIAL_1",
  "friendly_name": "Back Yard",
  "hostname": "VMC4030-XXXXX",
  "ip": "172.14.0.102",
  "mac_address": "aa:bb:cc:dd:ee:01",
  "online": true,
  "armed": true,
  "battery_percent": 92,
  "battery_voltage": 7.814,
  "signal_strength": 4,
  "charging_state": "Off",
  "charger_tech": "None",
  "last_seen": "2026-01-10T06:38:28.115986Z"
}
```

---

## Status Dashboard Features

**URL:** `https://security.example.com/status.html`

### Display Elements:
1. **Camera Header:**
   - Friendly name
   - Online/Offline badge with sleep time indicator
   - Example: `(sleep 15m) [Online]`

2. **Motion Detection Controls:**
   - Arm/Disarm buttons with color-coded state
   - Active state shown in green with "-ed" suffix
   - Action button shown in dark gray

3. **Battery Display:**
   - Visual progress bar (green/yellow/red)
   - Percentage display
   - Charging state indicator (⚡ when charging)
   - Voltage reading

4. **Signal Strength:**
   - Visual bar indicator (5 bars)
   - Based on SignalStrengthIndicator value

5. **Network Information:**
   - IP Address
   - MAC Address (monospace font)
   - Hostname
   - Serial Number

6. **Auto-Refresh:**
   - Updates every 30 seconds
   - Preserves armed/disarmed state between refreshes

### Sleep Time Calculation:
```javascript
function formatSleepTime(lastSeenIso) {
    // < 60 minutes: "(sleep Xm)"
    // 60 min - 24 hours: "(sleep Xh)"
    // > 24 hours: "(sleep Xd)"
}
```

---

## File Locations

### Backend:
```
/opt/arlo-cam-api/
├── arlo.db                          # SQLite database
├── config.yaml                      # Configuration file
├── server.py                        # Main server (registration, alerts, recording)
├── api/
│   └── api.py                       # Flask REST API
├── arlo/
│   ├── camera.py                    # Camera class (persist, arm/disarm, etc.)
│   ├── messages.py                  # Protocol message definitions
│   └── socket.py                    # Arlo protocol socket handling
└── helpers/
    ├── connectivity_checker.py      # ARP-based online detection
    ├── recorder.py                  # RTSP recording
    ├── webhook_manager.py           # Notification handling
    └── safe_print.py                # Thread-safe printing
```

### Frontend:
```
~/arlo-viewer/
├── server.js                        # Express server
├── public/
│   ├── index.html                   # Video player interface
│   └── status.html                  # Camera status dashboard
└── package.json
```

### Service:
```
/etc/systemd/system/arlo.service     # systemd service definition
```

---

## System Configuration

### Camera Aliases:
**File:** `/opt/arlo-cam-api/config.yaml`
```yaml
CameraAliases:
  'YOUR_SERIAL_1': 'Back Yard'
  'YOUR_SERIAL_2': 'Front Door'
```

### WiFi Settings:
```yaml
WifiCountryCode: 'EU'
```

### Recording Settings:
```yaml
RecordOnMotionAlert: true
RecordOnAudioAlert: false
MotionRecordingTimeout: 10
AudioRecordingTimeout: 15
RecordingBasePath: '/mnt/arlo-recordings/'
```

### Webhook Configuration:
```yaml
WebHookUrls:
  - 'https://ntfy.example.com/arlo-alerts'
```

---

## Important Discoveries & Lessons Learned

### 1. USB WiFi Hardware Incompatibility (December 2025 - January 2026)
**Problem:** Cameras reconnecting every 30 minutes with Alfa AWUS036ACH USB adapter
**Root Cause:** RTL8812AU driver incompatible with battery camera power management
**Solution:** Switched to TP-Link Omada EAP225 - cameras now sleep 2-5 hours
**Key Insight:** Problem was WiFi hardware layer, not protocol/configuration

### 2. Status Detection Method Evolution
**Original:** Registration timeout (45 minutes)
**Problem:** Cameras sleep 2-5 hours, always showed as offline
**Solution:** ARP table checking - detects WiFi connection, not just registration
**Result:** Accurate online/offline status regardless of sleep cycle

### 3. Stream Timeout Settings
**Original Research:** Set to 24 hours during battery optimization attempts
**Final Setting:** Rolled back to 30 minutes (1800 seconds)
**Reason:** No impact on battery life, 30 minutes is appropriate for motion-triggered recording

### 4. Armed/Disarmed State Persistence
**Challenge:** Cameras don't report PIRTargetState in status messages
**Solution:** Track in database, updated on arm/disarm API calls
**Default:** Armed (matches REGISTER_SET_INITIAL message sent on connection)

---

## Backup History

### v1.0 Snapshot (January 9, 2026)
**Features:**
- Armed/disarmed state tracking with visual feedback
- ARP-based connectivity detection
- MAC address display
- Sleep time indicator
- Complete status dashboard with color-coded controls

**Previous Backups:**
- `~/backups/arlo-cam-api/20260101-*` - USB WiFi investigation period
- `~/backups/arlo-cam-api/20260102-*` - Pre-Omada configuration

---

## Service Management

### Start/Stop/Restart:
```bash
sudo systemctl start arlo
sudo systemctl stop arlo
sudo systemctl restart arlo
sudo systemctl status arlo
```

### View Logs:
```bash
tail -f /tmp/arlo-service.log
journalctl -u arlo -f
```

### Database Access:
```bash
sudo -u arlo sqlite3 /opt/arlo-cam-api/arlo.db
```

---

## Network Architecture

### arlo-base (your local machine)
- Runs arlo-cam-api service (Python/Flask)
- Runs arlo-viewer service (Node.js/Express)
- Provides DHCP to cameras via dnsmasq
- Receives camera registrations on port 4000
- Receives motion alerts and status updates
- Captures RTSP streams on port 554

### Bore Tunnels (systemd services)
- `security-bore-tunnel.service` - Viewer tunnel (local :3003 → remote:8084)
- `ntfy-bore-tunnel.service` - Ntfy tunnel (local :8085 → remote:8085)

### External Access:
- `https://security.example.com/` - Video viewer and status dashboard
- `https://ntfy.example.com/arlo-alerts` - Push notifications

---

## Future Enhancement Ideas

### Potential Improvements:
1. Historical battery level trending/graphs
2. Recording retention management (auto-delete old videos)
3. Activity zone configuration UI
4. Multiple notification channels (email, SMS)
5. Camera firmware update mechanism
6. Multi-camera snapshot comparison view
7. Recording search by date/time/camera
8. Export configuration/settings backup

### Not Recommended:
- USB WiFi adapter replacement (Omada works perfectly)
- Extended stream timeouts (no battery benefit observed)
- Protocol-layer optimizations (hardware was the issue)

---

## Camera Specifications

**Model:** Netgear Arlo VMC4030
**Firmware:** 1.092.1.0_9_120d8b7
**Hardware Revision:** H14
**Battery:** Rechargeable, 7.8-7.9V typical
**WiFi:** 2.4GHz, supports 802.11n

**Capabilities:**
- IR LED night vision
- PIR motion detection
- Video motion estimation
- H.264 streaming (RTSP)
- JPEG snapshots
- Temperature sensor
- Microphone and speaker
- Battery charging (solar panel compatible)

---

## Support & Troubleshooting

### Common Issues:

**Camera shows offline but is connected:**
- Check ARP table: `arp -n | grep <mac_address>`
- Wait for next connectivity check (5 minute interval)
- Verify MAC address in database is correct

**Recording not triggering on motion:**
- Check camera armed state via API
- Verify RecordOnMotionAlert is true in config.yaml
- Check ffmpeg logs in `/mnt/arlo-recordings/`
- Confirm RTSP port 554 is accessible

**Battery draining faster than expected:**
- Check motion event frequency in logs
- Verify PIRStartSensitivity is appropriate (default 80)
- Check SignalStrengthIndicator (weak signal = more power)
- Confirm MaxStreamTimeLimit is 1800 (not 86400)

**Status dashboard not updating:**
- Check browser console for JavaScript errors
- Verify `/cameras/status` API endpoint returns data
- Confirm arlo service is running
- Check bore tunnel services: `systemctl status security-bore-tunnel ntfy-bore-tunnel`

---

## Conclusion

This v1.0 system provides a fully functional DIY Arlo base station replacement with enterprise-grade features, reliable connectivity detection, and an intuitive web interface. The system has been battle-tested and resolved all major issues (USB WiFi incompatibility, status detection accuracy, state persistence).

**System is production-ready and stable as of January 9, 2026.**
