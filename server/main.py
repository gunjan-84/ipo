import asyncio
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import accounts_store
import connections_store
import upi_store
from logging_config import log
from totp_util import generate_totp

KITE_BASE = "https://kite.zerodha.com"

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

accounts = accounts_store.load()  # [{id, label, user_id, password, totp_secret}]
upis = upi_store.load()  # [{id, upi_id, label}]


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
