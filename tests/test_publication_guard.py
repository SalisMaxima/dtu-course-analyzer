import copy
import json
from pathlib import Path

import pytest

from dtu_analyzer.analysis.publication_guard import publication_issues, publish_candidate
from dtu_analyzer.scripts.build_chrome_beta import build_dataset


@pytest.fixture
def evidence():
    return json.loads((Path(__file__).parent / "fixtures/exam_pipeline_cases.json").read_text())


def primary(data, course):
    return next(e for e in data[course]["exam_history"] if e["id"] == data[course]["default_exam_id"])


def test_representative_saved_cases(evidence):
    data = build_dataset({}, [evidence])
    assert primary(data, "01001")["grade_period"] == "Winter-2025"
    assert data["01001"]["exam_history"][0]["classification"] == "resit_candidate"
    assert primary(data, "01020")["grade_period"] == "Summer-2026"
    assert data["01020"]["grades"] == {"passed": "79", "not_passed": "7", "absent": "6"}
    assert data["01020"]["passpercent"] == 85
    assert "avg" not in data["01020"] and "avgp" not in data["01020"]
    assert primary(data, "01426")["distribution_status"] == "suppressed"
    assert not {"grades", "avg", "avgp", "passpercent"} & data["01426"].keys()
    for course, source, period in [("02280", "02285", "Summer-2026"),
                                   ("02426", "02424", "Summer-2024"),
                                   ("23103", "23102", "Summer-2026"),
                                   ("23104", "23102", "Summer-2026")]:
        exam = primary(data, course)
        assert exam["histogram_course"] == source
        assert exam["grade_period"] == period
        assert exam["identity_status"] == "manually_approved_history"
    assert data["23103"]["grades"] == data["23104"]["grades"]
    assert data["23103"]["grade_participants"] == data["23104"]["grade_participants"] == 53
    for course in ("01822", "02262"):
        assert data[course]["exam_history"] == []
        assert data[course]["default_exam_id"] is None
        assert "New course" in data[course]["exam_default_note"]
    for course in ("01037", "01666", "01025"):
        assert data[course]["default_exam_id"] is None
        assert data[course]["exam_history"]
    assert all(e["identity_status"] == "variant_requires_review" for e in data["01025"]["exam_history"])


@pytest.mark.parametrize("failure", ["auth", "unfinished", "missing_course", "missing_schedule",
                                    "failed_histogram", "course_error", "lost_history",
                                    "changed_counts", "lost_feedback", "unknown_no_links",
                                    "missing_candidate_course", "lost_default", "lost_category", "pending"])
def test_failed_updates_leave_published_bytes_untouched(tmp_path, evidence, failure):
    previous = build_dataset({"01001": {"qualityscore": 80}}, [evidence])
    candidate = copy.deepcopy(previous)
    if failure == "auth":
        evidence["fatal_error"] = "authentication_required_or_expired"
    elif failure == "unfinished":
        del evidence["finished_at"]
    elif failure == "missing_course":
        del evidence["courses"]["01001"]
    elif failure == "missing_schedule":
        evidence["courses"]["01001"]["schedule"] = {}
    elif failure == "failed_histogram":
        evidence["courses"]["01001"]["exams"][0]["distribution_status"] = "failed"
    elif failure == "course_error":
        evidence["courses"]["01001"]["errors"] = [{"reason": "network_error_or_timeout"}]
    elif failure == "lost_history":
        candidate["01001"]["exam_history"].pop()
    elif failure == "changed_counts":
        candidate["01020"]["grades"]["passed"] = "800"
    elif failure == "lost_feedback":
        del candidate["01001"]["qualityscore"]
    elif failure == "unknown_no_links":
        evidence["courses"]["01001"]["exams"] = []
        evidence["courses"]["01001"]["pages"] = {}
    elif failure == "missing_candidate_course":
        del candidate["01001"]
    elif failure == "lost_default":
        candidate["01001"]["default_exam_id"] = None
    elif failure == "lost_category":
        evidence["courses"]["01001"]["exams"][0]["result_counts"]["all_categories_retained"] = False
    elif failure == "pending":
        evidence["courses"]["01001"]["status"] = "pending"
    destination = tmp_path / "data.json"
    original = json.dumps(previous, indent=2).encode()
    destination.write_bytes(original)
    with pytest.raises(ValueError):
        publish_candidate(destination, candidate, evidence, previous.keys())
    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]


def test_valid_update_accepts_suppression_ambiguity_and_source_discrepancy(tmp_path, evidence):
    # A source discrepancy is diagnostic information, not a missing category.
    exam = evidence["courses"]["01001"]["exams"][0]
    exam["grades"]["participants"] += 1
    exam["result_counts"]["matches_participants"] = False
    base = {"01001": {"qualityscore": 80}}
    previous = build_dataset(base, [evidence])
    candidate = build_dataset({"01001": {"qualityscore": 81}}, [evidence])
    assert publication_issues(previous, candidate, evidence, previous.keys()) == []
    destination = tmp_path / "data.json"
    destination.write_text(json.dumps(previous))
    publish_candidate(destination, candidate, evidence, previous.keys())
    assert json.loads(destination.read_text()) == candidate
    assert candidate["01001"]["exam_history"][0]["participant_difference"] == 1


def test_atomic_write_failure_preserves_previous_dataset(tmp_path, evidence, monkeypatch):
    data = build_dataset({}, [evidence])
    destination = tmp_path / "data.json"
    original = json.dumps(data).encode()
    destination.write_bytes(original)
    def fail(*args):
        raise OSError("simulated replacement failure")
    monkeypatch.setattr("dtu_analyzer.analysis.publication_guard.os.replace", fail)
    with pytest.raises(OSError):
        publish_candidate(destination, data, evidence, data.keys())
    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]


def test_explicit_no_results_is_valid_but_unexplained_absence_is_blocked(evidence):
    row = copy.deepcopy(evidence["courses"]["01822"])
    row["course"] = "99999"
    row["pages"] = {"info": {"content": {"state": "no_published_results"}}}
    report = {"finished_at": "2026-09-08", "courses": {"99999": row}}
    candidate = build_dataset({}, [report])
    assert publication_issues({}, candidate, report, ["99999"]) == []
    row["pages"]["info"]["content"]["state"] = "no_links_unknown"
    assert any(i["reason"] == "absence_of_results_unconfirmed"
               for i in publication_issues({}, candidate, report, ["99999"]))
