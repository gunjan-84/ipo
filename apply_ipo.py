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

def apply_for_ipo(symbol, isin, lots, lot_size, price, upi_id, cutoff=True):
    """
    Applies for an IPO natively using the reverse-engineered checksum.
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    load_dotenv(env_path, override=True)
    
    bearer_token = os.getenv("GROWW_BEARER_TOKEN")
    device_id = os.getenv("GROWW_DEVICE_ID")
    user_nkey = os.getenv("GROWW_NKEY")
    pin_token = os.getenv("GROWW_PIN_TOKEN")

    if not bearer_token or not device_id or not user_nkey or not pin_token:
        print("[-] Error: Missing tokens in .env. Run create_session.py and unlock_pin.py first.")
        return

    # Correct Groww IPO apply endpoint
    url_path = "/v1/api/stocks_ipo/v1/order"
    
    # The exact payload structure captured from the browser
    quantity = lots * lot_size
    amount = int(quantity * price)
    
    payload = {
        "bidRequests": [
            {
                "amount": amount,
                "bidReferenceNumber": "",
                "isAtCutoffPrice": cutoff,
                "price": price,
                "quantity": quantity
            }
        ],
        "isin": isin,
        "symbol": symbol,
        "upi": upi_id,
        "category": "IND"
    }
    
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
        "x-user-campaign": f"Bearer {pin_token}"
    }

    # API requires strictly minified JSON
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    print(f"[*] Submitting IPO Application natively for {symbol}...")
    response = requests.post(f"https://groww.in{url_path}", headers=headers, data=payload_str)

    if response.status_code in (200, 201):
        data = response.json()
        print("\n[+] SUCCESS! IPO Application Submitted.")
        print(json.dumps(data, indent=2))
    elif response.status_code == 403:
        print("\n[-] FAILED. Status: 403 PIN Locked")
        print("Your PIN token has expired or is invalid. Run unlock_pin.py to renew it.")
    else:
        print(f"\n[-] Status: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Native Groww IPO Apply Script")
    parser.add_argument("--symbol", required=True, help="IPO Symbol (e.g., SKYWAYS)")
    parser.add_argument("--isin", required=True, help="ISIN (e.g., INE0PX301025)")
    parser.add_argument("--lots", type=int, required=True, help="Number of lots to bid for")
    parser.add_argument("--lot-size", type=int, required=True, help="Number of shares in one lot")
    parser.add_argument("--price", type=float, required=True, help="Bid price per share")
    parser.add_argument("--upi", required=True, help="UPI ID for the mandate")
    parser.add_argument("--no-cutoff", action="store_true", help="Set this flag if you are NOT bidding at the cut-off price")
    
    args = parser.parse_args()
    
    apply_for_ipo(
        symbol=args.symbol,
        isin=args.isin,
        lots=args.lots,
        lot_size=args.lot_size,
        price=args.price,
        upi_id=args.upi,
        cutoff=not args.no_cutoff
    )
