// Shared data and comparison helpers for DTU Course Analyzer.

(function initCourseUtils(root) {
  const GRADE_ORDER = ["-3", "00", "02", "4", "7", "10", "12"];
  const COMPARISON_KEY = "dtu-analyzer-comparison-v1";
  const MAX_COMPARISONS = 4;

  function normalizeGrades(grades) {
    const values = GRADE_ORDER.map((grade) => {
      const parsed = Number(grades && grades[grade]);
      return { grade, count: Number.isFinite(parsed) && parsed > 0 ? parsed : 0 };
    });
    const total = values.reduce((sum, item) => sum + item.count, 0);
    return values.map((item) => ({
      grade: item.grade,
      count: item.count,
      percentage: total > 0 ? (item.count / total) * 100 : 0,
    }));
  }

  function getConfidence(count) {
    const parsed = Number(count);
    if (!Number.isFinite(parsed) || parsed < 0) return null;
    if (parsed < 10) return { key: "low", label: "Low confidence" };
    if (parsed < 30) return { key: "moderate", label: "Moderate confidence" };
    return { key: "higher", label: "Higher confidence" };
  }

  function getMetricColor(value, maxValue = 1) {
    const parsedValue = Number(value);
    const parsedMax = Number(maxValue);
    if (!Number.isFinite(parsedValue) || !Number.isFinite(parsedMax) || parsedMax <= 0) {
      return null;
    }
    const clamped = Math.max(0, Math.min(1, parsedValue / parsedMax));
    return `hsl(${clamped * 120}, 100%, 50%)`;
  }

  function normalizeSelection(courseIds) {
    const unique = [];
    (Array.isArray(courseIds) ? courseIds : []).forEach((courseId) => {
      const normalized = String(courseId);
      if (/^[0-9]{5}$/.test(normalized) && !unique.includes(normalized)) {
        unique.push(normalized);
      }
    });
    return unique.slice(0, MAX_COMPARISONS);
  }

  function toggleSelection(courseIds, courseId) {
    const selection = normalizeSelection(courseIds);
    const normalizedId = String(courseId);
    if (selection.includes(normalizedId)) {
      return {
        selection: selection.filter((id) => id !== normalizedId),
        added: false,
        limitReached: false,
      };
    }
    if (selection.length >= MAX_COMPARISONS) {
      return { selection, added: false, limitReached: true };
    }
    return { selection: selection.concat(normalizedId), added: true, limitReached: false };
  }

  function readSelection() {
    return new Promise((resolve) => {
      chrome.storage.local.get(COMPARISON_KEY, (result) => {
        resolve(normalizeSelection(result && result[COMPARISON_KEY]));
      });
    });
  }

  function writeSelection(courseIds) {
    const selection = normalizeSelection(courseIds);
    return new Promise((resolve) => {
      chrome.storage.local.set({ [COMPARISON_KEY]: selection }, () => resolve(selection));
    });
  }

  const api = {
    COMPARISON_KEY,
    GRADE_ORDER,
    MAX_COMPARISONS,
    getConfidence,
    getMetricColor,
    normalizeGrades,
    normalizeSelection,
    readSelection,
    toggleSelection,
    writeSelection,
  };

  root.DTUAnalyzer = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
