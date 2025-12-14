# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DTU Course Analyzer is a web scraper and browser extension that collects and analyzes historical grade distributions and course evaluations from DTU's (Technical University of Denmark) course database. The system scrapes data, validates it, analyzes it, and packages it into a Chrome extension that students can use to search and compare courses.

## Essential Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Authenticate and get session cookie
python auth.py  # Requires DTU_USERNAME and DTU_PASSWORD env vars

# Get list of all course numbers
python getCourseNumbers.py

# Run scraper (async version - production)
python scraper_async.py

# Run scraper (threaded version - fallback)
python scraper.py

# Validate scraped data
python validator.py coursedic.json

# Generate extension data files
python analyzer.py extension

# Run tests
pytest
```

## Data Pipeline Architecture

The system follows a strict sequential pipeline:

1. **Authentication** ([auth.py](auth.py))
   - Uses Playwright to automate ADFS login at kurser.dtu.dk
   - Extracts ASP.NET_SessionId cookie
   - Saves to secret.txt for subsequent scraping

2. **Course Discovery** ([getCourseNumbers.py](getCourseNumbers.py))
   - Fetches complete list of all DTU course numbers
   - Saves to coursenumbers.txt

3. **Data Scraping** ([scraper_async.py](scraper_async.py) / [scraper.py](scraper.py))
   - Fetches grade distributions and course evaluations
   - Extracts bilingual course names (Danish and English)
   - Saves to coursedic.json

4. **Validation** ([validator.py](validator.py))
   - Validates data structure and integrity
   - Checks for required fields and data types

5. **Analysis** ([analyzer.py](analyzer.py))
   - Calculates aggregate statistics (percentiles, averages, pass rates)
   - Generates extension/db/data.js and data.json
   - Produces HTML table (extension/db.html) using DataTables

6. **Deployment** (GitHub Actions)
   - Automated via [.github/workflows/scrape.yml](.github/workflows/scrape.yml)
   - Manual trigger only (workflow_dispatch)
   - Commits updated data files

## Key Technical Patterns

### Async Scraping ([scraper_async.py](scraper_async.py))

The production scraper uses aiohttp for concurrent I/O:

- **MAX_CONCURRENT = 5**: Carefully tuned to avoid rate limiting
  - Higher values (10, 20, 50) cause server timeouts
  - 5 provides ~1.5x speedup over threaded version while maintaining reliability
- **Timeout Detection**: Global `timeout_occurred` flag for fail-fast behavior
  - If ANY request times out, entire scrape aborts
  - Prevents wasting time when server is rate-limiting
- **Semaphore-based Rate Limiting**: `asyncio.Semaphore(MAX_CONCURRENT)` controls concurrency

### Bilingual Support

The extension supports both Danish and English course names:

- **Data Collection**: Fetches both `name` (Danish) and `name_en` (English)
  - Danish: `BASE_URL/course/{courseN}`
  - English: `BASE_URL/course/{courseN}?lang=en-GB`
- **Search Implementation**: Uses DataTables hidden column pattern
  - English column has `bVisible: false, bSearchable: true`
  - Both languages indexed for search, only one displayed
- **Language Toggle**: JavaScript toggle in [extension/db.html](extension/db.html)
  - Uses `column().visible()` to switch displayed language
  - Preference persisted in localStorage

### Grade Data Parsing

Grades are extracted from HTML tables at `/course/{courseN}/karakterer/{semester}`:

- **Grade Distribution**: Table row parsing for individual grade counts
- **Timestamp Parsing**: Handles both 2-digit and 4-digit years via `parse_year()`
  - 2-digit: <50 → 2000s, ≥50 → 1900s
- **Summary Statistics**: Extracts participants, pass percentage, average
  - Robust error handling as these fields may not exist for all courses

### Review Data Parsing

Course evaluations from `/course/{courseN}/evaluering/{semester}`:

- **Question-Answer Structure**: Nested dictionaries for each survey question
- **Participant Count**: Required field, returns False if missing
- **firstOption**: Determines scoring direction (e.g., "Strongly Agree" vs "Strongly Disagree")

## Important Configuration

### Scraper Settings ([scraper_async.py](scraper_async.py):19-22)

```python
MAX_CONCURRENT = 5  # DO NOT INCREASE - server will rate limit
TIMEOUT = 30        # Seconds before giving up on a request
BASE_URL = "http://kurser.dtu.dk"
```

### Analyzer Configuration ([analyzer.py](analyzer.py))

- **Percentile Calculation**: Uses weighted percentile with grade counts
- **Column Ordering**: [headNames](analyzer.py:267-275) defines table structure
  - `name` (Danish) visible by default
  - `name_en` (English) hidden but searchable
  - Other columns: avg, participants, pass_percentage, etc.

### GitHub Actions ([.github/workflows/scrape.yml](.github/workflows/scrape.yml))

- **Python Version**: 3.12.3 (specified for consistency)
- **Manual Trigger Only**: workflow_dispatch prevents accidental runs
- **Commit Pattern**: Auto-commits with "[skip ci]" to prevent loops

## Data Structure

### coursedic.json Format

```json
{
  "01005": {
    "name": "Avanceret ingeniørmatematik",
    "name_en": "Advanced Engineering Mathematics",
    "grades": [
      {
        "timestamp": "januar-2024",
        "participants": 150,
        "pass_percentage": 85,
        "avg": 7.2,
        "url": "http://kurser.dtu.dk/course/01005/karakterer/januar-2024",
        "12": "30",
        "10": "45",
        ...
      }
    ],
    "reviews": [
      {
        "timestamp": "E23",
        "participants": 120,
        "firstOption": "Helt enig",
        "1": {
          "question": "Jeg synes, undervisningen var god",
          "0": "15",
          "1": "30",
          ...
        }
      }
    ]
  }
}
```

## Common Pitfalls

1. **Rate Limiting**: Do not increase MAX_CONCURRENT above 5
   - DTU's server will timeout and abort the entire scrape
   - Even 10 concurrent requests causes occasional timeouts

2. **Authentication**: secret.txt expires after a period
   - If scraper gets 403/401 errors, re-run auth.py
   - GitHub Actions uses DTU_USERNAME and DTU_PASSWORD secrets

3. **Data Validation**: Always run validator.py before analyzer.py
   - Invalid data causes analyzer to crash
   - Validation catches missing fields, wrong types, etc.

4. **Year Parsing**: The `parse_year()` function handles 2-digit years
   - Future instances should not modify this logic without testing
   - Edge case: years > current_year + 2 trigger warnings

5. **Column Indices**: When modifying DataTables in db.html template
   - Column indices are 0-based and must match headNames order
   - Language toggle assumes: column 1 = Danish, column 2 = English

## Testing Strategy

- **Unit Tests**: Located in tests/ directory (pytest)
- **Integration Test**: Run full pipeline locally before pushing
  ```bash
  python auth.py
  python getCourseNumbers.py
  python scraper_async.py
  python validator.py coursedic.json
  python analyzer.py extension
  ```
- **Manual Validation**: Check extension/db.html in browser
  - Test language toggle
  - Test search with both Danish and English names
  - Verify data.js loads correctly

## Browser Extension

The Chrome extension consists of:

- **Manifest**: [extension/manifest.json](extension/manifest.json)
- **Popup**: [extension/popup.html](extension/popup.html) - search interface
- **Data**: extension/db/data.js - generated by analyzer.py
- **Table**: extension/db.html - DataTables-based view

Key features:
- Search by course number or name (both languages)
- Sort by average grade, pass rate, participants
- View grade distributions and evaluation results
- Language toggle (DA/EN) with localStorage persistence

## Logging

All scripts use [logger_config.py](logger_config.py) for structured logging:

- **INFO**: Progress updates, counts, timing
- **WARNING**: Non-critical issues (HTTP errors, missing optional fields)
- **ERROR**: Critical failures (auth failed, file not found, timeouts)
- **DEBUG**: Detailed parsing info (missing tables, participants)

The async scraper logs are particularly important for diagnosing timeout issues.

## Architecture Strengths

1. **Separation of Concerns**: Auth, discovery, scraping, validation, analysis are isolated
2. **Fault Tolerance**: Robust error handling with per-course try/catch
3. **Performance**: Async I/O provides speedup while respecting rate limits
4. **Bilingual Support**: Clean hidden column pattern for dual-language search
5. **Automation**: GitHub Actions enables scheduled updates

## Known Limitations

1. **Authentication Dependency**: Requires valid DTU credentials
2. **Server Rate Limiting**: Cannot scrape faster than ~5 concurrent requests
3. **HTML Parsing Fragility**: Breaking changes to DTU's HTML structure require updates
4. **No Incremental Updates**: Always re-scrapes all courses (could be optimized)
