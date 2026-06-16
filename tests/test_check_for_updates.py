import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import dtu_analyzer.scripts.check_for_updates as checker


def test_resolve_baseline_file_prefers_updated_data_file(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "coursedic.json"
    legacy_file = tmp_path / "source-code" / "coursedic.json"
    data_file.parent.mkdir()
    legacy_file.parent.mkdir()
    data_file.write_text("{}")
    legacy_file.write_text("{}")

    assert checker.resolve_baseline_file(data_file, legacy_file) == data_file


def test_resolve_baseline_file_returns_primary_when_both_missing(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "coursedic.json"
    legacy_file = tmp_path / "source-code" / "coursedic.json"

    assert checker.resolve_baseline_file(data_file, legacy_file) == data_file


def test_select_probe_courses_uses_all_current_courses_by_default() -> None:
    coursedic = {
        "11111": {"grades": [{"participants": 2}]},
        "22222": {"grades": [{"participants": 200}]},
        "33333": {"grades": []},
        "44444": {"grades": [{"participants": 100}]},
    }

    selected = checker.select_probe_courses(coursedic, {"11111", "22222", "33333"})

    assert selected == ["11111", "22222"]


def test_select_probe_courses_can_be_capped_by_recent_activity() -> None:
    coursedic = {
        "11111": {"grades": [{"participants": 2}]},
        "22222": {"grades": [{"participants": 1}, {"participants": 200}]},
        "33333": {"grades": [{"participants": 100}]},
    }

    selected = checker.select_probe_courses(coursedic, set(coursedic), limit=2)

    assert selected == ["22222", "33333"]


def test_normalize_grade_href_avoids_scheme_false_positives() -> None:
    expected = "http://karakterer.dtu.dk/Histogram/1/01001/Summer-2025"

    assert checker.normalize_grade_href(expected) == expected
    assert checker.normalize_grade_href(expected.replace("http://", "https://")) == expected
    assert checker.normalize_grade_href("//karakterer.dtu.dk/Histogram/1/01001/Summer-2025") == expected


def test_grade_href_filter_only_accepts_histogram_pages() -> None:
    assert checker.is_grade_histogram_href("https://karakterer.dtu.dk/Histogram/1/01001/Summer-2025")
    assert not checker.is_grade_histogram_href("https://example.com/?ref=karakterer")
    assert not checker.is_grade_histogram_href("https://karakterer.dtu.dk/not-histogram/01001")


def test_load_current_course_numbers_returns_empty_when_missing(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "data" / "coursenumbers.txt"
    monkeypatch.setattr(checker.config, "paths", SimpleNamespace(course_numbers_file=missing))

    assert checker.load_current_course_numbers() == set()


def test_main_reports_probe_error_when_secret_is_missing(monkeypatch, tmp_path: Path) -> None:
    course_numbers = tmp_path / "data" / "coursenumbers.txt"
    coursedic = tmp_path / "data" / "coursedic.json"
    report_file = tmp_path / "check_report.json"
    course_numbers.parent.mkdir()
    course_numbers.write_text("11111")
    coursedic.write_text(json.dumps({"11111": {"grades": [{"participants": 1, "url": "x"}]}}))

    monkeypatch.setattr(checker, "BASELINE_NUMBERS_FILE", course_numbers)
    monkeypatch.setattr(checker, "BASELINE_COURSEDIC_FILE", coursedic)
    monkeypatch.setattr(checker, "LEGACY_NUMBERS_FILE", tmp_path / "missing-coursenumbers.txt")
    monkeypatch.setattr(checker, "LEGACY_COURSEDIC_FILE", tmp_path / "missing-coursedic.json")
    monkeypatch.setattr(checker, "REPORT_FILE", report_file)
    monkeypatch.setattr(checker, "get_course_numbers", lambda: True)
    monkeypatch.setattr(
        checker.config,
        "paths",
        SimpleNamespace(course_numbers_file=course_numbers, secret_file=tmp_path / "missing-secret.txt"),
    )

    assert checker.main() == 1

    report = json.loads(report_file.read_text())
    assert "probe_error" in report
    assert report["probed_course_count"] == 1


def test_probe_new_semesters_rejects_empty_secret(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("")
    monkeypatch.setattr(checker.config, "paths", SimpleNamespace(secret_file=secret))

    try:
        asyncio.run(checker.probe_new_semesters(["11111"], {"11111": {}}))
    except RuntimeError as e:
        assert "is empty" in str(e)
    else:
        raise AssertionError("Expected RuntimeError for empty secret")


def test_probe_new_semesters_returns_empty_when_urls_are_in_baseline(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("session")
    url = "http://karakterer.dtu.dk/Histogram/1/11111/Summer-2025"
    monkeypatch.setattr(checker.config, "paths", SimpleNamespace(secret_file=secret))

    async def fake_fetch(session, semaphore, course_n: str):
        return course_n, {url}

    monkeypatch.setattr(checker, "fetch_grade_links_for_course", fake_fetch)

    result = asyncio.run(
        checker.probe_new_semesters(
            ["11111"],
            {"11111": {"grades": [{"participants": 1, "url": url}]}},
        )
    )

    assert result == []


def test_probe_new_semesters_flags_all_empty_results_as_stale_cookie(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("session")
    monkeypatch.setattr(checker.config, "paths", SimpleNamespace(secret_file=secret))

    async def fake_fetch(session, semaphore, course_n: str):
        return course_n, set()

    monkeypatch.setattr(checker, "fetch_grade_links_for_course", fake_fetch)

    try:
        asyncio.run(checker.probe_new_semesters(["11111"], {"11111": {}}))
    except RuntimeError as e:
        assert "cookie may be stale" in str(e)
    else:
        raise AssertionError("Expected RuntimeError for empty probe results")


def test_probe_new_semesters_returns_stable_order(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("session")
    monkeypatch.setattr(checker.config, "paths", SimpleNamespace(secret_file=secret))

    async def fake_fetch(session, semaphore, course_n: str):
        return course_n, {f"http://karakterer.dtu.dk/Histogram/1/{course_n}/Summer-2025"}

    monkeypatch.setattr(checker, "fetch_grade_links_for_course", fake_fetch)

    result = asyncio.run(checker.probe_new_semesters(["22222", "11111"], {"11111": {}, "22222": {}}))

    assert result == [
        {"course": "11111", "url": "http://karakterer.dtu.dk/Histogram/1/11111/Summer-2025"},
        {"course": "22222", "url": "http://karakterer.dtu.dk/Histogram/1/22222/Summer-2025"},
    ]


def test_main_happy_path_reports_changes_and_new_semesters(monkeypatch, tmp_path: Path) -> None:
    course_numbers = tmp_path / "data" / "coursenumbers.txt"
    coursedic = tmp_path / "data" / "coursedic.json"
    report_file = tmp_path / "check_report.json"
    new_url = "http://karakterer.dtu.dk/Histogram/1/11111/Winter-2026"
    course_numbers.parent.mkdir()
    course_numbers.write_text("11111")
    coursedic.write_text(
        json.dumps(
            {
                "11111": {
                    "grades": [
                        {
                            "participants": 1,
                            "url": "http://karakterer.dtu.dk/Histogram/1/11111/Summer-2025",
                        }
                    ]
                }
            }
        )
    )

    def refresh_course_numbers() -> bool:
        course_numbers.write_text("11111,22222")
        return True

    async def fake_probe(probe_courses, baseline):
        assert probe_courses == ["11111"]
        return [{"course": "11111", "url": new_url}]

    monkeypatch.setattr(checker, "BASELINE_NUMBERS_FILE", course_numbers)
    monkeypatch.setattr(checker, "BASELINE_COURSEDIC_FILE", coursedic)
    monkeypatch.setattr(checker, "LEGACY_NUMBERS_FILE", tmp_path / "missing-coursenumbers.txt")
    monkeypatch.setattr(checker, "LEGACY_COURSEDIC_FILE", tmp_path / "missing-coursedic.json")
    monkeypatch.setattr(checker, "REPORT_FILE", report_file)
    monkeypatch.setattr(checker, "get_course_numbers", refresh_course_numbers)
    monkeypatch.setattr(checker, "probe_new_semesters", fake_probe)
    monkeypatch.setattr(
        checker.config,
        "paths",
        SimpleNamespace(course_numbers_file=course_numbers, secret_file=tmp_path / "secret.txt"),
    )

    assert checker.main() == 0

    report = json.loads(report_file.read_text())
    assert report["has_changes"] is True
    assert report["added_courses"] == ["22222"]
    assert report["new_semesters"] == [{"course": "11111", "url": new_url}]


def test_main_writes_failure_report_when_course_refresh_fails(monkeypatch, tmp_path: Path) -> None:
    report_file = tmp_path / "check_report.json"
    baseline = tmp_path / "data" / "coursenumbers.txt"
    baseline.parent.mkdir()
    baseline.write_text("11111")

    monkeypatch.setattr(checker, "BASELINE_NUMBERS_FILE", baseline)
    monkeypatch.setattr(checker, "LEGACY_NUMBERS_FILE", tmp_path / "missing-coursenumbers.txt")
    monkeypatch.setattr(checker, "REPORT_FILE", report_file)
    monkeypatch.setattr(checker, "get_course_numbers", lambda: False)

    assert checker.main() == 1

    report = json.loads(report_file.read_text())
    assert report["check_failed"] is True
    assert report["failure_reason"] == "course_number_refresh_failed"


def test_main_suppresses_course_diff_when_current_baseline_is_missing(monkeypatch, tmp_path: Path) -> None:
    current_numbers = tmp_path / "data" / "coursenumbers.txt"
    legacy_numbers = tmp_path / "source-code" / "coursenumbers.txt"
    coursedic = tmp_path / "data" / "coursedic.json"
    report_file = tmp_path / "check_report.json"
    current_numbers.parent.mkdir()
    legacy_numbers.parent.mkdir(parents=True)
    legacy_numbers.write_text("11111")
    coursedic.write_text("{}")

    def refresh_course_numbers() -> bool:
        current_numbers.write_text("11111,22222")
        return True

    monkeypatch.setattr(checker, "BASELINE_NUMBERS_FILE", tmp_path / "missing-coursenumbers.txt")
    monkeypatch.setattr(checker, "BASELINE_COURSEDIC_FILE", coursedic)
    monkeypatch.setattr(checker, "LEGACY_NUMBERS_FILE", legacy_numbers)
    monkeypatch.setattr(checker, "LEGACY_COURSEDIC_FILE", tmp_path / "missing-legacy-coursedic.json")
    monkeypatch.setattr(checker, "REPORT_FILE", report_file)
    monkeypatch.setattr(checker, "get_course_numbers", refresh_course_numbers)
    monkeypatch.setattr(
        checker.config,
        "paths",
        SimpleNamespace(course_numbers_file=current_numbers, secret_file=tmp_path / "secret.txt"),
    )

    assert checker.main() == 0

    report = json.loads(report_file.read_text())
    assert report["baseline_missing"] is True
    assert report["has_changes"] is False
    assert report["baseline_course_count"] == 1
    assert report["added_courses"] == []


def test_main_reads_course_number_baseline_before_refresh(monkeypatch, tmp_path: Path) -> None:
    course_numbers = tmp_path / "data" / "coursenumbers.txt"
    coursedic = tmp_path / "data" / "coursedic.json"
    report_file = tmp_path / "check_report.json"
    course_numbers.parent.mkdir()
    course_numbers.write_text("11111")
    coursedic.write_text("{}")

    def refresh_course_numbers() -> bool:
        course_numbers.write_text("11111,22222")
        return True

    monkeypatch.setattr(checker, "BASELINE_NUMBERS_FILE", course_numbers)
    monkeypatch.setattr(checker, "BASELINE_COURSEDIC_FILE", coursedic)
    monkeypatch.setattr(checker, "LEGACY_NUMBERS_FILE", tmp_path / "missing-coursenumbers.txt")
    monkeypatch.setattr(checker, "LEGACY_COURSEDIC_FILE", tmp_path / "missing-coursedic.json")
    monkeypatch.setattr(checker, "REPORT_FILE", report_file)
    monkeypatch.setattr(checker, "get_course_numbers", refresh_course_numbers)
    monkeypatch.setattr(
        checker.config,
        "paths",
        SimpleNamespace(course_numbers_file=course_numbers, secret_file=tmp_path / "secret.txt"),
    )

    assert checker.main() == 0

    report = json.loads(report_file.read_text())
    assert report["added_courses"] == ["22222"]
    assert report["removed_courses"] == []


def test_main_skips_semester_probe_when_current_coursedic_baseline_is_missing(monkeypatch, tmp_path: Path) -> None:
    course_numbers = tmp_path / "data" / "coursenumbers.txt"
    legacy_coursedic = tmp_path / "source-code" / "coursedic.json"
    report_file = tmp_path / "check_report.json"
    course_numbers.parent.mkdir()
    legacy_coursedic.parent.mkdir(parents=True)
    course_numbers.write_text("11111")
    legacy_coursedic.write_text(json.dumps({"11111": {"grades": [{"participants": 1, "url": "old"}]}}))

    async def fail_probe(*_args, **_kwargs):
        raise AssertionError("stale legacy coursedic must not be probed")

    monkeypatch.setattr(checker, "BASELINE_NUMBERS_FILE", course_numbers)
    monkeypatch.setattr(checker, "BASELINE_COURSEDIC_FILE", tmp_path / "missing-coursedic.json")
    monkeypatch.setattr(checker, "LEGACY_NUMBERS_FILE", tmp_path / "missing-coursenumbers.txt")
    monkeypatch.setattr(checker, "LEGACY_COURSEDIC_FILE", legacy_coursedic)
    monkeypatch.setattr(checker, "REPORT_FILE", report_file)
    monkeypatch.setattr(checker, "get_course_numbers", lambda: True)
    monkeypatch.setattr(checker, "probe_new_semesters", fail_probe)
    monkeypatch.setattr(
        checker.config,
        "paths",
        SimpleNamespace(course_numbers_file=course_numbers, secret_file=tmp_path / "secret.txt"),
    )

    assert checker.main() == 0

    report = json.loads(report_file.read_text())
    assert report["coursedic_baseline_missing"] is True
    assert report["probed_course_count"] == 0
    assert report["new_semesters"] == []
