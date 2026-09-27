# Independent implementation validation record

Recorded 2026-09-14 for `feature/secure-course-data-updates`.

## Pre-testing review — 2026-09-27

A review of the complete branch diff (publisher, workflows, client and documents)
before installed-browser and staging testing, starting from `3859fa4`. It found
and fixed the following; each fix has a regression test that fails on `3859fa4`.

| Finding | Effect | Change |
| --- | --- | --- |
| Every background start and privileged status/settings message re-created the one-shot alarm at now + 60 s | A due automatic check could be postponed repeatedly; reproduced in Chromium | A pending alarm is kept unless it is later than the persisted due time |
| The consent page reopened on every extension update for users who had declined | Repeated unsolicited tabs | Prompt only until a choice is recorded under the current disclosure revision |
| A failed or abnormally closed IndexedDB connection was kept | Cache unusable until the background restarted | Reopen on next use |
| Refused cache writes lost their reason | "Course cache write failed" instead of the cancellation reason | Preserve the reason |
| Cancelled attempts counted as host failures; error kept after opting out | Longer cooldown; "update unavailable" shown in bundled-only mode | Superseded attempts are not failures; opting out clears the error |
| One message covered every skipped check | "Downloads are disabled or the next check is not due yet" during a manual cooldown | Specific reasons, including the remaining cooldown |
| Post-deployment verification failed on the first stale pointer | Hosting cache lag would fail a publication and require a re-approved rerun | Up to six complete checks, 30 seconds apart |

| Check | Result |
| --- | --- |
| Python suite, CPython 3.12.3 (CI version) | 345 passed |
| JavaScript suite, Node 20.20.2 (CI major) and 22.22.2 | 58 passed |
| Mozilla addons-linter 10.12.0, offline and remote-enabled Firefox packages | 0 errors; the same 2 compatibility warnings |
| actionlint 1.7.7, promotion/publication/test workflows | Passed |
| Pinned action commits | Match the tags in their comments: checkout v4.4.0, setup-python v5.6.0, github-script v7.1.0, download-artifact v4.3.0, upload-artifact v4.6.2, deploy-pages v4.0.5 |
| Locked signing dependencies | Install with `--require-hashes` on CPython 3.12 x86_64; publication and promotion import no scraper dependencies |
| Publisher `export` and `verify` commands | Exported the allowlisted tree and verified a local HTTPS host |

A local Chromium 141 run (Playwright, headless) used a throwaway staging
RSA-3072 key, a local HTTPS release host and a stand-in DTU course page:

- As built, the consent page opened on installation, no dataset request was made
  before consent, and course and database pages used bundled data. Automation
  cannot answer the host-permission prompt.
- With host access pre-granted, opting in made no request. A manual check
  activated release 1 using only `current.json` and its immutable payload, without
  cookie, referrer or authorization headers.
- Release 2 (one course renamed, one removed) refreshed the database and an open
  course page to the same generation. The removed course stayed visible in the
  comparison as not in this dataset, and an explicitly selected exam was kept.
- A tampered payload, HTTP 500 and a redirect kept release 2. An older signed
  pointer was rejected. Clearing fell back to bundled data with the high watermark
  kept, then recovered the same sequence. A cold restart revalidated the cached
  release, and bundled-only mode applied immediately.
- In automatic mode a due alarm activated release 4 within 30 seconds and re-armed
  about a day ahead. Before the fix, it did not fire while status requests continued.
- Bumping the extension version (an update) did not reopen the consent page after
  a recorded refusal; an older disclosure revision reopened it.

Not covered: installed Firefox (Mozilla download hosts are blocked in this
environment), real permission prompts, browser quotas, live protected staging
publication and store review. The outstanding acceptance work below still applies.

## Browser compliance fixes — 2026-09-14

The follow-up to the preserved baseline below corrects the Firefox manifest,
disables private-window support in both browsers, rejects private-tab messages,
and replaces the technical-telemetry download dependency with explicit personal
data consent for IP-linked connection metadata. Consent revision 2 invalidates
the old disclosure while preserving release high watermarks. Downloads check
actual host access and, where supported, native data consent before each request.
Permission revocation disables downloads; unrelated telemetry permissions do not.

Validation after these changes:

| Check | Result |
| --- | --- |
| Full Python suite | 344 passed in 16.44 seconds |
| Full JavaScript suite | 53 passed, including permission refusal/revocation, old-consent invalidation and private-window write rejection |
| Mozilla addons-linter 10.12.0, offline Firefox package | 0 errors; 2 compatibility warnings |
| Mozilla addons-linter 10.12.0, remote-enabled Firefox package | 0 errors; 2 compatibility warnings |
| Updated workflow | actionlint passed |

