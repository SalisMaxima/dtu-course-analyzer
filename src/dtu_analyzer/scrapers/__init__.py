"""
Scrapers module for DTU Course Analyzer.

Provides both async and threaded scraper implementations.
"""

from .async_scraper import main as async_main
from .threaded_scraper import main as threaded_main

__all__ = ['async_main', 'threaded_main']
