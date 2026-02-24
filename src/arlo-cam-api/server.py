import socket
import sys
import json
import threading
import sqlite3
import time
import yaml
import logging

from arlo.messages import Message
from arlo.socket import ArloSocket
import arlo.messages
from arlo.camera import Camera
from helpers.safe_print import s_print
from helpers.recorder import Recorder
from helpers.webhook_manager import WebHookManager
import api.api
from helpers.connectivity_checker import ConnectivityChecker

# Configure logging to file for easy access
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('/tmp/arlo-service.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, 'arlo.db')

with open(r'config.yaml') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)

# Load camera aliases from config and set in camera module
import arlo.camera
arlo.camera.CAMERA_ALIASES = config.get('CameraAliases', {})

webhook_manager = WebHookManager(config)

with sqlite3.connect(DB_PATH) as conn:
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS camera (ip text, serialnumber text, hostname text, status text, register_set text, friendlyname text)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_camera_serialnumber ON camera (serialnumber)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_camera_ip ON camera (ip)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_camera_friendlyname ON camera (friendlyname)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_camera_hostname ON camera (hostname)")
    conn.commit()

recorder_lock = threading.Lock()
recorders = {}

# Battery warning tracking
# Stores last warned level for each camera: {serial_number: last_warned_level}
# Levels: None (not warned), 'low' (warned at 25%), 'critical' (warned at 10%)
battery_warning_state = {}
battery_warning_lock = threading.Lock()

WIFI_COUNTRY_CODE=config['WifiCountryCode']
MOTION_RECORDING_TIMEOUT=config['MotionRecordingTimeout']
AUDIO_RECORDING_TIMEOUT=config['AudioRecordingTimeout']
RECORDING_BASE_PATH=config['RecordingBasePath']
RECORD_ON_MOTION_ALERT=config['RecordOnMotionAlert']
RECORD_ON_AUDIO_ALERT=config['RecordOnAudioAlert']

def generate_thumbnail(video_filename):
    """Generate thumbnail from video file using ffmpeg"""
    import subprocess
    import os

    # Create thumbnail filename by replacing .mkv with .jpg
    thumbnail_filename = video_filename.replace('.mkv', '.jpg')

    # Use ffmpeg to extract frame at 1 second
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', video_filename,
        '-ss', '00:00:01',  # Extract frame at 1 second
        '-vframes', '1',     # Extract only 1 frame
        '-q:v', '2',         # High quality (2-5 is good, 2 is highest)
        thumbnail_filename
    ]

    try:
        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=10)
        if result.returncode == 0 and os.path.exists(thumbnail_filename):
            s_print(f"[THUMBNAIL] Generated: {thumbnail_filename}")
            return True
        else:
            s_print(f"[THUMBNAIL] Failed to generate thumbnail: {result.stderr.decode()}")
            return False
    except subprocess.TimeoutExpired:
        s_print(f"[THUMBNAIL] Timeout generating thumbnail for {video_filename}")
        return False
    except Exception as e:
        s_print(f"[THUMBNAIL] Error generating thumbnail: {e}")
        return False

