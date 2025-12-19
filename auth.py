"""
Backward compatibility wrapper for the authenticator.

This file maintains backward compatibility with existing scripts and workflows.
The actual implementation has been moved to src/dtu_analyzer/auth/authenticator.py

Usage: python auth.py
"""

from src.dtu_analyzer.auth.authenticator import main
import sys

if __name__ == "__main__":
    sys.exit(main())
