Sync code between master (Chrome) and firefox branches while preserving browser-specific manifest.json files.

## Arguments

$ARGUMENTS should be either:
- `to-firefox` — Update firefox branch with changes from master
- `to-master` — Update master branch with changes from firefox

## Branch Structure

- **master**: Chrome extension (Manifest V3 with Chrome-specific keys)
- **firefox**: Firefox extension (Manifest V3 with Firefox-specific keys like `browser_specific_settings`)

## Sync Process

### For `to-firefox`:

```bash
# 1. Ensure working directory is clean
git status --porcelain

# 2. Stash any uncommitted changes
git stash push -m "auto-stash before sync"

# 3. Checkout firefox branch
git checkout firefox

# 4. Save firefox manifest
cp extension/manifest.json /tmp/firefox-manifest.json

# 5. Merge master (prefer master for conflicts except manifest)
git merge master --no-commit --no-ff || true

# 6. Restore firefox manifest
cp /tmp/firefox-manifest.json extension/manifest.json

# 7. Stage all changes
git add -A

# 8. Check if there are changes to commit
git diff --cached --quiet || git commit -m "sync: merge master into firefox (preserve firefox manifest)"

# 9. Return to master
git checkout master

# 10. Pop stash if exists
git stash pop || true
```

### For `to-master`:

```bash
# 1. Ensure working directory is clean
git status --porcelain

# 2. Stash any uncommitted changes
git stash push -m "auto-stash before sync"

# 3. Stay on master (or checkout master)
git checkout master

# 4. Save master manifest
cp extension/manifest.json /tmp/master-manifest.json

# 5. Merge firefox (prefer firefox for conflicts except manifest)
git merge firefox --no-commit --no-ff || true

# 6. Restore master manifest
cp /tmp/master-manifest.json extension/manifest.json

# 7. Stage all changes
git add -A

# 8. Check if there are changes to commit
git diff --cached --quiet || git commit -m "sync: merge firefox into master (preserve chrome manifest)"

# 9. Pop stash if exists
git stash pop || true
```

## Important Notes

- Always run `git status` first and show the user what will happen
- If there are merge conflicts in files OTHER than manifest.json, stop and ask user how to resolve
- After sync, remind user to test on the target browser
- The manifest.json is NEVER merged — always preserved from target branch

## Manifest Differences to Preserve

**Chrome (master) manifest.json may have:**
- `background.service_worker`
- Chrome-specific permissions

**Firefox manifest.json may have:**
- `browser_specific_settings.gecko.id`
- `background.scripts` (if using background scripts instead of service worker)
- Firefox-specific permissions

## Post-Sync Checklist

1. [ ] Run `/project:preflight` to validate
2. [ ] Test on target browser
3. [ ] Push branch: `git push origin <branch>`
