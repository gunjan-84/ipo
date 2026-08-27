import time
import uuid

from playwright.async_api import async_playwright

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
_LOGIN_URL = "https://groww.in/login"
_PENDING_TTL_SECONDS = 5 * 60  # a login that's paused waiting for an OTP gets abandoned after this

# In-memory registry of logins paused mid-flow, waiting for the user to submit an OTP
# they've just received. Keyed by a one-time session id handed to the frontend.
_pending: dict[str, dict] = {}


def _sweep_expired():
    now = time.time()
    expired = [sid for sid, s in _pending.items() if now - s["started_at"] > _PENDING_TTL_SECONDS]
    for sid in expired:
        _abort(sid)


async def _abort(session_id: str):
    session = _pending.pop(session_id, None)
    if session:
        try:
            await session["browser"].close()
        except Exception:
            pass


def _make_token_sniffer():
    captured = {"bearer_token": None, "device_id": None, "user_nkey": None}

    def handle_request(request):
        auth = request.headers.get("authorization")
        did = request.headers.get("x-device-id")
        nkey = request.headers.get("x-user-nkey")
        if auth and auth.startswith("Bearer eyJ") and not captured["bearer_token"]:
            captured["bearer_token"] = auth.replace("Bearer ", "")
        if did and not captured["device_id"]:
            captured["device_id"] = did
        if nkey and not captured["user_nkey"]:
            captured["user_nkey"] = nkey

    return captured, handle_request


async def _wait_for_screen(page, timeout_iterations=30):
    """Groww's login flow doesn't expose stable selectors for OTP vs PIN, but the two
    screens always have exactly 6 vs 4 visible inputs — so we just count them."""
    for _ in range(timeout_iterations):
        count = await page.locator("input:visible").count()
        if count == 6:
            return "OTP"
        if count == 4:
            return "PIN"
        await page.wait_for_timeout(500)
    return None


async def _wait_for_tokens(page, captured: dict, require_nkey: bool, iterations=60):
    for _ in range(iterations):
        if captured["bearer_token"] and captured["device_id"] and (captured["user_nkey"] or not require_nkey):
            await page.wait_for_timeout(1000)
            return
        await page.wait_for_timeout(1000)


# --- Fresh login: email + password go straight into Groww's real login form; if Groww
# challenges with an OTP, we pause here and hand control back to the frontend to collect
# it from the user (the same OTP Groww is already sending them) — no OTP is ever guessed
# or intercepted on our end. ---
async def start_login(email: str, password: str, pin: str) -> dict:
    _sweep_expired()

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=_UA)
    page = await context.new_page()
    captured, handle_request = _make_token_sniffer()
    page.on("request", handle_request)

    try:
        await page.goto(_LOGIN_URL)
        await page.locator("#login_email1").wait_for(timeout=10000)
        await page.locator("#login_email1").fill(email)
        await page.get_by_role("button", name="Continue").click()

        await page.locator("#login_password1").wait_for(timeout=10000)
        await page.locator("#login_password1").fill(password)
        await page.get_by_role("button", name="Submit").click()

        screen = await _wait_for_screen(page)

        if screen == "OTP":
            session_id = str(uuid.uuid4())
            _pending[session_id] = {
                "playwright": playwright,
                "browser": browser,
                "context": context,
                "page": page,
                "captured": captured,
                "pin": pin,
                "started_at": time.time(),
            }
            return {"status": "otp_required", "session_id": session_id}

        if screen == "PIN":
            await page.wait_for_timeout(500)
            await page.locator("input:visible").first.click()
            await page.keyboard.type(pin)
            await _wait_for_tokens(page, captured, require_nkey=True)
            state_data = await context.storage_state()
            await browser.close()
            await playwright.stop()
            return {"status": "success", **captured, "state_data": state_data}

        await browser.close()
        await playwright.stop()
        return {"status": "error", "message": "Groww showed an unexpected screen after login — neither OTP nor PIN"}
    except Exception as err:
        await browser.close()
        await playwright.stop()
        return {"status": "error", "message": str(err)}


# --- Resumes a login paused at the OTP screen: types the OTP the user just received,
# then continues on to the PIN screen exactly as start_login would have. ---
async def submit_otp(session_id: str, otp: str) -> dict:
    session = _pending.pop(session_id, None)
    if not session:
        return {"status": "error", "message": "This login attempt has expired — please start again"}

    page = session["page"]
    captured = session["captured"]
    try:
        await page.locator("input:visible").first.click()
        await page.keyboard.type(otp)

        screen = None
        for _ in range(40):
            if await page.locator("input:visible").count() == 4:
                screen = "PIN"
                break
            await page.wait_for_timeout(500)

        if screen != "PIN":
            return {"status": "error", "message": "OTP was submitted but Groww never reached the PIN screen"}

        await page.wait_for_timeout(500)
        await page.locator("input:visible").first.click()
        await page.keyboard.type(session["pin"])
        await _wait_for_tokens(page, captured, require_nkey=True)

        state_data = await session["context"].storage_state()
        return {"status": "success", **captured, "state_data": state_data}
    except Exception as err:
        return {"status": "error", "message": str(err)}
    finally:
        await session["browser"].close()
        await session["playwright"].stop()


# --- Fetches a fresh set of Cloudflare bot-management cookies (__cf_bm, _cfuvid, etc.)
# by loading a real page with the account's saved browser session. These cookies can only
# be issued by Cloudflare after a real browser runs its JS challenge — a plain HTTP client
# can never produce them on its own. The browser only navigates here; it never submits or
# clicks anything, so this isn't itself a state-changing action. ---
async def fetch_cf_cookies(state_data: dict, path: str = "/") -> dict:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=_UA, storage_state=state_data)
    page = await context.new_page()

    try:
        await page.goto(f"https://groww.in{path}", wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1000)
        cookies = await context.cookies()
        return {c["name"]: c["value"] for c in cookies}
    finally:
        await browser.close()
        await playwright.stop()


# --- Silent refresh: reuses a previously saved browser session (cookies/storage) to get
# a fresh bearer token without any OTP — exactly what happens when you revisit a site
# you're still logged into. Used when the bearer token itself has expired. ---
async def silent_refresh(state_data: dict) -> dict:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=_UA, storage_state=state_data)
    page = await context.new_page()
    captured, handle_request = _make_token_sniffer()
    page.on("request", handle_request)

    try:
        await page.goto(_LOGIN_URL)
        await _wait_for_tokens(page, captured, require_nkey=False)
        if not captured["bearer_token"] or not captured["device_id"]:
            return {"status": "error", "message": "Saved session has expired — reconnect this account"}
        new_state_data = await context.storage_state()
        return {"status": "success", **captured, "state_data": new_state_data}
    except Exception as err:
        return {"status": "error", "message": str(err)}
    finally:
        await browser.close()
        await playwright.stop()
