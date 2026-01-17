# USB WiFi Hardware Removal Guide

**Date**: January 9, 2026  
**Reason**: RTL8812AU incompatible with Arlo camera power management  
**Replacement**: TP-Link Omada EAP225 (already in production)

---

## Hardware to Remove

### Physical Device
**Alfa AWUS036ACH USB WiFi Adapter**
- **Interface**: wlx00c0cab955c4
- **MAC**: 00:c0:ca:b9:55:c4
- **Chipset**: Realtek RTL8812AU (88XXau kernel module)
- **Current Status**: Broadcasting NETGEAR99 SSID, but no cameras connected
- **USB Location**: Identify via `lsusb` before unplugging

**Current USB Connection:**
```bash
lsusb | grep -i "realtek\|rtl\|alfa"
# Will show bus and device number
```

---

## Services to Disable

### 1. hostapd.service
**Purpose**: WiFi Access Point daemon for USB adapter  
**Config**: `/etc/hostapd/hostapd.conf`  
**Status**: Currently running, broadcasting NETGEAR99

**Stop and disable:**
```bash
sudo systemctl stop hostapd
sudo systemctl disable hostapd
```

**Config file** (keep for reference, mark as obsolete):
```bash
sudo mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.OBSOLETE-20260109
```

### 2. dnsmasq.service (PARTIAL - Review First!)
**Purpose**: DHCP/DNS server  
**Config**: `/etc/dnsmasq.conf`  
**Status**: Currently running for 172.14.0.0/24 network

**⚠️ IMPORTANT**: dnsmasq may still be needed for Omada!

**Current dnsmasq config:**
```bash
cat /etc/dnsmasq.conf
```

**Check if Omada needs it:**
- Omada is connected via USB Ethernet (enx00051b516407) at 172.14.0.2/24
- Cameras have DHCP leases: 172.14.0.102, 172.14.0.120
- If Omada is providing DHCP → can disable dnsmasq
- If arlo-base is providing DHCP → keep dnsmasq running

**To check:**
```bash
# See if cameras are getting DHCP from Omada or dnsmasq
cat /var/lib/misc/dnsmasq.leases | grep -E "(cc:40:d0:8c:83:e9|a0:04:60:cf:3d:c6)"
```

**If dnsmasq is still needed:**
- Keep running (cameras need DHCP)
- Update config to only listen on enx00051b516407 interface
- Remove wlx00c0cab955c4 from config

**If dnsmasq is NOT needed:**
```bash
sudo systemctl stop dnsmasq
sudo systemctl disable dnsmasq
```

---

## Network Configuration to Remove

### Interface Configuration

**wlx00c0cab955c4 interface** (USB WiFi):
- Currently configured with IP 172.14.0.1/24
- Access point mode
- Transmit power 30 dBm

**After unplugging USB adapter:**
- Interface will disappear automatically
- No manual cleanup needed

### Firewall Rules (Optional Cleanup)

**Check for wlx00c0cab955c4 specific rules:**
```bash
sudo iptables -L INPUT -n -v | grep wlx00c0cab955c4
```

**Current firewall rules for USB WiFi:**
```bash
# Port 4000 (Arlo control)
sudo iptables -D INPUT -i wlx00c0cab955c4 -p tcp --dport 4000 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT

# DHCP
sudo iptables -D INPUT -i wlx00c0cab955c4 -p udp --dport 67 -j ACCEPT

# DNS
sudo iptables -D INPUT -i wlx00c0cab955c4 -p udp --dport 53 -j ACCEPT

# RTSP
sudo iptables -D INPUT -i wlx00c0cab955c4 -p tcp --dport 554 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT

# Save rules
sudo netfilter-persistent save
```

**Note**: These rules may auto-cleanup when interface disappears, but can be manually removed.

---

## Driver/Kernel Module (Optional)

### RTL8812AU Driver (88XXau)

**Installed via DKMS:**
```bash
# Check if installed
dkms status | grep 8812

# Location
ls -la /usr/src/rtl8812au*/
```

**Options:**

**Option 1: Leave installed** (recommended)
- Keeps driver available for future monitor mode use
- Alfa adapter still useful for WiFi security testing
- No harm in keeping it

**Option 2: Remove driver**
```bash
# Find version
DRIVER_VERSION=$(dkms status | grep 8812 | awk -F', ' '{print $2}')

# Remove from DKMS
sudo dkms remove rtl8812au/$DRIVER_VERSION --all

# Delete source
sudo rm -rf /usr/src/rtl8812au*

# Remove repository (if cloned)
rm -rf ~/rtl8812au
```

**Recommendation**: KEEP the driver. The adapter is still excellent for monitor mode (WiFi security auditing, packet capture, etc).

---

## Physical Storage

### Alfa AWUS036ACH Adapter

**Current Use**: WiFi Access Point (unsuitable)  
**Better Use**: WiFi Monitor Mode / Packet Injection  
**Storage**: Keep in anti-static bag, label "For Monitor Mode Only"

**Label suggestion:**
```
Alfa AWUS036ACH (RTL8812AU)
✓ Excellent: Monitor mode, packet injection
✗ Poor: AP mode with power-managed clients
```

