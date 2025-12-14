// contentscript.js - Chrome Version 2.1.0

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

// 3. Wait for data to be available (handles race condition)
function waitForData(callback, maxAttempts = 20) {
  let attempts = 0;

  function check() {
    attempts++;
    if (typeof window.data !== 'undefined' && window.data !== null) {
      callback(window.data);
    } else if (attempts < maxAttempts) {
      setTimeout(check, 50);
    } else {
      console.warn("DTU Analyzer: Data not loaded after " + (maxAttempts * 50) + "ms");
      callback(null);
    }
  }

  check();
}

// 4. UI Generation Functions
function presentData(data) {
  // Vanilla JS selector: Find the table inside .box.information
  const infoBoxTable = document.querySelector(".box.information > table");

  // Guard clause if the page structure changes or element isn't found
  if (!infoBoxTable) {
    console.warn("DTU Analyzer: Could not find .box.information > table - page structure may have changed");
    return;
  }

  // Create the container table
  const table = document.createElement("table");
  const tbody = document.createElement("tbody");
  tbody.id = "DTU-Course-Analyzer";
  table.appendChild(tbody);

  // Insert our table immediately after the existing info table
  infoBoxTable.insertAdjacentElement("afterend", table);

  // Add Header Row
  const headerText = document.createElement("span");
  headerText.textContent = "—DTU Course Analyzer—";
  addRow(tbody, headerText);

  if (data) {
    let hasData = false;

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
function main() {
  const courseId = getCourseId();

  if (!courseId || courseId.length !== 5) {
    // Not on a course page, silently exit
    return;
  }

  waitForData((db) => {
    if (!db) {
      console.error("DTU Analyzer: Course data not loaded. Ensure db/data.js is included in manifest.");
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
  });
}

// Run when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
