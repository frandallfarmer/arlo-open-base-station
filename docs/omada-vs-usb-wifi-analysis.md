# WiFi AP Configuration Comparison: Omada EAP225 vs USB WiFi (hostapd)

## Network Topology
- **Omada EAP225**: Connected via USB Ethernet (enx00051b516407) at 172.14.0.2/24
- **USB WiFi Adapter**: Alfa AWUS036ACH (wlx00c0cab955c4) - RTL8812AU chipset
- **Both broadcast**: SSID "NETGEAR99" on channel 11 (2.462 GHz)
- **Cameras connect to**: Omada (via enx00051b516407 interface)

## Critical Differences

### 1. **Capability Flags**
| Parameter | Omada (cc:ba:bd:cf:b9:5e) | USB WiFi (00:c0:ca:b9:55:c4) |
|-----------|---------------------------|------------------------------|
| Capability | 0x0431 | 0x0411 |
| ShortPreamble | **YES** ✓ | NO |
| ShortSlotTime | YES ✓ | YES ✓ |
| Privacy | YES ✓ | YES ✓ |

**ShortPreamble (0x0020 bit)**: Present on Omada, missing on hostapd!
- Reduces overhead for packet transmission
- May affect power management behavior

### 2. **HT (802.11n) Capabilities**
| Parameter | Omada | USB WiFi |
|-----------|-------|----------|
| HT Capabilities | 0x1ac | 0x2c |
| **TX STBC** | **YES** ✓ | NO |
| **RX STBC** | 1-stream | NO |
| AMPDU time spacing | 8 usec | 16 usec |
| MCS rate indexes | 0-23 (3x3 MIMO) | 0-15 (2x2 MIMO) |

**STBC (Space-Time Block Coding)**: Improves reliability in multipath environments
- Omada supports transmit STBC
- hostapd does not advertise STBC capability

### 3. **HT Operation**
| Parameter | Omada | USB WiFi |
|-----------|-------|----------|
| RIFS | 1 (enabled) | 0 (disabled) |
| non-GF present | 1 | 0 |

**RIFS (Reduced Interframe Space)**: Allows shorter gaps between frames
- Omada: Enabled
- hostapd: Disabled

### 4. **WPA/RSN Configuration**
| Parameter | Omada | USB WiFi |
|-----------|-------|----------|
| WPA support | YES (v1) | NO |
| RSN Capabilities | 0x0000 | 0x000c |
| PTKSA Replay Counter | 1-bit | 16-bit |

**Important**: Omada advertises both WPA and WPA2 (RSN)
- hostapd config has `wpa_pairwise=TKIP` but it's not being advertised
- Omada shows WPA with CCMP cipher (stronger than expected)

### 5. **ERP Information**
| Parameter | Omada | USB WiFi |
|-----------|-------|----------|
| ERP flags | `<no flags>` | `Barker_Preamble_Mode` |

**Barker Preamble Mode**: Compatibility mode for older 802.11b devices
- Omada: Clean (modern mode)
- hostapd: Using legacy Barker preamble

### 6. **WMM/QoS** (Both identical)
Both support:
- u-APSD (Unscheduled Automatic Power Save Delivery) ✓
- Identical queue parameters

### 7. **Extended Capabilities**
| Capability | Omada | USB WiFi |
|-----------|-------|----------|
| HT Information Exchange | YES ✓ | NO |
| Operating Mode Notification | YES ✓ | NO |

### 8. **WPS Configuration**
| Parameter | Omada | USB WiFi |
|-----------|-------|----------|
| WPS advertised | NO | YES |
| WPS State | N/A | Configured |

---

## Power Management Analysis

### u-APSD (Unscheduled Automatic Power Save Delivery)
**Both APs support u-APSD** - allows clients to sleep and wake on their own schedule
- Critical for battery-powered devices like Arlo cameras
- Cameras can request data delivery without staying awake

### Missing DTIM Information
- **Neither AP shows DTIM period in probe responses**
- DTIM is typically in beacon frames (not probe responses)
- Default DTIM period for hostapd: 2 (if not configured)
- Omada DTIM period: Unknown (need beacon capture)

**DTIM (Delivery Traffic Indication Message)**:
- Tells sleeping clients when to wake up for broadcast/multicast
- Higher DTIM = clients sleep longer (better battery)
- If Omada has higher DTIM, cameras sleep longer between wakeups

---

## Likely Causes of 30-Minute Reconnection on USB WiFi

### Theory 1: ShortPreamble + Modern ERP Mode
- Omada's ShortPreamble may be more compatible with Arlo cameras
- hostapd using legacy Barker preamble mode may cause timing issues
- **Fix**: Add `preamble=1` to hostapd.conf (enable short preamble)

### Theory 2: STBC Support
- Omada's TX STBC provides better signal reliability
- Cameras may maintain connection longer with STBC
- **Fix**: Enable STBC in hostapd (if RTL8812AU driver supports)

### Theory 3: RIFS Enabled
- Reduced Interframe Spacing improves efficiency
- May affect power save timing
- **Fix**: Add `ht_capab=[RIFS]` to hostapd.conf

### Theory 4: Extended Capabilities
- "HT Information Exchange Supported" on Omada
- May enable better power management negotiation
- **Fix**: Investigate hostapd extended capabilities support

### Theory 5: WPA vs WPA2 Advertisement
- Omada advertises both WPA (v1) and WPA2 (RSN)
- hostapd only advertises WPA2 despite config having TKIP
- Cameras may prefer seeing both for compatibility
- **Fix**: Verify WPA1 is actually enabled in hostapd

### Theory 6: DTIM Period (Unverified)
- If Omada uses DTIM period > 2, cameras sleep longer
- Default hostapd DTIM=2 may be too aggressive
- **Fix**: Increase DTIM period (requires beacon capture to verify)

---

## Hostapd Configuration Missing Parameters

Current `/etc/hostapd/hostapd.conf` does not specify:
- `preamble` (defaults to long preamble)
- `dtim_period` (defaults to 2)
- `beacon_int` (defaults to 100 - matches Omada ✓)
- `ht_capab` (only `ieee80211n=1` set, no specific HT features)

### Recommended Additions (Investigation Phase):
```conf
# Enable short preamble (like Omada)
preamble=1

# Try higher DTIM for better power save
dtim_period=3

# Enable HT capabilities closer to Omada
ht_capab=[HT20][SHORT-GI-20][TX-STBC][RX-STBC1][MAX-AMSDU-3839]
```

**NOTE**: Do NOT apply these yet - investigation only!

---

## Next Steps for Investigation

1. **Capture beacon frames** from Omada to see actual DTIM period
2. **Test if cameras still work on hostapd** with recommended config changes
3. **Monitor registration intervals** after each config change
4. **Check RTL8812AU driver capabilities** for STBC support
5. **Verify WPA1 support** in current hostapd configuration

---

## Conclusion

The Omada EAP225 has several advantages over the current hostapd configuration:

**Power Management Related**:
- u-APSD support (both have this ✓)
- Unknown DTIM period (could be higher than hostapd's default 2)

**Signal Quality Related**:
- TX/RX STBC support (better reliability)
- RIFS enabled (more efficient transmission)
- Shorter AMPDU spacing (8 vs 16 usec)

**Compatibility Related**:
- ShortPreamble capability
- No legacy Barker preamble mode
- Both WPA1 and WPA2 advertised
- Extended capabilities (HT Info Exchange, OMN)

The **30-minute reconnection issue on USB WiFi** is likely caused by one or more of these differences. The Omada's superior 802.11n implementation and power management capabilities appear to allow cameras to maintain stable connections for hours without re-registering.
