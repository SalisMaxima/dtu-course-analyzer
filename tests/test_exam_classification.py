"""Diagnostic rules and collection tests using synthetic DTU-shaped pages."""

import asyncio
import csv
import json

import pytest

from dtu_analyzer.analysis.exam_classification import (
    classify_course, extract_schedule, parse_period,
)
from dtu_analyzer.scripts import probe_exam_classification as probe


def sheet(label, count=50, group=1):
    url = f"http://karakterer.dtu.dk/Histogram/{group}/01001/{label}"
    return {"url": url, "period": parse_period(url), "grades": {"participants": count}}


def record(schedule, exams):
    return {"course": "01001", "schedule": extract_schedule(
        f"<table><tr><td>Schedule</td><td>{schedule}</td></tr></table>"
    ), "exams": exams, "errors": []}


@pytest.mark.parametrize("schedule,primary", [
    ("Autumn", "Winter-2025"), ("Efterår E2A", "Winter-2025"),
    ("January", "Winter-2025"), ("Januar", "Winter-2025"),
    ("Spring F2B (Thurs 8-12)", "Summer-2026"),
    ("Forår", "Summer-2026"), ("June", "Summer-2026"),
    ("Juni", "Summer-2026"), ("July", "Summer-2026"),
])
def test_schedule_hypotheses(schedule, primary):
    result = classify_course(record(schedule, [sheet("Summer-2026", 500), sheet("Winter-2025", 20)]))
    assert result["primary_exam"]["period"]["label"] == primary
    assert result["status"] == "provisional"
    assert len(result["resit_exams"]) == 1
    assert result["caveats"]


def test_selects_latest_ordinary_across_all_sheets_not_participant_size():
    result = classify_course(record("Autumn", [
        sheet("Winter-2023", 300), sheet("Summer-2026", 600),
        sheet("Winter-2025", 4), sheet("Winter-2024", 900),
    ]))
    assert result["primary_exam"]["period"]["label"] == "Winter-2025"
    assert len(result["ordinary_exams"]) == 3
    assert len(result["resit_exams"]) == 1


@pytest.mark.parametrize("schedule,reason", [
    ("", "schedule_missing_or_unrecognized"),
    ("Spring and Autumn", "multiple_teaching_periods"),
    ("August", "august_histogram_mapping_unverified"),
    ("August. Also 42500(January), 42501(June)", "schedule_contains_other_course_references"),
])
def test_ambiguous_schedules_are_explicit(schedule, reason):
    result = classify_course(record(schedule, [sheet("Winter-2025"), sheet("Summer-2026")]))
    assert result["status"] == "undetermined"
    assert result["primary_exam"] is None
    assert result["resit_exams"] == []
    assert len(result["undetermined_exams"]) == 2
    assert reason in result["reasons"]


@pytest.mark.parametrize('schedule,primary', [
    ('Autumn and January', 'Winter-2025'),
    ('Spring and June', 'Summer-2026'),
    ('June and July', 'Summer-2026'),
])
def test_combined_teaching_periods_can_share_an_ordinary_season(schedule, primary):
    result = classify_course(record(schedule, [sheet('Summer-2026'), sheet('Winter-2025')]))
    assert result['status'] == 'provisional'
    assert result['primary_exam']['period']['label'] == primary
    assert len(result['resit_exams']) == 1


def test_august_with_another_period_stays_unresolved():
    result = classify_course(record('June and August', [sheet('Summer-2026')]))
    assert result['primary_exam'] is None
    assert 'august_histogram_mapping_unverified' in result['reasons']


def test_only_reads_schedule_field_not_other_course_references():
    html = """<table><tr><th>Schedule:</th><td>August</td></tr>
    <tr><td></td><td>The course runs in all periods: 42500(January), 42501(June)</td></tr>
    <tr><td>Exam</td><td>Winter</td></tr></table>"""
    assert extract_schedule(html)["periods"] == ["august"]
    assert not extract_schedule(html)["contains_course_references"]


def test_unknown_periods_and_zero_results_remain_visible():
    result = classify_course(record("Spring", [
        sheet("Summer-2026"), sheet("August-2026"), sheet("Special-2025"),
        sheet("Winter-2026", 0),
    ]))
    assert result["status"] == "partial"
    assert len(result["undetermined_exams"]) == 3
    assert result["undetermined_exams"][-1]["reason"] == "no_published_results"
    assert result['resit_status'] == 'undetermined'


def test_missing_primary_does_not_fall_back_to_resit():
    result = classify_course(record("Autumn", [sheet("Summer-2026")]))
    assert result["primary_exam"] is None
    assert result["status"] == "undetermined"
    assert len(result["resit_exams"]) == 1


def test_duplicate_primary_period_across_histogram_groups_needs_review():
    result = classify_course(record("Autumn", [
        sheet("Winter-2025"), sheet("Winter-2025", group=2),
    ]))
    assert result["primary_exam"] is None
    assert "multiple_histograms_for_latest_ordinary_period" in result["reasons"]


