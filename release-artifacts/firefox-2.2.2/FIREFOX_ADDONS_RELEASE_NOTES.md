# Firefox Add-ons Release Notes

Analyzes courses in the DTU course catalogue and shows you the stats that matter.

Install the extension and visit any course page, for example `http://kurser.dtu.dk/course/01005`. A new info box will appear showing:

- Average grade and pass percentage
- Total students and feedback response count
- Workload and Lazyscore based on student evaluations
- Color-coded stats: green is good

**New in Version 2.2.2:**

- Updated course data for the latest bundled dataset.
- Added participant statistics so students can see how many exam results and evaluation responses each score is based on.
- Improved bilingual course-name support for Danish and English course search.
- Updated Firefox Manifest V3 package with the current bundled course database.

This is a 100% private, open-source project maintained by DTU students: https://github.com/SMKIDRaadet/dtu-course-analyzer

## Reviewer Notes

- Test URL: `http://kurser.dtu.dk/course/01005`
- No account is needed for normal extension behavior.
- The extension uses a static bundled dataset and does not send analytics.
- Source-code build instructions are included in `build.md` inside the source-code package.
