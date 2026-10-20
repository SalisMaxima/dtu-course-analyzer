import pytest

from dtu_analyzer.scripts.get_course_numbers import extract_course_number, parse_result_count


@pytest.mark.parametrize('course', ['01001', '42S01', 'KU002'])
def test_course_number_paths(course):
    assert extract_course_number(f'/course/{course}') == course
    assert extract_course_number(f'https://kurser.dtu.dk/course/2025-2026/{course}/info?lang=en-GB') == course


@pytest.mark.parametrize('path', ['/course/010201', '/course/42s01', '/other/01001', '/course/01001-extra'])
def test_rejects_partial_or_invalid_ids(path):
    assert extract_course_number(path) is None


@pytest.mark.parametrize('text, expected', [
    ('\n    1556 courses match your search\n    ', 1556),
    ('1556 kurser matchede din søgning', 1556),
    ('Search result', None),
    (None, None),
])
def test_parse_result_count(text, expected):
    assert parse_result_count(text) == expected
