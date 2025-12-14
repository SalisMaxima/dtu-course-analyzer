"""
Async version of the DTU Course Analyzer scraper.

Uses aiohttp for concurrent HTTP requests, providing significant speedup
over the threaded version for I/O-bound operations.

Usage: python scraper_async.py
"""

import asyncio
import time
import aiohttp
from bs4 import BeautifulSoup
import json
import datetime
from tqdm.asyncio import tqdm
from logger_config import get_scraper_logger

# --- CONFIGURATION ---
MAX_CONCURRENT = 5  # Number of concurrent requests. Keep reasonable to avoid rate limiting.
TIMEOUT = 30         # Seconds to wait for a page before giving up
BASE_URL = "http://kurser.dtu.dk"
# ---------------------

logger = get_scraper_logger()
now = datetime.datetime.now()

# Global flag to track if a timeout has occurred
timeout_occurred = False
timeout_url = None

gradeHTMLNames = ["Ej m&#248;dt", "Syg", "Best&#229;et", "Ikke best&#229;et", "-3", "00", "02", "4", "7", "10", "12"]
grades = ["absent", "sick", "p", "np", "-3", "00", "02", "4", "7", "10", "12"]


class TimeoutException(Exception):
    """Raised when a request times out."""
    pass


def removeWhitespace(txt: str) -> str:
    """Remove all whitespace from a string."""
    return " ".join(txt.split()).replace(" ", "")


def parse_year(year_str: str) -> str:
    """
    Parse year string and handle 2-digit years.

    Args:
        year_str: Year as string (2 or 4 digits)

    Returns:
        4-digit year string
    """
    try:
        year = int(year_str)
        if len(year_str) == 2:
            if year < 50:
                return str(2000 + year)
            else:
                return str(1900 + year)
        elif year > now.year + 2:
            logger.warning(f"Suspicious year value: {year_str}")
        return year_str
    except ValueError:
        logger.warning(f"Invalid year format: {year_str}")
        return year_str


async def fetch_url(session: aiohttp.ClientSession, url: str) -> str | None:
    """
    Fetch a URL asynchronously and return HTML content.

    Args:
        session: aiohttp ClientSession
        url: The URL to fetch

    Returns:
        HTML content as string, or None on failure

    Raises:
        TimeoutException: If the request times out
    """
    global timeout_occurred, timeout_url

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as response:
            if response.status == 200:
                return await response.text()
            logger.warning(f"HTTP {response.status} for {url}")
    except asyncio.TimeoutError:
        timeout_occurred = True
        timeout_url = url
        logger.error(f"TIMEOUT: {url}")
        raise TimeoutException(f"Timeout fetching {url}")
    except aiohttp.ClientError as e:
        logger.warning(f"Client error for {url}: {e}")
    except Exception as e:
        logger.error(f"Request failed for {url}: {e}")
    return None


