import json
import os
import re
from difflib import SequenceMatcher

import httpx

# The scraped list lives in the bind-mounted data dir so a fresh refresh() survives image
# rebuilds — kfintech_ipos_seed.json is just a checked-in starting point for a brand new
# deployment that hasn't refreshed yet.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_FILE = os.path.join(_DATA_DIR, "kfintech_ipos.json")
_SEED_FILE = os.path.join(os.path.dirname(__file__), "kfintech_ipos_seed.json")
_STATUS_PAGE = "https://ipostatus.kfintech.com/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_NOISE_WORDS = {"LIMITED", "LTD", "IPO", "SME", "INVIT", "REIT", "TRUST", "NCD", "NCDS"}

_entries = []  # [{name, value}] — value is KFintech's client_id for the "Select IPO" dropdown


def load():
    global _entries
    path = _FILE if os.path.exists(_FILE) else _SEED_FILE
    if not os.path.exists(path):
        _entries = []
        return _entries
    with open(path, "r", encoding="utf-8") as f:
        _entries = json.load(f)
    return _entries


def all_entries():
    return sorted(_entries, key=lambda e: e["name"])


def save(entries):
    global _entries
    _entries = entries
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


# KFintech doesn't expose the "Select IPO" dropdown through any API call — their React app
# ships the whole list as a JSON blob baked directly into its JS bundle at build time, so we
# scrape the bundle itself rather than the page: fetch the page to find today's bundle
# filename (it's content-hashed and changes on every KFintech deploy), then pull the
# `JSON.parse('[{"clientId":...,"name":...}, ...]')` literal out of that file's source.
async def refresh() -> int:
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
        page_res = await client.get(_STATUS_PAGE)
        page_res.raise_for_status()
        script_match = re.search(r'src="\.?(/static/js/main\.[a-f0-9]+\.js)"', page_res.text)
        if not script_match:
            raise RuntimeError("Could not find KFintech's JS bundle in the status page")

        js_res = await client.get(_STATUS_PAGE.rstrip("/") + script_match.group(1))
        js_res.raise_for_status()

    blob_match = re.search(r"JSON\.parse\('(\[.*?clientId.*?\])'\)", js_res.text, re.DOTALL)
    if not blob_match:
        raise RuntimeError("Could not find the IPO list blob in KFintech's JS bundle")

    # The JS source has the JSON string's quotes backslash-escaped (it's a single-quoted JS
    # string literal) — unicode_escape undoes that the same way JS's own parser would.
    raw_entries = json.loads(blob_match.group(1).encode().decode("unicode_escape"))
    entries = [{"name": e["name"], "value": e["clientId"]} for e in raw_entries]
    save(entries)
    return len(entries)


def _normalize(name: str) -> str:
    n = name.upper()
    n = re.sub(r"\([^)]*\)", " ", n)  # drop parenthetical notes, e.g. "(INDIA)"
    n = re.sub(r"[^A-Z0-9 ]", " ", n)  # drop punctuation/hyphens
    tokens = [t for t in n.split() if t not in _NOISE_WORDS and not t.isdigit()]
    return " ".join(tokens)


def find_match(name: str, threshold: float = 0.55):
    """Fuzzy-match a Kite/display IPO name against the KFintech dropdown list.

    Returns (entry, score) where entry is {"name", "value"}, or (None, best_score) if nothing clears the threshold.
    """
    target = _normalize(name)
    best = None
    best_score = 0.0
    for entry in _entries:
        score = SequenceMatcher(None, target, _normalize(entry["name"])).ratio()
        if score > best_score:
            best_score = score
            best = entry
    if best and best_score >= threshold:
        return best, best_score
    return None, best_score
