"""Seed the scraper's resume checkpoint so only courses that need it are scraped again.

seed: reuse a failed Update Course Data run's scrape. Courses the source run
flagged, courses it did not collect and courses newly listed are scraped again;
exam histories, the candidate and its validation are rebuilt from scratch.

recollect: after the exam-history probe, scrape again any course whose page
now links more evaluations than were scraped, for example one published after
it was scraped, instead of letting it block the candidate.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

from .build_production_candidate import feedback_collection_issues
from .candidate_provenance import PROMOTION_FILES

# Evaluations and course lists change slowly, but reused data must still be recent
MAX_SOURCE_AGE = timedelta(days=7)
# Code that shapes the reused records; a change requires a full collection
COLLECTION_CODE = ("src/dtu_analyzer/parsers", "src/dtu_analyzer/scrapers/async_scraper.py")


def verify_source_run(run, repository, run_id, branch, now=None):
    if not re.fullmatch(r"[1-9][0-9]*", str(run_id)):
        raise ValueError("Repair run ID must be a positive integer")
    if str(run.get("id")) != str(run_id):
        raise ValueError("Repair run ID does not match GitHub metadata")
    if run.get("repository", {}).get("full_name") != repository or run.get("head_repository", {}).get("full_name") != repository:
        raise ValueError("Repair source must originate in this repository, not a fork")
    if run.get("path") != ".github/workflows/scrape.yml" or run.get("event") != "workflow_dispatch":
        raise ValueError("Repair source must be an Update Course Data run")
    if run.get("head_branch") != branch:
        raise ValueError("Repair source must come from the branch being updated")
    if run.get("status") != "completed" or run.get("conclusion") != "failure":
        raise ValueError("Repair source must be a failed run; promote a successful one instead")
    created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    if (now or datetime.now(timezone.utc)) - created > MAX_SOURCE_AGE:
        raise ValueError(f"Repair source is older than {MAX_SOURCE_AGE.days} days; run a full collection")


def verify_unchanged_since(root, source_sha):
    """The source commit must be available locally (the workflow fetches it)."""
    if not re.fullmatch(r"[0-9a-f]{40}", str(source_sha)):
        raise ValueError("Invalid repair source commit")
    checks = [
        (COLLECTION_CODE, "Collection code changed since the repair source run; run a full collection"),
        # Reused feedback would silently roll back a newer promoted dataset
        (PROMOTION_FILES, "A dataset was promoted after the repair source run; run a full collection"),
    ]
    for paths, message in checks:
        diff = subprocess.run(["git", "-C", str(root), "diff", "--quiet", source_sha, "HEAD", "--", *paths])
        if diff.returncode == 1:
            raise ValueError(message)
        if diff.returncode:
            raise ValueError("Could not compare with the repair source commit")


def listed_courses(course_file):
    return set(filter(None, re.split(r"[,\s]+", Path(course_file).read_text().strip())))


def write_checkpoint(output, courses):
    output = Path(output)
    if output.exists():
        raise ValueError(f"{output} already exists; refusing to mix checkpoints")
    output.write_text(json.dumps(courses))


def seed_checkpoint(candidate_dir, course_file, output):
    """Write the scraper checkpoint; return what is reused and what is collected again."""
    candidate_dir = Path(candidate_dir)
    provenance = json.loads((candidate_dir / "provenance.json").read_text())
    if provenance.get("repaired_from_run_id"):
        # Chained repairs would hide the age of the original collection
        raise ValueError("Source run is itself a repair; repair the original full run instead")
    validation = json.loads((candidate_dir / "validation.json").read_text())
    if validation.get("schema_version") != 1:
        raise ValueError("Unsupported repair source validation")
    raw = json.loads((candidate_dir / "data/coursedic.json").read_text())
    listed = listed_courses(course_file)
    flagged = {issue.get("course") for issue in validation.get("issues", [])} - {None}
    reused = {course: data for course, data in raw.items() if course in listed and course not in flagged}
    write_checkpoint(output, reused)
    return {"reused": len(reused), "collect": sorted(listed - reused.keys()),
            "flagged": sorted(flagged), "unlisted": sorted(raw.keys() - listed)}


def recollect_checkpoint(raw_file, report_file, course_file, output):
    """Write a checkpoint without courses missing linked evaluations; return those courses.

    Uses the candidate's own completeness rule. Nothing is written when no
    course needs collecting again.
    """
    raw = json.loads(Path(raw_file).read_text())
    report = json.loads(Path(report_file).read_text())
    listed = listed_courses(course_file)
    stale = sorted(issue["course"] for issue in feedback_collection_issues(raw, report, listed)
                   if issue["reason"] == "feedback_collection_incomplete")
    if stale:
        write_checkpoint(output, {c: d for c, d in raw.items() if c in listed and c not in stale})
    return stale


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Verify the source run before downloading its data")
    check.add_argument("--run-metadata", type=Path, required=True)
    check.add_argument("--repository", required=True)
    check.add_argument("--run-id", required=True)
    check.add_argument("--branch", required=True)
    check.add_argument("--root", type=Path, default=Path("."))
    seed = commands.add_parser("seed", help="Write the scraper checkpoint from the source candidate")
    seed.add_argument("--candidate", type=Path, required=True)
    seed.add_argument("--course-file", type=Path, required=True)
    seed.add_argument("--output", type=Path, required=True)
    recollect = commands.add_parser("recollect", help="Write a checkpoint without courses missing linked evaluations")
    recollect.add_argument("--raw", type=Path, required=True)
    recollect.add_argument("--report", type=Path, required=True)
    recollect.add_argument("--course-file", type=Path, required=True)
    recollect.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            run = json.loads(args.run_metadata.read_text())
            verify_source_run(run, args.repository, args.run_id, args.branch)
            verify_unchanged_since(args.root, run.get("head_sha"))
            print(f"Repair source run {args.run_id} accepted")
        elif args.command == "seed":
            summary = seed_checkpoint(args.candidate, args.course_file, args.output)
            print(f"Reusing {summary['reused']} scraped courses; collecting {len(summary['collect'])} again")
            print(f"Flagged by the source run: {', '.join(summary['flagged']) or 'none'}")
            if summary["unlisted"]:
                print(f"Dropped, no longer listed: {', '.join(summary['unlisted'])}")
        else:
            stale = recollect_checkpoint(args.raw, args.report, args.course_file, args.output)
            print(f"Courses missing linked evaluations: {', '.join(stale) or 'none'}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Repair refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
