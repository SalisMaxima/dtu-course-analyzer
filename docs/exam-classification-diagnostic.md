# Exam classification diagnostic

Run **Actions → Test Exam Classification → Run workflow**. Leave `courses`
empty to discover and inspect all current courses. For an initial smaller run,
enter `01001,01911,02443,42500,42501,42504`. The workflow uses the existing
`DTU_USERNAME` and `DTU_PASSWORD` Actions secrets. It does not update extension
data, commit files, or open issues.

## Diagnosing schedule access on GitHub Actions

The authentication step now runs a comparison immediately after login, before
closing Playwright. `auth_courses` defaults to `01001,01020` (failing example and
working control); it accepts up to seven course IDs independently of `courses`.
No local browser session is required.

The artifact additionally contains `auth-report.json` and `auth-summary.md`.
For each course it compares:

1. A browser page, including iframe contents, with the complete login state.
2. Playwright requests with the full cookie state and browser user agent.
3. aiohttp with only the exported session cookie and the same browser user agent.
4. aiohttp with only that cookie and the classification diagnostic's user agent.

Each mode receives an isolated copy of the initial login state. Cookie names,
domains, paths and security flags are recorded, along with sanitized navigation
URLs/statuses and whether a schedule was recovered. Cookie values, full storage
state, passwords, authentication HTML and screenshots are not added to these
artifacts. Redirects in request probes are bounded and restricted to DTU HTTPS
destinations. Comparisons checkpoint after each mode, including failures.

Full-cookie success with session-only failure points toward cookie-state or HTTP
client differences; browser-only success points toward browser navigation/storage;
a difference between the two session-only probes points toward the user agent.
These are hypotheses, not proof: server-side session state can still evolve
during the sequential tests. Inspect navigation evidence before changing production
authentication. If all modes succeed, the original failure was not reproduced.

The normal classification collection still follows this step. Authentication
failure prevents collection but produces an authentication diagnostic artifact.
This does not export extra cookies to the normal scraper or automatically adopt
any inferred authentication fix.

Download the `exam-classification-report` artifact:

- `courses.csv`: one registration for every requested course, with status,
  schedule, proposed latest primary exam, all proposed resit URLs, unresolved
  URLs, and reasons/errors. Import the course column as text to preserve zeros.
- `report.json`: the same registrations plus all historical ordinary candidates,
  grade counts, source URLs/link labels, original schedule text, and histogram
  headings/table text for checking the inference against the source.
- `summary.md`: totals by status and unresolved reason, also shown in Actions.

Assignments are hypotheses, not measured accuracy. `provisional` means a primary
was found without unresolved sheets. `partial` means a primary was found but
other sheets remain unresolved. Separate `primary_status` and `resit_status`
fields distinguish a successful primary selection from resit availability.
`none_found_in_collected_links` means no resit candidate was discovered; it does
not assert that the course has no resits.
`undetermined` means no unique primary could be assigned. `error` indicates a
collection/parsing problem; usable partial evidence is still retained. Checkpoints
are saved every 25 completed courses; `pending` registrations in an interrupted
run mean collection had not been checkpointed. A complete run returns nonzero
for collection errors, but unresolved classifications alone do not fail it.

Report schema version 4 also records course/info request attempts, HTTP status,
final URL (with authentication query parameters omitted), page title/headings,
table labels, and iframe count. The collector follows DTU's same-course
`forceLogin` iframe once; repeated wrappers or unrecognized pages become explicit
collection errors. It does not store full authentication pages or cookies.
Each parsed histogram includes source/retained category totals and a comparison
with registered participants. The summary counts discrepancies so omitted or
unrecognized result categories remain visible. It also counts mixed numeric and
pass/fail histograms for manual review. Approved/not-approved outcomes are
preserved separately from passed/not-passed outcomes.

## Initial hypotheses

| Current schedule | Ordinary candidate | Resit candidate |
| --- | --- | --- |
| Autumn / January | Winter | Summer |
| Spring / June / July | Summer | Winter |
| August | Undetermined | Undetermined |
| Multiple periods all mapping to winter | Winter | Summer |
| Multiple periods all mapping to summer | Summer | Winter |
| Conflicting, unverified or missing teaching periods | Undetermined | Undetermined |

Rule version `schedule-hypothesis-v5` permits combined periods when their ordinary
exam season agrees: Autumn + January maps to winter; Spring + June + July maps
to summer. Autumn + Spring remains unresolved, as does any combination involving
August until its histogram mapping is verified. These combinations identify a
season, not individual cohorts or separate sittings within that season.

The second column chooses the newest recognized year among **all** matching sheets,
including suppressed distributions;
participant count does not choose the exam. Zero-participant sheets remain
unresolved. The third column only means "outside the presumed ordinary season",
not confirmation that it is a resit. All resit candidates across all available
years are retained; they are not paired with the primary's student cohort.

DTU's [resit rules](https://student.dtu.dk/studieregler/eksamen/reeksamen)
place spring/June/July resits in August, and August-course resits in December.
The histogram service's Summer/August grouping remains unverified. Explicit
August or unknown URL labels stay unresolved so the collected evidence can
establish that mapping. Current schedules may not apply to historical sheets;
an ordinary-period histogram may itself include repeat attempts.

