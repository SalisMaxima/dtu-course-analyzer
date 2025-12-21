"""
Course number discovery script.

Fetches the complete list of DTU course numbers by scraping the search page.
Requires authentication cookie from auth.py.
"""

import os
import sys
import re
from playwright.sync_api import sync_playwright

# Import from our modules
from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger('course_numbers', 'course_numbers.log')

# This URL searches for courses across all schedule groups
SEARCH_URL = "https://kurser.dtu.dk/search?CourseCode=&SearchKeyword=&SchedulePlacement=E1%3BE2%3BE3%3BE4%3BE5%3BE1A%3BE2A%3BE3A%3BE4A%3BE5A%3BE1B%3BE2B%3BE3B%3BE4B%3BE5B%3BE7%3BE&SchedulePlacement=E1%3BE1A%3BE1B&SchedulePlacement=E1A&SchedulePlacement=E1B&SchedulePlacement=E2%3BE2A%3BE2B&SchedulePlacement=E2A&SchedulePlacement=E2B&SchedulePlacement=E3%3BE3A%3BE3B&SchedulePlacement=E3A&SchedulePlacement=E3B&SchedulePlacement=E4%3BE4A%3BE4B&SchedulePlacement=E4A&SchedulePlacement=E4B&SchedulePlacement=E5%3BE5A%3BE5B&SchedulePlacement=E5A&SchedulePlacement=E5B&SchedulePlacement=E7&SchedulePlacement=F1%3BF2%3BF3%3BF4%3BF5%3BF1A%3BF2A%3BF3A%3BF4A%3BF5A%3BF1B%3BF2B%3BF3B%3BF4B%3BF5B%3BF7%3BF&SchedulePlacement=F1%3BF1A%3BF1B&SchedulePlacement=F1A&SchedulePlacement=F1B&SchedulePlacement=F2%3BF2A%3BF2B&SchedulePlacement=F2A&SchedulePlacement=F2B&SchedulePlacement=F3%3BF3A%3BF3B&SchedulePlacement=F3A&SchedulePlacement=F3B&SchedulePlacement=F4%3BF4A%3BF4B&SchedulePlacement=F4A&SchedulePlacement=F4B&SchedulePlacement=F5%3BF5A%3BF5B&SchedulePlacement=F5A&SchedulePlacement=F5B&SchedulePlacement=F7&SchedulePlacement=January&SchedulePlacement=August%3BJuly%3BJune&SchedulePlacement=August&SchedulePlacement=July&SchedulePlacement=June&CourseType=&TeachingLanguage="


def get_course_numbers() -> bool:
    """
    Fetch all DTU course numbers from the search page.

    Requires a valid session cookie from auth.py.
    Saves course numbers to coursenumbers.txt.

    Returns:
        True if successful, False otherwise
    """
    # Read the session cookie
    try:
        with open(config.paths.secret_file, 'r') as file:
            session_id = file.read().strip()
        logger.info(f"Loaded session cookie from {config.paths.secret_file}")
    except FileNotFoundError:
        logger.error(f"{config.paths.secret_file} not found. Run auth.py first.")
        return False

    with sync_playwright() as p:
        logger.info("Launching browser to fetch course numbers...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        # Inject the cookie so we are logged in
        context.add_cookies([{
            "name": "ASP.NET_SessionId",
            "value": session_id,
            "domain": "kurser.dtu.dk",
            "path": "/"
        }])

        page = context.new_page()

        try:
            logger.info("Navigating to search page...")
            page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)

            # Wait for at least one course link to appear to ensure JS has rendered
            try:
                page.wait_for_selector('a[href*="/course/"]', timeout=30000)
            except Exception:
                logger.warning("Timed out waiting for course links. The page might be empty or layout changed.")
                # Take a screenshot if it fails, useful for debugging
                screenshot_path = config.paths.root_dir / "course_search_debug.png"
                page.screenshot(path=str(screenshot_path))
                logger.warning(f"Screenshot saved to {screenshot_path}")

            # Extract all links that look like /course/12345
            logger.info("Extracting course links...")
            links = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href'))
            """)

            course_numbers = set()
            for link in links:
                # Look for the pattern /course/XXXXX (5 digits)
                match = re.search(r'/course/(\d{5})', link)
                if match:
                    course_numbers.add(match.group(1))

            count = len(course_numbers)
            logger.info(f"Found {count} unique courses.")

            if count > 0:
                with open(config.paths.course_numbers_file, 'w') as f:
                    f.write(','.join(sorted(list(course_numbers))))
                logger.info(f"Saved to {config.paths.course_numbers_file}")
                return True
            else:
                logger.error("No courses found. Check 'course_search_debug.png' if generated.")
                return False

        except Exception as e:
            logger.error(f"Error fetching course numbers: {e}")
            return False

        finally:
            browser.close()


def main():
    """Main entry point for course number discovery."""
    success = get_course_numbers()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
