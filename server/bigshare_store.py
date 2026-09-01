import asyncio
import base64

import ddddocr
import httpx
from bs4 import BeautifulSoup

BASE = "https://ipo.bigshareonline.com"
# Unlike KFintech/MUFG, Bigshare rate-limits hard and per-IP — even two sessions running
# at once was enough to trip a 429 in testing. Serialize every lookup through one slot.
_CONCURRENCY = asyncio.Semaphore(1)
_STATUS_PAGE = f"{BASE}/ipo_status.html"
_CAPTCHA_URL = f"{BASE}/Captcha.ashx"
_FETCH_URL = f"{BASE}/Data.aspx/FetchIpodetails"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Loading ddddocr's OCR model takes a couple of seconds — do it once at import time,
# not on every captcha solve.
_ocr = ddddocr.DdddOcr(show_ad=False)


# Bigshare's dropdown only ever lists currently active offerings (like MUFG), so we
# fetch it live on every call rather than keeping a scraped snapshot.
async def fetch_entries() -> list:
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA}) as client:
        res = await client.get(_STATUS_PAGE)
        res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    select_tag = soup.find("select", id="ddlCompany")
    if not select_tag:
        return []
    return [
        {"name": opt.text.strip(), "value": opt.get("value")}
        for opt in select_tag.find_all("option")
        if opt.get("value") and opt.text.strip() not in ("", "--Select Company--")
    ]


async def _request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """GET/POST with a backoff retry on 429 — Bigshare's rate limit window seems to run
    tens of seconds, not the couple of seconds a typical API cools down in."""
    for attempt in range(4):
        res = await client.request(method, url, **kwargs)
        if res.status_code != 429:
            res.raise_for_status()
            return res
        await asyncio.sleep(15 * (attempt + 1))
    res.raise_for_status()
    return res


async def _get_captcha(client: httpx.AsyncClient):
    res = await _request_with_retry(client, "GET", _CAPTCHA_URL)
    data = res.json()
    token = data.get("token") or data.get("Token")
    image_b64 = data.get("image") or data.get("Image") or ""
    if image_b64.startswith("data:image/png;base64,"):
        image_b64 = image_b64.replace("data:image/png;base64,", "")
    return token, base64.b64decode(image_b64) if image_b64 else None


# Bigshare gates every lookup behind an image captcha — solved with ddddocr's OCR model
# and retried a few times, since an occasional misread just gets rejected with a
# "CAPTCHA" status rather than an error we could otherwise detect up front.
async def query_status(client_id: str, pan: str) -> dict:
    """Returns {"rows": [...], "not_applied": bool, "error": str | None}, normalized to the
    same row shape as KFintech's/MUFG's queries."""
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": BASE,
        "Referer": _STATUS_PAGE,
        "X-Requested-With": "XMLHttpRequest",
    }
    async with _CONCURRENCY, httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA}) as client:
        try:
            await _request_with_retry(client, "GET", _STATUS_PAGE)  # establishes the session cookie the captcha/lookup need
        except Exception as err:
            return {"rows": [], "not_applied": False, "error": str(err)}

        for _ in range(5):
            try:
                token, image_bytes = await _get_captcha(client)
            except Exception as err:
                return {"rows": [], "not_applied": False, "error": str(err)}
            if not token or not image_bytes:
                continue
            captcha_answer = _ocr.classification(image_bytes)

            try:
                res = await _request_with_retry(
                    client,
                    "POST",
                    _FETCH_URL,
                    json={
                        "Applicationno": "",
                        "Company": client_id,
                        "SelectionType": "PN",
                        "PanNo": pan,
                        "txtcsdl": "",
                        "txtDPID": "",
                        "txtClId": "",
                        "ddlType": "0",
                        "lang": "en",
                        "CaptchaToken": token,
                        "CaptchaAnswer": captcha_answer,
                        "ResultToken": "",
                    },
                    headers=headers,
                )
                body = res.json()
            except Exception as err:
                return {"rows": [], "not_applied": False, "error": str(err)}

            data = body.get("d") or {}
            status = data.get("Status")
            if status == "CAPTCHA":
                continue  # misread — try again with a fresh captcha
            if status == "NOTFOUND":
                return {"rows": [], "not_applied": True, "error": None}
            if not status:
                return {
                    "rows": [],
                    "not_applied": False,
                    "error": data.get("Message") or "Unknown response from Bigshare",
                }

            row = {
                "Name": data.get("Name", ""),
                "All_Shares": data.get("ALLOTED", "0"),
                "App_Shares": data.get("APPLIED", "0"),
                "Appln_No": data.get("ApplicationNo") or data.get("Applicationno", ""),
                "DP_CLID": data.get("DPID", ""),
                "Pan_No": pan,
            }
            return {"rows": [row], "not_applied": False, "error": None}

        return {"rows": [], "not_applied": False, "error": "Captcha could not be solved after 5 attempts"}
