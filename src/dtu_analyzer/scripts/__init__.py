"""
Scripts module for DTU Course Analyzer.

Provides utility scripts for course discovery and data collection.
"""

from .get_course_numbers import main as get_course_numbers_main, get_course_numbers

__all__ = ['get_course_numbers_main', 'get_course_numbers']
