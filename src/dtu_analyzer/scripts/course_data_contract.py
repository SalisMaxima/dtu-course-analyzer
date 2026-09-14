"""Version-one public dataset validation. No normalization or reconstruction."""

from datetime import datetime, timezone
import json
import math
import re

from ..analysis.course_history_reviews import APPROVED_HISTORY, EXCLUDED_HISTORY, PREFERRED_SOURCES

MAX_PAYLOAD = 16 * 1024 * 1024
MAX_ENVELOPE = 32 * 1024
MAX_COURSES = 10_000
MAX_EXAMS = 128
COURSE_ID = re.compile(r"[0-9A-Z]{5}")
SOURCE_URL = re.compile(
    r"https://karakterer\.dtu\.dk/Histogram/[1-9][0-9]{0,3}/"
    r"([0-9A-Z]{5}(?:-[0-9]{1,3})?)/(Summer|Winter)-([0-9]{4})"
)
GRADE_KEYS = {
    "-3",
    "00",
    "02",
    "4",
    "7",
    "10",
    "12",
    "absent",
    "sick",
    "passed",
    "not_passed",
    "approved",
    "not_approved",
}
RESULT_FIELDS = {
    "grade_source",
    "grade_period",
    "grades",
    "grading_scale",
    "grade_participants",
    "passpercent",
    "avg",
}
COURSE_FIELDS = RESULT_FIELDS | {
    "name",
    "name_en",
    "review_participants",
    "qualityscore",
    "workload",
    "lazyscore",
    "default_exam_id",
    "exam_history",
    "history_collected_at",
    "exam_default_note",
    "avgp",
    "pp",
}
EXAM_FIELDS = RESULT_FIELDS | {
    "id",
    "year",
    "season",
    "classification",
    "distribution_status",
    "identity_status",
    "histogram_course",
    "title",
    "identity_note",
    "participant_difference",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(content, limit=MAX_PAYLOAD):
    require(len(content) <= limit, "JSON byte limit exceeded")

    def pairs(items):
        result = {}
        for key, value in items:
            require(
                key not in result and key not in {"__proto__", "prototype", "constructor"},
                "Duplicate or forbidden object key",
            )
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid or excessively nested JSON") from exc


def timestamp(value):
    require(isinstance(value, str) and len(value) <= 40, "Invalid timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def number(value, low, high, integer=False):
    require(
        type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
        "Invalid numeric value",
    )
    require(not integer or type(value) is int, "Expected integer")


def text(value, nullable=False):
    require(
        (nullable and value is None)
        or (
            isinstance(value, str)
            and len(value) <= 4096
            and not any(0xD800 <= ord(c) <= 0xDFFF for c in value)
        ),
        "Invalid text",
    )


def result_fields(record):
    require("avgp" not in record or "avg" in record, "Grade percentile without an average")
    require("pp" not in record or "passpercent" in record, "Pass percentile without a pass rate")
    for key in {
        "avgp",
        "pp",
        "qualityscore",
        "workload",
        "lazyscore",
        "passpercent",
    } & record.keys():
        number(record[key], 0, 100)
    for key in {"grade_participants", "review_participants"} & record.keys():
        number(record[key], 0, 1_000_000, integer=True)
    if "avg" in record:
        number(record["avg"], -3, 12)
        require(record.get("grading_scale") == "seven_point", "Average on nonnumeric scale")
    if "grades" in record:
        grades = record["grades"]
        require(
            isinstance(grades, dict) and bool(grades) and set(grades) <= GRADE_KEYS,
            "Invalid grade categories",
        )
        for value in grades.values():
            if isinstance(value, str):
                require(re.fullmatch(r"[0-9]{1,7}", value), "Invalid grade count")
                value = int(value)
            number(value, 0, 1_000_000, integer=True)
        require(
            record.get("grading_scale") in {"seven_point", "pass_fail", "mixed"},
            "Invalid grading scale",
        )
        # Match the analyzer's scale rules using already-normalized public keys;
        # its raw-source alias parser is deliberately not used on public records.
        binary_keys = {"passed", "not_passed", "approved", "not_approved"}
        numeric = any(int(grades.get(k, 0)) > 0 for k in {"-3", "00", "02", "4", "7", "10", "12"})
        binary_positive = any(int(grades.get(k, 0)) > 0 for k in binary_keys)
        scale = (
            "mixed"
            if numeric and binary_positive
            else (
                "seven_point"
                if numeric
                else "pass_fail" if binary_keys & grades.keys() else "seven_point"
            )
        )
        require(
            scale == record["grading_scale"],
            "Grading scale disagrees with the histogram categories",
        )


def validate_dataset(content):
    """Reject invalid data; return the original object without fabricating fields."""
    data = strict_json(content)
    require(isinstance(data, dict) and 0 < len(data) <= MAX_COURSES, "Invalid course count")
    for course_id, course in data.items():
        require(COURSE_ID.fullmatch(course_id), "Invalid course identifier")
        require(isinstance(course, dict) and set(course) <= COURSE_FIELDS, "Invalid course fields")
        require(
            {"default_exam_id", "exam_history", "history_collected_at"} <= course.keys(),
            "Missing course schema fields",
        )
        for key in {"name", "name_en", "exam_default_note"} & course.keys():
            text(course[key])
        timestamp(course["history_collected_at"])
        result_fields(course)
        exams = course["exam_history"]
        require(isinstance(exams, list) and len(exams) <= MAX_EXAMS, "Invalid exam history")
        by_id = {}
        for exam in exams:
            require(isinstance(exam, dict) and set(exam) <= EXAM_FIELDS, "Invalid exam fields")
            required = {
                "id",
                "grade_source",
                "grade_period",
                "year",
                "season",
                "classification",
                "distribution_status",
                "identity_status",
                "histogram_course",
            }
            require(required <= exam.keys(), "Missing exam fields")
            text(exam["id"])
            match = SOURCE_URL.fullmatch(exam["id"])
            require(match and exam["grade_source"] == exam["id"], "Invalid source URL")
            require(exam["id"] not in by_id, "Duplicate exam ID")
            by_id[exam["id"]] = exam
            histogram, season, year = match.groups()
            require(
                exam["histogram_course"] == histogram
                and exam["season"] == season.lower()
                and type(exam["year"]) is int
                and exam["year"] == int(year)
                and exam["grade_period"] == f"{season}-{year}",
                "Inconsistent exam identity",
            )
            number(exam["year"], 1900, 2200, integer=True)
            require(
                exam["classification"] in {"ordinary_candidate", "resit_candidate", "undetermined"},
                "Invalid exam classification",
            )
            require(
                exam["identity_status"]
                in {
                    "exact_course_id",
                    "manually_approved_history",
                    "different_course_requires_review",
                    "variant_requires_review",
                },
                "Invalid history status",
            )
            if exam["identity_status"] == "exact_course_id":
                require(histogram == course_id, "Wrong exact course identity")
            if exam["identity_status"] == "manually_approved_history":
                require(
                    histogram in APPROVED_HISTORY.get(course_id, {}),
                    "Unapproved historical identity",
                )
            require(
                histogram not in EXCLUDED_HISTORY.get(course_id, set()),
                "Excluded historical identity",
            )
            for key in {"title", "identity_note"} & exam.keys():
                text(exam[key], nullable=key == "title")
            result_fields(exam)
            require(
                exam["distribution_status"] in {"published", "suppressed"}, "Invalid distribution"
            )
            if exam["distribution_status"] == "suppressed":
                require(
                    not (
                        {
                            "grades",
                            "avg",
                            "passpercent",
                            "grade_participants",
                            "grading_scale",
                            "participant_difference",
                        }
                        & exam.keys()
                    ),
                    "Suppressed grades must be absent",
                )
            else:
                require(
                    {"grades", "grade_participants", "passpercent", "grading_scale"} <= exam.keys(),
                    "Missing published results",
                )
                if "participant_difference" in exam:
                    number(exam["participant_difference"], -1_000_000, 1_000_000, integer=True)
                    require(
                        exam["grade_participants"] - sum(int(v) for v in exam["grades"].values())
                        == exam["participant_difference"],
                        "Inconsistent participant difference",
                    )
        default = course["default_exam_id"]
        if default is None:
            require(
                not ((RESULT_FIELDS | {"avgp", "pp"}) & course.keys()),
                "Results without a default exam",
            )
        else:
            require(isinstance(default, str) and default in by_id, "Unknown default exam")
            selected = by_id[default]
            require(
                (
                    selected["classification"] == "ordinary_candidate"
                    or selected["histogram_course"] in PREFERRED_SOURCES.get(course_id, [])
                )
                and selected["identity_status"] in {"exact_course_id", "manually_approved_history"},
                "Default exam must have approved ordinary identity",
            )
            for key in RESULT_FIELDS:
                require(
                    (key in course) == (key in selected) and course.get(key) == selected.get(key),
                    f"Default exam disagrees with course: {key}",
                )
    return data
