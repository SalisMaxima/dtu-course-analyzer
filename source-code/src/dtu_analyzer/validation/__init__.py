"""
Validation module for DTU Course Analyzer.

Provides data validation and integrity checking.
"""

from .validator import main as validate_main, CourseDataValidator, validate_file

__all__ = ['validate_main', 'CourseDataValidator', 'validate_file']
