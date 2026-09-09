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
NEW_COURSES = {"01822", "02262", "02339", "02820"}

# Reviewed absence means unknown availability, never a claim that the course is new.
REVIEWED_NPE = set("""
02984 10081 10406 10415 10869 10960 10961 12125 12150 12615
22214 22240 22286 22514 22531 23303 23513 23721 23750 23851
23934 23955 25216 25342 25357 25624 25625 25840 25841 25842
26250 26470 27029 27032 27064 27066 27200 27221 27232 27450
27829 28217 34063 34064 34375 34555 34766 38311 38312 38400
38401 38402 38403 38404 38405 41264 41349 41518 42S17 42S18
42S19 42S20 46220 46800 46805 62106 62117 62123 62126 62127
62128 62129 62130 62151 62226 62290 62414 62421 62451 62513
62678 62812 62813 62814 MA100 MA239 MA264 MA270 MA271 MA534
MA657 MA678 MA694 MA922
""".split())

REVIEWED_PREDECESSORS = {
    "02581": ["02580"], "12952": ["12950"], "22170": ["27692"],
    "22181": ["22180"], "22461": ["22433"], "25356": ["25314"],
    "25623": ["25617"], "25628": ["25349"], "25825": ["25803"],
    "27827": ["29905"], "34556": ["34551"], "41751": ["41730"],
    "41959": ["11305"], "62222": ["62229"], "62237": ["62236", "62234"],
    "62580": ["62581"], "62713": ["62712"], "62776": ["62775"],
    "MA263": ["41263"], "MA722": ["31301"], "MA776": ["62775"],
}
for course, sources in REVIEWED_PREDECESSORS.items():
    APPROVED_HISTORY.setdefault(course, {}).update({
        source: "Maintainer-reviewed predecessor/shared exam history; source counts are not combined."
        for source in sources
    })

# Explicit decisions, not a general age cutoff or an inferred historical schedule.
EXCLUDED_HISTORY = {"22170": {"27692"}, "25623": {"25617"}}
PREFERRED_SOURCES = {
    "62237": ["62236", "62234"],
    # Approved history is useful even when the historical regular season is unknown.
    "27827": ["29905"], "MA263": ["41263"],
}
REGULAR_SEASON_OVERRIDES = {("12952", "12950"): {"winter", "summer"}}
REGULAR_EXAM_OVERRIDES = {
    ("02581", "02580", "Summer-2025"),
    ("22181", "22180", "Winter-2025"),
}

# Confirmed broken source: ignore only this course/URL when it returns 404.
KNOWN_BROKEN_HISTOGRAMS = {
    ("22461", "https://karakterer.dtu.dk/Histogram/1/22433/Summer-2023"),
}
# Previously collected exam omitted from the latest info-page link list.
# Fetch again; do not infer suppression or manufacture counts from its absence.
EXTRA_HISTORY_URLS = {
    "25205": ["https://karakterer.dtu.dk/Histogram/1/25205/Summer-2022"],
}


def reviewed_broken_histogram(course, exam):
    return ((course, exam.get("url")) in KNOWN_BROKEN_HISTOGRAMS
            and exam.get("error") == "HTTP 404")


def history_review(course, source):
    note = APPROVED_HISTORY.get(course, {}).get(source)
    return {"date": REVIEW_DATE, "note": note} if note else None
