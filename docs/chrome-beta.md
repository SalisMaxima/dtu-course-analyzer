# Chrome beta 2.5.0-beta.3

The accepted build is now the repository's default in `extension/`, originally
copied from `dist/chrome-beta-2.5.0-beta.3/` (including its beta version name).
Load the root `extension/` directory in Chrome to use it. The previous 2.4.0
build is preserved in `archive/dtu-course-analyzer-2.4.0.zip`.

Exam history is a bundled snapshot. **Update Course Data** now builds a complete
exam-history candidate and defaults to a dry run. Leave **publish** unchecked
until its candidate artifact has been reviewed. See
[production validation](production-pipeline-validation.md) for the current rules.

This beta bundles the full test8 evidence, refreshed by the test9 sample, plus
the existing feedback dataset. No DTU login or live scraping is needed to use it.
Only the exam histories actually collected in those reports are available;
older exams absent from those reports cannot be selected.

Maintainer-reviewed histories are directional: 02280 accepts 02285, 02426
accepts 02424, and both 23103 and 23104 accept the shared 23102 history. Shared
counts are retained separately, never added together. These decisions live in
`analysis/course_history_reviews.py`; unknown relationships still require review.
01822 and 02262 are confirmed new courses with no expected history.

## Default and selector

- Autumn and January imply winter regular exams; Spring, June and July imply
  summer regular exams. Compatible combined periods use the same rule.
- Choose the newest inferred regular exam among exact or manually approved
  source identities. Participant size and a more recent resit do not override it.
- Keep a suppressed latest regular exam as default and explain that DTU hides
  its grades. Do not substitute an older visible exam.
- Ambiguous schedules, August, duplicate latest regular groups, or unapproved
  histories produce no automatic default. The dropdown permits explicit
  inspection of collected exams, with unverified identity warnings as needed.
- Selecting an exam updates only that page's grade counts, histogram, average
  or pass percentage, period and source. Reload restores the default. Feedback
  statistics remain from their separately collected survey. Database and course
  comparison views use default exams; historical selections do not change them.
- Numeric average percentiles are recomputed across the beta's default results
  and shown only for the default exam. Past exams have no invented percentile.
- Pass percentage uses DTU's integer summary based on registered participants
  (including absences). For example 01020 Summer-2026 displays 85%, while its
  passed bar represents 79/92, approximately 85.9%. Source-total differences
  are flagged instead of inventing missing results.

These seasonal assignments remain inferences from current schedules. Approved
course identity does not establish historical teaching schedules or student cohorts.

## Build and install

```bash
python -m dtu_analyzer.scripts.build_chrome_beta --report test8/report.json --report test9/report.json
```

The output is `dist/chrome-beta-2.5.0-beta.3/` and a ZIP of the same name.
The beta manifest uses version 2.5.0.3 and the name DTU Course Analyzer Beta.
Use **Switch exam season** at the top of the analyzer. The chart heading reads
"Grades in: **Winter 2025**" for that selected period. Explanatory notes are in
the **About these results** popup; Close or Escape dismisses it.
The builder refuses to overwrite a prior output; use `--output` for another build.

In Chrome, open `chrome://extensions`, enable Developer mode, disable the
existing DTU analyzer, then choose **Load unpacked** and select the output
directory containing `manifest.json`. Alternatively unzip the archive into a
directory and select that directory. Refresh open DTU course tabs.

## Beta checks

1. 01001 defaults to Winter-2025. Switch to Summer-2026 and back: source URL,
   participants, bars and average must change together. Refresh restores winter.
2. 01020 defaults to Summer-2026 with Passed/Not passed/Absent bars, 92 registered
   participants and 85% passed. Switch to its mixed Summer-2025 results: preserve
   the numerical failure and categorical results, showing pass percentage.
3. 02280 defaults to Summer-2026 from 02285; 02426 defaults to Summer-2024 from
   02424. Both show their reviewed historical source identities.
4. 23103 and 23104 each default to Summer-2026 from 23102, with the shared-history
   note and identical source counts. Comparison must not combine the counts.
5. 01018: select a suppressed summer exam and check that all previous grade
   metrics disappear. 01426's latest regular exam is suppressed by default.
6. 01822 and 02262 explain that they are new courses. 01037 and 01666 have no
   automatic default; select a collected exam manually. 01025's suffixed history
   is still unapproved and must show an identity warning on selection.
7. Open the extension database and comparison: their results use the defaults,
   even after you switch an individual course page to another exam.

Report the course ID, selected period, expected result and observed result for
any discrepancy. To roll back, disable/remove the beta and re-enable the old extension.
