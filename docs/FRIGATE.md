# Frigate (or any 24/7 NVR) without draining the battery

Frigate keeps its RTSP input open all the time. Pointed at the on-demand path
`arlo_<serial>` that keeps the camera streaming non-stop and empties the battery
in days. Use the always-on feed instead.

| Path | What it is | Wakes the camera? |
|---|---|---|
| `rtsp://<base>:8554/arlo_<serial>` | on-demand live relay | **yes** - while anyone reads it |
| `rtsp://<base>:8554/arlo_<serial>_feed` | always-on H.264 1080p15, no audio | **never** |

The feed (`helpers/always_on_feed.py`, `systemd/arlo-feed@.service`) shows live
video whenever the camera is awake for any other reason and otherwise repeats the
last live frame with an "asleep - last live HH:MM:SS" caption.

The camera wakes when:
- **motion** - PIR alert -> motion recording opens `arlo_<serial>` (RecordOnMotionAlert),
- **someone watches live** - VLC / Home Assistant / Frigate's "Live" stream on `arlo_<serial>`,
- **on request** - `POST /camera/<serial>/live/wake {"seconds": 120}` (`{"seconds": 0}` = sleep now).

## Setup on the base station
```bash
sudo install -o arlo -g arlo -m 755 src/arlo-cam-api/helpers/always_on_feed.py /opt/arlo-cam-api/helpers/
sudo cp systemd/arlo-feed@.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now arlo-feed@<CAMERA_SERIAL>
```
MediaMTX needs the local API and the `_feed` path - both are in `config/mediamtx.yml.example`.
CPU (2 vCPU VM): ~25 % of one core while asleep (re-encoding the still frame),
one 1080p15 decode + x264 encode while live.

## Frigate config
```yaml
go2rtc:
  streams:
    arlo_front:            # detect + record: never wakes the camera
      - rtsp://<base>:8554/arlo_<serial>_feed
    arlo_front_live:       # opening this in Frigate's live view wakes it
      - rtsp://<base>:8554/arlo_<serial>
cameras:
  arlo_front:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/arlo_front
          input_args: preset-rtsp-restream
          roles: [detect, record]
    live:
      streams:
        Live (wakes camera): arlo_front_live
        Feed (no wake): arlo_front
```
Do not set the camera's dashboard tile to "stream continuously" with the Live
stream - that keeps the camera awake.

## Home Assistant
`rest_command.arlo_wake` (see HOME-ASSISTANT.md pattern):
```yaml
rest_command:
  arlo_wake:
    url: "http://<base>:5000/camera/{{ serial }}/live/wake"
    method: post
    content_type: application/json
    payload: '{"seconds": {{ seconds | default(120) | int }}}'
    headers:
      Authorization: !secret arlo_api_auth
```


## Instant-start live view (`arlo_<serial>_view`)

Frigate's live player gives up after a few seconds without video, which is less
than a sleeping camera needs to wake. So `always_on_feed.py` publishes the same
picture twice, as `arlo_<serial>_feed` and `arlo_<serial>_view`. Both are always
up, so players start in under a second.

MediaMTX runs `helpers/view_publisher.py` (`runOnRead`) for every reader of the
`_view` path. While that reader stays connected, the script reads
`arlo_<serial>`, which wakes the camera. The feed then switches from the last
frame to live video. The caption reads "Waking camera...", then "LIVE". When the
viewer closes, the script exits, and the camera sleeps 15 s later.

    go2rtc:
      streams:
        arlo_front:      [rtsp://BASE:8554/arlo_<serial>_feed]   # detect/record, never wakes
        arlo_front_live: [rtsp://BASE:8554/arlo_<serial>_view]   # live view, wakes on open

## Recording in Frigate only (MotionAction: "wake")

With `MotionAction: "wake"` and `RecordOnMotionAlert: false` in config.yaml, the
base station records nothing itself. When the camera's PIR fires, the base station:

1. sends the HA motion webhook / ntfy as before;
2. calls `/live/wake` for `MotionWakeSeconds`; further motion renews the timer.

The feed goes live, Frigate sees the motion and objects, and records them as
alerts or detections.
