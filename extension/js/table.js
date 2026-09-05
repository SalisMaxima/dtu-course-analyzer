// table.js - Vanilla JS course table for db.html (no jQuery/DataTables)
// Loads db/data.json, renders pages of 50 rows with sorting and bilingual search.

const PAGE_SIZE = 50;

const COLUMNS = [
  { key: "course", numeric: false, cssClass: "" },
  { key: "name", numeric: false, cssClass: "col-name" },
  { key: "name_en", numeric: false, cssClass: "col-name-en" },
  { key: "avg", numeric: true, cssClass: "" },
  { key: "avgp", numeric: true, cssClass: "" },
  { key: "passpercent", numeric: true, cssClass: "" },
  { key: "grade_participants", numeric: true, cssClass: "" },
  { key: "review_participants", numeric: true, cssClass: "" },
  { key: "qualityscore", numeric: true, cssClass: "" },
  { key: "workload", numeric: true, cssClass: "" },
  { key: "lazyscore", numeric: true, cssClass: "" },
];

const state = {
  rows: [],
  filtered: [],
  sortKey: "course",
  sortAsc: true,
  page: 0,
  selected: [],
};

function buildRows(db) {
  return Object.keys(db).map((courseN) => {
    const data = db[courseN];
    const row = { course: courseN };
    COLUMNS.forEach(({ key }) => {
      if (key === "course") return;
      const val = data[key];
      row[key] = (typeof val === "undefined" || val === null) ? "" : val;
    });
    return row;
  });
}

// Empty values always sort last, regardless of direction
function compareRows(a, b) {
  const { sortKey, sortAsc } = state;
  const valA = a[sortKey];
  const valB = b[sortKey];

  if (valA === "" && valB === "") return 0;
  if (valA === "") return 1;
  if (valB === "") return -1;

  const numA = parseFloat(valA);
  const numB = parseFloat(valB);
  let result;
  if (!isNaN(numA) && !isNaN(numB)) {
    result = numA - numB;
  } else {
    result = String(valA).localeCompare(String(valB));
  }
  return sortAsc ? result : -result;
}

function applyFilter() {
  const query = document.getElementById("search-input").value.trim().toLowerCase();
  if (!query) {
    state.filtered = state.rows.slice();
  } else {
    // Search course number and both names so either language matches
    state.filtered = state.rows.filter((row) =>
      row.course.toLowerCase().includes(query) ||
      String(row.name).toLowerCase().includes(query) ||
      String(row.name_en).toLowerCase().includes(query)
    );
  }
  state.filtered.sort(compareRows);
}

function renderSortIndicators() {
  document.querySelectorAll("#course-table th").forEach((th) => {
    const indicator = th.querySelector(".sort-indicator");
    if (!indicator) return;
    if (th.dataset.key === state.sortKey) {
      indicator.textContent = state.sortAsc ? " ▲" : " ▼";
    } else {
      indicator.textContent = "";
    }
  });
}

function renderPage() {
  const tbody = document.getElementById("course-tbody");
  if (!tbody) return;

  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  const pageCount = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  if (state.page >= pageCount) state.page = pageCount - 1;

  const start = state.page * PAGE_SIZE;
  const pageRows = state.filtered.slice(start, start + PAGE_SIZE);

  pageRows.forEach((row) => {
    const tr = document.createElement("tr");

    COLUMNS.forEach(({ key, cssClass }) => {
      const td = document.createElement("td");
      if (cssClass) td.className = cssClass;

      if (key === "course") {
        const link = document.createElement("a");
        link.href = "https://kurser.dtu.dk/course/" + row.course;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = row.course;
        td.appendChild(link);
      } else {
        td.textContent = row[key];
      }
      tr.appendChild(td);
    });

    const compareCell = document.createElement("td");
    const compareButton = document.createElement("button");
    const selected = state.selected.includes(row.course);
    compareButton.type = "button";
    compareButton.className = selected ? "compare-btn selected" : "compare-btn";
    compareButton.textContent = selected ? "Remove" : "Add";
    compareButton.setAttribute("aria-pressed", String(selected));
    compareButton.addEventListener("click", () => toggleCourse(row.course));
    compareCell.appendChild(compareButton);
    tr.appendChild(compareCell);

    tbody.appendChild(tr);
  });

  const info = document.getElementById("table-info");
  info.textContent = "Page " + (state.page + 1) + " of " + pageCount +
    " (" + state.filtered.length + " courses)";

  document.getElementById("prev-page").disabled = state.page === 0;
  document.getElementById("next-page").disabled = state.page >= pageCount - 1;

  renderSortIndicators();
}

