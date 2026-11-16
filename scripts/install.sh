#!/bin/bash
# Arlo Open Base Station - Installation Script
# Reads config/install.conf and sets up the complete system.
#
#   sudo scripts/install.sh          # interactive
#   sudo scripts/install.sh --yes    # no confirmation prompt
#
# Re-running is safe: an existing config.yaml / arlo.db is kept (a fresh
# config.yaml is written next to it as config.yaml.new for comparison).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/config/install.conf"
ASSUME_YES=0
if [ "$1" = "--yes" ] || [ "$1" = "-y" ]; then ASSUME_YES=1; fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo $0"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Config file not found: $CONFIG_FILE"
    log_info "Copy config/install.conf.example to config/install.conf and fill in your values"
    exit 1
fi

log_info "Loading configuration from $CONFIG_FILE"
# shellcheck disable=SC1090
source "$CONFIG_FILE"

# Defaults for settings added after v1.0 (older install.conf files keep working)
AP_MODE="${AP_MODE:-hostapd}"
INSTALL_DIR="${INSTALL_DIR:-/opt/arlo-cam-api}"
SERVICE_USER="${SERVICE_USER:-arlo}"
LIVE_RTSP_ENABLED="${LIVE_RTSP_ENABLED:-true}"
MEDIAMTX_VERSION="${MEDIAMTX_VERSION:-v1.9.3}"
VIEWER_PASSWORD="${VIEWER_PASSWORD:-changeme}"
NTFY_ENABLED="${NTFY_ENABLED:-false}"
MOTION_TIMEOUT="${MOTION_TIMEOUT:-120}"

if [ "$AP_MODE" = "external" ]; then
    CAMERA_IF="${ARLO_INTERFACE}"
else
    CAMERA_IF="${WIFI_INTERFACE}"
fi
# With a pairing adapter the camera network lives on a bridge (wired + WPS WiFi)
if [ "$AP_MODE" = "external" ] && [ -n "$PAIRING_WIFI_INTERFACE" ]; then
    DHCP_IF="br-arlo"
else
    DHCP_IF="$CAMERA_IF"
fi

MISSING=""
[ -z "$USERNAME" ] && MISSING="$MISSING USERNAME"
[ -z "$CAMERA_IF" ] && MISSING="$MISSING $( [ "$AP_MODE" = external ] && echo ARLO_INTERFACE || echo WIFI_INTERFACE )"
[ -z "$ETH_INTERFACE" ] && MISSING="$MISSING ETH_INTERFACE"
[ -z "$WIFI_SSID" ] && MISSING="$MISSING WIFI_SSID"
[ -z "$WIFI_PASSWORD" ] && MISSING="$MISSING WIFI_PASSWORD"
if [ -n "$MISSING" ]; then
    log_error "Missing required configuration:$MISSING"
    exit 1
fi
if [ "$AP_MODE" != "hostapd" ] && [ "$AP_MODE" != "external" ]; then
    log_error "AP_MODE must be 'hostapd' or 'external' (got '$AP_MODE')"
    exit 1
fi
if ! id "$USERNAME" >/dev/null 2>&1; then
    log_error "User $USERNAME does not exist"
    exit 1
fi
USER_HOME="$(getent passwd "$USERNAME" | cut -d: -f6)"
RECORDINGS_PATH="${RECORDINGS_PATH:-$USER_HOME/arlo-recordings}"

if [ -z "$API_TOKEN" ]; then
    if [ -f "$INSTALL_DIR/config.yaml" ] && grep -q '^ApiToken:' "$INSTALL_DIR/config.yaml"; then
        API_TOKEN="$(sed -n 's/^ApiToken: *"\(.*\)"/\1/p' "$INSTALL_DIR/config.yaml")"
    else
        API_TOKEN="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' )"
    fi
fi

log_info "Configuration loaded:"
log_info "  AP mode:          $AP_MODE"
log_info "  Camera interface: $CAMERA_IF (DHCP on $DHCP_IF, 172.14.0.1/24)"
[ -n "$PAIRING_WIFI_INTERFACE" ] && log_info "  Pairing WiFi:     $PAIRING_WIFI_INTERFACE"
log_info "  LAN interface:    $ETH_INTERFACE"
log_info "  SSID:             $WIFI_SSID"
log_info "  Install dir:      $INSTALL_DIR"
log_info "  Recordings:       $RECORDINGS_PATH"
log_info "  Live RTSP:        $LIVE_RTSP_ENABLED"

