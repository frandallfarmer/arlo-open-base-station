# On-Demand Live Streaming Implementation Plan

## Overview

Add a "Start Live Stream" button to the camera status dashboard that allows viewing the live camera feed in the browser for 60 seconds with automatic timeout.

## Technology Stack

**HLS (HTTP Live Streaming)** via ffmpeg conversion from RTSP:
- ✅ Browser-native support (HTML5 video)
- ✅ Works with existing ffmpeg installation
- ✅ Proven RTSP connectivity pattern (from motion recording)
- ✅ Acceptable 5-10 second latency for security cameras
- ✅ No re-encoding needed (copy video codec)

## Architecture

```
Camera RTSP:554 → ffmpeg (Flask) → HLS segments → Express → Browser
                   (/tmp/arlo-stream/)
```

**Stream Lifecycle:**
1. User clicks "Start Live Stream" button
2. Backend wakes camera with `status_request()`, waits 2 seconds
3. Backend sets `UserStreamActive=1`, starts ffmpeg HLS conversion
4. Frontend displays video player with HLS.js, shows 60-second countdown
5. Auto-stop after 60 seconds OR manual stop via button
6. Cleanup: kill ffmpeg, delete temp files, set `UserStreamActive=0`

## Implementation Details

### 1. Backend: Stream Manager (NEW FILE)

**File:** `/opt/arlo-cam-api/helpers/stream_manager.py`

Create new Python class to manage HLS streaming:

```python
class StreamManager:
    - __init__(camera_serial, camera_ip, is4k=False)
    - start(duration=60) - spawns ffmpeg process for HLS conversion
    - stop() - terminates ffmpeg, cleanup temp files
    - get_playlist_path() - returns path to .m3u8 file
```

**Key ffmpeg parameters:**
- `-rtsp_transport tcp` - reliable connection
- `-c:v copy` - no re-encoding (fast, low CPU)
- `-c:a aac` - audio transcode for browser compatibility
- `-f hls` - HLS output format
- `-hls_time 2` - 2-second segments (lower latency)
- `-hls_list_size 3` - keep 3 segments (6 seconds buffer)
- `-hls_flags delete_segments` - auto-cleanup old segments
- `-t 60` - enforce 60-second timeout

**Stream storage:** `/tmp/arlo-stream/<serial>/stream.m3u8` (per-camera directories)

**Timeout handling:** Python threading.Timer for auto-cleanup after 60 seconds

### 2. Backend: Flask API Endpoints (MODIFY)

**File:** `/opt/arlo-cam-api/api/api.py`

Add three new endpoints:

1. **POST `/camera/<serial>/stream/start`**
   - Wake camera: `g.camera.status_request()`, sleep 2 seconds
   - Set `UserStreamActive=1`
   - Create StreamManager, call `start(duration=60)`
   - Track in `active_streams` dict
   - Return `{"result": true, "stream_url": "/stream/<serial>/stream.m3u8"}`

2. **POST `/camera/<serial>/stream/stop`**
   - Stop StreamManager, cleanup temp files
   - Set `UserStreamActive=0`
   - Remove from `active_streams` dict
   - Return `{"result": true}`

3. **GET `/camera/<serial>/stream/status`**
   - Check if serial in `active_streams`
   - Return `{"active": true/false, "stream_url": "..."}`

**Global state:** `active_streams = {}` dictionary at module level

**Cleanup on startup:** Delete `/tmp/arlo-stream/` directory on Flask app initialization

### 3. Frontend: Express Server Proxying (MODIFY)

**File:** `/home/randy/arlo-viewer/server.js`

Add four new endpoints:

1. **POST `/api/camera/:serial/stream/start`** - proxy to Flask backend
2. **POST `/api/camera/:serial/stream/stop`** - proxy to Flask backend
3. **GET `/api/camera/:serial/stream/status`** - proxy to Flask backend
4. **GET `/api/stream/:serial/:file`** - serve HLS files from `/tmp/arlo-stream/`

**File serving:**
- `.m3u8` files: `Content-Type: application/vnd.apple.mpegurl`
- `.ts` segments: `Content-Type: video/mp2t`
- Add `Cache-Control: no-cache` header
- Security: validate filename (no `..` or `/` characters)

### 4. Frontend: Status Page Button (MODIFY)

**File:** `/home/randy/arlo-viewer/public/status.html`

