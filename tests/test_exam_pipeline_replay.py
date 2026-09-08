import json

import pytest

from dtu_analyzer.scripts.check_exam_pipeline import compare_datasets, main


def test_comparison_detects_missing_courses_counts_defaults_and_feedback():
    expected = {"01001": {"exam_history": [{"grades": {"7": "8"}}],
                           "default_exam_id": "winter", "qualityscore": 80}, "01002": {}}
    candidate = {"01001": {"exam_history": [{"grades": {"7": "9"}}],
                            "default_exam_id": "summer", "qualityscore": 81}, "01003": {}}
    result = compare_datasets(expected, candidate)
    assert not result["matches"]
    assert result["missing_courses"] == ["01002"]
    assert result["added_courses"] == ["01003"]
    assert result["changed_fields_by_course"]["01001"] == ["default_exam_id", "exam_history", "qualityscore"]


def test_comparison_distinguishes_absent_field_from_null():
    assert not compare_datasets({"01001": {}}, {"01001": {"avg": None}})["matches"]


def test_replay_writes_isolated_artifacts_and_returns_failure_for_differences(tmp_path):
    inputs = {"base": {}, "report": {"courses": {}}, "expected": {}}
    for name, value in inputs.items():
        (tmp_path / name).write_text(json.dumps(value))
    args = ["--base", str(tmp_path / "base"), "--report", str(tmp_path / "report"),
            "--expected", str(tmp_path / "expected"), "--output", str(tmp_path / "result")]
    before = {name: (tmp_path / name).read_bytes() for name in inputs}
    assert main(args) == 0
    assert json.loads((tmp_path / "result/comparison.json").read_text())["matches"]
    assert before == {name: (tmp_path / name).read_bytes() for name in inputs}
    with pytest.raises(SystemExit):
        main(args)
    (tmp_path / "expected").write_text('{"01001": {}}')
    args[-1] = str(tmp_path / "mismatch")
    assert main(args) == 1
