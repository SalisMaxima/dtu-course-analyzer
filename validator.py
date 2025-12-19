"""
Backward compatibility wrapper for the validator.

This file maintains backward compatibility with existing scripts and workflows.
The actual implementation has been moved to src/dtu_analyzer/validation/validator.py

Usage: python validator.py [coursedic.json]
"""

from src.dtu_analyzer.validation.validator import main
import sys

if __name__ == "__main__":
    sys.exit(main())
