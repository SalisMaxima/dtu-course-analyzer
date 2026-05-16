# DTU Course Analyzer

**Version 2.2.2** - A browser extension that analyzes and scores courses on kurser.dtu.dk with comprehensive grade distributions and course evaluations.

**New in 2.2.2:**
- Updated course data for the latest dataset
- Manifest V3 extension package with the updated bundled course database

**New in 2.2.0:**
- **Participant Statistics**: Shows total students enrolled and feedback response counts
- Helps assess reliability of course ratings and workload scores
- Displays as "Students/Feedback count: 576/327" in course info box and table

**Version 2.1.1:**
- Bilingual support: Toggle between Danish and English course names
- Updated data from 2024-2025 academic year
- 1,418 courses with 94.3% Danish name translations

The extension is provided as is, with no guarantee nor responsibility for its stability and correctness. For more info, see the license.


## Installation

### Chrome
Install from the [Chrome Web Store](https://chromewebstore.google.com/detail/dtu-course-analyzer/bimhgdngikcnelkhjindmdghndfmdcde)

### Firefox
Install from [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/dtu-course-analyzer/)

An alternative Firefox version is also available [here](https://addons.mozilla.org/en-US/firefox/addon/dtu-course-analyzer-2023).

### Manual Installation (Chrome/Edge)
1. Download the latest release from GitHub
2. In Chrome/Edge, go to: `chrome://extensions/` or `edge://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked" and select the `extension` folder


## Features

**Bilingual Support:**
- Toggle between Danish and English course names
- Language preference saved in browser storage

**Participant Statistics:**
- **Total Students**: Number of students who took the exam/course
- **Feedback Count**: Number of students who completed the evaluation survey
- Helps assess reliability of feedback-based metrics (course rating, workload)
- Example: A rating based on 97/202 responses is more reliable than 8/20 responses

**Metrics Calculated:**
All metrics are calculated based on historical data (higher is better):
- **Average grade**: Mean grade across all exam instances
- **Average grade percentile**: All courses ranked by average grade
- **Percent passed**: Ratio of exam attendees who passed
- **Course rating percentile**: Ranked by "Overall I think the course is good" from reviews
- **Workscore percentile**: Ranked by workload question (5 ECTS = 9h/week)
- **Lazyscore**: Average percentile of pass rate and workload - a metric for how much beer one can drink during a semester and still get decent grades 🍺

## Data Gathering and Analysis

Data is gathered through an automated pipeline:
1. **Authentication**: Playwright-based ADFS login to kurser.dtu.dk
2. **Course Discovery**: Fetches complete list of DTU course numbers
3. **Scraping**: Async scraper collects grade distributions and evaluations (both Danish and English)
4. **Validation**: Ensures data integrity and structure
5. **Analysis**: Calculates percentiles and statistics, generates extension data files

The scraper uses `aiohttp` with controlled concurrency to avoid rate limiting while maintaining performance.

# Development

## Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Data Pipeline

### 1. Authentication
Set environment variables and authenticate:
```bash
export DTU_USERNAME="your_dtu_username"
export DTU_PASSWORD="your_dtu_password"
python auth.py
```

This creates `secret.txt` with the session cookie.

### 2. Update Course List
```bash
python getCourseNumbers.py
```

### 3. Run Scraper
```bash
# Production scraper (async, faster)
python scraper_async.py

# Alternative (threaded, fallback)
python scraper.py
```

### 4. Validate Data
```bash
python validator.py coursedic.json
```

### 5. Generate Extension Files
```bash
python analyzer.py extension
```

This generates:
- `extension/db/data.js` - Extension data bundle
- `data.json` - Analysis results
- `extension/db.html` - DataTables HTML view

## Chrome Web Store Release

1. Log in to the Chrome Developer Dashboard with `dtu.course.analyzer@gmail.com`.
2. Make sure the course data is updated on the main Chrome release branch by running the full scrape and update workflow. The scrape usually takes about 90 minutes to finish.
3. Generate the extension files after the scrape:
   ```bash
   dtu-analyze extension
   ```
4. Bump the version number in `extension/manifest.json`. Keep the project version files in sync when preparing a tagged release.
5. Update the Chrome Web Store release notes in `docs/CHROME_WEB_STORE_RELEASE_NOTES.md`.
6. Zip the contents of the `extension` folder, not the folder itself:
   ```bash
   cd extension
   zip -r ../dtu-course-analyzer-vX.Y.Z.zip .
   ```
7. In the Chrome Developer Dashboard, upload the ZIP under "Pakker".
8. Publish the new package and wait for Chrome Web Store approval.

## Firefox Add-ons Release

Firefox releases are prepared from the `firefox` branch. The scrape and update workflow does not automatically propagate data from `master` to `firefox`, so mirror the generated data and documentation to the Firefox branch while preserving the Firefox-specific manifest.

1. Check out and update the Firefox branch:
   ```bash
   git checkout firefox
   git pull --ff-only origin firefox
   ```
2. Make sure the generated data files match the current release data from `master`, including `extension/db/data.js`, `extension/db.html`, `extension/js/init_table.js`, and the matching files under `source-code/extension/`.
3. Confirm `extension/manifest.json` keeps `background.scripts` and `browser_specific_settings.gecko`.
4. Bump the version number in `extension/manifest.json` and `source-code/extension/manifest.json`.
5. Update the Firefox listing/release notes for the new version.
6. Zip the contents of the `extension` folder, not the folder itself:
   ```bash
   cd extension
   zip -r ../dtu-course-analyzer-firefox-vX.Y.Z.zip .
   ```
7. Zip the contents of `source-code` for AMO review:
   ```bash
   cd source-code
   zip -r ../dtu-course-analyzer-firefox-source-vX.Y.Z.zip .
   ```
8. Submit the extension ZIP on addons.mozilla.org.
9. When AMO asks whether source code is required, upload the source-code ZIP. Include reviewer notes with a test URL (`http://kurser.dtu.dk/course/01005`), no-account-needed note, privacy/static-data note, and the location of `build.md`.
10. Publish the new version and wait for AMO approval.
 
## Testing
```bash
# Run all tests
pytest -v

# Run validator on scraped data
python validator.py coursedic.json
```

## Debugging Extension

### Chrome/Edge
1. Open `chrome://extensions/` or `edge://extensions/`
2. Enable "Developer mode" (upper right corner)
3. Click "Load unpacked"
4. Select the `extension` directory

### Firefox
```bash
# Install web-ext globally
npm install --global web-ext

# Run extension in temporary Firefox instance
cd extension
web-ext run
```

## Branch Structure

- **master**: Chrome extension version (uses Manifest V3 `service_worker`)
- **firefox**: Firefox extension version (uses `scripts: ["background.js"]`, includes `browser_specific_settings`)

**Note**: The `source-code/` folder is maintained on the **firefox** branch only, as required for Firefox Add-ons submission.
