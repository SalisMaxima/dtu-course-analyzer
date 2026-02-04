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

- [ ] **Switch and Sync**
    - [ ] `git checkout firefox`
    - [ ] `git merge master`
- [ ] **Resolve Conflicts (Crucial)**
    - [ ] Fix `extension/manifest.json` (Keep `browser_specific_settings` & `background.scripts`, but update `version`).
- [ ] **Update Source Code Bundle**
    - [ ] Copy root `src/`, `README.md`, `LICENSE`, `pyproject.toml`, `setup.py`, `requirements.txt` into `source-code/`.
    - [ ] Ensure `source-code/extension/` matches `extension/`.
- [ ] **Package Firefox Extension**
    - [ ] Zip `extension/` directory -> `dtu-course-analyzer-firefox-v2.2.1.zip`
    - [ ] Zip `source-code/` directory -> `dtu-course-analyzer-source-v2.2.1.zip`

## Phase 3: Finalize

- [ ] **Push Changes**
    - [ ] `git push origin master`
    - [ ] `git push origin firefox`
