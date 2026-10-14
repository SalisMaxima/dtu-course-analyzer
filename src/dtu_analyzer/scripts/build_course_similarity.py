"""Build extension/db/similar.json from course descriptions with EmbeddingGemma 2.

Needs the optional dependencies: pip install -e ".[similarity]"

Usage: dtu-build-similarity --details data/course_details.json --report similarity-report.md
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from ..analysis.course_similarity import (
    DEFAULT_MODEL, DEFAULT_TOP_K, build_similarity, course_title, embeddinggemma_encoder,
)
from ..config import config

# Well-known courses whose neighbours are easy to sanity-check by hand
SAMPLE_COURSES = ("01001", "01005", "02402", "02450", "02105", "10020", "22100", "27002", "42500", "46000")


def label(data: dict, course: str) -> str:
    return f"{course} {course_title(data.get(course, {}))}".strip()


def write_report(path: Path, data: dict, details: dict, neighbours: dict, diagnostics: dict,
                 model: str, samples) -> None:
    lines = [
        "# Course similarity report", "",
        f"- Model: `{model}`",
        f"- Courses embedded: {diagnostics['embedded']} of {len(data)}",
        f"- 'Not applicable together with' pairs excluded: {diagnostics['excluded_pairs']}",
        f"- Courses without description text: {len(diagnostics['without_description'])}",
        "",
    ]
    for course in samples:
        if course not in neighbours:
            continue
        excluded = details.get(course, {}).get("not_applicable_with", [])
        lines.append(f"## {label(data, course)}")
        if excluded:
            lines.append(f"Excluded as equivalent: {', '.join(excluded)}")
        lines.append("")
        lines += [f"{rank}. {label(data, other)} ({score:.3f})"
                  for rank, (other, score) in enumerate(neighbours[course], 1)]
        lines.append("")
    if diagnostics["near_duplicates"]:
        lines += ["## Near-identical pairs without an exclusion link", "",
                  "These may be equivalent courses DTU does not mark as such.", ""]
        lines += [f"- {label(data, a)} / {label(data, b)} ({score:.3f})"
                  for a, b, score in diagnostics["near_duplicates"][:50]]
        lines.append("")
    if diagnostics["without_description"]:
        lines += ["## Without description text", "", ", ".join(diagnostics["without_description"]), ""]
    path.write_text("\n".join(lines))


def main(argv=None, encoder_factory=embeddinggemma_encoder):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--details", type=Path, default=config.paths.data_dir / "course_details.json")
    parser.add_argument("--data", type=Path, default=config.paths.extension_dir / "db/data.json")
    parser.add_argument("--output", type=Path, default=config.paths.extension_dir / "db/similar.json")
    parser.add_argument("--report", type=Path, help="Markdown spot-check report")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--sample", default=",".join(SAMPLE_COURSES),
                        help="Comma-separated courses to list in the report")
    args = parser.parse_args(argv)

    data = json.loads(args.data.read_text())
    details = json.loads(args.details.read_text())["courses"]
    neighbours, diagnostics = build_similarity(data, details, encoder_factory(args.model), args.top_k)
    if not neighbours:
        print("No course has description text; nothing written")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "schema_version": 1,
        "model": args.model,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "courses": neighbours,
    }, separators=(",", ":")))
    if args.report:
        write_report(args.report, data, details, neighbours, diagnostics, args.model,
                     [c.strip() for c in args.sample.split(",") if c.strip()])
    print(f"Wrote neighbours for {len(neighbours)} courses to {args.output} "
          f"({diagnostics['excluded_pairs']} equivalent pairs excluded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