function metricValue(data, key, unit = "") {
  const value = data && data[key];
  return (typeof value === "undefined" || value === null || value === "")
    ? "No data"
    : String(value) + unit;
}

function appendComparisonRow(tbody, label, selectedRows, valueForRow) {
  const tr = document.createElement("tr");
  const labelCell = document.createElement("td");
  labelCell.textContent = label;
  tr.appendChild(labelCell);

  selectedRows.forEach((row) => {
    const td = document.createElement("td");
    const value = valueForRow(row, td);
    if (typeof value !== "undefined") td.textContent = value;
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
}

function appendColoredComparisonRow(tbody, label, selectedRows, key, unit, maxValue) {
  appendComparisonRow(tbody, label, selectedRows, (row, td) => {
    const value = row[key];
    if (typeof value === "undefined" || value === null || value === "") return "No data";

    const badge = document.createElement("span");
    badge.className = "metric-value";
    badge.textContent = String(value) + unit;
    badge.style.backgroundColor = DTUAnalyzer.getMetricColor(value, maxValue);
    td.appendChild(badge);
  });
}

function renderComparison() {
  const panel = document.getElementById("comparison-panel");
  const table = document.getElementById("comparison-table");
  const empty = document.getElementById("comparison-empty");
  if (!panel || !table || !empty) return;

  // Keep selections that have no dataset entry so they stay visible and removable
  const selectedRows = state.selected.map((courseId) =>
    state.rows.find((row) => row.course === courseId) || { course: courseId, missing: true }
  );
  panel.hidden = selectedRows.length === 0 && window.location.hash !== "#compare";
  empty.hidden = selectedRows.length > 0;
  while (table.firstChild) table.removeChild(table.firstChild);
  if (selectedRows.length === 0) return;

  const useEnglish = document.getElementById("course-table").classList.contains("lang-en");
  const thead = document.createElement("thead");
  const heading = document.createElement("tr");
  const metricHeading = document.createElement("th");
  metricHeading.textContent = "Metric";
  heading.appendChild(metricHeading);
  selectedRows.forEach((row) => {
    const th = document.createElement("th");
    const link = document.createElement("a");
    link.href = "https://kurser.dtu.dk/course/" + row.course;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const name = useEnglish ? row.name_en : row.name;
    const label = row.missing ? "Not in this dataset" : (name || "Unnamed course");
    link.textContent = `${row.course} — ${label}`;
    th.appendChild(link);
    heading.appendChild(th);
  });
  thead.appendChild(heading);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  appendColoredComparisonRow(tbody, "Average grade", selectedRows, "avg", "", 12);
  appendColoredComparisonRow(tbody, "Grade percentile", selectedRows, "avgp", "%", 100);
  appendColoredComparisonRow(tbody, "Passed", selectedRows, "passpercent", "%", 100);
  appendColoredComparisonRow(tbody, "Course rating", selectedRows, "qualityscore", "%", 100);
  appendColoredComparisonRow(tbody, "Workload", selectedRows, "workload", "%", 100);
  appendColoredComparisonRow(tbody, "Lazy score", selectedRows, "lazyscore", "%", 100);
  appendComparisonRow(tbody, "Grade participants", selectedRows, (row) => metricValue(row, "grade_participants"));
  appendComparisonRow(tbody, "Feedback responses", selectedRows, (row, td) => {
    const count = row.review_participants;
    if (typeof count === "undefined" || count === null || count === "") return "No data";
    const countText = document.createTextNode(String(count));
    td.appendChild(countText);
    const confidence = DTUAnalyzer.getConfidence(count);
    if (confidence) {
      const note = document.createElement("span");
      note.className = "confidence-note";
      note.textContent = confidence.label;
      note.title = "Based on sample size, not response rate.";
      td.appendChild(note);
    }
  });
  appendComparisonRow(tbody, "Selection", selectedRows, (row, td) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "compare-btn selected";
    button.textContent = "Remove";
    button.addEventListener("click", () => toggleCourse(row.course));
    td.appendChild(button);
  });
  table.appendChild(tbody);
}

// Persist a selection and re-render, reporting failures instead of hanging the buttons
async function applySelection(selection) {
  const status = document.getElementById("comparison-status");
  try {
    state.selected = await DTUAnalyzer.writeSelection(selection);
  } catch (e) {
    console.error("DTU Analyzer: Could not save the comparison selection:", e);
    if (status) status.textContent = "Could not save your comparison selection.";
    return;
  }
  if (status) status.textContent = "";
  renderPage();
  renderComparison();
}

async function toggleCourse(courseId) {
  const result = DTUAnalyzer.toggleSelection(state.selected, courseId);
  const status = document.getElementById("comparison-status");
  if (result.invalid) {
    if (status) status.textContent = `${courseId} cannot be added to a comparison.`;
    return;
  }
  if (result.limitReached) {
    if (status) status.textContent = `Maximum ${DTUAnalyzer.MAX_COMPARISONS} courses. Remove one before adding another.`;
    return;
  }
  await applySelection(result.selection);
}

async function initComparison() {
  state.selected = await DTUAnalyzer.readSelection();

  const clearButton = document.getElementById("clear-comparison");
  if (clearButton) clearButton.addEventListener("click", () => applySelection([]));
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local" || !changes[DTUAnalyzer.COMPARISON_KEY]) return;
    const selection = DTUAnalyzer.normalizeSelection(changes[DTUAnalyzer.COMPARISON_KEY].newValue);
    // Our own writes have already re-rendered - skip the echo
    if (selection.join(",") === state.selected.join(",")) return;
    state.selected = selection;
    renderPage();
    renderComparison();
  });
  window.addEventListener("hashchange", renderComparison);
  window.addEventListener("dtu-analyzer-language-changed", renderComparison);
}

