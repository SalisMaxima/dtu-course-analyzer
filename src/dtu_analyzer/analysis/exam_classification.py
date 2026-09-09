"""Provisional exam-period classification for diagnostics and opt-in beta builds.

These are schedule-based hypotheses, not verified first-attempt populations.
Keep unknown periods and mixed schedules visible instead of guessing.
"""

import re
from .course_history_reviews import (NEW_COURSES, REVIEWED_NPE, history_review,
    EXCLUDED_HISTORY, PREFERRED_SOURCES, REGULAR_SEASON_OVERRIDES, REGULAR_EXAM_OVERRIDES,
    reviewed_broken_histogram)
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


COURSE_CODE = r"(?=[0-9A-Z]{0,4}[0-9])[0-9A-Z]{5}"
COURSE_REFERENCE = re.compile(
    rf"\b(?:course|kursus)\s+({COURSE_CODE})\b|\b({COURSE_CODE})\s*\(", re.I)
# Only consume explicit schedule notation, stopping before narrative prose.
PERIOD_WORD = r"(?:autumn|fall|efterår|spring|forår|january|januar|june|juni|july|juli|august)"
SCHEDULE_PREFIX = re.compile(
    rf"^({PERIOD_WORD}\b(?:\s+(?:and|og)\s+{PERIOD_WORD}\b|"
    rf"\s+[EF][1-7][AB]?\b(?:\s*\([^)]*\))?|"
    rf"\s*[,/]\s*{PERIOD_WORD}\b)*)", re.I)


def schedule_from_text(text: str, course: str | None = None) -> dict:
    """Conservative fallback for flattened legacy evidence and plain text cells."""
    references = sorted({(a or b).upper() for a, b in COURSE_REFERENCE.findall(text)
                         if (a or b).upper() != (course or "").upper()})
    match = SCHEDULE_PREFIX.match(text.strip())
    explicit = match[1] if match else ""
    notes = text.strip()[match.end():].strip() if match else text
    basis = explicit or text
    periods = [p for p, pattern in PERIOD_PATTERNS.items()
               if re.search(pattern, basis, re.I)]
    ambiguous = False
    # A period mentioned in prose is safe to ignore only when it repeats the
    # explicit schedule or is in a sentence referring to another course.
    for sentence in re.split(r"(?<=[.!?])\s+", notes):
        extra = [p for p, pattern in PERIOD_PATTERNS.items()
                 if p not in periods and re.search(pattern, sentence, re.I)]
        for period in extra:
            pattern = PERIOD_PATTERNS[period]
            # Only ignore a month when the text directly associates it with an
            # alternative course, not merely because a code occurs somewhere.
            attributed = any(
                re.search(rf"\b{re.escape(code)}\s*\(\s*{pattern}", sentence, re.I)
                or re.search(rf"{pattern}(?:\s+\w+){{0,3}}\s*\(\s*(?:course|kursus)\s+{re.escape(code)}\b",
                             sentence, re.I)
                for code in references)
            if not attributed:
                ambiguous = True
    if not explicit and references:
        ambiguous = True
    return {"raw": text, "explicit": explicit, "explanation": notes,
            "periods": periods, "referenced_courses": references,
            "contains_course_references": bool(references),
            "ambiguous_explanation": ambiguous, "basis": "text_prefix" if explicit else "text_fallback"}


