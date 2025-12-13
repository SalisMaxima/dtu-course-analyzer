"""
Unit tests for the DTU Course Analyzer scraper module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRemoveWhitespace:
    """Tests for the removeWhitespace function."""

    def test_removes_spaces(self):
        from scraper import removeWhitespace
        assert removeWhitespace("hello world") == "helloworld"

    def test_removes_tabs_and_newlines(self):
        from scraper import removeWhitespace
        assert removeWhitespace("hello\t\nworld") == "helloworld"

    def test_handles_empty_string(self):
        from scraper import removeWhitespace
        assert removeWhitespace("") == ""

    def test_handles_only_whitespace(self):
        from scraper import removeWhitespace
        assert removeWhitespace("   \t\n   ") == ""

    def test_preserves_non_whitespace(self):
        from scraper import removeWhitespace
        assert removeWhitespace("abc123") == "abc123"


class TestParseYear:
    """Tests for the parse_year function."""

    def test_two_digit_year_2000s(self):
        from scraper import parse_year
        assert parse_year("24") == "2024"
        assert parse_year("00") == "2000"
        assert parse_year("49") == "2049"

    def test_two_digit_year_1900s(self):
        from scraper import parse_year
        assert parse_year("50") == "1950"
        assert parse_year("99") == "1999"

    def test_four_digit_year(self):
        from scraper import parse_year
        assert parse_year("2024") == "2024"
        assert parse_year("2023") == "2023"

    def test_invalid_year_returns_original(self):
        from scraper import parse_year
        assert parse_year("abc") == "abc"
        assert parse_year("") == ""


class TestCourseClass:
    """Tests for the Course class."""

    def test_init_creates_empty_links(self):
        from scraper import Course
        course = Course("12345")
        assert course.courseN == "12345"
        assert course.reviewLinks == []
        assert course.gradeLinks == []

    def test_init_creates_grade_dict(self):
        from scraper import Course, grades
        course = Course("12345")
        for grade in grades:
            assert grade in course.dic
            assert course.dic[grade] == 0


class TestExtractGrades:
    """Tests for the Course.extractGrades method."""

    @patch('scraper.respObj')
    def test_returns_false_when_no_html(self, mock_resp):
        from scraper import Course
        mock_resp.return_value = False

        course = Course("12345")
        result = course.extractGrades("http://example.com/grades")

        assert result is False

    @patch('scraper.respObj')
    def test_returns_false_when_not_enough_tables(self, mock_resp):
        from scraper import Course
        mock_resp.return_value = "<html><body><table></table></body></html>"

        course = Course("12345")
        result = course.extractGrades("http://example.com/grades")

        assert result is False

    @patch('scraper.respObj')
    def test_extracts_timestamp_from_url(self, mock_resp):
        from scraper import Course
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

    @patch('scraper.respObj')
    def test_returns_false_when_no_html(self, mock_resp):
        from scraper import Course
        mock_resp.return_value = False

        course = Course("12345")
        result = course.extractReviews("http://example.com/reviews")

        assert result is False

    @patch('scraper.respObj')
    def test_returns_false_when_no_public_container(self, mock_resp):
        from scraper import Course
        mock_resp.return_value = "<html><body><div>No reviews here</div></body></html>"

        course = Course("12345")
        result = course.extractReviews("http://example.com/reviews")

        assert result is False


class TestRespObj:
    """Tests for the respObj function."""

    @patch('scraper.session')
    def test_returns_text_on_success(self, mock_session):
        from scraper import respObj
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>content</html>"
        mock_session.get.return_value = mock_response

        result = respObj("http://example.com")

        assert result == "<html>content</html>"

    @patch('scraper.session')
    def test_returns_false_on_non_200(self, mock_session):
        from scraper import respObj
        mock_response = Mock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response

        result = respObj("http://example.com")

        assert result is False

    @patch('scraper.session')
    def test_returns_false_on_timeout(self, mock_session):
        from scraper import respObj
        import requests
        mock_session.get.side_effect = requests.Timeout()

        result = respObj("http://example.com")

        assert result is False

    @patch('scraper.session')
    def test_returns_false_on_connection_error(self, mock_session):
        from scraper import respObj
        import requests
        mock_session.get.side_effect = requests.ConnectionError()

        result = respObj("http://example.com")

        assert result is False


class TestGather:
    """Tests for the Course.gather method."""

    def test_returns_false_when_no_data(self):
        from scraper import Course
        course = Course("12345")
        # No links added, so gather should return False
        result = course.gather()
        assert result is False

    @patch.object(__import__('scraper', fromlist=['Course']).Course, 'extractGrades')
    def test_returns_dict_when_grades_found(self, mock_extract):
        from scraper import Course
        mock_extract.return_value = {"participants": 50, "timestamp": "E-24"}

        course = Course("12345")
        course.gradeLinks = ["http://example.com/grades"]
        result = course.gather()

        assert result is not False
        assert "grades" in result
        assert len(result["grades"]) == 1


class TestProcessSingleCourse:
    """Tests for the process_single_course function."""

    @patch('scraper.respObj')
    def test_returns_none_when_no_overview(self, mock_resp):
        from scraper import process_single_course
        mock_resp.return_value = False

        result = process_single_course("12345")

        assert result is None

    @patch('scraper.respObj')
    @patch.object(__import__('scraper', fromlist=['Course']).Course, 'gather')
    def test_returns_none_when_no_data_gathered(self, mock_gather, mock_resp):
        from scraper import process_single_course
        mock_resp.return_value = "<html><body></body></html>"
        mock_gather.return_value = False

        result = process_single_course("12345")

        assert result is None