if [ "$ASSUME_YES" -ne 1 ]; then
    echo ""
    read -p "Continue with installation? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installation cancelled"
        exit 0
    fi
fi

# ===== Install System Packages =====
log_info "Installing required packages..."
PACKAGES="dnsmasq iptables netfilter-persistent iptables-persistent \
    python3-venv python3-dev build-essential ffmpeg nodejs npm vlc-bin vlc-plugin-base \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-rtsp python3-gi python3-gst-1.0 \
    curl ca-certificates iw psmisc"
if [ "$AP_MODE" = "hostapd" ] || [ -n "$PAIRING_WIFI_INTERFACE" ]; then
    PACKAGES="$PACKAGES hostapd"
fi
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y $PACKAGES
# python3-full only exists on newer Debian/Ubuntu; harmless if missing
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-full 2>/dev/null || true

# ===== Create Service User =====
log_info "Creating service user: $SERVICE_USER"
useradd "$SERVICE_USER" -m -r -s /usr/sbin/nologin 2>/dev/null || true
usermod -aG "$SERVICE_USER" "$USERNAME"

# ===== Install arlo-cam-api =====
log_info "Installing arlo-cam-api to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
# Never clobber live state
tar -C "$PROJECT_DIR/src/arlo-cam-api" --exclude=config.yaml --exclude=arlo.db --exclude=venv \
    --exclude=__pycache__ -cf - . | tar -C "$INSTALL_DIR" -xf -
chmod 755 "$INSTALL_DIR/helpers/live_publisher.py"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

log_info "Creating Python virtual environment..."
[ -x "$INSTALL_DIR/venv/bin/python3" ] || sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# ===== Generate config.yaml =====
CONFIG_TARGET="$INSTALL_DIR/config.yaml"
if [ -f "$CONFIG_TARGET" ]; then
    CONFIG_TARGET="$INSTALL_DIR/config.yaml.new"
    log_warn "Keeping existing config.yaml; new template written to $CONFIG_TARGET"
fi
log_info "Generating $CONFIG_TARGET..."
cat > "$CONFIG_TARGET" << EOF
WifiCountryCode: "$WIFI_COUNTRY"
MotionRecordingTimeout: $MOTION_TIMEOUT
AudioRecordingTimeout: 10
RecordOnMotionAlert: true
RecordOnAudioAlert: false
RecordingBasePath: "$RECORDINGS_PATH/"
MotionRecordingWebHookUrl: "$MOTION_WEBHOOK_URL"
AudioRecordingWebHookUrl: ""
UserRecordingWebHookUrl: ""
StatusUpdateWebHookUrl: ""
RegistrationWebHookUrl: ""
NotifyOnMotionAlert: true
NotifyOnAudioAlert: false
NotifyOnButtonPressAlert: true
PIRStartState: "armed"
PIRStartSensitivity: 80

# Address cameras use to reach this machine (snapshot uploads)
BaseStationIp: "172.14.0.1"

# Bearer token for REST API calls from other hosts (Home Assistant etc.)
ApiToken: "$API_TOKEN"

# Per-model tweaks, merged into the model's initial registerSet. Example:
# ModelOverrides:
#   VMC4041P:
#     register_set_values: {VideoTargetBitrate: 1500}
ModelOverrides: {}

# Ntfy Alert Configuration
NtfyEnabled: $NTFY_ENABLED
NtfyUrl: "$NTFY_URL"
NtfyTopic: "$NTFY_TOPIC"
NtfyPriority: "$NTFY_PRIORITY"
NtfyIncludeThumbnail: true
NtfyThumbnailBaseUrl: "$NTFY_THUMBNAIL_URL"
NtfyClickUrl: "$NTFY_CLICK_URL"

# Camera Aliases
CameraAliases:
EOF
ALIASES=0
for i in $(seq 1 20); do
    serial_var="CAMERA_SERIAL_$i"; name_var="CAMERA_NAME_$i"
    if [ -n "${!serial_var}" ]; then
        echo "  ${!serial_var}: \"${!name_var}\"" >> "$CONFIG_TARGET"
        ALIASES=$((ALIASES + 1))
    fi
done
[ "$ALIASES" -eq 0 ] && sed -i 's/^CameraAliases:$/CameraAliases: {}/' "$CONFIG_TARGET"

cat >> "$CONFIG_TARGET" << EOF

# Battery Warning Notifications
BatteryWarningEnabled: true
BatteryWarningLow: 25
BatteryWarningCritical: 10
EOF
chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_TARGET"
chmod 640 "$CONFIG_TARGET"

