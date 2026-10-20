"""Reuse a failed Update Course Data run's scrape instead of collecting everything again.

Only raw scraped course data is reused. Courses the source run flagged, courses
it did not collect and courses newly listed are scraped again; exam histories,
the candidate and its validation are rebuilt from scratch by the repair run.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

# Evaluations and course lists change slowly, but reused data must still be recent
MAX_SOURCE_AGE = timedelta(days=7)
# Code that shapes the reused records; a change requires a full collection
PARSER_PATHS = ("src/dtu_analyzer/parsers",)


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
    if run.get("status") != "completed":
        raise ValueError("Repair source run has not finished")
    created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    if (now or datetime.now(timezone.utc)) - created > MAX_SOURCE_AGE:
        raise ValueError(f"Repair source is older than {MAX_SOURCE_AGE.days} days; run a full collection")


def verify_parsers_unchanged(root, source_sha):
    """The source commit must be available locally (the workflow fetches it)."""
    if not re.fullmatch(r"[0-9a-f]{40}", str(source_sha)):
        raise ValueError("Invalid repair source commit")
    diff = subprocess.run(["git", "-C", str(root), "diff", "--quiet", source_sha, "HEAD", "--", *PARSER_PATHS])
    if diff.returncode == 1:
        raise ValueError("Parser code changed since the repair source run; run a full collection")
    if diff.returncode:
        raise ValueError("Could not compare parser code with the repair source commit")


def seed_checkpoint(candidate_dir, course_file, output):
    """Write the scraper checkpoint; return what is reused and what is collected again."""
    candidate_dir, output = Path(candidate_dir), Path(output)
    if output.exists():
        raise ValueError(f"{output} already exists; refusing to mix checkpoints")
    provenance = json.loads((candidate_dir / "provenance.json").read_text())
    if provenance.get("repaired_from_run_id"):
        # Chained repairs would hide the age of the original collection
        raise ValueError("Source run is itself a repair; repair the original full run instead")
    validation = json.loads((candidate_dir / "validation.json").read_text())
    if validation.get("schema_version") != 1:
        raise ValueError("Unsupported repair source validation")
    raw = json.loads((candidate_dir / "data/coursedic.json").read_text())
    listed = set(filter(None, re.split(r"[,\s]+", Path(course_file).read_text().strip())))
    flagged = {issue.get("course") for issue in validation.get("issues", [])} - {None}
    reused = {course: data for course, data in raw.items() if course in listed and course not in flagged}
    output.write_text(json.dumps(reused))
    return {"reused": len(reused), "collect": sorted(listed - reused.keys()),
            "flagged": sorted(flagged), "unlisted": sorted(raw.keys() - listed)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            run = json.loads(args.run_metadata.read_text())
            verify_source_run(run, args.repository, args.run_id, args.branch)
            verify_parsers_unchanged(args.root, run.get("head_sha"))
            print(f"Repair source run {args.run_id} accepted")
        else:
            summary = seed_checkpoint(args.candidate, args.course_file, args.output)
            print(f"Reusing {summary['reused']} scraped courses; collecting {len(summary['collect'])} again")
            print(f"Flagged by the source run: {', '.join(summary['flagged']) or 'none'}")
            if summary["unlisted"]:
                print(f"Dropped, no longer listed: {', '.join(summary['unlisted'])}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Repair refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
