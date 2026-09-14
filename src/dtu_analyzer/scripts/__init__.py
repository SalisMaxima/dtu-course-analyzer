"""
Scripts module for DTU Course Analyzer.

Provides utility scripts for course discovery and data collection.
"""

__all__ = ['get_course_numbers_main', 'get_course_numbers']


def __getattr__(name):
    # Promotion/publication must not import browser automation or auth code.
    if name not in __all__:
        raise AttributeError(name)
    from importlib import import_module
    discovery = import_module('.get_course_numbers', __name__)
    globals().update(get_course_numbers_main=discovery.main,
                     get_course_numbers=discovery.get_course_numbers)
    return globals()[name]
