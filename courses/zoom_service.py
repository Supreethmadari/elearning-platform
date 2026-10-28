import os
import base64
import requests
import time
import uuid
import re
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def get_zoom_config():
    account_id = os.getenv("ZOOM_ACCOUNT_ID") or getattr(settings, "ZOOM_ACCOUNT_ID", None)
    client_id = os.getenv("ZOOM_CLIENT_ID") or getattr(settings, "ZOOM_CLIENT_ID", None)
    client_secret = os.getenv("ZOOM_CLIENT_SECRET") or getattr(settings, "ZOOM_CLIENT_SECRET", None)
    return account_id, client_id, client_secret


def get_access_token():
    account_id, client_id, client_secret = get_zoom_config()
    if not (account_id and client_id and client_secret):
        logger.info("Zoom credentials not configured in environment or settings.")
        return None

    url = "https://zoom.us/oauth/token"
    data = {
        "grant_type": "account_credentials",
        "account_id": account_id
    }

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        r = requests.post(url, data=data, headers=headers, timeout=10)
        resp_json = r.json()
        if r.status_code == 200 and "access_token" in resp_json:
            return resp_json["access_token"]
        logger.warning(f"Zoom OAuth response: {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"Failed to obtain Zoom access token: {e}")

    return None


def create_meeting(topic, duration_minutes, meeting_link=None, course_id=None):
    """
    Creates a live meeting:
    1. If a custom meeting link (Zoom, Google Meet, Teams, etc.) is provided by trainer, use it.
    2. If Zoom credentials are configured in environment, use Zoom Server-to-Server OAuth.
    3. Fallback: Automatically generate an instant, functional web meeting room (Jitsi Meet).
    """
    # 1. Custom meeting link provided by trainer
    if meeting_link and meeting_link.strip():
        link = meeting_link.strip()
        if not (link.startswith("http://") or link.startswith("https://")):
            link = f"https://{link}"
        return {
            "id": str(int(time.time())),
            "join_url": link,
            "start_url": link
        }

    # 2. Try Zoom API if credentials exist
    token = get_access_token()
    if token:
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "topic": topic,
                "type": 2,
                "duration": duration_minutes,
                "settings": {
                    "join_before_host": False,
                    "waiting_room": False
                }
            }
            r = requests.post("https://api.zoom.us/v2/users/me/meetings", json=payload, headers=headers, timeout=10)
            if r.status_code in (200, 201):
                data = r.json()
                if "join_url" in data and "start_url" in data:
                    return {
                        "id": str(data.get("id")),
                        "join_url": data["join_url"],
                        "start_url": data["start_url"]
                    }
            logger.warning(f"Zoom meeting creation failed: {r.status_code} - {r.text}")
        except Exception as e:
            logger.error(f"Error calling Zoom meeting API: {e}")

    # 3. Fallback: Instant secure live video room (Free, zero-config, browser-based)
    clean_topic = re.sub(r'[^a-zA-Z0-9]', '', str(topic))[:20] or "LiveClass"
    room_name = f"Cyanopy-{course_id or 'Course'}-{clean_topic}-{uuid.uuid4().hex[:6]}"
    room_url = f"https://meet.jit.si/{room_name}"

    return {
        "id": str(int(time.time())),
        "join_url": room_url,
        "start_url": room_url
    }
