"""Verify and install exact candidate dataset and checker-baseline bytes.

Uses Python's standard library; no artifact scripts or extension code are executed.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .candidate_provenance import PROMOTION_FILES, git, runtime_hash, sha256


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
    if metadata.get("schema_version") != 2:
        raise ValueError("Unsupported or missing candidate provenance; build a new candidate")
    files = metadata.get("files", {})
    if set(files) != set(PROMOTION_FILES):
        raise ValueError("Candidate must include exactly the dataset and both checker baselines")
    payloads = {path: (candidate_dir / path).read_bytes() for path in PROMOTION_FILES}
    if (metadata.get("repository") != repository
            or str(metadata.get("run_id")) != str(run_id)
            or str(metadata.get("run_attempt")) != str(run.get("run_attempt"))
            or metadata.get("source_sha") != run.get("head_sha")):
        raise ValueError("Candidate provenance does not match the selected source run/attempt")
    if sha256(validation_bytes) != metadata.get("validation_sha256"):
        raise ValueError("Candidate validation checksum mismatch")
    for path, content in payloads.items():
        if sha256(content) != files[path].get("sha256"):
            raise ValueError(f"Candidate checksum mismatch: {path}")
        if sha256((root / path).read_bytes()) != files[path].get("baseline_sha256"):
            raise ValueError(f"Installed baseline changed since collection: {path}; build a new candidate")
    validation = json.loads(validation_bytes)
    data = json.loads(payloads["extension/db/data.json"])
    if validation.get("schema_version") != 1 or validation.get("publishable") is not True or validation.get("issues") != []:
        raise ValueError("Candidate did not pass publication validation")
    if not isinstance(data, dict) or not data or validation.get("courses") != len(data):
        raise ValueError("Candidate course count is invalid")
    source = metadata["source_sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Invalid source commit")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", source, "HEAD"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise ValueError("Candidate source commit is not in this branch's history")
    if runtime_hash(root) != metadata.get("runtime_sha256"):
        raise ValueError("Extension or pipeline code changed since testing; build a new candidate")
    return payloads


def install_files(root, payloads):
    """Prepare all writes before replacing files; roll back a failed replacement.

    Repository visibility is atomic at the subsequent single Git commit.
    """
    staged, backups, replaced = {}, {}, []
    def prepare(destination, content, entries, path):
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".promotion-", delete=False) as stream:
            temporary = Path(stream.name)
            entries[path] = temporary
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(destination.stat().st_mode & 0o777)
    try:
        for path in PROMOTION_FILES:
            destination = Path(root) / path
            prepare(destination, payloads[path], staged, path)
            prepare(destination, destination.read_bytes(), backups, path)
        for path in PROMOTION_FILES:
            os.replace(staged[path], Path(root) / path)
            replaced.append(path)
    except OSError:
        for path in reversed(replaced):
            os.replace(backups[path], Path(root) / path)
        raise
    finally:
        for temporary in [*staged.values(), *backups.values()]:
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
        install_files(args.root, data)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"Promotion refused: {exc}")
        return 1
    for path, content in data.items():
        print(f"Verified and installed {path} SHA-256: {sha256(content)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
