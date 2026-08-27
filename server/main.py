import asyncio
import re
import secrets
import time
import uuid

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import accounts_store
import auth_store
import connections_store
import groww_bids_store
import groww_client
import groww_login
import groww_store
import ipoji_store
import kfintech_store
import mufg_store
import pan_store
import upi_store
from logging_config import log
from totp_util import generate_totp

SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — personal-use tool, long-lived login is fine
_PUBLIC_AUTH_PATHS = {"/api/auth/status", "/api/auth/setup", "/api/auth/login"}

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
groww_accounts = groww_store.load()  # [{id, label, bearer_token, device_id, nkey, pin, pin_token}]
groww_bids = groww_bids_store.load()  # [{account_id, symbol, quantity, price, applied_at}]
auth_record = auth_store.load()  # {username, salt, password_hash} or None until first-run setup


async def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    await connections_store.client.set(f"session:{token}", username, ex=SESSION_TTL_SECONDS)
    return token


async def session_username(request: Request):
    token = request.cookies.get("session_token")
    return await connections_store.client.get(f"session:{token}") if token else None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    log.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response


# Gate every /api/* route behind a login, except the handful needed to set up or perform that login.
@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path in _PUBLIC_AUTH_PATHS:
        return await call_next(request)
    if not await session_username(request):
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not authenticated"})
    return await call_next(request)


@app.on_event("startup")
async def on_startup():
    await connections_store.client.ping()
    log.info("Connected to Redis")


# --- App login (protects every route above) ---
@app.get("/api/auth/status")
async def auth_status(request: Request):
    username = await session_username(request)
    return {
        "status": "success",
        "data": {"configured": auth_record is not None, "authenticated": username is not None, "username": username},
    }


# Only works once, before any credentials exist — sets the single app login and signs you in.
@app.post("/api/auth/setup")
async def auth_setup(payload: dict, response: Response):
    global auth_record
    if auth_record is not None:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Login is already set up"})

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or len(password) < 6:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "username is required and password must be at least 6 characters"},
        )

    auth_record = auth_store.save(username, password)
    token = await create_session(username)
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS)
    log.info(f"app login configured for {username}")
    return {"status": "success", "data": {"username": username}}


@app.post("/api/auth/login")
async def auth_login(payload: dict, response: Response):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not auth_store.verify(auth_record, username, password):
        return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid username or password"})

    token = await create_session(username)
    response.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS)
    log.info(f"login: {username}")
    return {"status": "success", "data": {"username": username}}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await connections_store.client.delete(f"session:{token}")
    response.delete_cookie("session_token")
    return {"status": "success"}


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


# --- Groww: bearer_token/device_id/nkey are captured once by driving Groww's real login
# page (see groww_login.py) — the user's own email/password, and any OTP Groww sends them,
# same as logging in through a browser. From then on the PIN alone lets us silently
# refresh access (see groww_client.unlock_pin), and the saved browser session (state_data)
# lets us silently refresh the bearer token itself if it expires — so the user never has
# to repeat that login just to keep pulling orders or applying to IPOs. ---
# Label + PIN chosen at /api/groww/login/start time, held here only until /otp completes
# the login and the account can actually be created (in-memory only — never touches disk).
_pending_logins: dict[str, dict] = {}


def find_groww_account(account_id: str):
    return next((a for a in groww_accounts if a["id"] == account_id), None)


def public_groww_account(a: dict) -> dict:
    return {"id": a["id"], "label": a["label"], "connected": bool(a.get("pin_token"))}


def _save_groww_login_result(label: str, login_result: dict) -> dict:
    account = {
        "id": str(uuid.uuid4()),
        "label": label or "Groww",
        "bearer_token": login_result["bearer_token"],
        "device_id": login_result["device_id"],
        "nkey": login_result["user_nkey"],
        "pin": login_result["pin"],
        "pin_token": None,
        "state_data": login_result.get("state_data"),
    }
    groww_accounts.append(account)
    groww_store.save(groww_accounts)
    log.info(f"groww account added via login: {account['label']}")
    return account


# Step 1 of adding a Groww account: drive the real login form with email/password. Groww
# either lets us straight through to the PIN screen, or challenges with an OTP first — in
# which case we pause and ask the frontend to collect it from the user right now.
@app.post("/api/groww/login/start")
async def groww_login_start(payload: dict):
    label = (payload.get("label") or "").strip()
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    pin = (payload.get("pin") or "").strip()
    if not email or not password or not pin:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "email, password and pin are required"}
        )

    result = await groww_login.start_login(email, password, pin)
    if result["status"] == "error":
        return JSONResponse(status_code=502, content={"status": "error", "message": result["message"]})

    if result["status"] == "otp_required":
        _pending_logins[result["session_id"]] = {"label": label, "pin": pin}
        return {"status": "success", "data": {"otp_required": True, "session_id": result["session_id"]}}

    account = _save_groww_login_result(label, {**result, "pin": pin})
    return {"status": "success", "data": {"otp_required": False, "account": public_groww_account(account)}}


