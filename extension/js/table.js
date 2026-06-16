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

    tbody.appendChild(tr);
  });

  const info = document.getElementById("table-info");
  info.textContent = "Page " + (state.page + 1) + " of " + pageCount +
    " (" + state.filtered.length + " courses)";

  document.getElementById("prev-page").disabled = state.page === 0;
  document.getElementById("next-page").disabled = state.page >= pageCount - 1;

  renderSortIndicators();
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
  try {
    const response = await fetch("db/data.json");
    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }
    const db = await response.json();
    state.rows = buildRows(db);
    initEvents();
    update();
  } catch (e) {
    console.error("DTU Analyzer: Failed to load db/data.json:", e);
    const info = document.getElementById("table-info");
    if (info) info.textContent = "Failed to load course data.";
  }
}

initTable();
