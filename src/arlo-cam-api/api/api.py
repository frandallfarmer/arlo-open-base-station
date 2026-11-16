import flask
import threading
import sqlite3
import json
import functools
import os
import time
import shutil
from arlo.camera import Camera
from arlo.messages import Message
from flask import g
from helpers.stream_manager import StreamManager
from helpers import events
import arlo.models
import arlo.messages
import glob
import socket

app = flask.Flask(__name__)
app.config["DEBUG"] = False
app.use_reloader=False

# Global dict to track active streams
active_streams = {}

# Set by server.py before the Flask thread starts
CONFIG = {}

# Live (MediaMTX on-demand) sessions: serial -> number of active publishers
live_sessions = {}
live_lock = threading.Lock()


@app.before_request
def check_api_token():
    """Optional bearer-token auth (config.yaml: ApiToken).

    Localhost (the viewer, the live publisher) and the camera snapshot upload
    endpoint are exempt so existing components keep working unchanged.
    """
    token = CONFIG.get('ApiToken')
    if not token:
        return None
    if flask.request.remote_addr in ('127.0.0.1', '::1'):
        return None
    if flask.request.path.startswith('/snapshot/'):
        return None
    if flask.request.headers.get('Authorization') == f"Bearer {token}":
        return None
    # Read-only GETs may pass ?token= instead, for clients that cannot set a
    # header (e.g. Home Assistant's Generic Camera still-image URL).
    if flask.request.method == 'GET' and flask.request.args.get('token') == token:
        return None
    flask.abort(401)
    return None


def camera_profile(camera):
    model = None
    if camera is not None and camera.registration is not None:
        model = camera.registration.dictionary.get('SystemModelNumber')
    return arlo.models.get_profile(model, CONFIG.get('ModelOverrides') or {})

# Cleanup leftover stream files on startup
if os.path.exists('/tmp/arlo-stream'):
    shutil.rmtree('/tmp/arlo-stream', ignore_errors=True)

def validate_camera_request(body_required=True):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            g.camera = Camera.from_db_serial(kwargs['serial'])
            if g.camera is None:
                flask.abort(404)

            if body_required:
                g.args = flask.request.get_json()
                if g.args is None:
                    flask.abort(400)

            return f(*args,**kwargs)
        return wrapper
    return decorator

@app.route('/', methods=['GET'])
def home():
    return "PING"

@app.route('/camera', methods=['GET'])
def list():
    with sqlite3.connect('arlo.db') as conn:
        c = conn.cursor()
        c.execute("SELECT ip, serialnumber, hostname, friendlyname FROM camera")
        rows = c.fetchall()
        cameras = []
        if rows is not None:
            for row in rows:
                (ip,serial_number,hostname,friendly_name) = row
                cameras.append({"ip":ip,"hostname":hostname,"serial_number":serial_number,"friendly_name":friendly_name})

        return flask.jsonify(cameras)