The linter reproduced the previous empty `required` list error. Corrected builds
use `required: ["none"]`; remote-enabled builds add optional
`personallyIdentifyingInfo`. The pinned validator and its lockfile are now part of
the test workflow (`npm run lint:firefox`). Public fixture keys let CI check the
remote-enabled package without secrets or deployment.

The two warnings concern the minimum version for the native data-consent key:
desktop 140 and Android 142. Desktop support remains 128 with explicit custom
consent below 140; Android distribution is not enabled. The warnings are not
suppressed. See the [client and store checklist](course-data-client.md) for the
classification rationale, disclosures and minimum-version testing.

These checks do not establish installed-browser behavior or store acceptance.
The IP-linked classification is a documented application of Mozilla's guidance,
not a ruling from its reviewers. Confirm actual hosting practices and explain the
classification during submission. The live staging and browser checks below,
and the subsequent PR #37 comparison, remain outstanding.

## Preserved baseline

- Publication implementation: [`872202ddbeb9c59bbea246716bf403eb7e1182d7`](https://github.com/SalisMaxima/dtu-course-analyzer/commit/872202ddbeb9c59bbea246716bf403eb7e1182d7).
- Complete publication and browser-client implementation: [`53a9ee0dab1bf069ec01d78c05d2550e3e052bb0`](https://github.com/SalisMaxima/dtu-course-analyzer/commit/53a9ee0dab1bf069ec01d78c05d2550e3e052bb0).
- Tested implementation tree: `b89c8d7d12587c25a875b6d801a24a8b5d2a253b`.
  The local staged tree and GitHub tree matched exactly. This record is a
  documentation-only addition after that checkpoint.

The design, publisher and client were developed from this branch's requirements
and existing code. PR #37 was not consulted during this implementation phase.
The requirements acknowledge an earlier discussion of that PR; this is not a
clean-room claim. Comparison remains deferred until the outstanding acceptance
checks are complete.

## Completed checks

| Check | Result |
| --- | --- |
| Full Python suite, `python -m pytest` | 344 passed in 15.88 seconds |
| Full JavaScript suite, `npm test` | 46 passed |
| Workflow lint, actionlint 1.7.7 | Promotion, publication and test workflows passed |
| JavaScript syntax checks | All new `data-*.js` modules passed |
| Patch whitespace check | `git diff --cached --check` passed |
| Current bundled dataset | All 1,554 courses / 4,458,318 bytes passed Python and JavaScript contracts |
| Signing-only installation | Locked release dependencies installed and exercised independently of scraper dependencies |
| Browser packages | Chrome/Firefox build tests passed; installed-browser execution is outstanding |

These are local automated results, not a claim of successful GitHub Actions or
live deployment. JavaScript ran on Node 24.19.0. Workflow CI selects Node 20.

Publisher tests cover promotion provenance and ancestry, exact reviewed bytes,
approval evidence, immutable release sequences, signatures, key rotation and
revocation, rollback, retry behavior, public-export allowlisting and bounded
HTTPS transport. An isolated local Git repository exercises the complete
promotion/publication path with simulated workflow/approval responses.

Client tests exercise the shipped IndexedDB cache against `fake-indexeddb`,
including atomic activation, cold restarts, interrupted staging, concurrent
consent changes, quota failures, cache corruption, offline fallback, request
limits, message privileges and rollback/replay rejection. They activate and
reload the real-size dataset. A public test vector confirms Python signing and
browser Web Crypto verification agree. The fixture contains no private key and
is not a deployable promotion receipt.

## Outstanding external acceptance

This baseline is **not fully validated**. No live protected staging publication,
installed Chrome/Firefox run, production deployment or store submission was
performed.

1. **Staging infrastructure:** the checked-in origin and signing-key settings
   remain unset. Endpoint ownership, separate staging/production keys,
   independent environment reviewers, protected branches and Pages settings
   must be configured through the [release runbook](publishing-course-data.md).
   Fresh collection and promotion are required to produce the new receipt.
2. **Installed browsers:** no installed Chrome/Firefox binary was available.
   `python -m playwright install chromium firefox` was attempted, but downloads
   from the Playwright CDN timed out. Automated IndexedDB tests do not establish
   real browser quotas, background suspension behavior, permission UI or render
   responsiveness. Complete the [browser acceptance checklist](course-data-client.md#automated-checks-and-external-acceptance)
   and record browser versions, results and supporting evidence.
3. **End-to-end evidence:** record actual collection, promotion and publication
   run IDs, immutable commits, approval evidence, downloaded release identity,
   cross-view activation and controlled rollback in staging.
4. **Deferred comparison:** once the above baseline is ready, compare the
   then-current description, diff and discussion of upstream PR #37, record
   evidence-based differences and validate any resulting changes.

Downloads remain disabled in default extension builds. Production publication
remains gated by repository identity, explicit configuration and the protected
environment enable switch. Issue #30 remains open; no store-policy approval or
provider log-retention duration is implied by this implementation.
