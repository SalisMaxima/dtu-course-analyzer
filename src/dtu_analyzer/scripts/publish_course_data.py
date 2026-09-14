"""Package approved bytes, persist immutable signed releases, and verify HTTPS deployment.

The caller serializes the ledger branch and supplies GitHub API evidence. No
collection, authentication, arbitrary artifact execution or data regeneration.
"""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

from .candidate_provenance import sha256
from .course_data_contract import (
    MAX_ENVELOPE,
    MAX_PAYLOAD,
    require,
    strict_json,
    timestamp,
    validate_dataset,
)
from .promotion_receipt import verify_promoted

CONTRACT = 1
COMPATIBILITY = {"minimum_extension": "2.6.0", "minimum_chrome": 120, "minimum_firefox": 128}
MAX_SITE = 900 * 1024 * 1024
REPOSITORIES = {
    "production": "SMKIDRaadet/dtu-course-analyzer",
    "staging": "SalisMaxima/dtu-course-analyzer",
}


def encode_json(value):
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def validate_origin(origin):
    require(isinstance(origin, str), "Configure the confirmed HTTPS origin before publishing")
    parsed = urlsplit(origin)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.netloc == parsed.hostname
        and not parsed.query
        and not parsed.fragment
        and origin.endswith("/")
        and re.fullmatch(r"[a-z0-9.-]+", parsed.hostname)
        and re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", parsed.path),
        "Invalid fixed HTTPS origin/prefix",
    )
    return origin


def decode64(value):
    require(isinstance(value, str), "Expected base64 string")
    return base64.b64decode(value, validate=True)


def public_key(encoded):
    key = serialization.load_der_public_key(decode64(encoded))
    require(
        isinstance(key, rsa.RSAPublicKey)
        and key.key_size == 3072
        and key.public_numbers().e == 65537,
        "Expected RSA-3072 public key with exponent 65537",
    )
    return key