def test_histogram_links_are_deduplicated_and_scoped_to_course():
    html = """<a href='https://karakterer.dtu.dk/Histogram/1/01001/Winter-2025'>v25</a>
    <a href='http://karakterer.dtu.dk/Histogram/1/01001/Winter-2025'>v25</a>
    <a href='http://karakterer.dtu.dk/Histogram/1/01911/Winter-2025'>v25</a>
    <a href='https://example.com/Histogram/1/01001/Winter-2025'>bad</a>"""
    links = probe.extract_histogram_links(html, "01001")
    assert len(links) == 1
    assert links[0]["link_label"] == "v25"
    assert links[0]["url"] == "https://karakterer.dtu.dk/Histogram/1/01001/Winter-2025"


@pytest.mark.asyncio
async def test_collection_records_partial_fetch_failure(monkeypatch):
    async def fetch(session, url, diagnostics=None):
        if "/Histogram/" in url:
            if "Summer" in url:
                raise ValueError("HTTP 503")
            return """<h1>Winter results</h1><table><tr><td>Course</td></tr>
            <tr><td>Participants</td><td>20</td></tr>
            <tr><td>Passed</td><td>20 (100%)</td></tr>
            <tr><td>Average</td><td>7.0</td></tr></table>
            <table></table><table><tr><th>Grade</th><th>Count</th></tr>
            <tr><td>7</td><td>20</td></tr></table>"""
        if "/info" in url:
            return """<a href='http://karakterer.dtu.dk/Histogram/1/01001/Winter-2025'>v25</a>
            <a href='http://karakterer.dtu.dk/Histogram/1/01001/Summer-2026'>s26</a>"""
        return "<h2>01001 Mathematics</h2><table><tr><td>Schedule</td><td>Autumn</td></tr></table>"

    monkeypatch.setattr(probe, "fetch_page", fetch)
    result = await probe.collect_course(None, asyncio.Semaphore(1), "01001")
    assert result["status"] == "error"
    assert result["primary_exam"]["grades"]["7"] == "20"
    assert result["undetermined_exams"][0]["error"] == "HTTP 503"
    assert result["primary_exam"]["evidence"]["headings"] == ["Winter results"]


