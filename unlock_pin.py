import os
import json
import requests
import uuid
import random
import string
import sys
from dotenv import load_dotenv, set_key
from checksum import generate_groww_checksum

# Force stdout encoding for compatibility
sys.stdout.reconfigure(encoding='utf-8')

def unlock_pin_natively():
    """
    100% Native Python PIN Unlocker.
    Requires a valid GROWW_BEARER_TOKEN and GROWW_NKEY stored in .env (via create_session.py).
    Sends the mathematical handshake and saves the PIN Token back to .env.
    """
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(env_path, override=True)
    
    PIN = os.getenv("PIN")
    bearer_token = os.getenv("GROWW_BEARER_TOKEN")
    device_id = os.getenv("GROWW_DEVICE_ID")
    user_nkey = os.getenv("GROWW_NKEY")

    if not PIN:
        print("[-] Error: PIN not found in .env!")
        return False
        
    if not bearer_token or not device_id or not user_nkey:
        print("[-] Error: Missing Bearer Token, Device ID, or NKey! Please run create_session.py first.")
        return False

    url = "/v1/api/user/v2/auth/pin/validate"
    payload = {"passCode": PIN}
    
    # Generate one-time request parameters
    req_id = str(uuid.uuid4())
    salt = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    # Compute the cryptographic checksum
    checksum = generate_groww_checksum(url, payload, req_id, salt)

    # All of these headers are STRICTLY validated by the Groww backend.
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.5",
        "authorization": f"Bearer {bearer_token}",
        "content-type": "application/json",
        "origin": "https://groww.in",
        "priority": "u=1, i",
        "referer": "https://groww.in/",
        "sec-ch-ua": '"Not=A?Brand";v="99", "Brave";v="151", "Chromium";v="151"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "sec-gpc": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
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
        "x-user-nkey": user_nkey
    }

    # API requires strictly minified JSON
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    print(f"[*] Mathematically unlocking PIN via {url}...")
    response = requests.post(f"https://groww.in{url}", headers=headers, data=payload_str)

    if response.status_code == 200:
        data = response.json()
        print("\n[+] SUCCESS! Status: 200 OK")
        
        user_campaign = data.get("data", {}).get("userCampaignHeader")
        print(f"[+] Unlocked PIN Token: {user_campaign[:50]}...")
        
        set_key(env_path, "GROWW_PIN_TOKEN", user_campaign)
        
        print("\n[+] PIN Token saved to .env as GROWW_PIN_TOKEN!")
        print("[+] Your Python bots can now trade purely natively without Playwright!")
        return True
        
    else:
        print(f"\n[-] FAILED. Status: {response.status_code}")
        print(response.text)
        return False

if __name__ == "__main__":
    unlock_pin_natively()
