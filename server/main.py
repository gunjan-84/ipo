import asyncio
import re
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import accounts_store
import connections_store
import ipoji_store
import kfintech_store
import mufg_store
import pan_store
import upi_store
from logging_config import log
from totp_util import generate_totp

KITE_BASE = "https://kite.zerodha.com"
KFINTECH_STATUS_URL = "https://0uz601ms56.execute-api.ap-south-1.amazonaws.com/prod/api/query"
KFINTECH_ORIGIN = "https://ipostatus.kfintech.com"
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def normalize_pan(pan: str) -> str | None:
    pan = (pan or "").strip().upper()
    return pan or None

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

accounts = accounts_store.load()  # [{id, label, user_id, password, totp_secret}]
upis = upi_store.load()  # [{id, upi_id, label}]
pans = pan_store.load()  # [{id, pan, label}] — shared PAN list, used for allotment checks
kfintech_store.load()  # [{name, value}] — KFintech's "Select IPO" dropdown, scraped from ipostatus.kfintech.com


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    log.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response


@app.on_event("startup")
async def on_startup():
    await connections_store.client.ping()
    log.info("Connected to Redis")


def find_account(account_id: str):
    return next((a for a in accounts if a["id"] == account_id), None)


# Kite returns this when the enctoken has expired/is invalid — treat it as an implicit logout
# so the account doesn't stay marked "connected" while every real call keeps failing.
async def is_auth_error(body: dict, account_id: str) -> bool:
    message = (body or {}).get("message")
    is_invalid_token = isinstance(message, str) and "incorrect" in message.lower() and "access_token" in message.lower()
    if is_invalid_token:
        await connections_store.delete(account_id)
        log.warning(f"account {account_id} auto-logged out — Kite rejected its enctoken")
    return is_invalid_token


async def public_account(a: dict) -> dict:
    conn = await connections_store.get(a["id"])
    return {
        "id": a["id"],
        "label": a["label"],
        "user_id": a["user_id"],
        "connected": conn is not None,
        "profile": (conn or {}).get("profile"),
    }


# --- Accounts CRUD ---
@app.get("/api/accounts")
async def list_accounts():
    data = [await public_account(a) for a in accounts]
    return {"status": "success", "data": data}


@app.post("/api/accounts")
async def add_account(payload: dict):
    label = payload.get("label")
    user_id = payload.get("user_id")
    password = payload.get("password")
    totp_secret = payload.get("totp_secret")
    if not user_id or not password or not totp_secret:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "user_id, password and totp_secret are required"},
        )

    account = {
        "id": str(uuid.uuid4()),
        "label": (label or user_id).strip(),
        "user_id": user_id.strip(),
        "password": password,
        "totp_secret": totp_secret.replace(" ", ""),
    }
    accounts.append(account)
    accounts_store.save(accounts)
    log.info(f"account added: {account['label']} ({account['user_id']})")
    return {"status": "success", "data": await public_account(account)}


@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str):
    global accounts
    accounts = [a for a in accounts if a["id"] != account_id]
    await connections_store.delete(account_id)
    accounts_store.save(accounts)
    log.info(f"account deleted: {account_id}")
    return {"status": "success"}


# Returns the stored credentials in plain text (personal-use tool, no auth gate).
@app.get("/api/accounts/{account_id}/reveal")
async def reveal_account(account_id: str):
    account = find_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})
    return {
        "status": "success",
        "data": {
            "user_id": account["user_id"],
            "password": account["password"],
            "totp_secret": account["totp_secret"],
        },
    }


@app.put("/api/accounts/{account_id}")
async def update_account(account_id: str, payload: dict):
    account = find_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    user_id = payload.get("user_id")
    if not user_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "user_id is required"})

    label = payload.get("label")
    password = payload.get("password")
    totp_secret = payload.get("totp_secret")

    credentials_changed = (
        user_id.strip() != account["user_id"]
        or (password and password != account["password"])
        or (totp_secret and totp_secret.replace(" ", "") != account["totp_secret"])
    )

    account["label"] = (label or user_id).strip()
    account["user_id"] = user_id.strip()
    if password:
        account["password"] = password
    if totp_secret:
        account["totp_secret"] = totp_secret.replace(" ", "")

    if credentials_changed:
        await connections_store.delete(account_id)

    accounts_store.save(accounts)
    log.info(f"account updated: {account['label']} ({account_id})")
    return {"status": "success", "data": await public_account(account)}


