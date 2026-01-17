import vlc
import time
addr = '172.14.0.102'  # Replace with your camera's IP
url = f"rtsp://{addr}/live"

# The cameras appear to restart WiFi if they don't receive an RTCP Receiver Report regularly.
# FFMpeg and anything that depends on this don't appear to send these enough?

#Basic Recording
# cvlc  rtsp://CAMERA_IP/live --sout file/ts:stream.mpg
# 
instance = vlc.Instance()
media = instance.media_new(url)
media.add_option("sout=file/ts:stream.mpg")
player = instance.media_player_new()
player.set_media(media)
player.play()

while 1:
    continue
