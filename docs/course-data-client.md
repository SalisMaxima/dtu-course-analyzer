# Browser updater, builds and reviewer checks

The 2.6.0 implementation uses one background data provider for the course page,
database and comparison views. Chrome runs a service worker; the Firefox build
loads the same modules in its nonpersistent background page. Existing Firefox
identity `dtu.course.analyzer@gmail.com` is preserved. Staging has a separate ID.

## Build

The source `extension/` directory works offline with downloads disabled.
Reproducible browser packages are copied from that current source:

```sh
python -m pip install -e ".[dev]"
python -m dtu_analyzer.scripts.build_browser_extension --browser chrome --output dist/chrome
python -m dtu_analyzer.scripts.build_browser_extension --browser firefox --output dist/firefox
```

To enable remote downloads, first complete the confirmed origin/public-key
configuration in [publication setup](publishing-course-data.md), then add
`--enable-remote`. Use `--channel staging` for a staging build. No private key
is needed or included in extension builds. The build adds optional permission
for that single HTTPS host; the client pins the exact path prefix in packaged
configuration. Arbitrary URL inputs from course pages are never accepted.

By default the client package trusts only the configured active signing key.
For a reviewed rotation overlap, set `client_key_ids` in the channel configuration
to the explicit public-key IDs to include. Historical public keys may remain in
the publisher's `trusted_keys` to verify its ledger without being trusted by a
new client build. Remove compromised IDs from `client_key_ids` and distribute
a reviewed extension update. Staging and production may not share public keys.

Browser minimums are Chrome 120 and Firefox 128. The package version is 2.6.0.
The client checks the installed extension version against signed compatibility
metadata; the manifests enforce browser minimums. Existing archived
`source-code/extension/` builds are not used by this packaging command.

## Consent and requests

A new installation or upgrade from the previous disclosure starts with both
download consent and automatic checks disabled. Consent revision 2 is persisted;
later code-only upgrades retain this consent. Configured builds show the database
consent page on installation or upgrade when current consent is absent. That focused page explains the host, transmitted
network metadata and the continued availability of bundled-only use.