Only labelled Schedule/Skemaplacering fields and their explanatory continuation
rows are retained. Explicit schedule notation is separated from prose, preserving
markup boundaries when present. Periods clearly attributed to another course are
excluded. Additional periods in ambiguous prose about the current course trigger
review; descriptions elsewhere do not contribute months. Missing fields are reported, never inferred from
participant counts. Duplicate source links are fetched once, while multiple
histogram groups for the latest ordinary period prevent a unique assignment.

## Reviewing the experiment

Start with the supplied examples and a spring course. Check the primary/resit
links against their schedules, then inspect August, mixed-period and failed
records. Use the JSON's period labels and table evidence to determine whether
August is a distinct histogram period or grouped with summer. Coverage totals
alone do not establish correctness: manually verify assignments before applying
these rules to production. No production selection or UI behavior uses this code.

## Local execution

With the package installed and a session from `dtu-auth`:

```bash
python -m dtu_analyzer.scripts.probe_exam_classification --courses 01001,01911,02443,42504
```

For all courses, run `dtu-get-courses`, then omit `--courses`. Optional
`--course-file` and `--output` flags select a course list and report directory.
The existing `MAX_CONCURRENT`, `TIMEOUT`, retry and pacing settings apply.

Tests use synthetic HTML, not authenticated live fixtures:

```bash
python -m pytest tests/test_exam_classification.py
```

## Availability and discrepancies (schema 4)

Every collected histogram has a `distribution_status`: `published`,
`suppressed`, or `failed`. DTU's small-cohort suppression message produces
`suppressed`, null grades, and no fabricated counts. Its period can still be an
ordinary/resit candidate. A suppressed latest ordinary exam remains primary;
older visible exams are listed separately and never silently substituted.
Genuine HTTP/authentication/parsing failures still produce error status.

JSON includes `distribution_summary` and `count_summary`. CSV additionally
records primary distribution availability, suppressed/failed histogram counts,
category-retention failures, participant discrepancies, and info-page state.
A histogram's `participant_difference` is registered participants minus its
source result total. This is separate from source categories lost during
normalization. Discrepancies are preserved, not filled with invented outcomes.

Mixed grading requires positive counts in both numerical and categorical
outcomes. Zero categorical placeholders alongside numeric results remain
seven-point grading; categorical-only zero distributions remain pass/fail.

Info-page evidence distinguishes `links_found`, `no_published_results`
(explicit source message), `no_links_unknown`, `empty_response`, and
`info_page_unrecognized`. Authentication failures are recorded on request
attempts before page content is captured. Missing links alone never establish
that results do not exist. Request attempts now include content type and the
UTF-8 byte length of the decoded response. Additional evidence includes bounded
result-related excerpts, link counts and sanitized course/histogram destinations;
forms, scripts, authentication URLs and credential query parameters are excluded.

## Replaying saved evidence

No authentication or network is needed:

```bash
python -m dtu_analyzer.scripts.probe_exam_classification --replay test5/report.json --output exam-classification-report/test5-replayed
```

The original report is preserved. The output is labelled as an offline replay.
Legacy flattened schedules can be reinterpreted conservatively, but missing
info-page content and original schedule markup cannot be recovered this way.
Replay returns success when report generation succeeds; remaining collection
errors are retained in the output rather than re-fetched.

For the next **Test Exam Classification** Actions run after pushing these changes:
- `courses`: `01025,01034,01037,01018,01004,01666,01911`
- `auth_courses`: `01001,01020`

This covers an unrecognized info page, other-course references, August,
suppressed histograms, zero categorical placeholders, ambiguous prose and
compatible combined periods. Save the artifact for review before another full
run. Production regular/resit selection remains unchanged.


## Suffixed histogram identities

Schema 4 / rule `schedule-hypothesis-v5` collects the exact course ID and
numeric suffixes such as `01025-2`, while excluding unrelated IDs and arbitrary
suffix text. Canonical URLs keep variants separate. JSON records
`histogram_course`, `identity_status`, and `histogram_title` alongside the
current course name and source headings. Titles are evidence for manual review;
translated or similar names do not automatically establish identity.

Every suffixed variant has `identity_status=variant_requires_review` and
classification reason `course_variant_identity_unverified`. It is not selected
as primary or resit, even if its year is newer than an exact-ID exam. Its grade
availability is independent: a small-cohort variant can be `suppressed` and
identity-unverified without being a collection error. CSV lists `variant_urls`;
the summary counts variants requiring review.

Next run **Test Exam Classification** on the updated branch with
`courses=01025,01001` and `auth_courses=01001,01020`. Check that 01025's suffixed
links appear and its Summer-2026 distribution is suppressed, while 01001 remains
the exact-ID control. Review this artifact before another all-course run.
Previous artifacts cannot recover links discarded by the old filter; a fresh
Actions run is required. Production selection and bundled data are unchanged.
