import os
import requests
import uuid
import random
import string
import json
import sys
from dotenv import load_dotenv
from checksum import generate_groww_checksum

# Force stdout encoding for compatibility
sys.stdout.reconfigure(encoding='utf-8')

def fetch_active_ipos(bearer_token=None, device_id=None, user_nkey=None, pin_token=None):
    """
    Fetches the list of active IPOs purely natively using the reverse-engineered checksum.
    Can be called directly with arguments by a backend server, or run standalone via CLI.
    Returns a dictionary with the response data.
    """
    if not all([bearer_token, device_id, user_nkey, pin_token]):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        load_dotenv(env_path, override=True)
        bearer_token = bearer_token or os.getenv("GROWW_BEARER_TOKEN")
        device_id = device_id or os.getenv("GROWW_DEVICE_ID")
        user_nkey = user_nkey or os.getenv("GROWW_NKEY")
        pin_token = pin_token or os.getenv("GROWW_PIN_TOKEN")

    if not bearer_token or not device_id or not user_nkey or not pin_token:
        print("[-] Error: Missing tokens in .env. Run create_session.py and unlock_pin.py first.")
        return {"success": False, "error": "Missing required credentials"}

    # GET requests have no payload, which translates to 'undefined' in JavaScript
    url_path = "/v1/api/primaries/v1/ipo/order/active"
    payload = None
    
    req_id = str(uuid.uuid4())
    salt = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    # Generate the cryptographic checksum
    checksum = generate_groww_checksum(url_path, payload, req_id, salt)

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.5",
        "authorization": f"Bearer {bearer_token}",
        "content-type": "application/json",
        "origin": "https://groww.in",
        "referer": "https://groww.in/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "x-app-id": "growwWeb",
        "x-device-id": device_id,
        "x-device-id-v2": device_id,
        "x-device-type": "desktop",
        "x-platform": "web",
        "x-primary-target": "td=1,au=1,ld=4",
        "x-secondary-target": "td=2,au=2,ld=3",
        "x-target-version": "0",
        "x-request-id": req_id,
        "x-request-checksum": checksum,
        "x-user-nkey": user_nkey,
        "x-user-campaign": f"Bearer {pin_token}"  # Must prepend Bearer!
    }

    print(f"[*] Fetching active IPOs natively via {url_path}...")
    response = requests.get(f"https://groww.in{url_path}", headers=headers)

    if response.status_code == 200:
        data = response.json()
        print("\n[+] SUCCESS! Status: 200 OK")
        print("\nActive IPO Data:")
        print(json.dumps(data, indent=2))
        return {"success": True, "data": data}
    elif response.status_code == 403:
        print("\n[-] FAILED. Status: 403 PIN Locked")
        print("Your PIN token has expired or is invalid. Run unlock_pin.py to renew it.")
        return {"success": False, "error": "403 PIN Locked", "status_code": 403}
    else:
        print(f"\n[-] FAILED. Status: {response.status_code}")
        print(response.text)
        return {"success": False, "error": response.text, "status_code": response.status_code}

if __name__ == "__main__":
    fetch_active_ipos()
