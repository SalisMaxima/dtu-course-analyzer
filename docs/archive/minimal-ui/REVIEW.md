# UI review and minimal design proposal

> Archived: the user preferred the original rough UI, including its imperfections, because this redesign felt too “AI generated / artificial.” The recommendations below are historical, not the current design direction. See [the archive decision](README.md).

**Recommendation:** retain the original red–yellow–green score colors within a simpler interface: white surfaces, restrained gray typography, subtle dividers and deep red controls. Use compact colored value badges across the database, comparison and course panel; establish hierarchy through type, spacing and alignment.

Open [the interactive design proposal](proposal.html) directly in a browser. Switch between **Course database** and **Course-page panel**. Search, sort, change course-name language and select up to four courses. The preview contains eight records copied from the bundled dataset; selection is temporary and resets on reload.

## Review scope

Reviewed the current working-tree implementation in `extension/`: the database page, comparison view, injected course panel, language controls and shared metric rendering. The toolbar icon opens the database in a tab; there is no separate popup to redesign. Existing local code changes were included in the review and left intact.

The database was rendered in headless Chrome with local extension-storage stubs and bundled data. The injected panel was rendered using its actual JavaScript inside a minimal local host-page fixture. Its surrounding DTU page typography/layout therefore needs verification on the real site before implementation is considered complete. This is a design review, not a live-site or assistive-technology audit. Historical promotional screenshots and the older `source-code/extension/` copy were not used as the current UI baseline.

| Current surface | Proposed surface |
| --- | --- |
| [Database and comparison](current-database.png) | [Database and comparison](proposed-database.png) |
| [Injected panel in a local fixture](current-course-panel.png) | [Course panel concept](proposed-course-panel.png) |

## Findings, in priority order

| Priority | Observation and evidence | Proposed change |
| --- | --- | --- |
| High | The original red–yellow–green fills make score values easy to scan (`getMetricColor` in `extension/js/course-utils.js:36`). This is a useful part of the existing design and should be retained. | Keep the same continuous hue mapping in compact filled badges, with slightly softer colors and dark numeric text. Apply it consistently across all three surfaces. Keep participant counts and missing values neutral; retain explicit confidence text. |
| High | The database measured **2,026 px wide in a 1,440 px viewport** with its initial course page. All cells and headers use `white-space: nowrap` (`extension/db.html:63`), putting later metrics and Compare beyond the viewport. | Allow names and header labels to wrap; cap the name column, right-align numbers, shorten repetitive headers and contain overflow inside the table. Keep all existing metrics visible or horizontally reachable. |
| High | The injected panel wraps every row label in bold (`extension/contentscript.js:320`). Participant counts, histogram, metric labels and the decorative “—DTU Course Analyzer—” heading compete at similar emphasis. | Use a small product label, a clear heading, regular-weight row labels and medium-weight values. Give average grade and pass rate slightly stronger prominence. |
| Medium | The database opens immediately with language controls and the table (`extension/db.html:201`); search is pushed to the far right. There is no visible page title. | Add a modest title and one-line description; place labeled search above the results. Make language controls a quiet segmented control labeled “Course names,” since the current feature changes names rather than the whole interface. |
| Medium | Comparison uses a complete cell grid, a thick red top border, bold row headings and colored badges (`extension/db.html:169`, `extension/js/table.js:168`). Links appear in browser-default blue while database links are red. | Use horizontal rules, consistent link styling, regular row labels and restrained separation between metric groups. Retain side-by-side values. |
| Medium | Buttons vary across surfaces: styled red database controls, filled red Remove buttons and largely browser-default panel buttons (`extension/contentscript.js:236`). | Share neutral secondary buttons and quiet removal actions, one filled primary style, consistent heights and explicit hover, pressed, disabled and focus states. |
| Medium | Units and names vary: “Course Rating” and “Workload” omit percentile context in the database; numbers lack percent signs. “Total Students” differs from the more precise “Grade participants.” | Use consistent labels and formatting across surfaces: “Rating percentile,” “Workload percentile,” “Grade participants,” “Feedback responses.” Explain workload direction in a short note. Preserve calculations. |
| Medium | Sorting is attached to pointer clicks on header cells (`extension/js/table.js:302`); language selection is expressed by CSS classes alone (`extension/js/language-toggle.js:8`). | During implementation, use buttons inside sortable headers, `aria-sort`, `aria-pressed` for language controls, and a visible search label. Include a consistent focus ring in the styling pass. |

## Style specification

