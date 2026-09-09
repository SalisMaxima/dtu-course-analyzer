# test10 review — 2026-09-09

## Follow-up implemented after maintainer review

- Unexpected login/wrapper responses get one delayed retry from the original
  public URL. A second authentication response still fails. This addresses the
  observed 12601/28022 access pattern without claiming it will always recover.
- Only 22461's `22433/Summer-2023` HTTP 404 is a reviewed exclusion. Other errors
  still block publication; the failed source evidence remains in diagnostics.
- 22181's `22180/Winter-2025` is a reviewed historical regular exam, following
  the maintainer's confirmation of an autumn-to-spring schedule change.
- 25205's previously collected Summer 2022 URL is explicitly fetched again if
  omitted from the info-page list. Suppression is recognized from the response,
  not inferred from a missing link. No hidden counts are invented.

These are collection/classification changes, not a regenerated extension dataset.
After pushing, use Test Exam Classification with courses
`12601,28022,22461,25205,22181` before another full Update Course Data dry run.
The original findings below describe the supplied test10 artifact.

Input: `test10/exam-classification-report/report.json`, schema 5,
rules `schedule-hypothesis-v8-maintainer-history`. Collection ran on September 8
from 21:08 to 22:27 UTC. All 1,554 course registrations have final statuses.

The supplied artifact contains only report.json, courses.csv, and summary.md.
There is no production candidate or validation.json. The collector returns a
failure exit code for its three error records; under the committed workflow,
this skips candidate construction. The artifact alone does not provide the
Actions execution log or the newly scraped feedback dataset.

## Collection results

- 5,096 published distributions; 993 suppressed; one failed.
- Zero category-retention failures; eight source participant discrepancies.
- 99 courses without collected exam links: four confirmed new courses,
  94 reviewed NPE cases, and one failed info-page request (28022).
- The diagnostic also retains 271 different-course and 175 suffixed histogram
  records requiring identity review. These are exam records, not course counts.

## Blocking findings

1. **12601**: course-page request followed a wrapper to the authentication page.
   No schedule was collected, although histogram collection succeeded. The
   existing default would disappear. This is not an NPE case.
2. **28022**: info-page request followed a wrapper to the authentication page.
   The schedule succeeded, but all five previously stored exams and its default
   would disappear. This is not an NPE case.
3. **22461**: predecessor histogram `22433/Summer-2023` returned HTTP 404.
   Winter 2023 and Winter 2022 were parsed successfully. A listed broken link
   should be diagnosed separately from a temporary network failure; it cannot
   be silently treated as a valid distribution.
4. **25205**: Summer 2026 is newly present while Summer 2022 is absent from the
   five collected links. Winter 2022 remains present. The retention guard flags
   losing the old Summer 2022 entry. This suggests a changing list of visible
   history links, not evidence that the old exam never existed. Verify/retrieve
   the old source or retain its earlier evidence with its original provenance.

An offline exam-only gate check produced ten reasons across these four courses.
It used previously bundled feedback solely to check exam publication behavior;
it is not a substitute for full production validation. Details are in
`dist/test10-local-review/publication-check.json`. The installed dataset was not changed.

## Reviewed cases

- 01001: Winter 2025; 01020: Summer 2026, 85% passed.
- 01426: suppressed Winter 2025 stays default.
- 02581: accepted 02580 Summer 2025 is default.
- 12952: 12950 Summer 2026 is default, with both seasons classified regular.
- 62237: 62236 Winter 2025 is default; 62234 history is retained.
- 62776 and MA776: each uses 62775 Winter 2025, without combining counts.
- 27827: 29905 Winter 2025; MA263: 41263 Summer 2026.
- 34556: 34551 Winter 2025.
- 22170 and 25623: excluded predecessor distributions are not displayed.
- All 94 reviewed NPE courses remain accepted unknown availability.

**22181 needs a default-selection decision:** its current Spring schedule makes
the pipeline select suppressed 22180 Summer 2024 and classify the available
Winter 2025 result as a reexam. The maintainer accepted Winter 2025 as useful
history; that identity approval did not establish a historical regular season.
If Winter 2025 should be the default, record a specific historical selection
decision instead of silently treating the current schedule as historical fact.

Next: address the four blocking cases and the 22181 selection question before
another full candidate run. Keep publication disabled.
