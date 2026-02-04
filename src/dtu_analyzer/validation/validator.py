"""
Data validation for DTU Course Analyzer.

This module validates scraped course data to detect issues early,
such as when the DTU website structure changes.
"""

import json
import sys
from typing import Any, Dict

# Import from our modules
from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger('validator', 'validator.log')


class ValidationError(Exception):
    """Raised when data validation fails."""
    pass


class CourseDataValidator:
    """Validates scraped course data structure and content."""

    # Minimum expected courses (adjust based on historical data)
    MIN_COURSES = 500

    # Required fields for grade data
    GRADE_REQUIRED_FIELDS = {"timestamp", "participants"}
    GRADE_OPTIONAL_FIELDS = {"pass_percentage", "avg", "url"}

    # Required fields for review data
    REVIEW_REQUIRED_FIELDS = {"timestamp", "participants"}
    REVIEW_OPTIONAL_FIELDS = {"firstOption", "url", "1.1", "2.1"}

    # Valid grade names
    VALID_GRADES = {"-3", "00", "02", "4", "7", "10", "12", "absent", "sick", "p", "np"}

    def __init__(self, data: dict):
        """
        Initialize validator with course data.

        Args:
            data: Dictionary of course data (courseN -> course_data)
        """
        self.data = data
        self.errors = []
        self.warnings = []

    def validate(self) -> bool:
        """
        Run all validations.

        Returns:
            True if validation passed (may have warnings), False if errors found
        """
        self._validate_course_count()
        self._validate_course_structure()
        self._validate_data_quality()

        # Log results
        for warning in self.warnings:
            logger.warning(warning)
        for error in self.errors:
            logger.error(error)

        if self.errors:
            logger.error(f"Validation FAILED with {len(self.errors)} errors and {len(self.warnings)} warnings")
            return False

        logger.info(f"Validation PASSED with {len(self.warnings)} warnings")
        return True

    def _validate_course_count(self):
        """Check that we have a reasonable number of courses."""
        count = len(self.data)

        if count == 0:
            self.errors.append("No courses found in data")
        elif count < self.MIN_COURSES:
            self.warnings.append(
                f"Only {count} courses found (expected at least {self.MIN_COURSES}). "
                "DTU website structure may have changed."
            )
        else:
            logger.info(f"Found {count} courses")

    def _validate_course_structure(self):
        """Validate the structure of each course."""
        for course_id, course_data in self.data.items():
            self._validate_course_id(course_id)
            self._validate_single_course(course_id, course_data)

    def _validate_course_id(self, course_id: str):
        """Validate course ID format."""
        if not course_id:
            self.errors.append("Empty course ID found")
            return

        if not course_id.isdigit() or len(course_id) != 5:
            self.warnings.append(f"Unusual course ID format: {course_id}")

    def _validate_single_course(self, course_id: str, course_data: dict):
        """Validate a single course's data structure."""
        if not isinstance(course_data, dict):
            self.errors.append(f"Course {course_id}: data is not a dictionary")
            return

        # Check for at least some data
        if not course_data:
            self.warnings.append(f"Course {course_id}: empty data")
            return

        # Validate grades if present
        if "grades" in course_data:
            self._validate_grades(course_id, course_data["grades"])

        # Validate reviews if present
        if "reviews" in course_data:
            self._validate_reviews(course_id, course_data["reviews"])

        # Check for name
        if "name" not in course_data:
            self.warnings.append(f"Course {course_id}: missing name")

    def _validate_grades(self, course_id: str, grades: Any):
        """Validate grade data structure."""
        if not isinstance(grades, list):
            self.errors.append(f"Course {course_id}: grades is not a list")
            return

        for i, semester in enumerate(grades):
            if not isinstance(semester, dict):
                self.errors.append(f"Course {course_id}: grade entry {i} is not a dictionary")
                continue

            # Check required fields
            missing = self.GRADE_REQUIRED_FIELDS - set(semester.keys())
            if missing:
                self.warnings.append(f"Course {course_id}: grade entry {i} missing fields: {missing}")

            # Validate participants
            if "participants" in semester:
                try:
                    participants = int(semester["participants"])
                    if participants < 0:
                        self.warnings.append(f"Course {course_id}: negative participants count")
                except (ValueError, TypeError):
                    self.errors.append(f"Course {course_id}: invalid participants value")

            # Validate pass percentage
            if "pass_percentage" in semester:
                try:
                    pct = int(semester["pass_percentage"])
                    if not 0 <= pct <= 100:
                        self.warnings.append(f"Course {course_id}: pass_percentage {pct} out of range")
                except (ValueError, TypeError):
                    self.errors.append(f"Course {course_id}: invalid pass_percentage value")

            # Validate average
            if "avg" in semester:
                try:
                    avg = float(semester["avg"])
                    if not -3 <= avg <= 12:
                        self.warnings.append(f"Course {course_id}: average {avg} out of expected range")
                except (ValueError, TypeError):
                    self.errors.append(f"Course {course_id}: invalid avg value")

    def _validate_reviews(self, course_id: str, reviews: Any):
        """Validate review data structure."""
        if not isinstance(reviews, list):
            self.errors.append(f"Course {course_id}: reviews is not a list")
            return

        for i, semester in enumerate(reviews):
            if not isinstance(semester, dict):
                self.errors.append(f"Course {course_id}: review entry {i} is not a dictionary")
                continue

            # Check required fields
            missing = self.REVIEW_REQUIRED_FIELDS - set(semester.keys())
            if missing:
                self.warnings.append(f"Course {course_id}: review entry {i} missing fields: {missing}")

            # Validate participants
            if "participants" in semester:
                try:
                    participants = int(semester["participants"])
                    if participants < 0:
                        self.warnings.append(f"Course {course_id}: negative review participants")
                except (ValueError, TypeError):
                    self.errors.append(f"Course {course_id}: invalid review participants value")

    def _validate_data_quality(self):
        """Check overall data quality metrics."""
        courses_with_grades = sum(1 for c in self.data.values() if "grades" in c)
        courses_with_reviews = sum(1 for c in self.data.values() if "reviews" in c)
        courses_with_name = sum(1 for c in self.data.values() if "name" in c)

        total = len(self.data)
        if total == 0:
            return

        grade_pct = 100 * courses_with_grades / total
        review_pct = 100 * courses_with_reviews / total
        name_pct = 100 * courses_with_name / total

        logger.info(f"Data quality: {grade_pct:.1f}% have grades, {review_pct:.1f}% have reviews, {name_pct:.1f}% have names")

        # Warn if data completeness is unusually low
        if grade_pct < 50:
            self.warnings.append(f"Only {grade_pct:.1f}% of courses have grade data")
        if review_pct < 30:
            self.warnings.append(f"Only {review_pct:.1f}% of courses have review data")
        if name_pct < 90:
            self.warnings.append(f"Only {name_pct:.1f}% of courses have names")

        # Check name translation quality
        self._validate_name_translations()

    def _validate_name_translations(self):
        """Check that Danish and English names are properly differentiated."""
        courses_with_both = 0
        courses_with_same_name = 0
        courses_with_different_name = 0

        for course_id, course in self.data.items():
            has_danish = "name" in course and course["name"]
            has_english = "name_en" in course and course["name_en"]

            if has_danish and has_english:
                courses_with_both += 1
                if course["name"] == course["name_en"]:
                    courses_with_same_name += 1
                else:
                    courses_with_different_name += 1

        if courses_with_both == 0:
            self.warnings.append("No courses have both Danish and English names")
            return

        same_pct = 100 * courses_with_same_name / courses_with_both
        diff_pct = 100 * courses_with_different_name / courses_with_both

        logger.info(f"Name translations: {courses_with_different_name}/{courses_with_both} ({diff_pct:.1f}%) have unique Danish names")

        # If more than 95% have identical names, the scraper probably isn't fetching Danish properly
        if same_pct > 95:
            self.warnings.append(
                f"Name translation issue: {same_pct:.1f}% of courses have identical Danish/English names. "
                f"Check that scraper is using ?lang=da-DK parameter."
            )

    def get_summary(self) -> dict:
        """
        Get validation summary.

        Returns:
            Dictionary with validation results
        """
        return {
            "total_courses": len(self.data),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "passed": len(self.errors) == 0
        }


def validate_file(filepath: str) -> bool:
    """
    Validate a JSON course data file.

    Args:
        filepath: Path to JSON file

    Returns:
        True if validation passed
    """
    try:
        with open(filepath) as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return False

    validator = CourseDataValidator(data)
    return validator.validate()


def main():
    """Main entry point for the validator."""
    # Run validation on coursedic.json by default
    filepath = sys.argv[1] if len(sys.argv) > 1 else str(config.paths.course_data_file)
    success = validate_file(filepath)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