---

## Removal Procedure (Step by Step)

### Phase 1: Stop Services (No Physical Changes)

```bash
# 1. Stop hostapd (WiFi AP)
sudo systemctl stop hostapd
sudo systemctl disable hostapd

# 2. Verify no cameras are connected to USB WiFi
iw dev wlx00c0cab955c4 station dump
# Should show empty (cameras already on Omada)

# 3. Check if cameras still work
curl http://localhost:5000/cameras/status
# Should show both cameras (connected via Omada)

# 4. Verify DHCP leases
cat /var/lib/misc/dnsmasq.leases
# Should show cameras with leases
```

### Phase 2: Review dnsmasq (Determine if Still Needed)

```bash
# Check dnsmasq config
grep "interface=" /etc/dnsmasq.conf

# If it specifies wlx00c0cab955c4 only:
#   - dnsmasq can be disabled (Omada likely providing DHCP)
# If it specifies enx00051b516407 or bind-interfaces:
#   - dnsmasq still needed for camera DHCP
```

**If dnsmasq still needed:**
```bash
# Update config to remove USB WiFi interface
sudo nano /etc/dnsmasq.conf
# Change: interface=wlx00c0cab955c4
# To: interface=enx00051b516407

# Restart
sudo systemctl restart dnsmasq
```

**If dnsmasq NOT needed:**
```bash
sudo systemctl stop dnsmasq
sudo systemctl disable dnsmasq
```

### Phase 3: Physical Removal

```bash
# 1. Identify USB device
lsusb | grep -i "realtek\|rtl"
# Note bus and device number

# 2. Power off system (safest) OR hot-unplug
sudo poweroff
# OR
# Simply unplug USB adapter

# 3. After reboot/unplug, verify interface gone
iw dev
# wlx00c0cab955c4 should not appear

# 4. Verify cameras still working
curl http://localhost:5000/cameras/status
# Both cameras should still be functional via Omada
```

### Phase 4: Cleanup (Optional)

```bash
# 1. Rename obsolete configs
sudo mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.OBSOLETE-20260109

# 2. Remove firewall rules (optional, auto-cleanup likely)
sudo iptables -L INPUT -n -v | grep wlx00c0cab955c4
# If rules still exist, remove them manually

# 3. Keep driver installed (for monitor mode use)
# No action needed
```

---

## Verification Checklist

After removal, verify:

- [ ] `iw dev` shows no wlx00c0cab955c4 interface
- [ ] `systemctl status hostapd` shows disabled/inactive
- [ ] `systemctl status dnsmasq` shows appropriate state (active or inactive based on need)
- [ ] `curl http://localhost:5000/cameras/status` shows both cameras
- [ ] Cameras can detect motion and record videos
- [ ] Video files appear in `/home/randy/arlo-recordings/`
- [ ] Push notifications via ntfy still working
- [ ] https://security.thefarmers.org still accessible

---

## Rollback Plan (If Something Breaks)

If cameras stop working after removal:

### Emergency Restore
```bash
# 1. Plug USB adapter back in
# Interface wlx00c0cab955c4 will reappear

# 2. Restore IP
sudo ip link set wlx00c0cab955c4 up
sudo ip addr add 172.14.0.1/24 dev wlx00c0cab955c4
sudo iw dev wlx00c0cab955c4 set txpower fixed 3000

# 3. Restart services
sudo systemctl start dnsmasq
sudo systemctl start hostapd

# 4. Cameras should reconnect within 5 minutes
```

**Note**: This should NOT be needed - cameras are already stable on Omada!

---

## Post-Removal Configuration

### Update Documentation

**CLAUDE.md section** to update:
```markdown
### Arlo Camera System (arlo-base)

**WiFi Access Point**: TP-Link Omada EAP225
- Connected via USB Ethernet (enx00051b516407)
- IP: 172.14.0.2/24
- SSID: NETGEAR99
- Enterprise 802.11n AP with proper power save support

**Camera Connection**:
- Both cameras connected via Omada
- Sleep cycles: 2-5 hours (excellent battery life)
- Wake on motion, no forced reconnections

**Retired Hardware**:
- Alfa AWUS036ACH (RTL8812AU) - unsuitable for AP mode
- Stored for monitor mode use only
```

---

## Summary

### What's Being Removed
- ✗ Alfa AWUS036ACH USB WiFi adapter (physical)
- ✗ hostapd.service (service)
- ? dnsmasq.service (if Omada provides DHCP)
- ✗ USB WiFi firewall rules (optional cleanup)

### What's Being Kept
- ✓ RTL8812AU driver (for monitor mode)
- ✓ Omada EAP225 (production WiFi)
- ✓ arlo.service (camera control)
- ✓ All bore tunnels (security, ntfy)
- ✓ ntfy Docker container
- ? dnsmasq (if needed for DHCP)

### Expected Result
- Cameras continue working perfectly via Omada
- No 30-minute reconnections
- Excellent battery life (2-5 hour sleep cycles)
- System simpler (one less service/hardware to manage)

---

**Created**: January 9, 2026  
**Status**: Ready for execution  
**Risk Level**: LOW (cameras already on Omada, rollback easy)
