import json
import os
import time

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "ipo_instruments_cache.json")

# Kite's IPO instrument list barely changes within a day — caching it means the "Public
# issues" list is viewable without any account connected/logged in, and every page load
# doesn't need to hit Kite at all once today's snapshot has been fetched.
TTL_SECONDS = 24 * 60 * 60


def load() -> dict | None:
    if not os.path.exists(_FILE):
        return None
    with open(_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(body):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump({"body": body, "fetched_at": time.time()}, f)


def is_fresh(cached: dict) -> bool:
    return bool(cached) and time.time() - cached["fetched_at"] < TTL_SECONDS
