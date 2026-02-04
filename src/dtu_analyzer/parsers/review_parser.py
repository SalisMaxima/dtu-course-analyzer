"""Parser for DTU course review/evaluation data.

Extracts course evaluation survey responses from DTU course review pages.
"""

from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from .base import remove_whitespace, parse_html
from ..utils.logger import get_scraper_logger

logger = get_scraper_logger()


def parse_reviews(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Parse review/evaluation data from HTML content.

    Extracts:
    - Number of participants who completed the survey
    - Timestamp (semester code, e.g., "E23" for Fall 2023)
    - First option label (determines scoring direction)
    - All question responses with vote counts

    Args:
        html: HTML content of reviews page
        url: URL for logging

    Returns:
        Dictionary with review data, or None on failure

    Example return:
        {
            "timestamp": "E23",
            "participants": 120,
            "firstOption": "Helt enig",
            "1": {
                "question": "Jeg synes, undervisningen var god",
                "0": "15",
                "1": "30",
                ...
            },
            ...
        }
    """
    try:
        soup = parse_html(html)
        if soup is None:
            return None

        # Find the public results container
        public_container = soup.find("div", {"id": "CourseResultsPublicContainer"})
        if not public_container:
            logger.debug(f"No public container found on {url}")
            return None

        dic = {}

        # Parse participants count (required field)
        try:
            participants_table = public_container.find("table")
            if not participants_table:
                logger.debug(f"No participants table found on {url}")
                return None

            participants_row = participants_table.find_all("tr")[1]
            participants_cell = participants_row.find_all("td")[0]
            dic["participants"] = int(participants_cell.text)
        except (AttributeError, IndexError, ValueError) as e:
            logger.debug(f"Could not parse review participants for {url}: {e}")
            return None  # Participants is required - fail if missing

        # Parse timestamp (semester code)
        try:
            h2 = public_container.find("h2")
            if h2:
                # Extract last 3 characters (e.g., "Kursusevaluering E23" -> "E23")
                dic["timestamp"] = h2.text[-3:] if len(h2.text) >= 3 else h2.text
            else:
                dic["timestamp"] = ""
        except AttributeError:
            dic["timestamp"] = ""

        # Parse first option label (determines scoring direction)
        # Example: "Helt enig" (strongly agree) vs "Helt uenig" (strongly disagree)
        row_wrapper = soup.find("div", {"class": "RowWrapper"})
        if row_wrapper:
            first_option_label = row_wrapper.find("div", {"class": "FinalEvaluation_Result_OptionColumn"})
            if first_option_label:
                dic["firstOption"] = first_option_label.text

        # Parse all question responses
        containers = soup.find_all("div", {"class": "ResultCourseModelWrapper"})
        for container in containers:
            # Get question number/position (e.g., "1.1", "2.1")
            pos_col = container.find("div", {"class": "FinalEvaluation_Result_QuestionPositionColumn"})
            if not pos_col:
                continue

            question_id = remove_whitespace(pos_col.text)
            dic[question_id] = {}

            # Get question text
            q_text = container.find("div", {"class": "FinalEvaluation_QuestionText"})
            dic[question_id]["question"] = q_text.text if q_text else ""

            # Get vote counts for each option (0-4, representing answer choices)
            for i, row in enumerate(container.find_all("div", {"class": "RowWrapper"})):
                ans_col = row.find("div", {"class": "FinalEvaluation_Result_AnswerCountColumn"})
                if ans_col:
                    span = ans_col.find("span")
                    if span:
                        dic[question_id][i] = remove_whitespace(span.text)

        return dic

    except Exception as e:
        logger.error(f"Unexpected error parsing reviews from {url}: {e}")
        return None
