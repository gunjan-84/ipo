import asyncio
import json
import random
import string
import uuid

import requests

from groww_checksum import generate_checksum

BASE = "https://groww.in"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def _common_headers(bearer_token: str, device_id: str, nkey: str, req_id: str, checksum: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {bearer_token}",
        "content-type": "application/json",
        "origin": BASE,
        "referer": f"{BASE}/",
        "user-agent": _UA,
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
        "x-user-nkey": nkey,
    }


def _req_id_and_salt():
    return str(uuid.uuid4()), "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


# Groww's backend blocks httpx's request fingerprint outright (500 "Something Went Wrong")
# even with byte-identical headers/body — but accepts the same request from `requests`.
# So this module deliberately uses `requests`, run off the event loop via to_thread.


def _unlock_pin_sync(bearer_token: str, device_id: str, nkey: str, pin: str) -> str:
    url_path = "/v1/api/user/v2/auth/pin/validate"
    payload = {"passCode": pin}
    req_id, salt = _req_id_and_salt()
    checksum = generate_checksum(url_path, payload, req_id, salt)
    headers = _common_headers(bearer_token, device_id, nkey, req_id, checksum)
    payload_str = json.dumps(payload, separators=(",", ":"))

    res = requests.post(f"{BASE}{url_path}", headers=headers, data=payload_str, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"PIN unlock failed ({res.status_code}): {res.text[:200]}")

    pin_token = (res.json().get("data") or {}).get("userCampaignHeader")
    if not pin_token:
        raise RuntimeError("PIN unlock succeeded but no token was returned")
    return pin_token


def _fetch_orders_once_sync(bearer_token: str, device_id: str, nkey: str, pin_token: str):
    url_path = "/v1/api/primaries/v1/ipo/order/active"
    req_id, salt = _req_id_and_salt()
    checksum = generate_checksum(url_path, None, req_id, salt)
    headers = _common_headers(bearer_token, device_id, nkey, req_id, checksum)
    headers["x-user-campaign"] = f"Bearer {pin_token}"

    return requests.get(f"{BASE}{url_path}", headers=headers, timeout=15)


# --- PIN unlock: only needs the credentials captured once via the manual browser login,
# never a browser again. This is what lets the app silently renew access on its own. ---
async def unlock_pin(bearer_token: str, device_id: str, nkey: str, pin: str) -> str:
    return await asyncio.to_thread(_unlock_pin_sync, bearer_token, device_id, nkey, pin)


# --- Orchestrated sequence: fetch with the stored pin_token; if Groww says it's expired
# (non-200) unlock a fresh one from the stored PIN and retry once. Returns
# (orders, refreshed_pin_token_or_None) so the caller can persist a renewed token. ---
async def fetch_orders_with_auto_unlock(account: dict):
    pin_token = account.get("pin_token")
    refreshed_pin_token = None

    if pin_token:
        res = await asyncio.to_thread(
            _fetch_orders_once_sync, account["bearer_token"], account["device_id"], account["nkey"], pin_token
        )
        if res.status_code == 200:
            return res.json().get("orders", []), None

    pin_token = await unlock_pin(account["bearer_token"], account["device_id"], account["nkey"], account["pin"])
    refreshed_pin_token = pin_token

    res = await asyncio.to_thread(
        _fetch_orders_once_sync, account["bearer_token"], account["device_id"], account["nkey"], pin_token
    )
    if res.status_code != 200:
        raise RuntimeError(f"Fetching Groww orders failed ({res.status_code}): {res.text[:200]}")

    return res.json().get("orders", []), refreshed_pin_token
