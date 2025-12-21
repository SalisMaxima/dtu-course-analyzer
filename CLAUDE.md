# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Current Version: 2.2.0**

DTU Course Analyzer is a web scraper and browser extension that collects and analyzes historical grade distributions and course evaluations from DTU's (Technical University of Denmark) course database. The system scrapes data, validates it, analyzes it, and packages it into browser extensions (Chrome and Firefox) that students can use to search and compare courses.

**Latest Release (2.2.0):**
- Modern Python package structure with `src/dtu_analyzer/` modular architecture
- Professional packaging (pip installable, CLI tools)
- Bilingual support with Danish/English language toggle
- 1,418 courses with 94.3% Danish name translations
- Updated data from 2024-2025 academic year
- Python 3.10+ compatible (recommended: 3.12+)

## Branch Structure

- **master**: Chrome extension version (uses `service_worker` in manifest.json)
- **firefox**: Firefox extension version (uses `scripts: ["background.js"]` in manifest.json, includes `browser_specific_settings`)

**IMPORTANT**: The **source-code/** folder is maintained on the **firefox branch only**. Firefox Add-ons requires source code submission for review, so the source-code folder must be kept up-to-date on firefox branch with all necessary build files and instructions. When updating the extension, remember to update source-code/ on the firefox branch.

## Repository Structure

The project uses a modern Python package structure with modular architecture:

```
dtu-course-analyzer/
├── src/dtu_analyzer/          # Main package (all source code)
│   ├── auth/                  # Authentication module
│   ├── scrapers/              # Async and threaded scrapers
│   ├── parsers/               # HTML parsing logic (grades, reviews)
│   ├── analysis/              # Data analysis and statistics
│   ├── validation/            # Data validation
│   ├── scripts/               # Utility scripts
│   ├── utils/                 # Shared utilities (logger, prepender)
│   └── config/                # Configuration management
├── extension/                 # Browser extension files
├── tests/                     # Test suite
├── docs/                      # Documentation (roadmap, test results)
├── setup.py                   # Package installation (pip install -e .)
├── pyproject.toml            # Modern Python packaging config
├── setup.sh                  # Automated setup script
└── requirements.txt          # Dependencies
```

**Key Benefits:**
- **Modular Architecture**: 7 well-organized modules with clear separation of concerns
- **CLI Tools**: `dtu-auth`, `dtu-scrape`, `dtu-validate`, `dtu-analyze`, etc.
- **Pip Installable**: `pip install -e .` for development, or publish to PyPI
- **No Code Duplication**: Shared parsing logic eliminates ~500 lines of duplicate code
- **Type Safety**: 120+ type hints for better IDE support and fewer bugs
- **Backward Compatible**: All existing workflows continue to work

See `docs/REFACTORING_COMPLETE.md` for complete details.

## Essential Commands

### Quick Setup

```bash
# Automated setup (installs dependencies, Playwright, creates directories)
./setup.sh

# Or manual installation
pip install -e .          # Install package with CLI tools
playwright install chromium
```

### CLI Tools (Recommended)

After installing with `pip install -e .`, use the CLI tools:

```bash
# Set credentials (required for authentication)
export DTU_USERNAME='your-username'
export DTU_PASSWORD='your-password'

# Authenticate and get session cookie
dtu-auth

# Get list of all course numbers
dtu-get-courses

# Run scraper (async version - production)
dtu-scrape

# Run scraper (threaded version - fallback)
dtu-scrape-threaded

# Validate scraped data
dtu-validate coursedic.json

# Generate extension data files
dtu-analyze extension

# Run tests
pytest
```

### Direct Module Usage (Alternative)

You can also run modules directly:

```bash
python -m dtu_analyzer.auth.authenticator
python -m dtu_analyzer.scripts.get_course_numbers
python -m dtu_analyzer.scrapers.async_scraper
python -m dtu_analyzer.validation.validator coursedic.json
python -m dtu_analyzer.analysis.analyzer extension
```

## Data Pipeline Architecture

The system follows a strict sequential pipeline:

1. **Authentication** ([src/dtu_analyzer/auth/authenticator.py](src/dtu_analyzer/auth/authenticator.py))
   - CLI: `dtu-auth`
   - Uses Playwright to automate ADFS login at kurser.dtu.dk
   - Extracts ASP.NET_SessionId cookie
   - Saves to secret.txt for subsequent scraping

2. **Course Discovery** ([src/dtu_analyzer/scripts/get_course_numbers.py](src/dtu_analyzer/scripts/get_course_numbers.py))
   - CLI: `dtu-get-courses`
   - Fetches complete list of all DTU course numbers
   - Saves to coursenumbers.txt

3. **Data Scraping** ([src/dtu_analyzer/scrapers/](src/dtu_analyzer/scrapers/))
   - CLI: `dtu-scrape` (async) or `dtu-scrape-threaded`
   - Fetches grade distributions and course evaluations
   - Uses shared parsers from [src/dtu_analyzer/parsers/](src/dtu_analyzer/parsers/)
   - Extracts bilingual course names (Danish and English)
   - Saves to coursedic.json

4. **Validation** ([src/dtu_analyzer/validation/validator.py](src/dtu_analyzer/validation/validator.py))
   - CLI: `dtu-validate coursedic.json`
   - Validates data structure and integrity
   - Checks for required fields and data types

5. **Analysis** ([src/dtu_analyzer/analysis/analyzer.py](src/dtu_analyzer/analysis/analyzer.py))
   - CLI: `dtu-analyze extension`
   - Calculates aggregate statistics (percentiles, averages, pass rates)
   - Generates extension/db/data.js and data.json
   - Produces HTML table (extension/db.html) using DataTables

6. **Deployment** (GitHub Actions)
   - Automated via [.github/workflows/scrape.yml](.github/workflows/scrape.yml)
   - Uses CLI tools for all pipeline steps
   - Manual trigger only (workflow_dispatch)
   - Commits updated data files

## Key Technical Patterns

### Async Scraping ([src/dtu_analyzer/scrapers/async_scraper.py](src/dtu_analyzer/scrapers/async_scraper.py))

The production scraper uses aiohttp for concurrent I/O:

- **MAX_CONCURRENT = 2**: Carefully tuned to avoid rate limiting
  - Changed from 5 to 2 for better reliability
  - Higher values (5, 10, 20) cause server timeouts
  - 2 provides reliable scraping without rate limiting
- **Timeout Detection**: Global `timeout_occurred` flag for fail-fast behavior
  - If ANY request times out, entire scrape aborts
  - Prevents wasting time when server is rate-limiting
- **Semaphore-based Rate Limiting**: `asyncio.Semaphore(MAX_CONCURRENT)` controls concurrency
- **Shared Parsers**: Uses [src/dtu_analyzer/parsers/](src/dtu_analyzer/parsers/) for grade/review parsing

### Bilingual Support

The extension supports both Danish and English course names:

- **Data Collection**: Fetches both `name` (Danish) and `name_en` (English)
  - Danish: `BASE_URL/course/{courseN}?lang=da-DK` (**CRITICAL**: Must include `?lang=da-DK`)
  - English: `BASE_URL/course/{courseN}?lang=en-GB`
  - Without language parameters, DTU returns English by default
- **Column Visibility**: Uses CSS class for hiding, NOT DataTables bVisible
  - Both columns always present in DOM with `hidden-col` CSS class
  - `bSearchable: true` on both name columns for bilingual search
  - **Never use `bVisible: false`** - it breaks the language toggle
- **Language Toggle**: JavaScript in [extension/js/language-toggle.js](extension/js/language-toggle.js)
  - External file for CSP compliance (no inline scripts allowed)
  - Uses `style.display = 'table-cell'` or `'none'` to show/hide columns
  - Preference persisted in localStorage with key `'dtu-analyzer-lang'`
  - Default: English ('en')

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

### Async Scraper Settings

Configured in [src/dtu_analyzer/config/settings.py](src/dtu_analyzer/config/settings.py):

```python
MAX_CONCURRENT = 2  # Reduced from 5 for better reliability
TIMEOUT = 30        # Seconds before giving up on a request
BASE_URL = "http://kurser.dtu.dk"
```

Can be overridden with environment variables:
- `MAX_CONCURRENT`: Number of concurrent requests
- `TIMEOUT`: Request timeout in seconds
- `BASE_URL`: DTU course database URL

### Threaded Scraper Settings

Configured in [src/dtu_analyzer/scrapers/threaded_scraper.py](src/dtu_analyzer/scrapers/threaded_scraper.py):

```python
MAX_WORKERS = 8          # Number of parallel threads for course processing
MAX_GATHER_WORKERS = 3   # Number of parallel threads for grade/review fetching per course
TIMEOUT = 30             # Seconds before giving up on a request
BASE_URL = "http://kurser.dtu.dk"
```

**Performance Optimization**: The threaded scraper uses a two-level parallelization strategy:
- **MAX_WORKERS**: Controls how many courses are scraped concurrently
- **MAX_GATHER_WORKERS**: Controls how many grade/review pages are fetched in parallel per course
  - Each course typically has 10-20 grade/review pages
  - Using MAX_GATHER_WORKERS=3 provides 3-5x speedup per course without overwhelming the server
  - Keep this value LOW (2-5) to avoid rate limiting and being flagged for malicious behavior
  - Total concurrent requests = MAX_WORKERS × MAX_GATHER_WORKERS (max 24 with defaults)

### Analyzer Configuration

[src/dtu_analyzer/analysis/analyzer.py](src/dtu_analyzer/analysis/analyzer.py):

- **HTML Generation**: Uses list concatenation + join for efficient string building
  - Previous string concatenation was O(n²) for 1,418 courses × 11 columns
  - New approach is O(n) and 2-3x faster

- **Percentile Calculation**: Uses weighted percentile with grade counts
- **Column Ordering**: Defines table structure in extension/db.html
  - `name` (Danish) visible by default
  - `name_en` (English) hidden but searchable
  - Other columns: avg, participants, pass_percentage, etc.

### GitHub Actions ([.github/workflows/scrape.yml](.github/workflows/scrape.yml))

- **Python Version**: 3.12.3 (recommended: 3.12+, minimum: 3.10)
- **Package Installation**: Uses `pip install -e .` to install package and CLI tools
- **CLI Tools**: Uses `dtu-auth`, `dtu-get-courses`, `dtu-scrape`, etc.
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

1. **Package Installation**: Install package before using CLI tools
   - Run `pip install -e .` or use `./setup.sh` for automated setup
   - This installs CLI tools: `dtu-auth`, `dtu-scrape`, `dtu-validate`, etc.
   - Without installation, CLI commands won't be available

2. **Rate Limiting**: MAX_CONCURRENT should be 2 (configured in src/dtu_analyzer/config/settings.py)
   - DTU's server will timeout with higher concurrency
   - Current setting of 2 provides reliable scraping without rate limiting
   - If you get timeouts, DO NOT increase concurrency - it makes it worse

3. **Authentication**: secret.txt expires after a period
   - If scraper gets 403/401 errors, re-run `dtu-auth`
   - Requires DTU_USERNAME and DTU_PASSWORD environment variables
   - GitHub Actions uses DTU_USERNAME and DTU_PASSWORD secrets

4. **Data Validation**: Always run `dtu-validate coursedic.json` before `dtu-analyze`
   - Invalid data causes analyzer to crash
   - Validation catches missing fields, wrong types, etc.
   - Validator checks name translations (warns if >95% identical DA/EN names)

5. **Year Parsing**: The `parse_year()` function in src/dtu_analyzer/parsers/base.py handles 2-digit years
   - Located in shared parsers module
   - Future instances should not modify this logic without testing
   - Edge case: years > current_year + 2 trigger warnings

6. **DataTables Column Visibility**: NEVER use `bVisible: false` in column definitions
   - It removes columns from DOM entirely, breaking CSS nth-child selectors
   - Use CSS `hidden-col` class instead for hiding columns
   - Language toggle depends on columns remaining in DOM

7. **Chrome Extension CSP**: No inline scripts or onclick handlers allowed
   - All JavaScript must be in external files (e.g., language-toggle.js)
   - Use addEventListener() instead of onclick attributes
   - This applies to both Chrome and Firefox Manifest V3

8. **Version Management**: Keep version numbers in sync
   - Update version in setup.py, pyproject.toml, and manifest.json
   - Update manifest.json on both master and firefox branches
   - Remember to update source-code/ folder on firefox branch after version bumps

9. **Python Version**: Package requires Python 3.10+ (recommended: 3.12+)
   - GitHub Actions uses Python 3.12.3
   - Local development: use setup.sh to check version compatibility
   - Environment variable MAX_CONCURRENT can be set to override defaults

## Testing Strategy

- **Validation Tests**: Located in tests/ directory
  - `tests/validate_refactor.py`: 14 structural validation tests
  - `tests/validate_pipeline.py`: 5 end-to-end pipeline tests
  - Run with: `python -m tests.validate_refactor`

- **Integration Test**: Run full pipeline locally before pushing
  ```bash
  # Using CLI tools (recommended)
  dtu-auth
  dtu-get-courses
  dtu-scrape
  dtu-validate coursedic.json
  dtu-analyze extension

  # Or using direct module imports
  python -m dtu_analyzer.auth.authenticator
  python -m dtu_analyzer.scripts.get_course_numbers
  python -m dtu_analyzer.scrapers.async_scraper
  python -m dtu_analyzer.validation.validator coursedic.json
  python -m dtu_analyzer.analysis.analyzer extension
  ```

- **Manual Validation**: Check extension/db.html in browser
  - Test language toggle
  - Test search with both Danish and English names
  - Verify data.js loads correctly

- **Test Results**: See `docs/TEST_RESULTS.md` for comprehensive test report

## Browser Extension

The Chrome extension consists of:

- **Manifest**: [extension/manifest.json](extension/manifest.json)
- **Popup**: [extension/popup.html](extension/popup.html) - search interface
- **Data**: extension/db/data.js - generated by `dtu-analyze` CLI tool
- **Table**: extension/db.html - DataTables-based view

Key features:
- Search by course number or name (both languages)
- Sort by average grade, pass rate, participants
- View grade distributions and evaluation results
- Language toggle (DA/EN) with localStorage persistence
- **Paging enabled** (50 courses per page) for improved performance
  - Reduces initial render time by 5-10x
  - Uses less memory on low-end devices
  - Configurable via `pageLength` in templates/init_table.js

## Logging

All modules use the shared logger from [src/dtu_analyzer/utils/logger.py](src/dtu_analyzer/utils/logger.py):

- **INFO**: Progress updates, counts, timing
- **WARNING**: Non-critical issues (HTTP errors, missing optional fields)
- **ERROR**: Critical failures (auth failed, file not found, timeouts)
- **DEBUG**: Detailed parsing info (missing tables, participants)

Usage in modules:
```python
from dtu_analyzer.utils.logger import get_logger
logger = get_logger(__name__)
```

The async scraper logs are particularly important for diagnosing timeout issues.

## Architecture Strengths

1. **Modular Design**: 7 well-organized modules in src/dtu_analyzer/
   - auth/, scrapers/, parsers/, analysis/, validation/, scripts/, utils/, config/
2. **Code Reusability**: Shared parsers eliminate ~500 lines of duplication
3. **Type Safety**: 120+ type hints for better IDE support
4. **Separation of Concerns**: Auth, discovery, scraping, validation, analysis are isolated
5. **Professional Packaging**: pip installable with CLI tools
6. **Configuration Management**: Centralized config with environment variable support
7. **Fault Tolerance**: Robust error handling with per-course try/catch
8. **Performance**: Async I/O provides speedup while respecting rate limits
9. **Bilingual Support**: Clean hidden column pattern for dual-language search
10. **Automation**: GitHub Actions uses CLI tools for pipeline execution

## Known Limitations

1. **Authentication Dependency**: Requires valid DTU credentials
2. **Server Rate Limiting**: Cannot scrape faster than ~2 concurrent requests
3. **HTML Parsing Fragility**: Breaking changes to DTU's HTML structure require updates
4. **No Incremental Updates**: Always re-scrapes all courses (could be optimized)

## Documentation

- **README.md**: Project overview and quick start guide
- **CLAUDE.md**: This file - comprehensive technical documentation
- **docs/REFACTORING_COMPLETE.md**: Complete Phase 1 refactoring summary
- **docs/ROADMAP.md**: Project roadmap with future phases
- **docs/TEST_RESULTS.md**: Automated test results (19/19 passing)
- **docs/VALIDATION_REPORT.md**: Data validation analysis
- **docs/PrivacyPolicy.md**: Browser extension privacy policy
- **tests/README.md**: Test suite documentation