| Element | Proposed treatment |
| --- | --- |
| Canvas / surface | `#F7F7F8` extension-page canvas; `#FFFFFF` table and panel surfaces. The injected panel keeps its own white surface. |
| Text | `#202124` primary; `#62666D` secondary. Muted text is for supporting context, not core metric values. |
| Dividers / controls | `#E3E5E8` decorative rules; `#858990` input and outlined-button borders. |
| Accent | Retain `#990000`; pale `#FBF0F0` selected treatment paired with text or a pressed state. |
| Focus | `2px solid #245AC2`, offset `3px`; visible on all interactive controls. |
| Type | System sans-serif; 14 px body with 1.5 line-height, 12 px supporting text, 18 px section headings, 26 px page title; 400 / 500 / 600 weights. Panel inherits the same scoped scale. |
| Metrics | Compact filled badges with dark text and tabular numerals; right-aligned database values. Preserve the original hue calculation: `120 × clamp(value / maximum, 0, 1)`, with maximum 12 for average grade and 100 for percentages. Use `hsl(hue, 85%, 78%)` for softer but clearly visible red, yellow and green fills. Missing data (`—`, accessible label “No data”) and participant counts remain uncolored; zero gets the lowest score color. |
| Spacing | 4 / 8 / 12 / 16 / 24 / 32 px scale. 20 px panel inset; 32 px desktop page inset; 16 px on narrow screens. |
| Shape | 6 px control radius; 8 px surface radius; 1 px borders; no decorative shadows or gradients. |
| Controls | 36–40 px typical height; compact 32 px table actions. Full text labels for Add, Remove and Compare. |
| Histogram | Retain the original deep red bars, grade labels and counts. True zero-height bars for zero counts. Preserve accessible distribution text. |

**Course-page panel:** product label → “Course insights” → average grade / passed → four percentile rows → histogram → participant and confidence context → comparison actions → explanatory link. This keeps all existing information while making the reading order clearer. The prominent values are still historical results, not predictions.

**Database:** modest page heading → search and language controls → comparison → full metric table → pagination. Use wrapping instead of reducing font size to fit. At narrower widths, horizontal scrolling belongs to the table region; the page heading and controls remain within the viewport. Production pagination stays in place; the eight-record preview does not simulate pagination.

**Comparison:** course numbers and wrapping names above aligned, colored score badges. A small Lower / Middle / Higher legend above the comparison explains the continuous color scale. Horizontal separators divide outcomes, percentile scores and sample counts. Confidence remains explicit text and describes feedback sample size only; grade counts are never used to imply a feedback response rate.

## Scope and implementation order

1. **Style pass:** introduce shared tokens and component styles; preserve the original score hue mapping with the proposed badge fills, unify links/buttons, adjust typography, spacing, borders and numeric alignment. This provides most of the visual improvement.
2. **Small markup pass:** add the page title and search label, wrap table overflow, allow header/name wrapping, add proper sort controls and state attributes, and group the course-panel metrics. These changes support the proposed appearance and keyboard access.
3. **Optional interaction refinement:** allow comparison to collapse and expand, as demonstrated in the preview. Selection remains visible as a count. Keep existing sorting, bilingual search, pagination and persisted four-course comparison behavior in production.

Implementation targets: `extension/db.html`, `extension/contentscript.js`, `extension/js/table.js`, `extension/js/language-toggle.js` and a new shared stylesheet. Scope every selector under an extension-owned wrapper (for example `.dtu-analyzer`) to avoid restyling DTU content. Load the shared stylesheet through both `db.html` and the content-script manifest entry. Keep production scripts external for extension CSP compliance. The standalone HTML preview uses inline scripts for portability and is not a replacement extension page. The active analyzer treats `db.html` as static; the legacy Firefox submission copy should only be synchronized through its existing release workflow.

## States and acceptance criteria

- Check the full dataset at 1,440 px and 1,024 px; table overflow should stay local to its scroll container. Check the injected panel at approximately 320–420 px, long Danish/English names, 200% zoom and four comparison columns.
- Keep search, sorting, language, pagination, comparison persistence and cross-tab synchronization working. Preserve focus after table updates, including Add → Remove and removal of a comparison column.
- Provide quiet, readable loading, no-results and no-data states. Use explicit text for load/storage errors and the four-course limit; distinguish error messages from the red used for low score values through explicit text and placement. The mockup demonstrates no results, empty selection and the selection limit; loading and storage failures remain implementation requirements.
- Verify readable text contrast and distinct control/focus boundaries; keep numeric values visible in every colored score badge and never make color the only selection, confidence or error cue. Verify keyboard sorting, language state, scroll regions and live status announcements with assistive technology.
- Verify style isolation and placement on a real DTU course page in supported browsers before shipping.

## Preview validation

The standalone mockup was checked in headless Chrome for search, empty results, Danish/English names, numeric sorting, clearing comparison, the four-course selection limit and panel navigation. Desktop and 390 px layouts were checked for document overflow; wide tables retain their own scroll regions. No JavaScript errors occurred during these checks. [Narrow layout capture](proposed-mobile.png).

Only proposal documents, the standalone mockup and review images were added. Production extension files were not modified.
