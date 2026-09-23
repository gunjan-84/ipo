import asyncio
import re
import time
from difflib import SequenceMatcher

import httpx
from bs4 import BeautifulSoup

URL = "https://www.ipoji.com/"
DETAIL_URL = "https://www.ipoji.com/ipo/{slug}"
UPCOMING_URLS = ("https://www.ipoji.com/ipo/upcoming-ipo", "https://www.ipoji.com/sme-ipo/upcoming-ipo")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_CACHE_TTL = 300  # seconds — ipoji's GMP/subscription figures don't change fast enough to justify fetching on every page load
_DETAIL_CACHE_TTL = 60  # subscription is "live" while bidding is open, so refresh more often
_UPCOMING_CACHE_TTL = 3600  # not-yet-filed IPOs barely change day to day

_LISTING_INFO_CACHE_TTL = 6 * 60 * 60  # a listing price never changes once set — this just
# caches against repeat lookups (and repeat 404s) for the same company

_cache = {"entries": [], "fetched_at": 0}
_detail_cache = {}  # slug -> {"data": {...}, "fetched_at": ts}
_upcoming_cache = {"entries": [], "fetched_at": 0}
_listing_info_cache = {}  # guessed slug -> {"data": dict | None, "fetched_at": ts}

_NOISE_WORDS = {"LIMITED", "LTD", "IPO", "SME", "INDIA"}


def _normalize(name: str) -> str:
    n = name.upper()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    tokens = [t for t in n.split() if t not in _NOISE_WORDS]
    return " ".join(tokens)


