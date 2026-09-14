"""Release trust, publication retries and replay checks; no network credentials."""

import base64
import copy
import json
from pathlib import Path
import subprocess

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from dtu_analyzer.scripts.candidate_provenance import git, sha256
from dtu_analyzer.scripts.course_data_contract import MAX_PAYLOAD, validate_dataset, strict_json
from dtu_analyzer.scripts.promotion_receipt import RECEIPT_PATH, make_receipt, verify_promoted
from dtu_analyzer.scripts.promote_course_data import install_files, verify_candidate
from dtu_analyzer.scripts.publish_course_data import (
    encode_json,
    package_release,
    read_ledger,
    sign_metadata,
    verify_deployed,
    verify_envelope,
    verify_payload,
    validate_origin,
)
from .test_candidate_promotion import candidate  # shared genuine git/artifact fixture

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://staging.example.org/course-data/"
COMMIT = "a" * 40


@pytest.fixture(scope="module")
def signing():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    spki = base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).decode()
    return pem, {"staging-test-1": spki}


@pytest.fixture
def release(tmp_path, signing):
    pem, keys = signing
    real = json.loads((ROOT / "extension/db/data.json").read_bytes())
    payload = encode_json({key: real[key] for key in ("01001", "01002", "01025", "27827")})
    receipt = {
        "repository": "SalisMaxima/dtu-course-analyzer",
        "approved_at": "2026-09-10T00:00:00+00:00",
        "validation": {"courses": 4},
        "provenance": {"files": {"extension/db/data.json": {"sha256": sha256(payload)}}},
    }
    approval = {
        "environment": "course-data-staging",
        "run_id": "999",
        "run_attempt": "1",
        "requested_by": "test-maintainer",
        "reviews": [{"state": "approved", "environments": [{"name": "course-data-staging"}]}],
    }
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    return dict(
        ledger=ledger,
        payload=payload,
        receipt=receipt,
        commit=COMMIT,
        request_id="test-1",
        origin=ORIGIN,
        channel="staging",
        key_id="staging-test-1",
        keys=keys,
        pem=pem,
        approval=approval,
    )


def snapshot(directory):
    return {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    }


def test_real_payload_schema_preserves_every_record():
    payload = (ROOT / "extension/db/data.json").read_bytes()
    assert validate_dataset(payload) == json.loads(payload)
    assert len(payload) < MAX_PAYLOAD


def test_package_exact_bytes_retry_and_forward_rollback(release):
    metadata, created = package_release(**release)
    assert created and metadata["sequence"] == 1
    ledger = release["ledger"]
    assert (ledger / "public" / metadata["path"]).read_bytes() == release["payload"]
    before = snapshot(ledger)
    retry, created = package_release(**{**release, "pem": b""})
    assert not created and retry == metadata and before == snapshot(ledger)
    newer, _ = package_release(**{**release, "request_id": "test-2"})
    assert newer["sequence"] == 2
    with pytest.raises(ValueError, match="newer release"):
        package_release(**release)
    rollback, _ = package_release(**{**release, "request_id": "rollback-1", "rollback": True})
    assert rollback["sequence"] == 3 and rollback["sha256"] == metadata["sha256"]
    assert rollback["collected_at"] == metadata["collected_at"]


def test_cannot_reuse_request_for_different_commit(release):
    package_release(**release)
    before = snapshot(release["ledger"])
    with pytest.raises(ValueError, match="different dataset"):
        package_release(**{**release, "commit": "b" * 40})
    assert snapshot(release["ledger"]) == before


def test_older_promotion_requires_explicit_rollback(release):
    package_release(**release)
    older = copy.deepcopy(release["receipt"])
    older["approved_at"] = "2026-09-09T22:00:00+00:00"
    with pytest.raises(ValueError, match="rollback"):
        package_release(**{**release, "receipt": older, "request_id": "older"})
    metadata, _ = package_release(
        **{**release, "receipt": older, "request_id": "older", "rollback": True}
    )
    assert metadata["sequence"] == 2


@pytest.mark.parametrize("change", ["unapproved", "wrong_environment", "wrong_repository", "bytes"])
def test_publication_rejects_unapproved_or_mismatched_input(release, change):
    if change == "unapproved":
        release["approval"]["reviews"] = []
    elif change == "wrong_environment":
        release["approval"]["reviews"][0]["environments"][0]["name"] = "course-data-production"
    elif change == "wrong_repository":
        release["receipt"]["repository"] = "someone/fork"
    else:
        release["payload"] += b" "
    with pytest.raises(ValueError):
        package_release(**release)
    assert snapshot(release["ledger"]) == {}


