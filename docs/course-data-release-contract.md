# Course-data release contract v1

All public files are JSON data. The publisher does not generate JavaScript,
HTML, templates or remote configuration for extension functionality.

## Envelope and exact signing input

`current.json` and `releases/<sequence>-<sha256>/release.json` contain
**identical envelope bytes**:

```json
{"key_id":"production-2026-1","metadata":"BASE64_EXACT_UTF8_METADATA","signature":"BASE64_RSA_SIGNATURE"}
```

The signature is RSA-3072 / exponent 65537 / RSASSA-PKCS1-v1_5 with SHA-256
over the **base64-decoded metadata bytes**. The publisher emits compact,
sorted UTF-8 JSON with one trailing LF. Verifiers must authenticate the
original bytes, including that LF, before parsing metadata; they must not
reserialize it to verify the signature. The envelope is at most 32 KiB.

Public keys use base64-encoded DER SubjectPublicKeyInfo. Private keys use
PKCS8 PEM. Select a packaged trust root using the untrusted envelope key ID,
verify the signature, then require the signed metadata key ID to agree.
Unknown keys, invalid base64, duplicate/prototype-related JSON keys and
invalid UTF-8 are rejected.

## Authenticated metadata

| Field | Contract |
| --- | --- |
| `contract_version`, `schema_version` | Integer `1`; reject unsupported versions |
| `dataset` | Exactly `dtu-course-data` |
| `path` | Exactly `releases/<sequence>-<sha256>/data.json`, relative to the fixed base URL |
| `sequence` | Positive integer, at most JavaScript's `2^53-1` |
| `published_at` | Timezone-aware ISO 8601 time of the first packaging attempt |
| `collected_at` | Oldest contributing course-history collection time; never reset by retry or rollback |
| `byte_length` | Exact UTF-8 dataset byte count, 1 through 16 MiB |
| `sha256` | Lowercase hexadecimal SHA-256 of the exact dataset bytes |
| `compatibility` | Exactly `{"minimum_extension":"2.6.0","minimum_chrome":120,"minimum_firefox":128}` |
| `key_id` | Matches the envelope and a reviewed public key |
| `origin` | Exact configured HTTPS base URL and path prefix, ending in `/` |
| `channel` | `staging` or `production`; must match the client's trust domain |
| `evidence_sha256` | Digest of the durable release evidence stored outside the public tree |
| `promotion_commit` | Full 40-character Git commit SHA containing the approved dataset and receipt |
| `request_id` | Stable lowercase letter/digit/hyphen token, maximum 64 characters |

The compatibility floor matches the implemented 2.6.0 updater; the older 2.5.0
extension cannot consume these releases. The client compares its installed
extension version, uses manifest-enforced browser minimums and persists the
highest accepted sequence. The standalone signature verifier remains useful
for offline review but does not itself manage client activation.

Collection precedes publication. Publication times over five minutes in the
future are rejected. A new release's path includes its sequence and digest.
Rollback uses a higher sequence; never edit an earlier path or re-sign its
metadata in place.

## Dataset schema and semantics

The dataset is an object keyed by five-character uppercase letter/digit DTU
course IDs. At most 10,000 courses and 128 exams per course are accepted.
Strings are bounded to 4,096 characters; course collection timestamps are
timezone-aware. Unknown course/exam fields are rejected, as are duplicate
exam IDs and prototype-related keys.

The exact field allowlists are `COURSE_FIELDS`, `EXAM_FIELDS` and
`GRADE_KEYS` in `course_data_contract.py`. Required course fields are
`default_exam_id`, `exam_history` and `history_collected_at`.
Names and feedback fields remain optional when genuinely unavailable.

- Percentages and percentile metrics are finite numbers in [0,100].
  Numerical grade averages are in [-3,12], only for seven-point distributions.
  Participant/count fields are nonnegative integers bounded to 1,000,000.
  Legacy histogram counts may be digit strings; they are validated without
  modifying their representation or the released bytes.
- Published distributions retain the allowed numeric, binary, absent and sick
  categories. Participant differences must equal participant total minus
  category sum. Suppressed distributions must omit grade counts and result
  summaries; no zeroes or placeholder values are fabricated.
- Source URLs are fixed HTTPS `karakterer.dtu.dk/Histogram/...` paths. URL,
  course identity, season, period and year must agree. No arbitrary source
  origin, port, query, fragment, user information or executable scheme is
  permitted.
- Manually approved history and excluded history are checked against the
  repository's existing reviewed mappings. Unreviewed historical variants may
  remain visible in the data but cannot become the default.
- Default-exam summary fields must exactly match the selected history record.
  Existing reviewed predecessor preferences may select a historical exam
  with unknown regular/reexam classification; that explicit exception is
  preserved. With no default, default-derived grade fields must be absent.
- Content strings remain untrusted even after authentication. Client renderers
  use safe DOM APIs and fixed URL derivation, with a second source-link check.

This validator checks schema and consistency; collection completeness and
default-selection provenance remain governed by the existing publication
guard and reviewed-candidate promotion checks.

## Network and retention bounds

The publisher's HTTPS smoke check rejects redirects, unexpected status,
compressed content encoding and mismatched URLs. It requests identity
encoding, checks actual received byte counts rather than trusting
Content-Length, uses a 30-second transfer budget with a five-second socket
timeout, and sends no cookies, authentication or referrer. It fetches only
the fixed pointer and its signed immutable paths. A mismatched pointer or
partial generation fails publication verification.

GitHub Pages controls response cache headers; custom header behavior is not
claimed. Publisher pointer requests use `Cache-Control: no-cache`; the client
uses fetch cache revalidation and authenticates every candidate. Payload hashes
and immutable paths provide content identity, not freshness by themselves.

The public tree is capped at 900 MiB. All release files and evidence remain in
the append-only release history until an explicitly reviewed hosting/archival
migration. Browser cache state and activation use IndexedDB transactions;
payloads are not stored in storage.local. See the client operations note for
cache limits and the remaining installed-browser quota checks.
