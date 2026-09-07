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

Report schema version 2 also records course/info request attempts, HTTP status,
final URL (with authentication query parameters omitted), page title/headings,
table labels, and iframe count. The collector follows DTU's same-course
`forceLogin` iframe once; repeated wrappers or unrecognized pages become explicit
collection errors. It does not store full authentication pages or cookies.
Each parsed histogram includes source/retained category totals and a comparison
with registered participants. The summary counts discrepancies so omitted or
unrecognized result categories remain visible. Approved/not-approved outcomes
are preserved separately from passed/not-passed outcomes.

## Initial hypotheses

| Current schedule | Ordinary candidate | Resit candidate |
| --- | --- | --- |
| Autumn / January | Winter | Summer |
| Spring / June / July | Summer | Winter |
| August | Undetermined | Undetermined |
| Multiple periods all mapping to winter | Winter | Summer |
| Multiple periods all mapping to summer | Summer | Winter |
| Conflicting, unverified or missing teaching periods | Undetermined | Undetermined |

Rule version `schedule-hypothesis-v3` permits combined periods when their ordinary
exam season agrees: Autumn + January maps to winter; Spring + June + July maps
to summer. Autumn + Spring remains unresolved, as does any combination involving
August until its histogram mapping is verified. These combinations identify a
season, not individual cohorts or separate sittings within that season.

The second column chooses the newest parsed year among **all** matching sheets;
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

Only labelled Schedule/Skemaplacering table fields are parsed. References to
other courses within those fields trigger review; descriptions elsewhere do
not contribute months. Missing fields are reported, never inferred from
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
