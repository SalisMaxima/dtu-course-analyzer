"""
Unit tests for the DTU Course Analyzer scraper module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dtu_analyzer.scrapers.threaded_scraper import (
    Course,
    init_session,
    respObj,
)
from dtu_analyzer.parsers.base import (
    remove_whitespace,
    parse_year,
)


class TestRemoveWhitespace:
    """Tests for the remove_whitespace function."""

    def test_removes_spaces(self):
        assert remove_whitespace("hello world") == "helloworld"

    def test_removes_tabs_and_newlines(self):
        assert remove_whitespace("hello\t\nworld") == "helloworld"

    def test_handles_empty_string(self):
        assert remove_whitespace("") == ""

    def test_handles_only_whitespace(self):
        assert remove_whitespace("   \t\n   ") == ""

    def test_preserves_non_whitespace(self):
        assert remove_whitespace("abc123") == "abc123"


class TestParseYear:
    """Tests for the parse_year function."""

    def test_two_digit_year_2000s(self):
        assert parse_year("24") == "2024"
        assert parse_year("00") == "2000"
        assert parse_year("49") == "2049"

    def test_two_digit_year_1900s(self):
        assert parse_year("50") == "1950"
        assert parse_year("99") == "1999"

    def test_four_digit_year(self):
        assert parse_year("2024") == "2024"
        assert parse_year("2023") == "2023"

    def test_invalid_year_returns_original(self):
        assert parse_year("abc") == "abc"
        assert parse_year("") == ""


class TestInitSession:
    """Tests for the init_session function."""

    def test_creates_session_with_cookie(self):
        session = init_session("test_cookie_123")
        assert session is not None
        assert "ASP.NET_SessionId" in session.cookies.keys()

    def test_sets_user_agent(self):
        session = init_session("test_cookie")
        assert "User-Agent" in session.headers
        assert "Chrome" in session.headers["User-Agent"]


class TestCourseClass:
    """Tests for the Course class."""

    def test_init_creates_empty_links(self):
        course = Course("12345")
        assert course.courseN == "12345"
        assert course.reviewLinks == []
        assert course.gradeLinks == []


class TestRespObj:
    """Tests for the respObj function."""

    def test_returns_false_when_no_session(self):
        # respObj should return False if no session is provided and global is None
        result = respObj("http://example.com", sess=None)
        # Since global session is None, it should return False
        assert result is False

    def test_returns_text_on_success(self):
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>content</html>"
        mock_session.get.return_value = mock_response

        result = respObj("http://example.com", sess=mock_session)

        assert result == "<html>content</html>"

    def test_returns_false_on_non_200(self):
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response

        result = respObj("http://example.com", sess=mock_session)

        assert result is False

    def test_returns_false_on_timeout(self):
        import requests
        mock_session = Mock()
        mock_session.get.side_effect = requests.Timeout()

        result = respObj("http://example.com", sess=mock_session)

        assert result is False

    def test_returns_false_on_connection_error(self):
        import requests
        mock_session = Mock()
        mock_session.get.side_effect = requests.ConnectionError()

        result = respObj("http://example.com", sess=mock_session)

        assert result is False


class TestExtractGrades:
    """Tests for the Course.extractGrades method."""

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_false_when_no_html(self, mock_resp):
        mock_resp.return_value = False

        course = Course("12345")
        result = course.extractGrades("http://example.com/grades")

        assert result is False

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_false_when_not_enough_tables(self, mock_resp):
        mock_resp.return_value = "<html><body><table></table></body></html>"

        course = Course("12345")
        result = course.extractGrades("http://example.com/grades")

        assert result is False

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_extracts_timestamp_from_url(self, mock_resp):
        # Mock HTML with 3 tables (minimum required)
        html = """
        <html><body>
            <table>
                <tr><th>Header</th></tr>
                <tr><td>Key</td><td>100</td></tr>
                <tr><td>Pass</td><td>80 (80%)</td></tr>
                <tr><td>Avg</td><td>7.5 (B)</td></tr>
            </table>
            <table></table>
            <table>
                <tr><th>Grade</th><th>Count</th></tr>
                <tr><td>12</td><td>10</td></tr>
            </table>
        </body></html>
        """
        mock_resp.return_value = html

        course = Course("12345")
        result = course.extractGrades("http://example.com/grades/E-24")

        assert result is not False
        assert "timestamp" in result


class TestExtractReviews:
    """Tests for the Course.extractReviews method."""

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_false_when_no_html(self, mock_resp):
        mock_resp.return_value = False

        course = Course("12345")
        result = course.extractReviews("http://example.com/reviews")

        assert result is False

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_false_when_no_public_container(self, mock_resp):
        mock_resp.return_value = "<html><body><div>No reviews here</div></body></html>"

        course = Course("12345")
        result = course.extractReviews("http://example.com/reviews")

        assert result is False


class TestGather:
    """Tests for the Course.gather method."""

    def test_returns_false_when_no_data(self):
        course = Course("12345")
        # No links added, so gather should return False
        result = course.gather()
        assert result is False

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_dict_when_grades_found(self, mock_resp):
        # Mock HTML with proper structure
        html = """
        <html><body>
            <table>
                <tr><th>Header</th></tr>
                <tr><td>Key</td><td>100</td></tr>
                <tr><td>Pass</td><td>80 (80%)</td></tr>
                <tr><td>Avg</td><td>7.5 (B)</td></tr>
            </table>
            <table></table>
            <table>
                <tr><th>Grade</th><th>Count</th></tr>
                <tr><td>12</td><td>10</td></tr>
            </table>
        </body></html>
        """
        mock_resp.return_value = html

        course = Course("12345")
        course.gradeLinks = ["http://example.com/grades/E-24"]
        result = course.gather()

        assert result is not False
        assert "grades" in result
        assert len(result["grades"]) == 1


class TestProcessSingleCourse:
    """Tests for the process_single_course function."""

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_none_when_no_overview(self, mock_resp):
        from dtu_analyzer.scrapers.threaded_scraper import process_single_course
        mock_resp.return_value = False

        result = process_single_course("12345")

        assert result is None

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_returns_none_when_no_links_found(self, mock_resp):
        from dtu_analyzer.scrapers.threaded_scraper import process_single_course
        # Return HTML with no grade/review links
        mock_resp.return_value = "<html><body><a href='/other'>Other</a></body></html>"

        result = process_single_course("12345")

        assert result is None

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_fetches_danish_name_with_lang_parameter(self, mock_resp):
        """Test that Danish course name is fetched with ?lang=da-DK parameter."""
        from dtu_analyzer.scrapers.threaded_scraper import process_single_course, BASE_URL

        # Track all URLs that respObj is called with
        called_urls = []

        def track_urls(url, sess=None):
            called_urls.append(url)
            # Return minimal valid HTML for overview page
            if "/info" in url:
                return "<html><body><a href='/course/12345/karakterer/E-24'>Grades</a></body></html>"
            # Return valid grade HTML
            if "/karakterer/" in url:
                return """
                <html><body>
                    <table><tr><td>Key</td><td>100</td></tr><tr><td>Pass</td><td>80 (80%)</td></tr><tr><td>Avg</td><td>7.5</td></tr></table>
                    <table></table>
                    <table><tr><td>12</td><td>10</td></tr></table>
                </body></html>
                """
            # Return course name HTML
            if "?lang=" in url:
                return "<html><body><h2>12345 Test Course</h2></body></html>"
            return "<html><body><h2>12345 Test Course</h2></body></html>"

        mock_resp.side_effect = track_urls

        result = process_single_course("12345")

        # Verify Danish URL was called with ?lang=da-DK
        danish_url = f"{BASE_URL}/course/12345?lang=da-DK"
        assert danish_url in called_urls, f"Expected {danish_url} in {called_urls}"

        # Verify English URL was called with ?lang=en-GB
        english_url = f"{BASE_URL}/course/12345?lang=en-GB"
        assert english_url in called_urls, f"Expected {english_url} in {called_urls}"

    @patch('dtu_analyzer.scrapers.threaded_scraper.respObj')
    def test_stores_different_danish_and_english_names(self, mock_resp):
        """Test that Danish and English names are stored separately and can differ."""
        from dtu_analyzer.scrapers.threaded_scraper import process_single_course, BASE_URL

        def return_language_specific_html(url, sess=None):
            # Return minimal valid HTML for overview page
            if "/info" in url:
                return "<html><body><a href='/course/12345/karakterer/E-24'>Grades</a></body></html>"
            # Return valid grade HTML
            if "/karakterer/" in url:
                return """
                <html><body>
                    <table><tr><td>Key</td><td>100</td></tr><tr><td>Pass</td><td>80 (80%)</td></tr><tr><td>Avg</td><td>7.5</td></tr></table>
                    <table></table>
                    <table><tr><td>12</td><td>10</td></tr></table>
                </body></html>
                """
            # Return DIFFERENT names for Danish and English
            if "?lang=da-DK" in url:
                return "<html><body><h2>12345 Matematik og Statistik</h2></body></html>"
            if "?lang=en-GB" in url:
                return "<html><body><h2>12345 Mathematics and Statistics</h2></body></html>"
            return "<html><body><h2>12345 Default Name</h2></body></html>"

        mock_resp.side_effect = return_language_specific_html

        result = process_single_course("12345")

        # Verify both names are captured
        assert result is not None
        course_num, course_data = result

        assert "name" in course_data, "Danish name should be stored in 'name'"
        assert "name_en" in course_data, "English name should be stored in 'name_en'"

        # Verify they are different (as mocked)
        assert course_data["name"] == "Matematik og Statistik"
        assert course_data["name_en"] == "Mathematics and Statistics"
        assert course_data["name"] != course_data["name_en"], "Danish and English names should be different"


class TestMain:
    """Tests for the main function."""

    @patch('builtins.open', side_effect=FileNotFoundError())
    def test_returns_error_when_coursenumbers_missing(self, mock_open):
        from dtu_analyzer.scrapers.threaded_scraper import main
        result = main()
        assert result == 1
