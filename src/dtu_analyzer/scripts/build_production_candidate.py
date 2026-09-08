"""Build, validate and optionally publish an exam-history dataset.

The default is an isolated candidate artifact. Publication is explicit and guarded.
"""

import argparse
import json
from pathlib import Path
import re
import shutil

from ..analysis.analyzer import process_courses
from ..analysis.publication_guard import publication_issues, publish_candidate
from .build_chrome_beta import build_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--course-file", type=Path, required=True)
    parser.add_argument("--extension", type=Path, default=Path("extension"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; choose a new directory")
    if args.output.resolve().is_relative_to(args.extension.resolve()):
        parser.error("Candidate output must be outside the installed extension")
    raw = json.loads(args.raw.read_text())
    report = json.loads(args.report.read_text())
    previous = json.loads((args.extension / "db/data.json").read_text())
    expected = set(filter(None, re.split(r"[,\s]+", args.course_file.read_text().strip())))
    candidate = build_dataset(process_courses(raw), [report])
    issues = publication_issues(previous, candidate, report, expected)
    for course in sorted(expected):
        info = report.get("courses", {}).get(course, {}).get("pages", {}).get("info", {}).get("content", {})
        review_links = info.get("evaluation_link_count")
        if review_links is None:
            issues.append({"course": course, "reason": "feedback_collection_evidence_missing"})
        elif len(raw.get(course, {}).get("reviews", [])) < review_links:
            issues.append({"course": course, "reason": "feedback_collection_incomplete"})
    # Produce review artifacts even if validation fails, but never publish them.
    args.output.mkdir(parents=True)
    (args.output / "validation.json").write_text(json.dumps({
        "schema_version": 1, "publishable": not issues, "issues": issues,
        "courses": len(candidate), "exams": sum(len(c["exam_history"]) for c in candidate.values()),
        "review_needed": [c for c, r in report.get("courses", {}).items()
                          if any(e.get("identity_status") in {"different_course_requires_review", "variant_requires_review"}
                                 for e in r.get("exams", []))],
    }, indent=2) + "\n")
    shutil.copytree(args.extension, args.output / "extension")
    (args.output / "extension/db/data.json").write_text(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")))
    if issues:
        print(f"Publication blocked: {len(issues)} issues. See {args.output / 'validation.json'}")
        return 1
    if args.publish:
        publish_candidate(args.extension / "db/data.json", candidate, report, expected)
    print(f"{'Published' if args.publish else 'Validated candidate'}: {len(candidate)} courses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
