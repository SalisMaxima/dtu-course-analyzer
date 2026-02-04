# Release Checklist (Target v2.2.1)

## Phase 1: Master Branch (Chrome)

- [x] **Bump Version to 2.2.1**
    - [x] `extension/manifest.json`
    - [x] `pyproject.toml`
    - [x] `setup.py`
- [x] **Commit Changes**
    - `git commit -am "chore: bump version to 2.2.1"`
- [x] **Package Chrome Extension**
    - [x] Zip `extension/` directory -> `dtu-course-analyzer-chrome-v2.2.1.zip`

## Phase 2: Firefox Branch

- [x] **Switch and Sync**
    - [x] `git checkout firefox`
    - [x] `git merge master`
- [x] **Resolve Conflicts (Crucial)**
    - [x] Fix `extension/manifest.json` (Keep `browser_specific_settings` & `background.scripts`, but update `version`).
- [x] **Update Source Code Bundle**
    - [x] Copy root `src/`, `README.md`, `LICENSE`, `pyproject.toml`, `setup.py`, `requirements.txt` into `source-code/`.
    - [x] Ensure `source-code/extension/` matches `extension/`.
- [x] **Package Firefox Extension**
    - [x] Zip `extension/` directory -> `dtu-course-analyzer-firefox-v2.2.1.zip`
    - [x] Zip `source-code/` directory -> `dtu-course-analyzer-source-v2.2.1.zip`

## Phase 3: Finalize

- [ ] **Push Changes**
    - [ ] `git push origin master`
    - [ ] `git push origin firefox`
