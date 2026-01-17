# Bore Tunnel Systemd Services Installation

This guide installs systemd services for all bore tunnels, replacing the old crontab-based approach.

## Services Overview

| Service | Machine | Port | Description |
|---------|---------|------|-------------|
| bird-webserver.service | Ryugi | 8081 | ✅ Already installed |
| ssh-bore-tunnel.service | Ryugi | 8083 | SSH access tunnel |
| security-bore-tunnel.service | arlo-base | 8084 | security.thefarmers.org |
| ntfy-bore-tunnel.service | arlo-base | 8085 | ntfy.thefarmers.org |

---

## Installation on Ryugi

### 1. Install SSH Bore Tunnel Service

```bash
# Copy service file
sudo cp /tmp/ssh-bore-tunnel.service /etc/systemd/system/

# Create log file
sudo touch /var/log/ssh-bore-tunnel.log
sudo chown randy:randy /var/log/ssh-bore-tunnel.log

# Stop old tunnel and crontab monitors
pkill -f "bore local 22.*8083"

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable ssh-bore-tunnel.service
sudo systemctl start ssh-bore-tunnel.service

# Verify
sudo systemctl status ssh-bore-tunnel.service
tail -f /var/log/ssh-bore-tunnel.log
```

### 2. Remove Old Crontab Entries (Ryugi)

```bash
# Edit crontab
crontab -e

# Remove these lines:
# @reboot /home/randy/hosting/start-ssh-bore-tunnel.sh
# */5 * * * * /home/randy/hosting/monitor-ssh-bore-tunnel.sh
```

---

## Installation on arlo-base

### 1. Install Security Bore Tunnel Service

```bash
# Copy service file
sudo cp /tmp/security-bore-tunnel.service /etc/systemd/system/

# Create log file
sudo touch /var/log/security-bore-tunnel.log
sudo chown randy:randy /var/log/security-bore-tunnel.log

# Stop old tunnel and crontab monitors
pkill -f "bore local 3003.*8084"

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable security-bore-tunnel.service
sudo systemctl start security-bore-tunnel.service

# Verify
sudo systemctl status security-bore-tunnel.service
tail -f /var/log/security-bore-tunnel.log
```

### 2. Install Ntfy Bore Tunnel Service

```bash
# Copy service file
sudo cp /tmp/ntfy-bore-tunnel.service /etc/systemd/system/

# Create log file
sudo touch /var/log/ntfy-bore-tunnel.log
sudo chown randy:randy /var/log/ntfy-bore-tunnel.log

# Stop old tunnel and crontab monitors
pkill -f "bore local 8085.*8085"

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable ntfy-bore-tunnel.service
sudo systemctl start ntfy-bore-tunnel.service

# Verify
sudo systemctl status ntfy-bore-tunnel.service
tail -f /var/log/ntfy-bore-tunnel.log
```

### 3. Remove Old Crontab Entries (arlo-base)

```bash
# Edit crontab
crontab -e

# Remove these lines:
# @reboot /home/randy/hosting/start-security-bore-tunnel.sh
# @reboot /home/randy/hosting/start-ntfy-bore-tunnel.sh
# */5 * * * * /home/randy/hosting/monitor-security-bore-tunnel.sh
# */5 * * * * /home/randy/hosting/monitor-ntfy-bore-tunnel.sh
```

---

## Service Management

### Check all bore tunnels:

**On Ryugi:**
```bash
sudo systemctl status bird-webserver.service ssh-bore-tunnel.service
```

**On arlo-base:**
```bash
sudo systemctl status security-bore-tunnel.service ntfy-bore-tunnel.service
```

**On droplet (verify connections):**
```bash
ssh droplet "ss -tlnp | grep bore"
```

### View logs:

```bash
# Ryugi
tail -f /var/log/bird-webserver.log
tail -f /var/log/ssh-bore-tunnel.log

# arlo-base
tail -f /var/log/security-bore-tunnel.log
tail -f /var/log/ntfy-bore-tunnel.log
```

### Restart services:

```bash
# Ryugi
sudo systemctl restart ssh-bore-tunnel.service

# arlo-base
sudo systemctl restart security-bore-tunnel.service
sudo systemctl restart ntfy-bore-tunnel.service
```

---

## Testing Reboot Scenarios

### Test Ryugi reboot:
```bash
sudo reboot
# After reboot, verify:
sudo systemctl status bird-webserver.service ssh-bore-tunnel.service
ssh droplet "ss -tlnp | grep -E '8081|8083'"
```

### Test arlo-base reboot:
```bash
ssh arlo-base "sudo reboot"
# After reboot, verify:
ssh arlo-base "sudo systemctl status security-bore-tunnel.service ntfy-bore-tunnel.service"
ssh droplet "ss -tlnp | grep -E '8084|8085'"
```

### Test droplet bore-server restart:
```bash
ssh droplet "sudo systemctl restart bore-server.service"
# All tunnels should auto-reconnect within 10-20 seconds
sleep 20
ssh droplet "ss -tlnp | grep bore"
```

---

## Benefits Over Crontab Approach

✅ **Auto-restart on failure** - systemd restarts immediately (10 sec) vs cron (5 min)  
✅ **Better logging** - journalctl + dedicated log files  
✅ **Cleaner process management** - No duplicate tunnels, proper cleanup  
✅ **Status visibility** - `systemctl status` shows health  
✅ **Dependency management** - Waits for network before starting  
✅ **No crontab clutter** - All services in one place  

---

## Troubleshooting

### Tunnel not connecting:
```bash
# Check if bore binary exists
which bore

# Check if remote port is available on droplet
ssh droplet "ss -tlnp | grep 8084"

# Restart bore server on droplet
ssh droplet "sudo systemctl restart bore-server.service"
```

### Port already in use:
```bash
# Find what's using the port
lsof -i :8084

# Kill old tunnel
pkill -f "bore local 8084"

# Restart service
sudo systemctl restart security-bore-tunnel.service
```

### Service won't start:
```bash
# Check logs
journalctl -u security-bore-tunnel.service -n 50

# Verify bore binary path
which bore  # Should be /usr/local/bin/bore

# Test bore command manually
bore local 3003 --to 64.227.96.215 --port 8084
```

---

**Created:** January 7, 2026  
**Purpose:** Migrate bore tunnels from crontab to systemd management