def monitor_and_record(ip, rtsp_url, filename, serial_number, zones, webhook_manager, friendly_name, hostname):
    """Background thread: monitor port 554, then record immediately when port opens"""
    import subprocess
    import socket as sock_module

    recording_duration = 10  # seconds - matches battery camera stream duration
    max_wait = 3.0  # seconds - maximum time to wait for port to open
    check_interval = 0.1  # seconds - how often to check port
    max_attempts = int(max_wait / check_interval)

    s_print(f"[{ip}] Monitoring for RTSP stream (port 554) - max wait {max_wait}s")

    # Monitor port 554 until it opens or timeout
    port_opened = False
    for attempt in range(max_attempts):
        sock = sock_module.socket(sock_module.AF_INET, sock_module.SOCK_STREAM)
        sock.settimeout(check_interval)
        result = sock.connect_ex((ip, 554))
        sock.close()

        if result == 0:
            port_opened = True
            elapsed = attempt * check_interval
            s_print(f"[{ip}] Port 554 opened after {elapsed:.1f}s - starting recording immediately")
            break

        time.sleep(check_interval)

    if not port_opened:
        s_print(f"[{ip}] Port 554 never opened - recording failed")
        return

    # Port is open - start recording immediately (no validation to avoid consuming stream)
    s_print(f"[{ip}] Starting ffmpeg recording for {recording_duration}s")

    # Generate thumbnail filename
    thumbnail_filename = filename.replace('.mkv', '.jpg')

    # Stream is ready - start recording with dual output (video + thumbnail)
    ffmpeg_cmd = [
        'ffmpeg',
        '-use_wallclock_as_timestamps', '1',
        '-fflags', '+genpts+igndts',
        '-analyzeduration', '10000000',
        '-probesize', '10000000',
        '-rtsp_transport', 'udp',
        '-i', rtsp_url,
        # First output: full video (10 seconds)
        '-t', str(recording_duration),
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-avoid_negative_ts', 'make_zero',
        '-f', 'matroska',
        filename,
        # Second output: thumbnail (first frame only)
        '-frames:v', '1',
        '-q:v', '2',
        thumbnail_filename
    ]

    # Run ffmpeg and wait for completion
    logfile = f"{RECORDING_BASE_PATH}ffmpeg-{serial_number}-{time.strftime('%Y%m%d-%H%M%S')}.log"
    log = open(logfile, 'w')
    proc = subprocess.Popen(ffmpeg_cmd, stdout=log, stderr=log)
    s_print(f"[{ip}] Recording started: {filename} (log: {logfile})")

    # Wait briefly for thumbnail to be generated (first frame capture)
    import os
    max_wait = 2.0  # seconds
    wait_interval = 0.1
    for _ in range(int(max_wait / wait_interval)):
        if os.path.exists(thumbnail_filename):
            s_print(f"[{ip}] Thumbnail ready: {thumbnail_filename}")
            break
        time.sleep(wait_interval)
    else:
        s_print(f"[{ip}] Warning: Thumbnail not ready after {max_wait}s")

    # Trigger webhook notification (thumbnail should now exist)
    webhook_manager.motion_detected(ip, friendly_name, hostname, serial_number, zones, filename)

    # Wait for ffmpeg to complete with timeout
    timeout = recording_duration + 5  # recording duration + 5 second buffer
    recording_success = False
    try:
        returncode = proc.wait(timeout=timeout)
        if returncode == 0:
            s_print(f"[{ip}] Recording completed successfully")
            recording_success = True
        else:
            s_print(f"[{ip}] Recording failed with exit code {returncode} - check {logfile}")
    except subprocess.TimeoutExpired:
        s_print(f"[{ip}] Recording timeout - killing ffmpeg process")
        proc.kill()
        proc.wait()
        # Even though ffmpeg timed out, if video file exists with content, consider it successful
        import os
        if os.path.exists(filename) and os.path.getsize(filename) > 100000:  # > 100KB
            s_print(f"[{ip}] Video file created despite timeout - treating as successful")
            recording_success = True
    finally:
        log.close()
        # Thumbnail already generated during recording (dual output)

