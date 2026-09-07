# Exam classification diagnostic

Run **Actions → Test Exam Classification → Run workflow**. Leave `courses`
empty to discover and inspect all current courses. For an initial smaller run,
enter `01001,01911,02443,42500,42501,42504`. The workflow uses the existing
`DTU_USERNAME` and `DTU_PASSWORD` Actions secrets. It does not update extension
data, commit files, or open issues.

Download the `exam-classification-report` artifact:

- `courses.csv`: one registration for every requested course, with status,
  schedule, proposed latest primary exam, all proposed resit URLs, unresolved
  URLs, and reasons/errors. Import the course column as text to preserve zeros.
- `report.json`: the same registrations plus all historical ordinary candidates,
  grade counts, source URLs/link labels, original schedule text, and histogram
  headings/table text for checking the inference against the source.
- `summary.md`: totals by status and unresolved reason, also shown in Actions.

Assignments are hypotheses, not measured accuracy. `provisional` means a primary
and at least one resit candidate were found without unresolved sheets. `partial`
means a primary was found but resits or other sheets remain unresolved.
`undetermined` means no unique primary could be assigned. `error` indicates a
collection/parsing problem; usable partial evidence is still retained. Checkpoints
are saved every 25 completed courses; `pending` registrations in an interrupted
run mean collection had not been checkpointed. A complete run returns nonzero
for collection errors, but unresolved classifications alone do not fail it.

## Initial hypotheses

| Current schedule | Ordinary candidate | Resit candidate |
| --- | --- | --- |
| Autumn / January | Winter | Summer |
| Spring / June / July | Summer | Winter |
| August | Undetermined | Undetermined |
| Multiple or missing teaching periods | Undetermined | Undetermined |

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