@app.route('/cameras/status', methods=['GET'])
def cameras_status():
    """Get comprehensive status for all cameras"""
    import time
    with sqlite3.connect('arlo.db') as conn:
        c = conn.cursor()
        c.execute("SELECT ip, serialnumber, hostname, status, register_set, friendlyname, last_seen, mac_address, connected, armed FROM camera")
        rows = c.fetchall()
        cameras_status = []


        if rows is not None:
            for row in rows:
                (ip, serial_number, hostname, status_json, registration_json, friendly_name, last_seen_db, mac_address, connected, armed) = row

                # Use connectivity checker result
                online = bool(connected) if connected is not None else False
                # Parse status for battery and other info
                battery_percent = None
                signal_strength = None
                charging_state = None
                charger_tech = None
                battery_voltage = None
                temperature = None
                model_number = None
                firmware = None

                if registration_json:
                    try:
                        reg = Message.from_json(registration_json)
                        model_number = reg.dictionary.get('SystemModelNumber')
                        firmware = reg.dictionary.get('SystemFirmwareVersion')
                    except Exception:
                        pass

                if status_json:
                    try:
                        status_data = Message.from_json(status_json)
                        battery_percent = status_data.dictionary.get('BatPercent')
                        signal_strength = status_data.dictionary.get('SignalStrengthIndicator')
                        charging_state = status_data.dictionary.get('ChargingState')
                        charger_tech = status_data.dictionary.get('ChargerTech')
                        battery_voltage = status_data.dictionary.get('Bat1Volt')
                        temperature = status_data.dictionary.get('Temperature')
                        firmware = status_data.dictionary.get('SystemFirmwareVersion') or firmware
                    except:
                        pass

                # Convert last_seen from Julian day to ISO timestamp for readability
                last_seen_iso = None
                if last_seen_db is not None:
                    # Calculate seconds since epoch from Julian day
                    # Julian day 0 = noon on January 1, 4713 BC
                    # Unix epoch (1970-01-01 00:00:00) = Julian day 2440587.5
                    import datetime
                    epoch_julian = 2440587.5
                    seconds_since_epoch = (last_seen_db - epoch_julian) * 86400
                    last_seen_iso = datetime.datetime.utcfromtimestamp(seconds_since_epoch).isoformat() + 'Z'

                camera_info = {
                    "serial_number": serial_number,
                    "friendly_name": friendly_name or hostname or serial_number,
                    "hostname": hostname,
                    "ip": ip if online else None,
                    "mac_address": mac_address,
                    "online": online,
                    "armed": bool(armed) if armed is not None else True,
                    "battery_percent": battery_percent,
                    "signal_strength": signal_strength,
                    "charging_state": charging_state,
                    "charger_tech": charger_tech,
                    "battery_voltage": battery_voltage,
                    "temperature": temperature,
                    "model_number": model_number,
                    "model_name": arlo.models.get_profile(model_number)['name'],
                    "firmware": firmware,
                    "live_active": live_sessions.get(serial_number, 0) > 0,
                    "last_seen": last_seen_iso
                }

                cameras_status.append(camera_info)

        return flask.jsonify(cameras_status)

@app.route('/camera/<serial>', methods=['GET'])
@validate_camera_request(body_required=False)
def status(serial):
    if g.camera.status is None:
        return flask.jsonify({})
    else:
        return flask.jsonify(g.camera.status.dictionary)

@app.route('/camera/<serial>/registration', methods=['GET'])
@validate_camera_request(body_required=False)
def registration(serial):
    if g.camera.registration is None:
        return flask.jsonify({})
    else:
        return flask.jsonify(g.camera.registration.dictionary)

@app.route('/camera/<serial>/statusrequest', methods=['POST'])
@validate_camera_request(body_required=False)
def status_request(serial):
    result = g.camera.status_request()
    return flask.jsonify({"result":result})

@app.route('/camera/<serial>/userstreamactive', methods=['POST'])
@validate_camera_request()
def user_stream_active(serial):
    active = g.args["active"]
    if active is None:
        flask.abort(400)

    # Trigger recording when motion detected (active=1)
    if int(active) == 1:
        import subprocess
        subprocess.Popen([os.path.expanduser('~/arlo-record-oneshot.sh')],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)

    result = g.camera.set_user_stream_active(int(active))
    return flask.jsonify({"result":result})

@app.route('/camera/<serial>/arm', methods=['POST'])
@validate_camera_request(body_required=False)
def arm(serial):
    # Use provided args or defaults for arming
    args = flask.request.get_json() if flask.request.is_json else {}
    arm_config = {
        'PIRTargetState': args.get('PIRTargetState', 1),
        'VideoMotionEstimationEnable': args.get('VideoMotionEstimationEnable', 1),
        'AudioTargetState': args.get('AudioTargetState', 1)
    }
    result = g.camera.arm(arm_config)
    if result:
        g.camera.armed = 1
        g.camera.persist()
    return flask.jsonify({"result":result})

@app.route('/camera/<serial>/disarm', methods=['POST'])
@validate_camera_request(body_required=False)
def disarm(serial):
    # Disarm by setting all detection to off
    disarm_config = {
        'PIRTargetState': 0,
        'VideoMotionEstimationEnable': 0,
        'AudioTargetState': 0
    }
    result = g.camera.arm(disarm_config)
    if result:
        g.camera.armed = 0
        g.camera.persist()
    return flask.jsonify({"result":result})

@app.route('/camera/<serial>/pirled', methods=['POST'])
@validate_camera_request()
def pir_led(serial):
    result = g.camera.pir_led(g.args)
    return flask.jsonify({"result":result})

@app.route('/camera/<serial>/quality', methods=['POST'])
@validate_camera_request()
def set_quality(serial):
    if g.args['quality'] is None:
        flask.abort(400)
    else:
        result = g.camera.set_quality(g.args)
        return flask.jsonify({"result":result})

