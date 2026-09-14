# Chrome Web Store Release Notes

## Draft 2.6.0 listing addition — publish only after configured staging validation

Receive reviewed course-data updates without waiting for a new extension release.
Downloads are optional and off by default. Enable them in the extension database,
choose automatic or manual checks, or keep using bundled data offline. Releases
are signed and validated before activation; dataset age and refresh status are shown.

The hosting provider receives your IP address, request time and browser-managed
connection headers to serve and secure downloads.
Course views, searches, exam choices, comparisons and DTU credentials are never sent.
Private/incognito windows are not supported.
See the [privacy policy](PrivacyPolicy.md) and [reviewer instructions](course-data-client.md).

Before submission, complete the [store disclosure checklist](course-data-client.md#store-submission-disclosures).

## Earlier listing text

Analyzes courses in the DTU course catalogue and shows you the stats that matter.

Simply install the extension and visit any course page, for example `http://kurser.dtu.dk/course/01005`. A new info box will appear showing:

- Average grade and pass percentage
- Total students and feedback response count
- Workload and Lazyscore based on student evaluations
- Color-coded stats: green is good

**New in Version 2.4.0:**
- Grade distribution histograms on DTU course pages.
- Feedback sample-size confidence labels.
- Persistent side-by-side comparison for up to four courses.

**New in Version 2.2.2:**

- Updated course data for the latest dataset.
- Added participant statistics so students can see how many exam results and evaluation responses each score is based on.
- Improved bilingual course-name support for Danish and English course search.
- Manifest V3 extension package with the updated bundled course database.

This is an open-source project maintained by DTU students: https://github.com/SMKIDRaadet/dtu-course-analyzer
