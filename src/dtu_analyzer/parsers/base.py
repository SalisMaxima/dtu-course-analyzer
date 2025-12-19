"""Base parser with shared functionality for HTML parsing.

This module provides common utilities used by both grade and review parsers.
"""

from bs4 import BeautifulSoup
from typing import Optional
import datetime
from ..utils.logger import get_scraper_logger

logger = get_scraper_logger()
now = datetime.datetime.now()


def remove_whitespace(txt: str) -> str:
    """Remove all whitespace from a string.

    Args:
        txt: Input string

    Returns:
        String with all whitespace removed

    Example:
        >>> remove_whitespace("  hello   world  ")
        'helloworld'
    """
    return " ".join(txt.split()).replace(" ", "")


def parse_year(year_str: str) -> str:
    """Parse year string and handle 2-digit years.

    Converts 2-digit years to 4-digit format using the rule:
    - Years < 50 are assumed to be 2000s (e.g., 24 -> 2024)
    - Years >= 50 are assumed to be 1900s (e.g., 98 -> 1998)

    Args:
        year_str: Year as string (2 or 4 digits)

    Returns:
        4-digit year string

    Example:
        >>> parse_year("24")
        '2024'
        >>> parse_year("98")
        '1998'
        >>> parse_year("2024")
        '2024'
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


def parse_html(html: str, parser: str = 'lxml') -> Optional[BeautifulSoup]:
    """Parse HTML with error handling.

    Args:
        html: HTML content as string
        parser: Parser to use (default: 'lxml' for speed)

    Returns:
        BeautifulSoup object or None if parsing fails
    """
    try:
        return BeautifulSoup(html, parser)
    except Exception as e:
        logger.error(f"Failed to parse HTML: {e}")
        return None


def extract_table_cell_text(cell) -> str:
    """Extract and clean text from a table cell.

    Args:
        cell: BeautifulSoup table cell element

    Returns:
        Cleaned text content
    """
    if cell is None:
        return ""
    return remove_whitespace(cell.text)


def parse_timestamp_from_url(url: str) -> str:
    """Extract and parse timestamp from URL.

    Handles URLs like:
    - /course/01005/karakterer/januar-2024
    - /course/01005/karakterer/Winter-24

    Args:
        url: URL containing timestamp

    Returns:
        Formatted timestamp string (e.g., "januar-2024")
    """
    try:
        timestamp = url.split("/")[-1]
        parts = timestamp.split("-")
        if len(parts) >= 2:
            season = parts[0]
            year = parse_year(parts[-1])
            return f"{season}-{year}"
        return timestamp
    except (IndexError, AttributeError):
        logger.debug(f"Could not parse timestamp from URL: {url}")
        return url.split("/")[-1] if "/" in url else url
