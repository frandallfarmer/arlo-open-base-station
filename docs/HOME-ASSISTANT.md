# Home Assistant integration

All endpoints are on the base station's LAN address. Calls from anything other
than localhost need `Authorization: Bearer <ApiToken>` (from `/opt/arlo-cam-api/config.yaml`).

| What | How |
|------|-----|
| Live video | `rtsp://BASE:8554/arlo_<SERIAL>` - MediaMTX wakes the camera on the first viewer and lets it sleep 15 s after the last one leaves. Use the Generic Camera integration (or go2rtc / Frigate). Every view costs battery. |
| Still image | `GET /camera/<SERIAL>/snapshot.jpg` - newest motion thumbnail or uploaded snapshot; never wakes the camera, safe to poll. GET requests also accept `?token=<ApiToken>` (Generic Camera cannot send headers). |
| Fresh still | `POST /camera/<SERIAL>/snapshot/refresh` - wakes the camera to upload a JPEG. |
| Status | `GET /cameras/status` - battery, signal, temperature, model, firmware, armed, online, live_active. |
| Arm / disarm | `POST /camera/<SERIAL>/arm`, `POST /camera/<SERIAL>/disarm` |
| Motion | `MotionRecordingWebHookUrl` in config.yaml -> HA webhook (JSON with serial_number, friendly_name, file_name), or the SSE stream `GET /events` (motion, motion_end, status, registration, snapshot, recording, connectivity, live). |

Example (`configuration.yaml` / packages):

```yaml
rest:
  - resource: http://BASE:5000/cameras/status
    headers: {Authorization: !secret arlo_api_auth}   # "Bearer <token>"
    scan_interval: 300
    sensor:
      - name: Arlo Front battery
        unique_id: arlo_front_battery
        value_template: "{{ (value_json | selectattr('serial_number','eq','SERIAL') | first).battery_percent }}"
        unit_of_measurement: "%"
        device_class: battery

rest_command:
  arlo_arm:
    url: http://BASE:5000/camera/{{ serial }}/arm
    method: post
    headers: {Authorization: !secret arlo_api_auth}
  arlo_disarm:
    url: http://BASE:5000/camera/{{ serial }}/disarm
    method: post
    headers: {Authorization: !secret arlo_api_auth}
```

Motion automation trigger: `platform: webhook`, `webhook_id: arlo_motion`,
`local_only: true`, with `MotionRecordingWebHookUrl: "http://HA:8123/api/webhook/arlo_motion"`.
