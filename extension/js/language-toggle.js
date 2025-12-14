// Language toggle functionality for DTU Course Analyzer
// This file must be external (not inline) to comply with Chrome Extension CSP

function toggleLanguage(lang) {
  // Get all cells in both name columns (column indices: 2=Danish, 3=English in CSS nth-child)
  var danishCells = document.querySelectorAll('#example td:nth-child(2), #example th:nth-child(2)');
  var englishCells = document.querySelectorAll('#example td:nth-child(3), #example th:nth-child(3)');

  if (lang === 'en') {
    // Show English name (column 3), hide Danish name (column 2)
    danishCells.forEach(function(cell) {
      cell.style.display = 'table-cell';
    });
    englishCells.forEach(function(cell) {
      cell.style.display = 'none';
    });

    document.getElementById('lang-en').classList.add('active');
    document.getElementById('lang-da').classList.remove('active');
    localStorage.setItem('dtu-analyzer-lang', 'en');
  } else {
    // Show Danish name (column 2), hide English name (column 3)
    danishCells.forEach(function(cell) {
      cell.style.display = 'none';
    });
    englishCells.forEach(function(cell) {
      cell.style.display = 'table-cell';
    });

    document.getElementById('lang-da').classList.add('active');
    document.getElementById('lang-en').classList.remove('active');
    localStorage.setItem('dtu-analyzer-lang', 'da');
  }
}

// Restore language preference on page load
$(document).ready(function() {
  // Add click event listeners (CSP-compliant, no inline onclick)
  document.getElementById('lang-da').addEventListener('click', function() {
    toggleLanguage('da');
  });
  document.getElementById('lang-en').addEventListener('click', function() {
    toggleLanguage('en');
  });

  // Restore saved language preference after DataTables initializes
  // Default to English ('en')
  setTimeout(function() {
    var savedLang = localStorage.getItem('dtu-analyzer-lang') || 'en';
    toggleLanguage(savedLang);
  }, 100);
});
