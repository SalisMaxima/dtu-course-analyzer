"""
Analysis module for DTU Course Analyzer.

Provides course data processing and extension file generation.
"""

from .analyzer import main as analyze_main, process_courses, generate_extension_data

__all__ = ['analyze_main', 'process_courses', 'generate_extension_data']
