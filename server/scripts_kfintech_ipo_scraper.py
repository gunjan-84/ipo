"""
Scraper for the IPO dropdown list on https://ipostatus.kfintech.com/

The page is a client-side rendered React app - the IPO list is not
fetched from a separate API, it's rendered directly into the MUI
Select dropdown once the app has mounted. So we drive a real browser
(Playwright/Chromium), open the "Select IPO" dropdown, and read the
<li role="option" data-value="..."> entries straight from the DOM.

Usage:
    pip install playwright
    playwright install chromium
    python kfintech_ipo_scraper.py [-o output.json] [--csv output.csv]
"""

import argparse
import json
import csv
import sys

from playwright.sync_api import sync_playwright

URL = "https://ipostatus.kfintech.com/"


def scrape_ipo_list(headless: bool = True) -> list[dict]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")

        # Open the "Select IPO" dropdown
        page.get_by_role("combobox", name="Select IPO").click()

        # Wait for the option list to render
        page.wait_for_selector('li[role="option"]')

        options = page.eval_on_selector_all(
            'li[role="option"]',
            """els => els.map(el => ({
                name: el.textContent.trim(),
                value: el.getAttribute('data-value')
            }))""",
        )

        browser.close()
        return options


def main():
    parser = argparse.ArgumentParser(description="Scrape KFintech IPO dropdown list")
    parser.add_argument("-o", "--output", default="ipo_list.json", help="JSON output file")
    parser.add_argument("--csv", dest="csv_output", default=None, help="Optional CSV output file")
    parser.add_argument("--show", action="store_true", help="Run browser visibly (non-headless)")
    args = parser.parse_args()

    ipos = scrape_ipo_list(headless=not args.show)

    if not ipos:
        print("No IPO options found - the page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(ipos, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(ipos)} IPOs to {args.output}")

    if args.csv_output:
        with open(args.csv_output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "value"])
            writer.writeheader()
            writer.writerows(ipos)
        print(f"Saved {len(ipos)} IPOs to {args.csv_output}")


if __name__ == "__main__":
    main()
