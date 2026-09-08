"""Explicit maintainer decisions; mappings are directional, never transitive.

Reviewed by the maintainer in the September 8, 2026 beta preparation.
These approvals associate history, not individual students or cohorts.
"""

REVIEW_DATE = "2026-09-08"
APPROVED_HISTORY = {
    "02280": {"02285": "Previous course number; accepted as the same course."},
    "02426": {"02424": "Previous course number; accepted as the same course."},
    "23103": {"23102": "Shared historical exam with 23104; counts must not be combined."},
    "23104": {"23102": "Shared historical exam with 23103; counts must not be combined."},
}
NEW_COURSES = {"01822", "02262"}


def history_review(course, source):
    note = APPROVED_HISTORY.get(course, {}).get(source)
    return {"date": REVIEW_DATE, "note": note} if note else None
