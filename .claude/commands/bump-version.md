Bump version numbers across the DTU Course Analyzer project.

## Arguments

$ARGUMENTS should be the new version number (e.g., "2.2.1")

## Files to Update

1. `extension/manifest.json` — update `"version": "x.y.z"`
2. `setup.py` — update `version="x.y.z"`
3. `pyproject.toml` — update `version = "x.y.z"`
4. `CLAUDE.md` — update version in Project Overview section
5. `Safari extension/DTU Course Analyzer.xcodeproj/project.pbxproj` — update `MARKETING_VERSION` (appears multiple times)

## Steps

1. Read current versions from all files
2. Show diff preview of proposed changes
3. Apply changes after confirmation
4. Remind about firefox branch:
   - Update manifest.json on firefox branch separately
   - Update source-code/ folder on firefox branch
5. Suggest git commit message: `chore: bump version to x.y.z`

## Post-Bump Checklist

- [ ] Version updated in extension/manifest.json
- [ ] Version updated in setup.py
- [ ] Version updated in pyproject.toml
- [ ] Version updated in CLAUDE.md
- [ ] Version updated in Safari project.pbxproj
- [ ] Firefox branch manifest.json updated (use `/project:sync-branch to-firefox`)
- [ ] source-code/ folder updated on firefox branch