# --- Connect: login + TOTP in one shot using stored credentials ---
@app.post("/api/accounts/{account_id}/connect")
async def connect_account(account_id: str):
    account = find_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            login_res = await client.post(
                f"{KITE_BASE}/api/login",
                data={"user_id": account["user_id"], "password": account["password"]},
            )
            login_json = login_res.json()
            if login_json.get("status") != "success" or not login_json.get("data", {}).get("request_id"):
                log.warning(f"login failed for {account['label']}: {login_json.get('message')}")
                return JSONResponse(status_code=login_res.status_code or 400, content=login_json)

            totp = generate_totp(account["totp_secret"])
            twofa_res = await client.post(
                f"{KITE_BASE}/api/twofa",
                data={
                    "request_id": login_json["data"]["request_id"],
                    "user_id": account["user_id"],
                    "twofa_value": totp,
                    "twofa_type": login_json["data"].get("twofa_type", "totp"),
                },
            )
            twofa_json = twofa_res.json()
            if twofa_json.get("status") != "success":
                log.warning(f"twofa failed for {account['label']}: {twofa_json.get('message')}")
                return JSONResponse(status_code=twofa_res.status_code or 400, content=twofa_json)

            enc_token = twofa_res.cookies.get("enctoken")
            if not enc_token:
                return JSONResponse(
                    status_code=400, content={"status": "error", "message": "enctoken not found in response"}
                )

            await connections_store.set(
                account_id,
                {
                    "encToken": enc_token,
                    "profile": twofa_json.get("data", {}).get("profile", {}),
                    "connectedAt": int(time.time() * 1000),
                },
            )

            # Validate the token actually works before reporting success — Kite occasionally
            # issues an enctoken that gets rejected on the very next call.
            verify_res = await client.get(
                f"{KITE_BASE}/oms/ipo/instruments",
                headers={"Authorization": f"enctoken {enc_token}"},
            )
            verify_json = verify_res.json()
            if await is_auth_error(verify_json, account_id):
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": "error",
                        "message": "Login succeeded but the token was rejected — try connecting again",
                    },
                )

            log.info(f"account connected: {account['label']} ({account['user_id']})")
            return {"status": "success", "data": await public_account(account)}
    except Exception as err:
        log.exception(f"connect failed for account {account_id}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(err)})


@app.post("/api/accounts/{account_id}/disconnect")
async def disconnect_account(account_id: str):
    await connections_store.delete(account_id)
    log.info(f"account disconnected: {account_id}")
    return {"status": "success"}


# --- UPI IDs (shared across all accounts/applications) ---
@app.get("/api/upis")
async def list_upis():
    return {"status": "success", "data": upis}


@app.post("/api/upis")
async def add_upi(payload: dict):
    upi_id = payload.get("upi_id")
    label = payload.get("label", "")
    if not upi_id or "@" not in upi_id:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "A valid upi_id (e.g. name@bank) is required"}
        )
    entry = {"id": str(uuid.uuid4()), "upi_id": upi_id.strip(), "label": (label or "").strip()}
    upis.append(entry)
    upi_store.save(upis)
    return {"status": "success", "data": entry}


@app.delete("/api/upis/{upi_id}")
async def delete_upi(upi_id: str):
    global upis
    upis = [u for u in upis if u["id"] != upi_id]
    upi_store.save(upis)
    return {"status": "success"}


# --- PAN numbers (shared list, independent of accounts — used for allotment checks) ---
@app.get("/api/pans")
async def list_pans():
    return {"status": "success", "data": pans}


