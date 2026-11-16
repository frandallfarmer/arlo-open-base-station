#!/usr/bin/env python3
"""GStreamer HLS streaming helper for Arlo cameras.

Usage: gst_hls_stream.py <rtsp_url> <output_dir> <duration> [udp|tcp]

Uses GStreamer with Python bindings to handle the complex pipeline
that includes both video (H264) and audio (AAC) streams.
"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import os
import signal

def main():
    if len(sys.argv) not in (4, 5):
        print(f"Usage: {sys.argv[0]} <rtsp_url> <output_dir> <duration> [udp|tcp]")
        sys.exit(1)

    rtsp_url = sys.argv[1]
    output_dir = sys.argv[2]
    duration = int(sys.argv[3])
    transport = sys.argv[4] if len(sys.argv) == 5 else 'udp'

    if transport == 'tcp':
        # Pro 3/4: UDP times out after 20 s, and GStreamer's rtspsrc cannot
        # parse the camera's interleaved TCP framing - let FFmpeg do it.
        os.makedirs(output_dir, exist_ok=True)
        os.execvp('ffmpeg', [
            'ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'warning',
            '-rtsp_transport', 'tcp', '-timeout', '10000000', '-i', rtsp_url,
            '-t', str(duration), '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy',
            '-f', 'hls', '-hls_time', '2', '-hls_list_size', '3',
            '-hls_flags', 'delete_segments',
            '-hls_segment_filename', f'{output_dir}/segment%05d.ts',
            f'{output_dir}/stream.m3u8'])

    Gst.init(None)
    os.makedirs(output_dir, exist_ok=True)

    # Pipeline with video and audio - uses hlssink2's built-in muxer
    pipeline_str = f'''
        rtspsrc location={rtsp_url} latency=100 name=src
        hlssink2 name=hls location={output_dir}/segment%05d.ts playlist-location={output_dir}/stream.m3u8 target-duration=2 max-files=3
        
        src. ! application/x-rtp,media=video ! rtph264depay ! h264parse ! queue ! hls.video
        src. ! application/x-rtp,media=audio,encoding-name=MPEG4-GENERIC ! rtpmp4gdepay ! aacparse ! queue ! hls.audio
    '''

    pipeline = Gst.parse_launch(pipeline_str)
    loop = GLib.MainLoop()

    def on_message(bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("EOS received")
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}")
            loop.quit()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)

    # Handle termination signals
    def signal_handler(sig, frame):
        print("Signal received, stopping...")
        pipeline.send_event(Gst.Event.new_eos())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Timeout to stop after duration
    def timeout_callback():
        print(f"Duration {duration}s reached, stopping...")
        pipeline.send_event(Gst.Event.new_eos())
        return False

    GLib.timeout_add_seconds(duration, timeout_callback)

    print(f"Starting HLS stream from {rtsp_url}")
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    except:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)
        print("Stream stopped")

if __name__ == "__main__":
    main()
