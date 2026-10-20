import asyncio
import json
from pathlib import Path

import pytest

from tests.test_exam_classification import Response, Session
from tests.test_maintainer_pipeline import report
from dtu_analyzer.scripts import probe_exam_classification as probe
from dtu_analyzer.scripts.build_chrome_beta import build_dataset
from dtu_analyzer.analysis.publication_guard import publication_issues


@pytest.mark.asyncio
async def test_login_wrapper_failure_retries_original_public_url(monkeypatch):
    async def no_wait(*args):
        pass
    monkeypatch.setattr(probe.asyncio, "sleep", no_wait)
    url = "https://kurser.dtu.dk/course/12601?lang=en-GB"
    session = Session([Response(html='<iframe src="?forceLogin=true"></iframe>', url=url),
                       Response(url="https://auth.dtu.dk/login"), Response(html="public", url=url)])
    requested = []
    get = session.get
    def track(url, **kwargs):
        requested.append(url)
        return get(url, **kwargs)
    session.get = track
    assert await probe.fetch_page(session, url) == "public"
    assert requested[0] == requested[2] == url
    assert "forceLogin=true" in requested[1]


def test_reviewed_404_is_excluded_but_other_errors_still_block():
    evidence = report("22461", [("22433", "Summer-2023"), ("22433", "Winter-2023")])
    bad = evidence["courses"]["22461"]["exams"][0]
    bad.update(error="HTTP 404", distribution_status="failed", grades=None)
    evidence["courses"]["22461"] = probe.classify_course(evidence["courses"]["22461"])
    data = build_dataset({}, [evidence])
    assert len(data["22461"]["exam_history"]) == 1
    assert data["22461"]["default_exam_id"].endswith("Winter-2023")
    assert not publication_issues({}, data, evidence, ["22461"])
    bad = evidence["courses"]["22461"]["exams"][0]
    bad["error"] = "network_error_or_timeout"
    assert publication_issues({}, data, evidence, ["22461"])


def test_22181_uses_reviewed_winter_despite_current_spring_schedule():
    data = build_dataset({}, [report("22181", [("22180", "Winter-2025"), ("22180", "Summer-2024")], "Spring")])
    assert data["22181"]["default_exam_id"].endswith("Winter-2025")


@pytest.mark.asyncio
async def test_missing_previously_collected_suppressed_exam_is_refetched(monkeypatch):
    urls = []
    async def fetch(session, url, diagnostics=None):
        urls.append(url)
        if "/Histogram/" in url:
            return "<p>Fordelingen vises ikke da tre eller færre har været til denne eksamen.</p>"
        if "/info" in url:
            return '<p>25205</p><a href="https://karakterer.dtu.dk/Histogram/1/25205/Summer-2026">s26</a>'
        return '<h2>25205</h2><table><tr><td>Schedule</td><td>Spring</td></tr></table>'
    monkeypatch.setattr(probe, "fetch_page", fetch)
    row = await probe.collect_course(None, asyncio.Semaphore(1), "25205")
    assert len(row["exams"]) == 2
    assert any(u.endswith("Summer-2022") for u in urls)
    assert all(e["distribution_status"] == "suppressed" and not e.get("grades") for e in row["exams"])


def suppress(evidence, course, period):
    for exam in evidence["courses"][course]["exams"]:
        if exam["period"]["label"] == period:
            exam.update(distribution_status="suppressed", grades=None)
    return evidence


def test_reviewed_default_skips_suppressed_winter_2026():
    evidence = suppress(report("02289", [("02289", "Winter-2026"), ("02289", "Winter-2025")]), "02289", "Winter-2026")
    data = build_dataset({}, [evidence])["02289"]
    assert data["default_exam_id"].endswith("02289/Winter-2025")
    assert data["exam_default_note"] == "Default exam chosen by maintainer review."
    assert data["grade_participants"] == 10


def test_reviewed_no_default_keeps_predecessor_history_selectable():
    evidence = suppress(report("30224", [("30224", "Summer-2026"), ("30220", "Winter-2025")], "Spring"),
                        "30224", "Summer-2026")
    data = build_dataset({}, [evidence])["30224"]
    assert data["default_exam_id"] is None
    assert "too few participants" in data["exam_default_note"]
    predecessor = next(e for e in data["exam_history"] if e["histogram_course"] == "30220")
    assert predecessor["identity_status"] == "manually_approved_history"


@pytest.mark.parametrize("sources, suppressed", [
    ([("30224", "Summer-2027"), ("30224", "Summer-2026")], "Summer-2026"),
    ([("30224", "Summer-2026")], None),
])
def test_no_default_expires_once_evidence_no_longer_holds(sources, suppressed):
    evidence = report("30224", sources, "Spring")
    if suppressed:
        suppress(evidence, "30224", suppressed)
    data = build_dataset({}, [evidence])["30224"]
    assert data["default_exam_id"] == f"https://karakterer.dtu.dk/Histogram/1/{'/'.join(sources[0])}"
    assert "too few participants" not in data["exam_default_note"]

def test_only_approved_history_removals_pass():
    evidence = report("01037", [("01037", "Summer-2026")])
    candidate = build_dataset({}, [evidence])
    previous = build_dataset({}, [report("01037", [("01037", "Summer-2026"), ("01037", "Summer-2024")])])
    assert not any(i["reason"] == "previous_exam_history_lost"
                   for i in publication_issues(previous, candidate, evidence, ["01037"]))
    previous = build_dataset({}, [report("01037", [("01037", "Summer-2026"), ("01037", "Summer-2023")])])
    assert {"course": "01037", "reason": "previous_exam_history_lost"} in publication_issues(
        previous, candidate, evidence, ["01037"])


def test_only_reviewed_removed_course_may_disappear():
    evidence = report("01037", [("01037", "Summer-2026")])
    candidate = build_dataset({}, [evidence])
    previous = {**candidate, "34764": {"qualityscore": 80, "exam_history": []}}
    assert not any(i["course"] == "34764" for i in publication_issues(previous, candidate, evidence, ["01037"]))
    previous = {**candidate, "34765": {"exam_history": []}}
    assert {"course": "34765", "reason": "course_missing_from_candidate"} in publication_issues(
        previous, candidate, evidence, ["01037"])


def test_accepted_refresh_applies_only_to_reviewed_baseline():
    from dtu_analyzer.analysis.course_history_reviews import ACCEPTED_REFRESH_BASELINE_SHA256 as reviewed
    evidence = report("62000", [("62000", "Winter-2025")])
    candidate = build_dataset({}, [evidence])
    previous = build_dataset({}, [report("62000", [("62000", "Winter-2025"), ("62000", "Winter-2022")])])
    assert not publication_issues(previous, candidate, evidence, ["62000"], reviewed)
    assert {"course": "62000", "reason": "previous_exam_history_lost"} in publication_issues(
        previous, candidate, evidence, ["62000"], "0" * 64)


def test_reviewed_evaluation_overrides_participant_heuristic():
    from dtu_analyzer.analysis.analyzer import process_courses
    def sheet(review_id, participants):
        return {"url": f"https://evaluering.dtu.dk/kursus/42620/{review_id}",
                "participants": participants, "firstOption": "Helt enig"}
    raw = {"42620": {"reviews": [sheet(367466, 300), sheet(355671, 211)]},
           "42621": {"reviews": [sheet(367466, 300), sheet(355671, 211)]}}
    data = process_courses(raw)
    assert data["42620"]["review_participants"] == 211
    assert data["42621"]["review_participants"] == 300
