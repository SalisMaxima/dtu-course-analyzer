"""Provisional exam-period classification for the diagnostic workflow only.

These are schedule-based hypotheses, not verified first-attempt populations.
Keep unknown periods and mixed schedules visible instead of guessing.
"""

import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


PERIOD_PATTERNS = {
    "autumn": r"\b(?:autumn|fall|efterår|E[1-7](?:[AB])?)\b",
    "spring": r"\b(?:spring|forår|F[1-7](?:[AB])?)\b",
    "january": r"\b(?:january|januar)\b",
    "june": r"\b(?:june|juni)\b",
    "july": r"\b(?:july|juli)\b",
    "august": r"\baugust\b",
}
SCHEDULE_LABELS = {"schedule", "schedule placement", "skemaplacering"}
ORDINARY_SEASONS = {
    "autumn": "winter", "january": "winter",
    "spring": "summer", "june": "summer", "july": "summer",
}


def extract_schedule(html: str) -> dict:
    """Read the labelled schedule row, never the entire course description."""
    soup = BeautifulSoup(html, "lxml")
    fields = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).rstrip(":").strip().lower()
        if label not in SCHEDULE_LABELS:
            continue
        fields.append(" ".join(c.get_text(" ", strip=True) for c in cells[1:]))
    text = "\n".join(fields)
    # References to other course codes require review: their months must not
    # silently become teaching periods for the course being inspected.
    references = bool(re.search(r"\b[0-9A-Z]{5}\s*\(", text))
    periods = [p for p, pattern in PERIOD_PATTERNS.items()
               if re.search(pattern, text, re.IGNORECASE)]
    return {"raw": text, "periods": periods, "contains_course_references": references}


def parse_period(url: str) -> dict:
    label = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    match = re.fullmatch(r"([A-Za-z]+)-(\d{4}|\d{2})", label)
    season, year = None, None
    if match:
        name, digits = match.groups()
        season = {"winter": "winter", "v": "winter", "summer": "summer",
                  "s": "summer", "august": "august"}.get(name.lower())
        year = int(digits)
        if len(digits) == 2:
            year += 2000 if year < 50 else 1900
    return {"label": label, "season": season, "year": year}


def classify_course(record: dict) -> dict:
    """Assign candidates while retaining all evidence and unresolved sheets."""
    record = dict(record)
    schedule = record.get("schedule", {})
    periods = schedule.get("periods", [])
    reasons = []
    primary_season = None
    if not periods:
        reasons.append("schedule_missing_or_unrecognized")
    elif schedule.get("contains_course_references"):
        reasons.append("schedule_contains_other_course_references")
    elif "august" in periods:
        reasons.append("august_histogram_mapping_unverified")
    elif any(period not in ORDINARY_SEASONS for period in periods):
        reasons.append("schedule_missing_or_unrecognized")
    else:
        seasons = {ORDINARY_SEASONS[period] for period in periods}
        if len(seasons) == 1:
            primary_season = seasons.pop()
        else:
            reasons.append("multiple_teaching_periods")

    exams = []
    for source in record.get("exams", []):
        exam = {**source, "classification": "undetermined", "reason": None}
        period = exam["period"]
        if exam.get("error"):
            exam["reason"] = "histogram_fetch_or_parse_failed"
        elif exam.get("grades", {}).get("participants", 0) <= 0:
            exam["reason"] = "no_published_results"
        elif primary_season is None:
            exam["reason"] = reasons[0]
        elif period["season"] not in {"winter", "summer"} or period["year"] is None:
            exam["reason"] = "histogram_period_mapping_unverified"
        elif period["season"] == primary_season:
            exam.update(classification="ordinary_candidate", reason="matches_teaching_period")
        else:
            exam.update(classification="resit_candidate", reason="outside_ordinary_season")
        exams.append(exam)

    ordinary = [e for e in exams if e["classification"] == "ordinary_candidate"]
    ordinary.sort(key=lambda e: e["period"]["year"], reverse=True)
    resits = [e for e in exams if e["classification"] == "resit_candidate"]
    resits.sort(key=lambda e: e["period"]["year"], reverse=True)
    unresolved = [e for e in exams if e["classification"] == "undetermined"]
    primary = ordinary[0] if ordinary else None
    if len(ordinary) > 1 and ordinary[0]["period"]["year"] == ordinary[1]["period"]["year"]:
        primary = None
        reasons.append("multiple_histograms_for_latest_ordinary_period")
    if not exams:
        reasons.append("no_histogram_links")
    if not ordinary:
        reasons.append("no_ordinary_exam_identified")
    if unresolved:
        reasons.append("unclassified_histograms")
    errors = record.get("errors", [])
    status = "provisional" if primary and not unresolved and not reasons else "partial"
    if primary is None:
        status = "undetermined"
    if errors or any(e.get("error") for e in exams):
        status = "error"
    record.update(
        status=status, primary_exam=primary, ordinary_exams=ordinary,
        resit_exams=resits, undetermined_exams=unresolved, exams=exams,
        reasons=reasons, classification_basis="current_schedule_inference",
        primary_status="identified" if primary else "undetermined",
        resit_status="candidates_found" if resits else "undetermined" if unresolved or errors or primary is None else "none_found_in_collected_links",
        caveats=[
            "Assignments are hypotheses; they have not been manually verified.",
            "Current schedule may differ from historical course schedules.",
            "An ordinary-period histogram may include repeat attempts.",
            "Summer/August grouping is unverified; resits are not paired to cohorts.",
        ],
    )
    return record
