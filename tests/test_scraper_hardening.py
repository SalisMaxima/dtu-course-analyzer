"""
Unit tests for scraper hardening: https normalization, login-page
detection, retry/backoff behavior and pacing configuration.
"""

import pytest
from unittest.mock import Mock
from dtu_analyzer.config import ScraperConfig
from dtu_analyzer.scrapers import async_scraper, threaded_scraper
from dtu_analyzer.scrapers.async_scraper import is_login_page, retry_delay
from dtu_analyzer.scrapers.threaded_scraper import respObj
from dtu_analyzer.scripts.check_for_updates import normalize_grade_href


class TestNormalizeUrl:
    """Both scrapers must fetch absolute https URLs only."""

    @pytest.mark.parametrize("normalize", [async_scraper.normalize_url, threaded_scraper.normalize_url])
    def test_upgrades_http_to_https(self, normalize):
        assert normalize("http://kurser.dtu.dk/course/01005/karakterer/januar-2024") == \
            "https://kurser.dtu.dk/course/01005/karakterer/januar-2024"

    @pytest.mark.parametrize("normalize", [async_scraper.normalize_url, threaded_scraper.normalize_url])
    def test_makes_relative_href_absolute(self, normalize):
        result = normalize("/course/01005/karakterer/januar-2024")
        assert result.startswith("https://kurser.dtu.dk/")
        assert result.endswith("/course/01005/karakterer/januar-2024")

    @pytest.mark.parametrize("normalize", [async_scraper.normalize_url, threaded_scraper.normalize_url])
    def test_keeps_https_unchanged(self, normalize):
        url = "https://kurser.dtu.dk/course/01005/info"
        assert normalize(url) == url

    @pytest.mark.parametrize("normalize", [async_scraper.normalize_url, threaded_scraper.normalize_url])
    def test_preserves_karakterer_http(self, normalize):
        url = "http://karakterer.dtu.dk/Histogram/1/01005/Summer-2024"
        assert normalize(url) == url

    @pytest.mark.parametrize("normalize", [async_scraper.normalize_url, threaded_scraper.normalize_url])
    def test_forces_karakterer_https_to_http(self, normalize):
        url = "https://karakterer.dtu.dk/Histogram/1/01005/Summer-2024"
        assert normalize(url) == "http://karakterer.dtu.dk/Histogram/1/01005/Summer-2024"


class TestIsLoginPage:
    """Expired sessions return HTTP 200 with an ADFS login page."""

    def test_detects_adfs_redirect_url(self):
        assert is_login_page("<html></html>", "https://sts.ait.dtu.dk/adfs/ls/?wa=wsignin1.0")

    def test_detects_login_form_html(self):
        html = '<html><body><form><input id="userNameInput" type="email"></form></body></html>'
        assert is_login_page(html, "https://kurser.dtu.dk/course/01005/info")

    def test_accepts_normal_course_page(self):
        html = "<html><h2>01005 Advanced Engineering Mathematics</h2></html>"
        assert not is_login_page(html, "https://kurser.dtu.dk/course/01005/info")

    def test_handles_empty_html(self):
        assert not is_login_page(None, "https://kurser.dtu.dk/course/01005/info")


class TestRetryDelay:
    """Backoff grows exponentially and honors Retry-After."""

    def test_exponential_growth(self, monkeypatch):
        monkeypatch.setattr(async_scraper, "BACKOFF_BASE", 2.0)
        assert retry_delay(0) == 2.0
        assert retry_delay(1) == 4.0
        assert retry_delay(2) == 8.0

    def test_honors_retry_after_header(self):
        assert retry_delay(0, retry_after="30") == 30.0

    def test_invalid_retry_after_falls_back(self, monkeypatch):
        monkeypatch.setattr(async_scraper, "BACKOFF_BASE", 2.0)
        assert retry_delay(0, retry_after="soon") == 2.0


class TestRespObjRetries:
    """The threaded fetcher retries transient errors with backoff."""

    def _response(self, status, text=""):
        resp = Mock()
        resp.status_code = status
        resp.text = text
        resp.headers = {}
        return resp

    def test_retries_5xx_then_succeeds(self):
        sess = Mock()
        sess.get.side_effect = [self._response(503), self._response(200, "ok")]
        assert respObj("https://kurser.dtu.dk/course/01005/info", sess=sess) == "ok"
        assert sess.get.call_count == 2

    def test_does_not_retry_404(self):
        sess = Mock()
        sess.get.return_value = self._response(404)
        assert respObj("https://kurser.dtu.dk/course/01005/info", sess=sess) is False
        assert sess.get.call_count == 1

    def test_gives_up_after_max_retries(self, monkeypatch):
        monkeypatch.setattr(threaded_scraper, "MAX_RETRIES", 2)
        sess = Mock()
        sess.get.return_value = self._response(429)
        assert respObj("https://kurser.dtu.dk/course/01005/info", sess=sess) is False
        assert sess.get.call_count == 3  # initial attempt + 2 retries


class TestNormalizeGradeHref:
    """Baseline http:// URLs must compare equal to fresh https:// ones."""

    def test_http_and_https_normalize_identically(self):
        http_url = "http://kurser.dtu.dk/course/01005/karakterer/januar-2024"
        https_url = "https://kurser.dtu.dk/course/01005/karakterer/januar-2024"
        assert normalize_grade_href(http_url) == normalize_grade_href(https_url)

    def test_karakterer_host_stays_http(self):
        url = "https://karakterer.dtu.dk/Histogram/1/01005/Summer-2024"
        assert normalize_grade_href(url).startswith("http://karakterer.dtu.dk/")


class TestScraperConfigDefaults:
    """Pacing settings exist with safe defaults."""

    def test_base_url_is_https(self):
        assert ScraperConfig().base_url.startswith("https://")

    def test_pacing_defaults(self):
        cfg = ScraperConfig()
        assert 0 < cfg.request_delay_min <= cfg.request_delay_max
        assert cfg.max_retries >= 1
        assert cfg.backoff_base > 1
