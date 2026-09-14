# Independent implementation validation record

Recorded 2026-09-14 for `feature/secure-course-data-updates`.

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
