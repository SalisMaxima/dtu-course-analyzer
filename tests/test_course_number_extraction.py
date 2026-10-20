import importlib
from types import SimpleNamespace

import pytest

from dtu_analyzer.scripts.get_course_numbers import extract_course_number, parse_result_count

# The package re-exports a function with the module's name, so import the module itself.
fetcher = importlib.import_module('dtu_analyzer.scripts.get_course_numbers')


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


class FakePage:
    def __init__(self, total_text, links):
        self.total_text = total_text
        self.links = links

    def goto(self, *args, **kwargs):
        pass

    def wait_for_selector(self, *args, **kwargs):
        pass

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def evaluate(self, script):
        return self.total_text if '.panel-heading' in script else self.links


class FakePlaywright:
    def __init__(self, page):
        context = SimpleNamespace(add_cookies=lambda cookies: None, new_page=lambda: page)
        browser = SimpleNamespace(new_context=lambda **kwargs: context, close=lambda: None)
        self.chromium = SimpleNamespace(launch=lambda **kwargs: browser)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def search_page(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher.config.paths, 'root_dir', tmp_path)
    (tmp_path / 'secret.txt').write_text('session')
    (tmp_path / 'data').mkdir()

    def serve(total_text, links):
        monkeypatch.setattr(fetcher, 'sync_playwright', lambda: FakePlaywright(FakePage(total_text, links)))
        return fetcher.config.paths.course_numbers_file
    return serve


LINKS = ['/course/01001', '/course/2026-2027/KU002/info', '/course/01001', '/other/02002']


def test_saves_when_count_matches_page_total(search_page):
    output = search_page('2 courses match your search', LINKS)

    assert fetcher.get_course_numbers() is True
    assert output.read_text() == '01001,KU002'


@pytest.mark.parametrize('total_text', ['3 courses match your search', None])
@pytest.mark.parametrize('previous', [None, '01001,02002,KU002'])
def test_refuses_partial_or_unverified_list(search_page, total_text, previous):
    output = search_page(total_text, LINKS)
    if previous is not None:
        output.write_text(previous)

    assert fetcher.get_course_numbers() is False
    if previous is None:
        assert not output.exists()
    else:
        assert output.read_text() == previous
