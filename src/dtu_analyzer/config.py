"""Centralized configuration for DTU Course Analyzer.

This module provides a single source of truth for all configuration values,
supporting both environment variables and default values.
"""
from dataclasses import dataclass, field
from pathlib import Path
import os
from typing import Optional


@dataclass
class ScraperConfig:
    """Configuration for web scrapers."""

    # Async scraper settings
    max_concurrent: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT", "2"))
    )
    """Maximum concurrent requests for async scraper (default: 2)"""

    # Threaded scraper settings
    max_workers: int = field(
        default_factory=lambda: int(os.getenv("MAX_WORKERS", "8"))
    )
    """Maximum worker threads for threaded scraper (default: 8)"""

    max_gather_workers: int = field(
        default_factory=lambda: int(os.getenv("MAX_GATHER_WORKERS", "3"))
    )
    """Maximum threads for grade/review fetching per course (default: 3)"""

    # Common settings
    timeout: int = field(
        default_factory=lambda: int(os.getenv("TIMEOUT", "30"))
    )
    """Request timeout in seconds (default: 30)"""

    base_url: str = "http://kurser.dtu.dk"
    """Base URL for DTU course website"""


@dataclass
class PathConfig:
    """Configuration for file paths."""

    # Compute root directory (3 levels up from this file)
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)
    """Project root directory"""

    @property
    def data_dir(self) -> Path:
        """Directory for data files"""
        return self.root_dir / "data"

    @property
    def extension_dir(self) -> Path:
        """Directory for browser extension"""
        return self.root_dir / "extension"

    @property
    def templates_dir(self) -> Path:
        """Directory for HTML templates"""
        return self.root_dir / "templates"

    @property
    def logs_dir(self) -> Path:
        """Directory for log files"""
        return self.root_dir / "logs"

    # File paths - all files now in data/ directory
    @property
    def course_numbers_file(self) -> Path:
        """Path to course numbers file (data/coursenumbers.txt)"""
        return self.data_dir / "coursenumbers.txt"

    @property
    def course_data_file(self) -> Path:
        """Path to scraped course data file (data/coursedic.json)"""
        return self.data_dir / "coursedic.json"

    @property
    def analyzed_data_file(self) -> Path:
        """Path to analyzed data file (data/data.json)"""
        return self.data_dir / "data.json"

    @property
    def secret_file(self) -> Path:
        """Path to session cookie file"""
        return self.root_dir / "secret.txt"

    # Aliases for backward compatibility
    @property
    def template_dir(self) -> Path:
        """Alias for templates_dir (backward compatibility)"""
        return self.templates_dir

    @property
    def data_json_file(self) -> Path:
        """Alias for analyzed_data_file (backward compatibility)"""
        return self.analyzed_data_file


@dataclass
class Config:
    """Main configuration container."""

    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    """Scraper configuration"""

    paths: PathConfig = field(default_factory=PathConfig)
    """Path configuration"""

    # Authentication
    dtu_username: str = field(
        default_factory=lambda: os.getenv("DTU_USERNAME", "")
    )
    """DTU username from environment"""

    dtu_password: str = field(
        default_factory=lambda: os.getenv("DTU_PASSWORD", "")
    )
    """DTU password from environment"""

    # Logging
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    """Logging level (DEBUG, INFO, WARNING, ERROR)"""

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()


# Global config instance - can be imported and used anywhere
config = Config()


# Convenience function for getting paths
def get_data_dir() -> Path:
    """Get the data directory path."""
    return config.paths.data_dir


def get_extension_dir() -> Path:
    """Get the extension directory path."""
    return config.paths.extension_dir