@app.route('/camera/<serial>/registerset', methods=['POST'])
@validate_camera_request()
def register_set(serial):
    """Send a raw registerSet, e.g. {"SetValues": {"VideoTargetBitrate": 3000}}. For tuning."""
    values = g.args.get('SetValues')
    if not isinstance(values, dict) or not values:
        flask.abort(400)
    import copy
    msg = Message(copy.deepcopy(arlo.messages.REGISTER_SET))
    msg['SetValues'] = values
    return flask.jsonify({"result": g.camera.send_message(msg)})

@app.route('/camera/<serial>/raparams', methods=['POST'])
@validate_camera_request()
def ra_params(serial):
    """Send raw encoder rate-adaptation params, e.g. {"Params": {"1080p": {...}}}. For tuning."""
    params = g.args.get('Params')
    if not isinstance(params, dict) or not params:
        flask.abort(400)
    msg = Message({"Type": "raParams", "ID": -1, "Params": params})
    return flask.jsonify({"result": g.camera.send_message(msg)})

@app.route('/camera/<serial>/snapshot', methods=['POST'])
@validate_camera_request()
def request_snapshot(serial):
    if g.args['url'] is None:
        flask.abort(400)
    else:
        result = g.camera.snapshot_request(g.args['url'])
        return flask.jsonify({"result":result})

@app.route('/camera/<serial>/audiomic', methods=['POST'])
@validate_camera_request()
def request_mic(serial):
    if g.args['enabled'] is None:
        flask.abort(400)
    else:
        result = g.camera.mic_request(g.args['enabled'])
        return flask.jsonify({"result":result})

@app.route('/camera/<serial>/audiospeaker', methods=['POST'])
@validate_camera_request()
def request_speaker(serial):
    if g.args['enabled'] is None:
        flask.abort(400)
    else:
        result = g.camera.speaker_request(g.args['enabled'])
        return flask.jsonify({"result":result})

@app.route('/camera/<serial>/record', methods=['POST'])
@validate_camera_request()
def request_record(serial):
    if g.args['duration'] is None:
        flask.abort(400)
    else:
        result = g.camera.record(g.args['duration'], g.args['is4k'])
        return flask.jsonify({"result":result})

@app.route('/camera/<serial>/friendlyname', methods=['POST'])
@validate_camera_request()
def set_friendlyname(serial):
    if g.args['name'] is None:
        flask.abort(400)
    else:
        g.camera.friendly_name = g.args['name']
        g.camera.persist()

        return flask.jsonify({"result":True})

@app.route('/camera/<serial>/activityzones', methods=['POST','DELETE'])
@validate_camera_request()
def set_activity_zones(serial):
    if flask.request.method == 'DELETE':
        result = g.camera.unset_activity_zones()
    else:
        result = g.camera.set_activity_zones(g.args)

    return flask.jsonify({"result":result})

@app.route('/snapshot/<identifier>/', methods=['POST'])
def receive_snapshot(identifier):
    if 'file' not in flask.request.files:
        flask.abort(400)
    else:
        file = flask.request.files['file']
        if file.filename=='':
            flask.abort(400)
        else:
            start_path = os.path.abspath('/tmp')
            target_path = os.path.abspath(os.path.join(start_path,f"{identifier}.jpg"))
            if os.path.dirname(target_path) != start_path:
                flask.abort(400)
            else:
                file.save(target_path)
                events.publish("snapshot", serial=identifier, file=os.path.basename(target_path))
            return ""

@app.route('/camera/<serial>/stream/start', methods=['POST'])
@validate_camera_request(body_required=False)
def stream_start(serial):
    """Start HLS streaming from camera"""
    global active_streams

    # Check if stream already active for this camera
    if serial in active_streams:
        return flask.jsonify({
            "result": False,
            "error": "Stream already active for this camera"
        }), 400

    try:
        # Wake camera and wait for it to initialize
        g.camera.status_request()
        time.sleep(2)

        # Set UserStreamActive=1 and wait for RTSP port to open
        g.camera.set_user_stream_active(1)
        time.sleep(1)

        # Create StreamManager and start streaming
        stream_manager = StreamManager(
            camera_serial=serial,
            camera_ip=g.camera.ip,
            is4k=False,
            rtsp_transport=camera_profile(g.camera).get('rtsp_transport', 'udp')
        )

        if stream_manager.start(duration=60):
            active_streams[serial] = stream_manager
            return flask.jsonify({
                "result": True,
                "stream_url": f"/stream/{serial}/stream.m3u8"
            })
        else:
            return flask.jsonify({
                "result": False,
                "error": "Failed to start stream"
            }), 500

    except Exception as e:
        return flask.jsonify({
            "result": False,
            "error": str(e)
        }), 500

