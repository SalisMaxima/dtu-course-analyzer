import time
import requests
from bs4 import BeautifulSoup
import json
import datetime
from tqdm import tqdm
import concurrent.futures
from logger_config import get_scraper_logger

# --- CONFIGURATION ---
MAX_WORKERS = 8  # Number of parallel threads. Don't go too high (e.g. >20) to avoid getting blocked.
TIMEOUT = 30     # Seconds to wait for a page before giving up
BASE_URL = "http://kurser.dtu.dk"
# ---------------------

logger = get_scraper_logger()
now = datetime.datetime.now()

# Session is initialized lazily when running as main script
session = None

gradeHTMLNames = ["Ej m&#248;dt", "Syg", "Best&#229;et", "Ikke best&#229;et", "-3", "00", "02", "4", "7", "10", "12"]
grades = ["absent", "sick", "p", "np", "-3", "00", "02", "4", "7", "10", "12"]


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
            # Handle 2-digit year: assume 2000s for < 50, 1900s otherwise
            if year < 50:
                return str(2000 + year)
            else:
                return str(1900 + year)
        elif year > now.year + 2:
            # Sanity check: if year is too far in future, might be data error
            logger.warning(f"Suspicious year value: {year_str}")
        return year_str
    except ValueError:
        logger.warning(f"Invalid year format: {year_str}")
        return year_str


class Course:
    def __init__(self, courseN: str):
        self.courseN = courseN
        self.dic = {grade: 0 for grade in grades}
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

        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table')
            if len(tables) < 3:
                logger.debug(f"Not enough tables on {url}")
                return False

            # Parse individual grade counts
            obj = tables[2].find_all('tr')
            dic = {}
            for i in range(1, len(obj)):
                cells = obj[i].find_all('td')
                if len(cells) >= 2:
                    name = removeWhitespace(cells[0].text)
                    val = removeWhitespace(cells[1].text)
                    dic[name] = val

            # Parse timestamp
            timestamp = url.split("/")[-1]
            parts = timestamp.split("-")
            if len(parts) >= 2:
                season = parts[0]
                year = parse_year(parts[-1])
                dic["timestamp"] = f"{season}-{year}"
            else:
                dic["timestamp"] = timestamp

            # Parse summary statistics (these may not exist for all courses)
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
            return False

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

        try:
            soup = BeautifulSoup(html, 'html.parser')
            publicContainer = soup.find("div", {"id": "CourseResultsPublicContainer"})

            if not publicContainer:
                logger.debug(f"No public container found on {url}")
                return False

            dic = {}

            # Parse participants count
            try:
                participants_table = publicContainer.find("table")
                dic["participants"] = int(participants_table.find_all("tr")[1].find_all("td")[0].text)
            except (AttributeError, IndexError, ValueError) as e:
                logger.debug(f"Could not parse review participants for {url}: {e}")
                return False

            # Parse timestamp
            try:
                h2 = publicContainer.find("h2")
                dic["timestamp"] = h2.text[-3:] if h2 else ""
            except AttributeError:
                dic["timestamp"] = ""

            # Parse first option label (determines scoring direction)
            row_wrapper = soup.find("div", {"class": "RowWrapper"})
            if row_wrapper:
                firstOptionLabel = row_wrapper.find("div", {"class": "FinalEvaluation_Result_OptionColumn"})
                if firstOptionLabel:
                    dic["firstOption"] = firstOptionLabel.text

            # Parse all question responses
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
            return False

    def gather(self) -> dict | bool:
        """
        Gather all grade and review data for this course.

        Returns:
            Dictionary with all course data, or False if no data found
        """
        dic = {}
        tasks = [
            ("grades", self.gradeLinks, self.extractGrades),
            ("reviews", self.reviewLinks, self.extractReviews)
        ]

        foundData = False
        for name, urls, func in tasks:
            lst = []
            for link in urls:
                data = func(link)
                if data:
                    data["url"] = link
                    lst.append(data)

            if lst:
                dic[name] = lst
                foundData = True

        return dic if foundData else False


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
        soup = BeautifulSoup(overviewResp, "html.parser")
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

        # Fetch course name (Danish - must explicitly set lang parameter)
        nameResp = respObj(f"{BASE_URL}/course/{courseN}?lang=da-DK")
        if nameResp:
            nameSoup = BeautifulSoup(nameResp, "html.parser")
            h2_tags = nameSoup.find_all('h2')
            if h2_tags:
                try:
                    content = h2_tags[0].get_text().strip()
                    parts = content.split(" ", 1)
                    crawl["name"] = parts[1] if len(parts) > 1 else content
                except (IndexError, AttributeError) as e:
                    logger.debug(f"Could not extract Danish name for {courseN}: {e}")

        # Fetch course name (English)
        nameRespEn = respObj(f"{BASE_URL}/course/{courseN}?lang=en-GB")
        if nameRespEn:
            nameSoupEn = BeautifulSoup(nameRespEn, "html.parser")
            h2_tags_en = nameSoupEn.find_all('h2')
            if h2_tags_en:
                try:
                    content_en = h2_tags_en[0].get_text().strip()
                    parts_en = content_en.split(" ", 1)
                    crawl["name_en"] = parts_en[1] if len(parts_en) > 1 else content_en
                except (IndexError, AttributeError) as e:
                    logger.debug(f"Could not extract English name for {courseN}: {e}")

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
    with open('coursedic.json', 'w') as outfile:
        json.dump(courseDic, outfile)

    elapsed = time.time() - start_time
    logger.info(f"Done! Data saved to coursedic.json in {elapsed:.1f} seconds.")
    return 0


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    exit(main())