def verify_envelope(content, keys, origin, channel):
    """Authenticate exact metadata bytes before interpreting any metadata field."""
    envelope = strict_json(content, MAX_ENVELOPE)
    require(
        isinstance(envelope, dict) and set(envelope) == {"key_id", "metadata", "signature"},
        "Invalid release envelope",
    )
    key_id = envelope["key_id"]
    require(isinstance(key_id, str) and key_id in keys, "Unknown signing key")
    raw, signature = decode64(envelope["metadata"]), decode64(envelope["signature"])
    try:
        public_key(keys[key_id]).verify(signature, raw, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise ValueError("Release signature verification failed") from exc
    metadata = strict_json(raw, MAX_ENVELOPE)
    fields = {
        "contract_version",
        "schema_version",
        "dataset",
        "path",
        "sequence",
        "published_at",
        "collected_at",
        "byte_length",
        "sha256",
        "compatibility",
        "key_id",
        "origin",
        "channel",
        "evidence_sha256",
        "promotion_commit",
        "request_id",
    }
    require(isinstance(metadata, dict) and set(metadata) == fields, "Unsupported metadata fields")
    require(
        type(metadata["contract_version"]) is int
        and metadata["contract_version"] == CONTRACT
        and type(metadata["schema_version"]) is int
        and metadata["schema_version"] == 1
        and metadata["dataset"] == "dtu-course-data",
        "Unsupported release contract/schema",
    )
    require(
        metadata["key_id"] == key_id
        and metadata["origin"] == validate_origin(origin)
        and metadata["channel"] == channel,
        "Wrong release trust domain",
    )
    # Require the precise compatibility contract, not arbitrary remote requirements.
    require(
        encode_json(metadata["compatibility"]) == encode_json(COMPATIBILITY),
        "Unsupported compatibility requirements",
    )
    sequence = metadata["sequence"]
    require(type(sequence) is int and 0 < sequence <= 2**53 - 1, "Invalid release sequence")
    require(
        type(metadata["byte_length"]) is int and 0 < metadata["byte_length"] <= MAX_PAYLOAD,
        "Invalid payload byte length",
    )
    for field in ("sha256", "evidence_sha256"):
        require(
            isinstance(metadata[field], str) and re.fullmatch(r"[0-9a-f]{64}", metadata[field]),
            "Invalid digest",
        )
    require(
        isinstance(metadata["promotion_commit"], str)
        and re.fullmatch(r"[0-9a-f]{40}", metadata["promotion_commit"]),
        "Invalid promotion commit",
    )
    require(
        isinstance(metadata["request_id"], str)
        and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", metadata["request_id"]),
        "Invalid request ID",
    )
    require(
        metadata["path"] == f"releases/{sequence}-{metadata['sha256']}/data.json",
        "Invalid immutable payload path",
    )
    published, collected = timestamp(metadata["published_at"]), timestamp(metadata["collected_at"])
    require(
        collected <= published <= datetime.now(timezone.utc) + timedelta(minutes=5),
        "Invalid publication/collection chronology",
    )
    return metadata


def verify_payload(payload, metadata):
    require(
        len(payload) == metadata["byte_length"] and sha256(payload) == metadata["sha256"],
        "Payload length or digest mismatch",
    )
    return validate_dataset(payload)


def sign_metadata(metadata, pem, keys):
    key = serialization.load_pem_private_key(pem, password=None)
    require(
        isinstance(key, rsa.RSAPrivateKey) and key.key_size == 3072, "Expected RSA-3072 signing key"
    )
    require(
        key.public_key().public_numbers() == public_key(keys[metadata["key_id"]]).public_numbers(),
        "Signing secret does not match the reviewed public key",
    )
    raw = encode_json(metadata)
    return encode_json(
        {
            "key_id": metadata["key_id"],
            "metadata": base64.b64encode(raw).decode(),
            "signature": base64.b64encode(
                key.sign(raw, padding.PKCS1v15(), hashes.SHA256())
            ).decode(),
        }
    )


def read_ledger(ledger, keys, origin, channel):
    """Verify every retained release and require an exact public file allowlist."""
    ledger = Path(ledger)
    require(not ledger.is_symlink(), "Symlink ledger root")
    for path in ledger.rglob("*"):
        if ".git" not in path.relative_to(ledger).parts:
            require(not path.is_symlink(), "Symlink in release ledger")
    index_path = ledger / "index.json"
    if not index_path.exists():
        require(
            not any(p.name != ".git" for p in ledger.iterdir()), "Nonempty ledger without index"
        )
        return {"schema_version": 1, "releases": []}
    index = strict_json(index_path.read_bytes(), 1024 * 1024)
    require(
        isinstance(index, dict)
        and set(index) == {"schema_version", "releases"}
        and index["schema_version"] == 1
        and isinstance(index["releases"], list),
        "Invalid ledger",
    )
    allowed, requests, total = {"current.json"}, set(), 0
    for sequence, entry in enumerate(index["releases"], 1):
        require(
            isinstance(entry, dict) and set(entry) == {"request_id", "path"}, "Invalid ledger entry"
        )
        require(
            isinstance(entry["path"], str)
            and re.fullmatch(rf"releases/{sequence}-[0-9a-f]{{64}}/data\.json", entry["path"]),
            "Invalid ledger path",
        )
        directory = Path(entry["path"]).parent
        envelope_path = ledger / "public" / directory / "release.json"
        require(not envelope_path.is_symlink(), "Symlink in release ledger")
        metadata = verify_envelope(envelope_path.read_bytes(), keys, origin, channel)
        require(
            metadata["sequence"] == sequence
            and metadata["path"] == entry["path"]
            and metadata["request_id"] == entry["request_id"]
            and entry["request_id"] not in requests,
            "Inconsistent release ledger",
        )
        requests.add(entry["request_id"])
        payload_path = ledger / "public" / entry["path"]
        require(payload_path.stat().st_size <= MAX_PAYLOAD, "Oversized ledger payload")
        verify_payload(payload_path.read_bytes(), metadata)
        evidence = ledger / "evidence" / f"{sequence}.json"
        require(
            sha256(evidence.read_bytes()) == metadata["evidence_sha256"], "Release evidence changed"
        )
        allowed.update({entry["path"], (directory / "release.json").as_posix()})
    actual = set()
    for path in (ledger / "public").rglob("*"):
        require(not path.is_symlink(), "Symlink in public tree")
        if path.is_file():
            actual.add(path.relative_to(ledger / "public").as_posix())
            total += path.stat().st_size
    require(actual == (allowed if index["releases"] else set()), "Public file allowlist mismatch")
    require(total <= MAX_SITE, "Release history exceeds Pages size budget")
    if index["releases"]:
        latest = Path(index["releases"][-1]["path"]).parent / "release.json"
        require(
            (ledger / "public/current.json").read_bytes()
            == (ledger / "public" / latest).read_bytes(),
            "Current pointer differs from latest immutable release",
        )
    return index


def package_release(
    ledger,
    payload,
    receipt,
    commit,
    request_id,
    origin,
    channel,
    key_id,
    keys,
    pem,
    approval,
    published_at=None,
    rollback=False,
):
    """Prepare a release in a disposable ledger checkout; Git makes it durable atomically."""
    origin = validate_origin(origin)
    require(
        channel in REPOSITORIES and receipt["repository"] == REPOSITORIES[channel],
        "Wrong publication repository/channel",
    )
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", request_id), "Invalid release request ID")
    data = validate_dataset(payload)
    require(len(data) == receipt["validation"]["courses"], "Course count mismatch")
    require(
        sha256(payload) == receipt["provenance"]["files"]["extension/db/data.json"]["sha256"],
        "Payload is not the exact promoted dataset",
    )
    require(
        isinstance(approval, dict)
        and approval.get("environment") == f"course-data-{channel}"
        and approval.get("run_id")
        and approval.get("run_attempt")
        and approval.get("requested_by")
        and isinstance(approval.get("reviews"), list)
        and any(
            review.get("state") == "approved"
            and any(
                env.get("name") == f"course-data-{channel}"
                for env in review.get("environments", [])
            )
            for review in approval["reviews"]
        ),
        "Protected environment approval evidence is missing",
    )
    ledger = Path(ledger)
    index = read_ledger(ledger, keys, origin, channel)
    for entry in index["releases"]:
        if entry["request_id"] == request_id:
            metadata = verify_envelope(
                (ledger / "public" / Path(entry["path"]).parent / "release.json").read_bytes(),
                keys,
                origin,
                channel,
            )
            require(
                metadata["promotion_commit"] == commit and metadata["sha256"] == sha256(payload),
                "Request ID already used for a different dataset",
            )
            require(
                entry == index["releases"][-1],
                "A newer release exists; cannot retry an older pointer",
            )
            return metadata, False
    if index["releases"]:
        previous = verify_envelope(
            (ledger / "public/current.json").read_bytes(), keys, origin, channel
        )
        require(
            rollback
            or timestamp(receipt["approved_at"])
            >= timestamp(
                strict_json((ledger / "evidence" / f"{previous['sequence']}.json").read_bytes())[
                    "receipt"
                ]["approved_at"]
            ),
            "Older promotion requires explicit controlled rollback",
        )
    sequence = len(index["releases"]) + 1
    evidence = encode_json(
        {
            "receipt": receipt,
            "promotion_commit": commit,
            "publication": approval,
            "controlled_rollback": rollback,
        }
    )
    metadata = {
        "contract_version": CONTRACT,
        "schema_version": 1,
        "dataset": "dtu-course-data",
        "path": f"releases/{sequence}-{sha256(payload)}/data.json",
        "sequence": sequence,
        "published_at": published_at or datetime.now(timezone.utc).isoformat(),
        # Oldest contributing collection time: republishing must not conceal stale records.
        "collected_at": min((c["history_collected_at"] for c in data.values()), key=timestamp),
        "byte_length": len(payload),
        "sha256": sha256(payload),
        "compatibility": COMPATIBILITY,
        "key_id": key_id,
        "origin": origin,
        "channel": channel,
        "evidence_sha256": sha256(evidence),
        "promotion_commit": commit,
        "request_id": request_id,
    }
    envelope = sign_metadata(metadata, pem, keys)
    verify_envelope(envelope, keys, origin, channel)
    directory = ledger / "public" / Path(metadata["path"]).parent
    require(not directory.exists(), "Immutable release already exists")
    directory.mkdir(parents=True)
    (directory / "data.json").write_bytes(payload)
    (directory / "release.json").write_bytes(envelope)
    (ledger / "evidence").mkdir(exist_ok=True)
    (ledger / "evidence" / f"{sequence}.json").write_bytes(evidence)
    (ledger / "public/current.json").write_bytes(envelope)
    index["releases"].append({"request_id": request_id, "path": metadata["path"]})
    (ledger / "index.json").write_bytes(encode_json(index))
    read_ledger(ledger, keys, origin, channel)
    return metadata, True


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirects are forbidden for release downloads")


def fetch_bytes(url, limit, timeout=30):
    """Bound exact received bytes and total time; request no compressed encoding."""
    started = time.monotonic()
    request = Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    with build_opener(NoRedirect).open(request, timeout=min(timeout, 5)) as response:
        require(response.status == 200 and response.geturl() == url, "Unexpected HTTP response")
        require(
            response.headers.get("Content-Encoding", "identity").lower() == "identity",
            "Unexpected compressed response",
        )
        chunks, size = [], 0
        while True:
            require(time.monotonic() - started < timeout, "Download deadline exceeded")
            chunk = response.read1(min(64 * 1024, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            require(size <= limit, "Download byte limit exceeded")
            chunks.append(chunk)
        return b"".join(chunks)


def verify_deployed(origin, channel, keys, expected, fetch=fetch_bytes):
    origin = validate_origin(origin)
    envelope = fetch(origin + "current.json", MAX_ENVELOPE)
    require(envelope == expected, "Deployed pointer is not the expected release")
    metadata = verify_envelope(envelope, keys, origin, channel)
    payload = fetch(origin + metadata["path"], MAX_PAYLOAD)
    verify_payload(payload, metadata)
    immutable = fetch(origin + str(Path(metadata["path"]).parent) + "/release.json", MAX_ENVELOPE)
    require(immutable == envelope, "Incomplete or mixed deployment")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["package", "verify", "export"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/course-data-release.json"))
    parser.add_argument("--channel", choices=list(REPOSITORIES), required=True)
    parser.add_argument("--commit")
    parser.add_argument("--request-id")
    parser.add_argument("--promotion-run", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = strict_json(args.config.read_bytes(), 128 * 1024)[args.channel]
        origin, keys = validate_origin(config["origin"]), config["trusted_keys"]
        if args.command == "package":
            require(
                all([args.commit, args.request_id, args.promotion_run, args.approval]),
                "Missing package arguments",
            )
            payload, receipt = verify_promoted(
                args.root,
                args.commit,
                REPOSITORIES[args.channel],
                strict_json(args.promotion_run.read_bytes(), 1024 * 1024),
            )
            metadata, created = package_release(
                args.ledger,
                payload,
                receipt,
                args.commit,
                args.request_id,
                origin,
                args.channel,
                config["signing_key_id"],
                keys,
                os.environ.get("COURSE_DATA_SIGNING_KEY", "").encode(),
                strict_json(args.approval.read_bytes(), 1024 * 1024),
                rollback=args.rollback,
            )
            print(
                f"{'Prepared' if created else 'Reusing'} release {metadata['sequence']}: {metadata['sha256']}"
            )
        elif args.command == "export":
            read_ledger(args.ledger, keys, origin, args.channel)
            require(
                args.output and not args.output.exists(), "Export requires a new output directory"
            )
            shutil.copytree(args.ledger / "public", args.output)
        else:
            metadata = verify_deployed(
                origin, args.channel, keys, (args.ledger / "public/current.json").read_bytes()
            )
            print(f"Verified deployed release {metadata['sequence']}: {origin}{metadata['path']}")
    except (OSError, ValueError, KeyError, TypeError, InvalidSignature) as exc:
        # Never echo the signing key or raw GitHub authentication responses.
        print(f"Publication {args.command} failed: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
