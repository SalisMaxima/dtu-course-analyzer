// contentscript.js - Version 2.4.0

// 1. Configuration (Must be defined BEFORE running logic)
const outputArr = [
  ["Average grade", "avg", "", 12],
  ["Average grade percentile", "avgp", "%", 100],
  ["Percent passed", "passpercent", "%", 100],
  ["Course rating percentile", "qualityscore", "%", 100],
  ["Workscore percentile", "workload", "%", 100],
  ["Lazyscore percentile", "lazyscore", "%", 100],
];

const METRIC_HELP = {
  "Average grade": "DTU's published average numerical grade for the selected exam, on the Danish seven-point scale. Higher is better. Pass/fail and mixed distributions show percentage passed instead.",
  "Average grade percentile": "Courses with numerical default-exam averages are ranked from lowest to highest. Equal averages share a rank. Higher is better. This percentile is shown only for the default exam, not for other historical selections.",
  "Percentage passed": "The percentage of registered participants who passed the selected exam, including absent participants in the denominator. This uses DTU's rounded summary percentage, so it may differ slightly from the percentage calculated from the histogram counts. Higher is better.",
  "Course rating percentile": "Courses are ranked using responses to the course-review question: ‘Overall I think the course is good.’ Higher means more positive ratings.",
  "Workscore percentile": "Courses are ranked using responses to: ‘5 points are allocated to 9 h/week (45 h/week in the 3-week period). I think my workload in the course is [Much less … Much more].’ Higher means a lower reported workload relative to that expectation.",
  "Lazyscore percentile": "The pass-rate percentile and lower-workload percentile are combined with equal weight, then courses are ranked again. The displayed value is that final percentile, not simply the average of the two inputs. Higher indicates a combination of higher pass rates and lower reported workload — the beer-friendly score. 🍺 This score comes from the bundled course-score dataset and does not change when you switch exams.",
};
METRIC_HELP["Percent passed"] = METRIC_HELP["Percentage passed"];

function openMetricHelp(label, explanation) {
  const dialog = document.createElement("dialog");
  dialog.setAttribute("aria-label", label);
  dialog.style.cssText = "max-width:520px;width:calc(100vw - 64px);padding:24px;border:1px solid #999;border-radius:8px;background:white;color:#222;";
  const heading = document.createElement("h3");
  heading.textContent = label;
  const text = document.createElement("p");
  text.textContent = explanation;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => dialog.remove());
  dialog.appendChild(heading);
  dialog.appendChild(text);
  dialog.appendChild(close);
  document.body.appendChild(dialog);
  dialog.showModal();
}

// 2. Extract course ID from URL
function getCourseId() {
  return DTUAnalyzer.getCourseIdFromPath(window.location.pathname);
}

// 3. Load packaged course data (async, does not block the page)
// Returns { ok: true, db } or { ok: false, reason } so a broken install stays
// distinguishable from a course we simply have no data for
async function loadData() {
  try {
    const response = await fetch(chrome.runtime.getURL("db/data.json"));
    if (!response.ok) {
      console.error("DTU Analyzer: Failed to load db/data.json (HTTP " + response.status + ")");
      return { ok: false, reason: "HTTP " + response.status };
    }
    return { ok: true, db: await response.json() };
  } catch (e) {
    console.error("DTU Analyzer: Failed to load course data:", e);
    return { ok: false, reason: e.message };
  }
}

// 4. UI Generation Functions

// Find where to insert the stats table, with fallbacks for DTU markup changes
function findInsertionPoint() {
  const infoBoxTable = document.querySelector(".box.information > table");
  if (infoBoxTable) return { element: infoBoxTable, position: "afterend" };

  const infoBox = document.querySelector(".box.information");
  if (infoBox) return { element: infoBox, position: "afterbegin" };

  const main = document.querySelector("#pagecontents, main, #content");
  if (main) return { element: main, position: "afterbegin" };

  return null;
}