def parse_grades(html: str, url: str) -> dict | None:
    """
    Parse grade data from HTML content.

    Args:
        html: HTML content of grades page
        url: URL for logging and timestamp extraction

    Returns:
        Dictionary with grade data, or None on failure
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        if len(tables) < 3:
            logger.debug(f"Not enough tables on {url}")
            return None

        obj = tables[2].find_all('tr')
        dic = {}
        for i in range(1, len(obj)):
            cells = obj[i].find_all('td')
            if len(cells) >= 2:
                name = removeWhitespace(cells[0].text)
                val = removeWhitespace(cells[1].text)
                dic[name] = val

        timestamp = url.split("/")[-1]
        parts = timestamp.split("-")
        if len(parts) >= 2:
            season = parts[0]
            year = parse_year(parts[-1])
            dic["timestamp"] = f"{season}-{year}"
        else:
            dic["timestamp"] = timestamp

        try:
            summary_table = tables[0].find_all('tr')
            participants_cell = summary_table[1].find_all('td')[1]
            dic["participants"] = int(removeWhitespace(participants_cell.text))
        except (IndexError, ValueError) as e:
            logger.debug(f"Could not parse participants for {url}: {e}")

        try:
            pass_cell = summary_table[2].find_all('td')[1]
            pass_text = pass_cell.text.split("(")[1].split("%")[0]
            dic["pass_percentage"] = int(removeWhitespace(pass_text))
        except (IndexError, ValueError) as e:
            logger.debug(f"Could not parse pass percentage for {url}: {e}")

        try:
            avg_cell = summary_table[3].find_all('td')[1]
            avg_text = avg_cell.text.split(" (")[0]
            dic["avg"] = float(removeWhitespace(avg_text).replace(",", "."))
        except (IndexError, ValueError) as e:
            logger.debug(f"Could not parse average for {url}: {e}")

        return dic

    except Exception as e:
        logger.error(f"Unexpected error parsing grades from {url}: {e}")
        return None


def parse_reviews(html: str, url: str) -> dict | None:
    """
    Parse review/evaluation data from HTML content.

    Args:
        html: HTML content of reviews page
        url: URL for logging

    Returns:
        Dictionary with review data, or None on failure
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        publicContainer = soup.find("div", {"id": "CourseResultsPublicContainer"})

        if not publicContainer:
            logger.debug(f"No public container found on {url}")
            return None

        dic = {}

        try:
            participants_table = publicContainer.find("table")
            dic["participants"] = int(participants_table.find_all("tr")[1].find_all("td")[0].text)
        except (AttributeError, IndexError, ValueError) as e:
            logger.debug(f"Could not parse review participants for {url}: {e}")
            return None

        try:
            h2 = publicContainer.find("h2")
            dic["timestamp"] = h2.text[-3:] if h2 else ""
        except AttributeError:
            dic["timestamp"] = ""

        row_wrapper = soup.find("div", {"class": "RowWrapper"})
        if row_wrapper:
            firstOptionLabel = row_wrapper.find("div", {"class": "FinalEvaluation_Result_OptionColumn"})
            if firstOptionLabel:
                dic["firstOption"] = firstOptionLabel.text

        containers = soup.find_all("div", {"class": "ResultCourseModelWrapper"})
        for container in containers:
            pos_col = container.find("div", {"class": "FinalEvaluation_Result_QuestionPositionColumn"})
            if not pos_col:
                continue

            name = removeWhitespace(pos_col.text)
            dic[name] = {}

            q_text = container.find("div", {"class": "FinalEvaluation_QuestionText"})
            dic[name]["question"] = q_text.text if q_text else ""

            for i, row in enumerate(container.find_all("div", {"class": "RowWrapper"})):
                ans_col = row.find("div", {"class": "FinalEvaluation_Result_AnswerCountColumn"})
                if ans_col:
                    span = ans_col.find("span")
                    if span:
                        dic[name][i] = removeWhitespace(span.text)

        return dic

    except Exception as e:
        logger.error(f"Unexpected error parsing reviews from {url}: {e}")
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
        soup = BeautifulSoup(html, "html.parser")
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
        semaphore: Semaphore to limit concurrent requests
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
            soup = BeautifulSoup(overview_html, "html.parser")
            review_links = []
            grade_links = []

            for link in soup.find_all('a'):
                href = link.get('href')
                if not href:
                    continue
                if "evaluering" in href:
                    review_links.append(href)
                elif "karakterer" in href:
                    grade_links.append(href)

            # Fetch all grade and review pages concurrently
            grade_tasks = [fetch_url(session, url) for url in grade_links]
            review_tasks = [fetch_url(session, url) for url in review_links]

            # Also fetch course names (Danish and English) concurrently
            name_da_task = fetch_url(session, f"{BASE_URL}/course/{courseN}")
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
        with open("coursenumbers.txt", 'r') as file:
            courses = file.read().split(",")
        logger.info(f"Loaded {len(courses)} course numbers from coursenumbers.txt")
    except FileNotFoundError:
        logger.error("coursenumbers.txt not found. Run getCourseNumbers.py first.")
        return 1

    # Load Session Cookie
    try:
        with open("secret.txt", 'r') as file:
            key = file.read().strip()
        logger.info("Session cookie loaded from secret.txt")
    except FileNotFoundError:
        logger.error("secret.txt not found. Run auth.py first.")
        return 1

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # Configure aiohttp session
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)
    cookies = {'ASP.NET_SessionId': key}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    courseDic = {}
    logger.info(f"Starting async scrape of {len(courses)} courses with {MAX_CONCURRENT} concurrent requests...")

    async with aiohttp.ClientSession(connector=connector, cookies=cookies, headers=headers) as session:
        # Create tasks for all courses
        tasks = [process_single_course(session, semaphore, c) for c in courses]

        # Process with progress bar
        try:
            for coro in tqdm.as_completed(tasks, total=len(courses)):
                # Check if timeout occurred in another task
                if timeout_occurred:
                    logger.error(f"Stopping due to timeout on: {timeout_url}")
                    logger.error("FAILED: Server is rate-limiting or overloaded. Try reducing MAX_CONCURRENT.")
                    return 1

                result = await coro
                if result:
                    c_num, c_data = result
                    courseDic[c_num] = c_data
        except TimeoutException as e:
            logger.error(f"FAILED: {e}")
            logger.error("Server is rate-limiting or overloaded. Try reducing MAX_CONCURRENT.")
            return 1
        except Exception as e:
            if timeout_occurred:
                logger.error(f"FAILED: Timeout occurred on {timeout_url}")
                logger.error("Server is rate-limiting or overloaded. Try reducing MAX_CONCURRENT.")
                return 1
            logger.error(f"Task failed: {e}")

    logger.info(f"Scraping finished. Found data for {len(courseDic)} courses.")

    # Save data
    with open('coursedic.json', 'w') as outfile:
        json.dump(courseDic, outfile)

    elapsed = time.time() - start_time
    logger.info(f"Done! Data saved to coursedic.json in {elapsed:.1f} seconds.")
    return 0


def main():
    """Sync wrapper for the async main function."""
    return asyncio.run(main_async())


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    exit(main())
