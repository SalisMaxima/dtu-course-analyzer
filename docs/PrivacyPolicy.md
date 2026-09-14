# Privacy Policy for DTU Course Analyzer

Last updated: 14 September 2026. Applies to the 2.6.0 updater implementation.

DTU Course Analyzer reads the course identifier on a DTU course page and
displays public course statistics. Course views, searches, selected exams
and comparison choices are processed locally. The extension has no accounts,
advertising, analytics, installation identifiers or telemetry.

## Optional public-data downloads

Downloads are off by default, including when upgrading from a version that
used only bundled data. In the extension database you can explicitly allow
downloads, optionally enable automatic checks, or continue using bundled data
only. Declining downloads leaves local course statistics and comparison usable.
The download host is shown before you consent.

When enabled, the background extension requests the same public release
metadata and course dataset for every user. It never appends viewed course
numbers, page URLs, searches, exam choices, comparison lists, DTU credentials,
cookies or user identifiers. Requests omit credentials and referrers.
Automatic checks occur at most once per 24 hours with up to one hour of jitter;
manual checks are rate-limited. No remote scripts or UI templates are loaded.

The hosting provider necessarily receives the network IP address, request time
and normal connection/request metadata, including browser-managed HTTP headers.
Therefore downloads do not transmit “no information whatsoever.” For the
GitHub Pages hosting option, GitHub states that it logs visitors' IP addresses
for security purposes. See [GitHub Pages data collection](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages#data-collection)
and the [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).
GitHub describes retention by processing purpose and legal obligations; those
documents do not specify a fixed Pages IP-log retention period. We do not
promise one or control GitHub's security-log retention.

The checked-in build has no configured production download origin or trusted
keys. Production downloads cannot start until a reviewed build configures them.

## Local storage and control

The extension stores comparison choices, download preferences, update timing,
the highest accepted release sequence and a bounded cache of verified public
datasets locally in your browser. Dataset signatures, checksums and schema
are checked before activation. The bundled dataset remains an offline fallback.

“Use bundled data only” disables future downloads and displays bundled data.
“Clear downloaded data” removes cached payloads while retaining the anti-rollback
sequence and download preferences. You can disable automatic checks separately.
Removing the extension removes its browser-managed extension storage.

On Firefox versions supporting built-in data consent, optional download-related
connection metadata is declared as personally identifying information because
the host receives it together with your IP address. This permission covers that
connection metadata; the extension does not request your name, email address or
account details. There is no separate analytics or technical-telemetry collection.
The extension also requires its own explicit opt-in. Older supported Firefox
versions use that explicit consent screen. Revoking relevant host/data permission
disables further downloads. Changing from the earlier technical-data disclosure
requires fresh consent; existing permission grants alone do not enable downloads.
No browsing-activity permission is requested.

Private/incognito windows are not supported. The browser prevents the extension
from running there, so private-session comparison choices are not saved.

The extension's use of information is limited to its stated course-statistics
and comparison features, including serving and securing optional data downloads.
It does not use or transfer user information for advertising, profiling or sale.
These practices follow the Chrome Web Store User Data Policy's Limited Use
requirements.

## Contact

For questions, contact the maintainers through the
[project repository](https://github.com/SMKIDRaadet/dtu-course-analyzer).
All executable functionality is packaged with the extension and can be reviewed
in the source code.