function presentData(data, courseId, loadError) {
  const insertion = findInsertionPoint();

  // Guard clause if the page structure changes and no anchor is found
  if (!insertion) {
    console.warn("DTU Analyzer: Could not find an insertion point - page structure may have changed");
    return;
  }

  // Create the container table
  const table = document.createElement("table");
  table.style.width = "100%";
  table.style.minWidth = "280px";
  table.style.tableLayout = "fixed";
  table.style.borderCollapse = "collapse";
  const tbody = document.createElement("tbody");
  tbody.id = "DTU-Course-Analyzer";
  table.appendChild(tbody);

  insertion.element.insertAdjacentElement(insertion.position, table);

  // Add Header Row
  const headerText = document.createElement("span");
  headerText.textContent = "—DTU Course Analyzer—";
  headerText.style.whiteSpace = "nowrap";
  addRow(tbody, headerText);

  // The shared helpers ship as a separate content script - say so if it did not load
  if (typeof DTUAnalyzer === "undefined") {
    console.error("DTU Analyzer: course-utils.js did not load");
    addRow(tbody, "Extension scripts failed to load - try reinstalling the extension");
    return;
  }

  if (data && Array.isArray(data.exam_history)) {
    addExamHistory(tbody, data);
    if (typeof data.review_participants !== "undefined") addFeedbackRow(tbody, data.review_participants);
    outputArr.slice(3).forEach(([label, key, unit, maxVal]) => {
      if (data[key] !== undefined && data[key] !== null && Number.isFinite(Number(data[key]))) {
        addRow(tbody, label, Math.round(data[key] * 10) / 10, unit, true, maxVal);
      }
    });
  } else if (data) {
    let hasData = false;

    // Add participant counts and an honest sample-size confidence cue.
    const gradeParticipants = data["grade_participants"];
    const reviewParticipants = data["review_participants"];

    if (typeof gradeParticipants !== "undefined") {
      addRow(tbody, "Grade participants", gradeParticipants);
      hasData = true;
    }

    if (typeof reviewParticipants !== "undefined") {
      addFeedbackRow(tbody, reviewParticipants);
      hasData = true;
    }

    const gradeDistribution = DTUAnalyzer.normalizeGrades(data.grades);
    if (gradeDistribution.some((item) => item.count > 0)) {
      addGradeHistogram(tbody, gradeDistribution, data.grade_period);
      hasData = true;
    }

    const metrics = DTUAnalyzer.usesPassPercentage(data)
      ? [["Percentage passed", "passpercent", "%", 100], ...outputArr.slice(3)]
      : outputArr;
    metrics.forEach(([label, key, unit, maxVal]) => {
      const val = data[key];

      if (typeof val !== "undefined" && val !== null && !isNaN(val)) {
        hasData = true;
        const rounded = Math.round(val * 10) / 10;

        // Create label span
        const labelSpan = document.createElement("span");
        labelSpan.textContent = label;

        addRow(tbody, labelSpan, rounded, unit, true, maxVal);
      }
    });

    if (!hasData) {
      addRow(tbody, "Data available but no metrics found");
    }
  } else if (loadError) {
    addRow(tbody, "Course data could not be loaded (" + loadError + ") - try reinstalling");
  } else {
    addRow(tbody, "No data found for this course");
  }

  // Only offer comparison for courses the packaged dataset can actually render
  if (data) addComparisonControls(tbody, courseId);

  // Add Footer Link
  const link = document.createElement("a");
  link.href = "https://github.com/SMKIDRaadet/dtu-course-analyzer";
  link.target = "_blank";

  const linkLabel = document.createElement("label");
  linkLabel.textContent = "What is this?";
  linkLabel.style.cursor = "pointer";

  link.appendChild(linkLabel);
  addRow(tbody, link);
}

