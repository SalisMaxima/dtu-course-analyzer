import asyncio
import copy
import csv
import json
from pathlib import Path

import pytest

from dtu_analyzer.analysis.exam_classification import classify_course, extract_schedule, schedule_from_text
from dtu_analyzer.scripts import probe_exam_classification as probe

FIXTURES = Path(__file__).parent / "fixtures"


def exam(period):
    url = f"https://karakterer.dtu.dk/Histogram/1/01001/{period}"
    return {"url": url, "period": probe.parse_period(url)}


def test_latest_hidden_exam_remains_primary_and_has_no_invented_counts():
    latest = exam("Winter-2025")
    probe.read_distribution(latest, (FIXTURES / "suppressed-histogram.html").read_text())
    older = exam("Winter-2024")
    older.update(grades={"participants": 20}, distribution_status="published")
    resit = {**copy.deepcopy(latest), **exam("Summer-2026")}
    row = classify_course({"schedule": schedule_from_text("Autumn"), "exams": [older, latest, resit]})
    assert row["status"] == "provisional"
    assert row["primary_exam"]["period"]["label"] == "Winter-2025"
    assert row["primary_exam"]["distribution_status"] == "suppressed"
    assert row["primary_exam"]["grades"] is None
    assert "result_counts" not in row["primary_exam"]
    assert row["resit_exams"][0]["distribution_status"] == "suppressed"


def test_invalid_distribution_is_still_a_real_error():
    item = exam("Winter-2025")
    probe.read_distribution(item, "<h2>Unknown results markup</h2>")
    row = classify_course({"schedule": schedule_from_text("Autumn"), "exams": [item]})
    assert row["status"] == "error"
    assert row["exams"][0]["distribution_status"] == "failed"


def test_structured_schedule_excludes_other_course_months():
    schedule = extract_schedule((FIXTURES / "schedule-references.html").read_text(), "01034")
    assert schedule["explicit"] == "Autumn E1A (Mon 8-12)"
    assert schedule["basis"] == "structured_schedule"
    assert "August" in schedule["explanation"]
    assert schedule["periods"] == ["autumn"]
    assert schedule["referenced_courses"] == ["01035", "01037"]
    assert not schedule["ambiguous_explanation"]
    row = classify_course({"schedule": schedule, "exams": [dict(exam("Winter-2025"), grades={"participants": 20})]})
    assert row["primary_status"] == "identified"


@pytest.mark.parametrize("text,course,periods,ambiguous", [
    ("Autumn and January Teaching takes place in January 2027.", "01911", ["autumn", "january"], False),
    ("Spring and June", "02443", ["spring", "june"], False),
    ("Spring and Autumn", "01001", ["autumn", "spring"], False),
    ("Spring F5B (Wed 13-17) and June In special cases also in the fall term.", "01666", ["spring", "june"], True),
    ("August Other versions are 42500(January), 42501(June).", "42504", ["august"], False),
    ("June The course 02443 also runs in Autumn.", "02443", ["june"], True),
    ("Course 42500(January) or 42501(June)", "42504", ["january", "june"], True),
])
def test_schedule_text_fallback_is_conservative(text, course, periods, ambiguous):
    schedule = schedule_from_text(text, course)
    assert schedule["periods"] == periods
    assert schedule["ambiguous_explanation"] == ambiguous
    assert course not in schedule["referenced_courses"]


@pytest.mark.parametrize("html,state", [
    ("", "empty_response"),
    ("<h2>01001 Results</h2><p>No published results available</p>", "no_published_results"),
    ("<h2>01001 Results</h2>", "no_links_unknown"),
    ("<title>Unexpected page</title>", "info_page_unrecognized"),
    ('<form><input type="password"></form>', "authentication_required_or_expired"),
])
def test_info_page_states(html, state):
    assert probe.info_evidence(html, "https://kurser.dtu.dk/course/01001/info", "01001")["state"] == state


def test_info_evidence_is_bounded_and_does_not_store_credentials():
    html = """<h2>01001 Results</h2><script>secret_token</script>
    <form>private_grade_details<input value="password"></form>
    <a href="https://user:secret@karakterer.dtu.dk/Histogram/1/01001/Summer-2026?token=secret#private">Grades</a>
    <a href="https://auth.dtu.dk/private/token">Login</a>
    <p>Contact grades@example.com</p>""" + "<p>Exam results " + "x" * 2000 + "</p>"
    result = probe.info_evidence(html, "https://kurser.dtu.dk/course/01001/info", "01001")
    serialized = json.dumps(result)
    assert all(value not in serialized for value in ["secret", "password", "private", "grades@example"])
    assert result["relevant_links"] == ["https://karakterer.dtu.dk/Histogram/1/01001/Summer-2026"]
    assert all(len(e) <= 250 for e in result["course_content_excerpts"])


