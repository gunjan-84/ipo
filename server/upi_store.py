import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "upis.json")


def load():
    if not os.path.exists(_FILE):
        return []
    with open(_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(upis):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(upis, f, indent=2)