function addExamHistory(tbody, data) {
  const note = document.createElement("span");
  note.textContent = data.exam_default_note;
  if (!data.exam_history.length) {
    addRow(tbody, "Exam history", note);
    return;
  }

  const select = document.createElement("select");
  select.setAttribute("aria-label", "Displayed exam");
  select.style.maxWidth = "100%";
  select.style.width = "100%";
  select.style.minHeight = "40px";
  select.style.padding = "8px";
  select.style.border = "2px solid #990000";
  select.style.borderRadius = "5px";
  select.style.backgroundColor = "#fff";
  select.style.color = "#222";
  select.style.fontSize = "1em";
  select.style.cursor = "pointer";
  select.style.transform = "translateX(-6px)";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose an exam";
  select.appendChild(placeholder);
  data.exam_history.forEach(exam => {
    const option = document.createElement("option");
    option.value = exam.id;
    const role = exam.classification === "ordinary_candidate" ? "Regular exam (inferred)"
      : exam.classification === "resit_candidate" ? "Reexam (inferred)" : "Unclassified";
    option.textContent = `${formatExamPeriod(exam.grade_period)} · ${role} · ${exam.histogram_course}`
      + (exam.distribution_status === "published" ? "" : ` · ${exam.distribution_status}`)
      + (exam.id === data.default_exam_id ? " · default" : "");
    select.appendChild(option);
  });
  select.value = data.default_exam_id || "";
  addRow(tbody, "Switch exam season", select);
  if (data.history_collected_at) addRow(tbody, "Exam history collected", data.history_collected_at.slice(0, 10));
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 2;
  td.style.padding = "0";
  const panel = document.createElement("table");
  panel.style.width = "100%";
  panel.style.tableLayout = "fixed";
  panel.style.borderCollapse = "collapse";
  panel.style.margin = "0";
  const body = document.createElement("tbody");
  body.setAttribute("aria-live", "polite");
  panel.appendChild(body);
  td.appendChild(panel);
  tr.appendChild(td);
  tbody.appendChild(tr);
  const render = () => {
    while (body.firstChild) body.removeChild(body.firstChild);
    const exam = data.exam_history.find(item => item.id === select.value);
    if (!exam) { addRow(body, "Select an exam to view its results."); return; }
    addRow(body, "Exam period", formatExamPeriod(exam.grade_period));
    const link = document.createElement("a");
    link.href = exam.grade_source;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = exam.title || `DTU results for ${exam.histogram_course}`;
    addRow(body, "Source", link);
    if (exam.identity_note) addRow(body, "Reviewed history", exam.identity_note);
    if (["different_course_requires_review", "variant_requires_review"].includes(exam.identity_status)) {
      addRow(body, "Historical course identity is unverified. These results are not assigned to the current course.");
    }
    if (exam.distribution_status === "suppressed") {
      addRow(body, "DTU hides this distribution because three or fewer attended. No grade statistics are displayed.");
      return;
    }
    if (exam.distribution_status !== "published") {
      addRow(body, "Results could not be collected for this exam. Open the source to inspect it.");
      return;
    }
    if (exam.grade_participants !== undefined) addRow(body, "Grade participants (registered)", exam.grade_participants);
    if (exam.participant_difference) {
      addRow(body, "Source totals differ", `${exam.participant_difference} registered participants are not accounted for by the displayed result total.`);
    }
    const distribution = DTUAnalyzer.normalizeGrades(exam.grades);
    if (distribution.some(item => item.count > 0)) addGradeHistogram(body, distribution, exam.grade_period);
    const primary = DTUAnalyzer.getPrimaryResult(exam);
    if (primary.value !== undefined && primary.value !== null) {
      addRow(body, primary.label, primary.value, DTUAnalyzer.usesPassPercentage(exam) ? "%" : "", true, primary.maxValue);
    }
    if (!DTUAnalyzer.usesPassPercentage(exam) && exam.passpercent !== undefined) {
      addRow(body, "Percentage passed", exam.passpercent, "%", true, 100);
    }
    if (exam.id === data.default_exam_id && data.avgp !== undefined) {
      addRow(body, "Average grade percentile", data.avgp, "%", true, 100);
    }
  };
  select.addEventListener("change", render);
  render();
  addExamDisclaimer(tbody, data);
}

