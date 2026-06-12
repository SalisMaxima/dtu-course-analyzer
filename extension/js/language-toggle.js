// Language toggle functionality for DTU Course Analyzer
// This file must be external (not inline) to comply with Chrome Extension CSP
//
// The table carries a lang-da/lang-en class; CSS hides the other language's
// name column. Both columns stay in the DOM, so rows rendered later by
// table.js automatically follow the active language.

function applyLanguage(lang) {
  const table = document.getElementById("course-table");
  if (!table) return;

  const isEnglish = lang === "en";
  table.classList.toggle("lang-en", isEnglish);
  table.classList.toggle("lang-da", !isEnglish);

  document.getElementById("lang-en").classList.toggle("active", isEnglish);
  document.getElementById("lang-da").classList.toggle("active", !isEnglish);

  localStorage.setItem("dtu-analyzer-lang", lang);
}

function initLanguageToggle() {
  const danishButton = document.getElementById("lang-da");
  const englishButton = document.getElementById("lang-en");
  if (!danishButton || !englishButton) return;

  // CSP-compliant listeners, no inline onclick
  danishButton.addEventListener("click", () => applyLanguage("da"));
  englishButton.addEventListener("click", () => applyLanguage("en"));

  // Restore saved preference (default: English)
  applyLanguage(localStorage.getItem("dtu-analyzer-lang") || "en");
}

initLanguageToggle();