# Step 2 (only when start_login paused for one): the OTP Groww just sent the user.
@app.post("/api/groww/login/otp")
async def groww_login_otp(payload: dict):
    session_id = payload.get("session_id")
    otp = (payload.get("otp") or "").strip()
    if not session_id or not otp:
        return JSONResponse(status_code=400, content={"status": "error", "message": "session_id and otp are required"})

    result = await groww_login.submit_otp(session_id, otp)
    if result["status"] == "error":
        return JSONResponse(status_code=502, content={"status": "error", "message": result["message"]})

    pending = _pending_logins.pop(session_id, {"label": "", "pin": None})
    if not pending["pin"]:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "This login attempt has expired — please start again"}
        )
    account = _save_groww_login_result(pending["label"], {**result, "pin": pending["pin"]})
    return {"status": "success", "data": public_groww_account(account)}


# Shared recovery path for order/apply/cancel calls: if the action fails and we have a
# saved browser session, silently refresh the bearer token (no OTP) and retry once.
async def _groww_with_recovery(account: dict, action):
    try:
        return await action(account)
    except Exception:
        if not account.get("state_data"):
            raise
        refresh = await groww_login.silent_refresh(account["state_data"])
        if refresh["status"] != "success":
            raise
        account["bearer_token"] = refresh["bearer_token"]
        account["device_id"] = refresh["device_id"]
        if refresh.get("user_nkey"):
            account["nkey"] = refresh["user_nkey"]
        account["state_data"] = refresh["state_data"]
        account["pin_token"] = None
        groww_store.save(groww_accounts)
        log.info(f"groww bearer token silently refreshed for {account['label']}")
        return await action(account)


@app.get("/api/groww/accounts")
async def list_groww_accounts():
    return {"status": "success", "data": [public_groww_account(a) for a in groww_accounts]}


@app.post("/api/groww/accounts")
async def add_groww_account(payload: dict):
    label = (payload.get("label") or "").strip()
    bearer_token = (payload.get("bearer_token") or "").strip()
    device_id = (payload.get("device_id") or "").strip()
    nkey = (payload.get("nkey") or "").strip()
    pin = (payload.get("pin") or "").strip()
    if not bearer_token or not device_id or not nkey or not pin:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "bearer_token, device_id, nkey and pin are required"},
        )

    account = {
        "id": str(uuid.uuid4()),
        "label": label or "Groww",
        "bearer_token": bearer_token,
        "device_id": device_id,
        "nkey": nkey,
        "pin": pin,
        "pin_token": None,
    }
    groww_accounts.append(account)
    groww_store.save(groww_accounts)
    log.info(f"groww account added: {account['label']}")
    return {"status": "success", "data": public_groww_account(account)}


# Lets the user paste fresh bearer_token/device_id/nkey after re-running the browser
# login (e.g. once the old JWT finally expires), without losing the account's id/label/PIN.
@app.put("/api/groww/accounts/{account_id}")
async def update_groww_account(account_id: str, payload: dict):
    account = find_groww_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    label = payload.get("label")
    bearer_token = payload.get("bearer_token")
    device_id = payload.get("device_id")
    nkey = payload.get("nkey")
    pin = payload.get("pin")

    if label:
        account["label"] = label.strip()
    if bearer_token:
        account["bearer_token"] = bearer_token.strip()
    if device_id:
        account["device_id"] = device_id.strip()
    if nkey:
        account["nkey"] = nkey.strip()
    if pin:
        account["pin"] = pin.strip()
    if bearer_token or device_id or nkey or pin:
        account["pin_token"] = None  # force a fresh unlock next fetch

    groww_store.save(groww_accounts)
    log.info(f"groww account updated: {account['label']} ({account_id})")
    return {"status": "success", "data": public_groww_account(account)}


@app.delete("/api/groww/accounts/{account_id}")
async def delete_groww_account(account_id: str):
    global groww_accounts
    groww_accounts = [a for a in groww_accounts if a["id"] != account_id]
    groww_store.save(groww_accounts)
    log.info(f"groww account deleted: {account_id}")
    return {"status": "success"}


# Mirrors Kite's "Connect": confirms access works right now by unlocking a fresh PIN
# token (falling back to a silent bearer-token refresh first, if needed), rather than
# waiting for the next orders/apply/cancel call to discover it's stale.
@app.post("/api/groww/accounts/{account_id}/connect")
async def connect_groww_account(account_id: str):
    account = find_groww_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    async def do_unlock(acc):
        return await groww_client.unlock_pin(acc["bearer_token"], acc["device_id"], acc["nkey"], acc["pin"])

    try:
        pin_token = await _groww_with_recovery(account, do_unlock)
    except Exception as err:
        log.warning(f"groww connect failed for {account['label']}: {err}")
        return JSONResponse(status_code=502, content={"status": "error", "message": str(err)})

    account["pin_token"] = pin_token
    groww_store.save(groww_accounts)
    log.info(f"groww account connected: {account['label']}")
    return {"status": "success", "data": public_groww_account(account)}


