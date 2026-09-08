const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// Small DOM double: execute the shipped renderers without a browser dependency.
class Element {
  constructor() {
    this.children = [];
    this.style = {};
    this.attributes = {};
    this.classList = { contains: () => false };
    this.value = "";
    this.listeners = {};
  }
  set textContent(value) { this.children = []; this.text = String(value); }
  get textContent() { return (this.text || "") + this.children.map(c => c.textContent).join(""); }
  get firstChild() { return this.children[0]; }
  appendChild(child) { this.children.push(child); return child; }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
  insertAdjacentElement(position, child) { this.appendChild(child); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
}

function renderer(script) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const context = vm.createContext({
    console, Node: Element,
    document: {
      readyState: "loading",
      addEventListener() {},
      createElement: () => new Element(),
      createTextNode: text => { const e = new Element(); e.textContent = text; return e; },
      querySelector: () => node("anchor"),
      querySelectorAll: () => [],
      getElementById: node,
    },
    window: { location: { pathname: "/course/01020", hash: "#compare" } },
    chrome: {
      runtime: {},
      storage: { local: { get: (key, cb) => cb({}) }, onChanged: { addListener() {} } },
    },
    // Leave automatic table initialization pending; tests provide their fixtures.
    fetch: () => new Promise(() => {}),
  });
  for (const file of ["js/course-utils.js", script]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../extension", file), "utf8"), context);
  }
  return { context, node };
}

for (const scale of ["pass_fail", "mixed", "seven_point"]) {
  // Stale numeric metrics must also be hidden for older packaged datasets.
  const fixture = {
    grading_scale: scale, avg: 9.4, avgp: 61.2, passpercent: 85.9,
    grades: scale === "seven_point" ? { "12": 79, "00": 7 }
      : { passed: 79, not_passed: 7, absent: 6, ...(scale === "mixed" ? { "12": 2 } : {}) },
    grade_period: "Summer-2026",
  };
  test(`course page renders correct metrics for ${scale}`, () => {
    const { context, node } = renderer("contentscript.js");
    context.presentData(fixture, "01020");
    const text = node("anchor").textContent;
    assert.match(text, /Grades in: Summer 2026/);
    if (scale === "seven_point") {
      assert.match(text, /Average gradeⓘ9.4/);
      assert.match(text, /Average grade percentileⓘ61.2%/);
    } else {
      assert.match(text, /Percentage passedⓘ85.9%/);
      assert.doesNotMatch(text, /Average grade/);
      const tbody = node("anchor").children[0].children[0];
      const chart = tbody.children.flatMap(row => row.children)
        .flatMap(cell => cell.children).find(e => e.attributes.role === "img");
      assert.match(chart.attributes["aria-label"], /Passed: 79, Not passed: 7, Absent: 6/);
      if (scale === "mixed") assert.match(chart.attributes["aria-label"], /12: 2/);
      else assert.doesNotMatch(chart.attributes["aria-label"], /12:/);
    }
  });

  test(`database and comparison render correct metrics for ${scale}`, () => {
    const { context, node } = renderer("js/table.js");
    context.fixture = fixture;
    vm.runInContext(`
      state.rows = buildRows({ "01020": fixture });
      state.filtered = state.rows;
      state.selected = ["01020"];
      renderPage();
      renderComparison();
    `, context);
    const cells = node("course-tbody").children[0].children;
    const rows = node("comparison-table").children[1].children;
    const percentile = rows.find(row => row.children[0].textContent === "Grade percentile");
    if (scale === "seven_point") {
      assert.equal(cells[3].textContent, "9.4");
      assert.equal(cells[4].textContent, "61.2");
      assert.equal(percentile.children[1].textContent, "61.2%");
    } else {
      assert.equal(cells[3].textContent, "85.9% passed");
      assert.equal(cells[4].textContent, "Not applicable");
      assert.equal(rows[0].children[1].textContent, "85.9% passed");
      assert.equal(percentile.children[1].textContent, "Not applicable");
    }
  });
}

test("zero pass/fail placeholders keep the numeric histogram and average", () => {
  const { context, node } = renderer("contentscript.js");
  context.presentData({
    grading_scale: "seven_point", avg: 7, avgp: 50, passpercent: 100,
    grades: { "7": "10", passed: "0", not_passed: "0", approved: "0" },
  }, "01001");
  const text = node("anchor").textContent;
  assert.match(text, /Average gradeⓘ7/);
  assert.match(text, /Average grade percentileⓘ50%/);
  const tbody = node("anchor").children[0].children[0];
  const chart = tbody.children.flatMap(row => row.children)
    .flatMap(cell => cell.children).find(e => e.attributes.role === "img");
  assert.doesNotMatch(chart.attributes["aria-label"], /Passed|Approved/);
  assert.match(chart.attributes["aria-label"], /7: 10/);
});

test("approval-only and zero-result categorical histograms retain their labels", () => {
  const { context } = renderer("contentscript.js");
  for (const grades of [{ approved: 0, not_approved: 0 }, { passed: 0, not_passed: 0 }]) {
    const distribution = context.DTUAnalyzer.normalizeGrades(grades);
    assert.equal(distribution.length, 2);
    assert.ok(distribution.every(item => item.count === 0 && item.percentage === 0));
  }
  const mixed = context.DTUAnalyzer.normalizeGrades({ "7": 1, approved: 2 });
  assert.ok(mixed.some(item => item.grade === "Approved" && item.count === 2));
  assert.ok(mixed.some(item => item.grade === "7" && item.count === 1));
});

test("beta selector switches numerical, pass/fail and hidden exams without stale metrics", () => {
  const { context, node } = renderer("contentscript.js");
  const data = {
    default_exam_id: "regular", avgp: 75,
    exam_default_note: "Latest regular exam", history_collected_at: "2026-09-08",
    exam_history: [
      { id: "regular", grade_period: "Winter-2025", histogram_course: "01001", classification: "ordinary_candidate",
        distribution_status: "published", grading_scale: "seven_point", avg: 6.7, passpercent: 80, grades: { "7": 8, "00": 2 } },
      { id: "binary", grade_period: "Summer-2026", histogram_course: "01001", classification: "resit_candidate",
        distribution_status: "published", grading_scale: "pass_fail", passpercent: 90, grades: { passed: 9, not_passed: 1 } },
      { id: "hidden", grade_period: "Summer-2024", histogram_course: "01001", classification: "resit_candidate",
        distribution_status: "suppressed" },
    ],
  };
  context.presentData(data, "01001");
  function walk(e) { return [e, ...e.children.flatMap(walk)]; }
  const select = walk(node("anchor")).find(e => e.attributes["aria-label"] === "Displayed exam");
  assert.equal(select.value, "regular");
  assert.match(node("anchor").textContent, /Average gradeⓘ6.7/);
  assert.match(node("anchor").textContent, /Average grade percentileⓘ75%/);
  select.value = "binary"; select.listeners.change();
  assert.match(node("anchor").textContent, /Percentage passedⓘ90%/);
  assert.doesNotMatch(node("anchor").textContent, /Average grade/);
  select.value = "hidden"; select.listeners.change();
  assert.match(node("anchor").textContent, /three or fewer/);
  assert.doesNotMatch(node("anchor").textContent, /Grades awarded|Percentage passed90%|Average grade/);
  select.value = "regular"; select.listeners.change();
  assert.match(node("anchor").textContent, /Average gradeⓘ6.7/);
  assert.doesNotMatch(node("anchor").textContent, /three or fewer/);
});
