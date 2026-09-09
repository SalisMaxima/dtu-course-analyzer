"""Checksums and source metadata for a reviewed, immutable candidate artifact."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


def runtime_hash(root):
    """Bind the candidate to tracked extension/pipeline code, excluding live data."""
    paths = git(root, "ls-files", "-z", "--", "extension", "src/dtu_analyzer",
                "pyproject.toml", "requirements.txt", ".github/workflows/scrape.yml",
                ".github/workflows/promote-course-data.yml").split("\0")
    files = {p: sha256((Path(root) / p).read_bytes()) for p in sorted(filter(None, paths))
             if p != "extension/db/data.json"}
    return sha256(json.dumps(files, sort_keys=True).encode())


def write_provenance(output, baseline_bytes, root=Path(".")):
    output = Path(output)
    metadata = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "source_sha": git(root, "rev-parse", "HEAD"),
        "runtime_sha256": runtime_hash(root),
        "baseline_sha256": sha256(baseline_bytes),
        "dataset_sha256": sha256((output / "extension/db/data.json").read_bytes()),
        "validation_sha256": sha256((output / "validation.json").read_bytes()),
    }
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata
