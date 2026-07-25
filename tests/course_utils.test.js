const assert = require("node:assert/strict");
const test = require("node:test");

const utils = require("../extension/js/course-utils.js");

test("normalizes grade counts and calculates percentages", () => {
  const distribution = utils.normalizeGrades({
    "-3": "1",
    "00": "0",
    "02": "1",
    "4": "2",
    "7": "2",
    "10": "2",
    "12": "2",
  });

  assert.deepEqual(distribution.map((item) => item.grade), utils.GRADE_ORDER);
  assert.equal(distribution.reduce((sum, item) => sum + item.count, 0), 10);
  assert.equal(distribution.find((item) => item.grade === "4").percentage, 20);
});

test("returns zero percentages for missing grade data", () => {
  const distribution = utils.normalizeGrades(null);
  assert.ok(distribution.every((item) => item.count === 0 && item.percentage === 0));
});

test("classifies feedback confidence at documented boundaries", () => {
  assert.equal(utils.getConfidence(9).key, "low");
  assert.equal(utils.getConfidence(10).key, "moderate");
  assert.equal(utils.getConfidence(29).key, "moderate");
  assert.equal(utils.getConfidence(30).key, "higher");
  assert.equal(utils.getConfidence(undefined), null);
});

test("uses the shared red-to-green metric color scale", () => {
  assert.equal(utils.getMetricColor(0, 100), "hsl(0, 100%, 50%)");
  assert.equal(utils.getMetricColor(50, 100), "hsl(60, 100%, 50%)");
  assert.equal(utils.getMetricColor(100, 100), "hsl(120, 100%, 50%)");
  assert.equal(utils.getMetricColor(150, 100), "hsl(120, 100%, 50%)");
  assert.equal(utils.getMetricColor(undefined, 100), null);
});

test("normalizes, deduplicates, and caps comparison IDs", () => {
  const selection = utils.normalizeSelection([
    "11111",
    "11111",
    "invalid",
    "22222",
    "33333",
    "44444",
    "55555",
  ]);
  assert.deepEqual(selection, ["11111", "22222", "33333", "44444"]);
});

test("toggles selections and reports the four-course limit", () => {
  assert.deepEqual(utils.toggleSelection(["11111", "22222"], "11111").selection, ["22222"]);
  assert.equal(
    utils.toggleSelection(["11111", "22222", "33333", "44444"], "55555").limitReached,
    true
  );
});
