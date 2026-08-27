import os
import requests
import uuid
import random
import string
import json
import sys
import argparse
from dotenv import load_dotenv
from checksum import generate_groww_checksum

# Force stdout encoding for compatibility
sys.stdout.reconfigure(encoding='utf-8')

def cancel_ipo_application(order_id, bearer_token=None, device_id=None, pin_token=None, user_nkey=None):
    """
    Cancels an active IPO application natively using the reverse-engineered checksum.
    Can be called directly with arguments by a backend server, or run standalone via CLI.
    Returns a dictionary with the response data.
    """
    # If any arguments are missing, fallback to .env for CLI execution
    if not all([bearer_token, device_id, pin_token, user_nkey]):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        load_dotenv(env_path, override=True)
        bearer_token = bearer_token or os.getenv("GROWW_BEARER_TOKEN")
        device_id = device_id or os.getenv("GROWW_DEVICE_ID")
        pin_token = pin_token or os.getenv("GROWW_PIN_TOKEN")
        user_nkey = user_nkey or os.getenv("GROWW_NKEY")

    if not bearer_token or not device_id or not pin_token:
        print("[-] Error: Missing tokens. Run create_session.py and unlock_pin.py first.")
        return {"success": False, "error": "Missing required credentials"}

    url_path = f"/v1/api/stocks_ipo/v1/order/{order_id}/cancel"
    payload = ""
    
    req_id = str(uuid.uuid4())
    salt = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    # Generate the cryptographic checksum (payload is None for empty requests)
    checksum = generate_groww_checksum(url_path, payload, req_id, salt)

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.5",
        "authorization": f"Bearer {bearer_token}",
        "content-type": "application/x-www-form-urlencoded",
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
        "x-user-campaign": f"Bearer {pin_token}"
    }
    
    print(f"[*] Submitting Cancellation for IPO Order {order_id}...")
    # Passing data="" forces the 'requests' library to include 'Content-Length: 0'
    response = requests.put(f"https://groww.in{url_path}", headers=headers, data="")

    if response.status_code in (200, 201, 204):
        print("\n[+] SUCCESS! IPO Application Cancelled.")
        # Some endpoints return 204 No Content with empty text
        if response.text:
            try:
                data = response.json()
                print(json.dumps(data, indent=2))
                return {"success": True, "data": data}
            except:
                pass
        return {"success": True, "data": {}}
    elif response.status_code == 403:
        print("\n[-] FAILED. Status: 403 PIN Locked")
        print("Your PIN token has expired or is invalid. Run unlock_pin.py to renew it.")
        return {"success": False, "error": "403 PIN Locked", "status_code": 403}
    else:
        print(f"\n[-] Status: {response.status_code}")
        print(response.text)
        return {"success": False, "error": response.text, "status_code": response.status_code}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Native Groww IPO Cancellation Script")
    parser.add_argument("--order-id", required=True, help="The Groww Order ID to cancel (e.g., GIOnUCe0u7bo8Vnr)")
    
    args = parser.parse_args()
    
    cancel_ipo_application(order_id=args.order_id)
