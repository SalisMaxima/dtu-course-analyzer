const assert = require("node:assert/strict");
const test = require("node:test");

const utils = require("../extension/js/course-utils.js");

test("extracts bounded numeric and alphanumeric course IDs from catalogue paths", () => {
  for (const id of ["01001", "42S01", "KU002"]) {
    assert.equal(utils.getCourseIdFromPath(`/course/${id}`), id);
    assert.equal(utils.getCourseIdFromPath(`/course/2025-2026/${id}/info`), id);
  }
  for (const pathname of ["/course/010201", "/course/42s01", "/other/01001", "/course/01001-extra"]) {
    assert.equal(utils.getCourseIdFromPath(pathname), null);
  }
});

test("primary result uses pass percentage for pass/fail and grade for numeric courses", () => {
  const result = utils.getPrimaryResult({ grading_scale: "pass_fail", passpercent: 85, avg: 0 });
  assert.equal(result.value, 85);
  assert.equal(result.unit, "% passed");
  assert.equal(result.maxValue, 100);
  assert.equal(utils.getPrimaryResult({ grading_scale: "mixed", passpercent: 80, avg: 7 }).value, 80);
  assert.equal(utils.getPrimaryResult({ avg: 7, passpercent: 85 }).value, 7);
  assert.equal(utils.getPrimaryResult({ grading_scale: "pass_fail" }).value, undefined);
});

test("pass/fail results show their actual categories and source percentages", () => {
  const result = utils.normalizeGrades({ passed: "79", not_passed: "7", absent: "6" });
  assert.deepEqual(result.map(item => item.grade), ["Passed", "Not passed", "Absent"]);
  assert.equal(result[0].percentage.toFixed(1), "85.9");
  assert.equal(result[1].percentage.toFixed(1), "7.6");
  assert.equal(result[2].percentage.toFixed(1), "6.5");
});

test("approval categories stay visible and count toward the source denominator", () => {
  const result = utils.normalizeGrades({ passed: '575', not_passed: '127',
    approved: '0', not_approved: '45', absent: '57' });
  assert.equal(result.reduce((sum, item) => sum + item.count, 0), 804);
  assert.equal(result.find(item => item.grade === 'Not approved').count, 45);
  assert.equal(result.find(item => item.grade === 'Passed').percentage.toFixed(1), '71.5');
  assert.deepEqual(utils.normalizeGrades({approved: '9', not_approved: '1'}).map(item => item.grade),
    ['Approved', 'Not approved']);
});

test("mixed numeric and pass/fail data retains all awarded results", () => {
  const result = utils.normalizeGrades({ "7": "1", passed: "8", not_passed: "1" });
  assert.equal(result.reduce((sum, item) => sum + item.count, 0), 10);
  assert.equal(result.find(item => item.grade === "7").count, 1);
  assert.equal(result.find(item => item.grade === "Passed").count, 8);
});

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

  assert.deepEqual(
    distribution.map((item) => item.grade),
    ["-3", "00", "02", "4", "7", "10", "12"]
  );
  assert.equal(distribution.reduce((sum, item) => sum + item.count, 0), 10);
  assert.equal(distribution.find((item) => item.grade === "4").percentage, 20);
});

test("returns zero percentages for missing grade data", () => {
  const distribution = utils.normalizeGrades(null);
  assert.ok(distribution.every((item) => item.count === 0 && item.percentage === 0));
});

test("classifies feedback confidence at documented boundaries", () => {
  assert.equal(utils.getConfidence(0).key, "low");
  assert.equal(utils.getConfidence(9).key, "low");
  assert.equal(utils.getConfidence(10).key, "moderate");
  assert.equal(utils.getConfidence(29).key, "moderate");
  assert.equal(utils.getConfidence(30).key, "higher");
});

test("reports no confidence when the response count is missing", () => {
  assert.equal(utils.getConfidence(undefined), null);
  assert.equal(utils.getConfidence(null), null);
  assert.equal(utils.getConfidence(""), null);
  assert.equal(utils.getConfidence(-1), null);
  assert.equal(utils.getConfidence("many"), null);
});

// Hue carries the meaning (0 red to 120 green); the exact string format does not
function hueOf(color) {
  return color === null ? null : Number(color.match(/hsl\((\d+(?:\.\d+)?)/)[1]);
}

test("uses the shared red-to-green metric color scale", () => {
  assert.equal(hueOf(utils.getMetricColor(0, 100)), 0);
  assert.equal(hueOf(utils.getMetricColor(50, 100)), 60);
  assert.equal(hueOf(utils.getMetricColor(100, 100)), 120);
  assert.equal(hueOf(utils.getMetricColor(150, 100)), 120, "clamps above the maximum");
  assert.equal(utils.getMetricColor(undefined, 100), null);
  assert.equal(utils.getMetricColor(50, 0), null, "a zero maximum has no scale");
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

test("keeps course numbers that contain letters", () => {
  assert.deepEqual(utils.normalizeSelection(["42S01", "KU002", "23F11"]), [
    "42S01",
    "KU002",
    "23F11",
  ]);
  assert.equal(utils.isValidCourseId("42S01"), true);
  assert.equal(utils.isValidCourseId("42s01"), false, "lower case is not a course number");
  assert.equal(utils.isValidCourseId("123456"), false, "course numbers are five characters");
});

test("toggles selections and reports the four-course limit", () => {
  assert.deepEqual(utils.toggleSelection(["11111", "22222"], "11111").selection, ["22222"]);
  assert.equal(
    utils.toggleSelection(["11111", "22222", "33333", "44444"], "55555").limitReached,
    true
  );
});

test("refuses ids it cannot store instead of reporting success", () => {
  const result = utils.toggleSelection(["11111"], "not-a-course");
  assert.equal(result.invalid, true);
  assert.equal(result.added, false);
  assert.deepEqual(result.selection, ["11111"], "the selection is left untouched");
});

// A storage error must never look like an empty selection or a successful save
test("rejects when chrome.storage reports an error", async () => {
  const failure = { message: "QUOTA_BYTES quota exceeded" };
  globalThis.chrome = {
    runtime: { lastError: failure },
    storage: {
      local: {
        get: (key, callback) => callback(undefined),
        set: (items, callback) => callback(),
      },
    },
  };

  await assert.rejects(utils.readSelection(), /QUOTA_BYTES quota exceeded/);
  await assert.rejects(utils.writeSelection(["11111"]), /QUOTA_BYTES quota exceeded/);
  delete globalThis.chrome;
});

test("round-trips a selection through chrome.storage", async () => {
  let stored = null;
  globalThis.chrome = {
    runtime: {},
    storage: {
      local: {
        get: (key, callback) => callback(stored === null ? {} : { [key]: stored }),
        set: (items, callback) => {
          stored = items[utils.COMPARISON_KEY];
          callback();
        },
      },
    },
  };

  // Corrupt and over-long input is sanitised on the way in and on the way out
  const written = await utils.writeSelection(["11111", "nope", "11111", "22222"]);
  assert.deepEqual(written, ["11111", "22222"]);
  assert.deepEqual(await utils.readSelection(), ["11111", "22222"]);
  delete globalThis.chrome;
});
