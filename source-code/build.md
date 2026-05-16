# Build Instructions for DTU Course Analyzer

This document describes how to build the `DTU Course Analyzer` extension from source.

## 1. Environment Requirements
*   **Operating System:** Windows, macOS, or Linux.
*   **Python:** Python 3.10 or higher.
*   **Node.js/NPM:** Required if you wish to run the `web-ext` linting or testing tools (optional).
*   **Dependencies:** Listed in `requirements.txt`.

## 2. Setup
1.  Unzip the source code archive.
2.  Open a terminal in the root directory of the project.
3.  Install the package in editable mode to make the CLI tools available:
    ```bash
    pip install -e .
    ```
    (Or install dependencies manually: `pip install -r requirements.txt`)

## 3. Extension Architecture
The source code for the extension is located in the `extension/` directory.
*   `extension/manifest.json`: Manifest V3 configuration.
*   `extension/background.js`: Background service worker/scripts.
*   `extension/contentscript.js`: Content script injected into DTU pages.
*   `extension/db/data.js`: **Pre-generated data file** containing course statistics.

## 4. Re-generating Data (Optional)
The `extension/db/data.js` file is included in this bundle and contains the analyzed data from the 2024-2025 academic year.

**Note:** Re-generating this data requires valid DTU student/staff credentials and takes significant time.

If you have credentials and wish to verify the pipeline:
1.  **Authenticate:**
    ```bash
    export DTU_USERNAME="your_username"
    export DTU_PASSWORD="your_password"
    dtu-auth
    ```
2.  **Scrape Data:**
    ```bash
    dtu-scrape
    ```
    (This creates `coursedic.json`)
3.  **Analyze & Generate:**
    ```bash
    dtu-analyze extension
    ```
    (This updates `extension/db/data.js` and `extension/db.html`)

## 5. Building the Extension Package
To create the ZIP file for installation or submission (e.g., to Firefox Add-ons):

1.  Navigate to the extension directory:
    ```bash
    cd extension
    ```
2.  Zip the **contents** of the directory (not the directory itself):
    ```bash
    zip -r ../dtu-course-analyzer-build.zip .
    ```

The resulting `dtu-course-analyzer-build.zip` is ready for installation.

## 6. Chrome Web Store Publishing

Chrome releases are prepared from the main Chrome release branch, not automatically from the scrape itself. After updating the data there, mirror the generated data and documentation to the Firefox branch when needed.

1.  Log in to the Chrome Developer Dashboard with `dtu.course.analyzer@gmail.com`.
2.  Make sure the course data is updated on the main Chrome release branch by running the full scrape and update workflow. The scrape usually takes about 90 minutes.
3.  Generate the extension files after the scrape:
    ```bash
    dtu-analyze extension
    ```
4.  Bump the version number in `extension/manifest.json`.
5.  Update the Chrome Web Store release notes in `docs/CHROME_WEB_STORE_RELEASE_NOTES.md`.
6.  Zip the contents of the `extension` folder, not the folder itself:
    ```bash
    cd extension
    zip -r ../dtu-course-analyzer-vX.Y.Z.zip .
    ```
7.  Upload the ZIP under "Pakker".
8.  Publish it and wait for Chrome Web Store approval.

## 7. Firefox Add-ons Publishing

Firefox releases are prepared from the `firefox` branch. The scrape and update workflow does not automatically propagate data from `master` to `firefox`; mirror the generated data and documentation to the Firefox branch while preserving the Firefox-specific manifest.

1.  Make sure `extension/db/data.js`, `extension/db.html`, `extension/js/init_table.js`, and the matching files under `source-code/extension/` contain the current release data.
2.  Confirm `extension/manifest.json` keeps the Firefox-specific fields:
    - `background.scripts`
    - `browser_specific_settings.gecko`
3.  Bump the version number in `extension/manifest.json` and `source-code/extension/manifest.json`.
4.  Update the Firefox listing/release notes for the new version.
5.  Build the Firefox extension package by zipping the contents of `extension/`, not the folder itself:
    ```bash
    cd extension
    zip -r ../dtu-course-analyzer-firefox-vX.Y.Z.zip .
    ```
6.  Build the source-code package for AMO review by zipping the contents of `source-code/`:
    ```bash
    cd source-code
    zip -r ../dtu-course-analyzer-firefox-source-vX.Y.Z.zip .
    ```
7.  Submit the extension ZIP on addons.mozilla.org.
8.  When AMO asks whether source code is required, upload the source-code ZIP. Include reviewer notes with test URL `http://kurser.dtu.dk/course/01005`, no account needed, static bundled dataset/no analytics, and build instructions in this `build.md`.
9.  Publish the new version and wait for AMO approval.
