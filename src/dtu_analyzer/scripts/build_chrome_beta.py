"""Build an isolated Chrome beta using saved, reviewed diagnostic evidence."""

import argparse
import copy
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit
import zipfile

from ..analysis.analyzer import extract_grade_results, insertPercentile
from ..analysis.exam_classification import classify_course

GRADE_FIELDS = {"avg", "avgp", "pp", "grades", "grading_scale", "passpercent",
                "grade_participants", "grade_period", "grade_source"}


def exam_record(exam):
    sheet = exam.get("grades") or {}
    grades, scale = extract_grade_results(sheet)
    period = exam["period"]
    row = {
        "id": exam["url"], "grade_source": exam["url"], "grade_period": period["label"],
        "year": period.get("year"), "season": period.get("season"),
        "classification": exam["classification"],
        "distribution_status": exam.get("distribution_status", "failed"),
        "identity_status": exam.get("identity_status", "exact_course_id"),
        "histogram_course": exam.get("histogram_course") or urlsplit(exam["url"]).path.split("/")[-2],
        "title": exam.get("histogram_title", ""),
        "identity_note": exam.get("identity_review", {}).get("note", ""),
    }
    if row["distribution_status"] == "published":
        row.update(grades=grades, grading_scale=scale)
        if "participants" in sheet:
            row["grade_participants"] = sheet["participants"]
        if "pass_percentage" in sheet:
            row["passpercent"] = sheet["pass_percentage"]
        if scale == "seven_point" and "avg" in sheet:
            row["avg"] = sheet["avg"]
        if "participants" in sheet:
            row["participant_difference"] = sheet["participants"] - sum(int(v) for v in grades.values())
    return row


def build_dataset(base, reports):
    records = {}
    # Caller supplies reports oldest first; later records replace earlier ones.
    for report in reports:
        for course, source in report["courses"].items():
            row = copy.deepcopy(source)
            row["course"] = course
            row["collected_at"] = report.get("finished_at", report.get("started_at", ""))
            records[course] = classify_course(row)
    result = {}
    for course in sorted(set(base) | set(records)):
        data = {k: v for k, v in base.get(course, {}).items() if k not in GRADE_FIELDS}
        record = records.get(course, {})
        if record.get("name"):
            data["name_en"] = record["name"]
        history = [exam_record(e) for e in record.get("exams", [])]
        history.sort(key=lambda e: (e["year"] or 0, {"winter": 0, "summer": 1}.get(e["season"], -1), e["id"]), reverse=True)
        primary = record.get("primary_exam")
        data["default_exam_id"] = primary["url"] if primary else None
        data["exam_history"] = history
        data["history_collected_at"] = record.get("collected_at", "")
        data["exam_default_note"] = (
            "Latest regular exam inferred from the current schedule. Historical schedules may differ."
            if primary else "New course: no historical exam results expected."
            if record.get("history_status") == "new_course_no_history_expected"
            else "Regular exam could not be determined. Choose an available exam to inspect its results."
            if history else "No exam history was collected for this course.")
        for exam in history:
            if exam["id"] == data["default_exam_id"]:
                data.update({k: v for k, v in exam.items() if k in GRADE_FIELDS})
        result[course] = data
    for key, percentile in (("avg", "avgp"), ("passpercent", "pp")):
        insertPercentile([[course, data[key]] for course, data in result.items() if key in data], percentile, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True, help="Oldest report first; repeat for newer evidence")
    parser.add_argument("--extension", type=Path, default=Path("extension"))
    parser.add_argument("--output", type=Path, default=Path("dist/chrome-beta-2.5.0-beta.3"))
    args = parser.parse_args(argv)
    if args.output.exists() or Path(str(args.output) + ".zip").exists():
        parser.error("Output already exists; choose a new output directory to preserve the previous build")
    base = json.loads((args.extension / "db/data.json").read_text())
    reports = [json.loads(path.read_text()) for path in args.report]
    dataset = build_dataset(base, reports)
    shutil.copytree(args.extension, args.output)
    (args.output / "db/data.json").write_text(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")))
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(name="DTU Course Analyzer Beta", version="2.5.0.3", version_name="2.5.0-beta.3")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    archive = Path(str(args.output) + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(args.output.rglob("*")):
            if path.is_file():
                stream.write(path, path.relative_to(args.output))
    print(f"Built {len(dataset)} courses in {args.output}; archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
