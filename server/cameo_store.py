import asyncio
import ddddocr
import httpx
from bs4 import BeautifulSoup
from logging_config import log

SERVER1_BASE = "https://ipostatus1.cameoindia.com"
SERVER2_BASE = "https://ipostatus2.cameoindia.com:3000"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_CONCURRENCY = asyncio.Semaphore(1)
_ocr = ddddocr.DdddOcr(show_ad=False)


async def _fetch_server1_entries() -> list:
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": _UA}, verify=False) as client:
            res = await client.get(f"{SERVER1_BASE}/")
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            select_tag = soup.find("select", id="drpCompany")
            if not select_tag:
                return []
            return [
                {"name": opt.text.strip(), "value": f"s1:{opt.get('value')}"}
                for opt in select_tag.find_all("option")
                if opt.get("value") and opt.get("value") != "0"
            ]
    except Exception as err:
        log.warning(f"Cameo Server 1 entries failed: {err}")
        return []


async def _fetch_server2_entries() -> list:
    try:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": _UA,
        }
        async with httpx.AsyncClient(timeout=15, headers=headers, verify=False) as client:
            res = await client.post(f"{SERVER2_BASE}/api/1.0/company/getcompany", json={"isrecent": False})
            res.raise_for_status()
            companies = res.json()
            return [
                {"name": comp["name"], "value": f"s2:{comp['code']}"}
                for comp in companies
            ]
    except Exception as err:
        log.warning(f"Cameo Server 2 entries failed: {err}")
        return []


async def fetch_entries() -> list:
    s1, s2 = await asyncio.gather(_fetch_server1_entries(), _fetch_server2_entries())
    
    # Deduplicate by company name. Prefer Server 2 (API) since it avoids CAPTCHA.
    seen = set()
    deduped = []
    
    for entry in s2:
        name_key = entry["name"].strip().upper()
        if name_key not in seen:
            seen.add(name_key)
            deduped.append(entry)
            
    for entry in s1:
        name_key = entry["name"].strip().upper()
        if name_key not in seen:
            seen.add(name_key)
            deduped.append(entry)
            
    return deduped


