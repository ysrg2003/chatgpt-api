"""
Standalone keepalive script — opens the project's Playwright persistent profile
and visits https://chatgpt.com to let the site refresh session cookies.

Usage (from the project root, with your venv activated):

Windows Task Scheduler or cron can run this daily:
python keepalive.py

"""
import os
import time
import requests

from playwright.sync_api import sync_playwright

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "chrome-profile-real")
SERVER_ENDPOINT = os.getenv("KEEPALIVE_ENDPOINT", "http://localhost:7860/internal/keepalive")
API_KEY = os.getenv("API_KEY", "")


def call_server_keepalive():
    if not API_KEY:
        print("No API key provided; skipping server keepalive call")
        return False
    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        r = requests.post(SERVER_ENDPOINT, headers=headers, timeout=10)
        if 200 <= r.status_code < 300:
            print("Keepalive triggered via server endpoint (status=", r.status_code, ")")
            return True
        print("Server keepalive returned non-2xx:", r.status_code, r.text)
    except Exception as e:
        print("Server keepalive call failed:", e)
    return False


def main():
    # Prefer triggering the running server's internal keepalive (opens a new page in same context).
    if call_server_keepalive():
        print("Server-side keepalive completed")
        return

    # Fallback: open the profile directly (only if server is not running).
    if not os.path.isdir(PROFILE_DIR):
        print(f"Profile directory not found: {PROFILE_DIR}")
        return

    with sync_playwright() as pw:
        browser_ctx = None
        try:
            browser_ctx = pw.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=True,
            )
            page = browser_ctx.new_page()
            page.goto("https://chatgpt.com/", wait_until="networkidle", timeout=60000)
            # Give the site a little time to set/refresh cookies
            time.sleep(5)
            try:
                page.close()
            except Exception:
                pass
        except Exception as e:
            print("Keepalive failed:", e)
        finally:
            try:
                if browser_ctx:
                    browser_ctx.close()
            except Exception:
                pass

    print("Keepalive completed")


if __name__ == "__main__":
    main()
