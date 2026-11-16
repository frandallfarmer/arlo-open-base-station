#!/usr/bin/env python3
"""Wakes a camera while somebody watches rtsp://BASE:8554/arlo_<serial>_view.

arlo_<serial>_view is published all the time by always_on_feed.py (same picture
as arlo_<serial>_feed), so players get video instantly - NVR players such as
Frigate's give up long before a battery camera has woken and opened RTSP.
MediaMTX runs this script (runOnRead) for every reader of the view path and
stops it when that reader leaves. While it runs it reads arlo_<serial> (and
throws the data away), which wakes the camera and keeps it awake; the feed sees
the camera live and switches the picture from the last frame to live video.

Usage: view_publisher.py <CAMERA_SERIAL | arlo_<serial>_view>. System python3.
"""
import os
import re
import signal
import subprocess
import sys
import time

MEDIAMTX = os.environ.get('ARLO_MEDIAMTX', 'rtsp://127.0.0.1:8554')
RETRY_S = 30  # don't hammer a camera that failed to open RTSP

if len(sys.argv) != 2:
    sys.exit(f"usage: {sys.argv[0]} <CAMERA_SERIAL>")
serial = re.sub(r'^arlo_|_view$', '', sys.argv[1])
stopping = []
signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
signal.signal(signal.SIGINT, lambda *_: stopping.append(1))


def log(msg):
    print(f"[view {serial}] {msg}", file=sys.stderr, flush=True)


def main():
    proc, started = None, -RETRY_S
    log("viewer connected - waking camera")
    try:
        while not stopping:
            if (proc is None or proc.poll() is not None) and time.monotonic() - started >= RETRY_S:
                if proc is not None:
                    log(f"camera stream ended ({proc.returncode}), waking again")
                proc = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'quiet', '-rtsp_transport', 'tcp',
                                         '-i', f"{MEDIAMTX}/arlo_{serial}", '-map', '0:v:0',
                                         '-c', 'copy', '-f', 'null', '-'])
                started = time.monotonic()
            time.sleep(0.5)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        log("viewer left - camera may sleep")
    return 0


if __name__ == '__main__':
    sys.exit(main())
