# Signed course-data pipeline: independent design

Design recorded before implementation, 2026-09-14. Starting commit:
`962d9d197abf19284adea5e914bc276041cc231e`. PR #37 has not been
consulted during this implementation.

## Delivery boundary

This change implements the **data publication pipeline** requested on the
secure-updates branch: collect → validate → review → promote → sign → publish
→ verify. The browser updater is a dependent deliverable; publishing does not
close issue #30 or complete the entire secure-updates specification. Existing
extensions continue using their bundled data until that updater is released.

## Decisions

- Keep the existing authenticated collection and candidate checks. Promotion
  records a durable receipt in the same Git commit as the three approved files.
  Publication accepts a full promotion commit SHA, never an arbitrary JSON file
  or a mutable Actions artifact name. It rechecks source ancestry, parent
  baselines, approved bytes, runtime binding and the successful promotion run.
- Use GitHub Pages for static JSON: no database service or browser credentials
  are needed. A separate release-ledger branch retains immutable payloads,
  signed envelopes and provenance. Only an explicitly allowlisted `public/`
  tree is deployed; evidence stays outside the Pages artifact.
- Production is restricted to `SMKIDRaadet/dtu-course-analyzer`, `master`, and
  the protected `course-data-production` environment. The user's fork may
  publish staging using a separate `course-data-staging` environment and key.
  Both require explicit environment configuration. **The production hostname,
  actual approvers, key custodians and hosting retention practices have not
  been confirmed; production must remain disabled until they are recorded.**
- Use RSA-3072, RSASSA-PKCS1-v1_5 with SHA-256, SPKI DER public keys and PKCS8
  PEM private keys. Sign exact UTF-8 metadata bytes, carried as base64 in a
  bounded envelope. RSA has established Web Crypto interoperability; planned
  client minimums are Chrome 120 and Firefox 128. No custom cryptography.
- Contract/schema version 1; older clients must reject unknown versions and
  unsupported compatibility requirements. Schema 1 will remain available for
  the lifetime of the first updater release; migrations require reviewed code.
- Current payload: 4,458,318 bytes / 1,554 courses. Limits: 16 MiB payload,
  32 KiB envelope, 10,000 courses, 128 exams/course, bounded fields. Keep at
  most 900 MiB in a Pages tree, failing before the hosting limit; no automatic
  deletion of old releases. The future client should reserve space for two
  payloads in IndexedDB, not assume storage.local can fit them.
- Serialize all staging/production publication jobs repository-wide. Assign
  sequence from the durable ledger. Commit the release before deployment;
  retry by the same release-request identifier reuses the exact signed bytes.
  Retrying an older request cannot move the pointer behind a newer release.
- Rollback is an explicitly approved new request using an older promotion
  commit. It receives a new sequence. Collection time remains the original
  time; publication time does not make old data appear recently collected.
- Pages controls its response cache headers. Verification uses no-cache
  requests; clients must use cache revalidation for the pointer and verify
  digest/length for immutable payloads. Mixed generations fail safely.
- Protected environment approval is the publication approval. Preserve the
  GitHub approval history in the durable evidence alongside source run,
  artifact, attempt, validation digest, promotion commit and publication run.

## Trust and policy

Production consumers must embed reviewed public keys and a confirmed origin;
keys served by hosting are not trust roots. Staging keys are never production
keys. A signing-workflow compromise can authorize false data; signing cannot
prevent outages or withheld releases. Rotation/compromise recovery requires
an extension update removing revoked keys, followed by a higher sequence.

No extension permissions or privacy claims change in this pipeline-only
delivery because installed extensions do not make remote requests yet. The
client follow-up must provide explicit opt-in before any remote request,
bundled-only operation, local cache controls and an accurate disclosure that
the host receives IP addresses and request times. Actual provider log retention
must be established before enabling production downloads.

Official references checked during design:
- [Chrome's remote hosted code guidance](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code)
  distinguishes JSON data from executable code; this publisher emits JSON only.
- [Mozilla add-on policies](https://extensionworkshop.com/documentation/publish/add-on-policies/)
  must be rechecked when the client is submitted; no store approval is claimed.
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
  describe the Pages artifact, deployment environment and OIDC permissions.

## Verification and deferred comparison

Automate promotion-receipt checks, tampering, wrong origin, failed validation,
stale baselines, release retries, rollback sequences, key/signature failures,
URL/redirect and size limits, allowlist enforcement, and Python/Web Crypto
interoperability on the real payload. Keep existing regression tests.

Authenticated collection, protected staging publication, installed Chrome and
Firefox activation, consent, quotas and network inspection require external
configuration and the browser updater. Record these as incomplete; do not call
this a fully validated end-to-end baseline. The specification explicitly puts
comparison with #37 after the complete working baseline, so that comparison
remains deferred, with neither #30 nor #37 closed or modified.
