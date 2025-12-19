"""
Authentication module for DTU Course Analyzer.

Provides automated login functionality for DTU's ADFS system.
"""

from .authenticator import main as auth_main, authenticate

__all__ = ['auth_main', 'authenticate']
