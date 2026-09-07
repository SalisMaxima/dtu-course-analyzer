import pytest

from dtu_analyzer.scripts.get_course_numbers import extract_course_number


@pytest.mark.parametrize('course', ['01001', '42S01', 'KU002'])
def test_course_number_paths(course):
    assert extract_course_number(f'/course/{course}') == course
    assert extract_course_number(f'https://kurser.dtu.dk/course/2025-2026/{course}/info?lang=en-GB') == course


@pytest.mark.parametrize('path', ['/course/010201', '/course/42s01', '/other/01001', '/course/01001-extra'])
def test_rejects_partial_or_invalid_ids(path):
    assert extract_course_number(path) is None
