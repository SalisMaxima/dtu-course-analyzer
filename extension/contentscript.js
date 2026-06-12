// contentscript.js - Version 2.3.0

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
async function loadData() {
  try {
    const response = await fetch(chrome.runtime.getURL("db/data.json"));
    if (!response.ok) {
      console.error("DTU Analyzer: Failed to load db/data.json (HTTP " + response.status + ")");
      return null;
    }
    return await response.json();
  } catch (e) {
    console.error("DTU Analyzer: Failed to load course data:", e);
    return null;
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

function presentData(data) {
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

  if (data) {
    let hasData = false;

    // Add combined participant count at the top (if available)
    const gradeParticipants = data["grade_participants"];
    const reviewParticipants = data["review_participants"];

    if (typeof gradeParticipants !== "undefined" && typeof reviewParticipants !== "undefined") {
      const labelSpan = document.createElement("span");
      labelSpan.textContent = "Students/Feedback count";
      labelSpan.style.whiteSpace = "nowrap";
      addRow(tbody, labelSpan, `${gradeParticipants}/${reviewParticipants}`, "", false);
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
  } else {
    addRow(tbody, "No data found for this course");
  }

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
  span.textContent = value + unit;

  if (colored && maxVal > 0) {
    span.style.backgroundColor = getColor(value / maxVal);
    span.style.padding = "2px 6px";
    span.style.borderRadius = "4px";
  }

  tdRight.appendChild(span);
  tr.appendChild(tdRight);

  tbody.appendChild(tr);
}

function getColor(value) {
  // Clamp value between 0 and 1
  const clamped = Math.max(0, Math.min(1, value));
  // Calculate Hue (Green=120 to Red=0)
  const hue = (clamped * 120).toString(10);
  return `hsl(${hue}, 100%, 50%)`;
}

// 5. Main Execution Logic
async function main() {
  try {
    const courseId = getCourseId();

    if (!courseId || courseId.length !== 5) {
      // Not on a course page, silently exit
      return;
    }

    const db = await loadData();
    if (!db) {
      presentData(null);
      return;
    }

    const courseData = db[courseId];
    if (courseData) {
      presentData(courseData);
    } else {
      console.info("DTU Analyzer: No data available for course " + courseId);
      presentData(null);
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