@pytest.mark.asyncio
async def test_missing_session_writes_record_for_every_course(monkeypatch, tmp_path):
    monkeypatch.setattr(probe.config.paths, "root_dir", tmp_path)
    output = tmp_path / "report"
    assert await probe.run_probe(["01001", "01911"], output) == 1
    report = json.loads((output / "report.json").read_text())
    assert report["summary"] == {"error": 2}
    assert set(report["courses"]) == {"01001", "01911"}
    with (output / "courses.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == 2


@pytest.mark.asyncio
async def test_full_run_retains_unresolved_courses_and_scopes_cookie(monkeypatch, tmp_path):
    monkeypatch.setattr(probe.config.paths, "root_dir", tmp_path)
    (tmp_path / "secret.txt").write_text("test-session")

    async def collect(session, semaphore, course):
        assert session.cookie_jar.filter_cookies(probe.URL("https://kurser.dtu.dk"))
        assert not session.cookie_jar.filter_cookies(probe.URL("http://karakterer.dtu.dk"))
        assert not session.cookie_jar.filter_cookies(probe.URL("http://kurser.dtu.dk"))
        assert not session.cookie_jar.filter_cookies(probe.URL("https://auth.dtu.dk"))
        assert session.headers['User-Agent'] == probe.BROWSER_USER_AGENT
        assert 'Chrome/' in session.headers['User-Agent']
        result = classify_course(record("Autumn" if course == "01001" else "August", [
            sheet("Winter-2025"), sheet("Summer-2026"),
        ]))
        result["course"] = course
        return result

    monkeypatch.setattr(probe, "collect_course", collect)
    output = tmp_path / "output"
    assert await probe.run_probe(["01001", "42504"], output) == 0
    report = json.loads((output / "report.json").read_text())
    assert report["summary"] == {"provisional": 1, "undetermined": 1}
    assert "test-session" not in (output / "report.json").read_text()


@pytest.mark.asyncio
async def test_unexpected_course_failure_does_not_lose_registration(monkeypatch):
    async def broken(*args):
        raise RuntimeError("broken course page")

    monkeypatch.setattr(probe, "collect_course", broken)
    row = await probe.collect_registered_course(None, asyncio.Semaphore(1), "01001")
    assert row["course"] == "01001"
    assert row["status"] == "error"
    assert row["errors"] == [{"source": "collector", "reason": "RuntimeError"}]


class Response:
    def __init__(self, status=200, html="<h1>Results</h1>", url="https://kurser.dtu.dk"):
        self.status, self.html, self.url = status, html, url
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def text(self):
        return self.html


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return next(self.responses)


@pytest.mark.asyncio
async def test_fetch_retries_transient_failure():
    session = Session([Response(503), Response()])
    assert await probe.fetch_page(session, "https://kurser.dtu.dk") == "<h1>Results</h1>"
    assert session.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("response,reason", [
    (Response(404), "HTTP 404"),
    (Response(url="https://auth.dtu.dk/login"), "authentication_required_or_expired"),
])
async def test_fetch_distinguishes_login_and_http_failure(response, reason):
    session = Session([response])
    with pytest.raises(ValueError, match=reason):
        await probe.fetch_page(session, "https://kurser.dtu.dk")
    assert session.calls == 1


@pytest.mark.asyncio
async def test_force_login_wrapper_is_followed_once_and_diagnosed():
    url = 'https://kurser.dtu.dk/course/01001?lang=en-GB'
    wrapper = '<title>kurser.dtu.dk</title><iframe src="?forceLogin=true"></iframe>'
    target = probe.course_wrapper_url(wrapper, url)
    assert target == 'https://kurser.dtu.dk/course/01001?forceLogin=true&lang=en-GB'
    html = '<h2>01001 Mathematics</h2><table><tr><td>Schedule</td><td>Autumn</td></tr></table>'
    diagnostics = {}
    session = Session([Response(html=wrapper, url=url), Response(html=html, url=target)])
    assert await probe.fetch_page(session, url, diagnostics) == html
    assert session.calls == 2
    assert diagnostics['attempts'][0]['page']['iframe_count'] == 1
    assert diagnostics['attempts'][1]['page']['table_labels'] == ['Schedule']
    assert diagnostics['attempts'][1]['final_url'] == target


@pytest.mark.asyncio
async def test_repeated_wrapper_fails_instead_of_becoming_missing_schedule():
    url = 'https://kurser.dtu.dk/course/01001?lang=en-GB'
    html = '<iframe src="?forceLogin=true"></iframe>'
    session = Session([Response(html=html, url=url), Response(html=html, url=url)])
    with pytest.raises(ValueError, match='authentication_wrapper_unresolved'):
        await probe.fetch_page(session, url)
    assert session.calls == 2


def test_wrapper_does_not_follow_other_hosts_or_other_course_paths():
    url = 'https://kurser.dtu.dk/course/01001'
    assert probe.course_wrapper_url('<iframe src="https://example.com/course/01001?forceLogin=true"></iframe>', url) is None
    assert probe.course_wrapper_url('<iframe src="/course/01911?forceLogin=true"></iframe>', url) is None
    assert probe.diagnostic_url('https://auth.dtu.dk/login?token=secret&lang=en-GB') == 'https://auth.dtu.dk/login?lang=en-GB'


@pytest.mark.asyncio
async def test_unrecognized_success_response_is_a_collection_error(monkeypatch):
    async def fetch(session, url, diagnostics=None):
        return '<title>Unexpected page</title>'
    monkeypatch.setattr(probe, 'fetch_page', fetch)
    row = await probe.collect_course(None, asyncio.Semaphore(1), '01001')
    assert row['status'] == 'error'
    assert {e['reason'] for e in row['errors']} == {'course_page_unrecognized', 'info_page_unrecognized'}


def test_primary_without_resit_links_is_successful_but_does_not_claim_no_resits_exist():
    row = classify_course(record('Spring', [sheet('Summer-2026')]))
    assert row['status'] == 'provisional'
    assert row['primary_status'] == 'identified'
    assert row['resit_status'] == 'none_found_in_collected_links'


def test_count_check_detects_missing_source_categories_and_registration_mismatch():
    sheet = {'Bestået': '575', 'Ikkebestået': '127', 'Godkendt': '0',
             'IkkeGodkendt': '45', 'Ejmødt': '57', 'participants': 804}
    assert probe.result_count_check(sheet) == {
        'source_total': 804, 'retained_total': 804, 'participants': 804,
        'all_categories_retained': True, 'matches_participants': True,
        'grading_scale': 'pass_fail',
    }
    sheet['UnknownOutcome'] = '1'
    check = probe.result_count_check(sheet)
    assert not check['all_categories_retained']
    assert not check['matches_participants']


def test_report_summary_flags_mixed_grading_histograms(tmp_path):
    counts = probe.result_count_check({
        '7': '1', 'Bestået': '8', 'Ikkebestået': '1', 'participants': 10,
    })
    report = {'courses': {'01001': {
        'status': 'provisional', 'primary_status': 'identified',
        'resit_status': 'none_found_in_collected_links', 'schedule': {},
        'primary_exam': None, 'exams': [{
            'url': 'https://karakterer.dtu.dk/Histogram/1/01001/Summer-2025',
            'period': {'label': 'Summer-2025'}, 'result_counts': counts,
        }], 'resit_exams': [], 'undetermined_exams': [], 'reasons': [], 'errors': [],
    }}}
    probe.write_reports(report, tmp_path)
    assert counts['grading_scale'] == 'mixed'
    assert 'Mixed numeric/pass-fail histograms requiring review: 1' in (
        tmp_path / 'summary.md').read_text()
