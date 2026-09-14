# Non-production interoperability vector

This directory contains one public course record, a signed release envelope
and its public verification key. The key was generated exclusively for this
fixture; its private part was discarded and is not committed. Never add this
key to a production or deployed staging trust store.

The all-zero promotion SHA and synthetic evidence digest identify a test
vector, not an approved production release. The publisher cannot accept this
directory as a promotion receipt or a release ledger. The example.org origin
is illustrative and no files have been deployed there.

To verify the unchanged signature bytes, dataset digest, size and schema:

```sh
python -m pip install -e ".[release]"
PYTHONPATH=src python - <<'PY'
from pathlib import Path
from dtu_analyzer.scripts.course_data_contract import strict_json
from dtu_analyzer.scripts.publish_course_data import verify_envelope, verify_payload
root = Path("tests/fixtures/course-data-release")
metadata = verify_envelope(
    (root / "current.json").read_bytes(),
    strict_json((root / "public-keys.json").read_bytes()),
    "https://staging.example.org/course-data/", "staging",
)
verify_payload((root / "data.json").read_bytes(), metadata)
print("Signature, exact bytes, digest and schema verified")
PY
```

The automated release tests also generate independent ephemeral keys and
verify the Python signatures through the standard Web Crypto API in Node.
This establishes signing-format interoperability; it is not a claim of
installed Chrome/Firefox updater validation.