@pytest.mark.asyncio
async def test_explicit_no_results_is_not_collection_error(monkeypatch):
    async def fetch(session, url, diagnostics=None):
        if "/info" in url:
            return "<p>No published results available</p>"
        return "<h2>01001 Course</h2><table><tr><th>Schedule</th><td>Autumn</td></tr></table>"
    monkeypatch.setattr(probe, "fetch_page", fetch)
    row = await probe.collect_course(None, asyncio.Semaphore(1), "01001")
    assert row["status"] == "undetermined"
    assert row["errors"] == []
    assert row["pages"]["info"]["content"]["state"] == "no_published_results"


def test_offline_replay_preserves_source_and_reports_availability(tmp_path):
    item = exam("Winter-2025")
    item.update(error="histogram_parse_failed", grades=None, evidence={"tables": [
        "Fordelingen vises ikke da tre eller færre har været til denne eksamen."]})
    source = tmp_path / "report.json"
    original = json.dumps({"schema_version": 2, "courses": {"01001": {
        "schedule": {"raw": "Autumn"}, "exams": [item], "errors": []}}})
    source.write_text(original)
    result = probe.replay_report(source, tmp_path / "replayed")
    assert source.read_text() == original
    assert result["schema_version"] == 3
    assert result["distribution_summary"] == {"suppressed": 1}
    assert result["summary"] == {"provisional": 1}
    with (tmp_path / "replayed/courses.csv").open() as stream:
        row = next(csv.DictReader(stream))
    assert row["primary_distribution_status"] == "suppressed"
    assert row["suppressed_histograms"] == "1"
    with pytest.raises(ValueError):
        probe.replay_report(source, tmp_path)


def test_source_discrepancy_is_separate_from_category_loss():
    result = probe.result_count_check({"7": "30", "participants": 35})
    assert result["all_categories_retained"]
    assert not result["matches_participants"]
    assert result["participant_difference"] == 5
    result = probe.result_count_check({"7": "30", "Unknown": "5", "participants": 35})
    assert not result["all_categories_retained"]
    assert result["matches_participants"]


def test_words_before_parentheses_are_not_course_codes():
    schedule = schedule_from_text("Spring F2B (Thurs 8-12) Other (optional) sessions.", "01001")
    assert schedule["referenced_courses"] == []


@pytest.mark.asyncio
async def test_request_records_content_metadata_but_not_login_content():
    from tests.test_exam_classification import Response, Session
    response = Response(html="<h2>01001 Grades</h2>")
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    diagnostics = {}
    await probe.fetch_page(Session([response]), "https://kurser.dtu.dk", diagnostics)
    attempt = diagnostics["attempts"][0]
    assert attempt["content_type"] == response.headers["Content-Type"]
    assert attempt["response_bytes"] == len(response.html.encode("utf-8"))
    diagnostics = {}
    with pytest.raises(ValueError, match="authentication_required"):
        await probe.fetch_page(Session([Response(html='<form><input type="password" value="secret"></form>')]),
                               "https://kurser.dtu.dk", diagnostics)
    assert diagnostics["attempts"][0]["state"] == "authentication_required_or_expired"
    assert "page" not in diagnostics["attempts"][0]
    assert "secret" not in json.dumps(diagnostics)


def test_unrelated_other_course_reference_cannot_hide_own_extra_period():
    schedule = schedule_from_text("Spring The course also runs in Autumn and requires course 01037.", "01001")
    assert schedule["ambiguous_explanation"]
    row = classify_course({"schedule": schedule, "exams": [dict(exam("Summer-2026"), grades={"participants": 10})]})
    assert row["status"] == "undetermined"


def test_continuation_with_own_additional_period_requires_review():
    schedule = extract_schedule("<table><tr><td>Schedule</td><td>Spring</td></tr>"
                                "<tr><td></td><td>This course also runs in Autumn.</td></tr></table>", "01001")
    assert schedule["ambiguous_explanation"]
    assert "Autumn" in schedule["explanation"]
