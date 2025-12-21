"""Parser for DTU course grade data.

Extracts grade distributions and statistics from DTU course grade pages.
"""

from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from .base import remove_whitespace, parse_html, parse_timestamp_from_url
from ..utils.logger import get_scraper_logger

logger = get_scraper_logger()


def parse_grades(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Parse grade data from HTML content.

    Extracts:
    - Individual grade counts (12, 10, 7, 4, 02, 00, -3, passed, not passed, absent, sick)
    - Summary statistics (participants, pass percentage, average grade)
    - Timestamp from URL

    Args:
        html: HTML content of grades page
        url: URL for logging and timestamp extraction

    Returns:
        Dictionary with grade data, or None on failure

    Example return:
        {
            "timestamp": "januar-2024",
            "participants": 150,
            "pass_percentage": 85,
            "avg": 7.2,
            "12": "30",
            "10": "45",
            ...
        }
    """
    try:
        soup = parse_html(html)
        if soup is None:
            return None

        tables = soup.find_all('table')
        if len(tables) < 3:
            logger.debug(f"Not enough tables on {url} (expected 3, found {len(tables)})")
            return None

        dic = {}

        # Parse individual grade counts from table 2 (index 2)
        grade_table = tables[2].find_all('tr')
        for i in range(1, len(grade_table)):
            cells = grade_table[i].find_all('td')
            if len(cells) >= 2:
                name = remove_whitespace(cells[0].text)
                value = remove_whitespace(cells[1].text)
                dic[name] = value

        # Parse timestamp from URL
        dic["timestamp"] = parse_timestamp_from_url(url)

        # Parse summary statistics from table 0 (optional)
        try:
            summary_table = tables[0].find_all('tr')

            # Participants (row 1, column 1)
            if len(summary_table) > 1:
                participants_cell = summary_table[1].find_all('td')[1]
                dic["participants"] = int(remove_whitespace(participants_cell.text))

            # Pass percentage (row 2, column 1) - extract from "XX (YY%)"
            if len(summary_table) > 2:
                pass_cell = summary_table[2].find_all('td')[1]
                pass_text = pass_cell.text.split("(")[1].split("%")[0]
                dic["pass_percentage"] = int(remove_whitespace(pass_text))

            # Average grade (row 3, column 1) - extract before parenthesis
            if len(summary_table) > 3:
                avg_cell = summary_table[3].find_all('td')[1]
                avg_text = avg_cell.text.split(" (")[0]
                dic["avg"] = float(remove_whitespace(avg_text).replace(",", "."))

        except (IndexError, ValueError, AttributeError) as e:
            # Summary statistics are optional - don't fail if they're missing
            logger.debug(f"Could not parse summary statistics for {url}: {e}")

        return dic

    except Exception as e:
        logger.error(f"Unexpected error parsing grades from {url}: {e}")
        return None
