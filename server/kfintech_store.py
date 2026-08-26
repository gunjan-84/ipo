import json
import os
import re
from difflib import SequenceMatcher

_FILE = os.path.join(os.path.dirname(__file__), "kfintech_ipos.json")

_NOISE_WORDS = {"LIMITED", "LTD", "IPO", "SME", "INVIT", "REIT", "TRUST", "NCD", "NCDS"}

_entries = []  # [{name, value}] — value is KFintech's client_id for the "Select IPO" dropdown


def load():
    global _entries
    if not os.path.exists(_FILE):
        _entries = []
        return _entries
    with open(_FILE, "r", encoding="utf-8") as f:
        _entries = json.load(f)
    return _entries


def all_entries():
    return sorted(_entries, key=lambda e: e["name"])


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