@app.post("/api/pans")
async def add_pan(payload: dict):
    pan = normalize_pan(payload.get("pan"))
    label = (payload.get("label") or "").strip()
    if not pan or not PAN_RE.match(pan):
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "A valid pan (e.g. ABCDE1234F) is required"}
        )
    entry = {"id": str(uuid.uuid4()), "pan": pan, "label": label or "Unknown"}
    pans.append(entry)
    pan_store.save(pans)
    return {"status": "success", "data": entry}


@app.put("/api/pans/{pan_id}")
async def update_pan(pan_id: str, payload: dict):
    entry = next((p for p in pans if p["id"] == pan_id), None)
    if not entry:
        return JSONResponse(status_code=404, content={"status": "error", "message": "PAN not found"})
    label = (payload.get("label") or "").strip()
    if not label:
        return JSONResponse(status_code=400, content={"status": "error", "message": "label is required"})
    entry["label"] = label
    pan_store.save(pans)
    return {"status": "success", "data": entry}


@app.delete("/api/pans/{pan_id}")
async def delete_pan(pan_id: str):
    global pans
    pans = [p for p in pans if p["id"] != pan_id]
    pan_store.save(pans)
    return {"status": "success"}


# --- IPO instruments: account-agnostic, uses any connected account's token ---
# Tries each connected account in turn, dropping any whose token Kite rejects, until one works.
@app.get("/api/ipo/instruments")
async def get_instruments():
    ids = await connections_store.connected_account_ids()
    if not ids:
        return JSONResponse(
            status_code=401, content={"status": "error", "message": "Connect at least one account first"}
        )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for account_id in ids:
                conn = await connections_store.get(account_id)
                if not conn:
                    continue
                res = await client.get(
                    f"{KITE_BASE}/oms/ipo/instruments", headers={"Authorization": f"enctoken {conn['encToken']}"}
                )
                body = res.json()
                if await is_auth_error(body, account_id):
                    continue
                return JSONResponse(status_code=res.status_code, content=body)
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Connected account(s) were logged out — reconnect and try again"},
        )
    except Exception as err:
        log.exception("get_instruments failed")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(err)})


# --- Applications across every connected account, tagged by account ---
@app.get("/api/ipo/applications")
async def get_applications():
    connected_ids = set(await connections_store.connected_account_ids())
    connected_accounts = [a for a in accounts if a["id"] in connected_ids]
    if not connected_accounts:
        return {"status": "success", "data": []}

    async def fetch_for(account):
        meta = {"id": account["id"], "label": account["label"], "user_id": account["user_id"]}
        conn = await connections_store.get(account["id"])
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.get(
                    f"{KITE_BASE}/oms/ipo/applications", headers={"Authorization": f"enctoken {conn['encToken']}"}
                )
                body = res.json()
            if await is_auth_error(body, account["id"]):
                return {"account": meta, "applications": [], "error": "Session expired — reconnect this account"}
            if body.get("status") == "success":
                return {"account": meta, "applications": body.get("data", []), "error": None}
            return {"account": meta, "applications": [], "error": body.get("message", "Failed to load applications")}
        except Exception as err:
            return {"account": meta, "applications": [], "error": str(err)}

    try:
        groups = await asyncio.gather(*(fetch_for(a) for a in connected_accounts))
        return {"status": "success", "data": groups}
    except Exception as err:
        log.exception("get_applications failed")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(err)})


