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

// 2. Extract course ID from URL
function getCourseId() {
  const courseMatch = window.location.href.match(
    /^http.:\/\/kurser.dtu.dk\/course\/(?:[0-9-]*\/)?([0-9]{5})/
  );
  return courseMatch ? courseMatch[1] : null;
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

  if (data) {
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
      addGradeHistogram(tbody, gradeDistribution);
      hasData = true;
    }

    outputArr.forEach(([label, key, unit, maxVal]) => {
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

function addGradeHistogram(tbody, distribution) {
  const tr = document.createElement("tr");
  const td = document.createElement("td");
  td.colSpan = 2;
  td.style.paddingTop = "8px";

  const title = document.createElement("b");
  title.textContent = "Grades awarded";
  td.appendChild(title);

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
      const current = await DTUAnalyzer.readSelection();
      const result = DTUAnalyzer.toggleSelection(current, courseId);
      if (result.invalid) {
        message.textContent = `${courseId} cannot be added to a comparison.`;
        return;
      }
      if (result.limitReached) {
        message.textContent = `Remove a course before adding another (maximum ${DTUAnalyzer.MAX_COMPARISONS}).`;
        return;
      }
      const saved = await DTUAnalyzer.writeSelection(result.selection);
      message.textContent = "";
      await refresh(saved);
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
  tr.appendChild(tdLeft);

  // Right Column (Value)
  const tdRight = document.createElement("td");
  tdRight.style.paddingLeft = "15px";
  const span = document.createElement("span");
  if (value instanceof Node) {
    span.appendChild(value);
    if (unit) span.appendChild(document.createTextNode(unit));
  } else {
    span.textContent = value + unit;
  }

  if (colored && maxVal > 0) {
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
