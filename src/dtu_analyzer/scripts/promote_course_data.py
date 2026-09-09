"""Verify a selected Actions artifact and install only its exact dataset bytes.

Uses Python's standard library; no artifact scripts or extension code are executed.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .candidate_provenance import git, runtime_hash, sha256


def verify_origin(run, artifact, repository, run_id, artifact_id):
    if not re.fullmatch(r"[1-9][0-9]*", str(run_id)) or not re.fullmatch(r"[1-9][0-9]*", str(artifact_id)):
        raise ValueError("Run ID and artifact ID must be positive integers")
    if str(run.get("id")) != str(run_id) or str(artifact.get("id")) != str(artifact_id):
        raise ValueError("Selected run or artifact ID does not match GitHub metadata")
    if run.get("repository", {}).get("full_name") != repository or run.get("head_repository", {}).get("full_name") != repository:
        raise ValueError("Candidate must originate in this repository, not a fork")
    if run.get("path") != ".github/workflows/scrape.yml" or run.get("event") != "workflow_dispatch":
        raise ValueError("Candidate must come from Update Course Data")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("Source run must have completed successfully")
    if artifact.get("expired") is not False or artifact.get("name") != "course-data-candidate":
        raise ValueError("Candidate artifact is expired or has an unexpected name")
    if str(artifact.get("workflow_run", {}).get("id")) != str(run_id):
        raise ValueError("Artifact belongs to a different workflow run")


def verify_candidate(candidate_dir, root, run, artifact, repository, run_id, artifact_id):
    verify_origin(run, artifact, repository, run_id, artifact_id)
    candidate_dir, root = Path(candidate_dir), Path(root)
    metadata = json.loads((candidate_dir / "provenance.json").read_text())
    validation_bytes = (candidate_dir / "validation.json").read_bytes()
    data_bytes = (candidate_dir / "extension/db/data.json").read_bytes()
    if metadata.get("schema_version") != 1:
        raise ValueError("Unsupported or missing candidate provenance; build a new candidate")
    if (metadata.get("repository") != repository
            or str(metadata.get("run_id")) != str(run_id)
            or str(metadata.get("run_attempt")) != str(run.get("run_attempt"))
            or metadata.get("source_sha") != run.get("head_sha")):
        raise ValueError("Candidate provenance does not match the selected source run/attempt")
    if sha256(data_bytes) != metadata.get("dataset_sha256") or sha256(validation_bytes) != metadata.get("validation_sha256"):
        raise ValueError("Candidate dataset or validation checksum mismatch")
    validation = json.loads(validation_bytes)
    data = json.loads(data_bytes)
    if validation.get("schema_version") != 1 or validation.get("publishable") is not True or validation.get("issues") != []:
        raise ValueError("Candidate did not pass publication validation")
    if not isinstance(data, dict) or not data or validation.get("courses") != len(data):
        raise ValueError("Candidate course count is invalid")
    if sha256((root / "extension/db/data.json").read_bytes()) != metadata.get("baseline_sha256"):
        raise ValueError("Installed dataset changed since collection; build and review a new candidate")
    source = metadata["source_sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Invalid source commit")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", source, "HEAD"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise ValueError("Candidate source commit is not in this branch's history")
    if runtime_hash(root) != metadata.get("runtime_sha256"):
        raise ValueError("Extension or pipeline code changed since testing; build a new candidate")
    return data_bytes


def install_dataset(root, data_bytes):
    destination = Path(root) / "extension/db/data.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".promotion-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(destination.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        if git(args.root, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("Tracked worktree must be clean before promotion")
        data = verify_candidate(args.candidate, args.root,
                                json.loads(args.run_metadata.read_text()), json.loads(args.artifact_metadata.read_text()),
                                args.repository, args.run_id, args.artifact_id)
        install_dataset(args.root, data)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"Promotion refused: {exc}")
        return 1
    print(f"Verified and installed dataset SHA-256: {sha256(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
