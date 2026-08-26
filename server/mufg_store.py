import xml.etree.ElementTree as ET

import httpx

BASE = "https://in.mpms.mufg.com/Initial_Offer/IPO.aspx"
ORIGIN = "https://in.mpms.mufg.com"

_HEADERS = {
    "Content-Type": "application/json;charset:utf-8",
    "Origin": ORIGIN,
    "Referer": f"{ORIGIN}/Initial_Offer/public-issues.html",
}


def _parse_dataset(xml_str: str) -> list:
    """Parses MUFG's "<NewDataSet><Table>...</Table></NewDataSet>" responses
    (or the empty self-closing "<NewDataSet />" for no results) into dicts."""
    if not xml_str:
        return []
    root = ET.fromstring(xml_str)
    return [{child.tag: (child.text or "") for child in table} for table in root.findall("Table")]


# MUFG's dropdown only ever lists currently active offerings (unlike KFintech's full
# history), so we fetch it live on every call rather than keeping a scraped snapshot.
async def fetch_entries() -> list:
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(f"{BASE}/GetDetails", json={}, headers=_HEADERS)
        body = res.json()
    rows = _parse_dataset(body.get("d", ""))
    return [{"name": r.get("companyname", ""), "value": r.get("company_id", "")} for r in rows if r.get("company_id")]


async def query_status(client_id: str, pan: str) -> dict:
    """Returns {"rows": [...], "not_applied": bool, "error": str | None}, normalized to the
    same row shape as KFintech's query_kfintech_status (Name/All_Shares/App_Shares/Appln_No/DP_CLID/Pan_No)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                f"{BASE}/SearchOnPan",
                json={"clientid": client_id, "PAN": pan, "IFSC": "", "CHKVAL": "1", "token": "1"},
                headers=_HEADERS,
            )
            body = res.json()
    except Exception as err:
        return {"rows": [], "not_applied": False, "error": str(err)}

    rows = _parse_dataset(body.get("d", ""))
    if not rows:
        return {"rows": [], "not_applied": True, "error": None}

    normalized = [
        {
            "Name": r.get("NAME1", ""),
            "All_Shares": r.get("ALLOT", "0"),
            "App_Shares": r.get("SHARES", "0"),
            "Appln_No": r.get("RFNDNO", ""),
            "DP_CLID": r.get("DPCLITID", ""),
            "Pan_No": pan,
        }
        for r in rows
    ]
    return {"rows": normalized, "not_applied": False, "error": None}