function addExamDisclaimer(tbody, data) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 2;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "About these results";
  button.style.cssText = "background:none;border:0;padding:6px 0;color:#990000;text-decoration:underline;cursor:pointer;font:inherit;";
  button.setAttribute("aria-haspopup", "dialog");
  const dialog = document.createElement("dialog");
  dialog.setAttribute("aria-labelledby", "dtu-exam-disclaimer-title");
  dialog.style.cssText = "max-width:520px;width:calc(100vw - 64px);padding:24px;border:1px solid #999;border-radius:8px;background:white;color:#222;";
  const title = document.createElement("h3");
  title.id = "dtu-exam-disclaimer-title";
  title.textContent = "About these results";
  dialog.appendChild(title);
  [data.exam_default_note,
    "Pass percentage uses registered participants, including absences, and DTU's rounded summary value.",
    "Changing the exam affects this page only. Reload restores the default; comparisons use default exams.",
    "Feedback metrics use their own latest collected survey."].filter(Boolean).forEach(text => {
      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      dialog.appendChild(paragraph);
    });
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => dialog.close());
  dialog.appendChild(close);
  button.addEventListener("click", () => dialog.showModal());
  cell.appendChild(button);
  cell.appendChild(dialog);
  row.appendChild(cell);
  tbody.appendChild(row);
}

function addFeedbackRow(tbody, count) {
  const confidence = DTUAnalyzer.getConfidence(count);
  const value = document.createElement("span");
  value.textContent = String(count);

  if (confidence) {
    const badge = document.createElement("span");
    badge.textContent = confidence.label;
    badge.title = "Confidence is based on feedback sample size, not response rate.";
    badge.style.marginLeft = "8px";
    badge.style.padding = "2px 6px";
    badge.style.borderRadius = "10px";
    badge.style.fontSize = "0.85em";
    badge.style.fontWeight = "bold";
    badge.style.color = confidence.key === "low" ? "#842029" : "#4d3d00";
    badge.style.backgroundColor = confidence.key === "low" ? "#f8d7da" : "#fff3cd";
    if (confidence.key === "higher") {
      badge.style.color = "#0f5132";
      badge.style.backgroundColor = "#d1e7dd";
    }
    value.appendChild(badge);
  }

  addRow(tbody, "Feedback responses", value);
}

function formatExamPeriod(period) {
  return String(period || "").replace(/^([A-Za-z]+)-(\d{4})$/, "$1 $2");
}

function resultsAreOlderThanOneYear(period, now = new Date()) {
  const match = /^(?:Winter|Summer)[ -](\d{4})$/.exec(String(period || ""));
  // Seasons do not establish an exact exam date. Use the end of the labeled
  // year as the upper bound, avoiding guesses about DTU's winter boundaries.
  return Boolean(match) && now.getUTCFullYear() > Number(match[1]) + 1;
}

function addOlderResultsNotice(container, period) {
  if (!resultsAreOlderThanOneYear(period)) return;
  const explanation = `The selected results (${formatExamPeriod(period)}) are over a year old and may not reflect the course's current format. Only the exam season and year are available, so this notice uses a conservative year-based check. This does not mean the course has not run since.`;
  const notice = document.createElement("button");
  notice.type = "button";
  notice.textContent = "ⓘ Older results";
  notice.title = explanation;
  notice.setAttribute("aria-label", "About older results");
  notice.setAttribute("aria-haspopup", "dialog");
  notice.style.cssText = "margin-left:8px;padding:0;border:0;background:transparent;color:#666;font:inherit;font-size:0.85em;cursor:pointer;";
  notice.addEventListener("click", () => openMetricHelp("Older results", explanation));
  container.appendChild(notice);
}

