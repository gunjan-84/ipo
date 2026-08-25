import json
import os

import crypto_store

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "accounts.json")


def load():
    if not os.path.exists(_FILE):
        return []
    with open(_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [
        {**a, "password": crypto_store.decrypt(a["password"]), "totp_secret": crypto_store.decrypt(a["totp_secret"])}
        for a in raw
    ]


def save(accounts):
    os.makedirs(_DATA_DIR, exist_ok=True)
    raw = [
        {**a, "password": crypto_store.encrypt(a["password"]), "totp_secret": crypto_store.encrypt(a["totp_secret"])}
        for a in accounts
    ]
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
