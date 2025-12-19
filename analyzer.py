"""
Backward compatibility wrapper for the analyzer.

This file maintains backward compatibility with existing scripts and workflows.
The actual implementation has been moved to src/dtu_analyzer/analysis/analyzer.py

Usage: python analyzer.py <extension-folder-name>
"""

from src.dtu_analyzer.analysis.analyzer import main
import sys

if __name__ == "__main__":
    sys.exit(main())
