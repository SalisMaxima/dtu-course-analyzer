# Build once, review, then promote

## Collect and test

1. Push these changes. The new **Promote Course Data** workflow must also exist
   on the repository's default branch to appear as a manually runnable workflow.
2. Run **Update Course Data** on the branch you intend to update. It is now
   candidate-only: there is no publish checkbox and it cannot commit data.
3. Download **course-data-candidate**. It contains `extension/`,
   `validation.json`, and `provenance.json`. Collection evidence is a separate
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

Promotion downloads that exact artifact, verifies it, then commits only
`extension/db/data.json` to the selected branch. The dataset bytes are copied
unchanged; it does not scrape, regenerate percentiles, install archived extension
code, update raw scraping files, or submit anything to the browser stores.

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
- Dataset and validation checksums match; validation passed with no issues.
- The currently installed dataset still matches the collection baseline.
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

Provenance contains repository, source commit, run ID/attempt, creation time,
baseline SHA-256, dataset SHA-256, validation SHA-256, and a runtime code checksum.
Checksums detect changes; authenticity relies on the verified GitHub run/artifact
origin. No code from the artifact is executed.

Older artifacts created before provenance was added cannot be promoted by this
workflow. Thirty-day retention applies to new uploads and remains subject to
repository/organization retention limits and manual artifact deletion.

GitHub references: [artifact download by ID and run](https://github.com/actions/download-artifact/tree/v4),
[artifact retention and immutable IDs](https://github.com/actions/upload-artifact/tree/v4),
[manually running workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
