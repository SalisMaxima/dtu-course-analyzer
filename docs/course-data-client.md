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

A new or upgrading installation starts with both download consent and automatic
checks disabled. Configured builds show the database consent page on installation
or upgrade when no consent exists. That focused page explains the host, transmitted
network metadata and the continued availability of bundled-only use.

Opting in requests the configured host permission directly from the user's gesture.
Firefox builds declare optional `technicalAndInteraction` consent conservatively
for download-related network metadata. Where Firefox exposes its built-in
`data_collection` permission API, the UI requests that permission too and the
background checks it before every request. Firefox 128–139 uses the explicit
custom opt-in. Revoking host/data permission aborts active work and disables
downloads. This classification and disclosure must be reviewed against Mozilla's
then-current policy before store submission; no approval is claimed.

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
python -m pytest
```

The JavaScript suite uses `fake-indexeddb` to exercise real transaction ordering
with the shipped storage class; it is not a measurement of browser quotas.
It tests restarts, concurrency, consent withdrawal, corrupt caches, incomplete
candidates, quota failures, offline operation, fixed private requests, signatures,
rollback and message boundaries. Both Python and JavaScript validate the real
4,458,318-byte dataset. The signed sample is verified across Python and Web Crypto.

Remaining installed-browser/staging checks:

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
