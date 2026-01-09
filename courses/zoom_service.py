import os, base64, requests, time

ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")


def get_access_token():
    url = "https://zoom.us/oauth/token"
    data = {
        "grant_type": "account_credentials",
        "account_id": os.getenv("ZOOM_ACCOUNT_ID")
    }

    auth = base64.b64encode(
        f"{os.getenv('ZOOM_CLIENT_ID')}:{os.getenv('ZOOM_CLIENT_SECRET')}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    r = requests.post(url, data=data, headers=headers)
    print("TOKEN RESPONSE:", r.text)   # 🔥 ADD
    return r.json()["access_token"]


def create_meeting(topic, duration_minutes):
    token = get_access_token()

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

    r = requests.post("https://api.zoom.us/v2/users/me/meetings", json=payload, headers=headers)
    print("MEETING RESPONSE:", r.text)   # 🔥 ADD

    data = r.json()
    return {
        "id": data["id"],
        "join_url": data["join_url"],
        "start_url": data["start_url"]
    }
