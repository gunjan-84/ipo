import sys
import json
import base64
import requests
from bs4 import BeautifulSoup
import ddddocr

def get_companies(session):
    url = 'https://ipo.bigshareonline.com/ipo_status.html'
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ipo_status.html: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    select_tag = soup.find('select', id='ddlCompany')
    if not select_tag:
        print("Could not find the company dropdown on the page.")
        return []

    companies = []
    for option in select_tag.find_all('option'):
        val = option.get('value')
        text = option.text.strip()
        if val and text and val != '--Select Company--' and text != '--Select Company--':
            companies.append({'value': val, 'name': text})
    return companies

def get_captcha(session):
    url = 'https://ipo.bigshareonline.com/Captcha.ashx'
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        token = data.get('token') or data.get('Token')
        image_b64 = data.get('image') or data.get('Image')
        
        if image_b64 and image_b64.startswith('data:image/png;base64,'):
            image_b64 = image_b64.replace('data:image/png;base64,', '')
        
        return token, base64.b64decode(image_b64)
    except Exception as e:
        print(f"Error fetching captcha: {e}")
        return None, None

def check_allotment(session, company_id, pan_no, captcha_token, captcha_answer):
    url = 'https://ipo.bigshareonline.com/Data.aspx/FetchIpodetails'
    payload = {
        "Applicationno": "",
        "Company": company_id,
        "SelectionType": "PN",
        "PanNo": pan_no,
        "txtcsdl": "",
        "txtDPID": "",
        "txtClId": "",
        "ddlType": "0",
        "lang": "en",
        "CaptchaToken": captcha_token,
        "CaptchaAnswer": captcha_answer,
        "ResultToken": ""
    }
    
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.8',
        'Content-Type': 'application/json; charset=UTF-8',
        'Origin': 'https://ipo.bigshareonline.com',
        'Referer': 'https://ipo.bigshareonline.com/ipo_status.html',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    try:
        response = session.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error checking allotment: {e}")
        return None

def main():
    session = requests.Session()
    
    print("Fetching company list from Bigshare...")
    companies = get_companies(session)
    if not companies:
        print("Exiting due to missing companies.")
        return

    print("\nAvailable Companies:")
    for idx, comp in enumerate(companies, start=1):
        print(f"{idx}. {comp['name']}")

    while True:
        try:
            choice = input(f"\nSelect a company (1-{len(companies)}): ").strip()
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(companies):
                selected_company = companies[choice_idx]
                break
            else:
                print("Invalid choice, please try again.")
        except ValueError:
            print("Please enter a valid number.")

    pan_no = input("Enter your PAN number: ").strip().upper()
    if not pan_no:
        print("PAN number is required.")
        return

    max_retries = 5
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    for attempt in range(1, max_retries + 1):
        print(f"\nFetching Captcha (Attempt {attempt})...")
        token, image_bytes = get_captcha(session)
        if not token or not image_bytes:
            print("Failed to get captcha.")
            continue
            
        print("Solving Captcha...")
        captcha_text = ocr.classification(image_bytes)
        print(f"Solved Captcha: {captcha_text}")
        
        print("Checking Allotment Status...")
        result = check_allotment(session, selected_company['value'], pan_no, token, captcha_text)
        
        if result and 'd' in result:
            comp_data = result['d']
            status = comp_data.get('Status')
            error_msg = comp_data.get('DPID')
            
            if status == 'NOTFOUND':
                print(f"\nResult: No Record Found for PAN {pan_no} in {selected_company['name']}.")
                break
            elif status == 'CAPTCHA':
                print("Incorrect Captcha. Retrying...")
                continue
            elif error_msg in ["Please Enter Valid Pan No", "Invalid Captcha"]:
                print(f"Error from server: {error_msg}")
                if "Captcha" in error_msg:
                    print("Retrying due to incorrect captcha...")
                    continue
                break
            elif status:
                print("\n=== Allotment Found! ===")
                print(f"Company: {comp_data.get('Name')}")
                print(f"Applied: {comp_data.get('APPLIED')}")
                print(f"Allotted: {comp_data.get('ALLOTED')}")
                # Print all fields dynamically just in case
                for key, val in comp_data.items():
                    if key not in ["__type", "Status", "Message", "MatchCount", "Records", "ResultToken", "Name", "APPLIED", "ALLOTED"] and not key.startswith("H_"):
                        if val:
                            print(f"{key}: {val}")
                break
            else:
                print(f"Server returned unknown status. Full response: {result}")
                if attempt < max_retries:
                    print("Retrying just in case it was a captcha issue...")
                    continue
                break
        else:
            print(f"Unexpected response format: {result}")
            break

if __name__ == '__main__':
    main()
