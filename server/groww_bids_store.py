import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "groww_bids.json")

# Groww's order-list API never echoes back the quantity/price a bid was placed at —
# only a status summary. We already know both at the moment of applying (we're the
# ones sending them), so we record them here and match them back to orders by
# account + symbol + closest timestamp when displaying the applications table.


def load() -> list:
    if not os.path.exists(_FILE):
        return []
    with open(_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(bids: list):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(bids, f, indent=2)
