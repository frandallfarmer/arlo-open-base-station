"""Per-model camera profiles.

The base-station protocol (TCP 4000 registration/status/alert + RTSP on the
camera) is the same across the Arlo Pro family, but the initial registerSet,
RTSP port and codec differ per generation. Everything model-specific lives here
so adding a camera is a table entry, and config.yaml can tweak it without code:

    ModelOverrides:
      VMC4041P:
        register_set_values: {VideoTargetBitrate: 1500}
        rtsp_port: 554
        video_codec: h264
        audio: true
"""
import copy

import arlo.messages as m

# Keyed by model-number prefix (cameras report e.g. "VMC4041P" / "VMC4041PB").
# rtsp_ready_delay: seconds between the camera's RTSP port opening and the stream
# actually being served. A Pro 4 accepts the TCP connection immediately but drops
# the first request (EOF) until ~2-3 s later (verified on VMC4041PB fw 34.0.17).
# rtsp_transport: how to pull RTP from the camera. Over UDP a Pro 4 ends the
# stream after exactly 20 s ("rtcp timeout" in its log, then a Wi-Fi re-auth)
# no matter how often or what RTCP receiver reports are sent - or if none are.
# Over RTSP-interleaved TCP it streams indefinitely (verified on VMC4041PB fw
# 34.0.17: 75 s at 1080p15). Pro / Pro 2 are known to work over UDP.
PROFILES = {
    "VMC4030": {"name": "Arlo Pro", "register_set": m.REGISTER_SET_INITIAL,
                "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": True, "rtsp_ready_delay": 0, "rtsp_transport": "udp"},
    "VMC4130": {"name": "Arlo Pro 2", "register_set": m.REGISTER_SET_INITIAL,
                "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": True, "rtsp_ready_delay": 0, "rtsp_transport": "udp"},
    # Pro 3 / Pro 4 / Pro 5S are the same platform as the Ultra (2K, HDR,
    # spotlight). Default to the H.264 1080p stream on 554 - the HEVC/2K stream
    # is not requested by REGISTER_SET_INITIAL_PRO4.
    "VMC4040": {"name": "Arlo Pro 3", "register_set": m.REGISTER_SET_INITIAL_PRO4,
                "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": False, "rtsp_ready_delay": 3, "rtsp_transport": "tcp",
                "rtsp_port_2k": 555, "video_codec_2k": "h265"},
    "VMC4041": {"name": "Arlo Pro 4", "register_set": m.REGISTER_SET_INITIAL_PRO4,
                "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": True, "rtsp_ready_delay": 3, "rtsp_transport": "tcp",
                "rtsp_port_2k": 555, "video_codec_2k": "h265"},
    "VMC4050": {"name": "Arlo Pro 5S", "register_set": m.REGISTER_SET_INITIAL_PRO4,
                "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": False, "rtsp_ready_delay": 3, "rtsp_transport": "tcp",
                "rtsp_port_2k": 555, "video_codec_2k": "h265"},
    "VMC5040": {"name": "Arlo Ultra", "register_set": m.REGISTER_SET_INITIAL_ULTRA,
                "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": False, "rtsp_ready_delay": 3, "rtsp_transport": "tcp",
                "rtsp_port_2k": 555, "video_codec_2k": "h265"},
}

DEFAULT = {"name": "Arlo (unknown model)", "register_set": m.REGISTER_SET_INITIAL,
           "rtsp_port": 554, "video_codec": "h264", "audio": True, "verified": False, "rtsp_ready_delay": 3, "rtsp_transport": "udp"}


def _base_profile(model):
    if model:
        for prefix, profile in PROFILES.items():
            if model.upper().startswith(prefix):
                return profile
    return DEFAULT


def get_profile(model, overrides=None):
    """Return a private (deep-copied) profile for `model`, with config overrides applied."""
    profile = copy.deepcopy(_base_profile(model))
    override = (overrides or {}).get(model) if model else None
    if override:
        values = override.get("register_set_values") or {}
        profile["register_set"]["SetValues"].update(values)
        for key in ("name", "rtsp_port", "video_codec", "audio", "rtsp_ready_delay", "rtsp_transport",
                    "rtsp_port_2k", "video_codec_2k"):
            if key in override:
                profile[key] = override[key]
    return profile