# --- Apply to an IPO on behalf of one or more connected accounts ---
@app.post("/api/ipo/apply")
async def apply_ipo(payload: dict):
    account_ids = payload.get("account_ids")
    instrument_id = payload.get("instrument_id")
    investor_type = payload.get("investor_type")
    upi_id = payload.get("upi_id")
    bids = payload.get("bids")

    if not isinstance(account_ids, list) or not account_ids:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Select at least one account"})
    if not instrument_id or not upi_id or not isinstance(bids, list) or not bids:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "instrument_id, upi_id and bids are required"}
        )

    async def apply_for(account_id):
        account = find_account(account_id)
        meta = (
            {"id": account["id"], "label": account["label"], "user_id": account["user_id"]}
            if account
            else {"id": account_id}
        )
        conn = await connections_store.get(account_id)
        if not conn:
            return {"account": meta, "status": "error", "message": "Account not connected"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    f"{KITE_BASE}/oms/ipo/applications",
                    headers={"Authorization": f"enctoken {conn['encToken']}", "Content-Type": "application/json"},
                    json={
                        "instrument_id": instrument_id,
                        "investor_type": investor_type,
                        "upi_id": upi_id,
                        "bids": bids,
                    },
                )
                body = res.json()
            if await is_auth_error(body, account_id):
                return {"account": meta, "status": "error", "message": "Session expired — reconnect this account"}
            log.info(f"apply result for {meta.get('label', account_id)}: {body.get('status')}")
            return {
                "account": meta,
                "status": body.get("status"),
                "message": (body.get("data") or {}).get("message") or body.get("message"),
                "data": body.get("data"),
            }
        except Exception as err:
            return {"account": meta, "status": "error", "message": str(err)}

    results = await asyncio.gather(*(apply_for(aid) for aid in account_ids))
    return {"status": "success", "data": results}


# --- Cancel a specific account's application ---
@app.delete("/api/accounts/{account_id}/ipo/applications/{app_id}")
async def cancel_application(account_id: str, app_id: str):
    conn = await connections_store.get(account_id)
    if not conn:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Account not connected"})
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.request(
                "DELETE",
                f"{KITE_BASE}/oms/ipo/applications/{app_id}",
                headers={"Authorization": f"enctoken {conn['encToken']}", "Content-Type": "application/json"},
                json={},
            )
            body = res.json()
        if await is_auth_error(body, account_id):
            return JSONResponse(
                status_code=401, content={"status": "error", "message": "Session expired — reconnect this account"}
            )
        log.info(f"cancel result for account {account_id}: {body.get('status')}")
        return JSONResponse(status_code=res.status_code, content=body)
    except Exception as err:
        log.exception("cancel_application failed")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(err)})