Opting in requests the configured host permission directly from the user's gesture.
Firefox builds declare `required: ["none"]`: no transmitted data is required to
use the bundled features. Remote-enabled builds additionally declare optional
`personallyIdentifyingInfo` for connection metadata linked to the requester's IP
address. Offline builds declare no optional data category. There is no technical
telemetry or analytics permission, and downloads never depend on an analytics
choice. This categorization applies Mozilla's guidance that technical information
linked to identifying information needs personal-data consent; it is an
implementation judgment, not a Mozilla determination about this specific host.
See [Mozilla's classification guidance](https://extensionworkshop.com/documentation/develop/best-practices-for-collecting-user-data-consents/#know-your-privacy-settings).

Where Firefox exposes its built-in `data_collection` permission API, the UI
requests personal-data consent together with optional host access. The background
checks actual host access and data consent before every remote request, including
after restart. Firefox 128–139 uses the explicit custom opt-in. Revoking host/data
permission aborts active work and disables downloads. Legacy disclosure consent
is invalidated even on those older versions. Confirm the host's actual practices
and explain this classification to Mozilla during review; no approval is claimed.

Policy sources checked 2026-09-14:
[Mozilla's built-in consent](https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/)
and [add-on consent requirements](https://extensionworkshop.com/documentation/publish/add-on-policies/#62-user-consent-and-control).
GitHub's documented Pages IP logging and its purpose-based retention statement
are linked in the updated [privacy policy](PrivacyPolicy.md). No fixed security-log
retention duration is invented.

Only two URLs are requested by an eligible client: the fixed `current.json`
pointer and its authenticated immutable dataset path. They contain no course
IDs or user selections. Fetch omits credentials/referrers, rejects redirects,
revalidates caches, times out each transfer after 30 seconds and bounds actual
streamed/decompressed bytes to 32 KiB metadata and 16 MiB payload.

Automatic checks are at least 24 hours apart, with up to one hour of jitter.
One-shot alarms and persisted timing survive sleep/restarts. Manual checks can
bypass the daily interval but use a five-minute minimum cooldown, increasing
to at most one hour after repeated failures. Failures do not trigger rapid
automatic retries. There is one in-flight operation per background instance.

## Verification, storage and rendering

The client verifies the exact signed metadata bytes with Web Crypto RSA/SHA-256
before trusting paths, lengths, versions or timestamps. The highest accepted
sequence, payload digest and envelope digest are committed with activation.
Older remote sequences and same-sequence metadata changes are rejected.
A same-sequence download is allowed only to recover the exact authenticated
release after cache loss/corruption. Controlled rollback requires a new signed
sequence, as in the publication pipeline.

The full dataset is validated before staging and activation. Schema 1 validates
finite values, ranges, identifiers, categories, suppression, source links,
reviewed identities, default-result relationships and bounded strings/arrays.
The parser rejects duplicate/prototype keys and bounds nesting before native
JSON parsing. Reviewed history policy is generated from the Python mappings;
tests prevent the packaged copy drifting from those mappings.

IndexedDB stores an active release, one previous release and at most one staged
candidate. One transaction stores authenticated bytes and changes the active
reference/high watermark. Incomplete candidates are never loaded. Cache reads
after a background restart revalidate signatures, hashes and schema. Corruption
falls back to the previous verified dataset and then the bundle. A quota or
transaction failure does not replace the working dataset. At the maximum size,
budget 64 MiB plus implementation overhead for committed/staged/transactional
copies; actual browser quota and responsiveness checks remain required.

Clearing downloaded payloads preserves the high watermark and preferences.
Bundled-only mode revokes local download consent and immediately uses the bundle.
Complete browser removal/reset of extension storage resets installation state.

Both manifests set `incognito: "not_allowed"`. The extension does not run in
private windows. Background handlers also reject private-tab comparison and
data-control messages, and notifications exclude private tabs. Supporting private
windows later requires a separate design that does not persist session activity.

Activation notifies extension pages and matching DTU content scripts. Each
render reads one complete generation; stale asynchronous refreshes are discarded.
Comparison selections absent from the new dataset remain visibly removable.
An explicitly selected exam is retained if still present, or replaced by the
“choose an exam” state and an explanation, never silently by a different exam.
Text is rendered through DOM text APIs, and grade-source links receive an
additional fixed-origin/path check.

## Automated checks and external acceptance

```sh
npm ci --ignore-scripts
npm test
npm run lint:firefox
python -m pytest
```

The JavaScript suite uses `fake-indexeddb` to exercise real transaction ordering
with the shipped storage class; it is not a measurement of browser quotas.
It tests restarts, concurrency, consent withdrawal, corrupt caches, incomplete
candidates, quota failures, offline operation, fixed private requests, signatures,
rollback and message boundaries. Both Python and JavaScript validate the real
4,458,318-byte dataset. The signed sample is verified across Python and Web Crypto.

Remaining installed-browser/staging checks:

Mozilla's `addons-linter` 10.12.0 runs on both offline and remote-enabled Firefox
packages in CI. Both must have zero errors. It reports two compatibility warnings
for `data_collection_permissions`: desktop support starts at 140 and Android at
142, while the supported desktop minimum remains 128. These warnings are retained
and visible. Desktop 128–139 uses custom consent, as Mozilla's guidance permits;
Android distribution is not enabled (no `gecko_android` entry). The fallback still
needs installed-browser testing. Successful lint is not store approval.

1. Load the staging Chrome and Firefox builds with the actual staged trust root.
   Inspect initial/upgrade consent; confirm no remote requests before acceptance.
2. Collect, review, promote and publish a staging candidate through the protected
   Actions environments. Record run IDs, promotion/release commits and approval.
3. Opt in and activate it without changing extension version. Compare course,
   database and comparison generation/age; preserve and remove exam selections.
4. Inspect request headers/URLs, revoke host and Firefox data consent mid-transfer,
   stop/restart the background, go offline and simulate storage exhaustion.
5. Verify cache corruption, real-size quotas/responsiveness, a higher-sequence
   rollback, replacement keys and removal of a compromised trust root.
6. Only after this working baseline is validated, compare with PR #37 as specified
   in the branch requirements. Do not close #30 or claim store acceptance early.

Browser binary installation was attempted in this execution environment but the
Playwright CDN downloads timed out. Installed Chrome/Firefox tests and live
protected staging publication therefore remain explicitly unverified.

## Store submission disclosures

Prepare submissions from the generated browser packages, not the archived
`source-code/` copies. The following checklist does not change any live listing.

| Item | Required content or action |
| --- | --- |
| Purpose | Public DTU course statistics, course comparison and optional reviewed-data refreshes. |
| Local data | Course identifiers, searches, selected exams and comparisons stay local; comparison choices persist in browser storage. |
| Remote data | The fixed dataset host receives IP address, request time and browser-managed connection headers for delivery and security. No course-view URLs, queries, identifiers, credentials or cookies are added to download requests. |
| Choice | Downloads default off. Declining leaves bundled course statistics and comparison usable. Show manual/automatic controls and revocation behavior. |
| Permissions | `storage` saves comparisons; `alarms` schedules opted-in refreshes; DTU host access supports course pages; the one optional release host serves data. No private-window access. |
| Firefox declaration | Offline builds: required `none`. Configured builds: required `none` plus optional `personallyIdentifyingInfo` for IP-linked connection metadata. No technical analytics. Explain this inference and actual host logging to the reviewer. |
| Privacy URL | Publish a reachable policy matching `docs/PrivacyPolicy.md` and the packaged `privacy.html`; enter its URL in the store dashboard. |
| Chrome dashboard | Disclose handling of local user data as well as host-side connection metadata. Complete Privacy practices and Limited Use certification accurately; do not claim that local processing is exempt. |
| Reviewer access | Supply the configured staging package, fixed origin, public trust root, build instructions and recorded end-to-end run. Explain signature verification, bundled code and bundled-only operation. |

Before submission, verify consistency between the actual build, hosting practices,
listing, privacy page and dashboard answers. Do not promise a provider retention
period without evidence. Obtain reviewer clarification if the classification of
this deployment's connection metadata is disputed; a unit test cannot settle a
policy interpretation.

Sources checked 2026-09-14:
[Chrome data handling and disclosure](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq),
[Mozilla classification and consent](https://extensionworkshop.com/documentation/develop/best-practices-for-collecting-user-data-consents/),
[Mozilla manifest](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/browser_specific_settings),
[private-window manifest setting](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/incognito).
