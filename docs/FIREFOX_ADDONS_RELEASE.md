# Firefox Add-ons Release

Firefox releases are prepared from the `firefox` branch. The scrape and update workflow does not automatically propagate data from `master` to `firefox`; after updating course data on the main Chrome release branch, mirror the generated data and documentation to `firefox` while preserving the Firefox-specific manifest.

## Checklist

1. Check out and update the Firefox branch:
   ```bash
   git checkout firefox
   git pull --ff-only origin firefox
   ```
2. Make sure the generated data files match the current release data from `master`:
   - `extension/db/data.js`
   - `extension/db.html`
   - `extension/js/init_table.js`
   - matching files under `source-code/extension/`
3. Confirm `extension/manifest.json` keeps the Firefox-specific fields:
   - `background.scripts`
   - `browser_specific_settings.gecko`
4. Bump the version number in `extension/manifest.json` and `source-code/extension/manifest.json`.
5. Update the release notes/listing text for the new version.
6. Build the Firefox extension package by zipping the contents of `extension/`, not the folder itself:
   ```bash
   cd extension
   zip -r ../dtu-course-analyzer-firefox-vX.Y.Z.zip .
   ```
7. Build the source-code package for AMO review:
   ```bash
   cd source-code
   zip -r ../dtu-course-analyzer-firefox-source-vX.Y.Z.zip .
   ```
8. Submit the extension ZIP on addons.mozilla.org.
9. When AMO asks whether source code is required, upload the source-code ZIP. Mozilla requires source code when reviewers need human-readable code and build instructions for generated, minified, bundled, or otherwise machine-generated files.
10. Add reviewer notes:
    - Test URL: `http://kurser.dtu.dk/course/01005`
    - No account is needed for normal extension behavior.
    - The extension uses a static bundled dataset and does not send analytics.
    - Build instructions are in `build.md` inside the source-code package.
11. Publish the new version and wait for AMO approval.

## References

- https://extensionworkshop.com/documentation/publish/submitting-an-add-on/
- https://extensionworkshop.com/documentation/publish/source-code-submission/
- https://extensionworkshop.com/documentation/publish/add-on-policies/