**Issue:** Status page auto-refreshes every 30 seconds - embedding video player would cause interruptions

**Solution:** Add button that opens streaming in a **new window/tab**

**CSS additions:** (add to `<style>` section)
- `.stream-button` - purple gradient button matching existing style

**HTML additions:** (add to each camera card after Motion Detection section)
```html
<button class="stream-button" onclick="openStreamWindow('${camera.serial_number}', '${camera.friendly_name}')">
    Start Live Stream
</button>
```

**JavaScript additions:** (add to `<script>` section)
```javascript
function openStreamWindow(serial, friendlyName) {
    const url = `/stream.html?serial=${serial}&name=${encodeURIComponent(friendlyName)}`;
    window.open(url, `stream-${serial}`, 'width=800,height=600');
}
```

**Button state:** Disable when `camera.online === false`

### 5. Frontend: Dedicated Streaming Page (CREATE)

**File:** `/home/randy/arlo-viewer/public/stream.html`

**Purpose:** Dedicated page for video streaming (no auto-refresh, won't interrupt stream)

**HTML structure:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>Live Stream</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        /* Styling for video player, controls, countdown timer */
    </style>
</head>
<body>
    <div class="stream-container">
        <h2 id="camera-name">Camera Stream</h2>
        <div class="stream-controls">
            <button id="stop-button">Stop Stream</button>
            <span id="countdown">60s</span>
        </div>
        <video id="video-player" controls autoplay></video>
        <div id="status-message">Initializing stream...</div>
    </div>
    <script>
        // Get serial from URL params
        // Call /api/camera/${serial}/stream/start
        // Initialize HLS player
        // Start countdown timer
        // Auto-stop at 0s or manual stop
    </script>
</body>
</html>
```

**JavaScript functionality:**
- `initStream()` - Parse URL params, call start API, init HLS player
- `startCountdown()` - 60-second countdown using `setInterval`
- `stopStream()` - Call stop API, close window
- `setupHLS()` - Initialize HLS.js or native Safari player

**HLS player initialization:**
```javascript
const video = document.getElementById('video-player');
if (Hls.isSupported()) {
    const hls = new Hls();
    hls.loadSource(streamUrl);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play();
    });
} else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = streamUrl; // Native Safari support
    video.play();
}
```

**Countdown timer:**
- Starts at 60 seconds, decrements every second
- Auto-calls `stopStream()` when reaches 0
- Cleared on manual stop button click
- Window closes after stream stops

### 6. Dependencies

**Already installed:**
- ffmpeg 6.1.1 ✓
- Python 3.x ✓
- Node.js/Express ✓

**New dependency:** HLS.js (CDN, no installation needed)

## Critical Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `/opt/arlo-cam-api/helpers/stream_manager.py` | **CREATE** | ffmpeg process management, HLS conversion, timeout, cleanup |
| `/opt/arlo-cam-api/api/api.py` | **MODIFY** | Add 3 stream endpoints, global `active_streams` dict, cleanup on startup |
| `/home/randy/arlo-viewer/server.js` | **MODIFY** | Add 4 proxy/serving endpoints for stream control and HLS files |
| `/home/randy/arlo-viewer/public/status.html` | **MODIFY** | Add "Start Live Stream" button that opens new window |
| `/home/randy/arlo-viewer/public/stream.html` | **CREATE** | Dedicated streaming page with video player, countdown, stop button |
| `/opt/arlo-cam-api/arlo/camera.py` | **REFERENCE** | Use existing `status_request()` and `set_user_stream_active()` methods |

## Error Handling

**Camera offline:** Button disabled when `camera.online === false`

**Stream initialization failure:** Show alert, reset button to "Start Live Stream"

**Network interruption:** ffmpeg auto-terminates, frontend shows error, cleanup happens

**Multiple concurrent streams:** Supported via per-camera directories and tracking dict

**Server restart with active streams:** Cleanup `/tmp/arlo-stream/` on Flask startup

**Leftover temp files:** Auto-deleted by `delete_segments` flag; manual cleanup on startup

## Battery Camera Considerations

**Wake-up sequence:**
1. Send `status_request()` to wake camera
2. Wait 2 seconds for camera to initialize
3. Set `UserStreamActive=1`
4. Wait 0.5 seconds
5. Start ffmpeg RTSP connection

**Battery impact:** Approximately 5-8% drain per 60-second stream session

**Best practices:**
- Only enable when camera is online (awake)
- Keep to 60-second limit for battery health
- Avoid during charging
- Monitor battery levels after testing

## Testing & Verification

### Basic Functionality
1. Navigate to `https://security.thefarmers.org/status.html`
2. Ensure camera shows "Online" status
3. Click "Start Live Stream" button
4. **Verify:** New window/tab opens with stream.html
5. **Verify:** Stream initialization message appears, countdown shows "60s"
6. **Verify:** After 5-10 seconds, video player appears with live feed
7. **Verify:** Video plays smoothly, audio works
8. **Verify:** Countdown decrements (59s, 58s, ...)

