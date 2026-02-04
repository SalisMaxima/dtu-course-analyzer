"""
Centralized logging configuration for DTU Course Analyzer.

Provides pre-configured loggers for each module with both file and console output.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    logs_dir: Optional[Path] = None
) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.

    Args:
        name: Logger name (usually __name__ from the calling module)
        log_file: Name of log file (default: {name}.log)
        level: Logging level (default INFO)
        logs_dir: Directory for log files (default: logs/)

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

    # Determine log file path
    if logs_dir is None:
        # Try to use configured logs directory, fall back to current dir
        try:
            from ..config import config
            logs_dir = config.paths.logs_dir
        except ImportError:
            logs_dir = Path(".")

    # Create logs directory if it doesn't exist
    if logs_dir != Path("."):
        logs_dir.mkdir(parents=True, exist_ok=True)

    if log_file is None:
        log_file = f"{name}.log"

    log_path = logs_dir / log_file

    # File handler - logs everything
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
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
    """Get logger for scraper modules."""
    return setup_logger('scraper', 'scraper.log')


def get_analyzer_logger() -> logging.Logger:
    """Get logger for analyzer module."""
    return setup_logger('analyzer', 'analyzer.log')


def get_auth_logger() -> logging.Logger:
    """Get logger for authentication module."""
    return setup_logger('auth', 'auth.log')


def get_validator_logger() -> logging.Logger:
    """Get logger for validator module."""
    return setup_logger('validator', 'validator.log')
