"""HTML parsing modules for DTU course data.

This package provides parsers for:
- Grade distributions (parse_grades)
- Course evaluations (parse_reviews)
- Common utilities (base module)
"""

from .base import (
    remove_whitespace,
    parse_year,
    parse_html,
    extract_table_cell_text,
    parse_timestamp_from_url,
)
from .grade_parser import parse_grades
from .review_parser import parse_reviews

__all__ = [
    # Base utilities
    'remove_whitespace',
    'parse_year',
    'parse_html',
    'extract_table_cell_text',
    'parse_timestamp_from_url',
    # Main parsers
    'parse_grades',
    'parse_reviews',
]
