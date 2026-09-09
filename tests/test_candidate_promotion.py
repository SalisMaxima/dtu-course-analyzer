import json

import pytest

from dtu_analyzer.scripts.candidate_provenance import PROMOTION_FILES, git, sha256, write_provenance
from dtu_analyzer.scripts.promote_course_data import main, verify_candidate, verify_origin


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "extension/db").mkdir(parents=True)
    baseline = b'{"01001":{"exam_history":[]}}\n'
    (root / "extension/db/data.json").write_bytes(baseline)
    (root / "extension/contentscript.js").write_text("// reviewed extension code\n")
    (root / "data").mkdir()
    (root / "data/coursenumbers.txt").write_bytes(b"01001\n")
    (root / "data/coursedic.json").write_text(json.dumps({"01001": {"grades": [
        {"url": "https://karakterer.dtu.dk/Histogram/1/01001/Winter-2025"}]}}))
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Initial")
    output = tmp_path / "candidate"
    (output / "extension/db").mkdir(parents=True)
    payload = b'{\n  "01001": {"exam_history": [], "name": "Test"}, "01002": {"exam_history": []}\n}\n'
    (output / "extension/db/data.json").write_bytes(payload)
    (output / "extension/contentscript.js").write_text("// never copied or executed\n")
    (output / "validation.json").write_text(json.dumps({"schema_version": 1, "publishable": True, "issues": [], "courses": 2}))
    (output / "data").mkdir()
    (output / "data/coursenumbers.txt").write_bytes(b"01001,01002\n")
    (output / "data/coursedic.json").write_text(json.dumps({"01001": {"grades": [
        {"url": "https://karakterer.dtu.dk/Histogram/1/01001/Winter-2025"},
        {"url": "https://karakterer.dtu.dk/Histogram/1/01001/Summer-2026"}]}, "01002": {}}))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    write_provenance(output, baseline, root)
    run = {"id": 123, "run_attempt": 1, "head_sha": git(root, "rev-parse", "HEAD"),
           "path": ".github/workflows/scrape.yml", "event": "workflow_dispatch",
           "status": "completed", "conclusion": "success",
           "repository": {"full_name": "owner/repo"}, "head_repository": {"full_name": "owner/repo"}}
    artifact = {"id": 456, "expired": False, "name": "course-data-candidate", "workflow_run": {"id": 123}}
    return root, output, run, artifact, payload


def promote(candidate, tmp_path):
    root, output, run, artifact, _ = candidate
    (tmp_path / "run.json").write_text(json.dumps(run))
    (tmp_path / "artifact.json").write_text(json.dumps(artifact))
    return main(["--root", str(root), "--candidate", str(output),
                 "--run-metadata", str(tmp_path / "run.json"),
                 "--artifact-metadata", str(tmp_path / "artifact.json"),
                 "--repository", "owner/repo", "--run-id", "123", "--artifact-id", "456"])


def test_promotes_exact_bytes_without_copying_extension_code_or_running_scraper(candidate, tmp_path):
    root, output, _, _, payload = candidate
    original_code = (root / "extension/contentscript.js").read_bytes()
    assert promote(candidate, tmp_path) == 0
    assert (root / "extension/db/data.json").read_bytes() == payload
    assert (root / "extension/contentscript.js").read_bytes() == original_code
    assert set(git(root, "diff", "--name-only").splitlines()) == set(PROMOTION_FILES)
    for path in PROMOTION_FILES:
        assert (root / path).read_bytes() == (output / path).read_bytes()


@pytest.mark.parametrize("failure", ["dataset", "validation", "failed_validation", "provenance",
                                    "stale_data", "stale_code", "old_attempt", "unmerged_source"])
def test_rejects_invalid_candidate_without_touching_installed_data(candidate, tmp_path, failure):
    root, output, run, artifact, _ = candidate
    manifest = output / "provenance.json"
    metadata = json.loads(manifest.read_text())
    if failure == "dataset":
        (output / "extension/db/data.json").write_text('{}')
    elif failure == "validation":
        (output / "validation.json").write_text('{}')
    elif failure == "failed_validation":
        (output / "validation.json").write_text(json.dumps({"schema_version": 1, "publishable": False, "issues": ["failure"]}))
        metadata["validation_sha256"] = sha256((output / "validation.json").read_bytes())
    elif failure == "provenance":
        metadata["repository"] = "someone/else"
    elif failure == "stale_data":
        (root / "extension/db/data.json").write_text('{"already":"updated"}')
    elif failure == "stale_code":
        (root / "extension/contentscript.js").write_text("// different code")
    elif failure == "old_attempt":
        run["run_attempt"] = 2
    elif failure == "unmerged_source":
        metadata["source_sha"] = run["head_sha"] = "f" * 40
    manifest.write_text(json.dumps(metadata))
    installed = (root / "extension/db/data.json").read_bytes()
    with pytest.raises(ValueError):
        verify_candidate(output, root, run, artifact, "owner/repo", "123", "456")
    assert promote(candidate, tmp_path) == 1
    assert (root / "extension/db/data.json").read_bytes() == installed