# ===== Recordings Directory (written by arlo, read/deleted by the viewer) =====
log_info "Creating recordings directory: $RECORDINGS_PATH"
mkdir -p "$RECORDINGS_PATH"
chown "$SERVICE_USER:$SERVICE_USER" "$RECORDINGS_PATH"
chmod 2775 "$RECORDINGS_PATH"
# The viewer user must be able to traverse the parent (e.g. /home/user is 0700 on Debian)
chmod o+x "$(dirname "$RECORDINGS_PATH")" 2>/dev/null || true

# ===== Camera network interface =====
if [ "$AP_MODE" = "external" ]; then
    log_info "Configuring camera network on $DHCP_IF (172.14.0.1/24)..."
    if [ "$DHCP_IF" = "br-arlo" ]; then
        cat > /etc/systemd/network/10-arlo-bridge.netdev << EOF
[NetDev]
Name=br-arlo
Kind=bridge
EOF
        cat > /etc/systemd/network/10-arlo-port.network << EOF
[Match]
Name=$ARLO_INTERFACE

[Network]
Bridge=br-arlo
EOF
        ARLO_NET_MATCH="br-arlo"
    else
        ARLO_NET_MATCH="$ARLO_INTERFACE"
    fi
    cat > /etc/systemd/network/10-arlo.network << EOF
[Match]
Name=$ARLO_NET_MATCH

[Network]
Address=172.14.0.1/24
ConfigureWithoutCarrier=yes
LinkLocalAddressing=no
IPv6AcceptRA=no
EOF
    # On cloud-init/netplan images (Proxmox) netplan also renders a unit for this NIC
    # (10-netplan-<if>.network). Ours sorts first ("10-arlo" < "10-netplan"), and
    # networkd uses the first matching file, so it wins without editing netplan
    # (which would also drop netplan's eth0/eth1 renaming).
    systemctl enable systemd-networkd >/dev/null 2>&1 || true
    networkctl reload 2>/dev/null || systemctl restart systemd-networkd
    networkctl reconfigure "$ARLO_INTERFACE" 2>/dev/null || true
fi

# ===== Configure dnsmasq =====
log_info "Configuring dnsmasq (DHCP for cameras on $DHCP_IF)..."
cat > /etc/dnsmasq.d/arlo.conf << EOF
# Arlo Open Base Station - DHCP/DNS for the camera network only
bind-dynamic
interface=$DHCP_IF
except-interface=lo
dhcp-range=172.14.0.100,172.14.0.199,255.255.255.0,infinite
dhcp-option=option:router,172.14.0.1
dhcp-option=option:dns-server,172.14.0.1
domain=arlo
address=/gateway.arlo/172.14.0.1
# Cameras have no business on the internet: answer nothing upstream
no-resolv
EOF
# Older installs wrote the whole /etc/dnsmasq.conf - move it out of the way once
if grep -q "Arlo Open Base Station" /etc/dnsmasq.conf 2>/dev/null; then
    mv /etc/dnsmasq.conf /etc/dnsmasq.conf.arlo-v1.bak
    touch /etc/dnsmasq.conf
fi
# Debian's systemd-resolved / dnsmasq resolvconf hook would hijack the host resolver
sed -i 's/^#\?IGNORE_RESOLVCONF=.*/IGNORE_RESOLVCONF=yes/' /etc/default/dnsmasq 2>/dev/null || true
grep -q '^DNSMASQ_EXCEPT=' /etc/default/dnsmasq 2>/dev/null || echo 'DNSMASQ_EXCEPT="lo"' >> /etc/default/dnsmasq
systemctl enable dnsmasq
systemctl restart dnsmasq || log_warn "dnsmasq failed to start (camera interface down?) - check after reboot"

# ===== Configure hostapd =====
write_hostapd_conf() {
    local iface="$1" bridge="$2"
    cat > /etc/hostapd/hostapd.conf << EOF
country_code=$WIFI_COUNTRY
interface=$iface
${bridge:+bridge=$bridge}
ctrl_interface=/var/run/hostapd
ctrl_interface_group=0
ssid=$WIFI_SSID
hw_mode=g
channel=11
macaddr_acl=0
auth_algs=1
wpa=2
wpa_passphrase=$WIFI_PASSWORD
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
ieee80211n=1
# WPS push-button: how Arlo cameras learn the SSID/PSK ("Sync" button)
eap_server=1
wps_state=2
ap_setup_locked=1
config_methods=push_button
device_name=Arlo Base Station
manufacturer=NETGEAR
EOF
    chmod 600 /etc/hostapd/hostapd.conf
}

