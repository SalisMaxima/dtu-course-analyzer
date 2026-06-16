"""
Async version of the DTU Course Analyzer scraper.

Uses aiohttp for concurrent HTTP requests, providing significant speedup
over the threaded version for I/O-bound operations.

Usage: python -m dtu_analyzer.scrapers.async_scraper
"""

import asyncio
import os
import random
import time
import aiohttp
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm

# Import from our modules
from ..config import config
from ..utils.logger import get_scraper_logger
from ..parsers.grade_parser import parse_grades
from ..parsers.review_parser import parse_reviews
from ..parsers.base import parse_html

# Configuration from centralized config
MAX_CONCURRENT = config.scraper.max_concurrent
TIMEOUT = config.scraper.timeout
BASE_URL = config.scraper.base_url
REQUEST_DELAY_MIN = config.scraper.request_delay_min
REQUEST_DELAY_MAX = config.scraper.request_delay_max
MAX_RETRIES = config.scraper.max_retries
BACKOFF_BASE = config.scraper.backoff_base

# HTTP statuses worth retrying with backoff (rate limiting / transient errors)
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Save a checkpoint after this many completed courses
CHECKPOINT_EVERY = 100

logger = get_scraper_logger()

# Global flags so any task can signal a fatal condition to the main loop
timeout_occurred = False
timeout_url = None
auth_failed = False

# Global pacing gate: enforces a jittered minimum spacing between request
# starts so traffic never bursts, regardless of concurrency
_last_request_time = 0.0
_pace_lock: asyncio.Lock | None = None


class TimeoutException(Exception):
    """Raised when a request times out."""
    pass


def normalize_url(href: str) -> str:
    """
    Make a scraped href absolute and normalize schemes per DTU host.

    Course and evaluation pages are fetched over https so session cookies never
    travel over cleartext. Grade histograms on karakterer.dtu.dk are kept on
    http because that host is historically canonicalized that way in project
    data and update checks.
    """
    url = urljoin(f"{BASE_URL}/", href.strip())
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if host == "karakterer.dtu.dk":
        return "http://" + url.split("://", 1)[1]
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url


def is_login_page(html: str | None, final_url: str) -> bool:
    """
    Detect an ADFS/login page served with HTTP 200 (expired session).

    DTU does not return 401/403 when the session cookie expires - it
    redirects to the ADFS login form, which would otherwise be parsed as
    "no data" and silently skipped for every remaining course.
    """
    url_lower = (final_url or "").lower()
    if "adfs" in url_lower or "/login" in url_lower or "sts." in url_lower:
        return True
    if html:
        head = html[:5000]
        if 'id="userNameInput"' in head or 'name="UserName"' in head:
            return True
    return False


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    """Exponential backoff delay, honoring a numeric Retry-After header."""
    if retry_after:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass
    return BACKOFF_BASE ** (attempt + 1)


async def pace_request():
    """
    Wait so consecutive request starts are spaced by a random jitter.

    A shared lock makes the spacing global across all concurrent tasks,
    which keeps the traffic profile smooth and human-paced.
    """
    global _last_request_time, _pace_lock
    if _pace_lock is None:
        _pace_lock = asyncio.Lock()
    async with _pace_lock:
        spacing = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
        wait = _last_request_time + spacing - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()


async def fetch_url(session: aiohttp.ClientSession, url: str) -> str | None:
    """
    Fetch a URL asynchronously and return HTML content.

    Retries with exponential backoff on timeouts, 429 and 5xx responses.
    Sets the global auth_failed flag if a login page is returned.

    Args:
        session: aiohttp ClientSession
        url: The URL to fetch

    Returns:
        HTML content as string, or None on failure

    Raises:
        TimeoutException: If the request still times out after all retries
    """
    global timeout_occurred, timeout_url, auth_failed

    for attempt in range(MAX_RETRIES + 1):
        # Stop queuing requests once another task hit a fatal condition
        if timeout_occurred or auth_failed:
            return None

        await pace_request()

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
                if response.status == 200:
                    html = await response.text()
                    if is_login_page(html, str(response.url)):
                        auth_failed = True
                        logger.error(f"Session expired: login page returned for {url}")
                        return None
                    return html

                if response.status in RETRY_STATUSES and attempt < MAX_RETRIES:
                    delay = retry_delay(attempt, response.headers.get("Retry-After"))
                    logger.warning(
                        f"HTTP {response.status} for {url}, retrying in {delay:.0f}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.warning(f"HTTP {response.status} for {url}")
                return None
        except asyncio.TimeoutError:
            if attempt < MAX_RETRIES:
                delay = retry_delay(attempt)
                logger.warning(
                    f"Timeout for {url}, retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                continue
            timeout_occurred = True
            timeout_url = url
            logger.error(f"TIMEOUT after {MAX_RETRIES} retries: {url}")
            raise TimeoutException(f"Timeout fetching {url}")
        except aiohttp.ClientError as e:
            if attempt < MAX_RETRIES:
                delay = retry_delay(attempt)
                logger.warning(f"Client error for {url}: {e}, retrying in {delay:.0f}s")
                await asyncio.sleep(delay)
                continue
            logger.warning(f"Client error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
    return None


def parse_course_name(html: str, courseN: str, lang: str = "da") -> str | None:
    """
    Parse course name from HTML content.

    Args:
        html: HTML content of course page
        courseN: Course number for logging
        lang: Language code for logging

    Returns:
        Course name string, or None on failure
    """
    try:
        soup = BeautifulSoup(html, "lxml")  # Use fast C-based parser (5-10x faster than html.parser)
        h2_tags = soup.find_all('h2')
        if h2_tags:
            content = h2_tags[0].get_text().strip()
            parts = content.split(" ", 1)
            return parts[1] if len(parts) > 1 else content
    except (IndexError, AttributeError) as e:
        logger.debug(f"Could not extract {lang} name for {courseN}: {e}")
    return None


async def process_single_course(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    courseN: str
) -> tuple | None:
    """
    Process a single course asynchronously: fetch and extract all data.

    Args:
        session: aiohttp ClientSession
        semaphore: Semaphore to limit concurrent course processing
        courseN: 5-digit course number

    Returns:
        Tuple of (courseN, data) on success, None on failure
    """
    async with semaphore:
        try:
            # Fetch main course page to get links
            overview_html = await fetch_url(session, f"{BASE_URL}/course/{courseN}/info")
            if not overview_html:
                logger.debug(f"Could not fetch overview for {courseN}")
                return None

            # Parse links from overview page
            soup = BeautifulSoup(overview_html, "lxml")
            review_links = []
            grade_links = []

            for link in soup.find_all('a'):
                href = link.get('href')
                if not href:
                    continue
                # Normalize: absolute URL, https-only (cookie must stay encrypted)
                if "evaluering" in href:
                    review_links.append(normalize_url(href))
                elif "karakterer" in href:
                    grade_links.append(normalize_url(href))

            # Fetch all grade and review pages concurrently
            grade_tasks = [fetch_url(session, url) for url in grade_links]
            review_tasks = [fetch_url(session, url) for url in review_links]

            # Also fetch course names (Danish and English) concurrently
            # Must explicitly set lang parameter - default may be English
            name_da_task = fetch_url(session, f"{BASE_URL}/course/{courseN}?lang=da-DK")
            name_en_task = fetch_url(session, f"{BASE_URL}/course/{courseN}?lang=en-GB")

            # Await all tasks
            all_results = await asyncio.gather(
                *grade_tasks,
                *review_tasks,
                name_da_task,
                name_en_task,
                return_exceptions=True
            )

            # Split results
            num_grades = len(grade_links)
            num_reviews = len(review_links)

            grade_htmls = all_results[:num_grades]
            review_htmls = all_results[num_grades:num_grades + num_reviews]
            name_da_html = all_results[-2]
            name_en_html = all_results[-1]

            # Parse grades
            crawl = {}
            grades_list = []
            for html, url in zip(grade_htmls, grade_links):
                if html and not isinstance(html, Exception):
                    data = parse_grades(html, url)
                    if data:
                        data["url"] = url
                        grades_list.append(data)

            if grades_list:
                crawl["grades"] = grades_list

            # Parse reviews
            reviews_list = []
            for html, url in zip(review_htmls, review_links):
                if html and not isinstance(html, Exception):
                    data = parse_reviews(html, url)
                    if data:
                        data["url"] = url
                        reviews_list.append(data)

            if reviews_list:
                crawl["reviews"] = reviews_list

            # If no data found, return None
            if not crawl:
                logger.debug(f"No data found for course {courseN}")
                return None

            # Parse course names
            if name_da_html and not isinstance(name_da_html, Exception):
                name_da = parse_course_name(name_da_html, courseN, "da")
                if name_da:
                    crawl["name"] = name_da

            if name_en_html and not isinstance(name_en_html, Exception):
                name_en = parse_course_name(name_en_html, courseN, "en")
                if name_en:
                    crawl["name_en"] = name_en

            return (courseN, crawl)

        except Exception as e:
            logger.error(f"Error processing course {courseN}: {e}")
            return None


async def main_async():
    """Async main entry point for the scraper."""
    start_time = time.time()

    # Load Course Numbers
    try:
        with open(config.paths.course_numbers_file, 'r') as file:
            courses = file.read().split(",")
        logger.info(f"Loaded {len(courses)} course numbers from {config.paths.course_numbers_file}")
    except FileNotFoundError:
        logger.error(f"{config.paths.course_numbers_file} not found. Run getCourseNumbers.py first.")
        return 1

    # Load Session Cookie
    try:
        with open(config.paths.secret_file, 'r') as file:
            key = file.read().strip()
        logger.info(f"Session cookie loaded from {config.paths.secret_file}")
    except FileNotFoundError:
        logger.error(f"{config.paths.secret_file} not found. Run auth.py first.")
        return 1

    # Checkpoint/resume: a failed run keeps its progress so it never has to
    # re-request everything (less load on DTU, less flagging risk)
    partial_file = config.paths.course_data_file.with_name("coursedic.partial.json")
    courseDic = {}
    if os.getenv("RESUME", "0") == "1" and partial_file.exists():
        try:
            with open(partial_file, 'r') as file:
                courseDic = json.load(file)
            total_before = len(courses)
            courses = [c for c in courses if c not in courseDic]
            logger.info(
                f"Resuming: {len(courseDic)} courses already scraped, "
                f"{len(courses)} of {total_before} remaining"
            )
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load checkpoint, starting fresh: {e}")
            courseDic = {}

    def save_checkpoint():
        try:
            with open(partial_file, 'w') as outfile:
                json.dump(courseDic, outfile)
            logger.info(f"Checkpoint: {len(courseDic)} courses saved to {partial_file}")
        except IOError as e:
            logger.warning(f"Failed to write checkpoint: {e}")

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # Configure aiohttp session
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    cookies = {'ASP.NET_SessionId': key}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept-Encoding': 'gzip, deflate'  # Request compressed responses (30-50% bandwidth reduction)
    }

    logger.info(f"Starting async scrape of {len(courses)} courses with {MAX_CONCURRENT} concurrent requests...")

    async with aiohttp.ClientSession(connector=connector, cookies=cookies, headers=headers) as session:
        # Create tasks for all courses (real tasks so they can be cancelled on abort)
        tasks = [asyncio.ensure_future(process_single_course(session, semaphore, c)) for c in courses]

        def cancel_pending():
            for task in tasks:
                if not task.done():
                    task.cancel()

        completed = 0

        # Process with progress bar
        try:
            for coro in tqdm.as_completed(tasks, total=len(courses)):
                # First record the completed task yielded by as_completed. A
                # fatal flag may have been set concurrently by another task,
                # but this result is already available and should be included
                # in the checkpoint before aborting.
                result = await coro
                completed += 1
                if result:
                    c_num, c_data = result
                    courseDic[c_num] = c_data
                if completed % CHECKPOINT_EVERY == 0:
                    save_checkpoint()

                # Then stop if another task signaled a fatal condition.
                if timeout_occurred:
                    logger.error(f"Stopping due to timeout on: {timeout_url}")
                    logger.error("FAILED: Server is rate-limiting or overloaded. Try reducing MAX_CONCURRENT.")
                    cancel_pending()
                    save_checkpoint()
                    logger.error("Partial progress saved. Re-run with RESUME=1 to continue.")
                    return 1
                if auth_failed:
                    logger.error("FAILED: Session expired. Re-run dtu-auth, then RESUME=1 to continue.")
                    cancel_pending()
                    save_checkpoint()
                    return 1
        except (TimeoutException, asyncio.CancelledError, KeyboardInterrupt) as e:
            logger.error(f"FAILED: {e}")
            logger.error("Server is rate-limiting or overloaded. Try reducing MAX_CONCURRENT.")
            cancel_pending()
            save_checkpoint()
            logger.error("Partial progress saved. Re-run with RESUME=1 to continue.")
            return 1
        except Exception as e:
            cancel_pending()
            save_checkpoint()
            if timeout_occurred:
                logger.error(f"FAILED: Timeout occurred on {timeout_url}")
                logger.error("Server is rate-limiting or overloaded. Try reducing MAX_CONCURRENT.")
                return 1
            logger.error(f"Task failed: {e}")
            logger.error("Partial progress saved. Re-run with RESUME=1 to continue.")
            return 1

    # Flags may have been set by the last tasks after the loop drained
    if timeout_occurred or auth_failed:
        save_checkpoint()
        logger.error("FAILED near the end of the run. Partial progress saved; re-run with RESUME=1.")
        return 1

    logger.info(f"Scraping finished. Found data for {len(courseDic)} courses.")

    # Save data
    with open(config.paths.course_data_file, 'w') as outfile:
        json.dump(courseDic, outfile)

    # Successful complete run - the checkpoint is no longer needed
    try:
        partial_file.unlink(missing_ok=True)
    except IOError as e:
        logger.warning(f"Could not remove checkpoint file: {e}")

    elapsed = time.time() - start_time
    logger.info(f"Done! Data saved to {config.paths.course_data_file} in {elapsed:.1f} seconds.")
    return 0


def main():
    """Sync wrapper for the async main function."""
    return asyncio.run(main_async())


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    exit(main())
