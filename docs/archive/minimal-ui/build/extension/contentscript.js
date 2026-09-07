// Course insights panel. All markup lives inside the extension's styled wrapper.
const outputArr = [
  ["Average grade", "avg", "", 12],
  ["Passed", "passpercent", "%", 100],
  ["Grade percentile", "avgp", "%", 100],
  ["Rating percentile", "qualityscore", "%", 100],
  ["Workload percentile", "workload", "%", 100],
  ["Lazy score percentile", "lazyscore", "%", 100],
];

function getCourseId() {
  const match = window.location.pathname.match(/^\/course\/(?:[0-9-]+\/)?([0-9A-Z]{5})(?:\/|$)/);
  return match ? match[1] : null;
}

async function loadData() {
  try {
    const response = await fetch(chrome.runtime.getURL("db/data.json"));
    if (!response.ok) throw new Error("HTTP " + response.status);
    return { ok: true, db: await response.json() };
  } catch (error) {
    console.error("DTU Analyzer: Failed to load course data:", error);
    return { ok: false, reason: error.message };
  }
}

function findInsertionPoint() {
  const table = document.querySelector(".box.information > table");
  if (table) return { element: table, position: "afterend" };
  const box = document.querySelector(".box.information");
  if (box) return { element: box, position: "afterbegin" };
  const main = document.querySelector("#pagecontents, main, #content");
  return main ? { element: main, position: "afterbegin" } : null;
}

function panelElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (typeof text !== "undefined") element.textContent = text;
  return element;
}

function hasNumber(value) {
  return value !== null && value !== "" && typeof value !== "undefined" && Number.isFinite(Number(value));
}

function addMetric(list, data, [label, key, unit, maximum], prominent) {
  const row = panelElement("div");
  const value = panelElement("dd");
  if (hasNumber(data[key])) {
    const badge = panelElement("span", "metric-value", String(Math.round(Number(data[key]) * 10) / 10));
    badge.style.backgroundColor = DTUAnalyzer.getMetricColor(data[key], maximum);
    if (prominent) badge.appendChild(panelElement("span", "metric-unit", key === "avg" ? " / 12" : unit));
    else badge.appendChild(document.createTextNode(unit));
    value.appendChild(badge);
  } else {
    value.textContent = "—";
    value.setAttribute("aria-label", "No data");
  }
  row.append(panelElement("dt", "", label), value);
  list.appendChild(row);
}

function presentData(data, courseId, loadError) {
  if (document.getElementById("DTU-Course-Analyzer")) return;
  const insertion = findInsertionPoint();
  if (!insertion) {
    console.warn("DTU Analyzer: Could not find an insertion point");
    return;
  }
  const panel = panelElement("section", "dtu-analyzer");
  panel.id = "DTU-Course-Analyzer";
  panel.setAttribute("aria-labelledby", "dtu-insights-title");
  const title = panelElement("h2", "", "Course insights");
  title.id = "dtu-insights-title";
  panel.append(panelElement("p", "eyebrow", "DTU Course Analyzer"), title);
  insertion.element.insertAdjacentElement(insertion.position, panel);

  if (typeof DTUAnalyzer === "undefined") {
    panel.appendChild(panelElement("p", "dtu-status", "Extension scripts failed to load. Try reloading the extension."));
    return;
  }

  if (data) {
    const keyMetrics = panelElement("dl", "key-metrics");
    const metrics = panelElement("dl", "metrics");
    outputArr.forEach((metric, index) => addMetric(index < 2 ? keyMetrics : metrics, data, metric, index < 2));
    panel.append(keyMetrics, metrics);
    panel.appendChild(panelElement("p", "muted small workload-note", "Higher workload percentile = lighter workload."));
    const distribution = DTUAnalyzer.normalizeGrades(data.grades);
    if (distribution.some((item) => item.count > 0)) addGradeHistogram(panel, distribution);

    const sample = panelElement("div", "sample-note");
    sample.appendChild(panelElement("p", "", hasNumber(data.grade_participants)
      ? `${data.grade_participants} grade participants` : "Grade participant count unavailable"));
    const confidence = DTUAnalyzer.getConfidence(data.review_participants);
    sample.appendChild(panelElement("p", "", hasNumber(data.review_participants)
      ? `${data.review_participants} feedback responses${confidence ? " · " + confidence.label : ""}`
      : "Feedback response count unavailable"));
    sample.appendChild(panelElement("p", "muted", "Confidence describes sample size only. Grade and feedback periods may differ."));
    panel.appendChild(sample);
    addComparisonControls(panel, courseId);
  } else {
    panel.appendChild(panelElement("p", loadError ? "dtu-status" : "muted comparison-note", loadError
      ? "Course data could not be loaded. Try reloading the extension."
      : "No data found for this course."));
  }

  const footer = panelElement("div", "panel-footer");
  const link = panelElement("a", "", "About these metrics");
  link.href = "https://github.com/SMKIDRaadet/dtu-course-analyzer";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  footer.append(panelElement("span", "muted", "Based on historical data"), link);
  panel.appendChild(footer);
}

