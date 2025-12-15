# DTU Course Analyzer

**Version 2.1.1** - A browser extension that analyzes and scores courses on kurser.dtu.dk with comprehensive grade distributions and course evaluations.

**New in 2.1.1:**
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