if [ "$AP_MODE" = "hostapd" ]; then
    log_info "Configuring hostapd on $WIFI_INTERFACE..."
    write_hostapd_conf "$WIFI_INTERFACE" ""
    systemctl unmask hostapd
    systemctl enable hostapd
elif [ -n "$PAIRING_WIFI_INTERFACE" ]; then
    log_info "Configuring pairing-only hostapd on $PAIRING_WIFI_INTERFACE (bridged to br-arlo, disabled until scripts/arlo-pair.sh)..."
    write_hostapd_conf "$PAIRING_WIFI_INTERFACE" "br-arlo"
    systemctl unmask hostapd
    systemctl disable hostapd 2>/dev/null || true
    systemctl stop hostapd 2>/dev/null || true
fi
install -m 755 "$PROJECT_DIR/scripts/arlo-pair.sh" /usr/local/sbin/arlo-pair

# ===== IP forwarding: cameras stay local =====
rm -f /etc/sysctl.d/routed-ap.conf
echo "net.ipv4.ip_forward=0" > /etc/sysctl.d/90-arlo.conf
sysctl -q -p /etc/sysctl.d/90-arlo.conf || true

# ===== Configure Firewall =====
log_info "Configuring firewall rules..."
mkdir -p /etc/iptables
cat > /etc/iptables/rules.v4 << EOF
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A INPUT -p icmp -j ACCEPT
# Camera network: registration (4000), snapshot upload (5000), DHCP, DNS, RTP/RTCP
-A INPUT -i $DHCP_IF -j ACCEPT
# LAN: SSH, REST API (token protected), web viewer, live RTSP
-A INPUT -i $ETH_INTERFACE -p tcp -m multiport --dports 22,5000,3003,8554 -j ACCEPT
-A INPUT -i $ETH_INTERFACE -p udp -m multiport --dports 8000,8001 -j ACCEPT
-A INPUT -i $ETH_INTERFACE -p udp -m udp --dport 68 -j ACCEPT
COMMIT
EOF
# Don't lock ourselves out of a camera bridge's member ports either
if [ "$DHCP_IF" = "br-arlo" ]; then
    sed -i "s/^-A INPUT -i br-arlo -j ACCEPT$/-A INPUT -i br-arlo -j ACCEPT\n-A INPUT -i $ARLO_INTERFACE -j ACCEPT/" /etc/iptables/rules.v4
fi
cat > /etc/iptables/rules.v6 << EOF
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A INPUT -p ipv6-icmp -j ACCEPT
-A INPUT -i $ETH_INTERFACE -p tcp -m multiport --dports 22,5000,3003,8554 -j ACCEPT
-A INPUT -i $ETH_INTERFACE -p udp -m multiport --dports 8000,8001 -j ACCEPT
COMMIT
EOF
systemctl enable netfilter-persistent
netfilter-persistent reload || log_warn "firewall reload failed - check /etc/iptables/rules.v4"

# ===== Install arlo.service =====
log_info "Installing arlo.service..."
cat > /etc/systemd/system/arlo.service << EOF
[Unit]
Description=Arlo Control Service (base station emulator)
After=network-online.target dnsmasq.service
Wants=network-online.target

[Service]
WorkingDirectory=$INSTALL_DIR/
User=$SERVICE_USER
Type=simple
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/server.py
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
rm -f /lib/systemd/system/arlo.service

# ===== MediaMTX (on-demand live RTSP) =====
if [ "$LIVE_RTSP_ENABLED" = "true" ]; then
    log_info "Installing MediaMTX $MEDIAMTX_VERSION..."
    case "$(uname -m)" in
        x86_64) MTX_ARCH=amd64 ;;
        aarch64) MTX_ARCH=arm64v8 ;;
        armv7l) MTX_ARCH=armv7 ;;
        *) MTX_ARCH="" ;;
    esac
    if [ -z "$MTX_ARCH" ]; then
        log_warn "Unsupported architecture for MediaMTX - live RTSP skipped"
    else
        if ! /usr/local/bin/mediamtx --version 2>/dev/null | grep -q "${MEDIAMTX_VERSION}"; then
            TMP="$(mktemp -d)"
            curl -fsSL -o "$TMP/mtx.tgz" \
                "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/mediamtx_${MEDIAMTX_VERSION}_linux_${MTX_ARCH}.tar.gz"
            tar -C "$TMP" -xzf "$TMP/mtx.tgz" mediamtx
            install -m 755 "$TMP/mediamtx" /usr/local/bin/mediamtx
            rm -rf "$TMP"
        fi
        mkdir -p /etc/mediamtx
        sed "s#/opt/arlo-cam-api#$INSTALL_DIR#g" "$PROJECT_DIR/config/mediamtx.yml.example" > /etc/mediamtx/mediamtx.yml
        sed "s/^User=arlo$/User=$SERVICE_USER/" "$PROJECT_DIR/systemd/mediamtx.service" > /etc/systemd/system/mediamtx.service
        systemctl daemon-reload
        systemctl enable mediamtx.service
    fi
