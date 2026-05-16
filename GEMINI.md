# DTU Course Analyzer

**Version 2.2.0**

## Project Overview

DTU Course Analyzer is a Python-based web scraper and browser extension (Chrome, Firefox, Safari) that collects, analyzes, and displays historical grade distributions and course evaluations from the Technical University of Denmark (DTU) course database.

The system features a complete data pipeline that:
1.  Authenticates with DTU's systems.
2.  Discovers all available courses.
3.  Scrapes grade data and evaluations (bilingual: Danish/English).
4.  Validates the data integrity.
5.  Analyzes statistics (percentiles, pass rates, workload).
6.  Packages the results into a browser extension for easy student access.

## Architecture

The project follows a modern Python package structure with modular architecture:

### Core Python Package (`src/dtu_analyzer/`)
*   **`auth/`**: Authentication module using Playwright to handle ADFS login.
*   **`scrapers/`**: Data collection logic.
    *   `async_scraper.py`: Production scraper using `aiohttp` (optimized for concurrency).
    *   `threaded_scraper.py`: Fallback scraper using `requests` and threading.
*   **`parsers/`**: Shared HTML parsing logic for extracting grades and reviews.
*   **`analysis/`**: Statistical analysis and generation of extension data files.
*   **`validation/`**: Data integrity checks.
*   **`scripts/`**: Utility scripts (e.g., fetching course numbers).
*   **`utils/`**: Shared utilities (logging, etc.).

### Browser Extension (`extension/`)
*   **Manifest V3**: Uses `service_worker` (Chrome) or background scripts (Firefox).
*   **Frontend**: Vanilla JavaScript using DataTables for the UI.
*   **Data**: `db/data.js` contains the pre-calculated analysis results.

## Building and Running

### 1. Initial Setup

```bash
# Automated setup (installs dependencies, Playwright, creates directories)
./setup.sh

# Manual setup
pip install -e .          # Installs package and CLI tools
playwright install chromium
```

### 2. Data Pipeline Execution

The data pipeline **must** be run in this specific order.

**Step 1: Authentication**
Requires `DTU_USERNAME` and `DTU_PASSWORD` environment variables.
```bash
export DTU_USERNAME='your-username'
export DTU_PASSWORD='your-password'
dtu-auth  # Creates secret.txt with session cookie
```

**Step 2: Course Discovery**
Fetches the list of all course numbers.
```bash
dtu-get-courses  # Creates coursenumbers.txt
```

**Step 3: Scraping**
Collects data. **MAX_CONCURRENT** is set to 2 to avoid rate limiting.
```bash
dtu-scrape  # Production async scraper -> outputs coursedic.json
# OR
dtu-scrape-threaded  # Fallback
```

**Step 4: Validation**
Ensures data integrity before analysis.
```bash
dtu-validate coursedic.json
```

**Step 5: Analysis & Generation**
Calculates statistics and generates extension files.
```bash
dtu-analyze extension
# Generates:
# - extension/db/data.js
# - extension/db.html
# - data.json
```

### 3. Loading the Extension

**Chrome/Edge:**
1.  Go to `chrome://extensions/`.
2.  Enable "Developer mode".
3.  Click "Load unpacked" and select the `extension/` directory.

**Firefox:**
1.  Use `web-ext run` inside the `extension/` directory.

## Development Conventions

### Python
*   **Async/Await**: The production scraper is asynchronous (`aiohttp`). Handle concurrency carefully; do not increase `MAX_CONCURRENT` > 2.
*   **Type Hints**: Extensive use of type hints is encouraged.
*   **Parsing**: Use `BeautifulSoup` for HTML parsing. Logic is centralized in `src/dtu_analyzer/parsers/`.
*   **Testing**: Run tests with `pytest`.

### JavaScript
*   **Vanilla Only**: No frameworks (React, Vue, etc.).
*   **DOM Manipulation**: Use `document.createElement()` instead of `innerHTML` to prevent XSS.
*   **CSP Compliance**: No inline scripts or event handlers. All JS must be in external files.

### Branching Strategy
*   **`master`**: Chrome extension version (Manifest V3 with `service_worker`).
*   **`firefox`**: Firefox extension version (Manifest V3 with background scripts and browser-specific settings).
*   **Syncing**: Use specialized commands to sync content while preserving `manifest.json` differences.

### Common Pitfalls
*   **Rate Limiting**: The DTU server is sensitive. Keep concurrency low (default: 2).
*   **Auth Expiry**: `secret.txt` session cookies expire. Re-run `dtu-auth` if you see 401/403 errors.
*   **DataTables**: Do NOT use `bVisible: false` to hide columns; it removes them from the DOM and breaks the language toggle. Use the CSS class `hidden-col` instead.

## Release & Packaging

When creating the ZIP file for Chrome Web Store or Firefox Add-ons, you **must zip the contents of the `extension` folder**, not the folder itself. The `manifest.json` file must be at the root of the archive.

### Chrome Web Store Publishing

1.  Log in to the Chrome Developer Dashboard with `dtu.course.analyzer@gmail.com`.
2.  Make sure the course data is updated on the main Chrome release branch by running the full scrape and update workflow. This usually takes about 90 minutes.
3.  Run `dtu-analyze extension` after the scrape so `extension/db/data.js`, `extension/db.html`, and `extension/js/init_table.js` are current.
4.  Bump the version number in `extension/manifest.json` and keep the package metadata in sync for tagged releases.
5.  Update the Chrome Web Store release notes in `docs/CHROME_WEB_STORE_RELEASE_NOTES.md`.
6.  Zip the contents of `extension/`, not the folder itself.
7.  Upload the ZIP in the Chrome Developer Dashboard under "Pakker".
8.  Publish the package and wait for Chrome Web Store approval.

### Firefox Add-ons Publishing

1.  Use the `firefox` branch. The scrape/update workflow does not automatically propagate data from `master` to `firefox`.
2.  Mirror the generated release data from `master` into `extension/db/data.js`, `extension/db.html`, `extension/js/init_table.js`, and the matching files in `source-code/extension/`.
3.  Preserve the Firefox manifest fields: `background.scripts` and `browser_specific_settings.gecko`.
4.  Bump the version number in both `extension/manifest.json` and `source-code/extension/manifest.json`.
5.  Update Firefox listing/release notes for the new version.
6.  Zip the contents of `extension/`, not the folder itself, for the add-on package.
7.  Zip the contents of `source-code/` for AMO source-code review.
8.  Upload the extension ZIP on addons.mozilla.org.
9.  When AMO asks whether source code is required, upload the source-code ZIP. Add reviewer notes: test URL `http://kurser.dtu.dk/course/01005`, no account needed for normal use, static bundled dataset, no analytics, and build instructions in `build.md`.
10. Publish the package and wait for AMO approval.

**Correct Command:**
```bash
cd extension && zip -r ../dtu-course-analyzer-vX.Y.Z.zip .
```

**Incorrect Command:**
```bash
zip -r dtu-course-analyzer-vX.Y.Z.zip extension/
```
