#!/usr/bin/env python3
"""On-demand live relay: camera RTSP -> MediaMTX (rtsp://127.0.0.1:8554/arlo_<serial>).

Started by MediaMTX (runOnDemand) when the first client opens the path and sent
SIGTERM when the last one leaves. Uses GStreamer because Arlo cameras drop the
stream unless they get RTCP receiver reports every ~5 s (FFmpeg sends every 10 s).
Pro 3/4-class cameras time out after 20 s over UDP regardless, so their profile
selects RTSP-over-TCP (rtsp_transport in arlo/models.py). GStreamer's rtspsrc
cannot parse the camera's interleaved TCP framing ("Parse error"), so the TCP
path relays with FFmpeg instead, which resyncs on it fine.

Usage: live_publisher.py <CAMERA_SERIAL>
Stream quality (1080p H.264 / 2K HEVC) is chosen by config.yaml LiveStreamQuality.
Runs with the system python3 (needs python3-gi + gstreamer1.0-rtsp), not the venv.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib  # noqa: E402

API = os.environ.get('ARLO_API', 'http://127.0.0.1:5000')
MEDIAMTX = os.environ.get('ARLO_MEDIAMTX', 'rtsp://127.0.0.1:8554')


def api_post(path):
    req = urllib.request.Request(f"{API}{path}", data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode() or '{}')


def build_pipeline(src_url, dst_url, codec, audio):
    if codec == 'h265':
        video = 'rtph265depay ! h265parse config-interval=-1'
    else:
        video = 'rtph264depay ! h264parse config-interval=-1'
    desc = (
        f'rtspsrc location={src_url} latency=200 name=src '
        f'rtspclientsink name=out location={dst_url} protocols=tcp '
        f'src. ! application/x-rtp,media=video ! {video} ! queue ! out. '
    )
    if audio:
        desc += ('src. ! application/x-rtp,media=audio,encoding-name=MPEG4-GENERIC '
                 '! rtpmp4gdepay ! aacparse ! queue ! out. ')
    return desc


def select_stream(_src, num, caps, audio=True):
    st = caps.get_structure(0)
    media = st.get_string('media')
    enc = (st.get_string('encoding-name') or '').upper()
    keep = media == 'video' or (media == 'audio' and enc == 'MPEG4-GENERIC')
    print(f"[live] stream {num}: media={media} encoding={enc} -> {'use' if keep else 'skip'}", flush=True)
    return keep


def ffmpeg_relay(src_url, dst_url, audio, should_stop):
    """Relay over RTSP-interleaved TCP with FFmpeg (stream copy). Returns exit code."""
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'warning',
           '-rtsp_transport', 'tcp', '-timeout', '10000000', '-i', src_url,
           '-map', '0:v:0']
    if audio:
        cmd += ['-map', '0:a:0?']  # first audio track is AAC; skip the Opus one
    cmd += ['-c', 'copy', '-f', 'rtsp', '-rtsp_transport', 'tcp', dst_url]
    proc = subprocess.Popen(cmd)
    try:
        while proc.poll() is None:
            if should_stop():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return 0
            time.sleep(0.2)
        return proc.returncode
    finally:
        if proc.poll() is None:
            proc.kill()


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <CAMERA_SERIAL>", file=sys.stderr)
        return 2
    serial = sys.argv[1]
    released = False

    def release():
        nonlocal released
        if not released:
            released = True
            try:
                api_post(f"/camera/{serial}/live/release")
            except Exception as e:  # noqa: BLE001
                print(f"[live {serial}] release failed: {e}", file=sys.stderr)

    # Every prepare call takes a live-session reference on the API side, so
    # always pair it with a release - or the camera is left streaming (and
    # draining its battery). If MediaMTX stops us mid-prepare, let the prepare
    # request finish first: releasing while it is still in flight makes the
    # API count drop before it rises, leaving a session that is never released
    # and a camera that refuses the next wake.
    stop_flag = []
    signal.signal(signal.SIGTERM, lambda *_: stop_flag.append(1))
    signal.signal(signal.SIGINT, lambda *_: stop_flag.append(1))
    info = {}
    for attempt in range(1, 3):
        try:
            info = api_post(f"/camera/{serial}/live/prepare")
        except Exception as e:  # noqa: BLE001
            print(f"[live {serial}] prepare failed: {e!r}", file=sys.stderr)
            release()
            return 1
        if stop_flag:
            print(f"[live {serial}] stopped while waking the camera", file=sys.stderr, flush=True)
            release()
            return 0
        if info.get('result'):
            break
        print(f"[live {serial}] camera did not open RTSP (attempt {attempt}): {info}", file=sys.stderr, flush=True)
        release()
        released = False
    if not info.get('result'):
        return 1

    dst_url = f"{MEDIAMTX}/arlo_{serial}"
    if info.get('rtsp_transport') == 'tcp':
        print(f"[live {serial}] {info.get('model_name')}: ffmpeg TCP relay {info['rtsp_url']} -> {dst_url}", flush=True)
        rc = 1
        try:
            # Right after waking the camera can refuse/close RTSP for several
            # seconds; keep retrying rather than give up and make MediaMTX
            # restart the whole prepare/wake cycle.
            for attempt in range(1, 13):
                started = time.monotonic()
                rc = ffmpeg_relay(info['rtsp_url'], dst_url, info.get('audio', True), lambda: bool(stop_flag))
                ran_for = time.monotonic() - started
                if stop_flag or rc == 0 or ran_for > 8:
                    break
                print(f"[live {serial}] early failure after {ran_for:.1f}s, retry {attempt}", file=sys.stderr, flush=True)
                time.sleep(3)
        finally:
            release()
        return rc

    Gst.init(None)
    desc = build_pipeline(info['rtsp_url'], dst_url,
                          info.get('video_codec', 'h264'), info.get('audio', True))
    print(f"[live {serial}] {info.get('model_name')}: {desc}", flush=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
        if loop is not None:
            loop.quit()
        return GLib.SOURCE_REMOVE

    loop = None
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, stop)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, stop)

    rc = 1
    try:
        # The camera sometimes drops the first RTSP request while its encoder
        # spins up; retry a failure that happens in the first few seconds.
        for attempt in range(1, 7):
            pipeline = Gst.parse_launch(desc)
            # Arlo Pro 3/4 offer a third RTSP track that nothing consumes. If it is
            # SETUP but never reported on, the camera hits its RTCP timeout ~30 s
            # in, stops streaming and drops off Wi-Fi. Only SETUP what we use.
            pipeline.get_by_name('src').connect('select-stream', select_stream)
            loop = GLib.MainLoop()
            state = {"rc": 0}
            started = GLib.get_monotonic_time()

            def on_message(_bus, msg, state=state, loop=loop):
                if msg.type == Gst.MessageType.EOS:
                    loop.quit()
                elif msg.type == Gst.MessageType.ERROR:
                    err, dbg = msg.parse_error()
                    print(f"[live {serial}] GStreamer error: {err} ({dbg})", file=sys.stderr, flush=True)
                    state["rc"] = 1
                    loop.quit()

            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', on_message)
            pipeline.set_state(Gst.State.PLAYING)
            loop.run()
            pipeline.set_state(Gst.State.NULL)
            bus.remove_signal_watch()
            rc = state["rc"]
            ran_for = (GLib.get_monotonic_time() - started) / 1e6
            if stopping or rc == 0 or ran_for > 8:
                break
            print(f"[live {serial}] early failure after {ran_for:.1f}s, retry {attempt}", file=sys.stderr, flush=True)
            GLib.usleep(3_000_000)
    finally:
        release()
    return rc


if __name__ == '__main__':
    sys.exit(main())
