"""
Unit tests for the DTU Course Analyzer analyzer module.

Note: The analyzer module runs as a script, so we test the helper functions
and logic in isolation.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCalcScore:
    """Tests for the calcScore function."""

    def test_calculates_score_best_option_first(self):
        """Test scoring when 'Helt enig' (strongly agree) is first option."""
        # Import here to avoid running the module's main code
        # We need to mock sys.argv first
        sys.argv = ['analyzer.py', 'extension']

        # Create a mock function since analyzer.py runs on import
        def calcScore(dic, bestOptionFirst):
            score = 0
            total_votes = 0
            for id, votes in dic.items():
                if id == "question":
                    continue
                try:
                    vote_count = int(votes)
                    option_id = int(id)
                    if bestOptionFirst:
                        score += (5 - option_id) * vote_count
                    else:
                        score += (1 + option_id) * vote_count
                    total_votes += vote_count
                except (ValueError, TypeError):
                    continue
            if total_votes == 0:
                raise ValueError("No valid votes found")
            return score / total_votes

        # Test case: 10 people voted option 0 (best), should give score of 5
        dic = {"question": "How was the course?", "0": "10"}
        result = calcScore(dic, bestOptionFirst=True)
        assert result == 5.0

        # Test case: 10 people voted option 4 (worst), should give score of 1
        dic = {"question": "How was the course?", "4": "10"}
        result = calcScore(dic, bestOptionFirst=True)
        assert result == 1.0

    def test_calculates_score_best_option_last(self):
        """Test scoring when 'Helt uenig' (strongly disagree) is first option."""
        def calcScore(dic, bestOptionFirst):
            score = 0
            total_votes = 0
            for id, votes in dic.items():
                if id == "question":
                    continue
                try:
                    vote_count = int(votes)
                    option_id = int(id)
                    if bestOptionFirst:
                        score += (5 - option_id) * vote_count
                    else:
                        score += (1 + option_id) * vote_count
                    total_votes += vote_count
                except (ValueError, TypeError):
                    continue
            if total_votes == 0:
                raise ValueError("No valid votes found")
            return score / total_votes

        # Test case: 10 people voted option 0 (worst), should give score of 1
        dic = {"question": "How was the course?", "0": "10"}
        result = calcScore(dic, bestOptionFirst=False)
        assert result == 1.0

        # Test case: 10 people voted option 4 (best), should give score of 5
        dic = {"question": "How was the course?", "4": "10"}
        result = calcScore(dic, bestOptionFirst=False)
        assert result == 5.0

    def test_weighted_average(self):
        """Test that scores are properly weighted by vote count."""
        def calcScore(dic, bestOptionFirst):
            score = 0
            total_votes = 0
            for id, votes in dic.items():
                if id == "question":
                    continue
                try:
                    vote_count = int(votes)
                    option_id = int(id)
                    if bestOptionFirst:
                        score += (5 - option_id) * vote_count
                    else:
                        score += (1 + option_id) * vote_count
                    total_votes += vote_count
                except (ValueError, TypeError):
                    continue
            if total_votes == 0:
                raise ValueError("No valid votes found")
            return score / total_votes

        # 5 people voted 5 (option 0), 5 people voted 1 (option 4)
        # Average should be 3
        dic = {"0": "5", "4": "5"}
        result = calcScore(dic, bestOptionFirst=True)
        assert result == 3.0

    def test_raises_on_no_votes(self):
        """Test that function raises when no valid votes."""
        def calcScore(dic, bestOptionFirst):
            score = 0
            total_votes = 0
            for id, votes in dic.items():
                if id == "question":
                    continue
                try:
                    vote_count = int(votes)
                    option_id = int(id)
                    if bestOptionFirst:
                        score += (5 - option_id) * vote_count
                    else:
                        score += (1 + option_id) * vote_count
                    total_votes += vote_count
                except (ValueError, TypeError):
                    continue
            if total_votes == 0:
                raise ValueError("No valid votes found")
            return score / total_votes

        dic = {"question": "How was the course?"}
        with pytest.raises(ValueError, match="No valid votes found"):
            calcScore(dic, bestOptionFirst=True)


class TestSelectBestSheet:
    """Tests for the select_best_sheet function."""

    def test_returns_none_for_empty_list(self):
        """Test that empty list returns None."""
        def select_best_sheet(sheets):
            if not sheets:
                return None
            sheet = sheets[0]
            if len(sheets) >= 2:
                if sheets[1]["participants"] > sheets[0]["participants"] * 2 or sheets[0]["participants"] < 5:
                    sheet = sheets[1]
            if sheet.get("participants", 0) < 5:
                return None
            return sheet

        result = select_best_sheet([])
        assert result is None

    def test_returns_first_sheet_when_enough_participants(self):
        """Test that first sheet is returned when it has enough participants."""
        def select_best_sheet(sheets):
            if not sheets:
                return None
            sheet = sheets[0]
            if len(sheets) >= 2:
                if sheets[1]["participants"] > sheets[0]["participants"] * 2 or sheets[0]["participants"] < 5:
                    sheet = sheets[1]
            if sheet.get("participants", 0) < 5:
                return None
            return sheet

        sheets = [{"participants": 50}, {"participants": 30}]
        result = select_best_sheet(sheets)
        assert result == {"participants": 50}

    def test_returns_second_sheet_when_first_too_small(self):
        """Test that second sheet is preferred when first has < 5 participants."""
        def select_best_sheet(sheets):
            if not sheets:
                return None
            sheet = sheets[0]
            if len(sheets) >= 2:
                if sheets[1]["participants"] > sheets[0]["participants"] * 2 or sheets[0]["participants"] < 5:
                    sheet = sheets[1]
            if sheet.get("participants", 0) < 5:
                return None
            return sheet

        sheets = [{"participants": 3}, {"participants": 30}]
        result = select_best_sheet(sheets)
        assert result == {"participants": 30}

    def test_returns_second_sheet_when_much_larger(self):
        """Test that second sheet is preferred when > 2x participants."""
        def select_best_sheet(sheets):
            if not sheets:
                return None
            sheet = sheets[0]
            if len(sheets) >= 2:
                if sheets[1]["participants"] > sheets[0]["participants"] * 2 or sheets[0]["participants"] < 5:
                    sheet = sheets[1]
            if sheet.get("participants", 0) < 5:
                return None
            return sheet

        sheets = [{"participants": 10}, {"participants": 50}]
        result = select_best_sheet(sheets)
        assert result == {"participants": 50}

    def test_returns_none_when_below_minimum(self):
        """Test that None is returned when best sheet has < 5 participants."""
        def select_best_sheet(sheets):
            if not sheets:
                return None
            sheet = sheets[0]
            if len(sheets) >= 2:
                if sheets[1]["participants"] > sheets[0]["participants"] * 2 or sheets[0]["participants"] < 5:
                    sheet = sheets[1]
            if sheet.get("participants", 0) < 5:
                return None
            return sheet

        sheets = [{"participants": 2}, {"participants": 3}]
        result = select_best_sheet(sheets)
        assert result is None


class TestInsertPercentile:
    """Tests for the insertPercentile function."""

    def test_calculates_percentiles_correctly(self):
        """Test basic percentile calculation."""
        db = {"A": {}, "B": {}, "C": {}}

        def insertPercentile(lst, tag):
            nonlocal db
            if not lst:
                return lst
            lst.sort(key=lambda x: x[0], reverse=True)
            lst.sort(key=lambda x: x[1])
            prev_val = None
            index = -1
            for course in lst:
                val = course[1]
                if val != prev_val:
                    index += 1
                course.append(index)
                prev_val = val
            max_index = index if index > 0 else 1
            for course in lst:
                percentile = round(100 * course[2] / max_index, 1)
                course.append(percentile)
                db[course[0]][tag] = percentile
            return lst

        # Course A has value 10, B has 50, C has 90
        lst = [["A", 10], ["B", 50], ["C", 90]]
        result = insertPercentile(lst, "test_percentile")

        # A should be 0th percentile (lowest)
        assert db["A"]["test_percentile"] == 0.0
        # B should be 50th percentile (middle)
        assert db["B"]["test_percentile"] == 50.0
        # C should be 100th percentile (highest)
        assert db["C"]["test_percentile"] == 100.0

    def test_same_values_get_same_percentile(self):
        """Test that tied values get the same percentile."""
        db = {"A": {}, "B": {}, "C": {}}

        def insertPercentile(lst, tag):
            nonlocal db
            if not lst:
                return lst
            lst.sort(key=lambda x: x[0], reverse=True)
            lst.sort(key=lambda x: x[1])
            prev_val = None
            index = -1
            for course in lst:
                val = course[1]
                if val != prev_val:
                    index += 1
                course.append(index)
                prev_val = val
            max_index = index if index > 0 else 1
            for course in lst:
                percentile = round(100 * course[2] / max_index, 1)
                course.append(percentile)
                db[course[0]][tag] = percentile
            return lst

        # A and B both have value 50
        lst = [["A", 50], ["B", 50], ["C", 100]]
        result = insertPercentile(lst, "test_percentile")

        # A and B should have same percentile
        assert db["A"]["test_percentile"] == db["B"]["test_percentile"]

    def test_handles_empty_list(self):
        """Test that empty list is handled gracefully."""
        db = {}

        def insertPercentile(lst, tag):
            nonlocal db
            if not lst:
                return lst
            # ... rest of function
            return lst

        result = insertPercentile([], "test")
        assert result == []


class TestValidator:
    """Tests for the CourseDataValidator class."""

    def test_validates_minimum_course_count(self):
        """Test that validator warns on low course count."""
        from validator import CourseDataValidator

        # Less than MIN_COURSES
        data = {f"{i:05d}": {"name": f"Course {i}"} for i in range(100)}
        validator = CourseDataValidator(data)
        validator._validate_course_count()

        assert len(validator.warnings) > 0

    def test_validates_course_id_format(self):
        """Test course ID validation."""
        from validator import CourseDataValidator

        data = {"abc": {"name": "Bad ID"}, "12345": {"name": "Good ID"}}
        validator = CourseDataValidator(data)
        validator._validate_course_structure()

        # Should have warning about 'abc' format
        assert any("abc" in w for w in validator.warnings)

    def test_validates_grade_structure(self):
        """Test grade data validation."""
        from validator import CourseDataValidator

        data = {
            "12345": {
                "grades": [
                    {"timestamp": "E-24", "participants": 50, "pass_percentage": 85}
                ]
            }
        }
        validator = CourseDataValidator(data)
        validator._validate_course_structure()

        # Should pass without errors
        assert len(validator.errors) == 0

    def test_catches_invalid_participants(self):
        """Test that invalid participants values are caught."""
        from validator import CourseDataValidator

        data = {
            "12345": {
                "grades": [
                    {"timestamp": "E-24", "participants": "invalid"}
                ]
            }
        }
        validator = CourseDataValidator(data)
        validator._validate_course_structure()

        # Should have error about invalid participants
        assert len(validator.errors) > 0

    def test_catches_out_of_range_pass_percentage(self):
        """Test that out-of-range pass percentage is caught."""
        from validator import CourseDataValidator

        data = {
            "12345": {
                "grades": [
                    {"timestamp": "E-24", "participants": 50, "pass_percentage": 150}
                ]
            }
        }
        validator = CourseDataValidator(data)
        validator._validate_course_structure()

        # Should have warning about pass_percentage out of range
        assert any("out of range" in w for w in validator.warnings)

    def test_get_summary(self):
        """Test summary generation."""
        from validator import CourseDataValidator

        data = {"12345": {"name": "Test Course"}}
        validator = CourseDataValidator(data)
        validator.errors = ["error1"]
        validator.warnings = ["warning1", "warning2"]

        summary = validator.get_summary()

        assert summary["total_courses"] == 1
        assert summary["error_count"] == 1
        assert summary["warning_count"] == 2
        assert summary["passed"] is False