@pytest.mark.parametrize(
    "change",
    [
        "payload",
        "metadata",
        "signature",
        "unknown_key",
        "staging_key",
        "schema",
        "compatibility",
        "path",
        "sequence",
        "length",
        "future",
        "origin",
    ],
)
def test_rejects_tampering_and_unsupported_contract(release, change):
    metadata, _ = package_release(**release)
    envelope = (release["ledger"] / "public/current.json").read_bytes()
    keys = release["keys"]
    if change == "payload":
        with pytest.raises(ValueError):
            verify_payload(release["payload"] + b" ", metadata)
        return
    if change in {"metadata", "signature", "unknown_key"}:
        fields = json.loads(envelope)
        fields[
            {"metadata": "metadata", "signature": "signature", "unknown_key": "key_id"}[change]
        ] = "AAAA"
        envelope = encode_json(fields)
    elif change == "staging_key":
        keys = {}
    else:
        field, value = {
            "schema": ("schema_version", 2),
            "compatibility": ("compatibility", {}),
            "path": ("path", "//evil.example/data.json"),
            "sequence": ("sequence", True),
            "length": ("byte_length", MAX_PAYLOAD + 1),
            "future": ("published_at", "2200-01-01T00:00:00Z"),
            "origin": ("origin", "https://evil.example/"),
        }[change]
        metadata[field] = value
        envelope = sign_metadata(metadata, release["pem"], keys)
    with pytest.raises(ValueError):
        verify_envelope(envelope, keys, ORIGIN, "staging")


@pytest.mark.parametrize(
    "path", ["public/credentials.json", "public/releases/evil/data.js", "public/report.json"]
)
def test_public_allowlist_rejects_any_extra_file(release, path):
    package_release(**release)
    target = release["ledger"] / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not allowed")
    with pytest.raises(ValueError, match="allowlist"):
        read_ledger(release["ledger"], release["keys"], ORIGIN, "staging")


def test_ledger_rejects_symlinks_and_evidence_corruption(release):
    metadata, _ = package_release(**release)
    path = release["ledger"] / "evidence/1.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="evidence"):
        read_ledger(release["ledger"], release["keys"], ORIGIN, "staging")
    path.unlink()
    path.symlink_to(release["ledger"] / "public" / metadata["path"])
    with pytest.raises(ValueError, match="Symlink"):
        read_ledger(release["ledger"], release["keys"], ORIGIN, "staging")


def test_deployed_smoke_check_detects_mixed_generation_and_http_failure(release):
    package_release(**release)
    public = release["ledger"] / "public"
    expected = (public / "current.json").read_bytes()
    calls = []

    def fetch(url, limit):
        assert url.startswith(ORIGIN)
        calls.append(url)
        return (public / url.removeprefix(ORIGIN)).read_bytes()

    assert verify_deployed(ORIGIN, "staging", release["keys"], expected, fetch)["sequence"] == 1
    assert len(calls) == 3 and all("?" not in url for url in calls)
    with pytest.raises(ValueError, match="expected release"):
        verify_deployed(ORIGIN, "staging", release["keys"], expected, lambda *_: b"{}")

    def missing(url, limit):
        if url.endswith("data.json"):
            raise OSError("HTTP 404")
        return fetch(url, limit)

    with pytest.raises(OSError):
        verify_deployed(ORIGIN, "staging", release["keys"], expected, missing)
    assert (public / "current.json").read_bytes() == expected


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "http://example.org/",
        "https://user:pass@example.org/",
        "https://example.org/a/../",
        "https://example.org/?token=x",
        "https://example.org/%2e%2e/",
        "https://example.org:444/",
    ],
)
def test_fixed_origin_rejects_unsafe_destinations(origin):
    with pytest.raises(ValueError):
        validate_origin(origin)


