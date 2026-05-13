"""Capture Shopee session cookies from a real headed browser and save them to the API.

Run this script on the Windows HOST (not inside Docker).

Prerequisites:
    pip install playwright httpx
    playwright install chromium

Usage:
    python tools/capture_shopee_session.py
    python tools/capture_shopee_session.py --api http://localhost:8000
"""
import argparse
import json
import sys
from datetime import datetime, timezone


def _post_session(api_base: str, source_id: str, label: str, cookies: list[dict]) -> dict:
    cookies_json = json.dumps(cookies)
    payload = {
        "source_id": source_id,
        "label": label,
        "cookies_json": cookies_json,
    }

    # Try httpx first, fall back to urllib
    try:
        import httpx
        resp = httpx.post(f"{api_base}/api/sessions", json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except ImportError:
        pass

    import urllib.request
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{api_base}/api/sessions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture Shopee session cookies from a headed browser and save to the Find-Item API."
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="Base URL of the Find-Item API (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    api_base = args.api.rstrip("/")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright is not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    print("Launching Chromium browser...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            locale="th-TH",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print("Navigating to https://shopee.co.th/ ...")
        page.goto("https://shopee.co.th/", timeout=60_000)

        print()
        print("=" * 60)
        print("Browser is open. If Shopee shows a challenge / CAPTCHA,")
        print("solve it. Wait until the Shopee homepage loads normally.")
        print("=" * 60)
        input("Press Enter here when Shopee looks normal...")
        print()

        # Collect cookies where domain contains 'shopee'
        all_cookies = context.cookies()
        shopee_cookies = [c for c in all_cookies if "shopee" in c.get("domain", "")]

        browser.close()

    if not shopee_cookies:
        print("No Shopee cookies captured. Did the page load correctly?")
        sys.exit(1)

    print(f"Captured {len(shopee_cookies)} Shopee cookies.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    label = f"captured-{timestamp}"

    print(f"Saving to API at {api_base} ...")
    try:
        result = _post_session(api_base, "shopee", label, shopee_cookies)
    except Exception as exc:
        print(f"ERROR: Could not reach API at {api_base}")
        print(f"  {exc}")
        print()
        print("Is the Find-Item stack running?  docker compose up -d")
        sys.exit(1)

    session_id = result.get("id", "?")
    print(f"Saved {len(shopee_cookies)} cookies as session id={session_id}.")
    print("Next Shopee scrape will use these cookies automatically.")


if __name__ == "__main__":
    main()
