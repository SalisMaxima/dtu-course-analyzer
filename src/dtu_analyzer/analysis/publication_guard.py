"""Fail-closed validation and atomic replacement for a future production updater.

Not connected to the legacy Actions workflow. Any lost course/history requires
review; no percentage threshold silently permits losses.
"""

import json
import os
from pathlib import Path
import tempfile

from .course_history_reviews import NEW_COURSES, REVIEWED_NPE, EXCLUDED_HISTORY
from ..scripts.build_chrome_beta import build_dataset


def publication_issues(previous, candidate, report, expected_courses):
    issues = []
    def flag(course, reason):
        issues.append({"course": course, "reason": reason})

    records = report.get("courses", {})
    expected = set(expected_courses)
    if not expected:
        flag(None, "empty_expected_course_set")
    if not report.get("finished_at") or report.get("fatal_error"):
        flag(None, "collection_not_completed_successfully")
    for course in sorted(expected - records.keys()):
        flag(course, "course_not_collected")
    for course in sorted((expected | previous.keys()) - candidate.keys()):
        flag(course, "course_missing_from_candidate")
    for course, record in records.items():
        if record.get("status") in {None, "pending", "error"} or record.get("errors"):
            flag(course, "course_collection_failed")
        if not record.get("schedule", {}).get("raw"):
            flag(course, "schedule_evidence_missing")
        exams = record.get("exams", [])
        if not exams and course not in NEW_COURSES | REVIEWED_NPE:
            state = record.get("pages", {}).get("info", {}).get("content", {}).get("state")
            if state != "no_published_results":
                flag(course, "absence_of_results_unconfirmed")
        for exam in exams:
            if exam.get("distribution_status") not in {"published", "suppressed"} or exam.get("error"):
                flag(course, "histogram_collection_failed")
            if exam.get("distribution_status") == "published":
                if not exam.get("grades"):
                    flag(course, "published_distribution_missing_grades")
                if exam.get("result_counts", {}).get("all_categories_retained") is False:
                    flag(course, "source_categories_lost")
    for course, old in previous.items():
        new = candidate.get(course, {})
        old_ids = {e["id"] for e in old.get("exam_history", [])
                   if e.get("histogram_course") not in EXCLUDED_HISTORY.get(course, set())}
        new_ids = {e["id"] for e in new.get("exam_history", [])}
        if old_ids - new_ids:
            flag(course, "previous_exam_history_lost")
        excluded_default = any(e.get("id") == old.get("default_exam_id")
                               and e.get("histogram_course") in EXCLUDED_HISTORY.get(course, set())
                               for e in old.get("exam_history", []))
        if old.get("default_exam_id") and not new.get("default_exam_id") and not excluded_default:
            flag(course, "previous_default_lost")
        for key in ("review_participants", "qualityscore", "workload", "lazyscore"):
            if key in old and key not in new:
                flag(course, "feedback_field_lost:" + key)
    # Independently reconstruct expected grade fields from the collected evidence.
    # Feedback is supplied separately; this gate checks its retention, not freshness.
    try:
        rebuilt = build_dataset(candidate, [report])
        for course in candidate:
            if candidate[course] != rebuilt[course]:
                flag(course, "candidate_disagrees_with_collected_evidence")
    except (KeyError, TypeError, ValueError, AttributeError):
        flag(None, "invalid_candidate_or_evidence")
    return issues


def publish_candidate(destination, candidate, report, expected_courses):
    """Validate against the installed dataset before atomically replacing it.

    Intended for a single writer. The caller must serialize production runs.
    """
    destination = Path(destination)
    previous = json.loads(destination.read_text())
    issues = publication_issues(previous, candidate, report, expected_courses)
    if issues:
        raise ValueError(json.dumps(issues))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".candidate-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(candidate, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(destination.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
