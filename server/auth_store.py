import hashlib
import json
import os
import secrets

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "auth.json")

_ITERATIONS = 200_000


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONS).hex()


def load():
    if not os.path.exists(_FILE):
        return None
    with open(_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(username: str, password: str):
    salt_hex = secrets.token_hex(16)
    record = {"username": username, "salt": salt_hex, "password_hash": _hash(password, salt_hex)}
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return record


def verify(record: dict, username: str, password: str) -> bool:
    if not record or username != record["username"]:
        return False
    return secrets.compare_digest(_hash(password, record["salt"]), record["password_hash"])