function update() {
  applyFilter();
  renderPage();
}

function initEvents() {
  document.querySelectorAll("#course-table th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (!key) return;
      if (state.sortKey === key) {
        state.sortAsc = !state.sortAsc;
      } else {
        state.sortKey = key;
        // Numeric metrics are most useful sorted high-to-low first
        const column = COLUMNS.find((col) => col.key === key);
        state.sortAsc = !(column && column.numeric);
      }
      state.page = 0;
      update();
    });
  });

  document.getElementById("search-input").addEventListener("input", () => {
    state.page = 0;
    update();
  });

  document.getElementById("prev-page").addEventListener("click", () => {
    if (state.page > 0) {
      state.page--;
      renderPage();
    }
  });

  document.getElementById("next-page").addEventListener("click", () => {
    state.page++;
    renderPage();
  });
}

async function initTable() {
  let db;
  try {
    const response = await fetch("db/data.json");
    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }
    db = await response.json();
  } catch (e) {
    console.error("DTU Analyzer: Failed to load db/data.json:", e);
    const info = document.getElementById("table-info");
    if (info) info.textContent = "Failed to load course data.";
    return;
  }

  state.rows = buildRows(db);
  initEvents();
  update();

  // Comparison needs chrome.storage - keep its failures out of the table's error path
  try {
    await initComparison();
    renderPage();
    renderComparison();
  } catch (e) {
    console.error("DTU Analyzer: Course comparison is unavailable:", e);
    const status = document.getElementById("comparison-status");
    if (status) status.textContent = "Course comparison is unavailable here.";
  }
}

initTable();
