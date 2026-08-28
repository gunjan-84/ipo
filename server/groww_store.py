import json
import os

import crypto_store

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "groww_accounts.json")

# Fields captured once via the browser login (see groww_login.py) plus the user's PIN —
# encrypted at rest just like Kite account credentials. state_data is the browser's
# cookies/storage from that login, used to silently refresh the bearer token without
# a fresh OTP. pin_token is the short-lived unlock we refresh automatically, so it's
# kept in plaintext (it's not a secret on its own — useless without the fields above).
_SECRET_FIELDS = ("bearer_token", "device_id", "nkey", "pin", "state_data")


def _encrypt_field(account: dict, field: str) -> str:
    value = account.get(field)
    text = json.dumps(value) if field == "state_data" else (value or "")
    return crypto_store.encrypt(text)


def _decrypt_field(account: dict, field: str):
    text = crypto_store.decrypt(account[field]) if field in account else ""
    if field == "state_data":
        return json.loads(text) if text else None
    return text


def load():
    if not os.path.exists(_FILE):
        return []
    with open(_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [{**a, **{f: _decrypt_field(a, f) for f in _SECRET_FIELDS if f in a}} for a in raw]


def save(accounts):
    os.makedirs(_DATA_DIR, exist_ok=True)
    raw = [{**a, **{f: _encrypt_field(a, f) for f in _SECRET_FIELDS}} for a in accounts]
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