def extract_schedule(html: str, course: str | None = None) -> dict:
    """Preserve schedule markup boundaries and explanatory continuation rows."""
    soup = BeautifulSoup(html, "lxml")
    fields, continuations, segments = [], [], []
    reading = False
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True).rstrip(":").strip().lower()
        if label in SCHEDULE_LABELS:
            reading = True
            fields.extend(c.get_text(" ", strip=True) for c in cells[1:])
            for cell in cells[1:]:
                fragment = BeautifulSoup(str(cell), "lxml")
                for boundary in fragment.find_all(["br", "p", "div"]):
                    boundary.insert_before("DTU_SCHEDULE_BOUNDARY")
                segments.extend(part.strip() for part in fragment.get_text(" ", strip=True).split("DTU_SCHEDULE_BOUNDARY") if part.strip())
        elif reading and not label:
            continuations.extend(c.get_text(" ", strip=True) for c in cells[1:])
        else:
            reading = False
    result = schedule_from_text("\n".join(fields + continuations), course)
    if len(segments) > 1:
        first = SCHEDULE_PREFIX.fullmatch(segments[0])
        if first:
            result["explicit"] = segments[0]
            result["explanation"] = "\n".join(segments[1:])
            result["basis"] = "structured_schedule"
    # Continuation rows are explicitly explanatory, but retain them as evidence.
    if continuations:
        if result["basis"] == "structured_schedule":
            result["explanation"] = "\n".join(filter(None, [result["explanation"], *continuations]))
        result["continuation_text"] = "\n".join(continuations)
    return result


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
    record.pop("history_status", None)
    record.pop("default_selection_note", None)
    schedule = record.get("schedule", {})
    periods = schedule.get("periods", [])
    reasons = []
    primary_season = None
    if not periods:
        reasons.append("schedule_missing_or_unrecognized")
    elif schedule.get("ambiguous_explanation", schedule.get("contains_course_references")):
        reasons.append("schedule_contains_other_course_references" if schedule.get("contains_course_references")
                       else "ambiguous_schedule_explanation")
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
        exam.pop("reviewed_unavailable", None)
        period = exam["period"]
        exam.setdefault("distribution_status", "failed" if exam.get("error") else "published")
        # Infer from the source URL too, so replayed/legacy records cannot
        # bypass identity review merely by lacking the new metadata.
        source_parts = urlsplit(exam.get("url", "")).path.rstrip("/").split("/")
        source_id = source_parts[-2] if len(source_parts) >= 2 else ""
        if (record.get("course") and re.fullmatch(r"[0-9A-Z]{5}(?:-[0-9]+)?", source_id)
                and source_id.split("-")[0] != record["course"]):
            exam["histogram_course"] = source_id
            exam["identity_status"] = "different_course_requires_review"
        elif re.fullmatch(r"[0-9A-Z]{5}-[0-9]+", source_id):
            exam["histogram_course"] = source_id
            exam["identity_status"] = "variant_requires_review"
        review = history_review(record.get("course"), source_id)
        if review:
            exam["identity_status"] = "manually_approved_history"
            exam["identity_review"] = review
        exam["display_eligible"] = source_id not in EXCLUDED_HISTORY.get(record.get("course"), set())
        if reviewed_broken_histogram(record.get("course"), exam):
            exam["display_eligible"] = False
            exam["reviewed_unavailable"] = True
        if exam.get("error"):
            exam["reason"] = "histogram_fetch_or_parse_failed"
        elif exam.get("identity_status") == "different_course_requires_review":
            exam["reason"] = "different_course_identity_unverified"
        elif exam.get("identity_status") == "variant_requires_review":
            exam["reason"] = "course_variant_identity_unverified"
        elif exam["distribution_status"] != "suppressed" and (exam.get("grades") or {}).get("participants", 0) <= 0:
            exam["reason"] = "no_published_results"
        elif (record.get("course"), source_id, period.get("label")) in REGULAR_EXAM_OVERRIDES:
            exam.update(classification="ordinary_candidate", reason="maintainer_reviewed_historical_regular_exam")
        elif period["season"] in REGULAR_SEASON_OVERRIDES.get((record.get("course"), source_id), set()):
            exam.update(classification="ordinary_candidate", reason="maintainer_reviewed_twice_yearly_offering")
        elif primary_season is None:
            exam["reason"] = reasons[0]
        elif period["season"] not in {"winter", "summer"} or period["year"] is None:
            exam["reason"] = "histogram_period_mapping_unverified"
        elif period["season"] == primary_season:
            exam.update(classification="ordinary_candidate", reason="matches_teaching_period")
        else:
            exam.update(classification="resit_candidate", reason="outside_ordinary_season")
        exams.append(exam)

    ordinary = [e for e in exams if e["classification"] == "ordinary_candidate" and e["display_eligible"]]
    ordinary.sort(key=lambda e: (e["period"]["year"], e["period"]["season"] == "winter"), reverse=True)
    resits = [e for e in exams if e["classification"] == "resit_candidate"]
    resits.sort(key=lambda e: e["period"]["year"], reverse=True)
    unresolved = [e for e in exams if e["classification"] == "undetermined"]
    primary = ordinary[0] if ordinary else None
    if len(ordinary) > 1 and ordinary[0]["period"] == ordinary[1]["period"]:
        primary = None
        reasons.append("multiple_histograms_for_latest_ordinary_period")
    preference = PREFERRED_SOURCES.get(record.get("course"), [])
    if primary and primary.get("histogram_course") == record.get("course"):
        preference = []  # A current-course regular exam supersedes predecessor fallback.
    for preferred in preference:
        eligible = [e for e in exams if e.get("histogram_course") == preferred
                    and e["display_eligible"] and not e.get("error")
                    and e.get("distribution_status") in {"published", "suppressed"}
                    and e["period"].get("year") is not None
                    and e["period"].get("season") in {"winter", "summer"}]
        if eligible:
            eligible.sort(key=lambda e: (e["period"]["year"], e["period"]["season"] == "winter"), reverse=True)
            primary = eligible[0] if len(eligible) == 1 or eligible[0]["period"] != eligible[1]["period"] else None
            record["default_selection_note"] = "Latest available exam from the most recent reviewed predecessor course; historical regular/reexam classification may be unknown."
            break
    if primary and primary.get("reason", "").startswith("maintainer_reviewed"):
        record["default_selection_note"] = "Regular exam selected using maintainer-reviewed historical offering information."
    if not exams:
        reasons.append("no_histogram_links")
    if not exams and record.get("course") in NEW_COURSES:
        record["history_status"] = "new_course_no_history_expected"
    elif not exams and record.get("course") in REVIEWED_NPE:
        record["history_status"] = "reviewed_no_prior_exam_found"
    if not ordinary:
        reasons.append("no_ordinary_exam_identified")
    if unresolved:
        reasons.append("unclassified_histograms")
    if any(e.get("identity_status") == "variant_requires_review" for e in exams):
        reasons.append("course_variant_identity_unverified")
    if any(e.get("identity_status") == "different_course_requires_review" for e in exams):
        reasons.append("different_course_identity_unverified")
    errors = record.get("errors", [])
    status = "provisional" if primary and not unresolved and not reasons else "partial"
    if primary is None:
        status = "undetermined"
    if errors or any(e.get("error") and not e.get("reviewed_unavailable") for e in exams):
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
