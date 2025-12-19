"""
Backward compatibility wrapper for get_course_numbers script.

This file maintains backward compatibility with existing scripts and workflows.
The actual implementation has been moved to src/dtu_analyzer/scripts/get_course_numbers.py

Usage: python getCourseNumbers.py
"""

from src.dtu_analyzer.scripts.get_course_numbers import main
import sys

if __name__ == "__main__":
    sys.exit(main())
