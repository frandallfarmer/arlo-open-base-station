#!/usr/bin/env python3
"""Always-on feed for NVRs (Frigate, Blue Iris...) that keep RTSP open 24/7.

Publishes rtsp://127.0.0.1:8554/arlo_<serial>_feed: a constant H.264 stream
that never disconnects and never wakes the camera by itself.

* While the camera is streaming for someone else (motion recording, a viewer on
  arlo_<serial>, POST /camera/<serial>/live/wake) the feed carries its live video.
* Otherwise it repeats the last live frame (at start-up: the camera's latest
  snapshot) with a small "asleep since HH:MM" caption.

So an NVR pointed at the feed costs the camera nothing; it goes live whenever
the camera is awake anyway. To watch on demand, open arlo_<serial> (which wakes
the camera) or call the wake endpoint - the feed follows automatically.

Usage: always_on_feed.py <CAMERA_SERIAL>
Needs the MediaMTX API on 127.0.0.1:9997 (to see whether the camera is live
without becoming a reader that keeps it awake). System python3, no extra modules.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

API = os.environ.get('ARLO_API', 'http://127.0.0.1:5000')
MEDIAMTX = os.environ.get('ARLO_MEDIAMTX', 'rtsp://127.0.0.1:8554')
MEDIAMTX_API = os.environ.get('ARLO_MEDIAMTX_API', 'http://127.0.0.1:9997')
W, H, FPS = 1920, 1080, 15
FRAME = W * H * 3 // 2  # yuv420p
FIT = f'scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuv420p'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
STATE_DIR = os.environ.get('ARLO_FEED_DIR', '/run/arlo-feed')
BITRATE = os.environ.get('ARLO_FEED_MAXRATE', '4M')

serial = sys.argv[1] if len(sys.argv) == 2 else sys.exit(f"usage: {sys.argv[0]} <CAMERA_SERIAL>")
live_path = f"arlo_{serial}"
caption_file = os.path.join(STATE_DIR, f"{serial}.txt")
last_jpg = os.path.join(STATE_DIR, f"{serial}-last.jpg")

lock = threading.Lock()
frame = bytes(FRAME)  # black until we have something better
stopping = threading.Event()


def log(msg):
    print(f"[feed {serial}] {msg}", flush=True)


def set_caption(text):
    # drawtext reloads the file every frame; write atomically so it never sees a half file.
    tmp = caption_file + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text or ' ')
    os.replace(tmp, caption_file)


def read_caption():
    try:
        with open(caption_file) as f:
            return f.read()
    except OSError:
        return ' '


def decode_one(path_or_url):
    """Decode a single image (file or URL) to one yuv420p frame, or None."""
    try:
        out = subprocess.run(['ffmpeg', '-v', 'error', '-i', path_or_url, '-frames:v', '1',
                              '-vf', FIT, '-f', 'rawvideo', '-'],
                             capture_output=True, timeout=20).stdout
        return out if len(out) == FRAME else None
    except Exception:  # noqa: BLE001
        return None


def path_status():
    """(ready, reader_count) of the camera's on-demand path; (False, 0) if idle.
    (False, n>0) means someone opened it and the camera is still waking up."""
    try:
        with urllib.request.urlopen(f"{MEDIAMTX_API}/v3/paths/get/{live_path}", timeout=2) as r:
            d = json.load(r)
        return bool(d.get('ready')), len(d.get('readers') or []) or (0 if d.get('ready') else 1)
    except Exception:  # noqa: BLE001 - 404 when the path is idle
        return False, 0


def save_last_frame(data):
    try:
        p = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'yuv420p',
                            '-s', f'{W}x{H}', '-i', '-', '-frames:v', '1', '-q:v', '3', '-y',
                            last_jpg + '.tmp.jpg'], input=data, timeout=20)
        if p.returncode == 0:
            os.replace(last_jpg + '.tmp.jpg', last_jpg)
    except Exception:  # noqa: BLE001
        pass


def live_reader():
    """Follow the camera while somebody else keeps it awake."""
    global frame
    asleep_caption, waking_since = None, 0.0
    while not stopping.is_set():
        ready, readers = path_status()
        if not ready or readers == 0:
            if readers and asleep_caption is None:  # path requested, camera not streaming yet
                asleep_caption = read_caption()
                waking_since = time.monotonic()
                set_caption('Waking camera...')
            elif readers and time.monotonic() - waking_since > 25:
                set_caption(f"Camera not answering yet - retrying ({int(time.monotonic() - waking_since)} s)")
            elif not readers and asleep_caption is not None:  # wake attempt gave up
                set_caption(asleep_caption)
                asleep_caption = None
            time.sleep(1)
            continue
        asleep_caption = None
        log(f"camera is live ({readers} reader(s)) - following")
        set_caption('LIVE')
        proc = subprocess.Popen(['ffmpeg', '-v', 'error', '-rtsp_transport', 'tcp',
                                 '-i', f"{MEDIAMTX}/{live_path}", '-an', '-vf', FIT,
                                 '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
        got = None
        last_check = time.monotonic()
        try:
            while not stopping.is_set():
                buf = proc.stdout.read(FRAME)
                if not buf or len(buf) < FRAME:
                    break
                got = buf
                with lock:
                    frame = buf
                if time.monotonic() - last_check >= 1:
                    last_check = time.monotonic()
                    ready, readers = path_status()
                    if not ready or readers <= 1:  # only us left: let the camera sleep
                        break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        set_caption(f"Camera asleep - last live {time.strftime('%H:%M:%S')}")
        log("camera went back to sleep - holding last frame")
        if got:
            save_last_frame(got)
        # Our RTSP session can linger a few seconds after ffmpeg exits; don't
        # mistake it for another viewer and rejoin.
        deadline = time.monotonic() + 15
        while not stopping.is_set() and time.monotonic() < deadline:
            if path_status()[1] == 0:
                break
            time.sleep(1)


def main():
    global frame
    os.makedirs(STATE_DIR, exist_ok=True)
    set_caption('Camera asleep - open live view to wake')
    first = decode_one(last_jpg) if os.path.exists(last_jpg) else None
    first = first or decode_one(f"{API}/camera/{serial}/snapshot.jpg")
    if first:
        frame = first

    def stop(*_):
        stopping.set()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    threading.Thread(target=live_reader, daemon=True).start()

    draw = (f"drawtext=fontfile={FONT}:textfile={caption_file}:reload=1:"
            "fontcolor=white:fontsize=28:box=1:boxcolor=black@0.5:boxborderw=8:x=20:y=h-th-24")
    enc_cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'warning',
               '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-s', f'{W}x{H}', '-framerate', str(FPS),
               '-i', '-', '-vf', draw,
               '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
               '-profile:v', 'high', '-crf', '23', '-maxrate', BITRATE, '-bufsize', '8M',
               '-g', str(FPS), '-keyint_min', str(FPS), '-sc_threshold', '0',
               '-flags', '+global_header', '-map', '0:v',
               '-f', 'tee', '|'.join(f"[f=rtsp:rtsp_transport=tcp:onfail=ignore]{MEDIAMTX}/{live_path}_{p}"
                                     for p in ('feed', 'view'))]
    while not stopping.is_set():
        log(f"publishing {MEDIAMTX}/{live_path}_feed and _view")
        enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)
        nxt = time.monotonic()
        try:
            while not stopping.is_set() and enc.poll() is None:
                with lock:
                    data = frame
                enc.stdin.write(data)
                nxt += 1.0 / FPS
                delay = nxt - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -1:  # fell behind (CPU spike): resync instead of bursting
                    nxt = time.monotonic()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                enc.stdin.close()
            except OSError:
                pass
            enc.terminate()
            try:
                enc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                enc.kill()
        if not stopping.is_set():
            log("encoder exited, restarting in 3 s")
            time.sleep(3)
    return 0


if __name__ == '__main__':
    sys.exit(main())