class ConnectionThread(threading.Thread):
    def __init__(self,connection,ip,port):
        threading.Thread.__init__(self)
        self.connection = ArloSocket(connection)
        self.ip = ip
        self.port = port

    def run(self):
        while True:
            timestr = time.strftime("%Y%m%d-%H%M%S")
            msg = self.connection.receive()
            if msg != None:
                # RAW MESSAGE LOGGING - see everything camera sends (disabled - too verbose)
                # logging.info(f"RAW MESSAGE from {self.ip}: {json.dumps(msg.dictionary, indent=2)}")

                if (msg['Type'] == "registration"):
                    camera = Camera.from_db_serial(msg['SystemSerialNumber'])
                    is_new_camera = camera is None
                    if is_new_camera:
                        camera = Camera(self.ip, msg)
                        # New camera defaults to armed state
                        camera.armed = 1
                    else:
                        camera.registration = msg
                        # Preserve existing armed state for known cameras
                    camera.persist()
                    s_print(f"<[{self.ip}][{msg['ID']}] Registration from {msg['SystemSerialNumber']} - {camera.hostname}")
                    if msg['SystemModelNumber'] ==  'VMC5040':
                        registerSet = Message(arlo.messages.REGISTER_SET_INITIAL_ULTRA)
                    else:
                        registerSet = Message(arlo.messages.REGISTER_SET_INITIAL)
                    registerSet['WifiCountryCode'] = WIFI_COUNTRY_CODE

                    # Apply current armed state to registration message
                    if camera.armed == 0:
                        # User wants camera disarmed - override REGISTER_SET_INITIAL defaults
                        registerSet['PIRTargetState'] = 0
                        registerSet['VideoMotionEstimationEnable'] = 0
                        registerSet['AudioTargetState'] = 0
                    # else: keep REGISTER_SET_INITIAL defaults (Armed, VME enabled, Audio disarmed)

                    camera.send_message(registerSet)
                elif (msg['Type'] == "status"):
                    s_print(f"<[{self.ip}][{msg['ID']}] Status from {msg['SystemSerialNumber']}")
                    camera = Camera.from_db_serial(msg['SystemSerialNumber'])
                    camera.ip = self.ip
                    camera.status = msg
                    camera.persist()

                    # Check battery level and send warnings if enabled
                    if config.get('BatteryWarningEnabled', False):
                        battery_percent = msg.dictionary.get('BatPercent')
                        if battery_percent is not None:
                            serial = camera.serial_number
                            warning_low = config.get('BatteryWarningLow', 25)
                            warning_critical = config.get('BatteryWarningCritical', 10)

                            with battery_warning_lock:
                                last_warned = battery_warning_state.get(serial)

                                # Check critical threshold (10%)
                                if battery_percent <= warning_critical and last_warned != 'critical':
                                    webhook_manager.send_battery_warning(
                                        camera.friendly_name, camera.hostname, serial,
                                        battery_percent, is_critical=True
                                    )
                                    battery_warning_state[serial] = 'critical'

                                # Check low threshold (25%) - only if not already critical
                                elif battery_percent <= warning_low and last_warned is None:
                                    webhook_manager.send_battery_warning(
                                        camera.friendly_name, camera.hostname, serial,
                                        battery_percent, is_critical=False
                                    )
                                    battery_warning_state[serial] = 'low'

                                # Reset warning state if battery recovers above low threshold
                                elif battery_percent > warning_low and last_warned is not None:
                                    s_print(f"[BATTERY] {camera.friendly_name} recovered to {battery_percent}% - resetting warnings")
                                    battery_warning_state[serial] = None
                elif (msg['Type'] == "alert"):
                    camera = Camera.from_db_ip(self.ip)
                    alert_type = msg['AlertType']
                    s_print(f"<[{self.ip}][{msg['ID']}] {msg['AlertType']}")

                    # For pirMotionAlert: ACK immediately, then monitor port and record
                    if alert_type == "pirMotionAlert" and RECORD_ON_MOTION_ALERT:
                       s_print(f"[{self.ip}] Motion detected - ACK first, then monitor for stream")

                       # Send ACK immediately
                       ack = Message(arlo.messages.RESPONSE)
                       ack['ID'] = msg['ID']
                       s_print(f">[{self.ip}][{msg['ID']}] Ack (immediate)")
                       self.connection.send(ack)

                       # Spawn background thread to monitor port and record
                       filename = f"{RECORDING_BASE_PATH}arlo-{camera.serial_number}-{timestr}.mkv"
                       rtsp_url = f"rtsp://{self.ip}/live"
                       zones = msg['PIRMotion'].get('zones', '')

                       monitor_thread = threading.Thread(
                           target=monitor_and_record,
                           args=(self.ip, rtsp_url, filename, camera.serial_number, zones, webhook_manager, camera.friendly_name, camera.hostname),
                           daemon=True
                       )
                       monitor_thread.start()
                       s_print(f"[{self.ip}] Monitoring thread started for recording")

                       # Close connection and exit - monitoring thread handles recording
                       self.connection.close()
                       break
                    elif alert_type == "audioAlert" and RECORD_ON_AUDIO_ALERT:
                       recorder = Recorder(self.ip, f"{RECORDING_BASE_PATH}{camera.serial_number}_{timestr}_audio.mpg", AUDIO_RECORDING_TIMEOUT)
                       with recorder_lock:
                           if self.ip in recorders:
                               recorders[self.ip].stop()
                           recorders[self.ip] = recorder
                       recorder.run()
                    elif alert_type == "motionTimeoutAlert":
                       with recorder_lock:
                           if self.ip in recorders and recorders[self.ip] is not None:
                               recorders[self.ip].stop()
                               del recorders[self.ip]
                else:
                    s_print(f"<[{self.ip}][{msg['ID']}] Unknown message")
                    s_print(msg)

                ack = Message(arlo.messages.RESPONSE)
                ack['ID'] = msg['ID']
                s_print(f">[{self.ip}][{msg['ID']}] Ack")
                self.connection.send(ack)
                self.connection.close()
                break

class ServerThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        threads = []
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_address = ('', 4000)
            sock.bind(server_address)

            sock.listen(12)
            while True:
                try:
                    (connection, (ip, port)) = sock.accept()
                    new_thread = ConnectionThread(connection,ip,port)
                    threads.append(new_thread)
                    new_thread.start()
                except KeyboardInterrupt as ki:
                    break
                except Exception as e:
                    print(e)

        for t in threads:
            t.join()


server_thread = ServerThread()
connectivity_thread = ConnectivityChecker()
connectivity_thread.start()
server_thread.start()
flask_thread = api.api.get_thread()
server_thread.join()
flask_thread.join()