fi

# ===== Install arlo-viewer =====
log_info "Installing arlo-viewer..."
VIEWER_DIR="$USER_HOME/arlo-viewer"
mkdir -p "$VIEWER_DIR"
cp -r "$PROJECT_DIR/src/arlo-viewer/"* "$VIEWER_DIR/"
chown -R "$USERNAME:$USERNAME" "$VIEWER_DIR"
log_info "Installing Node.js dependencies..."
(cd "$VIEWER_DIR" && sudo -u "$USERNAME" npm install --omit=dev --no-audit --no-fund)

if [ ! -f /etc/arlo-viewer.env ]; then
    cat > /etc/arlo-viewer.env << EOF
RECORDINGS_DIR=$RECORDINGS_PATH
AUTH_PASSWORD=$VIEWER_PASSWORD
AUTH_SECRET=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')
EOF
    chmod 640 /etc/arlo-viewer.env
    chown root:"$USERNAME" /etc/arlo-viewer.env
fi

log_info "Installing arlo-viewer.service..."
cat > /etc/systemd/system/arlo-viewer.service << EOF
[Unit]
Description=Arlo Recording Viewer
After=network.target arlo.service

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$VIEWER_DIR
EnvironmentFile=/etc/arlo-viewer.env
ExecStartPre=/usr/bin/bash -c "/usr/bin/fuser -k 3003/tcp || true"
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable arlo.service arlo-viewer.service

# ===== Setup Bore Tunnels (Optional) =====
if [ -n "$BORE_REMOTE_SERVER" ]; then
    log_info "Setting up bore tunnel systemd services..."
    for unit in security-bore-tunnel ntfy-bore-tunnel; do
        sed -e "s/YOUR_USERNAME/$USERNAME/g" -e "s/YOUR_BORE_SERVER/$BORE_REMOTE_SERVER/g" \
            -e "s/YOUR_BORE_VIEWER_PORT/$BORE_VIEWER_PORT/g" -e "s/YOUR_BORE_NTFY_PORT/$BORE_NTFY_PORT/g" \
            "$PROJECT_DIR/systemd/$unit.service" > "/etc/systemd/system/$unit.service"
    done
    systemctl daemon-reload
    systemctl enable security-bore-tunnel.service ntfy-bore-tunnel.service
fi

# ===== (Re)start =====
systemctl restart arlo.service
sleep 2
systemctl restart arlo-viewer.service
[ "$LIVE_RTSP_ENABLED" = "true" ] && systemctl restart mediamtx.service 2>/dev/null || true

LAN_IP="$(ip -4 -o addr show "$ETH_INTERFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)"
echo ""
log_info "===== INSTALLATION COMPLETE ====="
if [ "$AP_MODE" = "hostapd" ]; then
    log_warn "Give $WIFI_INTERFACE the address 172.14.0.1/24 (see docs/INSTALLATION.md), then reboot."
fi
log_info "Viewer:     http://${LAN_IP:-<host>}:3003   (password in /etc/arlo-viewer.env)"
log_info "REST API:   http://${LAN_IP:-<host>}:5000   (header: Authorization: Bearer <ApiToken in $INSTALL_DIR/config.yaml>)"
[ "$LIVE_RTSP_ENABLED" = "true" ] && log_info "Live RTSP:  rtsp://${LAN_IP:-<host>}:8554/arlo_<CAMERA_SERIAL>"
if [ "$AP_MODE" = "external" ]; then
    log_info "Pair cameras: sudo arlo-pair   (needs PAIRING_WIFI_INTERFACE or another WPS AP)"
fi
log_info "Logs:       tail -f /tmp/arlo-service.log ; journalctl -u mediamtx -f"