# Mirrors Kite's "Disconnect": drops the current PIN unlock (the saved login session and
# PIN are kept, so reconnecting doesn't need a fresh browser login or OTP).
@app.post("/api/groww/accounts/{account_id}/disconnect")
async def disconnect_groww_account(account_id: str):
    account = find_groww_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})
    account["pin_token"] = None
    groww_store.save(groww_accounts)
    log.info(f"groww account disconnected: {account['label']}")
    return {"status": "success", "data": public_groww_account(account)}


# Orchestrates the full sequence: fetch with the stored pin_token, transparently unlocking
# a fresh one from the stored PIN if it's expired (and, if even that fails, silently
# refreshing the bearer token from the saved browser session), then retrying.
@app.get("/api/groww/accounts/{account_id}/orders")
async def get_groww_orders(account_id: str):
    account = find_groww_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    try:
        orders, refreshed_pin_token = await _groww_with_recovery(account, groww_client.fetch_orders_with_auto_unlock)
    except Exception as err:
        log.exception(f"groww fetch failed for {account['label']}")
        return JSONResponse(status_code=502, content={"status": "error", "message": str(err)})

    if refreshed_pin_token:
        account["pin_token"] = refreshed_pin_token
        groww_store.save(groww_accounts)
        log.info(f"groww PIN token refreshed for {account['label']}")

    attach_groww_bid_info(account_id, orders)
    return {"status": "success", "data": orders}


# Matches each order against our own record of what we submitted at apply-time (see
# apply_groww_ipo below) — same account, same symbol, closest submission time — since
# Groww's order-list API never echoes back the bid quantity/price it was placed at.
def attach_groww_bid_info(account_id: str, orders: list):
    candidates = [b for b in groww_bids if b["account_id"] == account_id]
    for order in orders:
        matches = [b for b in candidates if b["symbol"] == order.get("symbol")]
        if not matches:
            continue
        best = min(matches, key=lambda b: abs(b["applied_at"] - (order.get("orderTimeStamp") or 0)))
        if abs(best["applied_at"] - (order.get("orderTimeStamp") or 0)) < 10 * 60 * 1000:
            order["bidQuantity"] = best["quantity"]
            order["bidPrice"] = best["price"]


# Applies for an IPO on a Groww account — only ever called by an explicit "Apply" click.
@app.post("/api/groww/accounts/{account_id}/apply")
async def apply_groww_ipo(account_id: str, payload: dict):
    account = find_groww_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    symbol = payload.get("symbol")
    isin = payload.get("isin")
    quantity = payload.get("quantity")
    price = payload.get("price")
    upi_id = payload.get("upi_id")
    cutoff = payload.get("cutoff", True)
    if not symbol or not isin or not quantity or not price or not upi_id:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "symbol, isin, quantity, price and upi_id are required"},
        )

    try:
        data, refreshed_pin_token = await _groww_with_recovery(
            account, lambda acc: groww_client.apply_for_ipo(acc, symbol, isin, quantity, price, upi_id, cutoff)
        )
    except Exception as err:
        log.exception(f"groww apply failed for {account['label']}")
        return JSONResponse(status_code=502, content={"status": "error", "message": str(err)})

    if refreshed_pin_token:
        account["pin_token"] = refreshed_pin_token
    groww_store.save(groww_accounts)

    groww_bids.append(
        {"account_id": account_id, "symbol": symbol, "quantity": quantity, "price": price, "applied_at": time.time() * 1000}
    )
    groww_bids_store.save(groww_bids)

    log.info(f"groww apply result for {account['label']} ({symbol}): success")
    return {"status": "success", "data": data}


# Cancels a previously submitted IPO application — only ever called by an explicit "Cancel" click.
@app.delete("/api/groww/accounts/{account_id}/orders/{order_id}")
async def cancel_groww_order(account_id: str, order_id: str, search_id: str = None):
    account = find_groww_account(account_id)
    if not account:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Account not found"})

    try:
        data, refreshed_pin_token = await _groww_with_recovery(
            account, lambda acc: groww_client.cancel_order(acc, order_id, search_id)
        )
    except Exception as err:
        log.exception(f"groww cancel failed for {account['label']}")
        return JSONResponse(status_code=502, content={"status": "error", "message": str(err)})

    if refreshed_pin_token:
        account["pin_token"] = refreshed_pin_token
    groww_store.save(groww_accounts)
    log.info(f"groww cancel result for {account['label']} (order {order_id}): success")
    return {"status": "success", "data": data}


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