@pytest.mark.parametrize(
    "change",
    [
        "course_id",
        "unknown_field",
        "url",
        "nan",
        "numeric_string",
        "negative_count",
        "long_text",
        "too_many_exams",
        "suppressed",
        "default",
        "history",
        "duplicate_exam",
        "default_result",
        "prototype",
    ],
)
def test_schema_rejects_malicious_or_inconsistent_fields(release, change):
    data = json.loads(release["payload"])
    record = data["01001"]
    exam = record["exam_history"][0]
    if change == "course_id":
        data["<img>"] = data.pop("01001")
    elif change == "unknown_field":
        record["script"] = "alert(1)"
    elif change == "url":
        exam["grade_source"] = "javascript:alert(1)"
    elif change == "nan":
        record["avg"] = float("nan")
    elif change == "numeric_string":
        record["avg"] = "12"
    elif change == "negative_count":
        exam["grades"]["12"] = -1
    elif change == "long_text":
        record["name"] = "x" * 4097
    elif change == "too_many_exams":
        record["exam_history"] *= 129
    elif change == "suppressed":
        exam["distribution_status"] = "suppressed"
    elif change == "default":
        record["default_exam_id"] = "missing"
    elif change == "history":
        exam["identity_status"] = "manually_approved_history"
    elif change == "duplicate_exam":
        record["exam_history"].append(exam)
    elif change == "default_result":
        record["passpercent"] = 99
    else:
        record["constructor"] = {}
    with pytest.raises(ValueError):
        validate_dataset(json.dumps(data).encode())


def test_duplicate_keys_and_non_utf8_are_rejected():
    for payload in (b'{"a":1,"a":2}', '{"a":1}'.encode("utf-16"), b'{"x":Infinity}'):
        with pytest.raises(ValueError):
            strict_json(payload)


def test_standard_webcrypto_verifies_python_signature(release, tmp_path):
    package_release(**release)
    vector = tmp_path / "vector.json"
    vector.write_bytes(
        encode_json(
            {
                "keys": release["keys"],
                "envelope": json.loads((release["ledger"] / "public/current.json").read_bytes()),
            }
        )
    )
    script = """
      const fs = require('node:fs');
      const {webcrypto} = require('node:crypto');
      (async () => {
        const {keys, envelope} = JSON.parse(fs.readFileSync(process.argv[1]));
        const key = await webcrypto.subtle.importKey('spki', Buffer.from(keys[envelope.key_id], 'base64'),
          {name:'RSASSA-PKCS1-v1_5', hash:'SHA-256'}, false, ['verify']);
        const ok = await webcrypto.subtle.verify('RSASSA-PKCS1-v1_5', key,
          Buffer.from(envelope.signature, 'base64'), Buffer.from(envelope.metadata, 'base64'));
        if (!ok) throw new Error('Python/Web Crypto signature mismatch');
      })().catch(e => { console.error(e); process.exit(1); });
    """
    subprocess.run(["node", "-e", script, str(vector)], check=True)


@pytest.fixture
def promoted(candidate, monkeypatch):
    root, output, run, artifact, _ = candidate
    parent = git(root, "rev-parse", "HEAD")
    for key, value in {
        "GITHUB_RUN_ID": "789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_ACTOR": "reviewer",
        "GITHUB_REF_NAME": "master",
        "GITHUB_SHA": parent,
    }.items():
        monkeypatch.setenv(key, value)
    payloads = verify_candidate(output, root, run, artifact, "owner/repo", "123", "456")
    receipt = make_receipt(output, root, run, artifact)
    payloads[RECEIPT_PATH] = encode_json(receipt)
    install_files(root, payloads)
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Promote",
    )
    commit = git(root, "rev-parse", "HEAD")
    promotion_run = {
        "id": 789,
        "run_attempt": 1,
        "head_sha": parent,
        "head_branch": "master",
        "repository": {"full_name": "owner/repo"},
        "head_repository": {"full_name": "owner/repo"},
        "path": ".github/workflows/promote-course-data.yml",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
    }
    return root, commit, promotion_run, payloads


def test_promoted_receipt_survives_artifact_expiry_and_docs_changes(promoted):
    root, commit, run, payloads = promoted
    payload, receipt = verify_promoted(root, commit, "owner/repo", run)
    assert payload == payloads["extension/db/data.json"] and receipt["source"]["artifact_id"] == 456
    (root / "README.md").write_text("Later docs")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Docs",
    )
    assert verify_promoted(root, commit, "owner/repo", run)[0] == payload


@pytest.mark.parametrize(
    "change", ["failed_run", "attempt", "fork", "commit", "receipt", "validation", "runtime"]
)
def test_promotion_receipt_cannot_authorize_unreviewed_bytes(promoted, change):
    root, commit, run, _ = promoted
    if change == "failed_run":
        run["conclusion"] = "failure"
    elif change == "attempt":
        run["run_attempt"] = 2
    elif change == "fork":
        run["head_repository"]["full_name"] = "someone/else"
    else:
        if change == "commit":
            (root / "extension/db/data.json").write_text("{}")
        elif change == "runtime":
            (root / "extension/contentscript.js").write_text("bad code")
        else:
            path = root / RECEIPT_PATH
            data = json.loads(path.read_bytes())
            if change == "receipt":
                data["provenance"]["files"]["extension/db/data.json"]["sha256"] = "0" * 64
            else:
                data["validation_json"] += " "
            path.write_bytes(encode_json(data))
        git(root, "add", ".")
        git(
            root,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--amend",
            "--no-edit",
            "-q",
        )
        commit = git(root, "rev-parse", "HEAD")
    with pytest.raises(ValueError):
        verify_promoted(root, commit, "owner/repo", run)