def _parse(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for card in soup.select("article.ipo-card"):
        name_el = card.select_one(".ipo-card-name")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        stats = {}
        for stat in card.select(".ipo-card-body-stat"):
            label_el = stat.select_one(".ipo-card-secondary-label")
            value_el = stat.select_one(".ipo-card-body-value")
            if label_el and value_el:
                stats[label_el.get_text(strip=True)] = value_el.get_text(" ", strip=True)

        premium_el = card.select_one(".ipo-card-body-left-block .ipo-card-body-value")
        premium_color = None
        if premium_el and premium_el.has_attr("style"):
            if "green" in premium_el["style"]:
                premium_color = "up"
            elif "red" in premium_el["style"]:
                premium_color = "down"

        # Listed IPOs carry a footer like "Listing Price : ₹137.0 at a Discount of 0.72%"
        # instead of the Exp. Premium stat (which only applies before listing).
        footer_el = card.select_one(".ipo-card-footer-text")
        listing_note = footer_el.get_text(" ", strip=True) if footer_el else None
        listing_direction = None
        if listing_note:
            lowered = listing_note.lower()
            if "premium" in lowered:
                listing_direction = "up"
            elif "discount" in lowered:
                listing_direction = "down"

        badge_el = card.select_one(".ipo-card-market-badge")

        href = card.get("data-agent-href", "")
        entries.append(
            {
                "name": name,
                "slug": href.rsplit("/", 1)[-1] if href else None,
                "status": card.get("data-ipo-status"),
                "market": badge_el.get_text(strip=True) if badge_el else None,
                "offer_price": stats.get("Offer Price"),
                "lot_size": stats.get("Lot Size"),
                "issue_size": stats.get("Issue Size"),
                "subscription": stats.get("Subscription"),
                "exp_premium": stats.get("Exp. Premium"),
                "premium_direction": premium_color,
                "list_price": stats.get("List Price"),
                "listing_date": stats.get("Listing Date"),
                "listing_note": listing_note,
                "listing_direction": listing_direction,
            }
        )
    return entries


async def fetch_entries(force: bool = False) -> list:
    now = time.time()
    if not force and _cache["entries"] and now - _cache["fetched_at"] < _CACHE_TTL:
        return _cache["entries"]

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(URL, headers=_HEADERS)
        res.raise_for_status()

    entries = _parse(res.text)
    _cache["entries"] = entries
    _cache["fetched_at"] = now
    return entries


def _parse_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("#aboutCompany")
    return el.get_text(" ", strip=True) if el else None


async def _fetch_description(client: httpx.AsyncClient, slug: str) -> str | None:
    try:
        res = await client.get(DETAIL_URL.format(slug=slug), headers=_HEADERS)
        res.raise_for_status()
        return _parse_description(res.text)
    except Exception:
        return None


# IPOs that haven't filed a prospectus yet — no dates, price band or lot size, just a
# name and (sometimes) an issue-size estimate. Scraped from ipoji's two dedicated
# "upcoming" listings (mainboard + SME) rather than the homepage, which only teases
# the first handful. The listing cards themselves carry no description (that only shows
# up on the homepage's own teaser and each IPO's own detail page), so we fetch each
# entry's detail page too — fine given this whole list is cached for an hour.
async def fetch_upcoming_entries(force: bool = False) -> list:
    now = time.time()
    if not force and _upcoming_cache["entries"] and now - _upcoming_cache["fetched_at"] < _UPCOMING_CACHE_TTL:
        return _upcoming_cache["entries"]

    entries = []
    async with httpx.AsyncClient(timeout=15) as client:
        for url in UPCOMING_URLS:
            res = await client.get(url, headers=_HEADERS)
            res.raise_for_status()
            entries += _parse(res.text)

        descriptions = await asyncio.gather(*(_fetch_description(client, e["slug"]) for e in entries if e["slug"]))
    desc_by_slug = dict(zip((e["slug"] for e in entries if e["slug"]), descriptions))
    for entry in entries:
        entry["description"] = desc_by_slug.get(entry["slug"])

    _upcoming_cache["entries"] = entries
    _upcoming_cache["fetched_at"] = now
    return entries


def _parse_subscription_detail(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    card = soup.select_one("#subscription")
    if not card:
        return None

    heading_el = card.select_one("h2")
    heading = heading_el.get_text(strip=True) if heading_el else None

    categories = []
    for row in card.select(".status-progress"):
        classes = row.get("class", [])
        if "d-block" in classes and "d-md-none" in classes:
            continue  # mobile-only duplicate of a row already shown in the desktop columns
        spans = row.select(".progress-label span")
        if len(spans) < 2:
            continue
        label = spans[0].get_text(strip=True)
        value = spans[1].get_text(strip=True)
        categories.append({"label": label, "value": value, "is_total": label.strip().lower() == "total"})

    time_el = card.select_one("time")
    updated_at = time_el.get_text(strip=True) if time_el else None

    if not categories:
        return None
    return {"heading": heading, "categories": categories, "updated_at": updated_at}


async def fetch_subscription_detail(slug: str, force: bool = False) -> dict | None:
    now = time.time()
    cached = _detail_cache.get(slug)
    if not force and cached and now - cached["fetched_at"] < _DETAIL_CACHE_TTL:
        return cached["data"]

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(DETAIL_URL.format(slug=slug), headers=_HEADERS)
        res.raise_for_status()

    data = _parse_subscription_detail(res.text)
    _detail_cache[slug] = {"data": data, "fetched_at": now}
    return data


def guess_slug(name: str) -> str:
    """Mirrors the client's own ipojiLink() slug guess (see IpoList.jsx) — used as a
    fallback when an IPO has aged off ipoji's homepage feed (see fetch_entries, which
    only keeps a rolling recent window) and so has no scraped slug to look up by."""
    cleaned = re.sub(r"\([^)]*\)", "", name or "")
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")
    return f"{slug}-ipo"


def _parse_listing_info(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    metrics = {}
    for m in soup.select(".ipo-gmp-metric"):
        dt, dd = m.select_one("dt"), m.select_one("dd")
        if dt and dd:
            metrics[dt.get_text(strip=True)] = dd.get_text(strip=True)

    list_price_text = metrics.get("Listing price")
    if not list_price_text:
        return None

    band_text = metrics.get("Upper price band")
    listing_direction = None
    listing_note = f"Listing Price: {list_price_text}"
    try:
        list_price = float(re.sub(r"[^\d.]", "", list_price_text))
        band = float(re.sub(r"[^\d.]", "", band_text)) if band_text else None
        if band:
            change_pct = (list_price - band) / band * 100
            listing_direction = "up" if change_pct >= 0 else "down"
            word = "Premium" if change_pct >= 0 else "Discount"
            listing_note = f"Listing Price: {list_price_text} at a {word} of {abs(change_pct):.2f}%"
    except ValueError:
        pass

    return {"list_price": list_price_text.lstrip("₹"), "listing_direction": listing_direction, "listing_note": listing_note}


# Fallback for IPOs that have already aged off ipoji's homepage feed — fetches that
# company's own detail page directly via a guessed slug, so listing price/premium still
# shows for older closed IPOs the homepage no longer teases. Cached per guessed slug
# (including negative/404 results) since a listing price never changes once set.
async def fetch_listing_info(name: str, force: bool = False) -> dict | None:
    slug = guess_slug(name)
    now = time.time()
    cached = _listing_info_cache.get(slug)
    if not force and cached and now - cached["fetched_at"] < _LISTING_INFO_CACHE_TTL:
        return cached["data"]

    data = None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(DETAIL_URL.format(slug=slug), headers=_HEADERS)
            if res.status_code == 200:
                data = _parse_listing_info(res.text)
    except Exception:
        data = None

    _listing_info_cache[slug] = {"data": data, "fetched_at": now}
    return data


def find_match(name: str, entries: list, threshold: float = 0.6):
    target = _normalize(name)
    best, best_score = None, 0.0
    for entry in entries:
        score = SequenceMatcher(None, target, _normalize(entry["name"])).ratio()
        if score > best_score:
            best, best_score = entry, score
    return (best, best_score) if best and best_score >= threshold else (None, best_score)
