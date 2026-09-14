"""Lint offline and remote-enabled Firefox packages using Mozilla's validator.

Run after npm ci and installing this project: python tests/lint_firefox_packages.py
Only public fixture keys are used. No downloads or deployments are performed.
"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from dtu_analyzer.scripts.build_browser_extension import build

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        root = scratch / "source"
        shutil.copytree(ROOT / "extension", root / "extension")
        (root / "config").mkdir()
        keys = json.loads(
            (ROOT / "tests/fixtures/course-data-release/public-keys.json").read_text()
        )
        config = {
            "production": {"origin": None, "signing_key_id": None, "trusted_keys": {}},
            "staging": {
                "origin": "https://staging.example.org/data/",
                "signing_key_id": next(iter(keys)),
                "trusted_keys": keys,
            },
        }
        (root / "config/course-data-release.json").write_text(json.dumps(config))
        for enabled in (False, True):
            name = "remote" if enabled else "offline"
            output = build(scratch / name, "firefox", "staging", enabled, root)
            result = subprocess.run(
                [str(ROOT / "node_modules/.bin/addons-linter"), str(output), "--output", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            print(f"Firefox {name}: {result.stdout}")
            if result.stderr:
                print(result.stderr)
            if result.returncode:
                raise SystemExit(result.returncode)
            report = json.loads(result.stdout)
            if report["summary"]["errors"]:
                raise SystemExit("Mozilla package validation failed")


if __name__ == "__main__":
    main()
