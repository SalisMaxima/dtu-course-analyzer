import asyncio
import copy
import json

import pytest

from dtu_analyzer.analysis.exam_classification import parse_period, schedule_from_text
from dtu_analyzer.analysis.publication_guard import publication_issues
from dtu_analyzer.scripts.build_chrome_beta import build_dataset
from dtu_analyzer.scripts import probe_exam_classification as probe
from dtu_analyzer.scripts.build_production_candidate import main


def report(course, sources, schedule="Autumn"):
    exams = []
    for source, period in sources:
        url = f"https://karakterer.dtu.dk/Histogram/1/{source}/{period}"
        exams.append({"url": url, "period": parse_period(url), "distribution_status": "published",
                      "histogram_course": source, "grades": {"7": "10", "participants": 10,
                                                               "avg": 7, "pass_percentage": 100}})
    return {"finished_at": "2026-09-08", "courses": {course: {
        "course": course, "status": "partial", "schedule": schedule_from_text(schedule),
        "errors": [], "exams": exams,
        "pages": {"info": {"content": {"state": "no_links_unknown", "evaluation_link_count": 0}}}}}}


def test_reviewed_npe_is_unknown_and_does_not_mask_failures():
    evidence = report("10415", [])
    data = build_dataset({}, [evidence])
    assert "Availability is unknown" in data["10415"]["exam_default_note"]
    assert publication_issues({}, data, evidence, ["10415"]) == []
    evidence["courses"]["10415"]["errors"] = [{"reason": "authentication_failed"}]
    assert any(i["reason"] == "course_collection_failed" for i in publication_issues({}, data, evidence, ["10415"]))


def test_twice_yearly_course_uses_latest_of_both_regular_seasons():
    data = build_dataset({}, [report("12952", [("12950", "Winter-2025"), ("12950", "Summer-2026")], "Spring Autumn")])["12952"]
    assert data["default_exam_id"].endswith("Summer-2026")
    assert all(e["classification"] == "ordinary_candidate" for e in data["exam_history"])
    same_year = build_dataset({}, [report("12952", [("12950", "Winter-2025"), ("12950", "Summer-2025")], "Spring Autumn")])["12952"]
    assert same_year["default_exam_id"].endswith("Winter-2025")


def test_historical_regular_override_survives_current_schedule_change():
    data = build_dataset({}, [report("02581", [("02580", "Summer-2025")])])["02581"]
    assert data["default_exam_id"].endswith("Summer-2025")
    assert "historical offering" in data["exam_default_note"]


def test_predecessor_preference_keeps_all_sources_without_aggregation():
    data = build_dataset({}, [report("62237", [("62234", "Winter-2024"), ("62236", "Winter-2025")])])["62237"]
    assert data["default_exam_id"].endswith("62236/Winter-2025")
    assert len(data["exam_history"]) == 2
    assert data["grade_participants"] == 10


@pytest.mark.parametrize("course,source", [("62776", "62775"), ("MA776", "62775"),
                                          ("27827", "29905"), ("MA263", "41263")])
def test_reviewed_shared_and_historical_sources_are_usable(course, source):
    data = build_dataset({}, [report(course, [(source, "Winter-2025")])])[course]
    assert data["default_exam_id"].endswith(f"{source}/Winter-2025")
    assert data["grade_participants"] == 10


@pytest.mark.parametrize("course,source", [("25623", "25617"), ("22170", "27692")])
def test_excluded_predecessor_remains_in_evidence_only(course, source):
    evidence = report(course, [(source, "Winter-2023")])
    original = copy.deepcopy(evidence)
    data = build_dataset({}, [evidence])[course]
    assert data["default_exam_id"] is None and data["exam_history"] == []
    assert "excluded" in data["exam_default_note"]
    assert evidence == original


@pytest.mark.asyncio
async def test_approved_shared_history_is_fetched_when_current_course_has_no_links(monkeypatch):
    calls = []
    async def fetch(session, url, diagnostics=None):
        calls.append(url)
        if "/Histogram/" in url:
            return "<p>Fordelingen vises ikke da tre eller færre har været til denne eksamen.</p>"
        if "/course/12950/info" in url:
            return '<a href="https://karakterer.dtu.dk/Histogram/1/12950/Summer-2026">s26</a>'
        if "/info" in url:
            return "<p>12952</p>"
        return "<h2>12952</h2><table><tr><td>Schedule</td><td>Spring Autumn</td></tr></table>"
    monkeypatch.setattr(probe, "fetch_page", fetch)
    row = await probe.collect_course(None, asyncio.Semaphore(1), "12952")
    assert len(row["exams"]) == 1
    assert row["primary_exam"]["url"].endswith("12950/Summer-2026")
    assert any("/course/12950/info" in u for u in calls)


def test_new_predecessor_is_discovered_but_not_automatically_approved():
    html = '<p>99999 Prior course: 88888</p><a href="https://karakterer.dtu.dk/Histogram/1/88888/Winter-2025">v25</a>'
    info = probe.info_evidence(html, "https://kurser.dtu.dk/course/99999/info", "99999")
    assert info["predecessor_courses"] == ["88888"]
    row = report("99999", [("88888", "Winter-2025")])
    assert build_dataset({}, [row])["99999"]["default_exam_id"] is None


def test_production_command_dry_run_and_incomplete_feedback_protection(tmp_path):
    evidence = report("10415", [])
    ext = tmp_path / "extension"
    (ext / "db").mkdir(parents=True)
    (ext / "manifest.json").write_text('{}')
    original = '{}\n'
    (ext / "db/data.json").write_text(original)
    (tmp_path / "raw.json").write_text('{}')
    (tmp_path / "courses.txt").write_text('10415\n')
    path = tmp_path / "report.json"
    path.write_text(json.dumps(evidence))
    args = ["--raw", str(tmp_path / "raw.json"), "--report", str(path),
            "--course-file", str(tmp_path / "courses.txt"), "--extension", str(ext),
            "--output", str(tmp_path / "candidate")]
    assert main(args) == 0
    assert (ext / "db/data.json").read_text() == original
    assert json.loads((tmp_path / "candidate/validation.json").read_text())["publishable"]
    evidence["courses"]["10415"]["pages"]["info"]["content"]["evaluation_link_count"] = 1
    path.write_text(json.dumps(evidence))
    args[-1] = str(tmp_path / "failed")
    assert main(args + ["--publish"]) == 1
    assert (ext / "db/data.json").read_text() == original
    assert not json.loads((tmp_path / "failed/validation.json").read_text())["publishable"]