async def _query_server1(client_id: str, pan: str) -> dict:
    headers = {
        "Accept": "*/*",
        "Cache-Control": "no-cache",
        "Origin": SERVER1_BASE,
        "Referer": f"{SERVER1_BASE}/",
        "User-Agent": _UA,
        "X-MicrosoftAjax": "Delta=true",
        "X-Requested-With": "XMLHttpRequest",
    }
    
    async with _CONCURRENCY, httpx.AsyncClient(timeout=15, headers=headers, verify=False) as client:
        try:
            res = await client.get(f"{SERVER1_BASE}/")
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            
            viewstate = soup.find("input", {"id": "__VIEWSTATE"})
            viewstategenerator = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
            eventvalidation = soup.find("input", {"id": "__EVENTVALIDATION"})
            
            if not viewstate or not viewstategenerator or not eventvalidation:
                return {"rows": [], "not_applied": False, "error": "Server 1 form fields missing"}

            captcha_img = soup.find("img", {"id": "imgCaptcha"})
            if not captcha_img:
                return {"rows": [], "not_applied": False, "error": "Server 1 captcha image missing"}
                
            captcha_url = f"{SERVER1_BASE}/{captcha_img['src']}"
            captcha_res = await client.get(captcha_url)
            captcha_res.raise_for_status()
            captcha_text = _ocr.classification(captcha_res.content)
            
            data = {
                "ScriptManager1": "OrdersPanel|btngenerate",
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "drpCompany": client_id,
                "ddlUserTypes": "PAN NO",
                "txtfolio": pan,
                "txt_phy_captcha": captcha_text,
                "__VIEWSTATE": viewstate["value"],
                "__VIEWSTATEGENERATOR": viewstategenerator["value"],
                "__EVENTVALIDATION": eventvalidation["value"],
                "__ASYNCPOST": "true",
                "btngenerate": "Submit",
            }
            
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            post_res = await client.post(f"{SERVER1_BASE}/", data=data)
            post_res.raise_for_status()
            
            parts = post_res.text.split("|")
            for i in range(len(parts)):
                if parts[i] == "updatePanel":
                    html_content = parts[i + 2] if i + 2 < len(parts) else None
                    if html_content:
                        soup_panel = BeautifulSoup(html_content, "html.parser")
                        
                        lblmsg = soup_panel.find(id="lblmsg")
                        if lblmsg:
                            msg = lblmsg.get_text(strip=True).upper()
                            if "CAPTCHA" in msg:
                                return {"rows": [], "not_applied": False, "error": "Server 1 CAPTCHA failed"}
                            if "NOT RECORD" in msg or "NO RECORD" in msg or "NOT FOUND" in msg or "NOT ALLOTED" in msg:
                                return {"rows": [], "not_applied": True, "error": None}
                                
                        table = soup_panel.find("table")
                        if table:
                            rows = table.find_all("tr")
                            if len(rows) > 1:
                                headers_row = [h.get_text(strip=True).upper() for h in rows[0].find_all(["th", "td"])]
                                results = []
                                for row in rows[1:]:
                                    cols = [col.get_text(strip=True) for col in row.find_all(["th", "td"])]
                                    row_dict = dict(zip(headers_row, cols))
                                    
                                    # Fallback matching for headers which might change cases/spacing
                                    def get_val(*keys):
                                        for k in keys:
                                            for rk, rv in row_dict.items():
                                                if k in rk:
                                                    return rv
                                        return ""
                                        
                                    results.append({
                                        "Name": get_val("NAME", "COMPANY"),
                                        "All_Shares": get_val("ALLOTED", "ALLOTTED"),
                                        "App_Shares": get_val("APPLIED", "APPLICATION"),
                                        "Appln_No": get_val("APPLNO", "APPLICATION NO"),
                                        "DP_CLID": get_val("DPID", "CLIENT ID"),
                                        "Pan_No": pan,
                                    })
                                return {"rows": results, "not_applied": False, "error": None}
                                
                elif parts[i] == "scriptStartupBlock":
                    script_content = parts[i + 2] if i + 2 < len(parts) else ""
                    if "incorrect" in script_content.lower() and "captcha" in script_content.lower():
                        return {"rows": [], "not_applied": False, "error": "Server 1 CAPTCHA failed"}
            
            return {"rows": [], "not_applied": False, "error": "Server 1 response could not be parsed"}

        except Exception as err:
            return {"rows": [], "not_applied": False, "error": str(err)}


async def _query_server2(client_id: str, pan: str) -> dict:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }
    async with httpx.AsyncClient(timeout=15, headers=headers, verify=False) as client:
        try:
            res = await client.post(
                f"{SERVER2_BASE}/api/1.0/ipostatus",
                json={"code": client_id, "type": "pan", "value": pan.upper()},
            )
            res.raise_for_status()
            data = res.json()
            
            if not data:
                return {"rows": [], "not_applied": True, "error": None}
                
            results = []
            for item in data:
                results.append({
                    "Name": item.get("name", ""),
                    "All_Shares": str(item.get("alloted", "0")),
                    "App_Shares": str(item.get("applied", "0")),
                    "Appln_No": item.get("appno", ""),
                    "DP_CLID": item.get("dp_id", ""),
                    "Pan_No": pan,
                })
            return {"rows": results, "not_applied": False, "error": None}
            
        except Exception as err:
            return {"rows": [], "not_applied": False, "error": str(err)}


async def query_status(client_id: str, pan: str) -> dict:
    if client_id.startswith("s1:"):
        for _ in range(5):
            res = await _query_server1(client_id[3:], pan)
            if res.get("error") == "Server 1 CAPTCHA failed":
                continue
            return res
        return {"rows": [], "not_applied": False, "error": "Server 1 Captcha could not be solved after 5 attempts"}
        
    elif client_id.startswith("s2:"):
        return await _query_server2(client_id[3:], pan)
        
    return {"rows": [], "not_applied": False, "error": "Invalid Cameo client ID"}