function addGradeHistogram(tbody, distribution, period) {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 2;
  td.style.paddingTop = "8px";
  td.style.paddingBottom = "16px";

  const title = document.createElement("span");
  title.textContent = period ? "Grades in: " : "Grades";
  td.appendChild(title);
  if (period) {
    const note = document.createElement("b");
    note.textContent = formatExamPeriod(period);
    td.appendChild(note);
    addOlderResultsNotice(td, period);
  }

  const chart = document.createElement("div");
  chart.setAttribute("role", "img");
  chart.setAttribute(
    "aria-label",
    distribution.map((item) => `${item.grade}: ${item.count}`).join(", ")
  );
  chart.style.display = "flex";
  chart.style.alignItems = "end";
  chart.style.gap = "5px";
  chart.style.height = "92px";
  chart.style.marginTop = "6px";
  chart.style.marginRight = "8px";

  const maximum = Math.max(...distribution.map((item) => item.percentage), 1);
  distribution.forEach((item) => {
    const column = document.createElement("div");
    column.style.display = "flex";
    column.style.flex = "1";
    column.style.height = "100%";
    column.style.minWidth = "26px";
    column.style.flexDirection = "column";
    column.style.justifyContent = "end";
    column.style.alignItems = "center";
    column.title = `${item.grade}: ${item.count} (${item.percentage.toFixed(1)}%)`;

    const count = document.createElement("span");
    count.textContent = String(item.count);
    count.style.fontSize = "0.75em";

    const bar = document.createElement("span");
    bar.style.display = "block";
    bar.style.width = "100%";
    bar.style.height = `${Math.max(2, (item.percentage / maximum) * 58)}px`;
    bar.style.backgroundColor = "#990000";
    bar.style.borderRadius = "3px 3px 0 0";

    const grade = document.createElement("span");
    grade.textContent = item.grade;
    grade.style.fontSize = "0.8em";
    grade.style.marginTop = "2px";

    column.appendChild(count);
    column.appendChild(bar);
    column.appendChild(grade);
    chart.appendChild(column);
  });

  td.appendChild(chart);
  tr.appendChild(td);
  tbody.appendChild(tr);
}

function addComparisonControls(tbody, courseId) {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 2;
  td.style.paddingTop = "8px";

  const button = document.createElement("button");
  button.type = "button";
  button.style.padding = "5px 9px";
  button.style.cursor = "pointer";

  const viewButton = document.createElement("button");
  viewButton.type = "button";
  viewButton.textContent = "View comparison";
  viewButton.style.marginLeft = "8px";
  viewButton.style.padding = "5px 9px";
  viewButton.style.cursor = "pointer";

  const message = document.createElement("span");
  message.setAttribute("role", "status");
  message.style.marginLeft = "8px";
  message.style.fontSize = "0.85em";

  let renderedSelection = "";

  async function refresh(selection) {
    try {
      const current = selection || await DTUAnalyzer.readSelection();
      const selected = current.includes(courseId);
      button.textContent = selected ? "Remove from comparison" : "Add to comparison";
      button.setAttribute("aria-pressed", String(selected));
      viewButton.textContent = `View comparison (${current.length}/${DTUAnalyzer.MAX_COMPARISONS})`;
      renderedSelection = current.join(",");
    } catch (e) {
      console.error("DTU Analyzer: Could not read the saved comparison:", e);
      message.textContent = "Comparison is unavailable - try reloading the page.";
    }
  }

  button.addEventListener("click", async () => {
    try {
      const result = await DTUAnalyzer.updateSelection("toggle", courseId);
      if (result.invalid) {
        message.textContent = `${courseId} cannot be added to a comparison.`;
        return;
      }
      if (result.limitReached) {
        message.textContent = `Remove a course before adding another (maximum ${DTUAnalyzer.MAX_COMPARISONS}).`;
        return;
      }
      message.textContent = "";
      await refresh(result.selection);
    } catch (e) {
      console.error("DTU Analyzer: Could not update the comparison:", e);
      message.textContent = "Could not save your comparison - try reloading the page.";
    }
  });

  viewButton.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "openComparison" }, () => {
      if (!chrome.runtime.lastError) return;
      console.error("DTU Analyzer: Could not open the comparison:", chrome.runtime.lastError.message);
      message.textContent = "Could not open the comparison - try reloading the page.";
    });
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes[DTUAnalyzer.COMPARISON_KEY]) return;
    const selection = DTUAnalyzer.normalizeSelection(changes[DTUAnalyzer.COMPARISON_KEY].newValue);
    // Our own writes have already refreshed the controls - skip the echo
    if (selection.join(",") === renderedSelection) return;
    refresh(selection);
  });

  td.appendChild(button);
  td.appendChild(viewButton);
  td.appendChild(message);
  tr.appendChild(td);
  tbody.appendChild(tr);
  refresh();
}

