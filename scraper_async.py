"""
Backward compatibility wrapper for the async scraper.

This file maintains backward compatibility with existing scripts and workflows.
The actual implementation has been moved to src/dtu_analyzer/scrapers/async_scraper.py

Usage: python scraper_async.py
"""

from src.dtu_analyzer.scrapers.async_scraper import main

if __name__ == "__main__":
    exit(main())
