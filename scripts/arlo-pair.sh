#!/bin/bash
# Pair (sync) Arlo cameras with this base station via WPS push-button.
#
#   sudo arlo-pair [seconds]     # default 120
#
# Arlo cameras learn the camera SSID + password through WPS when you press their
# Sync button (Pro 3/Pro 4: the Sync button by the battery after a factory reset;
# see the camera's "sync to SmartHub" instructions). Enterprise APs such as
# Omada don't do WPS, so this opens a temporary WPS AP with the SAME SSID/PSK on a
# spare WiFi adapter. Once paired the camera roams to the enterprise AP by itself.
#
# Watch it register:  tail -f /tmp/arlo-service.log
set -e
DURATION="${1:-120}"
CONF=/etc/hostapd/hostapd.conf

if [ "$EUID" -ne 0 ]; then echo "run as root"; exit 1; fi
if [ ! -f "$CONF" ]; then
    echo "No $CONF - set PAIRING_WIFI_INTERFACE (external mode) or AP_MODE=hostapd and re-run install.sh"
    exit 1
fi

STARTED_HERE=0
if ! systemctl is-active --quiet hostapd; then
    IFACE="$(sed -n 's/^interface=//p' "$CONF")"
    if ! ip link show "$IFACE" >/dev/null 2>&1; then
        echo "WiFi interface $IFACE not present (USB adapter plugged in / passed through to the VM?)"
        exit 1
    fi
    rfkill unblock wifi 2>/dev/null || true
    systemctl start hostapd
    STARTED_HERE=1
    sleep 3
fi

cleanup() {
    hostapd_cli wps_cancel >/dev/null 2>&1 || true
    if [ "$STARTED_HERE" = 1 ]; then
        echo "Stopping temporary pairing AP"
        systemctl stop hostapd
    fi
}
trap cleanup EXIT

SSID="$(sed -n 's/^ssid=//p' "$CONF")"
echo "WPS push-button open on SSID '$SSID' for ${DURATION}s."
echo ">>> Press and hold the Sync button on the camera now (one camera at a time)."
hostapd_cli wps_pbc >/dev/null

END=$((SECONDS + DURATION))
LEASES=/var/lib/misc/dnsmasq.leases
BEFORE="$(cat "$LEASES" 2>/dev/null | wc -l)"
while [ $SECONDS -lt $END ]; do
    STATUS="$(hostapd_cli wps_get_status 2>/dev/null | sed -n 's/^Last WPS result: //p')"
    if [ "$STATUS" = "Success" ]; then
        echo "WPS success - camera got the credentials. Waiting for DHCP + registration..."
        for _ in $(seq 1 30); do
            sleep 2
            if [ "$(cat "$LEASES" 2>/dev/null | wc -l)" -gt "$BEFORE" ]; then
                tail -1 "$LEASES"
                break
            fi
        done
        grep -E "Registration from|Model .* -> profile|registerSet" /tmp/arlo-service.log 2>/dev/null | tail -4 || true
        echo "Keep the camera close for a minute; it will move to the main AP afterwards."
        exit 0
    fi
    sleep 2
done
echo "No camera completed WPS within ${DURATION}s."
exit 1
