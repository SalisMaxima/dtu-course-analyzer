"""
DTU authentication module using Playwright.

Automates the DTU ADFS login flow to obtain a session cookie
for accessing authenticated course pages.
"""

import os
import sys
from playwright.sync_api import sync_playwright

# Import from our modules
from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger('auth', 'auth.log')


def authenticate() -> bool:
    """
    Authenticate with DTU and save session cookie.

    Reads credentials from DTU_USERNAME and DTU_PASSWORD environment variables,
    performs automated login via Playwright, and saves the session cookie to secret.txt.

    Returns:
        True if authentication successful, False otherwise
    """
    # Get credentials from environment variables
    username = os.environ.get("DTU_USERNAME")
    password = os.environ.get("DTU_PASSWORD")

    if not username or not password:
        logger.error("DTU_USERNAME and DTU_PASSWORD environment variables must be set")
        return False

    # Use forceLogin to help trigger the redirect
    url = "https://kurser.dtu.dk/?forceLogin=true"

    with sync_playwright() as p:
        logger.info("Launching browser...")
        # Add user_agent to look like a real browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()

        try:
            logger.info(f"Navigating to {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Check if we are already on the login page
            if "sts.ait.dtu.dk" not in page.url and "auth.dtu.dk" not in page.url:
                logger.info("Not on login page yet. Searching for 'Log in' button...")

                # DTU often has a 'Log på' or 'Log in' link in the header
                login_button = page.locator("a", has_text="Log på").or_(
                    page.locator("a", has_text="Log in")
                )

                if login_button.count() > 0 and login_button.first.is_visible():
                    logger.info("Clicking 'Log in' button to trigger redirect...")
                    login_button.first.click()
                else:
                    logger.info("No login button found. Assuming automatic redirect...")

            # Handle ADFS Login Form
            logger.info("Waiting for login fields...")

            # ADFS usually uses 'userNameInput' or 'UserName'
            username_selector = 'input[id="userNameInput"], input[name="UserName"], input[name="username"], input[type="email"]'

            # Wait up to 30s for the redirect to finish and field to appear
            page.wait_for_selector(username_selector, state="visible", timeout=30000)

            logger.info(f"Found username field. Logging in as {username}...")
            page.locator(username_selector).first.fill(username)

            # ADFS password field
            password_selector = 'input[id="passwordInput"], input[name="Password"], input[name="password"], input[type="password"]'
            page.locator(password_selector).first.fill(password)

            logger.info("Submitting login form...")
            submit_selector = 'span[id="submitButton"], button[id="submitButton"], input[type="submit"]'

            # Try clicking submit button, otherwise press Enter
            if page.locator(submit_selector).count() > 0:
                page.click(submit_selector)
            else:
                page.keyboard.press("Enter")

            # Wait for redirect back to kurser.dtu.dk
            logger.info("Waiting for redirect back to course site...")
            page.wait_for_url(
                lambda u: "kurser.dtu.dk" in u and "sts.ait.dtu.dk" not in u,
                timeout=60000
            )

            # Extract Cookie
            cookies = context.cookies()
            session_cookie = next((c for c in cookies if c["name"] == "ASP.NET_SessionId"), None)

            if session_cookie:
                logger.info("SUCCESS: Session cookie found!")
                with open(config.paths.secret_file, "w") as f:
                    f.write(session_cookie["value"])
                logger.info(f"Cookie saved to {config.paths.secret_file}")
                return True
            else:
                logger.error("FAILURE: Login flow finished, but ASP.NET_SessionId cookie was not found")
                logger.debug(f"Cookies present: {[c['name'] for c in cookies]}")
                return False

        except Exception as e:
            logger.error(f"CRITICAL ERROR: {e}")
            # Save screenshot for debugging
            screenshot_path = config.paths.root_dir / "login_error.png"
            page.screenshot(path=str(screenshot_path))
            logger.error(f"Screenshot saved to {screenshot_path}")
            return False

        finally:
            browser.close()


def main():
    """Main entry point for authentication."""
    success = authenticate()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
