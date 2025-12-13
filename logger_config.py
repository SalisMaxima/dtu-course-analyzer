"""
Centralized logging configuration for DTU Course Analyzer.
"""

import logging
import sys
from pathlib import Path


def setup_logger(name: str, log_file: str = "scraper.log", level: int = logging.INFO) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.

    Args:
        name: Logger name (usually __name__ from the calling module)
        log_file: Path to log file
        level: Logging level (default INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    # File handler - logs everything
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Console handler - logs INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Pre-configured loggers for each module
def get_scraper_logger() -> logging.Logger:
    return setup_logger('scraper', 'scraper.log')


def get_analyzer_logger() -> logging.Logger:
    return setup_logger('analyzer', 'analyzer.log')


def get_auth_logger() -> logging.Logger:
    return setup_logger('auth', 'auth.log')
