Prepare and validate the DTU Course Analyzer extension for testing.

## Pre-flight Checks

1. **Validate `extension/manifest.json`**:
   - Check JSON syntax
   - Verify Manifest V3 compliance
   - Confirm host_permissions includes `*://kurser.dtu.dk/*`
   - Verify content_scripts matches pattern

2. **Check `extension/db/data.js`**:
   - Verify file exists and exports valid JavaScript object
   - Report number of courses in database

3. **Lint JavaScript files**:
   - `extension/js/language-toggle.js`
   - `extension/contentscript.js` (if exists)
   - `extension/background.js`
   - Check for `var` usage (should be const/let)
   - Check for `innerHTML` usage (security concern)

4. **Check DataTables configuration**:
   - Verify NO `bVisible: false` in column definitions
   - Confirm `hidden-col` CSS class is used instead
   - Check `bSearchable: true` on name columns

5. **Safari compatibility check**:
   - Verify no Chrome-specific APIs without fallbacks
   - Check `browser` vs `chrome` namespace usage

6. **Python package check**:
   - Verify `pip install -e .` was run
   - Check CLI tools available: `dtu-auth`, `dtu-scrape`, etc.

## Output

Report any issues found, or confirm "Ready for testing" with instructions:
- Chrome: `chrome://extensions/` → Developer mode → Load unpacked → select `extension/`
- Firefox: `cd extension && web-ext run`
- Safari: Open `Safari extension/DTU Course Analyzer.xcodeproj` in Xcode, ⌘R
