# Production pipeline validation

## Current integration and next Actions run

**Update Course Data** now runs the raw scraper plus the exam-history collector,
then `build_production_candidate`. The standalone legacy analyzer remains
available, but the workflow no longer uses it to overwrite the extension.

In Actions, choose **Update Course Data**, select the branch containing these
changes, and leave **publish** unchecked. Download `course-data-candidate` and
inspect `validation.json` and the diagnostic summary. Its `extension/` directory
is the candidate Chrome build. A failed run can still upload diagnostic artifacts;
a candidate with `publishable: false` must not be treated as a release.

Only after that full candidate is reviewed should **publish** be enabled on a
subsequent run. Publication validates again, writes atomically, then commits the
data. Runs are serialized per branch. No Actions run has been launched locally.

The collector records predecessor IDs and evaluation-link counts, retains all
valid histogram links regardless of source ID, and queries explicitly approved
source course info pages when their history is absent from the current page.
New unapproved identities stay unclassified and appear in `review_needed`.
No recursive or transitive predecessor approval is inferred.

Reviewed policy:

- NPE is accepted unknown availability, not new-course status. Actual request,
  authentication, parsing, or missing-schedule failures still block publication.
- 12952 uses 12950 and treats both winter and summer as regular candidates.
- 02581 accepts 02580 Summer-2025 as a reviewed historical regular exam.
- 62237 prefers 62236, falling back to 62234 only if the preferred source has
  no eligible collected exam. Both histories remain separate.
- 62776 and MA776 both use 62775 without combining counts.
- 27827 and MA263 use their latest reviewed predecessor results; selection does
  not certify a historical regular season when the evidence is ambiguous.
- 25623's 25617 history and 22170's 27692 history are excluded from display by
  specific maintainer decisions, but remain in diagnostic evidence. There is no
  global age exclusion. Other older results receive the existing notice.
- 34556 retains its reviewed 34551 history and original histogram period labels.

Within a histogram year, winter follows summer (the supplied January 2026
evaluation is associated with the winter 2025 label). The exam selector now
uses that order consistently. This orders periods without inventing exact dates.
Current-course regular results supersede a predecessor fallback when available.

The candidate gate checks feedback collection counts against links observed on
the info page. A course with no feedback links need not have a legacy raw record.
Missing expected feedback, course/history/default losses, source count losses,
and genuine collection failures prevent publication. Legitimate removals need
review. Lazy scores retain the baseline analyzer calculation, as in the accepted
beta; changing exam selection on the page does not recompute them.

Saved test8/test9 evidence does not contain distributions for many newly reviewed
predecessors. Fresh collection is required; the implementation does not invent
their counts from link labels. The sections below document the earlier baseline
checks and should not be read as current unresolved-review totals.

## Step 1: saved-evidence replay

Run the dataset builder with the original 2.4.0 base dataset and the saved
test8/test9 reports, then compare every course and field with the accepted
extension dataset. This checks reproducibility and provides a baseline for
subsequent production integration. It does not validate live collection,
publication safeguards, or refreshed feedback calculations.

```bash
mkdir -p dist/pipeline-replay-inputs
unzip -p archive/dtu-course-analyzer-2.4.0.zip extension/db/data.json > dist/pipeline-replay-inputs/base-2.4.0.json
python -m dtu_analyzer.scripts.check_exam_pipeline \
  --base dist/pipeline-replay-inputs/base-2.4.0.json \
  --report test8/report.json --report test9/report.json \
  --expected extension/db/data.json \
  --output dist/pipeline-replay-step1
```

The reports are local, ignored evidence. Use a new output directory for each
run; existing output is never overwritten. The command writes `data.json` and
`comparison.json`, including input SHA-256 hashes, and exits with status 1 if
any course or field differs. Inputs and the installed extension are not changed.

Result on 2026-09-08: exact parsed-JSON agreement for 1,554 courses, 5,749 exam
records, and 1,253 default selections. No added/missing courses or changed fields.
This includes all feedback values, grade categories and counts, source identities,
availability statuses, defaults, and percentiles in the accepted dataset.

Next: explicitly verify representative edge cases, then implement and exercise
collection-failure safeguards before an Actions dry run with publishing disabled.
The production workflow remains unchanged.

## Step 2: edge cases and publication protection

`tests/fixtures/exam_pipeline_cases.json` retains the structured schedules,
source grade counts, availability, and count diagnostics for 12 representative
courses from test8, superseded by test9 where available. Page bodies, request
details, and authentication evidence are omitted. These fixed historical cases
are regression expectations, not assertions about future exam periods.

`tests/test_publication_guard.py` verifies winter defaults, pass/fail counts,
suppressed defaults, reviewed historical identities, shared counts, new courses,
and ambiguous or unapproved histories. It also simulates failed authentication,
unfinished runs, missing courses/schedules/histograms, lost history/defaults,
altered counts, lost feedback, and failures during atomic file replacement.
Every rejected update leaves the destination bytes unchanged.

The new `analysis.publication_guard.publish_candidate` validates before writing
and replaces the destination atomically. It requires an independent expected
course list from the caller, checks previous course/history/feedback retention,
and reconstructs the candidate from collected evidence. Suppression, genuine
schedule ambiguity, explicit no-results pages, and reviewed new courses are
accepted. Source participant discrepancies alone do not block publication;
category-retention failures do. Collection failures are blocked, even for a
reviewed new course. Legitimate removals need review rather than an automatic
percentage-loss allowance.

This safeguard is **not yet wired into Actions**. It assumes a single writer;
workflow integration must serialize updates. It does not establish whether the
upstream expected-course list or feedback collection is complete/fresh. Those
collection checks still belong in the production integration.

Offline application to combined test8/test9 evidence flags **117 courses whose
absence of results remains unconfirmed**. The candidate otherwise passes these
checks. This does not invalidate the accepted manually reviewed snapshot; it
means a fresh automatic publication needs explicit no-results evidence, further
review, or a separately designed policy to retain and mark unresolved old data.
The local details are in `dist/pipeline-replay-step2/publication-check.json`.
Do not weaken the safeguard simply to obtain a passing full run.