function addGradeHistogram(panel, distribution) {
  const figure = panelElement("figure", "histogram");
  const caption = panelElement("figcaption");
  caption.appendChild(panelElement("h3", "", "Grades awarded"));
  const chart = panelElement("div", "bars");
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", distribution.map((item) => `${item.grade}: ${item.count}`).join(", "));
  const maximum = Math.max(...distribution.map((item) => item.percentage), 1);
  distribution.forEach((item) => {
    const column = panelElement("div", "bar-column");
    column.title = `${item.grade}: ${item.count} (${item.percentage.toFixed(1)}%)`;
    const bar = panelElement("span", "bar");
    bar.style.height = `${item.count === 0 ? 0 : Math.max(2, (item.percentage / maximum) * 72)}px`;
    column.append(panelElement("span", "", String(item.count)), bar, panelElement("span", "grade-label", item.grade));
    chart.appendChild(column);
  });
  figure.append(caption, chart);
  panel.appendChild(figure);
}

function addComparisonControls(panel, courseId) {
  const controls = panelElement("div", "panel-actions");
  const button = panelElement("button", "dtu-btn primary", "Add to comparison");
  button.type = "button";
  button.disabled = true;
  const viewButton = panelElement("button", "dtu-btn", "View comparison");
  viewButton.type = "button";
  const message = panelElement("p", "dtu-status");
  message.setAttribute("role", "status");
  let renderedSelection = "";

  async function refresh(selection) {
    try {
      const current = selection || await DTUAnalyzer.readSelection();
      const selected = current.includes(courseId);
      button.textContent = selected ? "Remove from comparison" : "Add to comparison";
      button.setAttribute("aria-pressed", String(selected));
      button.disabled = false;
      viewButton.textContent = `View comparison (${current.length}/${DTUAnalyzer.MAX_COMPARISONS})`;
      renderedSelection = current.join(",");
    } catch (error) {
      console.error("DTU Analyzer: Could not read the saved comparison:", error);
      message.textContent = "Comparison is unavailable. Try reloading the page.";
    }
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
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
    } catch (error) {
      console.error("DTU Analyzer: Could not update the comparison:", error);
      message.textContent = "Could not save your comparison. Try reloading the page.";
    } finally {
      button.disabled = false;
    }
  });
  viewButton.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "openComparison" }, () => {
      if (!chrome.runtime.lastError) return;
      console.error("DTU Analyzer: Could not open the comparison:", chrome.runtime.lastError.message);
      message.textContent = "Could not open the comparison. Try reloading the page.";
    });
  });
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes[DTUAnalyzer.COMPARISON_KEY]) return;
    const selection = DTUAnalyzer.normalizeSelection(changes[DTUAnalyzer.COMPARISON_KEY].newValue);
    if (selection.join(",") !== renderedSelection) refresh(selection);
  });
  controls.append(button, viewButton, message);
  panel.appendChild(controls);
  refresh();
}

async function main() {
  try {
    const courseId = getCourseId();
    if (!courseId) return;
    const result = await loadData();
    presentData(result.ok ? result.db[courseId] : null, courseId, result.ok ? null : result.reason);
  } catch (error) {
    console.error("DTU Analyzer: Unexpected error:", error);
  }
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", main);
else main();
