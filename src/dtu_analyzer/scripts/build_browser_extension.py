"""Build current Chrome/Firefox packages with explicitly selected packaged trust roots."""

import argparse
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from .publish_course_data import validate_origin, public_key
from ..analysis.course_history_reviews import APPROVED_HISTORY, EXCLUDED_HISTORY, PREFERRED_SOURCES


def build(output, browser, channel="production", enable_remote=False, root=Path(".")):
    output, root = Path(output), Path(root)
    if output.exists() or output.resolve().is_relative_to((root / "extension").resolve()):
        raise ValueError("Choose a new output directory outside extension/")
    config = json.loads((root / "config/course-data-release.json").read_text())[channel]
    packaged = {"origin": None, "channel": channel, "trusted_keys": {}}
    if enable_remote:
        origin = validate_origin(config["origin"])
        if not config["trusted_keys"] or config["signing_key_id"] not in config["trusted_keys"]:
            raise ValueError("Commit the reviewed public keys before enabling downloads")
        for key in config["trusted_keys"].values():
            public_key(key)
        other = "staging" if channel == "production" else "production"
        other_keys = json.loads((root / "config/course-data-release.json").read_text())[other][
            "trusted_keys"
        ]
        if set(config["trusted_keys"].values()) & set(other_keys.values()):
            raise ValueError("Production and staging must use separate trust roots")
        client_ids = config.get("client_key_ids", [config["signing_key_id"]])
        if (
            not isinstance(client_ids, list)
            or not client_ids
            or any(
                not isinstance(key, str) or key not in config["trusted_keys"] for key in client_ids
            )
        ):
            raise ValueError("Select reviewed client trust roots")
        packaged.update(
            origin=origin, trusted_keys={key: config["trusted_keys"][key] for key in client_ids}
        )
    manifest = json.loads((root / "extension/manifest.json").read_text())
    if enable_remote:
        manifest["optional_host_permissions"] = [f"https://{urlsplit(packaged['origin']).netloc}/*"]
    else:
        manifest.pop("optional_host_permissions", None)
    if channel == "staging":
        manifest["name"] += " (staging)"
    if browser == "firefox":
        manifest.pop("minimum_chrome_version", None)
        manifest["background"] = {
            "scripts": [
                "js/course-utils.js",
                "js/data-contract.js",
                "js/data-updater.js",
                "js/data-background.js",
                "background.js",
            ]
        }
        manifest["browser_specific_settings"] = {
            "gecko": {
                "id": ("staging-" if channel == "staging" else "")
                + "dtu.course.analyzer@gmail.com",
                "strict_min_version": "128.0",
                # Connection metadata is linked to the requester's IP address.
                # Downloads are optional; this is not an analytics permission.
                "data_collection_permissions": (
                    {"required": ["none"], "optional": ["personallyIdentifyingInfo"]}
                    if enable_remote
                    else {"required": ["none"]}
                ),
            }
        }
    elif browser != "chrome":
        raise ValueError("Unsupported browser")
    shutil.copytree(root / "extension", output)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "js/data-update-config.json").write_text(json.dumps(packaged, indent=2) + "\n")
    policy = {
        "approved": APPROVED_HISTORY,
        "excluded": {k: sorted(v) for k, v in EXCLUDED_HISTORY.items()},
        "preferred": PREFERRED_SOURCES,
    }
    (output / "js/data-schema-policy.json").write_text(
        json.dumps(policy, sort_keys=True, indent=2) + "\n"
    )
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--browser", required=True, choices=["chrome", "firefox"])
    parser.add_argument("--channel", default="production", choices=["production", "staging"])
    parser.add_argument("--enable-remote", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(build(args.output, args.browser, args.channel, args.enable_remote))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Build refused: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
