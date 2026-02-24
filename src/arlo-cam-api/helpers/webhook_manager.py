import hmac
import hashlib
import time
import requests
from helpers.safe_print import s_print
from webhooks import webhook
from webhooks.senders import targeted


def thumbnail_token(filename, secret):
    return hmac.new(secret.encode(), filename.encode(), hashlib.sha256).hexdigest()

class WebHookManager:

    def __init__(self,config):
        self.config = config

    def motion_detected(self, ip,friendly_name,hostname,serial_number,zone,file_name):
        # Send standard webhook
        r = self.motion(ip,friendly_name,hostname, serial_number,zone,file_name,time.time(), url=self.config['MotionRecordingWebHookUrl'],encoding="application/json", timeout=5)
        # s_print(str(r))  # Disabled - too verbose

        # Send ntfy alert if enabled
        if self.config.get('NtfyEnabled', False):
            self.send_ntfy_alert(friendly_name, hostname, serial_number, zone, file_name)

    def send_ntfy_alert(self, friendly_name, hostname, serial_number, zone, file_name):
        """Send push notification via ntfy.sh"""
        try:
            ntfy_url = self.config.get('NtfyUrl', 'https://ntfy.sh')
            ntfy_topic = self.config.get('NtfyTopic', 'arlo-alerts')

            # Construct message
            camera_name = friendly_name or hostname or serial_number
            zone_text = f" (Zone: {zone})" if zone else ""
            message = f"Motion detected: {camera_name}{zone_text}"

            # Prepare headers
            headers = {
                "Title": "Arlo Motion Alert",
                "Priority": self.config.get('NtfyPriority', 'high'),
                "Tags": "rotating_light,camera,motion"
            }

            # Add thumbnail if configured
            if self.config.get('NtfyIncludeThumbnail', False):
                # Convert to .jpg filename for the thumbnail URL
                thumbnail_base_url = self.config.get('NtfyThumbnailBaseUrl', '')
                if thumbnail_base_url:
                    # Extract filename and convert .mkv to .jpg
                    video_filename = file_name.split('/')[-1]
                    thumbnail_filename = video_filename.replace('.mkv', '.jpg')
                    # Append HMAC token so viewer can authenticate the request
                    secret = self.config.get('ThumbnailSecret', '')
                    if secret:
                        token = thumbnail_token(thumbnail_filename, secret)
                        headers["Attach"] = f"{thumbnail_base_url}/{thumbnail_filename}?token={token}"
                    else:
                        headers["Attach"] = f"{thumbnail_base_url}/{thumbnail_filename}"

            # Add click action to video viewer
            base_url = self.config.get('NtfyClickUrl', 'https://security.example.com')
            headers["Click"] = base_url
            # Add action button with custom text
            headers["Actions"] = f"view, See video, {base_url}, clear=true"

            # Send notification
            response = requests.post(
                f"{ntfy_url}/{ntfy_topic}",
                data=message.encode('utf-8'),
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                s_print(f"[NTFY] Alert sent for {camera_name}")
            else:
                s_print(f"[NTFY] Failed to send alert: {response.status_code}")

        except Exception as e:
            s_print(f"[NTFY] Error sending alert: {e}")

    def send_battery_warning(self, friendly_name, hostname, serial_number, battery_percent, is_critical=False):
        """Send battery low/critical warning via ntfy"""
        try:
            if not self.config.get('BatteryWarningEnabled', False):
                return

            if not self.config.get('NtfyEnabled', False):
                return

            ntfy_url = self.config.get('NtfyUrl', 'https://ntfy.sh')
            ntfy_topic = self.config.get('NtfyTopic', 'arlo-alerts')

            # Construct message
            camera_name = friendly_name or hostname or serial_number
            level = "CRITICAL" if is_critical else "LOW"
            message = f"Battery {level}: {camera_name} at {battery_percent}%"

            # Prepare headers
            priority = "urgent" if is_critical else "high"
            tags = "warning,battery" if not is_critical else "warning,battery,rotating_light"

            headers = {
                "Title": f"Arlo Battery {level}",
                "Priority": priority,
                "Tags": tags
            }

            # Add click action to camera status page
            base_url = self.config.get('NtfyClickUrl', 'https://security.example.com')
            headers["Click"] = base_url

            # Send notification
            response = requests.post(
                f"{ntfy_url}/{ntfy_topic}",
                data=message.encode('utf-8'),
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                s_print(f"[BATTERY] Warning sent for {camera_name}: {battery_percent}% ({level})")
            else:
                s_print(f"[BATTERY] Failed to send warning: {response.status_code}")

        except Exception as e:
            s_print(f"[BATTERY] Error sending warning: {e}")

    @webhook(sender_callable=targeted.sender)
    def motion(self, ip, friendly_name,hostname,serial_number,zone,file_name,_time, url, encoding, timeout):
        return {"ip":ip,"friendly_name":friendly_name,"hostname":hostname,"serial_number":serial_number,"zone":zone,"file_name":file_name,"time":_time}
