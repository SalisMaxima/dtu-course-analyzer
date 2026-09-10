# Secure course-data updates: implementation requirements

Status: planning document; the remote updater and hosting pipeline are not implemented by this branch yet.

Branch: `feature/secure-course-data-updates`

Proposed implementation PR title: **Fetch reviewed course-data updates securely without extension releases**

Related work:
- [Issue #30: Hosting updated data](https://github.com/SMKIDRaadet/dtu-course-analyzer/issues/30)
- [PR #37: comparison reference after independent implementation](https://github.com/SMKIDRaadet/dtu-course-analyzer/pull/37)
- [Existing collection and promotion workflow](promoting-course-data.md)

## Objective and scope

Installed Chrome and Firefox extensions should receive approved course-data
updates without requiring a store release for each dataset. The first release
must introduce the updater; changes to extension code, permissions, trusted
keys, or unsupported data formats still require an extension release.

The extension currently reads its bundled `extension/db/data.json`. Existing
workflows collect candidates, validate them, and promote the exact reviewed
artifact into the repository. Extend that process to publish approved public
datasets and securely activate them in the extension.

Develop the solution from issue #30's user need, this repository's current
architecture, and the security and acceptance requirements below. Reuse the
current authentication, collection, validation, and promotion logic. Publishing
alone is not completion of #30.

This work does not include user accounts, telemetry, syncing course selections,
live scraping from users' browsers, remote UI templates, or remotely supplied
code. Existing grade-selection and reviewed course-history rules must hold.

## Methodology: implement independently, then compare

The sequence is **our own design → working implementation → validation →
comparison with PR #37 → evidence-based refinements**.

PR #37 has already been read during initial discussion; this is not a claim of
an unseen or clean-room implementation. From this point, use it as a deferred
comparison reference, not as the implementation plan or starting code.

1. **Design from our requirements.** Inspect the current repository and relevant
   browser policies. Record our architecture, release contract, trust model,
   privacy decisions, alternatives, and reasons before implementation. Choose
   hosting and other components on their merits; matching a choice in #37 is
   acceptable when independently justified.
2. **Build the complete workflow ourselves.** Implement publication and client
   consumption against the current pipeline. Do not cherry-pick, port, or adapt
   #37 as the starting implementation, and do not consult its diff to guide
   this phase. Resolve questions through current code, requirements, tests,
   and official documentation.
3. **Validate and preserve a baseline.** Complete the applicable automated tests,
   manual Chrome/Firefox checks, and staging end-to-end run below. Record the
   implementation commit and test evidence before comparison. Production
   deployment and store approval are not prerequisites for this checkpoint.
   If an external dependency blocks a check, record it explicitly; do not label
   the baseline fully validated until the check can be completed.
4. **Compare with the proposed PR.** Only after the working baseline is ready,
   inspect the then-current #37 description, diff, and discussion. Record its
   exact head commit. Compare intended scope, authentication, collection,
   publication, hosting, client updates, security, operations, and testing.
   Distinguish what #37 implements from work it explicitly defers; an omitted
   future feature is not automatically a defect in that PR.
5. **Refine based on evidence.** For each useful difference, explain whether to
   adopt the idea, retain our approach, or defer it. Apply justified refinements
   in separate commits after the baseline and rerun affected checks. Attribute
   any subsequently reused contribution appropriately. Agreement with #37 is
   not an acceptance criterion; the user need and requirements remain the test.

Deliver a comparison note alongside the implementation containing both commit
references, baseline test evidence, a concise comparison table, decisions and
reasons, and any resulting changes. Use it to explain whether #37 is superseded,
still contributes useful work, or needs a separate follow-up. Do not close or
modify #37 merely as part of writing the comparison.

## Required end-to-end flow

1. Collect a candidate using the existing authenticated maintainer workflow.
2. Validate the complete candidate and review the reports and proposed changes.
3. Promote the identified artifact, retaining existing provenance, ancestry,
   baseline, and concurrent-update checks.
4. Package the exact approved public dataset, assign a release sequence, and
   sign release metadata in a protected publication job.
5. Deploy immutable release files and the current-release pointer together.
6. Verify the deployed files from their public HTTPS URLs.
7. Eligible clients check for updates, authenticate and validate the candidate,
   then activate it atomically. Failure keeps the previous working dataset.

Collection, publication, and client activation are separate states. A failed
deployment must be reported as a publication failure even if repository
promotion succeeded. Retrying publication must not scrape or regenerate data.

## Public hosting and release format

- Use an organisation-controlled HTTPS origin. GitHub Pages is an appropriate
  initial hosting option; a database server is not required for static JSON.
  Confirm the final production origin before adding permissions or releasing.
- Publish only the extension's approved public dataset and release metadata.
  Use an explicit file allowlist. Never publish credentials, cookies, raw
  authentication responses, diagnostic reports, or the entire Actions artifact.
- Keep the dataset as JSON, with all rendering and behavioural logic packaged
  inside the extension. Do not host `data.js` as the update payload.
- Define and document a versioned release contract. Signed metadata must bind
  the dataset identifier/path, schema version, monotonically increasing release
  sequence, publication and collection timestamps, byte length, SHA-256 digest,
  compatibility requirements, and signing-key identifier.
- Give each dataset an immutable path containing its release ID or digest.
  Keep prior releases available for investigation and controlled rollback.
  Define cache headers and pointer revalidation so clients can discover updates.
- Publish the pointer only with an available, complete payload. A reader seeing
  mixed deployment generations must safely reject or retry, never activate a
  partial update. Run a post-deployment fetch and verification smoke check.
- Retain provenance mapping each release to repository commit, source workflow,
  run attempt, artifact ID, validation result, and maintainer approval. Store
  evidence durably beyond temporary Actions artifact retention.

## Authentication and integrity

Require signed releases for the production rollout. HTTPS and checksums alone
do not authenticate a dataset if an attacker can replace both the payload and
its checksum on the hosting account.

- Embed trusted public keys in the reviewed extension package. Verify metadata
  signatures before trusting its payload location, version, or size fields.
- Sign precisely specified bytes. For example, distribute a bounded signed
  envelope containing the exact metadata bytes and detached signature; verify
  those bytes before parsing metadata. Do not depend on unspecified JSON
  reserialization or property ordering.
- Choose a standard signature algorithm supported by the declared minimum
  Chrome and Firefox versions. Document key encoding, algorithm, signing input,
  verification procedure, and interoperability test vectors. Use established
  browser cryptography rather than custom cryptographic implementations.
- Keep the private key outside public hosting, source code, build artifacts,
  and logs. Grant access only to the protected release job after approval.
  Untrusted PRs and fork workflows must never receive signing or deploy secrets.
- Pin the allowed origin and path prefix in client code. Resolve payload paths
  strictly and reject unexpected origins, redirects, or protocols. Messages
  from course pages must not turn the background process into an arbitrary
  URL-fetching proxy.
- Verify the downloaded payload's exact byte length and digest before parsing.
  A signature establishes origin, not correctness; schema and content validation
  are still mandatory.
- Persist the highest accepted release sequence and reject older remote releases.
  A controlled rollback republishes an approved older dataset under a new signed
  sequence. Do not introduce a remotely activated bypass for version checks.
- Document key rotation and compromise recovery. New trust roots require a
  reviewed extension update unless an explicitly reviewed rotation mechanism
  is implemented. Do not trust keys simply because hosting serves them.
- Acknowledge residual risks: compromise of the signing workflow can authorize
  false data; signatures do not prevent hosting outages or withholding updates.
  Show data age and retain a safe offline fallback.

## Client download and activation

- Implement a shared data provider for course pages, the database, and comparison
  views. Chrome service-worker and Firefox background lifecycles must both work.
- Make update requests from the extension background context to the fixed
  endpoint. Request only the host access and browser APIs actually needed.
- Fetch the same public dataset for all users. Omit credentials and referrers;
  never append viewed course IDs, selected exams, searches, browsing URLs,
  comparison lists, DTU credentials, or installation identifiers.
- Check at most once per 24 hours automatically, with jitter, persisted timing,
  bounded retry/backoff, and a single in-flight operation. A manual check may
  bypass the daily interval but must still avoid request storms.
- Account for sleeping browsers, background termination, offline mode, denied
  host permission, storage errors, and interrupted downloads. No continuous
  polling or requirement that the browser remain running.
- Set explicit timeouts and byte limits for metadata and payloads, including
  actual streamed/decompressed bytes. Select and document limits using the
  current dataset size plus reasonable growth headroom before implementation
  is accepted. Do not trust `Content-Length` alone.
- Validate schema version, types, finite numeric values, semantic ranges,
  course IDs, bounded text/array lengths, and relationships between fields.
  Reject incompatible or malformed datasets without partially importing them.
  Handle object keys safely, including prototype-related keys.
- Preserve the existing publication guards, suppressed-grade representation,
  approved historical identities, default-exam semantics, and feedback/grade
  distinctions. Schema migrations must not fabricate missing values.
- Store the candidate separately, validate fully, and atomically change the
  active-dataset reference. Keep a bounded last-known-good cache and the bundled
  fallback. Test the chosen storage mechanism against real payload sizes and
  browser quotas; do not assume `storage.local` capacity is sufficient.
- Store the accepted payload with its authenticated metadata. Revalidate cached
  data as appropriate on load and reject corruption. Clear-cache recovery must
  still leave a working bundled dataset.
- Notify all data consumers after activation. Each render/comparison must use
  one consistent dataset generation. Clear stale memoized data and reconcile
  selections that no longer exist without silently substituting another exam.
- Distinguish dataset version and age from extension version. Show last
  successful refresh and a concise stale/offline status when useful. A failed
  update must not imply that old bundled data is current.

## Safe rendering and permissions

- Treat every remote field as untrusted even after signature verification.
  Render text through safe DOM APIs such as `textContent`; do not insert remote
  content through `innerHTML`, executable templates, script tags, `eval`, or
  `Function` constructors.
- Derive course links from validated IDs and fixed trusted destinations. If a
  data field contains a source URL, validate its scheme, origin, and intended
  path before making it clickable. Reject executable and unexpected URLs.
- Remote records must never select executable modules, supply expressions,
  change permissions, weaken CSP, or configure arbitrary network destinations.
- Keep a restrictive extension CSP and narrowly scoped host permissions. Check
  every renderer consuming the shared dataset, including Firefox, not just the
  Chrome course-page content script.

## Privacy and store review

- Update the privacy policy, store listings, permission explanations, and
  reviewer notes to accurately describe remote dataset checks and local caching.
  The current all-local description cannot remain unchanged.
- Explain that the hosting provider necessarily receives network metadata such
  as IP addresses and request times, and document actual logging and retention
  practices. Do not claim that downloads transmit no information whatsoever.
- Provide a clear control for automatic downloads and continued use of bundled
  data. Meet applicable Mozilla disclosure and consent requirements for both
  new and upgrading users and the supported Firefox versions before any
  transmission requiring consent begins. Resolve data classification against
  current policy rather than assuming a permission prompt is sufficient.
- Document that external JSON supplies records only; all functionality is
  inspectable in the submitted extension. Provide a sample signed release,
  schema documentation, reproducible build instructions, and reviewer test steps.
- Recheck store policies before submission. This design supports compliance;
  it does not guarantee acceptance by either store.

Policy references checked during planning (2026-09-10):
- [Chrome Manifest V3 requirements](https://developer.chrome.com/docs/webstore/program-policies/mv3-requirements/)
- [Chrome remote hosted code guidance](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code)
- [Mozilla add-on policies](https://extensionworkshop.com/documentation/publish/add-on-policies/)

## Publication controls and operations

- Restrict production publication to the intended organisation/repository and
  approved branch/environment. Forks and ordinary PR checks may produce test
  artifacts but must not publish or sign production releases.
- Use minimum job permissions, protected secrets, deployment concurrency, and
  immutable action revisions for jobs handling signing or publication. Never
  execute untrusted PR code with those privileges or bypass branch protection.
- Preserve the current separation between collection and human-reviewed
  promotion. Any later scheduling must not make unreviewed data public.
- Serialize release-sequence assignment and publication. Retries must be
  idempotent; concurrent jobs must not overwrite a newer pointer with an older
  release. Deployment success must be observable in the workflow summary.
- Document endpoint ownership, access recovery, signing-key custody, release
  retention, schema support windows, publication retry, rollback, and incident
  response. Publication must be possible without exposing credentials locally.
- Keep a staging endpoint and test signing key isolated from production.
  Production clients must reject staging signatures.

## Required verification and acceptance criteria

The independent implementation baseline must supply automated coverage and
manual browser evidence for the following behaviours before comparison with
PR #37. Any refinements following comparison must retain these guarantees:

- A reviewed candidate is published byte-for-byte, including digest/provenance
  checks. Unreviewed, mismatched, expired, or wrong-repository artifacts fail.
- Chrome and Firefox can activate a valid signed update without changing the
  installed extension version, and all views agree on the active generation.
- Tampered payloads/metadata, wrong signatures, unknown keys, older release
  sequences, incompatible schemas, and unsupported compatibility requirements
  fail without replacing working data.
- Malicious text, links, object keys, oversized responses, invalid numeric data,
  and malformed JSON cannot execute code, trigger arbitrary requests, or cause
  unbounded processing/storage use.
- Offline operation, HTTP failures, redirect attempts, interrupted downloads,
  service-worker restarts, storage exhaustion, cache corruption, partial hosting
  deployments, and simultaneous checks preserve a working fallback.
- A new signed release can deliberately roll back dataset content. Key rotation
  and compromised-key recovery are demonstrated using non-production keys.
- Network inspection shows only documented fixed-endpoint requests with no
  credentials, browsing details, course selections, or user identifiers.
- Download controls/consent work for new installations and upgrades, and all
  required permissions and disclosures match actual behaviour.
- Existing grade, history, comparison, and promotion regression checks pass.
  Test real dataset size and verify responsiveness and quotas in both browsers.
- A staging end-to-end run proves collection/review/promotion/publication/client
  activation. Production enablement requires the chosen endpoint, secret and
  environment configuration, and approved store release to be ready.

## Future PR description and delivery checklist

Suggested opening:

> Course data is currently bundled with each extension release, so installed
> users cannot receive refreshed results until the extension is updated. This
> change publishes approved, signed JSON datasets and lets Chrome and Firefox
> validate and cache updates independently, with the bundled dataset retained
> as an offline fallback. All executable code remains inside the extension.

The final PR must describe the implemented endpoint and trust model, publication
approval path, signature and schema formats, permissions and privacy changes,
fallback/rollback behaviour, browser compatibility, and concrete test evidence.
List any required maintainer setup separately from completed code. Include the
independent baseline commit and validation evidence, then link the comparison
note and explain any refinements made after reviewing #37. Close #30 as
implemented only when the full
publication-and-consumption path is delivered, not after planning or hosting
alone. If delivered in multiple PRs, make dependencies and remaining scope
explicit on each PR.

Before implementation, settle and record: production hostname, minimum browser
versions, signature algorithm, numeric download/storage limits, schema support
window, hosting log practices, consent approach, release approvers, and key
custodians. These decisions must be reflected in code, tests, and documentation.
