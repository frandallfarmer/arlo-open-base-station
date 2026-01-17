#!/bin/bash
# Arlo Open Base Station - Installation Script
# Reads config/install.conf and sets up the complete system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/config/install.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo $0"
    exit 1
fi

# Check for config file
if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Config file not found: $CONFIG_FILE"
    log_info "Copy config/install.conf.example to config/install.conf and fill in your values"
    exit 1
fi

# Source the config
log_info "Loading configuration from $CONFIG_FILE"
source "$CONFIG_FILE"

# Validate required fields
MISSING=""
[ -z "$USERNAME" ] && MISSING="$MISSING USERNAME"
[ -z "$WIFI_INTERFACE" ] && MISSING="$MISSING WIFI_INTERFACE"
[ -z "$WIFI_SSID" ] && MISSING="$MISSING WIFI_SSID"
[ -z "$WIFI_PASSWORD" ] && MISSING="$MISSING WIFI_PASSWORD"

if [ -n "$MISSING" ]; then
    log_error "Missing required configuration:$MISSING"
    exit 1
fi

log_info "Configuration loaded:"
log_info "  Username: $USERNAME"
log_info "  WiFi Interface: $WIFI_INTERFACE"
log_info "  SSID: $WIFI_SSID"
log_info "  Install Dir: $INSTALL_DIR"

echo ""
read -p "Continue with installation? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Installation cancelled"
    exit 0
fi

# ===== Install System Packages =====
log_info "Installing required packages..."
DEBIAN_FRONTEND=noninteractive apt install -y \
    hostapd dnsmasq netfilter-persistent iptables-persistent \
    python3-venv python3-full ffmpeg nodejs npm \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    python3-gst-1.0

# ===== Create Service User =====
log_info "Creating service user: $SERVICE_USER"
useradd $SERVICE_USER -m -r -s /usr/sbin/nologin 2>/dev/null || true

# ===== Install arlo-cam-api =====
log_info "Installing arlo-cam-api to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$PROJECT_DIR/src/arlo-cam-api/"* "$INSTALL_DIR/"
chown -R $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR"

log_info "Creating Python virtual environment..."
sudo -u $SERVICE_USER python3 -m venv "$INSTALL_DIR/venv"
sudo -u $SERVICE_USER "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# ===== Generate config.yaml =====
log_info "Generating config.yaml..."
cat > "$INSTALL_DIR/config.yaml" << EOF
WifiCountryCode: "$WIFI_COUNTRY"
MotionRecordingTimeout: $MOTION_TIMEOUT
AudioRecordingTimeout: 10
RecordOnMotionAlert: true
RecordOnAudioAlert: false
RecordingBasePath: "$RECORDINGS_PATH/"
MotionRecordingWebHookUrl: ""
AudioRecordingWebHookUrl: ""
UserRecordingWebHookUrl: ""
StatusUpdateWebHookUrl: ""
RegistrationWebHookUrl: ""
NotifyOnMotionAlert: true
NotifyOnAudioAlert: false
NotifyOnButtonPressAlert: true
PIRStartState: "armed"
PIRStartSensitivity: 80

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

# Add camera aliases if configured
if [ -n "$CAMERA_SERIAL_1" ]; then
    echo "  $CAMERA_SERIAL_1: \"$CAMERA_NAME_1\"" >> "$INSTALL_DIR/config.yaml"
fi
if [ -n "$CAMERA_SERIAL_2" ]; then
    echo "  $CAMERA_SERIAL_2: \"$CAMERA_NAME_2\"" >> "$INSTALL_DIR/config.yaml"
fi

cat >> "$INSTALL_DIR/config.yaml" << EOF

# Battery Warning Notifications
BatteryWarningEnabled: true
BatteryWarningLow: 25
BatteryWarningCritical: 10
EOF

chown $SERVICE_USER:$SERVICE_USER "$INSTALL_DIR/config.yaml"

# ===== Create Recordings Directory =====
log_info "Creating recordings directory: $RECORDINGS_PATH"
mkdir -p "$RECORDINGS_PATH"
chown $USERNAME:$USERNAME "$RECORDINGS_PATH"

# ===== Configure dnsmasq =====
log_info "Configuring dnsmasq..."
cat > /etc/dnsmasq.conf << EOF
# Arlo Open Base Station - DHCP/DNS Configuration
bind-interfaces
except-interface=lo
interface=$WIFI_INTERFACE
dhcp-range=172.14.0.100,172.14.0.199,255.255.255.0,infinite
domain=arlo
address=/gateway.arlo/172.14.0.1
EOF

# ===== Configure hostapd =====
log_info "Configuring hostapd..."
cat > /etc/hostapd/hostapd.conf << EOF
country_code=$WIFI_COUNTRY
interface=$WIFI_INTERFACE
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
wpa_pairwise=TKIP
rsn_pairwise=CCMP
ieee80211n=1
EOF

systemctl unmask hostapd
systemctl enable hostapd

# ===== Configure IP Forwarding =====
log_info "Enabling IP forwarding..."
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/routed-ap.conf