@pytest.mark.parametrize("field,value", [("conclusion", "failure"), ("status", "in_progress"),
                                        ("event", "pull_request"), ("path", ".github/workflows/other.yml")])
def test_rejects_wrong_or_unsuccessful_source_run(candidate, field, value):
    _, _, run, artifact, _ = candidate
    run[field] = value
    with pytest.raises(ValueError):
        verify_origin(run, artifact, "owner/repo", "123", "456")


@pytest.mark.parametrize("change", ["expired", "wrong_run", "wrong_artifact", "fork", "invalid_id"])
def test_rejects_wrong_artifact_and_fork(candidate, change):
    _, _, run, artifact, _ = candidate
    selected = "456"
    if change == "expired":
        artifact["expired"] = True
    elif change == "wrong_run":
        artifact["workflow_run"]["id"] = 999
    elif change == "wrong_artifact":
        artifact["id"] = 999
    elif change == "fork":
        run["head_repository"]["full_name"] = "fork/repo"
    else:
        selected = "456; echo unsafe"
    with pytest.raises(ValueError):
        verify_origin(run, artifact, "owner/repo", "123", selected)


def test_second_promotion_after_commit_is_rejected_as_stale(candidate, tmp_path):
    root, _, _, _, payload = candidate
    assert promote(candidate, tmp_path) == 0
    git(root, "add", *PROMOTION_FILES)
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Promote")
    assert promote(candidate, tmp_path) == 1
    assert (root / "extension/db/data.json").read_bytes() == payload


def test_documentation_only_commit_does_not_invalidate_candidate(candidate, tmp_path):
    root, _, _, _, _ = candidate
    (root / "README.md").write_text("Documentation update")
    git(root, "add", "README.md")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Docs")
    assert promote(candidate, tmp_path) == 0


@pytest.mark.parametrize("path", ["data/coursenumbers.txt", "data/coursedic.json"])
@pytest.mark.parametrize("failure", ["tampered", "missing", "stale"])
def test_checker_baseline_failure_rejects_entire_promotion(candidate, tmp_path, path, failure):
    root, output, run, artifact, _ = candidate
    if failure == "tampered":
        (output / path).write_bytes(b"tampered")
    elif failure == "missing":
        (output / path).unlink()
    else:
        (root / path).write_bytes(b"newer baseline")
        git(root, "add", path)
        git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Advance baseline")
    originals = {p: (root / p).read_bytes() for p in PROMOTION_FILES}
    assert promote(candidate, tmp_path) == 1
    assert originals == {p: (root / p).read_bytes() for p in PROMOTION_FILES}


def test_provenance_uses_committed_pre_scrape_baselines(candidate):
    root, output, _, _, _ = candidate
    originals = {p: (root / p).read_bytes() for p in PROMOTION_FILES}
    # In Update Course Data the working copies already contain the fresh scrape.
    for path in PROMOTION_FILES[1:]:
        (root / path).write_bytes((output / path).read_bytes())
    metadata = write_provenance(output, originals[PROMOTION_FILES[0]], root)
    for path in PROMOTION_FILES:
        assert metadata["files"][path]["baseline_sha256"] == sha256(originals[path])
        assert metadata["files"][path]["sha256"] == sha256((output / path).read_bytes())


def test_promoted_baselines_no_longer_report_collected_course_or_semester_as_new(candidate, tmp_path):
    from dtu_analyzer.scripts.check_for_updates import load_baseline_course_numbers, existing_grade_urls
    root, output, _, _, _ = candidate
    current = {"01001", "01002"}
    new_exam = "https://karakterer.dtu.dk/Histogram/1/01001/Summer-2026"
    assert current - load_baseline_course_numbers(root / "data/coursenumbers.txt") == {"01002"}
    assert new_exam not in existing_grade_urls(json.loads((root / "data/coursedic.json").read_text()), "01001")
    assert promote(candidate, tmp_path) == 0
    assert not current - load_baseline_course_numbers(root / "data/coursenumbers.txt")
    assert new_exam in existing_grade_urls(json.loads((root / "data/coursedic.json").read_text()), "01001")


def test_install_failure_rolls_back_all_files(candidate, tmp_path, monkeypatch):
    from dtu_analyzer.scripts import promote_course_data as promotion
    root, _, _, _, _ = candidate
    originals = {p: (root / p).read_bytes() for p in PROMOTION_FILES}
    replace = promotion.os.replace
    calls = 0
    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated replacement failure")
        return replace(source, destination)
    monkeypatch.setattr(promotion.os, "replace", fail_second)
    assert promote(candidate, tmp_path) == 1
    assert originals == {p: (root / p).read_bytes() for p in PROMOTION_FILES}
    assert not list(root.rglob(".promotion-*"))


def test_legacy_provenance_without_baselines_is_rejected(candidate, tmp_path):
    root, output, _, _, _ = candidate
    original = (root / "extension/db/data.json").read_bytes()
    path = output / "provenance.json"
    metadata = json.loads(path.read_text())
    metadata["schema_version"] = 1
    path.write_text(json.dumps(metadata))
    assert promote(candidate, tmp_path) == 1
    assert (root / "extension/db/data.json").read_bytes() == original
