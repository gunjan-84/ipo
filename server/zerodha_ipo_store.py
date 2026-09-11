import asyncio
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

BASE = "https://zerodha.com"
LIST_URL = f"{BASE}/ipo/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1
)}
_DATE_RANGE_RE = re.compile(r"(\d{1,2})\w{0,2}\s*[–-]\s*(\d{1,2})\w{0,2}\s+([A-Za-z]{3})[a-z]*\s+(\d{4})")
_LISTING_DATE_RE = re.compile(r"(?:Listing|Listed) on\s*(.+)", re.IGNORECASE)


def _parse_date_range(text: str):
    m = _DATE_RANGE_RE.search(text)
    if not m:
        return None, None
    start_day, end_day, mon, year = m.groups()
    month = _MONTHS.get(mon[:3].title())
    if not month:
        return None, None
    return date(int(year), month, int(start_day)), date(int(year), month, int(end_day))


def _parse_card(card) -> dict | None:
    symbol_el = card.select_one(".ipo-symbol")
    name_el = card.select_one(".ipo-name")
    if not symbol_el or not name_el:
        return None

    type_el = card.select_one(".ipo-type")
    link_el = card.select_one("a[href^='/ipo/']")
    logo_el = card.select_one(".card-left img")
    middle_el = card.select_one(".card-middle")
    middle_text = ""
    if middle_el:
        name_span = middle_el.select_one(".ipo-name")
        if name_span:
            name_span.extract()  # its text (the company name) isn't part of the date/price line
        middle_text = middle_el.get_text(" ", strip=True)
    bottom_el = card.select_one(".card-bottom")
    bottom_text = bottom_el.get_text(" ", strip=True) if bottom_el else ""

    start_date, end_date = _parse_date_range(middle_text)
    # The price band is whatever's left of the card-middle line after its date range —
    # e.g. "09th – 11th Sep 2026 • ₹384 – ₹404" → "₹384 – ₹404" (or just "To be announced").
    price_range = re.sub(r"\s+", " ", _DATE_RANGE_RE.sub("", middle_text).replace("•", "")).strip() or None
    if price_range and price_range.lower() == "to be announced":
        price_range = None  # already conveyed by the (missing) date range — don't repeat it

    listing_match = _LISTING_DATE_RE.search(bottom_text)
    already_listed = "listed on" in bottom_text.lower()

    return {
        "symbol": symbol_el.get_text(strip=True),
        "name": name_el.get_text(strip=True),
        "board": type_el.get_text(strip=True) if type_el else None,
        "logo_url": logo_el["src"] if logo_el and logo_el.get("src") else None,
        "start_date": start_date,
        "end_date": end_date,
        "price_range": price_range,
        "listing_date": listing_match.group(1).strip() if listing_match else None,
        "already_listed": already_listed,
        "zerodha_url": BASE + link_el["href"] if link_el and link_el.get("href") else None,
    }


def _parse_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = next((h for h in soup.find_all(["h2", "h3"]) if h.get_text(strip=True).startswith("About")), None)
    if not heading:
        return None
    p = heading.find_next_sibling("p")
    if not p:
        return None
    text = p.get_text(" ", strip=True)
    return re.sub(r"\s*Read more\.?\s*$", "", text) or None


async def _fetch_description(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        res = await client.get(url)
        res.raise_for_status()
        return _parse_description(res.text)
    except Exception:
        return None


# Zerodha's own IPO page lists Live + Upcoming + "to be announced" + recently-listed issues
# all as one flat set of cards, distinguished only by their dates (or lack thereof) — this
# picks out just the ones that haven't opened for bidding yet, since already-open issues are
# already covered by Kite's own instrument list (see /api/ipo/instruments) and would
# otherwise show up twice. Each entry's own detail page (linked from its card) carries an
# "About <Company>" writeup, fetched here too — same site as the rest of this data, so no
# name-matching against a different source is needed.
async def fetch_upcoming_entries() -> list:
    async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
        res = await client.get(LIST_URL)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        today = date.today()
        entries = []
        for card in soup.select(".card"):
            parsed = _parse_card(card)
            if not parsed or parsed["already_listed"]:
                continue
            if parsed["start_date"] and parsed["start_date"] <= today:
                continue  # already open (or was) — belongs in "Open now", not "Upcoming"
            parsed["start_date"] = parsed["start_date"].isoformat() if parsed["start_date"] else None
            parsed["end_date"] = parsed["end_date"].isoformat() if parsed["end_date"] else None
            entries.append(parsed)

        descriptions = await asyncio.gather(
            *(_fetch_description(client, e["zerodha_url"]) for e in entries if e["zerodha_url"])
        )
    desc_by_url = dict(zip((e["zerodha_url"] for e in entries if e["zerodha_url"]), descriptions))
    for entry in entries:
        entry["description"] = desc_by_url.get(entry["zerodha_url"])

    return entries
