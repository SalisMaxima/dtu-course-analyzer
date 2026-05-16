# Chrome Web Store Release

Chrome releases are prepared from the main Chrome release branch (`master`). The scrape and update workflow updates generated files in the working branch only; if Firefox also needs the new data, mirror the generated files to the `firefox` branch separately.

## Checklist

1. Check out and update the Chrome release branch:
   ```bash
   git checkout master
   git pull --ff-only origin master
   ```
2. Log in to the Chrome Developer Dashboard with `dtu.course.analyzer@gmail.com`.
3. Make sure the course data is updated on `master` by running the full scrape and update workflow. The scrape usually takes about 90 minutes.
4. Generate the extension files after the scrape:
   ```bash
   dtu-analyze extension
   ```
5. Confirm the generated files changed as expected:
   - `extension/db/data.js`
   - `extension/db.html`
   - `extension/js/init_table.js`
6. Bump the version number in `extension/manifest.json`. Keep the project version files in sync when preparing a tagged release:
   - `pyproject.toml`
   - `setup.py`
   - `README.md`
   - `CLAUDE.md`
7. Update the Chrome Web Store release notes in `docs/CHROME_WEB_STORE_RELEASE_NOTES.md`.
8. Build the Chrome extension package by zipping the contents of `extension/`, not the folder itself:
   ```bash
   cd extension
   zip -r ../dtu-course-analyzer-vX.Y.Z.zip .
   ```
9. In the Chrome Developer Dashboard, upload the ZIP under "Pakker".
10. Publish the new package and wait for Chrome Web Store approval.
11. If Firefox also needs the release data, update the `firefox` branch using `docs/FIREFOX_ADDONS_RELEASE.md`.
