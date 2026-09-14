"""Durable approval evidence, committed atomically with the promoted files."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from .candidate_provenance import PROMOTION_FILES, git, sha256
from .course_data_contract import require, strict_json, timestamp

RECEIPT_PATH = "data/course-data-promotion.json"


def git_bytes(root, ref, path):
    return subprocess.check_output(["git", "-C", str(root), "show", f"{ref}:{path}"])


def committed_runtime_hash(root, ref):
    paths = git(
        root,
        "ls-tree",
        "-r",
        "--name-only",
        ref,
        "--",
        "extension",
        "src/dtu_analyzer",
        "pyproject.toml",
        "requirements.txt",
        ".github/workflows/scrape.yml",
        ".github/workflows/promote-course-data.yml",
    ).splitlines()
    files = {
        path: sha256(git_bytes(root, ref, path))
        for path in sorted(paths)
        if path != "extension/db/data.json"
    }
    return sha256(json.dumps(files, sort_keys=True).encode())


def make_receipt(candidate, root, run, artifact):
    """Called only after verify_candidate; prepares evidence before any writes."""
    required = (
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_ACTOR",
        "GITHUB_REF_NAME",
        "GITHUB_SHA",
    )
    require(all(os.environ.get(key) for key in required), "Promotion workflow identity is missing")
    candidate = Path(candidate)
    return {
        "schema_version": 1,
        "repository": os.environ["GITHUB_REPOSITORY"],
        "parent_commit": git(root, "rev-parse", "HEAD"),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "promotion": {
            "run_id": os.environ["GITHUB_RUN_ID"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "requested_by": os.environ["GITHUB_ACTOR"],
            "branch": os.environ["GITHUB_REF_NAME"],
            "workflow_sha": os.environ["GITHUB_SHA"],
        },
        "source": {
            "run_id": run["id"],
            "run_attempt": run["run_attempt"],
            "commit": run["head_sha"],
            "artifact_id": artifact["id"],
            "workflow": run["path"],
            "validation": "passed",
        },
        # Only the successful validation summary, never the diagnostic artifact.
        "validation": strict_json((candidate / "validation.json").read_bytes()),
        "validation_json": (candidate / "validation.json").read_bytes().decode("utf-8"),
        "provenance": strict_json((candidate / "provenance.json").read_bytes()),
    }


def verify_promoted(root, commit, repository, promotion_run):
    require(re.fullmatch(r"[0-9a-f]{40}", commit), "Full promotion commit SHA required")
    require(
        subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"],
            capture_output=True,
        ).returncode
        == 0,
        "Promotion is not in the approved branch",
    )
    receipt = strict_json(git_bytes(root, commit, RECEIPT_PATH), 1024 * 1024)
    require(
        receipt.get("schema_version") == 1 and receipt.get("repository") == repository,
        "Invalid promotion receipt or repository",
    )
    promotion, source, provenance = receipt["promotion"], receipt["source"], receipt["provenance"]
    parents = git(root, "rev-list", "--parents", "-n", "1", commit).split()[1:]
    require(
        parents == [receipt["parent_commit"]],
        "Receipt must belong to a single-parent promotion commit",
    )
    require(
        receipt["parent_commit"] == promotion["workflow_sha"],
        "Promotion must use the exact workflow-start commit",
    )
    changed = set(
        git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
    )
    require(
        RECEIPT_PATH in changed and changed <= set(PROMOTION_FILES) | {RECEIPT_PATH},
        "Promotion commit includes unrelated changes or a reused receipt",
    )
    require(
        promotion_run.get("path") == ".github/workflows/promote-course-data.yml"
        and promotion_run.get("event") == "workflow_dispatch"
        and promotion_run.get("status") == "completed"
        and promotion_run.get("conclusion") == "success",
        "Promotion workflow did not complete successfully",
    )
    for key in ("repository", "head_repository"):
        require(
            promotion_run.get(key, {}).get("full_name") == repository, "Wrong promotion repository"
        )
    require(
        str(promotion_run.get("id")) == str(promotion["run_id"])
        and str(promotion_run.get("run_attempt")) == str(promotion["run_attempt"])
        and promotion_run.get("head_sha") == promotion["workflow_sha"]
        and promotion_run.get("head_branch") == promotion["branch"],
        "Wrong promotion run/attempt",
    )
    require(
        provenance.get("schema_version") == 2 and provenance.get("repository") == repository,
        "Invalid candidate provenance",
    )
    require(
        str(source["run_id"]) == str(provenance["run_id"])
        and str(source["run_attempt"]) == str(provenance["run_attempt"])
        and source["commit"] == provenance["source_sha"]
        and source["workflow"] == ".github/workflows/scrape.yml"
        and source["validation"] == "passed"
        and re.fullmatch(r"[1-9][0-9]*", str(source["artifact_id"])),
        "Invalid source evidence",
    )
    validation = receipt["validation"]
    require(
        sha256(receipt["validation_json"].encode("utf-8")) == provenance["validation_sha256"]
        and strict_json(receipt["validation_json"].encode("utf-8")) == validation,
        "Validation evidence checksum mismatch",
    )
    require(
        validation.get("schema_version") == 1
        and validation.get("publishable") is True
        and validation.get("issues") == [],
        "Candidate validation did not pass",
    )
    timestamp(receipt["approved_at"])
    timestamp(provenance["created_at"])
    require(re.fullmatch(r"[0-9a-f]{40}", source["commit"]), "Invalid source commit")
    require(
        subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", source["commit"], parents[0]],
            capture_output=True,
        ).returncode
        == 0,
        "Source is not an ancestor of promotion",
    )
    require(
        committed_runtime_hash(root, commit)
        == provenance["runtime_sha256"]
        == committed_runtime_hash(root, source["commit"]),
        "Runtime changed before promotion",
    )
    require(set(provenance["files"]) == set(PROMOTION_FILES), "Incomplete promotion file set")
    for path, expected in provenance["files"].items():
        require(
            sha256(git_bytes(root, commit, path)) == expected["sha256"], "Promoted bytes changed"
        )
        require(
            sha256(git_bytes(root, parents[0], path)) == expected["baseline_sha256"],
            "Promotion parent baseline mismatch",
        )
    payload = git_bytes(root, commit, "extension/db/data.json")
    require(
        len(strict_json(payload)) == validation.get("courses"), "Validation course count mismatch"
    )
    return payload, receipt
