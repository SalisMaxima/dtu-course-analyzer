"""
Threaded version of the DTU Course Analyzer scraper.

Uses threading for concurrent HTTP requests, with two-level parallelization:
- MAX_WORKERS threads for course processing
- MAX_GATHER_WORKERS threads for grade/review fetching per course

Usage: python -m dtu_analyzer.scrapers.threaded_scraper
"""

import time
import requests
from bs4 import BeautifulSoup
import json
from tqdm import tqdm
import concurrent.futures

# Import from our modules
from ..config import config
from ..utils.logger import get_scraper_logger
from ..parsers.grade_parser import parse_grades
from ..parsers.review_parser import parse_reviews
from ..parsers.base import parse_html

# Configuration from centralized config
MAX_WORKERS = config.scraper.max_workers
MAX_GATHER_WORKERS = config.scraper.max_gather_workers
TIMEOUT = config.scraper.timeout
BASE_URL = config.scraper.base_url

logger = get_scraper_logger()

# Session is initialized lazily when running as main script
session = None


def init_session(cookie: str) -> requests.Session:
    """Initialize and return a configured session."""
    sess = requests.Session()
    sess.cookies.set('ASP.NET_SessionId', cookie)
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    })
    return sess


def respObj(url: str, sess: requests.Session = None) -> str | bool:
    """
    Fetch a URL and return HTML content.

    Args:
        url: The URL to fetch
        sess: Optional session to use (uses global session if not provided)

    Returns:
        HTML content as string, or False on failure
    """
    use_session = sess if sess is not None else session
    if use_session is None:
        logger.error("No session available. Initialize session first.")
        return False

    try:
        r = use_session.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
        logger.warning(f"HTTP {r.status_code} for {url}")
    except requests.Timeout:
        logger.warning(f"Timeout fetching {url}")
    except requests.ConnectionError as e:
        logger.warning(f"Connection error for {url}: {e}")
    except requests.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
    return False


class Course:
    def __init__(self, courseN: str):
        self.courseN = courseN
        self.reviewLinks = []
        self.gradeLinks = []

    def extractGrades(self, url: str) -> dict | bool:
        """
        Extract grade data from a grades page.

        Args:
            url: URL to the grades page

        Returns:
            Dictionary with grade data, or False on failure
        """
        html = respObj(url)
        if not html:
            return False

        # Use the shared parser from parsers module
        data = parse_grades(html, url)
        return data if data else False

    def extractReviews(self, url: str) -> dict | bool:
        """
        Extract review/evaluation data from a reviews page.

        Args:
            url: URL to the reviews page

        Returns:
            Dictionary with review data, or False on failure
        """
        html = respObj(url)
        if not html:
            return False

        # Use the shared parser from parsers module
        data = parse_reviews(html, url)
        return data if data else False

    def gather(self) -> dict | bool:
        """
        Gather all grade and review data for this course.
        Uses ThreadPoolExecutor to parallelize grade/review fetching.

        Returns:
            Dictionary with all course data, or False if no data found
        """
        dic = {}
        tasks = [
            ("grades", self.gradeLinks, self.extractGrades),
            ("reviews", self.reviewLinks, self.extractReviews)
        ]

        foundData = False

        # Use ThreadPoolExecutor to parallelize grade and review fetching
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_GATHER_WORKERS) as executor:
            for name, urls, func in tasks:
                if not urls:
                    continue

                # Submit all URL fetches in parallel
                future_to_url = {executor.submit(func, url): url for url in urls}

                lst = []
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        data = future.result()
                        if data:
                            data["url"] = url
                            lst.append(data)
                    except Exception as e:
                        logger.debug(f"Error fetching {url}: {e}")

                if lst:
                    dic[name] = lst
                    foundData = True

        return dic if foundData else False


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
        soup = BeautifulSoup(html, "lxml")
        h2_tags = soup.find_all('h2')
        if h2_tags:
            content = h2_tags[0].get_text().strip()
            parts = content.split(" ", 1)
            return parts[1] if len(parts) > 1 else content
    except (IndexError, AttributeError) as e:
        logger.debug(f"Could not extract {lang} name for {courseN}: {e}")
    return None


def process_single_course(courseN: str) -> tuple | None:
    """
    Process a single course: fetch and extract all data.

    Args:
        courseN: 5-digit course number

    Returns:
        Tuple of (courseN, data) on success, None on failure
    """
    try:
        course = Course(courseN)

        # Fetch main course page
        overviewResp = respObj(f"{BASE_URL}/course/{courseN}/info")
        if not overviewResp:
            logger.debug(f"Could not fetch overview for {courseN}")
            return None

        # Parse links from overview page
        soup = BeautifulSoup(overviewResp, "lxml")
        for link in soup.find_all('a'):
            href = link.get('href')
            if not href:
                continue
            if "evaluering" in href:
                course.reviewLinks.append(href)
            elif "karakterer" in href:
                course.gradeLinks.append(href)

        # Gather data
        crawl = course.gather()
        if not crawl:
            logger.debug(f"No data found for course {courseN}")
            return None

        # Fetch course names (Danish and English)
        nameResp = respObj(f"{BASE_URL}/course/{courseN}?lang=da-DK")
        if nameResp:
            name_da = parse_course_name(nameResp, courseN, "da")
            if name_da:
                crawl["name"] = name_da

        nameRespEn = respObj(f"{BASE_URL}/course/{courseN}?lang=en-GB")
        if nameRespEn:
            name_en = parse_course_name(nameRespEn, courseN, "en")
            if name_en:
                crawl["name_en"] = name_en

        return (courseN, crawl)

    except Exception as e:
        logger.error(f"Error processing course {courseN}: {e}")
        return None


def main():
    """Main entry point for the scraper."""
    global session

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

    # Initialize session
    session = init_session(key)

    courseDic = {}
    logger.info(f"Starting scrape of {len(courses)} courses using {MAX_WORKERS} threads...")

    # ThreadPoolExecutor handles the parallelism
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_course = {executor.submit(process_single_course, c): c for c in courses}

        # Process as they complete (with progress bar)
        for future in tqdm(concurrent.futures.as_completed(future_to_course), total=len(courses)):
            try:
                result = future.result()
                if result:
                    c_num, c_data = result
                    courseDic[c_num] = c_data
            except Exception as e:
                course = future_to_course[future]
                logger.error(f"Future failed for course {course}: {e}")

    logger.info(f"Scraping finished. Found data for {len(courseDic)} courses.")

    # Save data
    with open(config.paths.course_data_file, 'w') as outfile:
        json.dump(courseDic, outfile)

    elapsed = time.time() - start_time
    logger.info(f"Done! Data saved to {config.paths.course_data_file} in {elapsed:.1f} seconds.")
    return 0


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    exit(main())