@app.route('/camera/<serial>/stream/stop', methods=['POST'])
@validate_camera_request(body_required=False)
def stream_stop(serial):
    """Stop HLS streaming from camera"""
    global active_streams

    if serial not in active_streams:
        return flask.jsonify({
            "result": False,
            "error": "No active stream for this camera"
        }), 400

    try:
        # Stop stream and cleanup
        stream_manager = active_streams[serial]
        stream_manager.stop()

        # Set UserStreamActive=0
        g.camera.set_user_stream_active(0)

        # Remove from active streams
        del active_streams[serial]

        return flask.jsonify({"result": True})

    except Exception as e:
        return flask.jsonify({
            "result": False,
            "error": str(e)
        }), 500

@app.route('/camera/<serial>/stream/status', methods=['GET'])
@validate_camera_request(body_required=False)
def stream_status(serial):
    """Check if stream is active for camera"""
    global active_streams

    if serial in active_streams and active_streams[serial].is_active():
        return flask.jsonify({
            "active": True,
            "stream_url": f"/stream/{serial}/stream.m3u8"
        })
    else:
        # Clean up inactive streams
        if serial in active_streams:
            del active_streams[serial]
        return flask.jsonify({"active": False})


@app.route('/events', methods=['GET'])
def event_stream():
    """Server-Sent Events: motion, motion_end, status, registration, snapshot, recording, connectivity."""
    return flask.Response(events.sse_stream(), mimetype='text/event-stream',
                          headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _latest_image(serial):
    """Newest of: last camera fullSnapshot upload, last motion-recording thumbnail."""
    candidates = []
    upload = f"/tmp/{serial}.jpg"
    if os.path.exists(upload):
        candidates.append(upload)
    base = CONFIG.get('RecordingBasePath')
    if base:
        thumbs = glob.glob(os.path.join(base, f"arlo-{glob.escape(serial)}-*.jpg"))
        if thumbs:
            candidates.append(max(thumbs, key=os.path.getmtime))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


@app.route('/camera/<serial>/snapshot.jpg', methods=['GET'])
@validate_camera_request(body_required=False)
def latest_snapshot(serial):
    """Latest still image. Never wakes the camera (safe for HA to poll)."""
    path = _latest_image(serial)
    if path is None:
        flask.abort(404)
    try:  # Flask >= 2.0
        return flask.send_file(path, mimetype='image/jpeg', conditional=True, max_age=0)
    except TypeError:  # Flask 1.x (pinned in requirements.txt)
        return flask.send_file(path, mimetype='image/jpeg', conditional=True, cache_timeout=0)


@app.route('/camera/<serial>/snapshot/refresh', methods=['POST'])
@validate_camera_request(body_required=False)
def refresh_snapshot(serial):
    """Ask the camera to upload a fresh JPEG (wakes the camera; costs battery)."""
    base_ip = CONFIG.get('BaseStationIp', '172.14.0.1')
    url = f"http://{base_ip}:5000/snapshot/{serial}/"
    result = g.camera.snapshot_request(url)
    return flask.jsonify({"result": result})


def _wait_for_port(ip, port, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((ip, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def apply_stream_bitrate(camera):
    """Pin the encoder to constant bitrate (config.yaml StreamBitrateKbps, 0 = camera default).

    Left to itself a Pro 4 runs VBR and drops to ~0.2 Mbps on a quiet scene;
    registerSet VideoTargetBitrate is ignored. raParams with vbr=false is
    honoured (verified VMC4041PB fw 34.0.17: 3000 -> ~2.7 Mbps measured).
    Sent before every stream because it is cheap and survives nothing we can see.
    """
    kbps = int(CONFIG.get('StreamBitrateKbps', 0) or 0)
    if kbps <= 0:
        return
    bps = kbps * 1024
    rate = {"minbps": bps // 2, "maxbps": bps * 4 // 3, "minQP": 18, "maxQP": 32,
            "vbr": False, "targetbps": bps, "cbrbps": bps}
    msg = Message({"Type": "raParams", "ID": -1,
                   "Params": {"1080p": dict(rate), "4K": dict(rate)}})
    if not camera.send_message(msg):
        print(f"[live {camera.serial_number}] raParams not acknowledged", flush=True)


@app.route('/camera/<serial>/live/prepare', methods=['POST'])
@validate_camera_request(body_required=False)
def live_prepare(serial):
    """Wake the camera and start its RTSP server. Used by helpers/live_publisher.py.

    Returns where to pull from and how to depayload it. Quality comes from
    config.yaml LiveStreamQuality ("1080p" default, or "2k" = the camera's HEVC
    2560x1440 server on models that have one); ?quality= overrides it. The
    camera serves one RTSP session at a time, so every consumer (live view,
    motion recordings) shares this one quality via the arlo_<serial> path.
    """
    if not g.camera.ip or g.camera.ip == 'UNKNOWN':
        return flask.jsonify({"result": False, "error": "camera IP unknown"}), 409
    profile = camera_profile(g.camera)
    port, codec = profile['rtsp_port'], profile['video_codec']
    quality = flask.request.args.get('quality') or str(CONFIG.get('LiveStreamQuality', '1080p'))
    if quality.lower() == '2k' and profile.get('rtsp_port_2k'):
        port, codec = profile['rtsp_port_2k'], profile.get('video_codec_2k', 'h265')
    with live_lock:
        live_sessions[serial] = live_sessions.get(serial, 0) + 1
    g.camera.status_request()  # wake-up nudge, as the HLS path does
    apply_stream_bitrate(g.camera)
    ok = g.camera.set_user_stream_active(1)
    port_open = _wait_for_port(g.camera.ip, port, 12)
    if not port_open:
        # Right after a previous stream the camera sometimes ignores the first
        # request ("no RTSPD started"); asking again usually opens it.
        g.camera.status_request()
        ok = g.camera.set_user_stream_active(1)
        port_open = _wait_for_port(g.camera.ip, port, 15)
    if port_open and profile.get('rtsp_ready_delay'):
        time.sleep(profile['rtsp_ready_delay'])
    events.publish("live", serial=serial, active=True)
    return flask.jsonify({
        "result": bool(ok and port_open),
        "rtsp_url": f"rtsp://{g.camera.ip}:{port}/live",
        "video_codec": codec,
        "audio": bool(profile['audio']),
        "model_name": profile['name'],
        "rtsp_transport": profile.get('rtsp_transport', 'udp'),
    })


@app.route('/camera/<serial>/live/release', methods=['POST'])
@validate_camera_request(body_required=False)
def live_release(serial):
    with live_lock:
        remaining = max(live_sessions.get(serial, 0) - 1, 0)
        live_sessions[serial] = remaining
    result = True
    if remaining == 0:
        result = g.camera.set_user_stream_active(0)
        events.publish("live", serial=serial, active=False)
    return flask.jsonify({"result": result, "sessions": remaining})


# serial -> (Popen, deadline) of the reader that keeps the camera awake for /live/wake
wake_holders = {}


@app.route('/camera/<serial>/live/wake', methods=['POST'])
@validate_camera_request(body_required=False)
def live_wake(serial):
    """Keep the camera streaming for N seconds (default 120) with nobody watching.

    Opens the on-demand MediaMTX path as a throw-away reader, which wakes the
    camera; arlo_<serial>_feed (always_on_feed.py) then shows it live. Calling it
    again while awake restarts the timer. {"seconds": 0} lets it sleep now.
    """
    import subprocess
    body = flask.request.get_json(silent=True) or {}
    seconds = int(body.get('seconds', flask.request.args.get('seconds', 120)))
    seconds = max(0, min(seconds, 1800))
    with live_lock:
        old = wake_holders.pop(serial, None)
        if old and old[0].poll() is None:
            old[0].terminate()
        if seconds:
            url = f"{CONFIG.get('MediaMtxRtspUrl', 'rtsp://127.0.0.1:8554')}/arlo_{serial}"
            proc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'quiet', '-rtsp_transport', 'tcp',
                                     '-i', url, '-t', str(seconds), '-c', 'copy', '-f', 'null', '-'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wake_holders[serial] = (proc, time.time() + seconds)
            threading.Thread(target=proc.wait, daemon=True).start()  # reap, no zombie
    return flask.jsonify({"result": True, "seconds": seconds})


def get_thread():
    return threading.Thread(target=app.run(host='0.0.0.0'))