function addRow(tbody, contentLeft, value = "", unit = "", colored = false, maxVal = 1) {
  const tr = document.createElement("tr");

  // Left Column (Label)
  const tdLeft = document.createElement("td");
  tdLeft.style.width = "33%";
  tdLeft.style.paddingLeft = "0";
  const b = document.createElement("b");
  if (typeof contentLeft === "string") {
    b.textContent = contentLeft;
  } else if (contentLeft instanceof Node) {
    b.appendChild(contentLeft);
  } else {
    console.warn("DTU Analyzer: Invalid content type for row:", typeof contentLeft);
    return;
  }
  tdLeft.appendChild(b);
  const label = typeof contentLeft === "string" ? contentLeft : contentLeft.textContent;
  const explanation = METRIC_HELP[label];
  if (explanation) {
    b.title = explanation;
    const info = document.createElement("button");
    info.type = "button";
    info.textContent = "ⓘ";
    info.title = explanation;
    info.setAttribute("aria-label", `About ${label}`);
    info.setAttribute("aria-haspopup", "dialog");
    info.style.cssText = "background:none;border:0;padding:0 4px;margin-left:4px;color:#990000;cursor:help;font:inherit;";
    info.addEventListener("click", () => openMetricHelp(label, explanation));
    tdLeft.appendChild(info);
  }
  tr.appendChild(tdLeft);

  // Right Column (Value)
  const tdRight = document.createElement("td");
  tdRight.style.paddingLeft = "15px";
  tdRight.style.overflowWrap = "anywhere";
  const span = document.createElement("span");
  if (value instanceof Node) {
    span.appendChild(value);
    if (unit) span.appendChild(document.createTextNode(unit));
  } else {
    span.textContent = value + unit;
  }

  if (colored && maxVal > 0) {
    for (const cell of [tdLeft, tdRight]) {
      cell.style.paddingTop = "6px";
      cell.style.paddingBottom = "6px";
    }
    span.style.backgroundColor = DTUAnalyzer.getMetricColor(value, maxVal);
    span.style.padding = "2px 6px";
    span.style.borderRadius = "4px";
  }

  tdRight.appendChild(span);
  tr.appendChild(tdRight);

  tbody.appendChild(tr);
}

// 5. Main Execution Logic
async function main() {
  try {
    const courseId = getCourseId();

    if (!courseId || courseId.length !== 5) {
      // Not on a course page, silently exit
      return;
    }

    const result = await loadData();
    if (!result.ok) {
      presentData(null, courseId, result.reason);
      return;
    }

    const courseData = result.db[courseId];
    if (courseData) {
      presentData(courseData, courseId);
    } else {
      console.info("DTU Analyzer: No data available for course " + courseId);
      presentData(null, courseId);
    }
  } catch (e) {
    // Never let an unexpected error escape onto DTU's page
    console.error("DTU Analyzer: Unexpected error:", e);
  }
}

// Run when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