# ===== Configure Firewall =====
log_info "Configuring firewall rules..."
cat > /etc/iptables/rules.v4 << EOF
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -i lo -j ACCEPT
-A INPUT -p icmp -j ACCEPT
-A INPUT -i $ETH_INTERFACE -p tcp -m tcp --dport 22 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
-A INPUT -p tcp -m tcp --dport 5000 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
-A INPUT -i $WIFI_INTERFACE -p tcp -m tcp --dport 4000 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
-A INPUT -i $WIFI_INTERFACE -p tcp -m tcp --dport 554 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
-A INPUT -i $WIFI_INTERFACE -p udp -m udp --dport 67 -j ACCEPT
-A INPUT -i $WIFI_INTERFACE -p udp -m udp --dport 53 -j ACCEPT
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A FORWARD -p icmp -j ACCEPT
-A OUTPUT -o lo -j ACCEPT
-A OUTPUT -p icmp -j ACCEPT
-A OUTPUT -m conntrack --ctstate ESTABLISHED -j ACCEPT
COMMIT
EOF

# ===== Install arlo.service =====
log_info "Installing arlo.service..."
cat > /lib/systemd/system/arlo.service << EOF
[Unit]
Description=Arlo Control Service
After=multi-user.target
StartLimitIntervalSec=

[Service]
WorkingDirectory=$INSTALL_DIR/
User=$SERVICE_USER
Type=idle
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/server.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable arlo.service

# ===== Install arlo-viewer =====
log_info "Installing arlo-viewer..."
VIEWER_DIR="/home/$USERNAME/arlo-viewer"
mkdir -p "$VIEWER_DIR"
cp -r "$PROJECT_DIR/src/arlo-viewer/"* "$VIEWER_DIR/"
chown -R $USERNAME:$USERNAME "$VIEWER_DIR"

log_info "Installing Node.js dependencies..."
cd "$VIEWER_DIR"
sudo -u $USERNAME npm install

# ===== Install arlo-viewer.service =====
log_info "Installing arlo-viewer.service..."
cat > /etc/systemd/system/arlo-viewer.service << EOF
[Unit]
Description=Arlo Recording Viewer
After=network.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$VIEWER_DIR
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable arlo-viewer.service

# ===== Setup Bore Tunnels (Optional) =====
if [ -n "$BORE_REMOTE_SERVER" ]; then
    log_info "Setting up bore tunnel scripts..."

    cat > "/home/$USERNAME/start-security-bore-tunnel.sh" << EOF
#!/bin/bash
LOGFILE="/home/$USERNAME/bore-security-tunnel.log"
echo "\$(date): Starting bore tunnel" >> "\$LOGFILE"
if pgrep -f "bore local 3003.*$BORE_VIEWER_PORT" > /dev/null; then
    echo "\$(date): Already running" >> "\$LOGFILE"
    exit 0
fi
sleep 10
nohup bore local 3003 --to $BORE_REMOTE_SERVER --port $BORE_VIEWER_PORT >> "\$LOGFILE" 2>&1 &
EOF

    cat > "/home/$USERNAME/start-ntfy-bore-tunnel.sh" << EOF
#!/bin/bash
LOGFILE="/home/$USERNAME/bore-ntfy-tunnel.log"
echo "\$(date): Starting bore tunnel" >> "\$LOGFILE"
if pgrep -f "bore local 8085.*$BORE_NTFY_PORT" > /dev/null; then
    echo "\$(date): Already running" >> "\$LOGFILE"
    exit 0
fi
sleep 10
nohup bore local 8085 --to $BORE_REMOTE_SERVER --port $BORE_NTFY_PORT >> "\$LOGFILE" 2>&1 &
EOF

    chmod +x "/home/$USERNAME/start-security-bore-tunnel.sh"
    chmod +x "/home/$USERNAME/start-ntfy-bore-tunnel.sh"
    chown $USERNAME:$USERNAME "/home/$USERNAME/start-"*"-bore-tunnel.sh"

    log_info "Bore tunnel scripts created. Add to crontab with:"
    log_info "  @reboot /home/$USERNAME/start-security-bore-tunnel.sh"
    log_info "  @reboot /home/$USERNAME/start-ntfy-bore-tunnel.sh"
fi

# ===== Final Instructions =====
echo ""
log_info "===== INSTALLATION COMPLETE ====="
echo ""
log_warn "Before rebooting, configure your WiFi interface IP address."
log_info "For netplan (Ubuntu 18.04+), create /etc/netplan/03-arlo-ap.yaml:"
echo ""
echo "network:"
echo "  version: 2"
echo "  wifis:"
echo "    $WIFI_INTERFACE:"
echo "      dhcp4: false"
echo "      addresses:"
echo "        - 172.14.0.1/24"
echo ""
log_info "Then run: sudo netplan apply"
echo ""
log_info "After reboot, check services with:"
log_info "  systemctl status arlo arlo-viewer"
echo ""
log_info "View recordings at: http://localhost:3003"
echo ""
log_warn "Now reboot to complete setup: sudo reboot"
