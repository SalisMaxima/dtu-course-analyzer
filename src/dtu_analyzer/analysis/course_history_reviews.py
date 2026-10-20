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


# Maintainer review of blocked Update Course Data run 39266739682 on 2026-10-20.
# The record of each decision is docs/course-review-39266739682.md.
OCTOBER_REVIEW_DATE = "2026-10-20"
OCTOBER_APPROVED_HISTORY = {
    "02234": {"02234-2": "Current histograms are published under 02234-2; accepted as the same course."},
    "26407": {"26407-1": "Current histograms are published under 26407-1; accepted as the same course."},
    "26455": {"26455-1": "Current histograms are published under 26455-1; accepted as the same course."},
    "30224": {"30220": "Previous course number; its older results stay available for selection."},
}
for course, sources in OCTOBER_APPROVED_HISTORY.items():
    APPROVED_HISTORY.setdefault(course, {}).update(sources)

# Exact published entries the maintainer accepted losing: retired old exams,
# dropped predecessor links and histograms that moved to a variant number.
APPROVED_HISTORY_REMOVALS = {
    course: {"https://karakterer.dtu.dk/Histogram/1/" + entry for entry in entries}
    for course, entries in {
        "01037": {"01037/Summer-2024", "01037/Winter-2023"},
        "02234": {"02234/Summer-2026", "02234/Winter-2025", "02234/Summer-2025", "02234/Winter-2024", "02234/Winter-2023"},
        "02349": {"02346/Summer-2026", "02346/Summer-2025", "02346/Summer-2024", "02346/Summer-2023"},
        "02465": {"02465/Summer-2023"},
        "12614": {"12614-1/Summer-2024"},
        "22239": {"27692/Winter-2023"},
        "22449": {"22435/Winter-2024"},
        "26022": {"26026/Summer-2023"},
        "26407": {"26407/Summer-2026", "26407/Winter-2025", "26407/Summer-2025", "26407/Winter-2024", "26407/Summer-2024"},
        "26455": {"26455/Summer-2025", "26455/Summer-2024", "26455/Summer-2023", "26455/Summer-2022"},
        "27101": {"27101/Winter-2024"},
        "28160": {"28160/Summer-2024"},
        "30224": {"30220/Summer-2024"},
        "34721": {"34721-1/Winter-2024"},
        "34723": {"34723-1/Winter-2024"},
        "41970": {"11300/Summer-2022"},
        "42620": {"42620/Summer-2024"},
        "47319": {"47319/Winter-2022"},
    }.items()
}

# Taught in both spring and autumn, so both exam seasons are regular.
REGULAR_SEASON_OVERRIDES.update({
    ("34721", "34721"): {"winter", "summer"},
    ("34723", "34723"): {"winter", "summer"},
})

# Explicit default exams. Many courses show a suppressed Winter-2026 histogram
# (apparently a one-person exam) that would otherwise become the default.
# None means: show no default and let people choose an older exam.
DEFAULT_EXAM_OVERRIDES = {
    course: "https://karakterer.dtu.dk/Histogram/1/" + entry if entry else None
    for course, entry in {
        "02234": "02234-2/Winter-2025",
        "02289": "02289/Winter-2025",
        "02452": "02452/Winter-2025",
        "02517": "02517/Winter-2025",
        "22449": "22449/Winter-2025",
        "42620": "42620/Winter-2025",
        "46745": "46745/Winter-2025",
        "34721": "34721/Summer-2026",
        "34723": "34723/Summer-2026",
        "30224": None,
    }.items()
}
# Explicit course evaluations, matched to the default exam's cohort. Evaluations
# are named by calendar month (Jan 26, semester E-25); histograms by semester (v25).
REVIEW_SHEET_OVERRIDES = {
    "42620": "/kursus/42620/355671",  # Jan 26 (E-25-03), 612 could respond; Winter-2025 has 611 registered.
}
NO_DEFAULT_NOTE ="The latest exam had too few participants to publish results. Choose an earlier exam to inspect its results."

REVIEWED_NPE.add("02197")

# No longer offered in the DTU course base; its published data may be dropped.
REMOVED_COURSES = {"34764": "Not in the 2026/2027 course search; maintainer confirmed no current information."}

# Courses the truncated course list kept out of run 39266739682. The maintainer
# accepts whatever the next complete collection finds for them. This applies
# only while the published dataset is still the one reviewed here, so it
# lapses as soon as a new dataset is promoted.
ACCEPTED_REFRESH_BASELINE_SHA256 = "815bf2da3e0535c84422402570a340ef90a474228f567bbd681f49da17a132ed"
ACCEPTED_REFRESH_COURSES = set("""
47519 47527 47528 56867 62000 62001 62008 62010 62014 62019
62024 62030 62033 62039 62041 62048 62054 62074 62079 62090
62096 62101 62104 62106 62108 62112 62117 62120 62123 62126
62127 62128 62129 62130 62133 62134 62139 62142 62143 62150
62151 62174 62177 62191 62198 62199 62200 62207 62210 62211
62218 62222 62223 62226 62231 62233 62235 62237 62243 62249
62261 62263 62265 62267 62268 62271 62272 62273 62276 62277
62278 62283 62284 62285 62286 62287 62288 62290 62319 62324
62326 62329 62331 62333 62360 62361 62370 62381 62389 62410
62413 62414 62421 62422 62424 62426 62427 62428 62443 62444
62451 62452 62453 62454 62484 62513 62517 62521 62523 62525
62531 62533 62550 62560 62575 62580 62582 62589 62595 62602
62604 62614 62616 62622 62629 62637 62640 62641 62642 62643
62646 62657 62670 62675 62677 62678 62683 62694 62696 62704
62708 62711 62713 62716 62733 62734 62735 62743 62748 62752
62755 62756 62760 62761 62762 62763 62764 62766 62768 62773
62774 62776 62782 62783 62798 62802 62806 62807 62809 62810
62811 62812 62813 62814 62908 62999 63851 63852 63853 63860
63861 63870 63880 63881 88383 KU002 KU003 KU004 KU005 KU006
KU010 KU011 KU013 KU101 KU103 KU105 KU180 KU181 LY100 LY200
LY300 MA100 MA143 MA200 MA239 MA263 MA264 MA270 MA271 MA300
MA534 MA604 MA646 MA657 MA675 MA678 MA694 MA722 MA776 MA911
MA922
""".split())


def reviewed_broken_histogram(course, exam):
    return ((course, exam.get("url")) in KNOWN_BROKEN_HISTOGRAMS
            and exam.get("error") == "HTTP 404")


def history_review(course, source):
    note = APPROVED_HISTORY.get(course, {}).get(source)
    date = OCTOBER_REVIEW_DATE if source in OCTOBER_APPROVED_HISTORY.get(course, {}) else REVIEW_DATE
    return {"date": date, "note": note} if note else None
