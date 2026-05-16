# Build Instructions for DTU Course Analyzer

This document describes how to build the `DTU Course Analyzer` extension from source.

## 1. Environment Requirements
* **Operating System:** Windows, macOS, or Linux.
* **Python:** Python 3.7 or higher is required.
* **Dependencies:** Listed in `requirements.txt`.

## 2. Setup
1.  Unzip the source code archive.
2.  Open a terminal in the root directory of the project.
3.  Install the required Python dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## 3. Build Process
The extension relies on a pre-generated dataset (`coursedic.json`) which is processed by a Python script to generate the final extension files (`db.html`, `data.js`, etc.).

To build the extension, run the following command:

```bash
python3 analyzer.py extension
```

## 4. Chrome Web Store Publishing

1. Log in to the Chrome Developer Dashboard with `dtu.course.analyzer@gmail.com`.
2. Make sure the course data is updated on the main Chrome release branch by running the full scrape and update workflow. The scrape usually takes about 90 minutes.
3. Bump the version number in `extension/manifest.json`.
4. Update the Chrome Web Store release notes in `docs/CHROME_WEB_STORE_RELEASE_NOTES.md`.
5. Zip the contents of the `extension` folder, not the folder itself:
   ```bash
   cd extension
   zip -r ../dtu-course-analyzer-vX.Y.Z.zip .
   ```
6. Upload the ZIP under "Pakker".
7. Publish it and wait for Chrome Web Store approval.
