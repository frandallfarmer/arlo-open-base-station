#!/bin/bash
# Create dated snapshot of Arlo camera system

BACKUP_DIR="/home/randy/backups/arlo-cam-api"
DATE=$(date +%Y%m%d-%H%M%S)
SNAPSHOT_DIR="$BACKUP_DIR/$DATE"

echo "Creating snapshot: $SNAPSHOT_DIR"

# Create backup directory
mkdir -p "$SNAPSHOT_DIR"

# Copy main code files
sudo cp -r /opt/arlo-cam-api/arlo "$SNAPSHOT_DIR/"
sudo cp -r /opt/arlo-cam-api/api "$SNAPSHOT_DIR/"
sudo cp /opt/arlo-cam-api/server.py "$SNAPSHOT_DIR/"
sudo cp /opt/arlo-cam-api/config.yaml "$SNAPSHOT_DIR/"

# Copy viewer files
cp -r ~/arlo-viewer/public "$SNAPSHOT_DIR/viewer-public"
cp ~/arlo-viewer/server.js "$SNAPSHOT_DIR/viewer-server.js"

# Copy database (just schema, not recordings metadata)
sudo sqlite3 /opt/arlo-cam-api/arlo.db ".schema" > "$SNAPSHOT_DIR/database-schema.sql"

# Fix permissions
sudo chown -R randy:randy "$SNAPSHOT_DIR"

# Create a manifest
cat > "$SNAPSHOT_DIR/MANIFEST.txt" << MANIFEST
Arlo Camera System Snapshot
Created: $(date)
Location: $SNAPSHOT_DIR

Contents:
- arlo/          Camera control code
- api/           Flask REST API
- server.py      Main server
- config.yaml    Configuration
- viewer-public/ Status dashboard HTML
- viewer-server.js Video viewer server
- database-schema.sql Database structure

To restore:
  sudo cp -r arlo api server.py config.yaml /opt/arlo-cam-api/
  cp -r viewer-public/* ~/arlo-viewer/public/
  cp viewer-server.js ~/arlo-viewer/server.js
  sudo systemctl restart arlo
MANIFEST

echo "✓ Snapshot created: $SNAPSHOT_DIR"
echo ""
echo "Recent snapshots:"
ls -lt "$BACKUP_DIR" | head -6
