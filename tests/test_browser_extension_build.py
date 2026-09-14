import json
from pathlib import Path
import shutil

import pytest

from dtu_analyzer.scripts.build_browser_extension import build
from dtu_analyzer.analysis.course_history_reviews import (
    APPROVED_HISTORY,
    EXCLUDED_HISTORY,
    PREFERRED_SOURCES,
)

ROOT = Path(__file__).resolve().parents[1]


def test_firefox_package_uses_shared_updater_and_existing_addon_identity(tmp_path):
    output = build(tmp_path / "firefox", "firefox", root=ROOT)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["browser_specific_settings"]["gecko"]["id"] == "dtu.course.analyzer@gmail.com"
    assert manifest["browser_specific_settings"]["gecko"]["strict_min_version"] == "128.0"
    assert manifest["background"]["scripts"][-1] == "background.js"
    assert "js/data-background.js" in manifest["background"]["scripts"]
    assert manifest["browser_specific_settings"]["gecko"]["data_collection_permissions"][
        "optional"
    ] == ["technicalAndInteraction"]
    assert "optional_host_permissions" not in manifest
    assert json.loads((output / "js/data-update-config.json").read_text())["origin"] is None


def test_staging_has_separate_identity_and_production_cannot_build_unconfigured(tmp_path):
    output = build(tmp_path / "staging", "firefox", "staging", root=ROOT)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["browser_specific_settings"]["gecko"]["id"].startswith("staging-")
    with pytest.raises(ValueError):
        build(tmp_path / "production", "chrome", enable_remote=True, root=ROOT)
    assert not (tmp_path / "production").exists()


def test_packaged_schema_policy_matches_reviewed_python_policy():
    policy = json.loads((ROOT / "extension/js/data-schema-policy.json").read_text())
    assert policy == {
        "approved": APPROVED_HISTORY,
        "excluded": {k: sorted(v) for k, v in EXCLUDED_HISTORY.items()},
        "preferred": PREFERRED_SOURCES,
    }


def test_client_key_rotation_does_not_retrust_archived_signing_keys(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "extension", root / "extension")
    (root / "config").mkdir()
    key = next(
        iter(
            json.loads(
                (ROOT / "tests/fixtures/course-data-release/public-keys.json").read_text()
            ).values()
        )
    )
    config = {
        "staging": {
            "origin": "https://staging.example.org/data/",
            "signing_key_id": "current",
            "trusted_keys": {"current": key, "archived": key},
            "client_key_ids": ["current"],
        },
        "production": {"origin": None, "signing_key_id": None, "trusted_keys": {}},
    }
    (root / "config/course-data-release.json").write_text(json.dumps(config))
    output = build(tmp_path / "output", "chrome", "staging", True, root)
    assert list(
        json.loads((output / "js/data-update-config.json").read_text())["trusted_keys"]
    ) == ["current"]
    assert json.loads((output / "manifest.json").read_text())["optional_host_permissions"] == [
        "https://staging.example.org/*"
    ]
