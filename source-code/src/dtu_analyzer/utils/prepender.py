"""Utility for prepending lines to existing files.

This module provides a context manager for safely prepending lines to files.
"""

from typing import List, Union
from pathlib import Path


class PrependToFile:
    """Context manager for prepending lines to an existing file.

    Example:
        >>> with PrependToFile('data.js') as f:
        ...     f.write_line('window.data = ')
    """

    def __init__(self, file_path: Union[str, Path]):
        """Initialize the prepender.

        Args:
            file_path: Path to the file to prepend to
        """
        self.file_path = Path(file_path)
        self.__write_queue: List[str] = []
        self.__open_file = None

        # Read in the existing file content
        with open(self.file_path, mode='r', encoding='utf-8') as f:
            self.__write_queue = f.readlines()

    def write_line(self, line: str) -> None:
        """Prepend a single line to the file.

        Args:
            line: Line to prepend (newline will be added if missing)
        """
        if not line.endswith('\n'):
            line += '\n'
        self.__write_queue.insert(0, line)

    def write_lines(self, lines: List[str]) -> None:
        """Prepend multiple lines to the file.

        Args:
            lines: List of lines to prepend (in order, first line first)
        """
        # Reverse so they're inserted in correct order
        lines_copy = lines.copy()
        lines_copy.reverse()
        for line in lines_copy:
            self.write_line(line)

    def close(self) -> None:
        """Close the file (alias for __exit__)."""
        self.__exit__(None, None, None)

    def __enter__(self) -> "PrependToFile":
        """Enter the context manager."""
        self.__open_file = open(self.file_path, mode='w', encoding='utf-8')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and write the file."""
        if self.__write_queue and self.__open_file:
            self.__open_file.writelines(self.__write_queue)
        if self.__open_file:
            self.__open_file.close()
