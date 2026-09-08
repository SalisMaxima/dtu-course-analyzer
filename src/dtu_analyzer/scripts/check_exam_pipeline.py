"""Replay saved exam evidence into an isolated candidate and compare a baseline.

This is a local integration check, not a publishing command or collection-health
gate. Supply the original analyzed feedback/base dataset, not the expected output.
"""

import argparse
import hashlib
import json
from pathlib import Path

from .build_chrome_beta import build_dataset


def compare_datasets(expected, candidate):
    changed = {}
    for course in sorted(expected.keys() & candidate.keys()):
        fields = sorted(
            key for key in expected[course].keys() | candidate[course].keys()
            if (key not in expected[course] or key not in candidate[course]
                or expected[course][key] != candidate[course][key])
        )
        if fields:
            changed[course] = fields
    missing = sorted(expected.keys() - candidate.keys())
    added = sorted(candidate.keys() - expected.keys())
    return {
        "matches": not (changed or missing or added),
        "expected_courses": len(expected), "candidate_courses": len(candidate),
        "missing_courses": missing, "added_courses": added,
        "changed_fields_by_course": changed,
        "candidate_exams": sum(len(c.get("exam_history", [])) for c in candidate.values()),
        "candidate_defaults": sum(c.get("default_exam_id") is not None for c in candidate.values()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--report", type=Path, action="append", required=True,
                        help="Repeat in oldest-to-newest order")
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory for candidate data and comparison summary")
    args = parser.parse_args(argv)
    if args.base.resolve() == args.expected.resolve():
        parser.error("Base must be independent of the expected output")
    if args.output.exists():
        parser.error("Output already exists; choose a new directory")
    paths = [args.base, *args.report, args.expected]
    contents = [path.read_bytes() for path in paths]
    base, *rest = [json.loads(content) for content in contents]
    reports, expected = rest[:-1], rest[-1]
    candidate = build_dataset(base, reports)
    summary = compare_datasets(expected, candidate)
    summary["schema_version"] = 1
    summary["inputs"] = [
        {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}
        for path, content in zip(paths, contents)
    ]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "data.json").write_text(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")))
    (args.output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if summary["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
