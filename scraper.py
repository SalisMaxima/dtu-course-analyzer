"""
Backward compatibility wrapper for the threaded scraper.

This file maintains backward compatibility with existing scripts and workflows.
The actual implementation has been moved to src/dtu_analyzer/scrapers/threaded_scraper.py

Usage: python scraper.py
"""

from src.dtu_analyzer.scrapers.threaded_scraper import main

if __name__ == "__main__":
    exit(main())
