# Archived minimal UI branch

Archived on 2026-09-05. The user preferred the original rough style, including its imperfections, because the redesign felt too “AI generated / artificial.” The original UI remains the preferred version. This branch preserves the experiment for reference, not as an active design direction.

The `archive/minimal-ui` branch preserves the revised course database, course comparison and injected course insights panel. It retains red–yellow–green score colors with softer fills, adds consistent typography and controls, and contains wide tables within horizontal scroll regions.

## Try either version

Two independent checkouts are available from the original project directory:

| Version | Branch | Folder to load in Chrome/Edge |
| --- | --- | --- |
| Original | `feature/course-insights-comparison-chrome` | `extension/` |
| Archived revised UI | `archive/minimal-ui` | `build/ui-rework/extension/` |

Open `chrome://extensions` (or `edge://extensions`), enable Developer mode, choose **Load unpacked**, and select the desired folder. Enable one copy at a time, then refresh any open DTU course pages. Click the extension icon to open its course database. Each unpacked copy has its own saved comparison and language preferences.

The new branch is checked out in `build/ui-rework`; the original checkout and its uncommitted changes are preserved. No branch switching is required to test both versions. The worktree is inside the existing ignored `build/` directory. Keep that directory while using this checkout; the committed branch also retains the implementation in Git.

The first commit on the UI branch captures the existing uncommitted extension fixes and their helper tests as the implementation baseline. The following commit contains the UI rework. Unrelated local changes were not copied into this branch.

## What changed

- Shared, locally bundled CSS for the database and course panel, scoped to extension-owned markup.
- Labeled search, quieter language controls, keyboard-operable sorting and consistent metric units.
- Colored scores across all three surfaces; missing values and participant counts remain neutral.
- Collapsible comparison, preserved keyboard focus after selection changes, and retained four-course persistence and synchronization.
- Course-panel metric hierarchy, grade histogram, sample-size confidence context and comparison actions.
- Visible loading, no-results and data/storage failure states.

No data pipeline, metric calculations or extension permissions changed. The manifest adds the shared stylesheet to the existing content-script entry. All scripts remain external for extension CSP compliance.

## Validation

Run helper checks from this worktree:

```bash
node --test tests/course_utils.test.js
```

Run the repeatable browser smoke checks with an environment that has Playwright installed:

```bash
python tests/extension_ui_smoke.py --chrome /usr/bin/google-chrome
```

The browser smoke script uses the actual extension HTML, scripts and bundled dataset with a local host fixture and storage adapter. It checks full-dataset pagination, keyboard sorting, bilingual search/display, selection persistence and cross-tab updates, comparison limits, focus, error states, course-panel controls, style isolation and narrow layouts. It writes screenshots to a temporary directory (or `--output PATH`).

These checks passed, along with all 11 shared-helper tests, JavaScript syntax checks and manifest asset checks. Automated loading of the unpacked extension was unavailable in the installed Chrome build. The live DTU request returned an empty page with none of the course-page anchors, so the real-site integration still needs a manual check after loading the extension. The fixture checks are not a substitute for that final check.
