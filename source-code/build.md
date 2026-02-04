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