def test_complete_local_review_promotion_publication_roundtrip(candidate, release, monkeypatch):
    from dtu_analyzer.scripts.candidate_provenance import write_provenance

    root, output, run, artifact, _ = candidate
    repository = "SalisMaxima/dtu-course-analyzer"
    for field in ("repository", "head_repository"):
        run[field]["full_name"] = repository
    monkeypatch.setenv("GITHUB_REPOSITORY", repository)
    (output / "extension/db/data.json").write_bytes(release["payload"])
    (output / "validation.json").write_bytes(
        encode_json({"schema_version": 1, "publishable": True, "issues": [], "courses": 4})
    )
    write_provenance(output, (root / "extension/db/data.json").read_bytes(), root)
    payloads = verify_candidate(output, root, run, artifact, repository, "123", "456")
    parent = git(root, "rev-parse", "HEAD")
    for key, value in {
        "GITHUB_RUN_ID": "789",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_ACTOR": "reviewer",
        "GITHUB_REF_NAME": "master",
        "GITHUB_SHA": parent,
    }.items():
        monkeypatch.setenv(key, value)
    receipt = make_receipt(output, root, run, artifact)
    payloads[RECEIPT_PATH] = encode_json(receipt)
    install_files(root, payloads)
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Promote",
    )
    commit = git(root, "rev-parse", "HEAD")
    promotion_run = {
        **run,
        "id": 789,
        "head_sha": parent,
        "head_branch": "master",
        "path": ".github/workflows/promote-course-data.yml",
    }
    payload, receipt = verify_promoted(root, commit, repository, promotion_run)
    metadata, _ = package_release(
        **{**release, "payload": payload, "receipt": receipt, "commit": commit}
    )
    public = release["ledger"] / "public"
    deployed = verify_deployed(
        ORIGIN,
        "staging",
        release["keys"],
        (public / "current.json").read_bytes(),
        lambda url, _: (public / url.removeprefix(ORIGIN)).read_bytes(),
    )
    assert deployed == metadata and metadata["sha256"] == sha256(payloads["extension/db/data.json"])


def test_rotation_and_compromised_key_removal(release):
    first, _ = package_release(**release)
    old_envelope = (release["ledger"] / "public/current.json").read_bytes()
    replacement = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    replacement_pem = replacement.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    replacement_public = base64.b64encode(
        replacement.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    ).decode()
    rotated_keys = {**release["keys"], "staging-test-2": replacement_public}
    second, _ = package_release(
        **{
            **release,
            "request_id": "rotation",
            "key_id": "staging-test-2",
            "keys": rotated_keys,
            "pem": replacement_pem,
        }
    )
    assert second["sequence"] > first["sequence"]
    new_envelope = (release["ledger"] / "public/current.json").read_bytes()
    recovered_client_keys = {"staging-test-2": replacement_public}
    verify_envelope(new_envelope, recovered_client_keys, ORIGIN, "staging")
    with pytest.raises(ValueError, match="Unknown signing key"):
        verify_envelope(old_envelope, recovered_client_keys, ORIGIN, "staging")
    with pytest.raises(ValueError, match="does not match"):
        sign_metadata(second, release["pem"], rotated_keys)


def test_download_transport_limits_redirects_and_request_privacy():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from dtu_analyzer.scripts.publish_course_data import fetch_bytes

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append((self.path, dict(self.headers)))
            self.send_response(302 if self.path == "/redirect" else 200)
            if self.path == "/redirect":
                self.send_header("Location", "/must-not-fetch")
            if self.path == "/compressed":
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            if self.path != "/redirect":
                self.wfile.write(b"x" * 65)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert fetch_bytes(base + "/valid", 65) == b"x" * 65
        for path, message in [
            ("/large", "byte limit"),
            ("/redirect", "Redirect"),
            ("/compressed", "compressed"),
        ]:
            with pytest.raises(ValueError, match=message):
                fetch_bytes(base + path, 64)
        assert "/must-not-fetch" not in [path for path, _ in calls]
        for _, headers in calls:
            assert not ({"cookie", "authorization", "referer"} & {h.lower() for h in headers})
            assert headers["Cache-Control"] == "no-cache"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
