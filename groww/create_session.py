import os
import getpass
import re
import msvcrt
from playwright.sync_api import sync_playwright
from dotenv import set_key, load_dotenv
import json

def flush_input():
    """Flushes the Windows terminal input buffer to prevent ghost inputs."""
    try:
        while msvcrt.kbhit():
            msvcrt.getch()
    except Exception:
        pass

def create_session(email=None, password=None, pin=None, state_data=None, otp_callback=None):
    """
    Spawns a browser to perform authentication.
    Can be called directly with arguments by a backend server, or run standalone via CLI.
    Returns a dictionary with the extracted tokens and Playwright state data.
    """
    is_standalone = (__name__ == "__main__")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    state_path = os.path.join(script_dir, "groww_state.json")
    env_path = os.path.join(script_dir, ".env")
    
    # Fallback to file reading if no state_data is provided and running standalone
    if is_standalone and not state_data and os.path.exists(state_path):
        with open(state_path, 'r') as f:
            state_data = json.load(f)
            
    is_silent_refresh = bool(state_data)
    
    if not is_silent_refresh and not all([email, password, pin]):
        if is_standalone:
            print("="*50)
            print("INITIAL LOGIN SETUP")
            print("="*50)
            email = input("Enter Groww Email: ").strip()
            password = getpass.getpass("Enter Groww Password: ")
            
            pin = ""
            while not pin.isdigit() or len(pin) != 4:
                flush_input()
                pin = getpass.getpass("Enter 4-digit PIN: ").strip()
                if not pin.isdigit() or len(pin) != 4:
                    print("[-] Invalid PIN. Must be exactly 4 digits.")
            
            # Save PIN to .env immediately so unlock_pin.py can use it later
            set_key(env_path, "PIN", pin)
        else:
            raise ValueError("Email, password, and pin must be provided for a fresh login.")

    with sync_playwright() as p:
        print("\n[*] Launching browser for authentication...")
        browser = p.chromium.launch(channel="msedge", headless=False)
        
        context_options = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        
        if is_silent_refresh:
            print("[+] Found existing state data! Loading it to silently refresh the Bearer Token...")
            context_options["storage_state"] = state_data
            
        context = browser.new_context(**context_options)
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
                print(f"\n[+] Captured Bearer Token!")
                
            if did and not device_id:
                device_id = did
                print(f"[+] Captured Device ID: {device_id}")
                
            if nkey and not user_nkey:
                user_nkey = nkey
                print(f"[+] Captured X-USER-NKEY: {user_nkey}")

        page.on("request", handle_request)
        page.goto("https://groww.in/login")
        
        if not is_silent_refresh:
            print("\n[*] Auto-filling Email and Password...")
            try:
                page.locator('#login_email1').wait_for(timeout=5000)
                page.locator('#login_email1').fill(email)
                page.get_by_role('button', name='Continue').click()
                
                page.locator('#login_password1').wait_for(timeout=5000)
                page.locator('#login_password1').fill(password)
                page.get_by_role('button', name='Submit').click()
                
                print("[*] Credentials submitted.")
                
                # ADAPT TO SCREEN: Forget URLs and Text. We count physical input boxes!
                # OTP Screen has exactly 6 inputs. PIN Screen has exactly 4 inputs.
                try:
                    # 1. Wait to see if we hit OTP (6) or go straight to PIN (4)
                    print("[*] Adapting to screen...")
                    screen_type = None
                    
                    for _ in range(30):
                        inputs_count = page.locator("input:visible").count()
                        if inputs_count == 6:
                            screen_type = "OTP"
                            break
                        elif inputs_count == 4:
                            screen_type = "PIN"
                            break
                        page.wait_for_timeout(500)
                        
                    if screen_type == "OTP":
                        otp = ""
                        if otp_callback:
                            otp = otp_callback()
                        else:
                            while not otp.isdigit() or len(otp) != 6:
                                flush_input()
                                otp = input("\n[!] OTP REQUIRED: Enter the 6-digit OTP sent to your device: ").strip()
                                if not otp.isdigit() or len(otp) != 6:
                                    print("[-] Invalid OTP. Must be exactly 6 digits.")
                                
                        print("[*] Typing OTP into browser...")
                        page.locator("input:visible").first.click()
                        page.keyboard.type(otp)
                        
                        # Now wait for the transition to the PIN screen (4 inputs)
                        for _ in range(40):
                            if page.locator("input:visible").count() == 4:
                                screen_type = "PIN"
                                break
                            page.wait_for_timeout(500)
                            
                    if screen_type == "PIN":
                        print("[*] Reached PIN screen! Auto-filling PIN...")
                        page.wait_for_timeout(500) # Give React a brief moment to settle
                        page.locator("input:visible").first.click()
                        page.keyboard.type(pin)
                        
                    if not screen_type:
                        print("[-] Could not adapt to screen. Neither OTP (6) nor PIN (4) inputs found.")
                        
                except Exception as e:
                    print(f"[-] Auto-fill encountered an issue, please continue manually. Error: {e}")
                    
            except Exception as e:
                print(f"[-] Auto-fill encountered an issue, please continue manually. ({e})")
        
        # Wait until we have the required tokens (timeout after 60 seconds)
        print("\n[*] Waiting to intercept tokens...")
        for _ in range(60):
            # If silent refresh, we only expect bearer and device_id.
            # If fresh login, we MUST wait for the user to enter their PIN on screen to capture the NKey!
            if is_silent_refresh:
                if bearer_token and device_id:
                    page.wait_for_timeout(1000)
                    print("\n[+] Silent refresh complete! Required tokens intercepted.")
                    break
            else:
                if bearer_token and device_id and user_nkey:
                    page.wait_for_timeout(1000)
                    print("\n[+] Fresh login complete! All tokens including NKey intercepted.")
                    break
                    
            page.wait_for_timeout(1000)
        else:
            print("\n[-] Timeout reached before capturing all tokens. Saving whatever we found...")

        # Extract standard storage state (cookies, localstorage) as a dictionary
        new_state_data = context.storage_state()
        
        result = {
            "state_data": new_state_data,
            "bearer_token": bearer_token,
            "device_id": device_id,
            "user_nkey": user_nkey
        }

        # ONLY save to physical files if run directly via CLI
        if is_standalone:
            with open(state_path, 'w') as f:
                json.dump(new_state_data, f)
            
            if bearer_token:
                set_key(env_path, "GROWW_BEARER_TOKEN", bearer_token)
            if device_id:
                set_key(env_path, "GROWW_DEVICE_ID", device_id)
            if user_nkey:
                set_key(env_path, "GROWW_NKEY", user_nkey)
                
            print("\n[+] Session successfully saved to groww_state.json!")
            print("[+] All API secrets successfully exported to .env!")

        browser.close()
        
        return result

if __name__ == "__main__":
    create_session()
