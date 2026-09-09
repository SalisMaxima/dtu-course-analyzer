# Build once, review, then promote

## Collect and test

1. Push these changes. The new **Promote Course Data** workflow must also exist
   on the repository's default branch to appear as a manually runnable workflow.
2. Run **Update Course Data** on the branch you intend to update. It is now
   candidate-only: there is no publish checkbox and it cannot commit data.
3. Download **course-data-candidate**. It contains `extension/`,
   `validation.json`, `provenance.json`, and the exact collected checker baselines
   in `data/coursenumbers.txt` and `data/coursedic.json`. Collection evidence is a separate
   **exam-classification-report** artifact. Both request 30-day retention.
4. Check the reports and load the candidate's `extension/` directory in Chrome.
   Do not promote a failed run or a report with `publishable: false`.
5. Save the **Run ID** and **Artifact ID** from the successful run's summary.
   The run ID also appears in `/actions/runs/123...`; the artifact ID appears
   in the artifact link `/artifacts/456...`. These are numeric IDs, not names.

## Promote the reviewed artifact

1. Open **Actions → Promote Course Data → Run workflow**.
2. Select the target branch (normally the same branch used for collection).
3. Enter the saved `run_id` and `artifact_id` and run the workflow.

Promotion downloads that exact artifact, verifies it, then commits
`extension/db/data.json`, `data/coursenumbers.txt`, and `data/coursedic.json`
together on the selected branch. All three files are copied byte-for-byte.
Advancing the checker baselines prevents already-collected courses and semesters
from being reported repeatedly as new. Promotion does not scrape, regenerate
percentiles, install archived extension code, or submit anything to the stores.

GitHub assigns immutable artifact IDs, so selecting an ID identifies the exact
build you reviewed. Existing artifacts are not overwritten by this workflow.
If a rerun encounters an artifact-name conflict, start a new workflow run rather
than deleting your reviewed artifact. Candidates from an earlier attempt of a
subsequently rerun workflow are rejected; select a new, successfully completed
run instead.

## Checks before promotion

- Source run is a successful manual **Update Course Data** run in this repository.
- Artifact has the selected ID, belongs to that run, has the expected name,
  and is not expired. Run attempt and source commit match its provenance.
- Dataset, both checker baselines, and validation checksums match; validation
  passed with no issues. Missing files reject the entire promotion.
- All three installed files still match their pre-scrape baselines. The two
  checker baseline hashes come from the source commit, not the working files
  already refreshed by the scraper.
- The candidate's source commit is an ancestor of the target branch.
- Tracked extension code, pipeline source, dependencies, and update/promotion
  workflows match the version used to build the candidate. Documentation-only
  commits do not invalidate it.
- The tracked worktree is clean before installation. A normal push rejects
  concurrent branch changes; no force push or branch-protection bypass is used.

If another dataset was published, code changed, or the artifact expired, collect
and review a fresh candidate. Cross-branch promotion requires the source commit
to have been merged into the target with compatible code and baseline; a squash
merge does not preserve that ancestry. Protected branches may reject the direct
commit; this workflow does not bypass their rules.

Provenance schema 2 contains repository, source commit, run ID/attempt, creation
time, per-file candidate and baseline SHA-256 hashes, validation SHA-256, and a
runtime code checksum. All files are verified and temporary writes prepared
before installation. A failed replacement is rolled back; all three files
become visible in GitHub in a single commit.
Checksums detect changes; authenticity relies on the verified GitHub run/artifact
origin. No code from the artifact is executed.

Older artifacts without schema-2 provenance and both baseline files cannot be
promoted by this workflow; create a fresh candidate. Thirty-day retention applies
to new uploads and remains subject to
repository/organization retention limits and manual artifact deletion.

GitHub references: [artifact download by ID and run](https://github.com/actions/download-artifact/tree/v4),
[artifact retention and immutable IDs](https://github.com/actions/upload-artifact/tree/v4),
[manually running workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
