"""Tests for the lightweight course-data update checker."""

import json
import asyncio
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