# --- KFintech allotment status ---
# KFintech identifies an IPO by the "client_id" its own dropdown uses (scraped
# separately into kfintech_store.py) and identifies an applicant purely by PAN
# passed in a header — no login required.
async def query_kfintech_status(client_id: str, pan: str) -> dict:
    """Returns {"rows": [...], "not_applied": bool, "error": str | None}."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                KFINTECH_STATUS_URL,
                params={"type": "pan"},
                headers={
                    "client_id": client_id,
                    "origin": KFINTECH_ORIGIN,
                    "referer": f"{KFINTECH_ORIGIN}/",
                    "reqparam": pan,
                },
            )
            body = res.json()
    except Exception as err:
        return {"rows": [], "not_applied": False, "error": str(err)}

    # KFintech responds with {"error": "Record Not Found"} (no "data" key) when the PAN
    # simply hasn't applied to this IPO — that's a normal, expected outcome, not a failure.
    not_applied = body.get("error") == "Record Not Found"
    if "error" in body and not not_applied:
        return {"rows": [], "not_applied": False, "error": body["error"]}
    return {"rows": body.get("data", []), "not_applied": not_applied, "error": None}


# List of every IPO KFintech tracks (name + its client_id), for populating a dropdown
# without needing a connected Kite account.
@app.get("/api/ipo/kfintech-list")
async def list_kfintech_ipos():
    return {"status": "success", "data": kfintech_store.all_entries()}


# Registrars are identified by an opaque code at the API boundary rather than by name,
# so the registrar's identity never has to travel in a URL or request body.
REGISTRAR_KFINTECH = "1"
REGISTRAR_MUFG = "2"


async def query_registrar_status(registrar: str, client_id: str, pan: str) -> dict:
    if registrar == REGISTRAR_MUFG:
        return await mufg_store.query_status(client_id, pan)
    if registrar == REGISTRAR_KFINTECH:
        return await query_kfintech_status(client_id, pan)
    return {"rows": [], "not_applied": False, "error": "Unknown registrar"}


# Combined dropdown across every registrar we can check allotment status with —
# KFintech's full (scraped) history plus MUFG's live list of currently active offerings.
@app.get("/api/ipo/registry")
async def list_registry():
    entries = [{**e, "registrar": REGISTRAR_KFINTECH} for e in kfintech_store.all_entries()]
    try:
        mufg_entries = await mufg_store.fetch_entries()
        entries += [{**e, "registrar": REGISTRAR_MUFG} for e in mufg_entries]
    except Exception as err:
        log.warning(f"failed to fetch MUFG IPO list: {err}")
    entries.sort(key=lambda e: e["name"])
    return {"status": "success", "data": entries}


# Single-PAN lookup: match our Kite IPO name against KFintech's dropdown list to get
# its client_id (or take client_id directly), then query status for one PAN.
@app.get("/api/ipo/status")
async def check_ipo_status(pan: str, name: str = None, client_id: str = None):
    pan = normalize_pan(pan)
    if not pan:
        return JSONResponse(status_code=400, content={"status": "error", "message": "pan is required"})

    matched_name = None
    match_score = None
    if not client_id:
        if not name:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": "name or client_id is required"}
            )
        match, score = kfintech_store.find_match(name)
        if not match:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": f"No matching IPO found on KFintech for '{name}'"},
            )
        client_id = match["value"]
        matched_name = match["name"]
        match_score = round(score, 2)

    result = await query_kfintech_status(client_id, pan)
    if result["error"]:
        return JSONResponse(status_code=502, content={"status": "error", "message": result["error"]})

    log.info(f"ipo status check: pan={pan} client_id={client_id} matched={matched_name} -> {len(result['rows'])} row(s)")
    return {
        "status": "success",
        "data": result["rows"],
        "not_applied": result["not_applied"],
        "matched_name": matched_name,
        "match_score": match_score,
        "client_id": client_id,
    }


# Allotment check across every saved account that has a PAN on file, for one IPO.
@app.get("/api/ipo/allotment")
async def check_allotment(client_id: str, registrar: str = REGISTRAR_KFINTECH):
    if not client_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "client_id is required"})

    if not pans:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "No PAN numbers saved yet — add one under PAN Numbers"},
        )

    async def fetch_for(entry):
        result = await query_registrar_status(registrar, client_id, entry["pan"])
        # First real hit for a still-unnamed PAN: adopt KFintech's applicant name as its label.
        if result["rows"] and entry.get("label", "Unknown") == "Unknown":
            applicant_name = result["rows"][0].get("Name")
            if applicant_name:
                entry["label"] = applicant_name.strip().title()
        return {
            "pan_entry": {"id": entry["id"], "pan": entry["pan"], "label": entry.get("label", "")},
            "data": result["rows"],
            "not_applied": result["not_applied"],
            "error": result["error"],
        }

    results = await asyncio.gather(*(fetch_for(p) for p in pans))
    pan_store.save(pans)
    log.info(f"allotment check: registrar={registrar} client_id={client_id} -> {len(results)} pan(s)")
    return {"status": "success", "data": results}


# Expected-premium (GMP) and subscription figures scraped from ipoji.com's homepage cards.
# Matching against our own instrument names happens client-side (see IpoList.jsx) — this
# just hands over ipoji's raw list, cached for a few minutes so we don't hammer their site.
@app.get("/api/ipo/premiums")
async def get_ipo_premiums():
    try:
        entries = await ipoji_store.fetch_entries()
    except Exception as err:
        log.warning(f"failed to fetch ipoji premiums: {err}")
        return {"status": "success", "data": []}
    return {"status": "success", "data": entries}


# Category-wise (QIB/NII/HNI/Retail/Total) live subscription breakdown for one IPO,
# scraped from its ipoji.com detail page.
@app.get("/api/ipo/subscription")
async def get_ipo_subscription(slug: str):
    try:
        detail = await ipoji_store.fetch_subscription_detail(slug)
    except Exception as err:
        log.warning(f"failed to fetch ipoji subscription detail for {slug}: {err}")
        return JSONResponse(status_code=502, content={"status": "error", "message": str(err)})

    if not detail:
        return JSONResponse(
            status_code=404, content={"status": "error", "message": "No subscription details found for this IPO"}
        )
    return {"status": "success", "data": detail}
