import json
import os

import crypto_store

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "groww_accounts.json")

# Fields captured once via the manual browser login (create_session.py-style flow) plus the
# user's PIN — encrypted at rest just like Kite account credentials. pin_token is the
# short-lived unlock we refresh automatically, so it's kept in plaintext (it's not a secret
# on its own — it's useless without the encrypted fields above).
_SECRET_FIELDS = ("bearer_token", "device_id", "nkey", "pin")


def load():
    if not os.path.exists(_FILE):
        return []
    with open(_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [{**a, **{f: crypto_store.decrypt(a[f]) for f in _SECRET_FIELDS}} for a in raw]


def save(accounts):
    os.makedirs(_DATA_DIR, exist_ok=True)
    raw = [{**a, **{f: crypto_store.encrypt(a[f]) for f in _SECRET_FIELDS}} for a in accounts]
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
