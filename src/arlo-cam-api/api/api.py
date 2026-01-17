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

app = flask.Flask(__name__)
app.config["DEBUG"] = False
app.use_reloader=False

# Global dict to track active streams
active_streams = {}

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
        c.execute("SELECT * FROM camera")
        rows = c.fetchall()
        cameras = []
        if rows is not None:
            for row in rows:
                (ip,serial_number,hostname,registration,status,friendly_name) = row
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

                if status_json:
                    try:
                        status_data = Message.from_json(status_json)
                        battery_percent = status_data.dictionary.get('BatPercent')
                        signal_strength = status_data.dictionary.get('SignalStrengthIndicator')
                        charging_state = status_data.dictionary.get('ChargingState')
                        charger_tech = status_data.dictionary.get('ChargerTech')
                        battery_voltage = status_data.dictionary.get('Bat1Volt')
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
            target_path = os.path.join(start_path,f"{identifier}.jpg")
            common_prefix = os.path.commonprefix([target_path, start_path])
            if (common_prefix != start_path):
                flask.abort(400)
            else:
                file.save(target_path)
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
            is4k=False
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


def get_thread():
    return threading.Thread(target=app.run(host='0.0.0.0'))
