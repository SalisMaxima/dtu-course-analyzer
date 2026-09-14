# Publish reviewed course data

The pipeline publishes signed, immutable JSON releases from an already
successful **Promote Course Data** commit. Collection, repository promotion
and public deployment have separate success states. No scrape occurs in
publication, verification, retry or rollback.

The publication pipeline is paired with the implemented [browser updater](course-data-client.md).
Existing installations need the reviewed 2.6.0 extension build, a configured
origin/trust root, optional host access and explicit consent before downloading.

## Required maintainer setup

The checked-in configuration deliberately has no active origin or trust roots.
Do the following before enabling either channel:

1. Merge the implementation into the repository's `master` branch. The manual
   publication workflow runs only from that branch. Collect a fresh candidate:
   existing artifacts predate the new runtime binding and durable receipt.
2. Use `SalisMaxima/dtu-course-analyzer` for staging and
   `SMKIDRaadet/dtu-course-analyzer` for production. These identities are checked
   in both the workflow and publisher. Production cannot run from a fork.
3. Confirm Pages ownership and its exact HTTPS base URL, including a trailing
   slash and any repository path. Commit it in
   `config/course-data-release.json` under the appropriate channel.
   **A Pages deployment replaces that repository's existing Pages site.**
   Use a dedicated hosting repository design if that site already serves
   something else; do not enable this workflow until ownership is resolved.
4. Configure Pages to use **GitHub Actions**. Restrict the `github-pages`
   deployment environment to `master`. The two channels use different
   repositories, so their Pages deployments and release histories are isolated.
5. Create `course-data-staging` / `course-data-production` environments as
   appropriate. Restrict them to `master`; require independent reviewer
   approval, prevent self-review and disable protection bypass. Record named
   approvers, backup administrators and recovery contacts in the team's
   operational records. The publisher also checks the API approval history;
   merely creating an unprotected environment will not authorize signing.
6. Generate separate RSA-3072 keys with exponent 65537 in the organisation's
   approved secret-management environment. Store the PKCS8 PEM private key
   only as the protected environment secret `COURSE_DATA_SIGNING_KEY`.
   Commit the SPKI DER public key, encoded as standard base64, in
   `trusted_keys`, and select its identifier in `signing_key_id`.
   Never upload a private key as an artifact, commit it, or paste it into logs.
7. Protect `master`, the workflow/configuration files and
   `course-data-releases-staging` / `course-data-releases-production`.
   Disallow force pushes/deletion of release histories. Permit the intended
   release job's normal fast-forward push without bypassing source-branch
   protection. The job will fail if repository rules do not permit that write.
8. Record actual provider logging/retention, key custodians, access recovery,
   endpoint ownership and release approvers before enabling production.
   These external decisions are not inferred by the implementation.
9. Finally set the environment variable
   `COURSE_DATA_PUBLICATION_ENABLED=true`. Complete the staging run and the
   browser-updater acceptance work before authorizing production rollout.

Private keys are made available only to the signing step of the protected
preparation job. Locked, hashed dependencies are installed beforehand.
Deployment uses a separate job with only Pages/OIDC permissions.
Untrusted PRs do not run this manual publication workflow.

## Publish and retry

1. Run **Update Course Data**, inspect the candidate and reports, then run
   **Promote Course Data** with the exact run and artifact IDs as described
   in [promotion instructions](promoting-course-data.md).
2. Wait for the promotion run to succeed. Copy its **publication commit SHA**
   from the summary. It must be in `master`'s history.
3. Run **Publish Course Data** on `master`, selecting the channel, full
   promotion SHA and a stable request ID such as `2026-09-reviewed-1`.
   Leave `rollback` off for a normal update.
4. The environment reviewer checks those inputs before approving the signing
   job. The job verifies the promotion receipt, source ancestry, parent
   baselines, runtime binding, validation bytes, candidate file hashes and
   successful promotion run/attempt.
5. The signed payload, metadata and approval evidence are committed to the
   channel's release-ledger branch. Only `public/current.json` and each
   `public/releases/<sequence>-<digest>/{data.json,release.json}` are exported.
   The explicit allowlist rejects extra files and symlinks.
6. Pages deploys the complete public tree in one artifact. A separate job
   fetches the fixed HTTPS pointer, payload and immutable envelope, requiring
   the expected exact pointer bytes, valid signature, length, digest and schema.
7. Only a successful **verify** job means publication succeeded. The final
   report explicitly distinguishes preparation, deployment and verification.

If upload, deployment or public verification fails, fix the failure and run
again with the **same request ID and promotion SHA**. The existing release
reuses its sequence, timestamp and signed bytes. It does not need the signing
key again, though protected approval and configuration are still required.
Retry remains possible after the original candidate artifact expires because
approved bytes and provenance were committed durably. The promotion workflow
run must remain available as successful GitHub evidence; do not delete it.

If a newer release has since been recorded, retrying an old request fails
instead of moving the current pointer backwards. Use the latest pending
request to finish deployment. Do not manually edit a release or its index.

GitHub's workflow concurrency serializes all publication jobs, including
deployment and verification. A normal Git push also rejects competing ledger
updates. GitHub may replace queued pending runs; rerun a cancelled request as
needed. Partial local preparation is disposable: nothing is public until
the ledger commit and deployment complete.

## Rollback and keys

For an approved content rollback, choose the earlier promotion SHA, a **new**
request ID and `rollback=true`; obtain environment approval again. The payload
is copied from that historical commit and receives a higher signed sequence.
Its collection time remains old. Existing validation and schema checks apply;
rollback never overrides them.

For routine key rotation, add the new public key to the reviewed publisher
configuration and the next reviewed extension package, distribute that
extension, then change the active signing-key ID/secret. The publisher retains
historical public keys to verify immutable archived releases. A production
client must trust only the keys deliberately included in its own package,
never keys downloaded from the host or the staging fixture.

On compromise: disable publication, revoke the secret and affected access,
audit durable receipts and deployment records, distribute an extension update
removing the compromised trust root, and publish a reviewed release with a new
key and a sequence above every previously accepted release. If the ledger
itself is compromised, recover its history from a trusted backup and establish
the highest used sequence before resuming. Do not reset the counter or delete
history to work around an error.

Keep all released payloads/evidence in Git and in the public Pages tree. The
900 MiB export cap deliberately fails before hosting capacity is exhausted.
Plan a reviewed archival/hosting migration before hitting it; the workflow
does not silently prune investigation or rollback evidence. Back up the
release branch and environment access independently.

## Local verification and reviewer material

The signing job targets Ubuntu x86_64 / CPython 3.12. The hashes in
`requirements-release.txt` lock its wheels, including transitive dependencies.
For ordinary development, `pip install -e ".[dev]"` includes release tests.

```sh
python -m pytest
npm ci --ignore-scripts
node --test tests/*.test.js
```

The executable contract is
`src/dtu_analyzer/scripts/course_data_contract.py`; see the
[release contract](course-data-release-contract.md) and the non-production
[interoperability sample](../tests/fixtures/course-data-release/README.md).
The test suite exercises exact-byte promotion/publication, signatures,
request idempotence, forward rollback, key rotation/revocation, schema attacks,
source URL restrictions, redirect rejection, bounded downloads and mixed
deployment failures. It includes a local simulated review → promotion →
publication → fetch-verification run. GitHub API evidence is simulated there;
this is not a live authenticated staging run.

Before declaring the full secure-updates feature fully validated, run authenticated staging
collection/review/promotion/publication and Chrome/Firefox activation; verify
real browser quotas and network behavior. Only then make the deferred
comparison with PR #37 under the branch's required methodology.
