from datetime import datetime, timezone
import json

import pytest

from dtu_analyzer.scrapers import async_scraper as scraper
from dtu_analyzer.scripts.candidate_provenance import git, write_provenance
from dtu_analyzer.scripts.prepare_repair import main, seed_checkpoint, verify_parsers_unchanged, verify_source_run

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def source_run(**changes):
    run = {"id": 123, "path": ".github/workflows/scrape.yml", "event": "workflow_dispatch",
           "head_branch": "master", "status": "completed", "conclusion": "failure",
           "created_at": "2026-10-20T07:12:34Z", "head_sha": "a" * 40,
           "repository": {"full_name": "owner/repo"}, "head_repository": {"full_name": "owner/repo"}}
    run.update(changes)
    return run


@pytest.fixture
def source(tmp_path):
    """Candidate artifact of a failed run that dropped 01002 and lost data for 01003."""
    candidate = tmp_path / "source"
    (candidate / "data").mkdir(parents=True)
    (candidate / "data/coursedic.json").write_text(json.dumps(
        {"01001": {"reviews": [1]}, "01003": {"reviews": [1]}, "01009": {"reviews": [1]}}))
    (candidate / "validation.json").write_text(json.dumps({"schema_version": 1, "publishable": False, "issues": [
        {"course": "01002", "reason": "feedback_collection_incomplete"},
        {"course": "01003", "reason": "feedback_field_lost:workload"},
        {"course": None, "reason": "collection_not_completed_successfully"}]}))
    (candidate / "provenance.json").write_text(json.dumps({"schema_version": 2, "repaired_from_run_id": None}))
    course_file = tmp_path / "coursenumbers.txt"
    course_file.write_text("01001,01002,01003,01004")
    return candidate, course_file


def test_accepts_a_recent_failed_run_from_this_branch():
    verify_source_run(source_run(), "owner/repo", "123", "master", NOW)


@pytest.mark.parametrize("change,run_id", [
    ({}, "12a"),
    ({"id": 999}, "123"),
    ({"head_repository": {"full_name": "fork/repo"}}, "123"),
    ({"path": ".github/workflows/probe-exam-classification.yml"}, "123"),
    ({"event": "schedule"}, "123"),
    ({"head_branch": "feature"}, "123"),
    ({"status": "in_progress"}, "123"),
    ({"created_at": "2026-10-12T07:12:34Z"}, "123"),
])
def test_rejects_unsuitable_source_runs(change, run_id):
    with pytest.raises(ValueError):
        verify_source_run(source_run(**change), "owner/repo", run_id, "master", NOW)


def test_parser_changes_since_the_source_run_require_a_full_collection(tmp_path):
    root = tmp_path / "repo"
    (root / "src/dtu_analyzer/parsers").mkdir(parents=True)
    (root / "src/dtu_analyzer/parsers/review_parser.py").write_text("# v1\n")
    (root / "README.md").write_text("v1\n")
    commit = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qam"]
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, *commit, "Source run")
    source_sha = git(root, "rev-parse", "HEAD")
    (root / "README.md").write_text("v2\n")
    git(root, *commit, "Unrelated change")
    verify_parsers_unchanged(root, source_sha)
    (root / "src/dtu_analyzer/parsers/review_parser.py").write_text("# v2\n")
    git(root, *commit, "Parser change")
    with pytest.raises(ValueError, match="Parser code changed"):
        verify_parsers_unchanged(root, source_sha)
    with pytest.raises(ValueError):
        verify_parsers_unchanged(root, "b" * 40)


def test_seed_reuses_only_clean_listed_courses(source, tmp_path):
    candidate, course_file = source
    output = tmp_path / "coursedic.partial.json"
    summary = seed_checkpoint(candidate, course_file, output)
    assert json.loads(output.read_text()) == {"01001": {"reviews": [1]}}
    assert summary == {"reused": 1, "collect": ["01002", "01003", "01004"],
                       "flagged": ["01002", "01003"], "unlisted": ["01009"]}


def test_seed_refuses_chained_repairs_and_existing_checkpoints(source, tmp_path):
    candidate, course_file = source
    output = tmp_path / "coursedic.partial.json"
    output.write_text("{}")
    with pytest.raises(ValueError, match="already exists"):
        seed_checkpoint(candidate, course_file, output)
    output.unlink()
    (candidate / "provenance.json").write_text(json.dumps({"schema_version": 2, "repaired_from_run_id": "99"}))
    with pytest.raises(ValueError, match="itself a repair"):
        seed_checkpoint(candidate, course_file, output)
    assert not output.exists()


def test_cli_reports_refusal_instead_of_raising(source, tmp_path, capsys):
    candidate, course_file = source
    (tmp_path / "run.json").write_text(json.dumps(source_run(status="in_progress")))
    assert main(["check", "--run-metadata", str(tmp_path / "run.json"), "--repository", "owner/repo",
                 "--run-id", "123", "--branch", "master"]) == 1
    assert "Repair refused" in capsys.readouterr().out
    assert main(["seed", "--candidate", str(candidate), "--course-file", str(course_file),
                 "--output", str(tmp_path / "partial.json")]) == 0


@pytest.mark.asyncio
async def test_repair_run_scrapes_only_courses_the_source_run_did_not_deliver(source, tmp_path, monkeypatch):
    candidate, course_file = source
    (tmp_path / "data").mkdir()
    (tmp_path / "data/coursenumbers.txt").write_text(course_file.read_text())
    (tmp_path / "secret.txt").write_text("cookie")
    monkeypatch.setattr(scraper.config.paths, "root_dir", tmp_path)
    monkeypatch.setattr(scraper, "timeout_occurred", False)
    monkeypatch.setattr(scraper, "auth_failed", False)
    monkeypatch.setenv("RESUME", "1")
    seed_checkpoint(candidate, course_file, tmp_path / "data/coursedic.partial.json")
    calls = []

    async def fake_course(session, semaphore, course):
        calls.append(course)
        return (course, {"reviews": [1, 2]}, True)
    monkeypatch.setattr(scraper, "process_single_course", fake_course)

    assert await scraper.main_async() == 0
    assert sorted(calls) == ["01002", "01003", "01004"]
    data = json.loads((tmp_path / "data/coursedic.json").read_text())
    assert data == {"01001": {"reviews": [1]}, "01002": {"reviews": [1, 2]},
                    "01003": {"reviews": [1, 2]}, "01004": {"reviews": [1, 2]}}
    assert not (tmp_path / "data/coursedic.partial.json").exists()


def test_provenance_records_the_repair_source(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    output = tmp_path / "candidate"
    for base in (root, output):
        (base / "extension/db").mkdir(parents=True)
        (base / "data").mkdir()
        for path in ("extension/db/data.json", "data/coursenumbers.txt", "data/coursedic.json"):
            (base / path).write_text("{}")
    (output / "validation.json").write_text("{}")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Initial")
    monkeypatch.setenv("REPAIR_RUN_ID", "39385020003")
    assert write_provenance(output, b"{}", root)["repaired_from_run_id"] == "39385020003"
    monkeypatch.setenv("REPAIR_RUN_ID", "")
    assert write_provenance(output, b"{}", root)["repaired_from_run_id"] is None
