"""Shared pytest fixtures."""

import pytest

import dtu_analyzer.scrapers.async_scraper as async_scraper
import dtu_analyzer.scrapers.threaded_scraper as threaded_scraper


@pytest.fixture(autouse=True)
def fast_pacing(monkeypatch):
    """Disable request pacing and backoff sleeps so tests stay fast."""
    for module in (async_scraper, threaded_scraper):
        monkeypatch.setattr(module, "REQUEST_DELAY_MIN", 0.0)
        monkeypatch.setattr(module, "REQUEST_DELAY_MAX", 0.0)
        monkeypatch.setattr(module, "BACKOFF_BASE", 0.0)