### Auto-Timeout
1. Start stream, wait full 60 seconds without clicking stop
2. **Verify:** Stream stops automatically at 0s
3. **Verify:** Stream window closes automatically
4. **Verify:** Temp files deleted (`ls /tmp/arlo-stream/` should be empty)

### Manual Stop
1. Start stream, wait 10 seconds (let it initialize)
2. Click "Stop Stream" button in stream window
3. **Verify:** Stream stops immediately
4. **Verify:** Countdown timer stops
5. **Verify:** Window closes
6. **Verify:** Temp files cleaned up

### Error Conditions
1. **Offline camera:** Verify button is disabled
2. **Network failure:** Disconnect WiFi during stream, verify graceful error
3. **Rapid clicks:** Click start/stop rapidly, verify no race conditions
4. **Multiple cameras:** Start streams on 2 cameras simultaneously, verify both work

### Backend Verification
```bash
# Check Flask is running
curl http://localhost:5000/

# Check stream directory structure after starting stream
ls -la /tmp/arlo-stream/<serial>/

# Should see: stream.m3u8, stream0.ts, stream1.ts, stream2.ts

# Check logs for errors
tail -f /tmp/arlo-service.log
```

## Deployment Steps

```bash
# 1. Backend (Flask)
cd /opt/arlo-cam-api

# Create new file: helpers/stream_manager.py
# Modify file: api/api.py (add endpoints)

# Restart Flask service
sudo systemctl restart arlo

# Verify Flask is running
curl http://localhost:5000/

# 2. Frontend (Express)
cd /home/randy/arlo-viewer

# Modify: server.js (add proxy endpoints)
# Modify: public/status.html (add button)
# Create: public/stream.html (streaming page)

# Restart Express (if running as service)
sudo systemctl restart arlo-viewer
# OR if running manually:
pkill -f "node server.js"
node server.js &

# Verify Express is running
curl http://localhost:3003/

# 3. Test
# Open browser to https://security.thefarmers.org/status.html
# Click "Start Live Stream" on an online camera
# Verify new window opens with streaming page
```

## Success Criteria

✅ "Start Live Stream" button appears on each camera card in status.html

✅ Clicking button opens new window/tab with stream.html

✅ Stream initializes and wakes camera within 10 seconds

✅ Video player shows live camera feed with audio

✅ Countdown timer shows remaining time (60s → 0s)

✅ Stream stops automatically after 60 seconds and window closes

✅ Manual stop button works immediately and closes window

✅ Temp files cleaned up after stream ends

✅ Multiple cameras can stream simultaneously (multiple windows)

✅ Status page can continue refreshing without affecting active streams

✅ Works in Chrome, Firefox, Safari browsers

✅ Battery drain is acceptable (<10% per stream session)

## Future Enhancements (Not in Scope)

- Extended streaming beyond 60 seconds
- Quality selection (SD/HD/4K toggle)
- Recording from live stream
- Two-way audio (push-to-talk)
- Snapshot capture during stream
- Stream history log
- Multi-camera grid view
- Mobile responsive optimization

## Notes

- **Separate window design**: Stream opens in new window to avoid interruption from status page auto-refresh (every 30s)
- HLS latency is 5-10 seconds, normal for this technology
- First stream may take 10-15 seconds to initialize (camera wake-up)
- Battery cameras are slower to start RTSP than powered cameras
- Temp files stored in `/tmp` (80GB available, no space concerns)
- ffmpeg copies video codec (no re-encoding), only transcodes audio to AAC
- Stream button disabled when camera offline
- Window closes automatically when stream ends (both timeout and manual stop)
- Multiple streams supported via separate windows (one per camera)
- Console logging added for debugging (can remove after testing)
