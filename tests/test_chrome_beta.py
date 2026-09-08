import copy

import pytest

from dtu_analyzer.scripts.build_chrome_beta import build_dataset
from dtu_analyzer.analysis.exam_classification import schedule_from_text, parse_period


def exam(source, period, status="published"):
    url = f"https://karakterer.dtu.dk/Histogram/1/{source}/{period}"
    return {"url": url, "period": parse_period(url), "distribution_status": status,
            "grades": {"participants": 10, "7": "8", "00": "2", "avg": 5.6, "pass_percentage": 80}
            if status == "published" else None}


def report(course, source, schedule="Spring"):
    return {"finished_at": "2026-09-08", "courses": {course: {
        "course": course, "schedule": schedule_from_text(schedule),
        "exams": [exam(source, "Summer-2026"), exam(source, "Winter-2025")], "errors": [],
    }}}


@pytest.mark.parametrize("course,source", [("02280", "02285"), ("02426", "02424"),
                                          ("23103", "23102"), ("23104", "23102")])
def test_reviewed_history_is_used_without_changing_source_counts(course, source):
    data = build_dataset({}, [report(course, source)])[course]
    assert data["default_exam_id"].endswith(f"/{source}/Summer-2026")
    assert data["grade_participants"] == 10
    assert data["grades"] == {"7": "8", "00": "2"}
    assert data["exam_history"][0]["identity_status"] == "manually_approved_history"
    assert "avgp" in data


def test_default_is_regular_not_newer_resit_or_larger_cohort():
    data = build_dataset({}, [report("01001", "01001", "Autumn")])["01001"]
    assert data["default_exam_id"].endswith("Winter-2025")
    assert data["exam_history"][0]["classification"] == "resit_candidate"


def test_hidden_primary_clears_legacy_metrics_and_never_falls_back():
    source = report("01001", "01001", "Autumn")
    source["courses"]["01001"]["exams"][1] = exam("01001", "Winter-2025", "suppressed")
    base = {"01001": {"avg": 12, "avgp": 100, "grades": {"12": "100"}, "passpercent": 100, "qualityscore": 80}}
    data = build_dataset(base, [source])["01001"]
    assert data["default_exam_id"].endswith("Winter-2025")
    assert not {"avg", "avgp", "grades", "passpercent"} & data.keys()
    assert data["qualityscore"] == 80


def test_unapproved_variant_requires_selection_and_new_courses_explain_absence():
    records = report("01025", "01025-2")
    records["courses"]["01822"] = {"course": "01822", "schedule": {}, "exams": []}
    data = build_dataset({}, [records])
    assert data["01025"]["default_exam_id"] is None
    assert len(data["01025"]["exam_history"]) == 2
    assert "New course" in data["01822"]["exam_default_note"]


def test_ambiguous_schedule_has_no_automatic_default():
    data = build_dataset({}, [report("99999", "99999", "Spring and Autumn")])["99999"]
    assert data["default_exam_id"] is None
    assert "Regular exam could not be determined" in data["exam_default_note"]


def test_report_precedence_and_shared_history_are_not_aggregated():
    a = report("23103", "23102")
    b = report("23104", "23102")
    original = copy.deepcopy(a)
    data = build_dataset({}, [a, b])
    assert a == original
    assert data["23103"]["grade_participants"] == data["23104"]["grade_participants"] == 10
    newer = copy.deepcopy(a)
    newer["courses"]["23103"]["exams"] = [exam("23102", "Summer-2025")]
    assert build_dataset({}, [a, newer])["23103"]["default_exam_id"].endswith("Summer-2025")
