import os
from playwright.sync_api import sync_playwright
from dotenv import set_key

def create_session():
    """
    Spawns a browser for the user to perform the initial login.
    Silently captures the Bearer Token, Device ID, and NKey binding directly from network requests,
    saving them to .env for native Python API usage.
    """
    with sync_playwright() as p:
        print("[*] Launching browser for initial authentication...")
        browser = p.chromium.launch(channel="msedge", headless=False)
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        bearer_token = None
        device_id = None
        user_nkey = None
        
        def handle_request(request):
            nonlocal bearer_token, device_id, user_nkey
            auth = request.headers.get("authorization")
            did = request.headers.get("x-device-id")
            nkey = request.headers.get("x-user-nkey")
            
            if auth and auth.startswith("Bearer eyJ") and not bearer_token:
                bearer_token = auth.replace("Bearer ", "")
                print(f"[+] Captured Bearer Token!")
                
            if did and not device_id:
                device_id = did
                print(f"[+] Captured Device ID: {device_id}")
                
            if nkey and not user_nkey:
                user_nkey = nkey
                print(f"[+] Captured X-USER-NKEY: {user_nkey}")

        page.on("request", handle_request)

        page.goto("https://groww.in/login")
        
        print("\n" + "="*50)
        print("ACTION REQUIRED:")
        print("1. Log in to Groww in the browser window using Email/Password/OTP.")
        print("2. Once you reach the dashboard, come back to this terminal.")
        print("3. Press ENTER here to save your session and tokens!")
        print("="*50 + "\n")
        
        input("Press ENTER when you are on the dashboard... ")

        # Save standard storage state (cookies, localstorage)
        context.storage_state(path="groww_state.json")
        
        # Save PLAINTEXT secrets directly to .env
        env_path = ".env"
        if bearer_token:
            set_key(env_path, "GROWW_BEARER_TOKEN", bearer_token)
        if device_id:
            set_key(env_path, "GROWW_DEVICE_ID", device_id)
        if user_nkey:
            set_key(env_path, "GROWW_NKEY", user_nkey)
            
        print("\n[+] Session successfully saved to groww_state.json!")
        print("[+] All API secrets successfully exported to .env!")

        browser.close()

if __name__ == "__main__":
    create_session()
