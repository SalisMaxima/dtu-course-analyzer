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
