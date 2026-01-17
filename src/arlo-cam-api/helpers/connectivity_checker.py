import subprocess
import sqlite3
import threading
import time
import logging

def check_arp(mac_address):
    """Check if MAC address is in ARP table"""
    try:
        result = subprocess.run(
            ['arp', '-n'],
            capture_output=True,
            text=True,
            timeout=1
        )
        return mac_address.lower() in result.stdout.lower()
    except Exception as e:
        logging.error(f"[CONNECTIVITY] Error checking ARP: {e}")
        return False

def update_camera_connectivity():
    """Update connectivity status for all cameras in database"""
    try:
        with sqlite3.connect('/opt/arlo-cam-api/arlo.db') as conn:
            c = conn.cursor()
            
            # Get all cameras with MAC addresses
            c.execute("SELECT serialnumber, mac_address, friendlyname FROM camera WHERE mac_address IS NOT NULL")
            cameras = c.fetchall()
            
            for serial, mac, friendly_name in cameras:
                if mac:
                    connected = 1 if check_arp(mac) else 0
                    c.execute("UPDATE camera SET connected = ? WHERE serialnumber = ?", (connected, serial))
                    status_str = "Connected" if connected else "Offline"
                    logging.info(f"[CONNECTIVITY] {friendly_name} ({serial}): {status_str}")
            
            conn.commit()
            
    except Exception as e:
        logging.error(f"[CONNECTIVITY] Error updating connectivity: {e}")

class ConnectivityChecker(threading.Thread):
    """Background thread that checks camera connectivity every 5 minutes"""
    
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.interval = 300  # 5 minutes in seconds
        
    def run(self):
        logging.info("[CONNECTIVITY] Connectivity checker started (5 minute interval)")
        
        # Do initial check immediately
        update_camera_connectivity()
        
        # Then check every 5 minutes
        while True:
            time.sleep(self.interval)
            update_camera_connectivity()
