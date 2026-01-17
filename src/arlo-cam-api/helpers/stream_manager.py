import os
import subprocess
import shutil
import threading
from helpers.safe_print import s_print


class StreamManager:
    """Manages HLS streaming from Arlo camera RTSP feeds using GStreamer

    GStreamer is used instead of ffmpeg because Arlo cameras require RTCP responses
    at 5-second intervals. FFmpeg sends RTCP at 10-second intervals (hardcoded) which
    causes the camera to kill the stream after ~10 seconds. GStreamer sends RTCP at
    the correct 5-second interval.
    """

    def __init__(self, camera_serial, camera_ip, camera=None, is4k=False):
        self.camera_serial = camera_serial
        self.camera_ip = camera_ip
        self.camera = camera  # Not used but kept for API compatibility
        self.is4k = is4k
        self.gst_process = None
        self.cleanup_timer = None

        # Stream directory and file paths
        self.stream_dir = f"/tmp/arlo-stream/{camera_serial}"
        self.playlist_path = f"{self.stream_dir}/stream.m3u8"

        # RTSP URL
        self.rtsp_url = f"rtsp://{camera_ip}/live"

    def start(self, duration=60):
        """
        Start GStreamer HLS streaming process

        Args:
            duration: Stream duration in seconds (default 60)

        Returns:
            bool: True if stream started successfully, False otherwise
        """
        try:
            # Create stream directory
            os.makedirs(self.stream_dir, exist_ok=True)

            # Use Python GStreamer helper script for audio+video pipeline
            helper_script = os.path.join(os.path.dirname(__file__), 'gst_hls_stream.py')
            gst_cmd = [
                'python3', helper_script,
                self.rtsp_url,
                self.stream_dir,
                str(duration)
            ]

            s_print(f"[StreamManager] Starting GStreamer for {self.camera_serial} at {self.rtsp_url}")
            s_print(f"[StreamManager] Command: {' '.join(gst_cmd)}")

            # Start GStreamer process
            self.gst_process = subprocess.Popen(
                gst_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Schedule cleanup after duration (with buffer for EOS handling)
            self.cleanup_timer = threading.Timer(duration + 10, self._cleanup)
            self.cleanup_timer.start()

            s_print(f"[StreamManager] GStreamer started successfully for {self.camera_serial}")
            return True

        except Exception as e:
            s_print(f"[StreamManager] Error starting GStreamer for {self.camera_serial}: {e}")
            self._cleanup()
            return False

    def stop(self):
        """
        Stop the GStreamer streaming process and cleanup

        Returns:
            bool: True if stopped successfully
        """
        s_print(f"[StreamManager] Stopping stream for {self.camera_serial}")
        self._cleanup()
        return True

    def _cleanup(self):
        """Internal cleanup method - terminates GStreamer and deletes temp files"""
        try:
            # Cancel cleanup timer if running
            if self.cleanup_timer and self.cleanup_timer.is_alive():
                self.cleanup_timer.cancel()
                self.cleanup_timer = None

            # Terminate GStreamer process
            if self.gst_process and self.gst_process.poll() is None:
                s_print(f"[StreamManager] Terminating GStreamer for {self.camera_serial}")
                self.gst_process.terminate()

                # Wait up to 3 seconds for graceful shutdown
                try:
                    self.gst_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    s_print(f"[StreamManager] Force killing GStreamer for {self.camera_serial}")
                    self.gst_process.kill()

                self.gst_process = None

            # Delete stream directory and all files
            if os.path.exists(self.stream_dir):
                s_print(f"[StreamManager] Cleaning up stream directory: {self.stream_dir}")
                shutil.rmtree(self.stream_dir, ignore_errors=True)

            s_print(f"[StreamManager] Cleanup complete for {self.camera_serial}")

        except Exception as e:
            s_print(f"[StreamManager] Error during cleanup for {self.camera_serial}: {e}")

    def get_playlist_path(self):
        """
        Get the path to the HLS playlist file

        Returns:
            str: Path to the .m3u8 playlist file
        """
        return self.playlist_path

    def is_active(self):
        """
        Check if the stream is currently active

        Returns:
            bool: True if GStreamer process is running, False otherwise
        """
        return self.gst_process is not None and self.gst_process.poll() is None
